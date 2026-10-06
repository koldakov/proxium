from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._limits import Direction
from ._policies import EMPTY_GRANT, Forbidden, Grant, Policy
from ._types import ProxyError

if TYPE_CHECKING:
    from ._types import Request, Session


class QuotaExceeded(Forbidden):
    pass


class UsageUnavailable(ProxyError):
    """The usage can't be read, e.g. the database is down. The client is refused: a quota mustn't be bypassed."""


class Unmetered(Exception):
    """The meter can't tell this client's usage, e.g. an anonymous one: quotas don't apply to it."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Bytes a client used so far, e.g. this month."""

    sent: int = 0
    received: int = 0


class Meter(ABC):
    """How much a client used, e.g. the traffic of its account this month.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    async def measure(self, request: Request, session: Session, /) -> Usage:
        """Include bytes of open connections. Raise `Unmetered` if the client can't be measured,
        `UsageUnavailable` if the usage can't be read now.
        """


class _QuotaGrant(Grant):
    """Measures again on the bytes of the tunnel, at most every `interval` seconds: measuring isn't free."""

    def __init__(self, quota: QuotaPolicy, request: Request, session: Session, /, *, interval: float) -> None:
        self._quota: QuotaPolicy = quota
        self._request: Request = request
        self._session: Session = session
        self._interval: float = interval
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._checked_at: float = self._loop.time()

    async def _recheck(self) -> None:
        now = self._loop.time()
        if now - self._checked_at < self._interval:
            return

        self._checked_at = now
        await self._quota.check(self._request, self._session)

    # Either way: past the quota the client gets nothing more, uploads of a download quota included.
    async def on_sent(self, n: int, /) -> None:
        await self._recheck()

    async def on_received(self, n: int, /) -> None:
        await self._recheck()


class QuotaPolicy(Policy):
    """At most `limit` bytes in `direction` as `meter` measures them, `BOTH` counts the two ways together.

    Past it new connections are refused, open ones are cut on their next bytes, checked every `check_interval`
    seconds: a tunnel may go over by what it moves in that time. Clients the meter can't measure aren't limited.
    """

    def __init__(
        self,
        meter: Meter,
        /,
        *,
        limit: int,
        direction: Direction = Direction.BOTH,
        check_interval: float = 1.0,
    ) -> None:
        if limit < 1:
            raise ValueError("The quota must be at least 1 byte.")

        self._meter: Meter = meter
        self._limit: int = limit
        self._direction: Direction = direction
        self._check_interval: float = check_interval

    def _count(self, usage: Usage, /) -> int:
        counted: int = 0
        if Direction.SENT in self._direction:
            counted += usage.sent
        if Direction.RECEIVED in self._direction:
            counted += usage.received
        return counted

    async def check(self, request: Request, session: Session, /) -> None:
        """Raise `QuotaExceeded` if the client used it up. The meter's errors pass through."""
        usage: Usage = await self._meter.measure(request, session)
        if self._count(usage) >= self._limit:
            raise QuotaExceeded()

    async def admit(self, request: Request, session: Session, /) -> Grant:
        try:
            await self.check(request, session)
        except Unmetered:
            return EMPTY_GRANT

        return _QuotaGrant(self, request, session, interval=self._check_interval)
