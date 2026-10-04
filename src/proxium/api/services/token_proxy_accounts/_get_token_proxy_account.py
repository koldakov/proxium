from datetime import datetime
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TokenProxyAccountModel
from proxium.helpers import BaseSchema


class GetTokenProxyAccountResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    key: str
    is_active: bool
    expires_at: datetime | None
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class GetTokenProxyAccountService(BaseUserAuthenticatedService[GetTokenProxyAccountResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_VIEW})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetTokenProxyAccountResponse:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: TokenProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        return GetTokenProxyAccountResponse.model_validate(account)
