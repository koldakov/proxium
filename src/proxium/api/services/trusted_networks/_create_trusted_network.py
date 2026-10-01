from datetime import datetime
from typing import Annotated, Self

from asyncpg import ForeignKeyViolationError, UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, StringConstraints, model_validator
from sqlalchemy import Insert, Result, Select, distinct, func, insert, select
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.core import api_settings
from proxium.db import OutgoingIPModel, OutgoingMode, TrustedNetworkModel, TrustedNetworkOutgoingIPModel
from proxium.helpers import BaseSchema


class CreateTrustedNetworkRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    # `10.0.0.0/8`, or a single address like `10.0.0.1`. Host bits are rejected: `10.0.0.1/8` is a typo.
    network: IPvAnyNetwork
    is_active: bool = True
    outgoing_mode: OutgoingMode = OutgoingMode.SYSTEM
    # The pool, IPs of one family: at least one with `pool`, none with the other modes.
    outgoing_ip_ids: set[int] = Field(
        default_factory=set,
        max_length=api_settings.outgoing_pool_max_size,
    )

    @model_validator(mode="after")
    def _check_outgoing(self) -> Self:
        if (self.outgoing_mode == OutgoingMode.POOL) != bool(self.outgoing_ip_ids):
            raise ValueError("The pool mode needs outgoing IPs, the other modes take none.")
        return self


class CreateTrustedNetworkResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    network: IPvAnyNetwork
    is_active: bool
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateTrustedNetworkService(BaseUserAuthenticatedService[CreateTrustedNetworkResponse]):
    data: CreateTrustedNetworkRequest

    def _insert_outgoing_ips_statement(self, network_id: int, /) -> Insert:
        return insert(TrustedNetworkOutgoingIPModel).values(
            [
                {
                    "trusted_network_id": network_id,
                    "outgoing_ip_id": outgoing_ip_id,
                }
                for outgoing_ip_id in self.data.outgoing_ip_ids
            ],
        )

    @property
    def _count_pool_families_statement(self) -> Select[tuple[int]]:
        return select(func.count(distinct(func.family(OutgoingIPModel.ip)))).where(
            OutgoingIPModel.id.in_(self.data.outgoing_ip_ids),
        )

    async def _insert_outgoing_ips(self, network_id: int, /) -> None:
        """Fill the pool from the request ids, nothing is loaded. Raise 422 if an IP is missing or families mix."""
        try:
            await self.session.execute(self._insert_outgoing_ips_statement(network_id))
        except IntegrityError as err:
            if err.orig.sqlstate == ForeignKeyViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Outgoing IP not found.",
                ) from None
            raise

        # After the insert: its foreign keys hold the IPs, and an IP update waits for them, family included.
        result: Result[tuple[int]] = await self.session.execute(self._count_pool_families_statement)
        # An IPv4 source can't reach IPv6 targets: a mixed pool would fail at random.
        if result.scalars().one() > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Outgoing IPs of a pool must be of one family, IPv4 or IPv6.",
            )

    async def process(self, *args, **kwargs) -> CreateTrustedNetworkResponse:
        network: TrustedNetworkModel = TrustedNetworkModel(
            name=self.data.name,
            network=self.data.network,
            is_active=self.data.is_active,
            outgoing_mode=self.data.outgoing_mode,
            created_by_id=self.user.id,
        )
        self.session.add(network)

        # The id for the pool rows. Checking the network first would race.
        try:
            await self.session.flush()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Network is already trusted.",
                ) from None
            raise

        if self.data.outgoing_ip_ids:
            await self._insert_outgoing_ips(network.id)
        await self.session.commit()

        # Timestamps come from the database.
        await self.session.refresh(network)
        return CreateTrustedNetworkResponse.model_validate(network)
