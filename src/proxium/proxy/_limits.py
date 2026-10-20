from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from enum import Flag, auto
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter

from ._policies import Forbidden, Grant, Policy
from ._types import ProxyError

if TYPE_CHECKING:
    from collections.abc import Hashable

    from ._scopes import Scope
    from ._types import Request, Session


class ConnectionLimitExceeded(Forbidden):
    pass


class ConnectionCountUnavailable(ProxyError):
    """Open connections can't be counted, e.g. Redis is down. The client is refused: a limit mustn't be bypassed."""


class ConnectionCounter(ABC):
    """Counts open connections per key for one connection limit, e.g. in process memory or in Redis shared by
    instances. One per limit: keys of different limits never mix.

    One instance serves all connections at once: keep state of one connection on its grant.
    """

    @abstractmethod
    async def acquire(self, key: Hashable, /, *, limit: int) -> Grant:
        """Count one more connection under `key`, its grant's `release` stops counting it.

        Raise `ConnectionLimitExceeded` if `limit` are open already, `ConnectionCountUnavailable` if they can't be
        counted now.
        """


class _MemoryConnectionGrant(Grant):
    def __init__(self, counts: Counter[Hashable], key: Hashable, /) -> None:
        self._counts: Counter[Hashable] = counts
        self._key: Hashable = key

    async def release(self) -> None:
        self._counts[self._key] -= 1
        # Only keys with open connections stay: memory is bounded by them.
        if not self._counts[self._key]:
            del self._counts[self._key]


class MemoryConnectionCounter(ConnectionCounter):
    """In process memory: other processes don't see these connections. E.g. for the connection scope, where
    nothing is shared anyway.
    """

    def __init__(self) -> None:
        self._counts: Counter[Hashable] = Counter()

    @property
    def counts(self) -> Counter[Hashable]:
        """Open connections per key."""
        return self._counts

    async def acquire(self, key: Hashable, /, *, limit: int) -> Grant:
        if self._counts[key] >= limit:
            raise ConnectionLimitExceeded()

        self._counts[key] += 1
        return _MemoryConnectionGrant(self._counts, key)


class ConnectionLimitPolicy(Policy):
    """At most `limit` open connections per key of `scope`, more are refused. `counter` decides who sees them:
    in memory only this process, in Redis every instance sharing it.
    """

    def __init__(
        self,
        scope: Scope,
        /,
        *,
        limit: int,
        counter: ConnectionCounter,
    ) -> None:
        if limit < 1:
            raise ValueError("The connection limit must be at least 1.")

        self._scope: Scope = scope
        self._limit: int = limit
        self._counter: ConnectionCounter = counter

    async def admit(self, request: Request, session: Session, /) -> Grant:
        return await self._counter.acquire(self._scope.key(request, session), limit=self._limit)


class Direction(Flag):
    """Which way bytes go through a tunnel."""

    # From the client to the target: uploads.
    SENT = auto()
    # From the target to the client: downloads.
    RECEIVED = auto()
    BOTH = SENT | RECEIVED


async def _take(limiter: AsyncLimiter, n: int, /) -> None:
    """Wait until `n` bytes fit the rate. In parts of at most the burst: the limiter takes no more at once."""
    remaining: float = n
    while remaining > 0:
        part = min(remaining, limiter.max_rate)
        await limiter.acquire(part)
        remaining -= part


@dataclass(slots=True)
class _Buckets:
    """The rate of one key, a bucket per direction, and how many connections share it."""

    sent: AsyncLimiter
    received: AsyncLimiter
    connections: int = 0


class _SpeedGrant(Grant):
    def __init__(self, buckets: dict[Hashable, _Buckets], key: Hashable, /, *, direction: Direction) -> None:
        self._buckets: dict[Hashable, _Buckets] = buckets
        self._key: Hashable = key
        self._direction: Direction = direction

    async def on_sent(self, n: int, /) -> None:
        if Direction.SENT in self._direction:
            await _take(self._buckets[self._key].sent, n)

    async def on_received(self, n: int, /) -> None:
        if Direction.RECEIVED in self._direction:
            await _take(self._buckets[self._key].received, n)

    async def release(self) -> None:
        buckets = self._buckets[self._key]
        buckets.connections -= 1
        # Only keys with open connections stay: memory is bounded by them.
        if not buckets.connections:
            del self._buckets[self._key]


class SpeedLimitPolicy(Policy):
    """At most `rate` bytes per second per key of `scope` in `direction`, shared by its connections. Never cuts.

    With `BOTH` each way has its own rate: uploads don't slow downloads. After a pause up to `burst` bytes go at once,
    one second of `rate` by default. Counted in this process only.
    """

    def __init__(
        self,
        scope: Scope,
        /,
        *,
        rate: float,
        burst: float | None = None,
        direction: Direction = Direction.BOTH,
    ) -> None:
        burst = rate if burst is None else burst
        if rate <= 0 or burst <= 0:
            raise ValueError("The rate and the burst must be positive.")

        self._scope: Scope = scope
        self._rate: float = rate
        self._burst: float = burst
        self._direction: Direction = direction
        self._buckets: dict[Hashable, _Buckets] = {}

    def _create_limiter(self) -> AsyncLimiter:
        # Takes `burst` at once and refills it in `burst / rate` seconds: `rate` per second on average.
        return AsyncLimiter(self._burst, self._burst / self._rate)

    async def admit(self, request: Request, session: Session, /) -> Grant:
        key = self._scope.key(request, session)
        try:
            buckets = self._buckets[key]
        except KeyError:
            buckets = self._buckets[key] = _Buckets(
                sent=self._create_limiter(),
                received=self._create_limiter(),
            )

        buckets.connections += 1
        return _SpeedGrant(self._buckets, key, direction=self._direction)
