from __future__ import annotations

from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis

from proxium.core import redis_settings
from proxium.db import redis_manager
from proxium.management.commands import MigrateCommand
from tests.redis_keys import TEST_KEY_PREFIX

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Iterator


@pytest.fixture
def redis_lock() -> MagicMock:
    """A Redis lock taken at once and released without a server."""
    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock()
    return lock


@pytest.fixture
def mocked_redis_manager(redis_lock: MagicMock) -> Iterator[MagicMock]:
    """`redis_manager` of `migrate`, handing out `redis_lock`."""
    manager = MagicMock()
    manager.key.side_effect = redis_manager.key
    manager.client.lock.return_value = redis_lock
    manager.close = AsyncMock()
    with patch("proxium.management.commands._migrate.redis_manager", manager):
        yield manager


@pytest.fixture
def redis_client(loop_runner: asyncio.Runner) -> Iterator[Redis]:
    """Redis of the tests by a client of its own: another instance next to the one under test."""
    # The last guard of live instances: the tests drop keys under it.
    if not redis_manager.key_prefix.startswith(TEST_KEY_PREFIX):
        raise RuntimeError(
            f"Refusing to run tests on keys {redis_manager.key_prefix!r}: it doesn't start with {TEST_KEY_PREFIX!r}.",
        )
    client = Redis.from_url(
        str(redis_settings.url),
        password=None if redis_settings.password is None else redis_settings.password.get_secret_value(),
    )

    yield client

    loop_runner.run(client.aclose())


@pytest.fixture
def migration_executor(loop_runner: asyncio.Runner, redis_client: Redis) -> Iterator[ThreadPoolExecutor]:
    """Runs `migrate` aside: it has a loop of its own, the steps go on meanwhile."""
    executor = ThreadPoolExecutor(max_workers=1)

    yield executor

    # A migration still waiting for the lock would wait forever.
    loop_runner.run(redis_client.delete(redis_manager.key(MigrateCommand.lock_name)))
    executor.shutdown(wait=True)


@pytest.fixture
def migration_args() -> Namespace:
    return Namespace(revision="head", wait=0)
