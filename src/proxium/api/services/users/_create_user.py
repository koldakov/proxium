import asyncio
from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import ForeignKeyViolationError, UniqueViolationError
from fastapi import HTTPException, status
from pydantic import EmailStr, Field, SecretStr, StringConstraints
from sqlalchemy import Insert, Result, Select, distinct, insert, select
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupPermissionModel, Hash, Permission, UserGroupModel, UserModel, UserPermissionModel
from proxium.helpers import BaseSchema


class CreateUserRequest(BaseSchema):
    email: Annotated[
        EmailStr,
        Field(
            max_length=255,
        ),
    ]
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ]
    surname: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=150,
        ),
    ]
    password: Annotated[
        SecretStr,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]
    is_active: bool = True
    # Only a superuser makes one.
    is_superuser: bool = False
    group_ids: set[int] = Field(
        default_factory=set,
        max_length=100,
    )
    # Given directly, besides the ones of the groups.
    permissions: set[Permission] = Field(
        default_factory=set,
    )


class CreateUserResponse(BaseSchema):
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


class CreateUserService(BaseUserAuthenticatedService[CreateUserResponse]):
    """A user can't give more than they have: neither permissions nor groups with permissions they lack."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.USERS_ADD})

    data: CreateUserRequest

    @property
    def _list_group_permissions_statement(self) -> Select[tuple[Permission]]:
        # Distinct, so there are no more rows than permissions.
        return select(distinct(GroupPermissionModel.permission)).where(
            GroupPermissionModel.group_id.in_(self.data.group_ids),
        )

    def _insert_groups_statement(self, user_id: int, /) -> Insert:
        return insert(UserGroupModel).values(
            [
                {
                    "user_id": user_id,
                    "group_id": group_id,
                }
                for group_id in self.data.group_ids
            ],
        )

    def _insert_permissions_statement(self, user_id: int, /) -> Insert:
        return insert(UserPermissionModel).values(
            [
                {
                    "user_id": user_id,
                    "permission": permission,
                }
                for permission in self.data.permissions
            ],
        )

    async def _check_grants(self) -> None:
        if self.data.is_superuser and not self.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can make superusers.",
            )

        missing: set[Permission] = self.data.permissions - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You can't give permissions you don't have: {', '.join(sorted(missing))}.",
            )

        if not self.data.group_ids:
            return
        result: Result[tuple[Permission]] = await self.session.execute(self._list_group_permissions_statement)
        missing = set(result.scalars()) - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The groups have permissions you don't have: {', '.join(sorted(missing))}.",
            )

    async def _insert_groups(self, user_id: int, /) -> None:
        """Add the user to the groups by the request ids, nothing is loaded. Raise 422 if a group is missing."""
        try:
            await self.session.execute(self._insert_groups_statement(user_id))
        except IntegrityError as err:
            if err.orig.sqlstate == ForeignKeyViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Group not found.",
                ) from None
            raise

    async def process(self, *args, **kwargs) -> CreateUserResponse:
        await self._check_grants()

        user: UserModel = UserModel(
            email=self.data.email,
            name=self.data.name,
            surname=self.data.surname,
            # Hashing is slow CPU work, it would stall the loop.
            password=await asyncio.to_thread(Hash.create, self.data.password.get_secret_value()),
            is_active=self.data.is_active,
            is_superuser=self.data.is_superuser,
        )
        self.session.add(user)

        # Checking the email first would race.
        try:
            await self.session.flush()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email is already taken.",
                ) from None
            raise

        if self.data.group_ids:
            await self._insert_groups(user.id)
        if self.data.permissions:
            await self.session.execute(self._insert_permissions_statement(user.id))
        await self.session.commit()

        # Timestamps come from the database.
        await self.session.refresh(user)
        return CreateUserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            surname=user.surname,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            group_ids=sorted(self.data.group_ids),
            permissions=sorted(self.data.permissions),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
