from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from ._caches import CacheMiss
from ._types import ANONYMOUS, Credentials, Identity, ProxyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from ._caches import Cache
    from ._types import Session

# What an inbound calls with the client's credentials: an authenticator with the session already bound.
type Authenticate = Callable[[Credentials | None], Awaitable[Identity]]
# What `CachedAuthenticator` tells connections apart by: equal keys share an outcome.
type CacheKey = Callable[[Credentials | None, Session], bytes]


class AuthenticationRequired(ProxyError):
    pass


class AuthenticationUnavailable(Exception):
    """A check shared by connections failed, e.g. the database is down. The cause is the original error.

    Not a refusal: the client isn't told its credentials are wrong. Each connection gets its own instance.
    """


# What `CachedAuthenticator` keeps: the identity or the refusal.
type AuthenticationOutcome = Identity | AuthenticationRequired


class CredentialsExpired(AuthenticationRequired):
    """The credentials are right but expired. Raise only after checking the secret, or it reveals the account exists."""


class CredentialsRevoked(AuthenticationRequired):
    """The credentials are right but revoked. Raise only after checking the secret, or it reveals the account exists."""


class Authenticator(ABC):
    """Turns client credentials into an identity. Where they are checked is up to the implementation.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        """Return the identity or raise `AuthenticationRequired`: `CredentialsRevoked`, `CredentialsExpired` if so.

        `session` tells who connects and where, e.g. to let in whitelisted client IPs without credentials.
        """


class AnonymousAuthenticator(Authenticator):
    """Lets everyone in. Only for local development."""

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        return ANONYMOUS


class DenyAllAuthenticator(Authenticator):
    """Lets no one in, e.g. clients without credentials when only accounts may connect."""

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        raise AuthenticationRequired()


_DENY_ALL_AUTHENTICATOR: Final[DenyAllAuthenticator] = DenyAllAuthenticator()


class DispatchAuthenticator(Authenticator):
    """Picks an authenticator by the credentials type, e.g. one for `BasicCredentials`, another for `BearerCredentials`.

    Credentials of a type not in `authenticators` are refused. Clients without credentials go to `without_credentials`,
    refused by default. Pass e.g. one that lets in trusted networks.
    """

    def __init__(
        self,
        authenticators: Mapping[type[Credentials], Authenticator],
        /,
        *,
        without_credentials: Authenticator = _DENY_ALL_AUTHENTICATOR,
    ) -> None:
        self._authenticators: dict[type[Credentials], Authenticator] = dict(authenticators)
        self._without_credentials: Authenticator = without_credentials

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        if credentials is None:
            return await self._without_credentials.authenticate(None, session)

        try:
            authenticator = self._authenticators[type(credentials)]
        except KeyError as err:
            raise AuthenticationRequired() from err

        return await authenticator.authenticate(credentials, session)


class CredentialsKey:
    """`CacheKey` by the credentials, digested with `secret`: the cache never keeps secrets in the clear.

    Credentials must be a dataclass. For authenticators that don't look at the session, e.g. proxy accounts.
    A random `secret` per process makes digests of no use outside it, e.g. in a memory dump of another run.
    A cache shared by processes, e.g. Redis, needs the same `secret` in all of them.
    """

    def __init__(
        self,
        *,
        secret: bytes,
    ) -> None:
        self._secret: bytes = secret

    def __call__(self, credentials: Credentials | None, session: Session, /) -> bytes:
        fields = () if credentials is None else (type(credentials).__qualname__, *dataclasses.astuple(credentials))
        return hashlib.blake2b(repr(fields).encode(), key=self._secret).digest()


class ClientKey:
    """`CacheKey` by the client host and the credentials, digested with `secret`, e.g. for trusted networks.

    The credentials too: one that refuses them must not let them in on an outcome cached for a client without.
    """

    def __init__(
        self,
        *,
        secret: bytes,
    ) -> None:
        self._secret: bytes = secret
        self._credentials_key: CredentialsKey = CredentialsKey(secret=secret)

    def __call__(self, credentials: Credentials | None, session: Session, /) -> bytes:
        host = None if session.client is None else session.client.host
        fields = (self._credentials_key(credentials, session), host)
        return hashlib.blake2b(repr(fields).encode(), key=self._secret).digest()


class CachedAuthenticator(Authenticator):
    """Reuses outcomes of another `Authenticator` for `ttl` seconds, refusals too, for connections with equal `key`.

    Saves the inner one's work on every connection, e.g. a database lookup and slow secret hashing. Connections
    arriving during a check wait for it instead of starting their own. Changes, e.g. a revoked account, reach new
    connections within `ttl`, so does expiry. `key` must cover all the inner one looks at: the first connection's
    outcome serves the rest. Other errors aren't cached, the next connection retries.

    Identities are kept in `cache`, refusals in `refusals`: a flood of wrong passwords, each with its own key,
    evicts only other refusals. Refusals save repeats, e.g. a client of a revoked account reconnecting in a loop.
    """

    def __init__(
        self,
        authenticator: Authenticator,
        /,
        *,
        key: CacheKey,
        cache: Cache[Identity],
        refusals: Cache[AuthenticationRequired],
        ttl: float = 10.0,
    ) -> None:
        self._authenticator: Authenticator = authenticator
        self._key: CacheKey = key
        self._cache: Cache[Identity] = cache
        self._refusals: Cache[AuthenticationRequired] = refusals
        self._ttl: float = ttl
        # Checks in progress, so connections with the same key share one. In process: a check can't be awaited
        # from another one.
        self._pending: dict[bytes, asyncio.Task[AuthenticationOutcome]] = {}

    async def _store(
        self,
        key: bytes,
        credentials: Credentials | None,
        session: Session,
        /,
    ) -> AuthenticationOutcome:
        try:
            identity = await self._authenticator.authenticate(credentials, session)
        except AuthenticationRequired as error:
            await self._refusals.set(key, error, ttl=self._ttl)
            return error

        await self._cache.set(key, identity, ttl=self._ttl)
        return identity

    async def _check(
        self,
        key: bytes,
        credentials: Credentials | None,
        session: Session,
        /,
    ) -> AuthenticationOutcome:
        # Pending until stored: a connection arriving in between would start a check of its own.
        try:
            return await self._store(key, credentials, session)
        finally:
            del self._pending[key]

    @staticmethod
    def _retrieve_error(task: asyncio.Task[AuthenticationOutcome], /) -> None:
        # Connections still waiting report the error, ones that gave up have no one to report it to:
        # without this asyncio logs it once more as never retrieved.
        if not task.cancelled():
            task.exception()

    async def _wait(
        self,
        key: bytes,
        credentials: Credentials | None,
        session: Session,
        /,
    ) -> AuthenticationOutcome:
        try:
            task = self._pending[key]
        except KeyError:
            task = asyncio.create_task(self._check(key, credentials, session))
            task.add_done_callback(self._retrieve_error)
            self._pending[key] = task

        # Not `await task`: a connection that gives up, e.g. on the handshake timeout, doesn't cancel the others'
        # check, and the error isn't raised as one instance from every connection, piling up their tracebacks.
        await asyncio.wait([task])
        error = task.exception()
        if error is not None:
            raise AuthenticationUnavailable() from error
        return task.result()

    async def _get_refusal(
        self,
        key: bytes,
        credentials: Credentials | None,
        session: Session,
        /,
    ) -> AuthenticationOutcome:
        try:
            return await self._refusals.get(key)
        except CacheMiss:
            return await self._wait(key, credentials, session)

    async def authenticate(self, credentials: Credentials | None, session: Session, /) -> Identity:
        key = self._key(credentials, session)
        # A key is in one of the caches at most: a check runs only when both miss, and stores in one.
        try:
            outcome: AuthenticationOutcome = await self._cache.get(key)
        except CacheMiss:
            outcome = await self._get_refusal(key, credentials, session)

        if isinstance(outcome, AuthenticationRequired):
            # A copy: raising the same instance from many connections would pile up their tracebacks on it.
            raise copy.copy(outcome)
        return outcome
