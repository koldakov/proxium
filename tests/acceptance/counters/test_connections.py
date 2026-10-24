from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from proxium.counters import RedisConnectionCounter
from proxium.db import redis_manager
from proxium.proxy import ConnectionLimitExceeded

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.counters import RedisConnectionLeases

# Longer than any test: leases expire only where a test waits for it.
_LONG_LEASE = 60.0
# Renewed every third of it.
_SHORT_LEASE = 0.3


class TestRedisConnectionCounter:
    def test_acquire_refuses_over_limit_of_other_instance(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_connection_leases_factory: Callable[[float], RedisConnectionLeases],
        connection_limit_name: str,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        # Two instances on one Redis.
        first, second = (
            RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_LONG_LEASE))
            for _ in range(2)
        )
        for _ in range(limit):
            loop_runner.run(first.acquire(key, limit=limit))

        # Act
        with pytest.raises(ConnectionLimitExceeded):
            loop_runner.run(second.acquire(key, limit=limit))

    def test_acquire_admits_after_other_instance_released(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_connection_leases_factory: Callable[[float], RedisConnectionLeases],
        connection_limit_name: str,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        first, second = (
            RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_LONG_LEASE))
            for _ in range(2)
        )
        grants = [loop_runner.run(first.acquire(key, limit=limit)) for _ in range(limit)]
        loop_runner.run(grants[0].release())

        # Act
        # Nothing raised.
        loop_runner.run(second.acquire(key, limit=limit))

    def test_acquire_admits_after_lease_of_stopped_instance_expired(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_connection_leases_factory: Callable[[float], RedisConnectionLeases],
        connection_limit_name: str,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        # Never started, as if crashed: renews nothing.
        stopped = RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_SHORT_LEASE))
        second = RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_LONG_LEASE))
        for _ in range(limit):
            loop_runner.run(stopped.acquire(key, limit=limit))
        loop_runner.run(asyncio.sleep(_SHORT_LEASE * 2))

        # Act
        # Nothing raised.
        loop_runner.run(second.acquire(key, limit=limit))

    def test_acquire_refuses_over_limit_of_instance_renewing_past_lease(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_connection_leases_factory: Callable[[float], RedisConnectionLeases],
        connection_limit_name: str,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        renewing_leases = redis_connection_leases_factory(_SHORT_LEASE)
        renewing = RedisConnectionCounter(connection_limit_name, leases=renewing_leases)
        second = RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_LONG_LEASE))

        async def acquire_and_wait() -> None:
            renewing_leases.start()
            for _ in range(limit):
                await renewing.acquire(key, limit=limit)
            await asyncio.sleep(_SHORT_LEASE * 2)

        loop_runner.run(acquire_and_wait())

        # Act
        with pytest.raises(ConnectionLimitExceeded):
            loop_runner.run(second.acquire(key, limit=limit))

    def test_acquire_counts_connections_admitted_in_outage_once_redis_back(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_connection_leases_factory: Callable[[float], RedisConnectionLeases],
        connection_limit_name: str,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        recovering_leases = redis_connection_leases_factory(_LONG_LEASE)
        recovering = RedisConnectionCounter(connection_limit_name, leases=recovering_leases)
        second = RedisConnectionCounter(connection_limit_name, leases=redis_connection_leases_factory(_LONG_LEASE))
        # Every script call fails as if Redis were down: admitted in this process alone.
        with patch.object(redis_manager.client, "evalsha", side_effect=RedisConnectionError()):
            for _ in range(limit):
                loop_runner.run(recovering.acquire(key, limit=limit))

        async def wait_for_probe() -> None:
            recovering_leases.start()
            # Probed every 50 ms: Redis answers, the open connections go there.
            await asyncio.sleep(0.3)

        loop_runner.run(wait_for_probe())

        # Act
        with pytest.raises(ConnectionLimitExceeded):
            loop_runner.run(second.acquire(key, limit=limit))
