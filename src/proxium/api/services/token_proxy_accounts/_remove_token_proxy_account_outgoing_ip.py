from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, delete, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, TokenProxyAccountModel, TokenProxyAccountOutgoingIPModel

if TYPE_CHECKING:
    from sqlalchemy.sql.dml import ReturningDelete


class RemoveTokenProxyAccountOutgoingIPService(BaseUserAuthenticatedService[None]):
    """Take an IP out of the outgoing IP pool, the IP itself stays. The last one stays while the pool is in use."""

    id: int
    outgoing_ip_id: int

    @property
    def _lock_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        # Held till commit: pool and mode changes of the account take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return (
            select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id).with_for_update(key_share=True)
        )

    @property
    def _delete_outgoing_ip_statement(self) -> ReturningDelete[tuple[int]]:
        return (
            delete(TokenProxyAccountOutgoingIPModel)
            .where(
                TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id,
                TokenProxyAccountOutgoingIPModel.outgoing_ip_id == self.outgoing_ip_id,
            )
            .returning(TokenProxyAccountOutgoingIPModel.id)
        )

    @property
    def _has_pool_ips_statement(self) -> Select[tuple[bool]]:
        return select(
            exists().where(TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id),
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

    async def _check_pool_not_empty(self) -> None:
        """Raise 409 if the pool has no IPs: the `pool` mode needs one."""
        result: Result[tuple[bool]] = await self.session.execute(self._has_pool_ips_statement)
        if not result.scalars().one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last IP of a pool in use, switch the outgoing mode first.",
            )

    async def process(self, *args, **kwargs) -> None:
        account: TokenProxyAccountModel = await self._lock_account()

        result: Result[tuple[int]] = await self.session.execute(self._delete_outgoing_ip_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outgoing IP is not in the pool.",
            ) from None

        # Raised before the commit, so the delete is rolled back.
        if account.outgoing_mode == OutgoingMode.POOL:
            await self._check_pool_not_empty()

        await self.session.commit()
