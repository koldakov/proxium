from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from proxium.proxy import (
    ConnectionLimitExceeded,
    ConnectionLimitPolicy,
    IdentityScope,
    MemoryConnectionCounter,
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
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst)
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
        policy = SpeedLimitPolicy(IdentityScope(), rate=rate, burst=burst)
        grants = [await policy.admit(proxy_request, session) for _ in range(2)]
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await asyncio.gather(*(grant.on_sent(size) for grant in grants))

        # Assert
        assert loop.time() - started >= (size * len(grants) - burst) / rate
