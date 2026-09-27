from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import EmailStr, Field
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseSessionService
from proxium.db import UserModel
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


class GetUserService(BaseSessionService[GetUserResponse]):
    id: int

    @property
    def _user_statement(self) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetUserResponse:
        result: Result[tuple[UserModel]] = await self.session.execute(self._user_statement)
        try:
            user: UserModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None

        return GetUserResponse.model_validate(user)
