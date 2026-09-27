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
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    async def process(self, *args, **kwargs) -> GetRefreshedAuthUserTokenResponse:
        user: UserModel = await self._get_user()
        refresh_token: RefreshToken = RefreshToken.from_user_id(user.id)
        return GetRefreshedAuthUserTokenResponse(
            access=refresh_token.access_token.encode(),
            refresh=refresh_token.encode(),
        )
