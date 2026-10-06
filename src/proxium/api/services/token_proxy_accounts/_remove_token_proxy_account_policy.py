from typing import TYPE_CHECKING, ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, delete
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, TokenProxyAccountPolicyModel

if TYPE_CHECKING:
    from sqlalchemy.sql.dml import ReturningDelete


class RemoveTokenProxyAccountPolicyService(BaseUserAuthenticatedService[None]):
    """Take a policy off the account, the policy itself stays."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_CHANGE})

    id: int
    policy_id: int

    @property
    def _delete_policy_statement(self) -> ReturningDelete[tuple[int]]:
        return (
            delete(TokenProxyAccountPolicyModel)
            .where(
                TokenProxyAccountPolicyModel.token_proxy_account_id == self.id,
                TokenProxyAccountPolicyModel.policy_id == self.policy_id,
            )
            .returning(TokenProxyAccountPolicyModel.id)
        )

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[int]] = await self.session.execute(self._delete_policy_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found, or the policy is not assigned to it.",
            ) from None

        await self.session.commit()
