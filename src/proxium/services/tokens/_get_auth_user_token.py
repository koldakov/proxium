import asyncio
import uuid
from typing import Annotated, ClassVar

from fastapi import HTTPException, status
from pydantic import EmailStr, Field, SecretStr
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.db import Hash, UserModel
from proxium.helpers import BaseSchema
from proxium.services import BaseSessionService, RefreshToken


class GetAuthUserTokenRequest(BaseSchema):
    email: Annotated[
        EmailStr,
        Field(
            max_length=255,
        ),
    ]
    password: Annotated[
        SecretStr,
        Field(
            min_length=1,
            max_length=128,
        ),
    ]


class GetAuthUserTokenResponse(BaseSchema):
    access: str
    refresh: str


class GetAuthUserTokenService(BaseSessionService[GetAuthUserTokenResponse]):
    data: GetAuthUserTokenRequest

    # Checked against when there is no user, so the answer takes as long as for a real one.
    _dummy_password_hash: ClassVar[Hash] = Hash.create(uuid.uuid4().hex)

    @property
    def _get_user_statement(self) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.email == self.data.email, UserModel.is_active.is_(True))

    async def process(self, *args, **kwargs) -> GetAuthUserTokenResponse:
        result: Result[tuple[UserModel]] = await self.session.execute(self._get_user_statement)
        try:
            user: UserModel = result.scalars().one()
        except NoResultFound:
            # Hash anyway: a fast 401 would tell that the email doesn't exist or the user is inactive.
            await asyncio.to_thread(self._dummy_password_hash.verify, self.data.password.get_secret_value())
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        # Hashing is slow CPU work, it would stall the loop.
        if not await asyncio.to_thread(user.password.verify, self.data.password.get_secret_value()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )

        refresh_token: RefreshToken = RefreshToken.from_user_id(user.id)
        return GetAuthUserTokenResponse(
            access=refresh_token.access_token.encode(),
            refresh=refresh_token.encode(),
        )
