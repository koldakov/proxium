from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, StringConstraints
from sqlalchemy import Result, Select, exists, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TrustedNetworkModel, TrustedNetworkOutgoingIPModel
from proxium.helpers import BaseSchema


class UpdateTrustedNetworkRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = None
    network: IPvAnyNetwork | None = None
    is_active: bool | None = None
    # `pool` needs IPs in the pool first.
    outgoing_mode: OutgoingMode | None = None


class UpdateTrustedNetworkResponse(BaseSchema):
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


class UpdateTrustedNetworkService(BaseUserAuthenticatedService[UpdateTrustedNetworkResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_CHANGE})

    id: int
    data: UpdateTrustedNetworkRequest

    @property
    def _lock_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        # Held till commit: pool and mode changes of the network take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id).with_for_update(key_share=True)

    @property
    def _has_pool_ips_statement(self) -> Select[tuple[bool]]:
        return select(
            exists().where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id),
        )

    async def _lock_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._lock_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def _check_pool_not_empty(self) -> None:
        """Raise 409 if the pool has no IPs: the `pool` mode needs one."""
        result: Result[tuple[bool]] = await self.session.execute(self._has_pool_ips_statement)
        if not result.scalars().one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The outgoing IP pool is empty, add IPs to it first.",
            )

    async def process(self, *args, **kwargs) -> UpdateTrustedNetworkResponse:
        network: TrustedNetworkModel = await self._lock_network()

        if self.data.outgoing_mode == OutgoingMode.POOL:
            await self._check_pool_not_empty()

        # Python mode keeps the network an `ipaddress` object, the column takes it as is.
        for field, value in self.data.model_dump(exclude_none=True).items():
            setattr(network, field, value)

        # Checking the network first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Network is already trusted.",
                ) from None
            raise

        # `updated_at` comes from the database.
        await self.session.refresh(network)
        return UpdateTrustedNetworkResponse.model_validate(network)
