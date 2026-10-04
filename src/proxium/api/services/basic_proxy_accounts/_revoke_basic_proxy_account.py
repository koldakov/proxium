from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, Permission


class RevokeBasicProxyAccountService(BaseUserAuthenticatedService[None]):
    """Stop the credentials for good, e.g. after a leak. There is no way back, create a new account instead."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.BASIC_PROXY_ACCOUNTS_REVOKE})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            account: BasicProxyAccountModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        account.is_active = False
        await self.session.commit()
