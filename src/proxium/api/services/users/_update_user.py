from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import ForeignKeyViolationError, UniqueViolationError
from fastapi import HTTPException, status
from pydantic import EmailStr, Field, StringConstraints
from sqlalchemy import Delete, Result, Select, delete, distinct, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupPermissionModel, Permission, UserGroupModel, UserModel, UserPermissionModel
from proxium.helpers import BaseSchema


class UpdateUserRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. `groupIds` and `permissions` replace the lists."""

    email: Annotated[
        EmailStr | None,
        Field(
            max_length=255,
        ),
    ] = None
    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ] = None
    surname: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ] = None
    # An inactive user can't log in, and the tokens they have stop working.
    is_active: bool | None = None
    # Only a superuser changes it.
    is_superuser: bool | None = None
    group_ids: Annotated[
        set[int] | None,
        Field(
            max_length=100,
        ),
    ] = None
    # Given directly, besides the ones of the groups.
    permissions: set[Permission] | None = None


class UpdateUserResponse(BaseSchema):
    id: int
    email: Annotated[
        EmailStr,
        Field(
            max_length=255,
        ),
    ]
    name: Annotated[
        str,
        Field(
            max_length=150,
        ),
    ]
    surname: Annotated[
        str,
        Field(
            max_length=150,
        ),
    ]
    is_active: bool
    is_superuser: bool
    group_ids: list[int]
    permissions: list[Permission]
    created_at: datetime
    updated_at: datetime


class UpdateUserService(BaseUserAuthenticatedService[UpdateUserResponse]):
    """Change another user, or oneself the way an admin would.

    A user can't give more than they have: neither permissions nor groups with permissions they lack. Taking away is
    always allowed. Only superusers change superusers, and nobody locks themselves out.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.USERS_CHANGE})

    id: int
    data: UpdateUserRequest

    @property
    def _get_user_statement(self) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.id == self.id)

    @property
    def _list_group_ids_statement(self) -> Select[tuple[int]]:
        # The API keeps a user in at most 100 groups.
        return select(UserGroupModel.group_id).where(UserGroupModel.user_id == self.id).limit(100)

    @property
    def _list_permissions_statement(self) -> Select[tuple[Permission]]:
        # One row per permission at most.
        return select(UserPermissionModel.permission).where(UserPermissionModel.user_id == self.id)

    def _list_group_permissions_statement(self, group_ids: set[int], /) -> Select[tuple[Permission]]:
        # Distinct, so there are no more rows than permissions.
        return select(distinct(GroupPermissionModel.permission)).where(
            GroupPermissionModel.group_id.in_(group_ids),
        )

    def _insert_groups_statement(self, group_ids: set[int], /) -> Insert:
        # Another admin may have added the same meanwhile.
        return (
            insert(UserGroupModel)
            .values(
                [
                    {
                        "user_id": self.id,
                        "group_id": group_id,
                    }
                    for group_id in group_ids
                ],
            )
            .on_conflict_do_nothing()
        )

    def _delete_groups_statement(self, group_ids: set[int], /) -> Delete:
        return delete(UserGroupModel).where(
            UserGroupModel.user_id == self.id,
            UserGroupModel.group_id.in_(group_ids),
        )

    def _insert_permissions_statement(self, permissions: set[Permission], /) -> Insert:
        # Another admin may have added the same meanwhile.
        return (
            insert(UserPermissionModel)
            .values(
                [
                    {
                        "user_id": self.id,
                        "permission": permission,
                    }
                    for permission in permissions
                ],
            )
            .on_conflict_do_nothing()
        )

    def _delete_permissions_statement(self, permissions: set[Permission], /) -> Delete:
        return delete(UserPermissionModel).where(
            UserPermissionModel.user_id == self.id,
            UserPermissionModel.permission.in_(permissions),
        )

    async def _get_user(self) -> UserModel:
        result: Result[tuple[UserModel]] = await self.session.execute(self._get_user_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None

    def _check_status(self, user: UserModel, /) -> None:
        """Raise 403 if a superuser status is out of reach, 409 if the user would lock themselves out."""
        if user.is_superuser and not self.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can change superusers.",
            )
        if self.data.is_superuser is not None and self.data.is_superuser != user.is_superuser:
            if not self.user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only superusers can make superusers.",
                )
            if user.id == self.user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You can't stop being a superuser yourself, ask another one.",
                )
        if self.data.is_active is False and user.id == self.user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You can't deactivate yourself.",
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

    async def _update_groups(self, group_ids: set[int], /) -> None:
        result: Result[tuple[int]] = await self.session.execute(self._list_group_ids_statement)
        current: set[int] = set(result.scalars())

        added: set[int] = group_ids - current
        if added:
            permissions_result: Result[tuple[Permission]] = await self.session.execute(
                self._list_group_permissions_statement(added),
            )
            missing: set[Permission] = set(permissions_result.scalars()) - self.permissions
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"The groups have permissions you don't have: {', '.join(sorted(missing))}.",
                )

        removed: set[int] = current - group_ids
        if removed:
            await self.session.execute(self._delete_groups_statement(removed))
        if not added:
            return
        try:
            await self.session.execute(self._insert_groups_statement(added))
        except IntegrityError as err:
            if err.orig.sqlstate == ForeignKeyViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Group not found.",
                ) from None
            raise

    async def process(self, *args, **kwargs) -> UpdateUserResponse:
        user: UserModel = await self._get_user()
        self._check_status(user)

        if self.data.permissions is not None:
            await self._update_permissions(self.data.permissions)
        if self.data.group_ids is not None:
            await self._update_groups(self.data.group_ids)
        for field, value in self.data.model_dump(exclude_none=True, exclude={"group_ids", "permissions"}).items():
            setattr(user, field, value)

        # Checking the email first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email is already taken.",
                ) from None
            raise

        # `updated_at` comes from the database.
        await self.session.refresh(user)
        group_ids_result: Result[tuple[int]] = await self.session.execute(self._list_group_ids_statement)
        permissions_result: Result[tuple[Permission]] = await self.session.execute(self._list_permissions_statement)
        return UpdateUserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            surname=user.surname,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            group_ids=sorted(group_ids_result.scalars()),
            permissions=sorted(permissions_result.scalars()),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
