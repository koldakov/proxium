from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, TrustedNetworkModel
from proxium.helpers import BaseSchema


class GetTrustedNetworkResponse(BaseSchema):
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


class GetTrustedNetworkService(BaseUserAuthenticatedService[GetTrustedNetworkResponse]):
    id: int

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

    async def process(self, *args, **kwargs) -> GetTrustedNetworkResponse:
        network: TrustedNetworkModel = await self._get_network()
        return GetTrustedNetworkResponse.model_validate(network)
