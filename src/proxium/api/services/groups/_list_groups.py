from datetime import datetime
from typing import Annotated, Any, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, field_validator
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupModel, Permission
from proxium.helpers import BaseSchema


class ListGroupsResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=150,
        ),
    ]
    permissions: list[Permission]
    created_at: datetime

    @field_validator("permissions", mode="before")
    @classmethod
    def _permission_values(cls, value: Any) -> Any:
        # The model has rows, the response their permissions.
        return sorted(row.permission for row in value)


class ListGroupsService(BaseUserAuthenticatedService[Page[ListGroupsResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.GROUPS_VIEW})

    # Matches the name, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None

    @property
    def _list_groups_statement(self) -> Select[tuple[GroupModel]]:
        # A group has at most one row per permission, so a page loads a bounded number of them.
        statement: Select[tuple[GroupModel]] = (
            select(GroupModel).options(selectinload(GroupModel.permissions)).order_by(GroupModel.name)
        )
        if self.query is not None:
            statement = statement.where(GroupModel.name.icontains(self.query, autoescape=True))

        return statement

    async def process(self, *args, **kwargs) -> Page[ListGroupsResponse]:
        return await apaginate(
            self.session,
            self._list_groups_statement,
        )
