from __future__ import annotations

import asyncio
import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ._types import ProxyError

if TYPE_CHECKING:
    import ssl

    from ._types import Session


class EncryptionUnavailable(ProxyError):
    """No TLS for the client: none is set up, or there's no certificate right now. The client gets a TLS alert."""


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
    """

    def __init__(self, encryption: Encryption, /, *, ttl: float = 5.0) -> None:
        self._encryption: Encryption = encryption
        self._ttl: float = ttl
        self._lock: asyncio.Lock = asyncio.Lock()
        # Never served: expired from the start, so the first connection loads the real one.
        self._outcome: ssl.SSLContext | EncryptionUnavailable = EncryptionUnavailable("Not looked up yet.")
        self._expires_at: float = float("-inf")

    async def _load(self, session: Session, /) -> ssl.SSLContext | EncryptionUnavailable:
        try:
            return await self._encryption.context(session)
        except EncryptionUnavailable as error:
            return error

    async def context(self, session: Session, /) -> ssl.SSLContext:
        loop = asyncio.get_running_loop()
        async with self._lock:
            if loop.time() >= self._expires_at:
                self._outcome = await self._load(session)
                self._expires_at = loop.time() + self._ttl
            outcome = self._outcome

        if isinstance(outcome, EncryptionUnavailable):
            # A copy: raising the same instance from many connections would pile up their tracebacks on it.
            raise copy.copy(outcome)
        return outcome
