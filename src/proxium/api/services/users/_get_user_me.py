from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import EmailStr, Field

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission
from proxium.helpers import BaseSchema


class GetUserMeResponse(BaseSchema):
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
    # What the user may do, every permission for a superuser. The admin UI hides the rest.
    permissions: list[Permission]
    created_at: datetime
    updated_at: datetime


class GetUserMeService(BaseUserAuthenticatedService[GetUserMeResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset()

    async def process(self, *args, **kwargs) -> GetUserMeResponse:
        return GetUserMeResponse(
            id=self.user.id,
            email=self.user.email,
            name=self.user.name,
            surname=self.user.surname,
            is_active=self.user.is_active,
            is_superuser=self.user.is_superuser,
            permissions=sorted(self.permissions),
            created_at=self.user.created_at,
            updated_at=self.user.updated_at,
        )
