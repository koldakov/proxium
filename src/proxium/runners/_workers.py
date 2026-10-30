import argparse
import asyncio
import logging
import multiprocessing
import os
import signal
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

import uvloop

from proxium.core import proxy_settings
from proxium.db import ProxyInstanceStatus, session_manager
from proxium.instances import InstanceHeartbeat

from ._proxy import ProxyRunner

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from multiprocessing.connection import Connection
    from multiprocessing.context import ForkContext, ForkServerContext, SpawnContext
    from multiprocessing.process import BaseProcess

    from proxium.core import LogLevel

# Lazy: the contexts are imported for type checking only.
type _WorkerContext = SpawnContext | ForkContext | ForkServerContext

logger = logging.getLogger(__name__)

# Doublings of the restart delay at most: 1 s doubled 16 times is past any sane longest delay.
MAX_RESTART_DOUBLINGS: Final[int] = 16

# With the process name: lines of the workers tell which one wrote them.
WORKERS_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(processName)s %(name)s: %(message)s"


class WorkerStartMethod(StrEnum):
    """How the master starts workers, see `multiprocessing` start methods. Set in code only, not in the environment."""

    # The default: a fresh interpreter, nothing of the master in it. The safe one, on every platform.
    SPAWN = "spawn"
    # DANGEROUS: a copy of the master, its loop, threads, open database connections and locks included, so a worker
    # may hang or share a connection with the master. Starts fastest. Only if you know the master holds nothing yet.
    FORK = "fork"
    # LINUX ONLY: workers forked from a clean server process started once, faster than spawn and as safe.
    FORKSERVER = "forkserver"


class WorkerStartError(Exception):
    """A worker exited before it served: the proxy stopped, the next would fail the same."""


class _WorkerRunner(ProxyRunner):
    """A proxy in a worker process: tells the master once it serves, stops if the master is gone."""

    def __init__(self, started: Connection, /) -> None:
        super().__init__()
        self._started: Connection = started

    def _on_master_gone(self, sentinel: int, /) -> None:
        asyncio.get_running_loop().remove_reader(sentinel)
        logger.warning("The master process is gone, shutting down")

        # The way a signal from the master goes: a graceful stop.
        os.kill(os.getpid(), signal.SIGTERM)

    async def start(self) -> None:
        await super().start()

        # Readable once the master exits, e.g. killed: no worker is left serving on its own. No polling.
        parent = multiprocessing.parent_process()
        if parent is not None:
            asyncio.get_running_loop().add_reader(parent.sentinel, self._on_master_gone, parent.sentinel)

        self._started.send_bytes(b"")
        self._started.close()


def run_worker(started: Connection, log_level: LogLevel, /) -> None:
    """A worker process: serve until a signal from the master, write to `started` once serving."""
    # Signals come from the master only: Ctrl+C in a terminal reaches the whole group, and the master forwards it.
    # Twice would force the stop.
    os.setpgrp()
    logging.basicConfig(level=log_level, format=WORKERS_LOG_FORMAT)

    runner = _WorkerRunner(started)
    runner.run()


class _Worker:
    """A worker process, as the master sees it."""

    def __init__(self, process: BaseProcess, started: Connection, /) -> None:
        self.process: BaseProcess = process
        # Readable once the worker serves, or at its exit: then nothing is in it.
        self.started: Connection = started
        self.is_started: bool = False
        # Loop time it began to serve.
        self.served_since: float = 0.0


