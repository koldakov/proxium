from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field, IPvAnyAddress
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel
from proxium.helpers import BaseSchema


class GetOutgoingIPResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    ip: IPvAnyAddress
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class GetOutgoingIPService(BaseUserAuthenticatedService[GetOutgoingIPResponse]):
    id: int

    @property
    def _get_outgoing_ip_statement(self) -> Select[tuple[OutgoingIPModel]]:
        return select(OutgoingIPModel).where(OutgoingIPModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetOutgoingIPResponse:
        result: Result[tuple[OutgoingIPModel]] = await self.session.execute(self._get_outgoing_ip_statement)
        try:
            outgoing_ip: OutgoingIPModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP not found.",
            ) from None

        return GetOutgoingIPResponse.model_validate(outgoing_ip)
