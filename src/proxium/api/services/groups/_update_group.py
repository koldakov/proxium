from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, StringConstraints
from sqlalchemy import Delete, Result, Select, delete, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupModel, GroupPermissionModel, Permission
from proxium.helpers import BaseSchema


class UpdateGroupRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. `permissions` replaces the list."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ] = None
    permissions: set[Permission] | None = None


class UpdateGroupResponse(BaseSchema):
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


class UpdateGroupService(BaseUserAuthenticatedService[UpdateGroupResponse]):
    """A user can't give a group permissions they don't have, taking away is always allowed.

    The users of the group get the change with their next request.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.GROUPS_CHANGE})

    id: int
    data: UpdateGroupRequest

    @property
    def _get_group_statement(self) -> Select[tuple[GroupModel]]:
        return select(GroupModel).where(GroupModel.id == self.id)

    @property
    def _list_permissions_statement(self) -> Select[tuple[Permission]]:
        # One row per permission at most.
        return select(GroupPermissionModel.permission).where(GroupPermissionModel.group_id == self.id)

    def _insert_permissions_statement(self, permissions: set[Permission], /) -> Insert:
        # Another admin may have added the same meanwhile.
        return (
            insert(GroupPermissionModel)
            .values(
                [
                    {
                        "group_id": self.id,
                        "permission": permission,
                    }
                    for permission in permissions
                ],
            )
            .on_conflict_do_nothing()
        )

    def _delete_permissions_statement(self, permissions: set[Permission], /) -> Delete:
        return delete(GroupPermissionModel).where(
            GroupPermissionModel.group_id == self.id,
            GroupPermissionModel.permission.in_(permissions),
        )

    async def _update_permissions(self, permissions: set[Permission], /) -> None:
        result: Result[tuple[Permission]] = await self.session.execute(self._list_permissions_statement)
        current: set[Permission] = set(result.scalars())

        added: set[Permission] = permissions - current
        missing: set[Permission] = added - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You can't give permissions you don't have: {', '.join(sorted(missing))}.",
            )

        removed: set[Permission] = current - permissions
        if removed:
            await self.session.execute(self._delete_permissions_statement(removed))
        if added:
            await self.session.execute(self._insert_permissions_statement(added))

    async def process(self, *args, **kwargs) -> UpdateGroupResponse:
        result: Result[tuple[GroupModel]] = await self.session.execute(self._get_group_statement)
        try:
            group: GroupModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.") from None

        if self.data.permissions is not None:
            await self._update_permissions(self.data.permissions)
        if self.data.name is not None:
            group.name = self.data.name

        # Checking the name first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Name is already taken.",
                ) from None
            raise

        # `updated_at` comes from the database.
        await self.session.refresh(group)
        permissions_result: Result[tuple[Permission]] = await self.session.execute(self._list_permissions_statement)
        return UpdateGroupResponse(
            id=group.id,
            name=group.name,
            permissions=sorted(permissions_result.scalars()),
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
