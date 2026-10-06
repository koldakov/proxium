from datetime import date
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import (
    Permission,
    PolicyModel,
    PolicyRuleModel,
    PolicyTrafficQuotaModel,
    TrustedNetworkModel,
    TrustedNetworkPolicyModel,
)
from proxium.helpers import BaseSchema


class ListTrustedNetworkPoliciesResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool
    # Of the assignment: quota periods count from this UTC day.
    starts_on: date
    # Only then `starts_on` matters.
    has_traffic_quotas: bool


class ListTrustedNetworkPoliciesService(BaseUserAuthenticatedService[Page[ListTrustedNetworkPoliciesResponse]]):
    """The policies assigned to the network. Global ones apply too, without being listed here."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_VIEW})

    id: int

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _list_policies_statement(self) -> Select[tuple[int, str, bool, bool, date, bool]]:
        has_traffic_quotas = (
            select(PolicyTrafficQuotaModel.id)
            .join(PolicyRuleModel, PolicyRuleModel.id == PolicyTrafficQuotaModel.rule_id)
            .where(PolicyRuleModel.policy_id == PolicyModel.id)
            .exists()
        )
        # By id after the name: names aren't unique, pages must not shuffle equal ones.
        return (
            select(
                PolicyModel.id,
                PolicyModel.name,
                PolicyModel.is_active,
                PolicyModel.is_global,
                TrustedNetworkPolicyModel.starts_on,
                has_traffic_quotas.label("has_traffic_quotas"),
            )
            .join(
                TrustedNetworkPolicyModel,
                TrustedNetworkPolicyModel.policy_id == PolicyModel.id,
            )
            .where(TrustedNetworkPolicyModel.trusted_network_id == self.id)
            .order_by(PolicyModel.name, PolicyModel.id)
        )

    async def _get_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTrustedNetworkPoliciesResponse]:
        # No policies give an empty page, a missing network a 404.
        await self._get_network()

        return await apaginate(
            self.session,
            self._list_policies_statement,
        )
