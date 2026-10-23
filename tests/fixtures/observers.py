from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from proxium.observers import SharedTraffic, TrafficShare, TrafficShareUnavailable

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import date

    from proxium.proxy import Usage


class FakeTrafficShare(TrafficShare):
    """Other processes as a test sets them in `shared`, read as is. While `available` is False every call fails as if
    Redis were down. Keeps the owners each successful publish announced as written.
    """

    def __init__(self) -> None:
        self.shared: dict[str, SharedTraffic] = {}
        # Long enough that no test's sync is away that long.
        self._lease: float = 30.0
        self.available: bool = True
        self.announced: list[set[str]] = []
        # Publishes tried, failed ones too, so a test can wait for them to pass.
        self.attempts: int = 0
        # Reads tried, failed ones too: one per sync, so a test can wait for syncs to pass.
        self.reads: int = 0
        self._called: asyncio.Condition = asyncio.Condition()

    @property
    def lease(self) -> float:
        return self._lease

    @lease.setter
    def lease(self, value: float) -> None:
        self._lease = value

    async def wait_attempts(self, count: int, /) -> None:
        async with self._called:
            await self._called.wait_for(lambda: self.attempts >= count)

    async def wait_reads(self, count: int, /) -> None:
        async with self._called:
            await self._called.wait_for(lambda: self.reads >= count)

    async def publish(self, unwritten: Mapping[str, Mapping[date, Usage]], /, *, written: Collection[str]) -> None:
        async with self._called:
            self.attempts += 1
            self._called.notify_all()
        if not self.available:
            raise TrafficShareUnavailable()
        self.announced.append(set(written))

    async def read(self, owners: Collection[str], /) -> dict[str, SharedTraffic]:
        async with self._called:
            self.reads += 1
            self._called.notify_all()
        if not self.available:
            raise TrafficShareUnavailable()
        return {
            owner: self.shared.get(owner, SharedTraffic(version=None, processes=frozenset(), days={}))
            for owner in owners
        }


@pytest.fixture
def traffic_share() -> FakeTrafficShare:
    return FakeTrafficShare()
