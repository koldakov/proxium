import asyncio
from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import AwareDatetime, Field, SecretStr, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, Hash
from proxium.helpers import BaseSchema


class CreateBasicProxyAccountRequest(BaseSchema):
    # Basic auth splits `username:password` at the first colon.
    username: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
            pattern=r"^[^:]+$",
        ),
    ]
    password: Annotated[
        SecretStr,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]
    is_active: bool = True
    # Never expires when null.
    expires_at: AwareDatetime | None = None


class CreateBasicProxyAccountResponse(BaseSchema):
    id: int
    username: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    is_active: bool
    expires_at: datetime | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateBasicProxyAccountService(BaseUserAuthenticatedService[CreateBasicProxyAccountResponse]):
    data: CreateBasicProxyAccountRequest

    async def process(self, *args, **kwargs) -> CreateBasicProxyAccountResponse:
        account: BasicProxyAccountModel = BasicProxyAccountModel(
            username=self.data.username,
            # Hashing is slow CPU work, it would stall the loop.
            password=await asyncio.to_thread(Hash.create, self.data.password.get_secret_value()),
            is_active=self.data.is_active,
            expires_at=self.data.expires_at,
            created_by_id=self.user.id,
        )
        self.session.add(account)

        # Checking the username first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is already taken.",
                ) from None
            raise

        # Timestamps come from the database.
        await self.session.refresh(account)
        return CreateBasicProxyAccountResponse.model_validate(account)
