from datetime import datetime
from typing import Annotated

from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import EmailStr, Field
from sqlalchemy import Select, or_, select

from proxium.db import UserModel
from proxium.helpers import BaseSchema
from proxium.services import BaseSessionService


class ListUsersResponse(BaseSchema):
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


class ListUsersService(BaseSessionService[Page[ListUsersResponse]]):
    params: Params
    # Matches email, name or surname, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None

    @property
    def _users_statement(self) -> Select[tuple[UserModel]]:
        statement: Select[tuple[UserModel]] = select(UserModel).order_by(UserModel.id.desc())
        if self.query is not None:
            statement = statement.where(
                or_(
                    UserModel.email.icontains(self.query, autoescape=True),
                    UserModel.name.icontains(self.query, autoescape=True),
                    UserModel.surname.icontains(self.query, autoescape=True),
                ),
            )

        return statement

    async def process(self, *args, **kwargs) -> Page[ListUsersResponse]:
        return await apaginate(
            self.session,
            self._users_statement,
            self.params,
            transformer=lambda users: [ListUsersResponse.model_validate(user) for user in users],
        )
