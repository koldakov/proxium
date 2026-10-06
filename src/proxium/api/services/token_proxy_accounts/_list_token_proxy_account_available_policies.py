from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Result, Select, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, PolicyModel, TokenProxyAccountModel, TokenProxyAccountPolicyModel
from proxium.helpers import BaseSchema


class ListTokenProxyAccountAvailablePoliciesRequest(BaseSchema):
    """Filters from the query string."""

    # Matches the name, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None


class ListTokenProxyAccountAvailablePoliciesResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool


class ListTokenProxyAccountAvailablePoliciesService(
    BaseUserAuthenticatedService[Page[ListTokenProxyAccountAvailablePoliciesResponse]],
):
    """Policies the account can take: not assigned yet and not global, those apply to it anyway."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset(
        {
            Permission.TOKEN_PROXY_ACCOUNTS_CHANGE,
            Permission.POLICIES_VIEW,
        },
    )

    id: int
    data: ListTokenProxyAccountAvailablePoliciesRequest

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    @property
    def _list_available_policies_statement(self) -> Select[tuple[PolicyModel]]:
        assigned = exists().where(
            TokenProxyAccountPolicyModel.token_proxy_account_id == self.id,
            TokenProxyAccountPolicyModel.policy_id == PolicyModel.id,
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

    async def _get_account(self) -> TokenProxyAccountModel:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTokenProxyAccountAvailablePoliciesResponse]:
        await self._get_account()

        return await apaginate(
            self.session,
            self._list_available_policies_statement,
        )
