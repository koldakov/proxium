from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy import EMPTY_GRANT, Direction, QuotaExceeded, QuotaPolicy, Usage

if TYPE_CHECKING:
    from faker import Faker

    from proxium.proxy import Request, Session
    from tests.fixtures.proxy import StaticMeter, UnmeteringMeter


class TestQuotaPolicy:
    async def test_admit_raises_quota_exceeded_when_both_ways_together_reach_limit(
        self,
        faker: Faker,
        static_meter: StaticMeter,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        sent = faker.pyint(min_value=1, max_value=1000)
        received = faker.pyint(min_value=1, max_value=1000)
        static_meter.usage = Usage(sent=sent, received=received)
        policy = QuotaPolicy(static_meter, limit=sent + received, direction=Direction.BOTH)

        # Act & Assert
        with pytest.raises(QuotaExceeded):
            await policy.admit(proxy_request, session)

    async def test_admit_returns_grant_when_other_direction_over_limit(
        self,
        faker: Faker,
        static_meter: StaticMeter,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=2, max_value=1000)
        static_meter.usage = Usage(sent=limit, received=limit - 1)
        policy = QuotaPolicy(static_meter, limit=limit, direction=Direction.RECEIVED)

        # Act
        grant = await policy.admit(proxy_request, session)

        # Assert
        # Admitted and watched: the tunnel is checked again as it goes.
        assert grant is not EMPTY_GRANT

    async def test_admit_returns_empty_grant_when_client_unmetered(
        self,
        faker: Faker,
        unmetering_meter: UnmeteringMeter,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        policy = QuotaPolicy(unmetering_meter, limit=faker.pyint(min_value=1))

        # Act
        grant = await policy.admit(proxy_request, session)

        # Assert
        assert grant is EMPTY_GRANT

    async def test_on_received_raises_quota_exceeded_when_used_up_after_admit(
        self,
        faker: Faker,
        static_meter: StaticMeter,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=1000)
        policy = QuotaPolicy(static_meter, limit=limit, check_interval=0)
        grant = await policy.admit(proxy_request, session)
        # Other connections of the client used it up meanwhile.
        static_meter.usage = Usage(received=limit)

        # Act & Assert
        with pytest.raises(QuotaExceeded):
            await grant.on_received(faker.pyint(min_value=1))
