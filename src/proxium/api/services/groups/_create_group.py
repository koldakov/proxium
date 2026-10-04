from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, StringConstraints
from sqlalchemy import Insert, insert
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupModel, GroupPermissionModel, Permission
from proxium.helpers import BaseSchema


class CreateGroupRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ]
    permissions: set[Permission] = Field(
        default_factory=set,
    )


class CreateGroupResponse(BaseSchema):
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


class CreateGroupService(BaseUserAuthenticatedService[CreateGroupResponse]):
    """A user can't give a group permissions they don't have."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.GROUPS_ADD})

    data: CreateGroupRequest

    def _insert_permissions_statement(self, group_id: int, /) -> Insert:
        return insert(GroupPermissionModel).values(
            [
                {
                    "group_id": group_id,
                    "permission": permission,
                }
                for permission in self.data.permissions
            ],
        )

    async def process(self, *args, **kwargs) -> CreateGroupResponse:
        missing: set[Permission] = self.data.permissions - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You can't give permissions you don't have: {', '.join(sorted(missing))}.",
            )

        group: GroupModel = GroupModel(name=self.data.name)
        self.session.add(group)

        # Checking the name first would race.
        try:
            await self.session.flush()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Name is already taken.",
                ) from None
            raise

        if self.data.permissions:
            await self.session.execute(self._insert_permissions_statement(group.id))
        await self.session.commit()

        # Timestamps come from the database.
        await self.session.refresh(group)
        return CreateGroupResponse(
            id=group.id,
            name=group.name,
            permissions=sorted(self.data.permissions),
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
