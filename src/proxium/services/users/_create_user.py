import asyncio
from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import EmailStr, Field, SecretStr, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.db import Hash, UserModel
from proxium.helpers import BaseSchema
from proxium.services import BaseSessionService


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
    created_at: datetime
    updated_at: datetime


class CreateUserService(BaseSessionService[CreateUserResponse]):
    data: CreateUserRequest

    async def process(self, *args, **kwargs) -> CreateUserResponse:
        user: UserModel = UserModel(
            email=self.data.email,
            name=self.data.name,
            surname=self.data.surname,
            # Hashing is slow CPU work, it would stall the loop.
            password=await asyncio.to_thread(Hash.create, self.data.password.get_secret_value()),
        )
        self.session.add(user)

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

        # Timestamps come from the database.
        await self.session.refresh(user)
        return CreateUserResponse.model_validate(user)
