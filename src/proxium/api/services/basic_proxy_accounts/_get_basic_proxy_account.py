from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, OutgoingMode
from proxium.helpers import BaseSchema


class GetBasicProxyAccountResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    username: str
    is_active: bool
    expires_at: datetime | None
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class GetBasicProxyAccountService(BaseUserAuthenticatedService[GetBasicProxyAccountResponse]):
    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetBasicProxyAccountResponse:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: BasicProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        return GetBasicProxyAccountResponse.model_validate(account)
