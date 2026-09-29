from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field, StringConstraints
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TokenProxyAccountModel
from proxium.helpers import BaseSchema


class UpdateTokenProxyAccountRequest(BaseSchema):
    """Only the name changes, the token is immutable."""

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]


class UpdateTokenProxyAccountResponse(BaseSchema):
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
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class UpdateTokenProxyAccountService(BaseUserAuthenticatedService[UpdateTokenProxyAccountResponse]):
    id: int
    data: UpdateTokenProxyAccountRequest

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> UpdateTokenProxyAccountResponse:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: TokenProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        account.name = self.data.name
        await self.session.commit()

        # `updated_at` comes from the database.
        await self.session.refresh(account)
        return UpdateTokenProxyAccountResponse.model_validate(account)
