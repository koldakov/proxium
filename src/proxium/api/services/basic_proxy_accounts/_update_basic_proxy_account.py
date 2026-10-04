from datetime import datetime
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import Field, StringConstraints
from sqlalchemy import Result, Select, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, BasicProxyAccountOutgoingIPModel, OutgoingMode, Permission
from proxium.helpers import BaseSchema


class UpdateBasicProxyAccountRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. The credentials are immutable."""

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


class UpdateBasicProxyAccountResponse(BaseSchema):
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


class UpdateBasicProxyAccountService(BaseUserAuthenticatedService[UpdateBasicProxyAccountResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.BASIC_PROXY_ACCOUNTS_CHANGE})

    id: int
    data: UpdateBasicProxyAccountRequest

    @property
    def _lock_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        # Held till commit: pool and mode changes of the account take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return (
            select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id).with_for_update(key_share=True)
        )

    @property
    def _has_pool_ips_statement(self) -> Select[tuple[bool]]:
        return select(
            exists().where(BasicProxyAccountOutgoingIPModel.basic_proxy_account_id == self.id),
        )

    async def _check_pool_not_empty(self) -> None:
        """Raise 409 if the pool has no IPs: the `pool` mode needs one."""
        result: Result[tuple[bool]] = await self.session.execute(self._has_pool_ips_statement)
        if not result.scalars().one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The outgoing IP pool is empty, add IPs to it first.",
            )

    async def _lock_account(self) -> BasicProxyAccountModel:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._lock_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> UpdateBasicProxyAccountResponse:
        account: BasicProxyAccountModel = await self._lock_account()

        if self.data.outgoing_mode == OutgoingMode.POOL:
            await self._check_pool_not_empty()

        if self.data.name is not None:
            account.name = self.data.name
        if self.data.outgoing_mode is not None:
            account.outgoing_mode = self.data.outgoing_mode
        await self.session.commit()

        # `updated_at` comes from the database.
        await self.session.refresh(account)
        return UpdateBasicProxyAccountResponse.model_validate(account)
