from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field

from proxium.helpers import BaseSchema
from proxium.services import BaseUserAuthenticatedService


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


class GetUserMeService(BaseUserAuthenticatedService[GetUserMeResponse]):
    async def process(self, *args, **kwargs) -> GetUserMeResponse:
        return GetUserMeResponse.model_validate(self.user)
