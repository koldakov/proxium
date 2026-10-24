from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.counters import RedisConnectionLeases, RedisSpeedBatches
from proxium.db import redis_manager

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Iterator

    from faker import Faker
    from redis.asyncio import Redis


@pytest.fixture
def redis_speed_batches_factory() -> Callable[[], RedisSpeedBatches]:
    """Batches of a new process on every call: several of them share buckets in Redis as instances do. Batches of
    10 ms, so tests wait little for the rate.
    """

    def create() -> RedisSpeedBatches:
        return RedisSpeedBatches(batch=0.01)

    return create


@pytest.fixture
def shared_redis_manager(loop_runner: asyncio.Runner) -> Iterator[None]:
    """`redis_manager` used on the tests' loop, its connections closed after: they belong to this loop, and other
    tests use `redis_manager` from loops of their own, e.g. `migrate`. It connects again on the next command.
    """
    yield

    loop_runner.run(redis_manager.close())


@pytest.fixture
def speed_limit_name(
    faker: Faker,
    loop_runner: asyncio.Runner,
    redis_client: Redis,
    shared_redis_manager: None,
) -> Iterator[str]:
    """The name of a speed limit's buckets in the tests' Redis, new for every test. Its buckets are dropped after."""
    name = f"{faker.unique.random_int()}:identity"

    yield name

    async def drop() -> None:
        async for key in redis_client.scan_iter(match=redis_manager.key(f"limit:speed:{name}:*")):
            await redis_client.delete(key)

    loop_runner.run(drop())


@pytest.fixture
def traffic_owner(
    faker: Faker,
    loop_runner: asyncio.Runner,
    redis_client: Redis,
    shared_redis_manager: None,
) -> Iterator[str]:
    """An owner of traffic shared in the tests' Redis, new for every test. Its hash is dropped after."""
    owner = f"traffic:{faker.unique.random_int()}"

    yield owner

    async def drop() -> None:
        # Of whatever format.
        async for key in redis_client.scan_iter(match=redis_manager.key(f"quota:traffic:*:{owner}")):
            await redis_client.delete(key)

    loop_runner.run(drop())


@pytest.fixture
def redis_connection_leases_factory(
    loop_runner: asyncio.Runner,
    shared_redis_manager: None,
) -> Iterator[Callable[[float], RedisConnectionLeases]]:
    """Leases of a new process on every call, for `lease` seconds: several of them share connection limits in Redis as
    instances do. Redis is probed every 50 ms, so tests wait little for it to come back. All are closed after.
    """
    created: list[RedisConnectionLeases] = []

    def create(lease: float, /) -> RedisConnectionLeases:
        leases = RedisConnectionLeases(lease=lease, outage_timeout=60.0, probe_interval=0.05)
        created.append(leases)
        return leases

    yield create

    for leases in created:
        loop_runner.run(leases.close())


@pytest.fixture
def connection_limit_name(
    faker: Faker,
    loop_runner: asyncio.Runner,
    redis_client: Redis,
    shared_redis_manager: None,
) -> Iterator[str]:
    """The name of a connection limit's keys in the tests' Redis, new for every test. Its keys are dropped after."""
    name = f"{faker.unique.random_int()}:identity"

    yield name

    async def drop() -> None:
        async for key in redis_client.scan_iter(match=redis_manager.key(f"limit:connections:{name}:*")):
            await redis_client.delete(key)

    loop_runner.run(drop())
