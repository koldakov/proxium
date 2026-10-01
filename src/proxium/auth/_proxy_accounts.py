from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from proxium.db import (
    BaseProxyAccountModel,
    BasicProxyAccountModel,
    BasicProxyAccountOutgoingIPModel,
    OutgoingIPModel,
    OutgoingMode,
    TokenProxyAccountModel,
    TokenProxyAccountOutgoingIPModel,
    session_manager,
)
from proxium.proxy import (
    AuthenticationRequired,
    Authenticator,
    BasicCredentials,
    BearerCredentials,
    CredentialsExpired,
    CredentialsRevoked,
    Identity,
)
from proxium.selectors import outgoing_claims

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

    from sqlalchemy import Result, Row, ScalarSelect, Select

    from proxium.proxy import Credentials, IPAddress, Session

# Splits a token into the public key and the secret: `<key>.<secret>`.
TOKEN_SEPARATOR: Final[str] = "."  # noqa: S105, a separator, not a secret.
# Starts every key, so a Proxium token is recognizable at a glance, e.g. by secret scanners.
TOKEN_PREFIX: Final[str] = "pxm_"  # noqa: S105, a prefix, not a secret.
# Starts every generated basic username, so it's told apart from a token key.
USERNAME_PREFIX: Final[str] = "pxu_"


class ProxyAccountAuthenticationError(Exception):
    """Why a proxy account check failed. Local: `authenticate` turns it into `AuthenticationRequired`."""


class UnsupportedCredentialsError(ProxyAccountAuthenticationError):
    """The credentials are of a type this authenticator doesn't handle."""


class MalformedCredentialsError(ProxyAccountAuthenticationError):
    """The credentials are of the right type but not in the expected format."""


class ProxyAccountNotFoundError(ProxyAccountAuthenticationError):
    """No proxy account matches the credentials."""


class BaseProxyAccountAuthenticator[M: BaseProxyAccountModel](Authenticator, ABC):
    """Checks credentials against proxy accounts in the database: the secret, `is_active` and `expires_at`.

    Subclasses tell how to find the account, the account knows its secret hash.
    """

    async def _get_account(self, statement: Select[tuple[M, IPAddress | None]], /) -> Row[tuple[M, IPAddress | None]]:
        """The account and a random IP of its pool, None unless it goes out through the pool."""
        async with session_manager.session() as session:
            result: Result[tuple[M, IPAddress | None]] = await session.execute(statement)

        try:
            return result.one()
        except NoResultFound as err:
            raise ProxyAccountNotFoundError() from err

    async def authenticate(self, credentials: Credentials | None, proxy_session: Session, /) -> Identity:
        try:
            statement, secret = self._lookup(credentials)
        except (UnsupportedCredentialsError, MalformedCredentialsError) as err:
            raise AuthenticationRequired() from err

        try:
            row: Row[tuple[M, IPAddress | None]] = await self._get_account(statement)
        except ProxyAccountNotFoundError as err:
            raise AuthenticationRequired() from err
        account, pool_ip = row

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

        return self._identity(account, pool_ip=pool_ip)

    @abstractmethod
    def _lookup(self, credentials: Credentials | None, /) -> tuple[Select[tuple[M, IPAddress | None]], str]:
        """The query that finds the account with a random IP of its pool, and the secret to verify.

        Raise `UnsupportedCredentialsError` for credentials of another type,
          `MalformedCredentialsError` for broken ones.
        """

    @abstractmethod
    def _identity(self, account: M, /, *, pool_ip: IPAddress | None = None) -> Identity:
        pass


class BasicProxyAccountAuthenticator(BaseProxyAccountAuthenticator[BasicProxyAccountModel]):
    """Username and password from `BasicProxyAccountModel`."""

    @property
    def _get_pool_ip_statement(self) -> ScalarSelect[IPv4Address | IPv6Address]:
        # A random IP of the pool, picked in the database so the pool is never loaded. NULL unless the pool is in use.
        return (
            select(OutgoingIPModel.ip)
            .join(
                BasicProxyAccountOutgoingIPModel,
                BasicProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(
                BasicProxyAccountOutgoingIPModel.basic_proxy_account_id == BasicProxyAccountModel.id,
                BasicProxyAccountModel.outgoing_mode == OutgoingMode.POOL,
            )
            .order_by(func.random())
            .limit(1)
            .correlate(BasicProxyAccountModel)
            .scalar_subquery()
        )

    def _get_lookup_statement(
        self,
        credentials: BasicCredentials,
        /,
    ) -> Select[tuple[BasicProxyAccountModel, IPAddress | None]]:
        # The pool IP in the same query: the connector needs it right after.
        return select(BasicProxyAccountModel, self._get_pool_ip_statement).where(
            BasicProxyAccountModel.username == credentials.username,
        )

    def _lookup(
        self,
        credentials: Credentials | None,
        /,
    ) -> tuple[Select[tuple[BasicProxyAccountModel, IPAddress | None]], str]:
        if not isinstance(credentials, BasicCredentials):
            raise UnsupportedCredentialsError()

        statement = self._get_lookup_statement(credentials)
        return statement, credentials.password

    def _identity(self, account: BasicProxyAccountModel, /, *, pool_ip: IPAddress | None = None) -> Identity:
        return Identity(
            subject=f"basic:{account.username}",
            claims={
                "basic_proxy_account_id": account.id,
                **outgoing_claims(account.outgoing_mode, ip=pool_ip),
            },
        )


class TokenProxyAccountAuthenticator(BaseProxyAccountAuthenticator[TokenProxyAccountModel]):
    """Bearer token `<key>.<secret>` from `TokenProxyAccountModel`: found by the key, the whole token is verified."""

    @property
    def _get_pool_ip_statement(self) -> ScalarSelect[IPv4Address | IPv6Address]:
        # A random IP of the pool, picked in the database so the pool is never loaded. NULL unless the pool is in use.
        return (
            select(OutgoingIPModel.ip)
            .join(
                TokenProxyAccountOutgoingIPModel,
                TokenProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(
                TokenProxyAccountOutgoingIPModel.token_proxy_account_id == TokenProxyAccountModel.id,
                TokenProxyAccountModel.outgoing_mode == OutgoingMode.POOL,
            )
            .order_by(func.random())
            .limit(1)
            .correlate(TokenProxyAccountModel)
            .scalar_subquery()
        )

    def _get_lookup_statement(
        self,
        key: str,
        /,
    ) -> Select[tuple[TokenProxyAccountModel, IPAddress | None]]:
        # The pool IP in the same query: the connector needs it right after.
        return select(TokenProxyAccountModel, self._get_pool_ip_statement).where(TokenProxyAccountModel.key == key)

    def _lookup(
        self,
        credentials: Credentials | None,
        /,
    ) -> tuple[Select[tuple[TokenProxyAccountModel, IPAddress | None]], str]:
        if not isinstance(credentials, BearerCredentials):
            raise UnsupportedCredentialsError()

        key, separator, _ = credentials.token.partition(TOKEN_SEPARATOR)
        if not separator:
            raise MalformedCredentialsError()

        statement = self._get_lookup_statement(key)
        return statement, credentials.token

    def _identity(self, account: TokenProxyAccountModel, /, *, pool_ip: IPAddress | None = None) -> Identity:
        # The key, never the token: the subject gets logged. Names aren't unique.
        return Identity(
            subject=f"token:{account.key}",
            claims={
                "token_proxy_account_id": account.id,
                **outgoing_claims(account.outgoing_mode, ip=pool_ip),
            },
        )
