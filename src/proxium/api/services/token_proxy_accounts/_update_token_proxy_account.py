from datetime import datetime
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import Field, StringConstraints
from sqlalchemy import Result, Select, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TokenProxyAccountModel, TokenProxyAccountOutgoingIPModel
from proxium.helpers import BaseSchema


class UpdateTokenProxyAccountRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. The token is immutable."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = None
    # `pool` needs IPs in the pool first.
    outgoing_mode: OutgoingMode | None = None


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
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class UpdateTokenProxyAccountService(BaseUserAuthenticatedService[UpdateTokenProxyAccountResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_CHANGE})

    id: int
    data: UpdateTokenProxyAccountRequest

    @property
    def _lock_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        # Held till commit: pool and mode changes of the account take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return (
            select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id).with_for_update(key_share=True)
        )

    @property
    def _has_pool_ips_statement(self) -> Select[tuple[bool]]:
        return select(
            exists().where(TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id),
        )

    async def _check_pool_not_empty(self) -> None:
        """Raise 409 if the pool has no IPs: the `pool` mode needs one."""
        result: Result[tuple[bool]] = await self.session.execute(self._has_pool_ips_statement)
        if not result.scalars().one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The outgoing IP pool is empty, add IPs to it first.",
            )

    async def _lock_account(self) -> TokenProxyAccountModel:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._lock_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> UpdateTokenProxyAccountResponse:
        account: TokenProxyAccountModel = await self._lock_account()

        if self.data.outgoing_mode == OutgoingMode.POOL:
            await self._check_pool_not_empty()

        if self.data.name is not None:
            account.name = self.data.name
        if self.data.outgoing_mode is not None:
            account.outgoing_mode = self.data.outgoing_mode
        await self.session.commit()

        # `updated_at` comes from the database.
        await self.session.refresh(account)
        return UpdateTokenProxyAccountResponse.model_validate(account)
