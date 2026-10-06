from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from proxium.core import api_settings
from proxium.db import (
    BaseProxyAccountModel,
    BasicProxyAccountModel,
    BasicProxyAccountOutgoingIPModel,
    BasicProxyAccountPolicyModel,
    OutgoingIPModel,
    OutgoingMode,
    TokenProxyAccountModel,
    TokenProxyAccountOutgoingIPModel,
    TokenProxyAccountPolicyModel,
    session_manager,
)
from proxium.policies import policy_claims
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
    from collections.abc import Sequence

    from sqlalchemy import Result, Select

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

    Subclasses tell how to find the account and its pool, the account knows its secret hash.
    Checked anew on every call, with slow hashing: wrap it in `CachedAuthenticator`.
    """

    def __init__(
        self,
        *,
        pool_max_size: int = api_settings.outgoing_pool_max_size,
        policies_max_size: int = api_settings.policies_max_per_owner,
    ) -> None:
        # The API keeps pools and policies within these, the caps only bound the queries.
        self._pool_max_size: int = pool_max_size
        self._policies_max_size: int = policies_max_size

    async def _get_account(self, statement: Select[tuple[M]], /) -> M:
        async with session_manager.session() as session:
            result: Result[tuple[M]] = await session.execute(statement)

        try:
            return result.scalars().one()
        except NoResultFound as err:
            raise ProxyAccountNotFoundError() from err

    async def _get_pool(self, account: M, /) -> list[IPAddress]:
        """The IPs of the account's pool, empty unless it goes out through the pool."""
        if account.outgoing_mode != OutgoingMode.POOL:
            return []

        async with session_manager.session() as session:
            result: Result[tuple[IPAddress]] = await session.execute(self._get_pool_statement(account))

        return list(result.scalars())

    async def _get_policy_ids(self, account: M, /) -> list[int]:
        """The ids of the policies assigned to the account, active or not: the proxy knows which are active."""
        async with session_manager.session() as session:
            result: Result[tuple[int]] = await session.execute(self._get_policies_statement(account))

        return list(result.scalars())

    async def authenticate(self, credentials: Credentials | None, proxy_session: Session, /) -> Identity:
        try:
            statement, secret = self._lookup(credentials)
        except (UnsupportedCredentialsError, MalformedCredentialsError) as err:
            raise AuthenticationRequired() from err

        try:
            account: M = await self._get_account(statement)
        except ProxyAccountNotFoundError as err:
            raise AuthenticationRequired() from err

        # Hashing is slow CPU work, it would stall every other connection on the loop.
        if not await asyncio.to_thread(account.secret_hash.verify, secret):
            raise AuthenticationRequired()

        # After the secret: only the owner may learn the account exists and is revoked or expired.
        # Revoked first: it's final, expiry is only a date.
        if not account.is_active:
            raise CredentialsRevoked()
        if account.is_expired():
            raise CredentialsExpired()

        # After the checks: the pool and the policies are of no use to a refused client.
        pool = await self._get_pool(account)
        policy_ids = await self._get_policy_ids(account)
        return self._identity(account, pool=pool, policy_ids=policy_ids)

    @abstractmethod
    def _lookup(self, credentials: Credentials | None, /) -> tuple[Select[tuple[M]], str]:
        """The query that finds the account, and the secret to verify.

        Raise `UnsupportedCredentialsError` for credentials of another type,
          `MalformedCredentialsError` for broken ones.
        """

    @abstractmethod
    def _get_pool_statement(self, account: M, /) -> Select[tuple[IPAddress]]:
        """The query for the IPs of the account's pool, at most `_pool_max_size`."""

    @abstractmethod
    def _get_policies_statement(self, account: M, /) -> Select[tuple[int]]:
        """The query for the ids of the policies assigned to the account, at most `_policies_max_size`."""

    @abstractmethod
    def _identity(
        self,
        account: M,
        /,
        *,
        pool: Sequence[IPAddress] = (),
        policy_ids: Sequence[int] = (),
    ) -> Identity:
        pass


