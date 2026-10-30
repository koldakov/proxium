from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

from sqlalchemy import func, select, update

from proxium.db import ProxyInstanceModel, ProxyInstanceStatus, session_manager

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from ipaddress import IPv4Address, IPv6Address

    import ifaddr
    from faker import Faker

    from proxium.instances import InstanceHeartbeat

# Reports are written in the background: how long a test waits for one.
_WAIT: Final[float] = 5.0


async def _read_instances() -> Sequence[ProxyInstanceModel]:
    """At most two: a test expects one, a second is already wrong."""
    async with session_manager.session() as session:
        result = await session.execute(select(ProxyInstanceModel).limit(2))
        return result.scalars().all()


async def _wait_for(predicate: Callable[[ProxyInstanceModel], bool], /) -> ProxyInstanceModel:
    """The only instance once it matches `predicate`."""
    async with asyncio.timeout(_WAIT):
        while True:
            instances = await _read_instances()
            assert len(instances) <= 1, instances
            if instances and predicate(instances[0]):
                return instances[0]
            await asyncio.sleep(0.05)


async def _update_instance(**values: object) -> None:
    async with session_manager.session() as session:
        await session.execute(update(ProxyInstanceModel).values(**values))
        await session.commit()


async def _start(heartbeat: InstanceHeartbeat, /) -> None:
    """In the loop the reports run in."""
    heartbeat.start()


class TestInstanceHeartbeat:
    def test_start_reports_pending(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        started_at = datetime.now(UTC)
        heartbeat = heartbeat_factory(started_at)

        # Act
        loop_runner.run(_start(heartbeat))
        instance = loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))

        # Assert
        assert instance.hostname == socket.gethostname()
        assert instance.started_at == started_at
        assert instance.is_deleted is False

    def test_set_status_reports_without_waiting_for_interval(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        heartbeat = heartbeat_factory(datetime.now(UTC))
        loop_runner.run(_start(heartbeat))
        loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))

        # Act
        # The interval is a minute: only a report at once makes it in time.
        heartbeat.set_status(ProxyInstanceStatus.RUNNING)
        instance = loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.RUNNING))

        # Assert
        assert instance.expires_at > instance.last_seen_at

    def test_close_reports_stopped(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        heartbeat = heartbeat_factory(datetime.now(UTC))
        loop_runner.run(_start(heartbeat))
        heartbeat.set_status(ProxyInstanceStatus.RUNNING)

        # Act
        loop_runner.run(heartbeat.close())

        # Assert
        (instance,) = loop_runner.run(_read_instances())
        assert instance.status == ProxyInstanceStatus.STOPPED

    def test_set_running_workers_reports_without_waiting_for_interval(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[..., InstanceHeartbeat],
    ) -> None:
        # Arrange
        workers = faker.pyint(min_value=2, max_value=64)
        running_workers = faker.pyint(min_value=1, max_value=workers)
        heartbeat = heartbeat_factory(datetime.now(UTC), workers=workers)
        loop_runner.run(_start(heartbeat))
        loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))

        # Act
        # The interval is a minute: only a report at once makes it in time.
        heartbeat.set_running_workers(running_workers)
        instance = loop_runner.run(_wait_for(lambda instance: instance.running_workers == running_workers))

        # Assert
        assert instance.workers == workers

    def test_close_reports_no_running_workers(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[..., InstanceHeartbeat],
    ) -> None:
        # Arrange
        workers = faker.pyint(min_value=1, max_value=64)
        heartbeat = heartbeat_factory(datetime.now(UTC), workers=workers)
        loop_runner.run(_start(heartbeat))
        heartbeat.set_running_workers(workers)

        # Act
        loop_runner.run(heartbeat.close())

        # Assert
        (instance,) = loop_runner.run(_read_instances())
        assert instance.running_workers == 0

    def test_restart_reports_to_same_row(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        now = datetime.now(UTC)
        old = heartbeat_factory(now - timedelta(hours=1))
        loop_runner.run(_start(old))
        loop_runner.run(old.close())
        new = heartbeat_factory(now)

        # Act
        loop_runner.run(_start(new))
        instance = loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))

        # Assert
        assert instance.started_at == now

    def test_older_process_leaves_row_of_newer(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        # A restart without downtime: the new process runs while the old one shuts down.
        now = datetime.now(UTC)
        old, new = heartbeat_factory(now - timedelta(minutes=1)), heartbeat_factory(now)
        loop_runner.run(_start(new))
        new.set_status(ProxyInstanceStatus.RUNNING)
        loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.RUNNING))

        # Act
        # Closed before its first report: only its stop, written by the time `close` returns.
        loop_runner.run(_start(old))
        loop_runner.run(old.close())

        # Assert
        (instance,) = loop_runner.run(_read_instances())
        assert instance.status == ProxyInstanceStatus.RUNNING
        assert instance.started_at == now

    def test_takes_row_of_stopped_newer_process(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        # Started "later" by a clock that has gone back since.
        now = datetime.now(UTC)
        newer = heartbeat_factory(now + timedelta(hours=1))
        loop_runner.run(_start(newer))
        loop_runner.run(newer.close())
        current = heartbeat_factory(now)

        # Act
        loop_runner.run(_start(current))
        instance = loop_runner.run(_wait_for(lambda instance: instance.started_at == now))

        # Assert
        assert instance.status == ProxyInstanceStatus.PENDING

    def test_takes_row_of_unknown_newer_process(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        now = datetime.now(UTC)
        newer = heartbeat_factory(now + timedelta(hours=1))
        loop_runner.run(_start(newer))
        loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))
        # Gone without a stop: its next report was due a minute ago.
        loop_runner.run(_update_instance(expires_at=func.now() - timedelta(minutes=1)))
        current = heartbeat_factory(now)

        # Act
        loop_runner.run(_start(current))
        instance = loop_runner.run(_wait_for(lambda instance: instance.started_at == now))

        # Assert
        assert instance.status == ProxyInstanceStatus.PENDING

    def test_report_registers_deregistered_instance_again(
        self,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
    ) -> None:
        # Arrange
        heartbeat = heartbeat_factory(datetime.now(UTC))
        loop_runner.run(_start(heartbeat))
        loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))
        loop_runner.run(_update_instance(is_deleted=True))

        # Act
        heartbeat.set_status(ProxyInstanceStatus.RUNNING)
        instance = loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.RUNNING))

        # Assert
        assert instance.is_deleted is False

    def test_report_replaces_ips_with_current_ones(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        heartbeat_factory: Callable[[datetime], InstanceHeartbeat],
        adapter_factory: Callable[[list[IPv4Address | IPv6Address]], ifaddr.Adapter],
    ) -> None:
        # Arrange
        old_ip, new_ip = ip_address(faker.unique.ipv4()), ip_address(faker.unique.ipv6())
        heartbeat = heartbeat_factory(datetime.now(UTC))
        # The interfaces as the OS lists them, read anew on each report.
        with patch("proxium.instances._heartbeat.ifaddr.get_adapters") as get_adapters:
            get_adapters.return_value = [adapter_factory([old_ip])]
            loop_runner.run(_start(heartbeat))
            loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.PENDING))

            # Act
            # An IP replaced on the server, reported with the next status.
            get_adapters.return_value = [adapter_factory([new_ip])]
            heartbeat.set_status(ProxyInstanceStatus.RUNNING)
            instance = loop_runner.run(_wait_for(lambda instance: instance.status == ProxyInstanceStatus.RUNNING))

        # Assert
        assert instance.ips == [new_ip]
