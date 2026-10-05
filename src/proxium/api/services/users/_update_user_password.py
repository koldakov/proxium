import asyncio
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import Field, SecretStr
from sqlalchemy import CompoundSelect, Result, Select, select, union
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupPermissionModel, Hash, Permission, UserGroupModel, UserModel, UserPermissionModel
from proxium.helpers import BaseSchema


class UpdateUserPasswordRequest(BaseSchema):
    """The password is typed twice in the UI."""

    password: Annotated[
        SecretStr,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]


class UpdateUserPasswordService(BaseUserAuthenticatedService[None]):
    """Set another user's password, e.g. a forgotten one.

    The password lets one log in as the user, so only a user with all their permissions sets it: otherwise it would
    give more than one has. Only superusers set superusers' passwords. One's own password needs the old one, see
    `UpdateUserMePasswordService`.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.USERS_CHANGE})

    id: int
    data: UpdateUserPasswordRequest

    @property
    def _get_user_statement(self) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.id == self.id)

    @property
    def _list_permissions_statement(self) -> CompoundSelect:
        # `union` drops duplicates, so there are no more rows than permissions.
        return union(
            select(UserPermissionModel.permission).where(UserPermissionModel.user_id == self.id),
            select(GroupPermissionModel.permission)
            .join(UserGroupModel, UserGroupModel.group_id == GroupPermissionModel.group_id)
            .where(UserGroupModel.user_id == self.id),
        )

    async def _get_user(self) -> UserModel:
        result: Result[tuple[UserModel]] = await self.session.execute(self._get_user_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None

    async def _check_access(self, user: UserModel, /) -> None:
        """Raise 409 for oneself, 403 if the user may do what the logged-in one may not."""
        if user.id == self.user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Change your own password under Profile.",
            )
        if user.is_superuser and not self.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can set superusers' passwords.",
            )

        result: Result[tuple[Permission]] = await self.session.execute(self._list_permissions_statement)
        missing: set[Permission] = set(result.scalars()) - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The user has permissions you don't have: {', '.join(sorted(missing))}.",
            )

    async def process(self, *args, **kwargs) -> None:
        user: UserModel = await self._get_user()
        await self._check_access(user)

        # Hashing is slow CPU work, it would stall the loop.
        user.password = await asyncio.to_thread(Hash.create, self.data.password.get_secret_value())
        await self.session.commit()