class BasicProxyAccountAuthenticator(BaseProxyAccountAuthenticator[BasicProxyAccountModel]):
    """Username and password from `BasicProxyAccountModel`."""

    def _get_lookup_statement(self, credentials: BasicCredentials, /) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.username == credentials.username)

    def _lookup(self, credentials: Credentials | None, /) -> tuple[Select[tuple[BasicProxyAccountModel]], str]:
        if not isinstance(credentials, BasicCredentials):
            raise UnsupportedCredentialsError()

        statement = self._get_lookup_statement(credentials)
        return statement, credentials.password

    def _get_pool_statement(self, account: BasicProxyAccountModel, /) -> Select[tuple[IPAddress]]:
        return (
            select(OutgoingIPModel.ip)
            .join(
                BasicProxyAccountOutgoingIPModel,
                BasicProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(BasicProxyAccountOutgoingIPModel.basic_proxy_account_id == account.id)
            .limit(self._pool_max_size)
        )

    def _get_policies_statement(self, account: BasicProxyAccountModel, /) -> Select[tuple[int]]:
        return (
            select(BasicProxyAccountPolicyModel.policy_id)
            .where(BasicProxyAccountPolicyModel.basic_proxy_account_id == account.id)
            .order_by(BasicProxyAccountPolicyModel.policy_id)
            .limit(self._policies_max_size)
        )

    def _identity(
        self,
        account: BasicProxyAccountModel,
        /,
        *,
        pool: Sequence[IPAddress] = (),
        policy_ids: Sequence[int] = (),
    ) -> Identity:
        return Identity(
            subject=f"basic:{account.username}",
            claims={
                "basic_proxy_account_id": account.id,
                **outgoing_claims(account.outgoing_mode, ips=pool),
                **policy_claims(policy_ids),
            },
        )


class TokenProxyAccountAuthenticator(BaseProxyAccountAuthenticator[TokenProxyAccountModel]):
    """Bearer token `<key>.<secret>` from `TokenProxyAccountModel`: found by the key, the whole token is verified."""

    def _get_lookup_statement(self, key: str, /) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.key == key)

    def _lookup(self, credentials: Credentials | None, /) -> tuple[Select[tuple[TokenProxyAccountModel]], str]:
        if not isinstance(credentials, BearerCredentials):
            raise UnsupportedCredentialsError()

        key, separator, _ = credentials.token.partition(TOKEN_SEPARATOR)
        if not separator:
            raise MalformedCredentialsError()

        statement = self._get_lookup_statement(key)
        return statement, credentials.token

    def _get_pool_statement(self, account: TokenProxyAccountModel, /) -> Select[tuple[IPAddress]]:
        return (
            select(OutgoingIPModel.ip)
            .join(
                TokenProxyAccountOutgoingIPModel,
                TokenProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(TokenProxyAccountOutgoingIPModel.token_proxy_account_id == account.id)
            .limit(self._pool_max_size)
        )

    def _get_policies_statement(self, account: TokenProxyAccountModel, /) -> Select[tuple[int]]:
        return (
            select(TokenProxyAccountPolicyModel.policy_id)
            .where(TokenProxyAccountPolicyModel.token_proxy_account_id == account.id)
            .order_by(TokenProxyAccountPolicyModel.policy_id)
            .limit(self._policies_max_size)
        )

    def _identity(
        self,
        account: TokenProxyAccountModel,
        /,
        *,
        pool: Sequence[IPAddress] = (),
        policy_ids: Sequence[int] = (),
    ) -> Identity:
        # The key, never the token: the subject gets logged. Names aren't unique.
        return Identity(
            subject=f"token:{account.key}",
            claims={
                "token_proxy_account_id": account.id,
                **outgoing_claims(account.outgoing_mode, ips=pool),
                **policy_claims(policy_ids),
            },
        )
