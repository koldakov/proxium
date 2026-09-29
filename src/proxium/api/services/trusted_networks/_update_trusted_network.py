from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, StringConstraints
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TrustedNetworkModel
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
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class UpdateTrustedNetworkService(BaseUserAuthenticatedService[UpdateTrustedNetworkResponse]):
    id: int
    data: UpdateTrustedNetworkRequest

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    async def _get_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def process(self, *args, **kwargs) -> UpdateTrustedNetworkResponse:
        network: TrustedNetworkModel = await self._get_network()

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
