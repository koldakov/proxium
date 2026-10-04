import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self

import jwt
from fastapi import HTTPException, status
from pydantic import Field, ValidationError
from sqlalchemy import CompoundSelect, Result, Select, select, union
from sqlalchemy.exc import NoResultFound

from proxium.core import api_settings
from proxium.db import (
    GroupPermissionModel,
    Permission,
    UserGroupModel,
    UserModel,
    UserPermissionModel,
    session_manager,
)
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """The token can't be used. Catch it to handle every reason at once."""


class ExpiredTokenError(TokenError):
    """The token was fine, but its `exp` has passed."""


class InvalidTokenError(TokenError):
    """The token is forged or malformed: bad signature, not a JWT, and the like."""


class InvalidTokenPayloadError(TokenError):
    """The token is genuine, but its payload doesn't fit: another type or missing fields."""


class TokenUser(BaseSchema):
    id: int


class BaseToken(BaseSchema):
    """A JWT payload for a user.

    Subclasses add `type: Literal[TokenType...]` with a default and set `lifetime`:
    a token of another type fails `decode`.
    """

    algorithm: ClassVar[str] = "HS256"
    lifetime: ClassVar[timedelta]

    exp: datetime
    nonce: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
    )
    user: TokenUser

    @classmethod
    def from_user_id(cls, user_id: int, /) -> Self:
        return cls(
            exp=datetime.now(UTC) + cls.lifetime,
            user=TokenUser(id=user_id),
        )

    def encode(self) -> str:
        # Python mode: PyJWT turns `exp` datetime into a timestamp itself.
        return jwt.encode(
            self.model_dump(),
            api_settings.secret_key.get_secret_value(),
            algorithm=self.algorithm,
        )

    @classmethod
    def decode(cls, token: str, /) -> Self:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                key=api_settings.secret_key.get_secret_value(),
                algorithms=[cls.algorithm],
            )
        except jwt.ExpiredSignatureError as err:
            raise ExpiredTokenError() from err
        except jwt.InvalidTokenError as err:
            raise InvalidTokenError() from err

        try:
            return cls.model_validate(payload)
        except ValidationError as err:
            raise InvalidTokenPayloadError() from err


class AccessToken(BaseToken):
    lifetime: ClassVar[timedelta] = timedelta(minutes=15)

    type: Literal[TokenType.ACCESS] = TokenType.ACCESS


class RefreshToken(BaseToken):
    lifetime: ClassVar[timedelta] = timedelta(days=5)

    type: Literal[TokenType.REFRESH] = TokenType.REFRESH

    @property
    def access_token(self) -> AccessToken:
        """A fresh access token for the same user."""
        return AccessToken.from_user_id(self.user.id)


class BaseService[R](BaseSchema, ABC):
    """One use case. Fields are its input, validated on construction; `await service()` runs it."""

    @abstractmethod
    async def __call__(self, *args, **kwargs) -> R:
        """Run the use case."""


class BaseSessionService[R](BaseService[R], ABC):
    """A use case with a database session, closed once `process` returns."""

    def __init__(self, /, **data: Any) -> None:
        super().__init__(**data)

        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Session is not initialized.")

        return self._session

    @abstractmethod
    async def process(self, *args, **kwargs) -> R:
        """Run the use case in `self.session`. Commit is up to the service."""

    async def __call__(self, *args, **kwargs) -> R:
        async with session_manager.session() as session:
            self._session = session

            return await self.process(*args, **kwargs)


class BaseUserAuthenticatedService[R](BaseSessionService[R], ABC):
    """A use case of the logged-in user, available via `self.user`. `token` is an access JWT.

    Subclasses set `required_permissions`, all of them are needed, empty for any active user.
    """

    # Checked on every call, not taken from the token: a change applies to the next request.
    required_permissions: ClassVar[frozenset[Permission]]

    token: str

    def __init__(self, /, **data: Any) -> None:
        super().__init__(**data)

        self._user: UserModel | None = None
        self._permissions: frozenset[Permission] | None = None

    @property
    def user(self) -> UserModel:
        if self._user is None:
            raise RuntimeError("User is not initialized.")

        return self._user

    @property
    def permissions(self) -> frozenset[Permission]:
        """What the user may do: given directly and through groups, every permission for a superuser."""
        if self._permissions is None:
            raise RuntimeError("Permissions are not initialized.")

        return self._permissions

    @property
    def _access_token(self) -> AccessToken:
        try:
            return AccessToken.decode(self.token)
        except TokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    # `_auth_` names: subclasses have their own users and permissions statements.
    @property
    def _get_auth_user_statement(self) -> Select[tuple[UserModel]]:
        # The user may be deactivated since the token was issued.
        return select(UserModel).where(
            UserModel.id == self._access_token.user.id,
            UserModel.is_active.is_(True),
        )

    @property
    def _list_auth_permissions_statement(self) -> CompoundSelect:
        # `union` drops duplicates, so there are no more rows than permissions.
        return union(
            select(UserPermissionModel.permission).where(UserPermissionModel.user_id == self.user.id),
            select(GroupPermissionModel.permission)
            .join(UserGroupModel, UserGroupModel.group_id == GroupPermissionModel.group_id)
            .where(UserGroupModel.user_id == self.user.id),
        )

    async def _set_user(self) -> None:
        result: Result[tuple[UserModel]] = await self.session.execute(self._get_auth_user_statement)
        try:
            self._user = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    async def _set_permissions(self) -> None:
        if self.user.is_superuser:
            self._permissions = frozenset(Permission)
            return

        result: Result[tuple[Permission]] = await self.session.execute(self._list_auth_permissions_statement)
        self._permissions = frozenset(result.scalars())

    def _check_permissions(self) -> None:
        missing: frozenset[Permission] = self.required_permissions - self.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(sorted(missing))}.",
            )

    async def __call__(self, *args, **kwargs) -> R:
        async with session_manager.session() as session:
            self._session = session
            await self._set_user()
            await self._set_permissions()
            self._check_permissions()

            return await self.process(*args, **kwargs)
