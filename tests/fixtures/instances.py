from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from proxium.instances import InstanceHeartbeat

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Iterator
    from datetime import datetime


@pytest.fixture
def heartbeat_factory(
    loop_runner: asyncio.Runner,
    database: None,
) -> Iterator[Callable[[datetime], InstanceHeartbeat]]:
    """Heartbeats of processes started at the given time. All of them run on this machine, so they report to one
    row. A report a minute: within a test only status changes write. Closed after the test.
    """
    heartbeats: list[InstanceHeartbeat] = []

    def create(started_at: datetime) -> InstanceHeartbeat:
        # The process start is read once, when the heartbeat is made.
        with patch("proxium.instances._heartbeat.datetime") as clock:
            clock.now.return_value = started_at
            heartbeat = InstanceHeartbeat(interval=60.0)
        heartbeats.append(heartbeat)
        return heartbeat

    yield create

    for heartbeat in heartbeats:
        loop_runner.run(heartbeat.close())
