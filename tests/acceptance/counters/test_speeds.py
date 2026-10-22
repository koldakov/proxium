from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from proxium.counters import RedisSpeedBucket
from proxium.proxy import Direction

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.counters import RedisSpeedBatches

# Of `redis_speed_batches_factory`: each instance may go over a limit by one batch, 10 ms of the rate.
_BATCH = 0.01


class TestRedisSpeedBucket:
    def test_take_shares_rate_between_instances(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
        speed_limit_name: str,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        # Two instances: each with batches of its own, one bucket in Redis.
        buckets = [RedisSpeedBucket(speed_limit_name, batches=redis_speed_batches_factory()) for _ in range(2)]
        key = faker.uuid4()
        for bucket in buckets:
            bucket.open(key)

        async def take() -> float:
            loop = asyncio.get_running_loop()
            started = loop.time()
            await asyncio.gather(
                *(bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=burst) for bucket in buckets),
            )
            return loop.time() - started

        # Act
        elapsed = loop_runner.run(take())

        # Assert
        # Counted apart, each would take its burst and finish in half the time.
        assert elapsed >= (size * len(buckets) - burst - len(buckets) * rate * _BATCH) / rate

    def test_take_shares_rate_between_instances_when_their_terms_differ(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
        speed_limit_name: str,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=3, max_value=4)
        # An edited burst, seen by one instance only: until the next lookup of policies, up to
        # PROXY_SETTINGS_POLL_INTERVAL, they take from one bucket by different terms.
        bursts = (burst, burst * 2)
        buckets = [RedisSpeedBucket(speed_limit_name, batches=redis_speed_batches_factory()) for _ in bursts]
        key = faker.uuid4()
        for bucket in buckets:
            bucket.open(key)

        async def take() -> float:
            loop = asyncio.get_running_loop()
            started = loop.time()
            await asyncio.gather(
                *(
                    bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=instance_burst)
                    for bucket, instance_burst in zip(buckets, bursts, strict=True)
                ),
            )
            return loop.time() - started

        # Act
        elapsed = loop_runner.run(take())

        # Assert
        # At most the larger burst at once, the rest at the rate. Each forgiving the other's debt, they'd finish in
        # about half the time, as if counted apart.
        assert elapsed >= (size * len(buckets) - max(bursts) - len(buckets) * rate * _BATCH) / rate

    def test_take_passes_at_most_burst_after_pause(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        redis_speed_batches_factory: Callable[[], RedisSpeedBatches],
        speed_limit_name: str,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=3, max_value=4)
        bucket = RedisSpeedBucket(speed_limit_name, batches=redis_speed_batches_factory())
        key = faker.uuid4()
        bucket.open(key)

        async def take_after_pause() -> float:
            # Creates the bucket in Redis, then a pause long enough to refill three bursts if nothing capped it.
            await bucket.take(key, Direction.RECEIVED, 1, rate=rate, burst=burst)
            await asyncio.sleep(burst * 3 / rate)
            loop = asyncio.get_running_loop()
            started = loop.time()
            await bucket.take(key, Direction.RECEIVED, size, rate=rate, burst=burst)
            return loop.time() - started

        # Act
        elapsed = loop_runner.run(take_after_pause())

        # Assert
        # The burst at once, plus what's left of the first batch, the rest at the rate.
        assert elapsed >= (size - burst - rate * _BATCH) / rate
