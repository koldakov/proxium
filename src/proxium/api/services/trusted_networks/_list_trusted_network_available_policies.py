from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Result, Select, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, PolicyModel, TrustedNetworkModel, TrustedNetworkPolicyModel
from proxium.helpers import BaseSchema


class ListTrustedNetworkAvailablePoliciesRequest(BaseSchema):
    """Filters from the query string."""

    # Matches the name, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None


class ListTrustedNetworkAvailablePoliciesResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool


class ListTrustedNetworkAvailablePoliciesService(
    BaseUserAuthenticatedService[Page[ListTrustedNetworkAvailablePoliciesResponse]],
):
    """Policies the network can take: not assigned yet and not global, those apply to it anyway."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset(
        {
            Permission.TRUSTED_NETWORKS_CHANGE,
            Permission.POLICIES_VIEW,
        },
    )

    id: int
    data: ListTrustedNetworkAvailablePoliciesRequest

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _list_available_policies_statement(self) -> Select[tuple[PolicyModel]]:
        assigned = exists().where(
            TrustedNetworkPolicyModel.trusted_network_id == self.id,
            TrustedNetworkPolicyModel.policy_id == PolicyModel.id,
        )

        # By id after the name: names aren't unique, pages must not shuffle equal ones.
        statement: Select[tuple[PolicyModel]] = (
            select(PolicyModel)
            .where(
                ~assigned,
                PolicyModel.is_global.is_(False),
            )
            .order_by(PolicyModel.name, PolicyModel.id)
        )
        if self.data.query is not None:
            statement = statement.where(PolicyModel.name.icontains(self.data.query, autoescape=True))

        return statement

    async def _get_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTrustedNetworkAvailablePoliciesResponse]:
        await self._get_network()

        return await apaginate(
            self.session,
            self._list_available_policies_statement,
        )
