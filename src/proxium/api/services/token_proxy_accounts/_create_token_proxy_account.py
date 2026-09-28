import asyncio
import secrets
from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import AwareDatetime, Field, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.auth import TOKEN_PREFIX, TOKEN_SEPARATOR
from proxium.db import Hash, TokenProxyAccountModel
from proxium.helpers import BaseSchema


class CreateTokenProxyAccountRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    is_active: bool = True
    # Never expires when null.
    expires_at: AwareDatetime | None = None


class CreateTokenProxyAccountResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    key: str
    # Only here, the database keeps the hash.
    token: str
    is_active: bool
    expires_at: datetime | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateTokenProxyAccountService(BaseUserAuthenticatedService[CreateTokenProxyAccountResponse]):
    data: CreateTokenProxyAccountRequest

    async def process(self, *args, **kwargs) -> CreateTokenProxyAccountResponse:
        key: str = f"{TOKEN_PREFIX}{secrets.token_hex(8)}"
        token: str = f"{key}{TOKEN_SEPARATOR}{secrets.token_urlsafe(32)}"
        account: TokenProxyAccountModel = TokenProxyAccountModel(
            name=self.data.name,
            key=key,
            # Hashing is slow CPU work, it would stall the loop.
            token=await asyncio.to_thread(Hash.create, token),
            is_active=self.data.is_active,
            expires_at=self.data.expires_at,
            created_by_id=self.user.id,
        )
        self.session.add(account)

        # Checking the name first would race. A random key clash is too unlikely to tell apart.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Name is already taken.",
                ) from None
            raise

        # Timestamps come from the database.
        await self.session.refresh(account)
        return CreateTokenProxyAccountResponse(
            id=account.id,
            name=account.name,
            key=account.key,
            token=token,
            is_active=account.is_active,
            expires_at=account.expires_at,
            created_by_id=account.created_by_id,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
