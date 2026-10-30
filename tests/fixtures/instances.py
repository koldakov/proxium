from __future__ import annotations

from ipaddress import IPv4Address
from typing import TYPE_CHECKING
from unittest.mock import patch

import ifaddr
import pytest

from proxium.instances import InstanceHeartbeat

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Iterator
    from datetime import datetime
    from ipaddress import IPv6Address

    from faker import Faker


@pytest.fixture
def adapter_factory(faker: Faker) -> Callable[[list[IPv4Address | IPv6Address]], ifaddr.Adapter]:
    """A network interface with the IPs, as `ifaddr.get_adapters` returns it."""

    def create(ips: list[IPv4Address | IPv6Address]) -> ifaddr.Adapter:
        name = faker.unique.slug()
        # IPv6 comes as (address, flow info, scope id), with a prefix as long as the address: a host route.
        return ifaddr.Adapter(
            name,
            name,
            [
                ifaddr.IP(str(ip), 32, name) if isinstance(ip, IPv4Address) else ifaddr.IP((str(ip), 0, 0), 128, name)
                for ip in ips
            ],
        )

    return create


@pytest.fixture
def heartbeat_factory(
    loop_runner: asyncio.Runner,
    database: None,
) -> Iterator[Callable[[datetime], InstanceHeartbeat]]:
    """Heartbeats of processes started at the given time, of one worker unless `workers` says more. All of them run
    on this machine, so they report to one row. A report a minute: within a test only changes write. Closed after
    the test.
    """
    heartbeats: list[InstanceHeartbeat] = []

    def create(started_at: datetime, /, *, workers: int = 1) -> InstanceHeartbeat:
        # The process start is read once, when the heartbeat is made.
        with patch("proxium.instances._heartbeat.datetime") as clock:
            clock.now.return_value = started_at
            heartbeat = InstanceHeartbeat(interval=60.0, workers=workers)
        heartbeats.append(heartbeat)
        return heartbeat

    yield create

    for heartbeat in heartbeats:
        loop_runner.run(heartbeat.close())
