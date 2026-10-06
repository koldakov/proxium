from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Flag, auto
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter

from ._policies import Forbidden, Grant, Policy

if TYPE_CHECKING:
    from collections.abc import Hashable

    from ._scopes import Scope
    from ._types import Request, Session


class ConnectionLimitExceeded(Forbidden):
    pass


class _ConnectionGrant(Grant):
    def __init__(self, counts: Counter[Hashable], key: Hashable, /) -> None:
        self._counts: Counter[Hashable] = counts
        self._key: Hashable = key

    async def release(self) -> None:
        self._counts[self._key] -= 1
        # Only keys with open connections stay: memory is bounded by them.
        if not self._counts[self._key]:
            del self._counts[self._key]


class ConnectionLimitPolicy(Policy):
    """At most `limit` open connections per key of `scope`, more are refused. Counted in this process only.

    Pass `counts` of the previous instance to change the limit: connections open under it keep being counted.
    """

    def __init__(
        self,
        scope: Scope,
        /,
        *,
        limit: int,
        counts: Counter[Hashable] | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError("The connection limit must be at least 1.")

        self._scope: Scope = scope
        self._limit: int = limit
        self._counts: Counter[Hashable] = Counter() if counts is None else counts

    @property
    def counts(self) -> Counter[Hashable]:
        """Open connections per key, to hand over to an instance with another limit."""
        return self._counts

    async def admit(self, request: Request, session: Session, /) -> Grant:
        key = self._scope.key(request, session)
        if self._counts[key] >= self._limit:
            raise ConnectionLimitExceeded()

        self._counts[key] += 1
        return _ConnectionGrant(self._counts, key)


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
