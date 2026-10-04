import asyncio
import secrets
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Self

from asyncpg import ForeignKeyViolationError
from fastapi import HTTPException, status
from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import Insert, Result, Select, distinct, func, insert, select
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.auth import USERNAME_PREFIX
from proxium.core import api_settings
from proxium.db import (
    BasicProxyAccountModel,
    BasicProxyAccountOutgoingIPModel,
    Hash,
    OutgoingIPModel,
    OutgoingMode,
    Permission,
)
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
    outgoing_mode: OutgoingMode = OutgoingMode.SYSTEM
    # The pool, IPs of one family: at least one with `pool`, none with the other modes.
    outgoing_ip_ids: set[int] = Field(
        default_factory=set,
        max_length=api_settings.outgoing_pool_max_size,
    )

    @field_validator("expires_at")
    @classmethod
    def _check_expires_at(cls, value: datetime | None) -> datetime | None:
        # Expiry is immutable: an account born expired could never be used.
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("Must be in the future.")
        return value

    @model_validator(mode="after")
    def _check_outgoing(self) -> Self:
        if (self.outgoing_mode == OutgoingMode.POOL) != bool(self.outgoing_ip_ids):
            raise ValueError("The pool mode needs outgoing IPs, the other modes take none.")
        return self


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
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateBasicProxyAccountService(BaseUserAuthenticatedService[CreateBasicProxyAccountResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.BASIC_PROXY_ACCOUNTS_ADD})

    data: CreateBasicProxyAccountRequest

    def _insert_outgoing_ips_statement(self, account_id: int, /) -> Insert:
        return insert(BasicProxyAccountOutgoingIPModel).values(
            [
                {
                    "basic_proxy_account_id": account_id,
                    "outgoing_ip_id": outgoing_ip_id,
                }
                for outgoing_ip_id in self.data.outgoing_ip_ids
            ],
        )

    @property
    def _count_pool_families_statement(self) -> Select[tuple[int]]:
        return select(func.count(distinct(func.family(OutgoingIPModel.ip)))).where(
            OutgoingIPModel.id.in_(self.data.outgoing_ip_ids),
        )

    async def _insert_outgoing_ips(self, account_id: int, /) -> None:
        """Fill the pool from the request ids, nothing is loaded. Raise 422 if an IP is missing or families mix."""
        try:
            await self.session.execute(self._insert_outgoing_ips_statement(account_id))
        except IntegrityError as err:
            if err.orig.sqlstate == ForeignKeyViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Outgoing IP not found.",
                ) from None
            raise

        # After the insert: its foreign keys hold the IPs, and an IP update waits for them, family included.
        result: Result[tuple[int]] = await self.session.execute(self._count_pool_families_statement)
        # An IPv4 source can't reach IPv6 targets: a mixed pool would fail at random.
        if result.scalars().one() > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Outgoing IPs of a pool must be of one family, IPv4 or IPv6.",
            )

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
            outgoing_mode=self.data.outgoing_mode,
            created_by_id=self.user.id,
        )
        self.session.add(account)
        # The id for the pool rows.
        await self.session.flush()
        if self.data.outgoing_ip_ids:
            await self._insert_outgoing_ips(account.id)
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
            outgoing_mode=account.outgoing_mode,
            created_by_id=account.created_by_id,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
