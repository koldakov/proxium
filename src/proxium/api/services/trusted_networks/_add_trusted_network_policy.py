from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, func, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.core import api_settings
from proxium.db import Permission, PolicyModel, TrustedNetworkModel, TrustedNetworkPolicyModel


class AddTrustedNetworkPolicyService(BaseUserAuthenticatedService[None]):
    """Assign a policy. Assigning it again changes nothing. A global policy applies anyway, so it's refused."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_CHANGE})

    id: int
    policy_id: int

    @property
    def _lock_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        # Held till commit: assignments to the network take turns, the cap holds.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id).with_for_update(key_share=True)

    @property
    def _lock_policy_statement(self) -> Select[tuple[PolicyModel]]:
        # Shared lock: the policy can't be deleted until it's assigned.
        return select(PolicyModel).where(PolicyModel.id == self.policy_id).with_for_update(read=True)

    @property
    def _insert_policy_statement(self) -> Insert:
        return (
            insert(TrustedNetworkPolicyModel)
            .values(
                trusted_network_id=self.id,
                policy_id=self.policy_id,
            )
            .on_conflict_do_nothing()
        )

    @property
    def _count_policies_statement(self) -> Select[tuple[int]]:
        return (
            select(func.count())
            .select_from(TrustedNetworkPolicyModel)
            .where(TrustedNetworkPolicyModel.trusted_network_id == self.id)
        )

    async def _lock_network(self) -> None:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._lock_network_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def _lock_policy(self) -> PolicyModel:
        result: Result[tuple[PolicyModel]] = await self.session.execute(self._lock_policy_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found.",
            ) from None

    async def process(self, *args, **kwargs) -> None:
        await self._lock_network()
        policy: PolicyModel = await self._lock_policy()
        if policy.is_global:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The policy is global, it applies to every client already.",
            )

        # Counted after the insert, so assigning a policy again never hits the cap.
        await self.session.execute(self._insert_policy_statement)
        result: Result[tuple[int]] = await self.session.execute(self._count_policies_statement)
        if result.scalars().one() > api_settings.policies_max_per_owner:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Too many policies, at most {api_settings.policies_max_per_owner}.",
            )

        await self.session.commit()
