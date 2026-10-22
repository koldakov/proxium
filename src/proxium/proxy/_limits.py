from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import Counter
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


class SpeedBucket(ABC):
    """Bytes per second per key and direction for one speed limit, e.g. in process memory or in Redis shared by
    instances. One per limit: keys of different limits never mix.

    One instance serves all connections at once: `open` and `close` tell which keys they use.
    """

    @abstractmethod
    def open(self, key: Hashable, /) -> None:
        """A connection under `key` starts: what's kept for `key` stays until every one of them is closed."""

    @abstractmethod
    def close(self, key: Hashable, /) -> None:
        """A connection under `key` is done."""

    @abstractmethod
    async def take(self, key: Hashable, direction: Direction, n: int, /, *, rate: float, burst: float) -> None:
        """Wait until `n` bytes of `key` fit `rate` in `direction`, `SENT` or `RECEIVED`. Up to `burst` go at once
        after a pause. Doesn't raise if the bytes can't be counted where they're shared, e.g. Redis is down: a speed
        limit slows down, it doesn't cut.

        `rate` and `burst` may change between calls: an edited limit applies at once.
        """


async def _take(limiter: AsyncLimiter, n: int, /) -> None:
    """Wait until `n` bytes fit the rate. In parts of at most the burst: the limiter takes no more at once."""
    remaining: float = n
    while remaining > 0:
        part = min(remaining, limiter.max_rate)
        await limiter.acquire(part)
        remaining -= part


class MemorySpeedBucket(SpeedBucket):
    """In process memory: other processes don't see these bytes. E.g. for the connection scope, where nothing is
    shared anyway.
    """

    def __init__(self) -> None:
        self._connections: Counter[Hashable] = Counter()
        # Only keys with open connections: memory is bounded by them.
        self._limiters: dict[Hashable, dict[Direction, AsyncLimiter]] = {}

    def open(self, key: Hashable, /) -> None:
        self._connections[key] += 1
        self._limiters.setdefault(key, {})

    def close(self, key: Hashable, /) -> None:
        self._connections[key] -= 1
        if not self._connections[key]:
            del self._connections[key]
            del self._limiters[key]

    def _create_limiter(self, key: Hashable, direction: Direction, /, *, rate: float, burst: float) -> AsyncLimiter:
        # Takes `burst` at once and refills it in `burst / rate` seconds: `rate` per second on average.
        limiter = self._limiters[key][direction] = AsyncLimiter(burst, burst / rate)
        return limiter

    def _get_limiter(self, key: Hashable, direction: Direction, /, *, rate: float, burst: float) -> AsyncLimiter:
        try:
            limiter = self._limiters[key][direction]
        except KeyError:
            return self._create_limiter(key, direction, rate=rate, burst=burst)

        # An edited limit starts a fresh bucket: up to one more burst may pass.
        if (limiter.max_rate, limiter.time_period) != (burst, burst / rate):
            return self._create_limiter(key, direction, rate=rate, burst=burst)
        return limiter

    async def take(self, key: Hashable, direction: Direction, n: int, /, *, rate: float, burst: float) -> None:
        await _take(self._get_limiter(key, direction, rate=rate, burst=burst), n)


class _SpeedGrant(Grant):
    def __init__(self, policy: SpeedLimitPolicy, key: Hashable, /) -> None:
        self._policy: SpeedLimitPolicy = policy
        self._key: Hashable = key
        self._released: bool = False

    async def _take(self, direction: Direction, n: int, /) -> None:
        remaining = n
        # Released meanwhile, e.g. by the other direction switching rules: the key's state may be gone with its last
        # connection, nothing is left to wait for.
        while remaining > 0 and not self._released:
            remaining -= await self._policy.take_part(self._key, direction, remaining)

    async def on_sent(self, n: int, /) -> None:
        await self._take(Direction.SENT, n)

    async def on_received(self, n: int, /) -> None:
        await self._take(Direction.RECEIVED, n)

    async def release(self) -> None:
        self._released = True
        self._policy.close(self._key)


class SpeedLimitPolicy(Policy):
    """At most `rate` bytes per second per key of `scope` in `direction`, shared by its connections. Never cuts.

    With `BOTH` each way has its own rate: uploads don't slow downloads. After a pause up to `burst` bytes go at once,
    one second of `rate` by default. `bucket` decides who shares the rate: in memory only this process, in Redis
    every instance sharing it.

    `update` and `retire` apply to open connections too, bytes already waiting within one burst.
    """

    @staticmethod
    def check_terms(*, rate: float, burst: float) -> None:
        """Raise `ValueError` unless the rate and the burst are positive, e.g. to check edits before applying any."""
        if rate <= 0 or burst <= 0:
            raise ValueError("The rate and the burst must be positive.")

    def __init__(
        self,
        scope: Scope,
        /,
        *,
        rate: float,
        bucket: SpeedBucket,
        burst: float | None = None,
        direction: Direction = Direction.BOTH,
    ) -> None:
        burst = rate if burst is None else burst
        self.check_terms(rate=rate, burst=burst)

        self._scope: Scope = scope
        self._bucket: SpeedBucket = bucket
        self._rate: float = rate
        self._burst: float = burst
        self._direction: Direction = direction
        self._retired: bool = False

    def update(self, *, rate: float, burst: float, direction: Direction) -> None:
        """The limit was edited, or came back after `retire`: its connections get the new terms. All of them are
        given: a default would silently overwrite what was set.
        """
        # Checked first: invalid terms change nothing.
        self.check_terms(rate=rate, burst=burst)

        self._rate = rate
        self._burst = burst
        self._direction = direction
        self._retired = False

    def retire(self) -> None:
        """The limit was removed: its connections aren't slowed down anymore, until `update` or `restore` brings it
        back.
        """
        self._retired = True

    def restore(self) -> None:
        """The limit is back with the terms it had, e.g. kept for open connections of its old scope."""
        self._retired = False

    async def take_part(self, key: Hashable, direction: Direction, n: int, /) -> int:
        """Wait until the first of `n` bytes of a connection under `key` going in `direction` fit the limit and
        return how many: at most a burst, all of `n` if the limit doesn't slow them. In parts, each with the terms
        of the moment: an edit or `retire` doesn't wait for a big chunk to finish at the old rate.
        """
        if self._retired or direction not in self._direction:
            return n

        part = min(n, max(1, math.floor(self._burst)))
        await self._bucket.take(key, direction, part, rate=self._rate, burst=self._burst)
        return part

    def close(self, key: Hashable, /) -> None:
        """A connection under `key` is done."""
        self._bucket.close(key)

    async def admit(self, request: Request, session: Session, /) -> Grant:
        key = self._scope.key(request, session)
        self._bucket.open(key)
        return _SpeedGrant(self, key)
