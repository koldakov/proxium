from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from proxium.counters import RedisSpeedBucket
from proxium.db import redis_manager
from proxium.proxy import Direction

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.counters import RedisSpeedBatches


class TestRedisSpeedBucket:
    async def test_take_limits_locally_when_redis_fails(
        self,
        faker: Faker,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        bucket = RedisSpeedBucket(f"{faker.unique.random_int()}:identity", batches=redis_speed_batches_factory())
        key = faker.uuid4()
        bucket.open(key)
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        # Every script call fails as if Redis were down.
        with patch.object(redis_manager.client, "evalsha", side_effect=RedisConnectionError()):
            await bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=burst)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_take_limits_key_locally_and_keeps_other_keys_on_redis_when_script_fails(
        self,
        faker: Faker,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        bucket = RedisSpeedBucket(f"{faker.unique.random_int()}:identity", batches=redis_speed_batches_factory())
        key, other_key = keys = (faker.uuid4(), faker.uuid4())
        for opened in keys:
            bucket.open(opened)
        loop = asyncio.get_running_loop()

        # Act
        # An error of the script, not an outage: Redis answers, the call fails.
        with patch.object(redis_manager.client, "evalsha", side_effect=ResponseError()) as evalsha:
            started = loop.time()
            await bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=burst)
            elapsed = loop.time() - started
            await bucket.take(other_key, Direction.RECEIVED, 1, rate=rate, burst=burst)

        # Assert
        assert elapsed >= (size - burst) / rate
        # Each key asked Redis once, the other one too: the process wasn't taken off it.
        assert evalsha.call_count == len(keys)

    async def test_take_drops_batch_left_of_old_rate_when_limit_edited(
        self,
        faker: Faker,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms by the new rate.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        bucket = RedisSpeedBucket(f"{faker.unique.random_int()}:identity", batches=redis_speed_batches_factory())
        key = faker.uuid4()
        bucket.open(key)
        loop = asyncio.get_running_loop()
        # By the old terms Redis gives a batch at once, of four chunks, then fails: the rest is limited here, by the
        # new rate, unless the old batch is spent.
        with patch.object(
            redis_manager.client,
            "evalsha",
            new_callable=AsyncMock,
            side_effect=[0, RedisConnectionError()],
        ):
            await bucket.take(key, Direction.RECEIVED, 1, rate=rate * 1_000, burst=size * 4)
            started = loop.time()

            # Act
            await bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=burst)

        # Assert
        assert loop.time() - started >= (size - burst) / rate
