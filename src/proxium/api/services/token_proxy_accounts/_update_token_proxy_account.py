from datetime import datetime
from typing import Annotated, Any

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import AwareDatetime, Field, StringConstraints
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TokenProxyAccountModel
from proxium.helpers import BaseSchema


class UpdateTokenProxyAccountRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are, except `expires_at`: null there means never."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = None
    is_active: bool | None = None
    expires_at: AwareDatetime | None = None


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

    @property
    def _values(self) -> dict[str, Any]:
        values: dict[str, Any] = self.data.model_dump(exclude_none=True)
        if "expires_at" in self.data.model_fields_set:
            values["expires_at"] = self.data.expires_at

        return values

    async def process(self, *args, **kwargs) -> UpdateTokenProxyAccountResponse:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: TokenProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        for field, value in self._values.items():
            setattr(account, field, value)

        # Checking the name first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Name is already taken.",
                ) from None
            raise

        # `updated_at` comes from the database.
        await self.session.refresh(account)
        return UpdateTokenProxyAccountResponse.model_validate(account)
