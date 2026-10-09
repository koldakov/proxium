import asyncio
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import Field, SecretStr

from proxium.api.services import BaseUserAuthenticatedService, RefreshToken
from proxium.db import Hash, Permission
from proxium.helpers import BaseSchema


class UpdateUserMePasswordRequest(BaseSchema):
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


class UpdateUserMePasswordResponse(BaseSchema):
    """A new token pair: the new password revokes the tokens issued before, these included."""

    access: str
    refresh: str


class UpdateUserMePasswordService(BaseUserAuthenticatedService[UpdateUserMePasswordResponse]):
    # Any active user, for themselves.
    required_permissions: ClassVar[frozenset[Permission]] = frozenset()

    data: UpdateUserMePasswordRequest

    async def process(self, *args, **kwargs) -> UpdateUserMePasswordResponse:
        # Hashing is slow CPU work, it would stall the loop.
        if not await asyncio.to_thread(self.user.password.verify, self.data.old_password.get_secret_value()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect.")

        self.user.set_password(await asyncio.to_thread(Hash.create, self.data.new_password.get_secret_value()))
        await self.session.commit()

        refresh_token: RefreshToken = RefreshToken.from_user(self.user)
        return UpdateUserMePasswordResponse(
            access=refresh_token.access_token.encode(),
            refresh=refresh_token.encode(),
        )
