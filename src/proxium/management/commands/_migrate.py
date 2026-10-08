import asyncio
import time
from typing import TYPE_CHECKING, ClassVar

import uvloop
from alembic import command
from alembic.config import Config
from asyncpg import CannotConnectNowError
from sqlalchemy import select

from proxium.db import session_manager
from proxium.management._base import BaseCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace


class MigrateCommand(BaseCommand):
    """Applies Alembic migrations up to `revision`, from the installed package: no alembic.ini needed."""

    name: ClassVar[str] = "migrate"
    help: ClassVar[str] = "Apply database migrations."

    script_location: ClassVar[str] = "proxium.db:migrations"
    # Seconds between connection attempts with --wait.
    wait_interval: ClassVar[float] = 1

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
        parser.add_argument(
            "--lock",
            action="store_true",
            help="Hold a lock while migrating, so several instances can start at once. Not implemented yet.",
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

    def handle(self, args: Namespace, /) -> None:
        if args.lock:
            raise NotImplementedError("Migration lock needs a shared lock store, e.g. Redis.")

        if args.wait > 0:
            uvloop.run(self._wait_for_database(args.wait))
        command.upgrade(self._create_config(), args.revision)
        self.stdout.write(f"Database migrated to {args.revision}.\n")
