from datetime import datetime
from typing import Annotated, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field
from sqlalchemy import Select, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, PolicyModel
from proxium.helpers import BaseSchema


class ListPoliciesResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=255,
        ),
    ]
    is_active: bool
    is_global: bool
    created_by_id: int
    created_at: datetime


class ListPoliciesService(BaseUserAuthenticatedService[Page[ListPoliciesResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.POLICIES_VIEW})

    # Matches the name, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None
    # Only global ones, or only the others. Both when missing.
    is_global: bool | None = None

    @property
    def _list_policies_statement(self) -> Select[tuple[PolicyModel]]:
        # By id after the name: names aren't unique, pages must not shuffle equal ones.
        statement: Select[tuple[PolicyModel]] = select(PolicyModel).order_by(PolicyModel.name, PolicyModel.id)
        if self.query is not None:
            statement = statement.where(PolicyModel.name.icontains(self.query, autoescape=True))
        if self.is_global is not None:
            statement = statement.where(PolicyModel.is_global.is_(self.is_global))

        return statement

    async def process(self, *args, **kwargs) -> Page[ListPoliciesResponse]:
        return await apaginate(
            self.session,
            self._list_policies_statement,
        )
