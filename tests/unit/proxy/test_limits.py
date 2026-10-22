from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from proxium.proxy import (
    ConnectionLimitExceeded,
    ConnectionLimitPolicy,
    Direction,
    IdentityScope,
    MemoryConnectionCounter,
    MemorySpeedBucket,
    SpeedLimitPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session


class TestConnectionLimitPolicy:
    async def test_admit_raises_connection_limit_exceeded_when_limit_reached(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        counter = MemoryConnectionCounter()
        policy = ConnectionLimitPolicy(IdentityScope(), limit=limit, counter=counter)
        for _ in range(limit):
            await policy.admit(proxy_request, session)

        # Act & Assert
        with pytest.raises(ConnectionLimitExceeded):
            await policy.admit(proxy_request, session)

    async def test_admit_returns_grant_when_released_connection_frees_slot(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        counter = MemoryConnectionCounter()
        policy = ConnectionLimitPolicy(IdentityScope(), limit=limit, counter=counter)
        grants = [await policy.admit(proxy_request, session) for _ in range(limit)]
        await faker.random_element(grants).release()

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert counter.counts[proxy_request.identity.subject] == limit

    async def test_admit_returns_grant_when_other_key_reached_limit(
        self,
        faker: Faker,
        proxy_request_factory: Callable[[], Request],
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        counter = MemoryConnectionCounter()
        policy = ConnectionLimitPolicy(IdentityScope(), limit=limit, counter=counter)
        busy_request = proxy_request_factory()
        for _ in range(limit):
            await policy.admit(busy_request, session)
        proxy_request = proxy_request_factory()

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert counter.counts[proxy_request.identity.subject] == 1

    async def test_release_drops_key_when_last_connection_closed(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        counter = MemoryConnectionCounter()
        policy = ConnectionLimitPolicy(
            IdentityScope(),
            limit=faker.pyint(min_value=1, max_value=10),
            counter=counter,
        )
        grant = await policy.admit(proxy_request, session)

        # Act
        await grant.release()

        # Assert
        assert proxy_request.identity.subject not in counter.counts

    async def test_admit_raises_connection_limit_exceeded_when_shared_counter_reaches_new_limit(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        # A limit edited in place: the new policy gets the counter of the old one.
        old_limit = faker.pyint(min_value=2, max_value=10)
        counter = MemoryConnectionCounter()
        old_policy = ConnectionLimitPolicy(IdentityScope(), limit=old_limit, counter=counter)
        for _ in range(old_limit):
            await old_policy.admit(proxy_request, session)
        policy = ConnectionLimitPolicy(
            IdentityScope(),
            limit=faker.pyint(min_value=1, max_value=old_limit),
            counter=counter,
        )

        # Act & Assert
        with pytest.raises(ConnectionLimitExceeded):
            await policy.admit(proxy_request, session)

    async def test_admit_returns_grant_when_connection_of_shared_counter_released(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        counter = MemoryConnectionCounter()
        old_policy = ConnectionLimitPolicy(IdentityScope(), limit=limit, counter=counter)
        old_grants = [await old_policy.admit(proxy_request, session) for _ in range(limit)]
        policy = ConnectionLimitPolicy(IdentityScope(), limit=limit, counter=counter)
        await faker.random_element(old_grants).release()

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert counter.counts[proxy_request.identity.subject] == limit


class TestSpeedLimitPolicy:
    async def test_on_sent_waits_for_rate_when_bytes_exceed_burst(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst, bucket=MemorySpeedBucket())
        grant = await policy.admit(proxy_request, session)
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_sent(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_on_sent_shares_rate_when_connections_have_same_key(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst, bucket=MemorySpeedBucket())
        grants = [await policy.admit(proxy_request, session) for _ in range(2)]
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await asyncio.gather(*(grant.on_sent(size) for grant in grants))

        # Assert
        assert loop.time() - started >= (size * len(grants) - burst) / rate

    async def test_on_received_takes_new_rate_when_updated(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Before: a burst a second, the bytes would take seconds. After: 5 ms per burst.
        old_rate = burst
        rate = burst * 200
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = SpeedLimitPolicy(IdentityScope(), rate=old_rate, burst=burst, bucket=MemorySpeedBucket())
        grant = await policy.admit(proxy_request, session)
        policy.update(rate=rate, burst=burst, direction=Direction.BOTH)
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started < (size - burst) / old_rate

    async def test_on_received_stops_waiting_when_retired_during_chunk(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 200 ms: the whole chunk would take over a second.
        rate = burst * 5
        size = burst * faker.pyint(min_value=8, max_value=10)
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst, bucket=MemorySpeedBucket())
        grant = await policy.admit(proxy_request, session)
        loop = asyncio.get_running_loop()
        started = loop.time()
        chunk = asyncio.create_task(grant.on_received(size))
        # The first burst goes at once, the chunk waits for the next.
        await asyncio.sleep(0)

        # Act
        policy.retire()
        await chunk

        # Assert
        assert loop.time() - started < (size - burst) / rate

    async def test_on_received_stops_waiting_when_released_during_chunk(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 200 ms: the whole chunk would take over a second.
        rate = burst * 5
        size = burst * faker.pyint(min_value=8, max_value=10)
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst, bucket=MemorySpeedBucket())
        grant = await policy.admit(proxy_request, session)
        loop = asyncio.get_running_loop()
        started = loop.time()
        chunk = asyncio.create_task(grant.on_received(size))
        # The first burst goes at once, the chunk waits for the next.
        await asyncio.sleep(0)

        # Act
        # As the other direction does switching rules: the last connection of the key, its state goes with it.
        await grant.release()
        await chunk

        # Assert
        assert loop.time() - started < (size - burst) / rate

    async def test_on_received_returns_at_once_when_retired(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # One burst a second: still limited, the bytes would take seconds.
        rate = burst
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst, bucket=MemorySpeedBucket())
        grant = await policy.admit(proxy_request, session)
        policy.retire()
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started < (size - burst) / rate