class ProxyWorkers:
    """Runs `workers` proxy processes on the same ports with `SO_REUSEPORT`, the kernel spreads new connections
    between them. Limits and quotas are shared through Redis, as between instances. The master reports the instance
    with how many workers serve: it's one proxy in the admin.

    SIGINT/SIGTERM is forwarded to every worker, each shuts down gracefully, a second signal forces the stop. A worker
    that exits after it started is restarted in `restart_delay` seconds, twice as long on each crash in a row, up to
    `max_restart_delay`: a worker crashing at once doesn't spin. One that served `max_restart_delay` seconds starts
    the count over. One that fails its first start, e.g. an invalid policy or a taken port, stops them all with exit
    code 1: the next would fail the same. A restart that fails is a crash: the others keep serving, e.g. through a
    moment the database is down.

    `target` runs in each worker, `run_worker` by default: it gets the connection to write to once serving and the
    log level. It must be importable by name: with `start_method` spawn, the default, or forkserver a worker starts
    clean and imports it. Fork is dangerous, forkserver is for Linux only, see `WorkerStartMethod`.
    """

    signals: ClassVar[tuple[signal.Signals, ...]] = ProxyRunner.signals

    def __init__(  # noqa: PLR0913
        self,
        *,
        workers: int = proxy_settings.workers,
        reuse_port: bool = proxy_settings.reuse_port,
        log_level: LogLevel = proxy_settings.log_level,
        name: str = proxy_settings.name,
        heartbeat_interval: float = proxy_settings.heartbeat_interval,
        restart_delay: float = 1.0,
        max_restart_delay: float = 30.0,
        target: Callable[[Connection, LogLevel], None] = run_worker,
        start_method: WorkerStartMethod = WorkerStartMethod.SPAWN,
    ) -> None:
        if workers < 1:
            raise ValueError(f"Workers must be at least 1, got {workers}.")

        if max_restart_delay < restart_delay:
            raise ValueError(
                f"Max restart delay {max_restart_delay} s is shorter than restart delay {restart_delay} s.",
            )

        # Else every worker but the first fails to listen.
        if workers > 1 and not reuse_port:
            raise ValueError("Several workers listen on the same ports: they need PROXY_REUSE_PORT=true.")

        self._workers: int = workers
        self._log_level: LogLevel = log_level
        self._restart_delay: float = restart_delay
        self._max_restart_delay: float = max_restart_delay
        # Worker number → crashes in a row.
        self._crashes: dict[int, int] = dict.fromkeys(range(1, workers + 1), 0)
        # Numbers whose worker served at least once: its failed start is then a crash, e.g. the database down for a
        # moment, not a setup that can't work.
        self._have_served: set[int] = set()
        self._target: Callable[[Connection, LogLevel], None] = target
        self._heartbeat: InstanceHeartbeat = InstanceHeartbeat(
            name=name,
            interval=heartbeat_interval,
            workers=workers,
        )
        self._context: _WorkerContext = multiprocessing.get_context(start_method)  # type: ignore[assignment]
        self._running: dict[int, _Worker] = {}
        self._restarts: dict[int, asyncio.TimerHandle] = {}
        self._is_stopping: bool = False
        self._is_failed: bool = False
        # Set once no worker is left, nor one to restart.
        self._done: asyncio.Event = asyncio.Event()

    def _report(self) -> None:
        started = sum(worker.is_started for worker in self._running.values())

        self._heartbeat.set_running_workers(started)
        # Pending while none serves: at the start, or when every one crashed. Not on the way down: the last worker
        # gone is the stop, `close` reports it.
        if not self._is_stopping:
            self._heartbeat.set_status(ProxyInstanceStatus.RUNNING if started else ProxyInstanceStatus.PENDING)

    def _read_started(self, number: int, /) -> None:
        worker = self._running[number]
        asyncio.get_running_loop().remove_reader(worker.started.fileno())

        try:
            worker.started.recv_bytes()
        except EOFError:
            # Exited before it served: the exit tells the rest.
            return

        worker.is_started = True
        worker.served_since = asyncio.get_running_loop().time()
        self._have_served.add(number)
        logger.info("Worker %d serves", number)
        self._report()

    def _spawn(self, number: int, /) -> None:
        self._restarts.pop(number, None)

        started, started_writer = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=self._target,
            args=(started_writer, self._log_level),
            name=f"worker-{number}",
        )
        process.start()
        # The worker's end: closed here, the master reads the end of file once the worker exits.
        started_writer.close()

        self._running[number] = _Worker(process, started)
        loop = asyncio.get_running_loop()
        loop.add_reader(started.fileno(), self._read_started, number)
        loop.add_reader(process.sentinel, self._reap, number)

        logger.info("Started worker %d, pid %s", number, process.pid)

    def _try_spawn(self, number: int, /) -> None:
        """Spawn, or stop them all if the process can't be made, e.g. out of file descriptors: then the admin shows
        the stop, not a proxy hanging in pending.
        """
        try:
            self._spawn(number)
        except Exception:
            logger.exception("Can't start worker %d, stopping", number)
            self._is_failed = True
            self._stop()

    def _get_restart_delay(self, number: int, worker: _Worker, /) -> float:
        """Count the crash of `worker`, the one under `number`, and how long to wait before starting it again."""
        # Served long enough: healthy, the crash isn't one in a row. One that never served is.
        loop = asyncio.get_running_loop()
        if worker.is_started and loop.time() - worker.served_since >= self._max_restart_delay:
            self._crashes[number] = 0

        crashes = self._crashes[number]
        self._crashes[number] = crashes + 1

        # Capped: past the longest delay more doublings change nothing, and a huge power overflows a float.
        return min(self._restart_delay * 2 ** min(crashes, MAX_RESTART_DOUBLINGS), self._max_restart_delay)

    def _finish_if_done(self) -> None:
        if not self._running and not self._restarts:
            self._done.set()

    def _stop(self) -> None:
        """Send SIGTERM to every worker: the first one stops gracefully, a second forces it."""
        if not self._is_stopping:
            logger.info("Shutting down %d workers, press Ctrl+C again to force", len(self._running))

        self._is_stopping = True
        for handle in self._restarts.values():
            handle.cancel()
        self._restarts.clear()

        for worker in self._running.values():
            worker.process.terminate()

        self._finish_if_done()

    def _reap(self, number: int, /) -> None:
        loop = asyncio.get_running_loop()
        worker = self._running[number]
        loop.remove_reader(worker.process.sentinel)

        # Started and exited at once: both may be readable, the start is read first.
        if not worker.is_started and worker.started.poll():
            self._read_started(number)

        loop.remove_reader(worker.started.fileno())
        worker.started.close()
        worker.process.join()
        del self._running[number]
        self._report()

        if self._is_stopping:
            logger.info("Worker %d stopped", number)
        # Only the first start is fatal: a restart that fails is a crash, the others go on serving.
        elif not worker.is_started and number not in self._have_served:
            logger.error("Worker %d failed to start, exit code %s, stopping", number, worker.process.exitcode)
            self._is_failed = True
            self._stop()
        else:
            delay = self._get_restart_delay(number, worker)
            logger.error(
                "Worker %d exited, exit code %s, restarting in %s s",
                number,
                worker.process.exitcode,
                delay,
            )
            self._restarts[number] = loop.call_later(delay, self._try_spawn, number)

        self._finish_if_done()

    async def serve(self) -> None:
        """Run the workers until a signal, then wait for them to stop. In a running loop, e.g. in tests, else use
        `run`. Raise `WorkerStartError` if one failed to start.

        The database pool stays open: the caller owns `session_manager`.
        """
        loop = asyncio.get_running_loop()
        for sig in self.signals:
            loop.add_signal_handler(sig, self._stop)

        try:
            # First: a start that fails or hangs shows as pending, then unknown.
            self._heartbeat.start()
            for number in range(1, self._workers + 1):
                self._try_spawn(number)
                # Failed: the rest isn't started, those started already stop.
                if self._is_stopping:
                    break

            await self._done.wait()
            await self._heartbeat.close()
        finally:
            for sig in self.signals:
                loop.remove_signal_handler(sig)

        if self._is_failed:
            raise WorkerStartError()

    async def _serve_and_close(self) -> None:
        try:
            await self.serve()
        finally:
            await session_manager.close()

    def run(self) -> None:
        """Serve in a loop of its own. Exit code 1 if a worker failed to start."""
        multiprocessing.current_process().name = "master"
        logging.basicConfig(level=self._log_level, format=WORKERS_LOG_FORMAT)

        try:
            uvloop.run(self._serve_and_close())
        except WorkerStartError:
            # Logged by the master as it happened, with the worker's own error above.
            raise SystemExit(1) from None


def run_proxy(args: Sequence[str] | None = None) -> None:
    """Serve in `--workers` processes on the same ports, under a master. One worker too: one way to run, restarts
    included.
    """
    parser = argparse.ArgumentParser(
        prog="proxium",
        description="Run the proxy.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=proxy_settings.workers,
        help="proxy processes on the same ports, one per CPU core; default PROXY_WORKERS, 1",
    )
    namespace = parser.parse_args(args)

    try:
        workers = ProxyWorkers(workers=namespace.workers)
    except ValueError as error:
        parser.error(str(error))

    workers.run()
