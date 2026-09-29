import asyncio
import secrets
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints

from proxium.api.services import BaseUserAuthenticatedService
from proxium.auth import USERNAME_PREFIX
from proxium.db import BasicProxyAccountModel, Hash
from proxium.helpers import BaseSchema


class CreateBasicProxyAccountRequest(BaseSchema):
    """The username and password are generated."""

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    # Never expires when null.
    expires_at: AwareDatetime | None = None


class CreateBasicProxyAccountResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    username: str
    # Only here, the database keeps the hash.
    password: str
    is_active: bool
    expires_at: datetime | None
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateBasicProxyAccountService(BaseUserAuthenticatedService[CreateBasicProxyAccountResponse]):
    data: CreateBasicProxyAccountRequest

    async def process(self, *args, **kwargs) -> CreateBasicProxyAccountResponse:
        # A random username clash is too unlikely to tell apart.
        username: str = f"{USERNAME_PREFIX}{secrets.token_hex(8)}"
        password: str = secrets.token_urlsafe(32)
        account: BasicProxyAccountModel = BasicProxyAccountModel(
            name=self.data.name,
            username=username,
            # Hashing is slow CPU work, it would stall the loop.
            password=await asyncio.to_thread(Hash.create, password),
            expires_at=self.data.expires_at,
            created_by_id=self.user.id,
        )
        self.session.add(account)
        await self.session.commit()

        # Timestamps come from the database.
        await self.session.refresh(account)
        return CreateBasicProxyAccountResponse(
            id=account.id,
            name=account.name,
            username=account.username,
            password=password,
            is_active=account.is_active,
            expires_at=account.expires_at,
            created_by_id=account.created_by_id,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
