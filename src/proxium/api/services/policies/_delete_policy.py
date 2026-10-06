from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Delete, Result, Select, delete, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import (
    BasicProxyAccountPolicyModel,
    Permission,
    PolicyConnectionLimitModel,
    PolicyModel,
    PolicyRuleModel,
    PolicySpeedLimitModel,
    PolicyTrafficQuotaModel,
    TokenProxyAccountPolicyModel,
    TrustedNetworkPolicyModel,
)


class DeletePolicyService(BaseUserAuthenticatedService[None]):
    """The policy is taken off its accounts and networks, which stay. The proxy drops it with its next lookup."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.POLICIES_DELETE})

    id: int

    @property
    def _get_policy_statement(self) -> Select[tuple[PolicyModel]]:
        # Locked: an assignment or a rule added meanwhile waits and then fails, instead of failing the delete.
        return select(PolicyModel).where(PolicyModel.id == self.id).with_for_update()

    @property
    def _list_rule_ids_statement(self) -> Select[tuple[int]]:
        return select(PolicyRuleModel.id).where(PolicyRuleModel.policy_id == self.id)

    @property
    def _delete_assignments_statements(self) -> tuple[Delete, ...]:
        return (
            delete(BasicProxyAccountPolicyModel).where(BasicProxyAccountPolicyModel.policy_id == self.id),
            delete(TokenProxyAccountPolicyModel).where(TokenProxyAccountPolicyModel.policy_id == self.id),
            delete(TrustedNetworkPolicyModel).where(TrustedNetworkPolicyModel.policy_id == self.id),
        )

    @property
    def _delete_limits_statements(self) -> tuple[Delete, ...]:
        rule_ids = self._list_rule_ids_statement
        return (
            delete(PolicyConnectionLimitModel).where(PolicyConnectionLimitModel.rule_id.in_(rule_ids)),
            delete(PolicySpeedLimitModel).where(PolicySpeedLimitModel.rule_id.in_(rule_ids)),
            delete(PolicyTrafficQuotaModel).where(PolicyTrafficQuotaModel.rule_id.in_(rule_ids)),
        )

    @property
    def _delete_rules_statement(self) -> Delete:
        return delete(PolicyRuleModel).where(PolicyRuleModel.policy_id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[PolicyModel]] = await self.session.execute(self._get_policy_statement)
        try:
            policy: PolicyModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found.",
            ) from None

        # One statement each, nothing is loaded. The foreign keys keep a policy with rows.
        for statement in self._delete_assignments_statements:
            await self.session.execute(statement)
        for statement in self._delete_limits_statements:
            await self.session.execute(statement)

        await self.session.execute(self._delete_rules_statement)
        await self.session.delete(policy)
        await self.session.commit()
