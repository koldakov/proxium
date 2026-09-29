from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from proxium.db import BasicProxyAccountModel, ProxyBaseAccountModel, TokenProxyAccountModel, session_manager
from proxium.proxy import (
    AuthenticationRequired,
    Authenticator,
    BasicCredentials,
    BearerCredentials,
    CredentialsExpired,
    CredentialsRevoked,
    Identity,
)

if TYPE_CHECKING:
    from sqlalchemy import Result, Select

    from proxium.proxy import Credentials, Session

# Splits a token into the public key and the secret: `<key>.<secret>`.
TOKEN_SEPARATOR: Final[str] = "."  # noqa: S105, a separator, not a secret.
# Starts every key, so a Proxium token is recognizable at a glance, e.g. by secret scanners.
TOKEN_PREFIX: Final[str] = "pxm_"  # noqa: S105, a prefix, not a secret.
# Starts every generated basic username, so it's told apart from a token key.
USERNAME_PREFIX: Final[str] = "pxu_"


class AccountAuthenticationError(Exception):
    """Why an account check failed. Local: `authenticate` turns it into `AuthenticationRequired`, it never leaves."""


class UnsupportedCredentialsError(AccountAuthenticationError):
    """The credentials are of a type this authenticator doesn't handle."""


class MalformedCredentialsError(AccountAuthenticationError):
    """The credentials are of the right type but not in the expected format."""


class AccountNotFoundError(AccountAuthenticationError):
    """No account matches the credentials."""


class BaseAccountAuthenticator[M: ProxyBaseAccountModel](Authenticator, ABC):
    """Checks credentials against proxy accounts in the database: the secret, `is_active` and `expires_at`.

    Subclasses tell how to find the account, the account knows its secret hash.
    """

    async def _get_account(self, statement: Select[tuple[M]], /) -> M:
        async with session_manager.session() as session:
            result: Result[tuple[M]] = await session.execute(statement)

        try:
            return result.scalars().one()
        except NoResultFound as err:
            raise AccountNotFoundError() from err

    async def authenticate(self, credentials: Credentials | None, proxy_session: Session, /) -> Identity:
        try:
            statement, secret = self._lookup(credentials)
        except (UnsupportedCredentialsError, MalformedCredentialsError) as err:
            raise AuthenticationRequired() from err

        try:
            account: M = await self._get_account(statement)
        except AccountNotFoundError as err:
            raise AuthenticationRequired() from err

        # Hashing is slow CPU work, it would stall every other connection on the loop.
        # Still paid on every connection: cache successful checks once Redis is in.
        if not await asyncio.to_thread(account.secret_hash.verify, secret):
            raise AuthenticationRequired()

        # After the secret: only the owner may learn the account exists and is revoked or expired.
        # Revoked first: it's final, expiry is only a date.
        if not account.is_active:
            raise CredentialsRevoked()
        if account.is_expired():
            raise CredentialsExpired()

        return self._identity(account)

    @abstractmethod
    def _lookup(self, credentials: Credentials | None, /) -> tuple[Select[tuple[M]], str]:
        """The query that finds the account and the secret to verify.

        Raise `UnsupportedCredentialsError` for credentials of another type,
          `MalformedCredentialsError` for broken ones.
        """

    @abstractmethod
    def _identity(self, account: M, /) -> Identity:
        pass


class BasicAccountAuthenticator(BaseAccountAuthenticator[BasicProxyAccountModel]):
    """Username and password from `BasicProxyAccountModel`."""

    def _get_lookup_statement(
        self,
        credentials: BasicCredentials,
        /,
    ) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.username == credentials.username)

    def _lookup(
        self,
        credentials: Credentials | None,
        /,
    ) -> tuple[Select[tuple[BasicProxyAccountModel]], str]:
        if not isinstance(credentials, BasicCredentials):
            raise UnsupportedCredentialsError()

        statement = self._get_lookup_statement(credentials)
        return statement, credentials.password

    def _identity(self, account: BasicProxyAccountModel, /) -> Identity:
        return Identity(
            subject=f"basic:{account.username}",
            claims={"account_id": account.id},
        )


class TokenAccountAuthenticator(BaseAccountAuthenticator[TokenProxyAccountModel]):
    """Bearer token `<key>.<secret>` from `TokenProxyAccountModel`: found by the key, the whole token is verified."""

    def _get_lookup_statement(
        self,
        key: str,
        /,
    ) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.key == key)

    def _lookup(
        self,
        credentials: Credentials | None,
        /,
    ) -> tuple[Select[tuple[TokenProxyAccountModel]], str]:
        if not isinstance(credentials, BearerCredentials):
            raise UnsupportedCredentialsError()

        key, separator, _ = credentials.token.partition(TOKEN_SEPARATOR)
        if not separator:
            raise MalformedCredentialsError()

        statement = self._get_lookup_statement(key)
        return statement, credentials.token

    def _identity(self, account: TokenProxyAccountModel, /) -> Identity:
        # The key, never the token: the subject gets logged. Names aren't unique.
        return Identity(
            subject=f"token:{account.key}",
            claims={"account_id": account.id},
        )
