from __future__ import annotations

import asyncio
import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

from ._caches import CacheMiss
from ._types import ProxyError

if TYPE_CHECKING:
    import ssl

    from ._caches import Cache
    from ._types import Session

# The context doesn't depend on the session: one entry serves every connection.
_CONTEXT_KEY: Final[bytes] = b"context"


class EncryptionUnavailable(ProxyError):
    """No TLS for the client: none is set up, or there's no certificate right now. The client gets a TLS alert."""


# What `CachedEncryption` keeps: the context or the refusal.
type EncryptionOutcome = ssl.SSLContext | EncryptionUnavailable


class Encryption(ABC):
    """Where TLS for clients comes from. Asked on every TLS connection, so it may change between connections.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def context(self, session: Session, /) -> ssl.SSLContext:
        """The server-side context for this client's handshake. Raise `EncryptionUnavailable` to refuse TLS."""


class StaticEncryption(Encryption):
    """The same context for every connection, e.g. loaded from files on start."""

    def __init__(self, context: ssl.SSLContext, /) -> None:
        self._context: ssl.SSLContext = context

    async def context(self, session: Session, /) -> ssl.SSLContext:
        return self._context


class CachedEncryption(Encryption):
    """Reuses the context of another `Encryption` for `ttl` seconds, its refusal too.

    Clients reach `context` before they authenticate: without a cache, a flood of TLS handshakes makes the inner
    one work for each, e.g. query the database. Connections arriving during a lookup wait for it instead of
    starting their own. Changes reach new connections within `ttl`. The inner one must not depend on the session:
    the first connection's session serves all of them. Other errors aren't cached, the next connection retries.
    The context is kept in `cache`, in process memory: an `ssl.SSLContext` can't leave the process.
    """

    def __init__(
        self,
        encryption: Encryption,
        /,
        *,
        cache: Cache[EncryptionOutcome],
        ttl: float = 10.0,
    ) -> None:
        self._encryption: Encryption = encryption
        self._cache: Cache[EncryptionOutcome] = cache
        self._ttl: float = ttl
        # One lookup at a time, the rest wait for it and find it cached.
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _load(self, session: Session, /) -> EncryptionOutcome:
        try:
            return await self._encryption.context(session)
        except EncryptionUnavailable as error:
            return error

    async def _get(self, session: Session, /) -> EncryptionOutcome:
        try:
            outcome = await self._cache.get(_CONTEXT_KEY)
        except CacheMiss:
            outcome = await self._load(session)
            await self._cache.set(_CONTEXT_KEY, outcome, ttl=self._ttl)
        return outcome

    async def context(self, session: Session, /) -> ssl.SSLContext:
        async with self._lock:
            outcome = await self._get(session)

        if isinstance(outcome, EncryptionUnavailable):
            # A copy: raising the same instance from many connections would pile up their tracebacks on it.
            raise copy.copy(outcome)
        return outcome
