from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from unittest.mock import patch

import pytest
from sqlalchemy import select

from proxium.db import ProxyInstanceModel, ProxyInstanceStatus, session_manager
from proxium.runners import ProxyWorkers, WorkerStartError

if TYPE_CHECKING:
    from collections.abc import Callable
    from multiprocessing.connection import Connection

    from faker import Faker

    from proxium.core import LogLevel

# Workers are spawned processes: how long a test waits for them to start and stop.
_WAIT: Final[float] = 30.0
# A worker of `_crash_once` serves before the crash and after the restart.
_SERVED_TIMES: Final[int] = 2
# Restarts of `_crash_then_fail_to_start`: after its crash, then after its failed restart.
_CRASH_AND_RESTART: Final[int] = 2
# Delays of three crashes in a row from `_create_workers`' restart delay.
_DOUBLED_DELAYS: Final[list[float]] = [0.1, 0.2, 0.4]
# What the master logs on a crash, with the worker number, its exit code and the delay as arguments.
_RESTARTING: Final[str] = "Worker %d exited, exit code %s, restarting in %s s"
# Where `_crash_once` finds its marker: the workers inherit the environment.
_MARKER_ENV: Final[str] = "PROXIUM_TEST_WORKER_MARKER"


# Worker targets: spawned, so module level. None of them touches the database or Redis, only the master does.


def _serve_until_signal(started: Connection, log_level: LogLevel, /) -> None:
    """Serves at once, exits 0 on SIGTERM from the master."""
    # Blocked before serving: a signal then waits for `sigwait`, it doesn't kill.
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    started.send_bytes(b"")
    signal.sigwait({signal.SIGTERM})


def _fail_at_start(started: Connection, log_level: LogLevel, /) -> None:
    """Exits before it serves, as on an invalid policy."""
    raise SystemExit(1)


def _crash_once(started: Connection, log_level: LogLevel, /) -> None:
    """The first run serves, then crashes. The next ones serve until a signal."""
    marker = Path(os.environ[_MARKER_ENV])
    if marker.exists():
        _serve_until_signal(started, log_level)
        return

    marker.touch()
    started.send_bytes(b"")
    raise SystemExit(3)


def _crash_then_fail_to_start(started: Connection, log_level: LogLevel, /) -> None:
    """The first run serves, then crashes. The next ones exit before they serve, as with the database down."""
    marker = Path(os.environ[_MARKER_ENV])
    if marker.exists():
        raise SystemExit(1)

    marker.touch()
    started.send_bytes(b"")
    raise SystemExit(3)


def _crash_after_serving(started: Connection, log_level: LogLevel, /) -> None:
    """Every run serves, then crashes at once."""
    started.send_bytes(b"")
    raise SystemExit(3)


def _create_workers(workers: int, target: Callable[[Connection, LogLevel], None], /) -> ProxyWorkers:
    # A report a minute: within a test only changes write. Restarts at once.
    return ProxyWorkers(workers=workers, heartbeat_interval=60.0, restart_delay=0.1, target=target)


async def _read_instance() -> ProxyInstanceModel:
    """The only instance, the master's."""
    async with session_manager.session() as session:
        result = await session.execute(select(ProxyInstanceModel).limit(2))
        (instance,) = result.scalars().all()
        return instance


def _count_messages(caplog: pytest.LogCaptureFixture, message: str, /) -> int:
    return len([record for record in caplog.records if record.getMessage() == message])


def _get_restart_delays(caplog: pytest.LogCaptureFixture, /) -> list[float]:
    """Delays of the restarts the master logged, in order."""
    return [cast("tuple[int, int, float]", record.args)[2] for record in caplog.records if record.msg == _RESTARTING]


async def _wait_for_instance(predicate: Callable[[ProxyInstanceModel], bool], /) -> ProxyInstanceModel:
    async with asyncio.timeout(_WAIT):
        while True:
            async with session_manager.session() as session:
                result = await session.execute(select(ProxyInstanceModel).limit(2))
                instances = result.scalars().all()

            assert len(instances) <= 1, instances
            if instances and predicate(instances[0]):
                return instances[0]

            await asyncio.sleep(0.05)


def _stop() -> None:
    # As a terminal or Docker sends it: to the master, which forwards it.
    os.kill(os.getpid(), signal.SIGTERM)


