from datetime import datetime
from typing import Annotated, Any, ClassVar

from fastapi import HTTPException, status
from pydantic import Field, field_validator
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupModel, Permission
from proxium.helpers import BaseSchema


class GetGroupResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            max_length=150,
        ),
    ]
    permissions: list[Permission]
    created_at: datetime
    updated_at: datetime

    @field_validator("permissions", mode="before")
    @classmethod
    def _permission_values(cls, value: Any) -> Any:
        # The model has rows, the response their permissions.
        return sorted(row.permission for row in value)


class GetGroupService(BaseUserAuthenticatedService[GetGroupResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.GROUPS_VIEW})

    id: int

    @property
    def _get_group_statement(self) -> Select[tuple[GroupModel]]:
        # One row per permission at most.
        return select(GroupModel).options(selectinload(GroupModel.permissions)).where(GroupModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetGroupResponse:
        result: Result[tuple[GroupModel]] = await self.session.execute(self._get_group_statement)
        try:
            group: GroupModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.") from None

        return GetGroupResponse.model_validate(group)
