from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Final

import pytest
from pytest_bdd import given, then, when

from proxium.db import redis_manager
from proxium.management.commands import MigrateCommand

from ._async import async_step

if TYPE_CHECKING:
    from argparse import Namespace
    from concurrent.futures import Future, ThreadPoolExecutor

    from redis.asyncio import Redis
    from redis.asyncio.lock import Lock

# Seconds a waiting migration is given to finish anyway: it would, were the lock ignored.
WAITING_CHECK: Final[float] = 1.0
# Seconds a migration gets once nothing holds it back.
MIGRATION_TIMEOUT: Final[float] = 30.0


@given("the database is migrated")
def _(test_database: str) -> None:
    """Migrated by the fixture: `migrate` finds nothing to do, only the lock is tested."""


@given("another instance holds the migration lock", target_fixture="other_lock")
@async_step
async def _(redis_client: Redis) -> Lock:
    lock = redis_client.lock(redis_manager.key(MigrateCommand.lock_name), timeout=MigrateCommand.lock_timeout)
    assert await lock.acquire(blocking=False)
    return lock


@when("an instance migrates", target_fixture="migration")
def _(migration_executor: ThreadPoolExecutor, migration_args: Namespace) -> Future[int]:
    command = MigrateCommand(stdout=StringIO(), stderr=StringIO())
    return migration_executor.submit(command.run, migration_args)


@when("the other instance releases the migration lock")
@async_step
async def _(other_lock: Lock) -> None:
    await other_lock.release()


@then("the migration waits")
def _(migration: Future[int]) -> None:
    with pytest.raises(TimeoutError):
        migration.result(timeout=WAITING_CHECK)


@then("the migration finishes")
def _(migration: Future[int]) -> None:
    assert migration.result(timeout=MIGRATION_TIMEOUT) == 0


@then("the migration lock is free")
@async_step
async def _(redis_client: Redis) -> None:
    assert not await redis_client.exists(redis_manager.key(MigrateCommand.lock_name))