async def _serve_until(workers: ProxyWorkers, predicate: Callable[[ProxyInstanceModel], bool], /) -> ProxyInstanceModel:
    """Serve until the instance matches `predicate`, then stop and wait for the workers."""
    serving = asyncio.create_task(workers.serve())
    try:
        instance = await _wait_for_instance(predicate)
    finally:
        # Not to a master that's done: without its handler SIGTERM would kill the tests.
        if not serving.done():
            _stop()

        async with asyncio.timeout(_WAIT):
            await serving

    return instance


@pytest.mark.usefixtures("database")
class TestProxyWorkers:
    def test_serve_reports_every_worker_running(self, faker: Faker, loop_runner: asyncio.Runner) -> None:
        # Arrange
        count = faker.pyint(min_value=2, max_value=4)
        workers = _create_workers(count, _serve_until_signal)

        # Act
        instance = loop_runner.run(_serve_until(workers, lambda instance: instance.running_workers == count))

        # Assert
        assert instance.status == ProxyInstanceStatus.RUNNING
        assert instance.workers == count

    def test_signal_stops_every_worker_and_reports_stopped(self, faker: Faker, loop_runner: asyncio.Runner) -> None:
        # Arrange
        count = faker.pyint(min_value=2, max_value=4)
        workers = _create_workers(count, _serve_until_signal)

        # Act
        loop_runner.run(_serve_until(workers, lambda instance: instance.running_workers == count))

        # Assert
        # `serve` returned: every worker exited.
        instance = loop_runner.run(_read_instance())
        assert instance.status == ProxyInstanceStatus.STOPPED
        assert instance.running_workers == 0

    def test_serve_raises_worker_start_error_when_worker_fails_to_start(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
    ) -> None:
        # Arrange
        workers = _create_workers(faker.pyint(min_value=2, max_value=4), _fail_at_start)

        # Act
        # Every worker fails: the first one stops the rest, no signal needed.
        with pytest.raises(WorkerStartError):
            loop_runner.run(workers.serve())

        # Assert
        instance = loop_runner.run(_read_instance())
        assert instance.status == ProxyInstanceStatus.STOPPED

    def test_crashed_worker_is_restarted(
        self,
        loop_runner: asyncio.Runner,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Arrange
        marker = tmp_path / "crashed"
        workers = _create_workers(1, _crash_once)

        # Act
        with (
            patch.dict(os.environ, {_MARKER_ENV: str(marker)}),
            caplog.at_level(logging.INFO, logger="proxium.runners._workers"),
        ):
            loop_runner.run(
                _serve_until(workers, lambda _: _count_messages(caplog, "Worker 1 serves") == _SERVED_TIMES),
            )

        # Assert
        assert marker.exists()
        assert any("Worker 1 exited, exit code 3" in record.getMessage() for record in caplog.records)

    def test_failed_restart_is_crash_not_failed_start(
        self,
        loop_runner: asyncio.Runner,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Arrange
        marker = tmp_path / "crashed"
        workers = _create_workers(1, _crash_then_fail_to_start)

        # Act
        # The crash, then a restart that fails: both restarted, no WorkerStartError from `serve`.
        with (
            patch.dict(os.environ, {_MARKER_ENV: str(marker)}),
            caplog.at_level(logging.INFO, logger="proxium.runners._workers"),
        ):
            loop_runner.run(_serve_until(workers, lambda _: len(_get_restart_delays(caplog)) >= _CRASH_AND_RESTART))

        # Assert
        assert not any(record.getMessage().startswith("Worker 1 failed to start") for record in caplog.records)

    def test_restart_delay_doubles_on_each_crash_in_a_row(
        self,
        loop_runner: asyncio.Runner,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Arrange
        # Crashes far quicker than the longest delay: each one is in a row.
        workers = _create_workers(1, _crash_after_serving)

        # Act
        with caplog.at_level(logging.INFO, logger="proxium.runners._workers"):
            loop_runner.run(_serve_until(workers, lambda _: len(_get_restart_delays(caplog)) >= len(_DOUBLED_DELAYS)))

        # Assert
        assert _get_restart_delays(caplog)[: len(_DOUBLED_DELAYS)] == pytest.approx(_DOUBLED_DELAYS)
