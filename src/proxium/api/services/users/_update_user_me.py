from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import EmailStr, Field, StringConstraints

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission  # noqa: TC001, pydantic reads annotations at runtime.
from proxium.helpers import BaseSchema


class UpdateUserMeRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are. The email is the login, an admin changes it."""

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


class UpdateUserMeResponse(BaseSchema):
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
    created_at: datetime
    updated_at: datetime


class UpdateUserMeService(BaseUserAuthenticatedService[UpdateUserMeResponse]):
    # Any active user, for themselves.
    required_permissions: ClassVar[frozenset[Permission]] = frozenset()

    data: UpdateUserMeRequest

    async def process(self, *args, **kwargs) -> UpdateUserMeResponse:
        for field, value in self.data.model_dump(exclude_none=True).items():
            setattr(self.user, field, value)
        await self.session.commit()

        # `updated_at` comes from the database.
        await self.session.refresh(self.user)
        return UpdateUserMeResponse.model_validate(self.user)
