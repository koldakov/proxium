from datetime import date
from typing import TYPE_CHECKING, ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, update
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, TokenProxyAccountPolicyModel
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from sqlalchemy.sql.dml import ReturningUpdate


class UpdateTokenProxyAccountPolicyRequest(BaseSchema):
    # Quota periods of the policy count from this UTC day for the account, e.g. the day it paid.
    starts_on: date


class UpdateTokenProxyAccountPolicyService(BaseUserAuthenticatedService[None]):
    """Change how a policy is assigned to the account."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TOKEN_PROXY_ACCOUNTS_CHANGE})

    id: int
    policy_id: int
    data: UpdateTokenProxyAccountPolicyRequest

    @property
    def _update_policy_statement(self) -> ReturningUpdate[tuple[int]]:
        return (
            update(TokenProxyAccountPolicyModel)
            .where(
                TokenProxyAccountPolicyModel.token_proxy_account_id == self.id,
                TokenProxyAccountPolicyModel.policy_id == self.policy_id,
            )
            .values(
                starts_on=self.data.starts_on,
            )
            .returning(TokenProxyAccountPolicyModel.id)
        )

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[int]] = await self.session.execute(self._update_policy_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found, or the policy is not assigned to it.",
            ) from None

        await self.session.commit()
