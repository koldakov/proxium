from datetime import datetime
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import EmailStr, Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, UserGroupModel, UserModel, UserPermissionModel
from proxium.helpers import BaseSchema


class GetUserResponse(BaseSchema):
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
    # Given directly, the groups have their own.
    permissions: list[Permission]
    created_at: datetime
    updated_at: datetime


class GetUserService(BaseUserAuthenticatedService[GetUserResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.USERS_VIEW})

    id: int

    @property
    def _user_statement(self) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.id == self.id)

    @property
    def _list_group_ids_statement(self) -> Select[tuple[int]]:
        # The API keeps a user in at most 100 groups.
        return (
            select(UserGroupModel.group_id)
            .where(UserGroupModel.user_id == self.id)
            .order_by(UserGroupModel.group_id)
            .limit(100)
        )

    @property
    def _list_permissions_statement(self) -> Select[tuple[Permission]]:
        # One row per permission at most.
        return (
            select(UserPermissionModel.permission)
            .where(UserPermissionModel.user_id == self.id)
            .order_by(UserPermissionModel.permission)
        )

    async def process(self, *args, **kwargs) -> GetUserResponse:
        result: Result[tuple[UserModel]] = await self.session.execute(self._user_statement)
        try:
            user: UserModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None

        group_ids_result: Result[tuple[int]] = await self.session.execute(self._list_group_ids_statement)
        permissions_result: Result[tuple[Permission]] = await self.session.execute(self._list_permissions_statement)
        return GetUserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            surname=user.surname,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            group_ids=list(group_ids_result.scalars()),
            permissions=list(permissions_result.scalars()),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
