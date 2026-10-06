from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, BasicProxyAccountPolicyModel, Permission, PolicyModel
from proxium.helpers import BaseSchema


class ListBasicProxyAccountPoliciesResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool


class ListBasicProxyAccountPoliciesService(BaseUserAuthenticatedService[Page[ListBasicProxyAccountPoliciesResponse]]):
    """The policies assigned to the account. Global ones apply too, without being listed here."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.BASIC_PROXY_ACCOUNTS_VIEW})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    @property
    def _list_policies_statement(self) -> Select[tuple[PolicyModel]]:
        # By id after the name: names aren't unique, pages must not shuffle equal ones.
        return (
            select(PolicyModel)
            .join(
                BasicProxyAccountPolicyModel,
                BasicProxyAccountPolicyModel.policy_id == PolicyModel.id,
            )
            .where(BasicProxyAccountPolicyModel.basic_proxy_account_id == self.id)
            .order_by(PolicyModel.name, PolicyModel.id)
        )

    async def _get_account(self) -> BasicProxyAccountModel:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListBasicProxyAccountPoliciesResponse]:
        # No policies give an empty page, a missing account a 404.
        await self._get_account()

        return await apaginate(
            self.session,
            self._list_policies_statement,
        )
