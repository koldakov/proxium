import asyncio
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import Field, SecretStr

from proxium.db import Hash
from proxium.helpers import BaseSchema
from proxium.services import BaseUserAuthenticatedService


class UpdateUserPasswordRequest(BaseSchema):
    """The new password is typed twice in the UI, only the old one is checked here."""

    old_password: Annotated[
        SecretStr,
        Field(
            min_length=1,
            max_length=128,
        ),
    ]
    new_password: Annotated[
        SecretStr,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]


class UpdateUserPasswordService(BaseUserAuthenticatedService[None]):
    data: UpdateUserPasswordRequest

    async def process(self, *args, **kwargs) -> None:
        # Hashing is slow CPU work, it would stall the loop.
        if not await asyncio.to_thread(self.user.password.verify, self.data.old_password.get_secret_value()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect.")

        self.user.password = await asyncio.to_thread(Hash.create, self.data.new_password.get_secret_value())
        await self.session.commit()
