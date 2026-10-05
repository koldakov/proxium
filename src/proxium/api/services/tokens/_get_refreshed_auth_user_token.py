from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseSessionService, RefreshToken, TokenError
from proxium.db import UserModel
from proxium.helpers import BaseSchema


class GetRefreshedAuthUserTokenRequest(BaseSchema):
    refresh: str


class GetRefreshedAuthUserTokenResponse(BaseSchema):
    access: str
    refresh: str


class GetRefreshedAuthUserTokenService(BaseSessionService[GetRefreshedAuthUserTokenResponse]):
    data: GetRefreshedAuthUserTokenRequest

    @property
    def _refresh_token(self) -> RefreshToken:
        try:
            return RefreshToken.decode(self.data.refresh)
        except TokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired, log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    @property
    def _get_user_statement(self) -> Select[tuple[UserModel]]:
        # The user may be deactivated since the token was issued.
        return select(UserModel).where(
            UserModel.id == self._refresh_token.user.id,
            UserModel.is_active.is_(True),
        )

    async def _get_user(self) -> UserModel:
        result: Result[tuple[UserModel]] = await self.session.execute(self._get_user_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired, log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    async def process(self, *args, **kwargs) -> GetRefreshedAuthUserTokenResponse:
        user: UserModel = await self._get_user()
        # The same answer as for an expired token: the holder isn't told why, the token may be stolen.
        if not self._refresh_token.user.has_password_of(user):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired, log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        refresh_token: RefreshToken = RefreshToken.from_user(user)
        return GetRefreshedAuthUserTokenResponse(
            access=refresh_token.access_token.encode(),
            refresh=refresh_token.encode(),
        )
