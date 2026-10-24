from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from proxium.counters import RedisConnectionCounter, RedisConnectionLeases
from proxium.db import redis_manager
from proxium.proxy import ConnectionCountUnavailable, ConnectionLimitExceeded

if TYPE_CHECKING:
    from faker import Faker


class TestRedisConnectionLeases:
    def test_init_raises_value_error_on_negative_spare_renewals(self, faker: Faker) -> None:
        # Arrange
        spare_renewals = faker.pyint(min_value=-10, max_value=-1)

        # Act
        with pytest.raises(ValueError, match="Spare renewals can't be negative"):
            RedisConnectionLeases(spare_renewals=spare_renewals)


class TestRedisConnectionCounter:
    async def test_acquire_takes_empty_key_suffix_for_none_key(self, faker: Faker) -> None:
        # Arrange
        name = f"{faker.unique.random_int()}:global"
        counter = RedisConnectionCounter(name, leases=RedisConnectionLeases())

        # Act
        # Admitted, as Redis would answer.
        with patch.object(redis_manager.client, "evalsha", new_callable=AsyncMock, return_value=1) as evalsha:
            await counter.acquire(None, limit=faker.pyint(min_value=1))

        # Assert
        # Called with the script's sha, the number of keys, then the key.
        assert evalsha.call_args.args[2] == redis_manager.key(f"limit:connections:{name}:")

    async def test_acquire_limits_locally_when_redis_fails(self, faker: Faker) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=5)
        key = faker.uuid4()
        counter = RedisConnectionCounter(
            f"{faker.unique.random_int()}:identity",
            leases=RedisConnectionLeases(outage_timeout=60.0),
        )

        # Act
        # Every script call fails as if Redis were down.
        with patch.object(redis_manager.client, "evalsha", side_effect=RedisConnectionError()):
            for _ in range(limit):
                await counter.acquire(key, limit=limit)
            with pytest.raises(ConnectionLimitExceeded):
                await counter.acquire(key, limit=limit)

    async def test_acquire_raises_connection_count_unavailable_after_outage_timeout(self, faker: Faker) -> None:
        # Arrange
        outage_timeout = 0.01
        limit = faker.pyint(min_value=2, max_value=5)
        key = faker.uuid4()
        counter = RedisConnectionCounter(
            f"{faker.unique.random_int()}:identity",
            leases=RedisConnectionLeases(outage_timeout=outage_timeout),
        )

        # Act
        with patch.object(redis_manager.client, "evalsha", side_effect=RedisConnectionError()):
            # Within the outage timeout: admitted in this process alone.
            await counter.acquire(key, limit=limit)
            await asyncio.sleep(outage_timeout * 2)
            with pytest.raises(ConnectionCountUnavailable):
                await counter.acquire(key, limit=limit)
