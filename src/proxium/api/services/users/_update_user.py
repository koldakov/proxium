from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import EmailStr, Field, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.helpers import BaseSchema


class UpdateUserRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are."""

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
            min_length=1,
            max_length=150,
        ),
    ]
    surname: Annotated[
        str,
        Field(
            min_length=1,
            max_length=150,
        ),
    ]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class UpdateUserService(BaseUserAuthenticatedService[UpdateUserResponse]):
    data: UpdateUserRequest

    async def process(self, *args, **kwargs) -> UpdateUserResponse:
        for field, value in self.data.model_dump(exclude_none=True).items():
            setattr(self.user, field, value)

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
        await self.session.refresh(self.user)
        return UpdateUserResponse.model_validate(self.user)
