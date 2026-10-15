import asyncio
import time
from typing import TYPE_CHECKING, ClassVar

import uvloop
from alembic import command
from alembic.config import Config
from asyncpg import CannotConnectNowError
from redis.exceptions import LockError, RedisError
from sqlalchemy import select

from proxium.db import redis_manager, session_manager
from proxium.management._base import BaseCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from redis.asyncio.lock import Lock


class MigrateCommand(BaseCommand):
    """Applies Alembic migrations up to `revision`, from the installed package: no alembic.ini needed.

    Holds a lock in Redis meanwhile: instances starting at once migrate one at a time, the others then find nothing
    to migrate.
    """

    name: ClassVar[str] = "migrate"
    help: ClassVar[str] = "Apply database migrations."

    script_location: ClassVar[str] = "proxium.db:migrations"
    # Seconds between connection attempts with --wait.
    wait_interval: ClassVar[float] = 1.0
    # One for every instance: only one migrates at a time. Under REDIS_KEY_PREFIX, locks under lock:.
    lock_name: ClassVar[str] = "lock:migrate"
    # Seconds the lock outlives a crashed instance. Also the longest migration: a longer one may run next to another.
    lock_timeout: ClassVar[float] = 600.0

    def add_arguments(self, parser: ArgumentParser, /) -> None:
        parser.add_argument(
            "revision",
            nargs="?",
            default="head",
            help="Revision to upgrade to, head by default.",
        )
        parser.add_argument(
            "--wait",
            type=float,
            default=0,
            metavar="SECONDS",
            help="Wait up to SECONDS for the database to accept connections, e.g. while it starts. 0 by default.",
        )

    async def _check_database(self) -> None:
        async with session_manager.session() as session:
            await session.execute(select(1))

    async def _poll_database(self, timeout: float, /) -> None:
        """Retry until the database answers. Only "not up yet" errors are retried, e.g. a wrong password fails."""
        deadline: float = time.monotonic() + timeout
        while True:
            try:
                await self._check_database()
            # Refused while the server starts, or "the database system is starting up".
            except (OSError, CannotConnectNowError) as err:
                if time.monotonic() >= deadline:
                    raise CommandError(f"The database didn't answer in {timeout:g}s: {err}") from None
                self.stderr.write("Waiting for the database...\n")
                await asyncio.sleep(self.wait_interval)
            else:
                return

    async def _wait_for_database(self, timeout: float, /) -> None:
        try:
            await self._poll_database(timeout)
        finally:
            await session_manager.close()

    def _create_config(self) -> Config:
        config: Config = Config()
        config.set_main_option("script_location", self.script_location)
        return config

    async def _migrate(self, revision: str, /) -> None:
        lock: Lock = redis_manager.client.lock(redis_manager.key(self.lock_name), timeout=self.lock_timeout)
        if not await lock.acquire(blocking=False):
            self.stderr.write("Another instance is migrating, waiting for it...\n")
            # No time limit: the lock expires if its owner crashes.
            await lock.acquire()
        try:
            # Nothing to do if the other one migrated, the rest if it crashed. In a thread: Alembic runs a loop of
            # its own, see migrations/env.py.
            await asyncio.to_thread(command.upgrade, self._create_config(), revision)
        finally:
            await lock.release()

    async def _wait_and_migrate(self, revision: str, /, *, wait: float) -> None:
        if wait > 0:
            await self._wait_for_database(wait)
        await self._migrate(revision)

    async def _run(self, revision: str, /, *, wait: float) -> None:
        try:
            await self._wait_and_migrate(revision, wait=wait)
        # Released after it expired.
        except LockError as err:
            raise CommandError(f"The migration outlived its lock, another instance may have run too: {err}") from None
        except RedisError as err:
            raise CommandError(f"Redis failed: {err}") from None
        finally:
            await redis_manager.close()

    def handle(self, args: Namespace, /) -> None:
        uvloop.run(self._run(args.revision, wait=args.wait))
        self.stdout.write(f"Database migrated to {args.revision}.\n")
