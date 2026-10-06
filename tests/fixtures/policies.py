from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.db import Direction, LimitScope, QuotaPeriod
from proxium.policies import PeriodUsage, RuleSetBuilder
from proxium.proxy import Usage
from proxium.watchers import (
    ConnectionLimitSnapshot,
    PolicySnapshot,
    RuleSnapshot,
    SpeedLimitSnapshot,
    TrafficQuotaSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from faker import Faker

    from proxium.proxy import Identity


@pytest.fixture
def connection_limit_snapshot_factory(faker: Faker) -> Callable[..., ConnectionLimitSnapshot]:
    """Per-identity connection limits, a new one on every call unless `id` is given."""

    def create(*, id: int | None = None, max_connections: int | None = None) -> ConnectionLimitSnapshot:  # noqa: A002
        return ConnectionLimitSnapshot(
            id=faker.unique.random_int() if id is None else id,
            scope=LimitScope.IDENTITY,
            max_connections=faker.pyint(min_value=1, max_value=10) if max_connections is None else max_connections,
        )

    return create


@pytest.fixture
def speed_limit_snapshot(faker: Faker) -> SpeedLimitSnapshot:
    return SpeedLimitSnapshot(
        id=faker.unique.random_int(),
        scope=LimitScope.IDENTITY,
        direction=faker.enum(Direction),
        rate=faker.pyint(min_value=1),
        burst=faker.pyint(min_value=1),
    )


@pytest.fixture
def total_traffic_quota_snapshot(faker: Faker) -> TrafficQuotaSnapshot:
    """A quota that never resets: its period starts on the anchor day itself."""
    return TrafficQuotaSnapshot(
        id=faker.unique.random_int(),
        scope=LimitScope.IDENTITY,
        direction=faker.enum(Direction),
        max_bytes=faker.pyint(min_value=1),
        period=QuotaPeriod.TOTAL,
        period_length=1,
    )


@pytest.fixture
def policy_snapshot_factory(faker: Faker) -> Callable[..., PolicySnapshot]:
    """Policies of one rule that always applies these limits, global unless told. A new one on every call unless
    `id` is given, the same rule for equal `id`.
    """

    def create(
        *,
        id: int | None = None,  # noqa: A002
        is_global: bool = True,
        connection_limits: tuple[ConnectionLimitSnapshot, ...] = (),
        speed_limits: tuple[SpeedLimitSnapshot, ...] = (),
        traffic_quotas: tuple[TrafficQuotaSnapshot, ...] = (),
    ) -> PolicySnapshot:
        policy_id = faker.unique.random_int() if id is None else id
        rule = RuleSnapshot(
            id=policy_id,
            condition={"kind": "always"},
            connection_limits=connection_limits,
            speed_limits=speed_limits,
            traffic_quotas=traffic_quotas,
        )
        return PolicySnapshot(
            id=policy_id,
            is_global=is_global,
            global_starts_on=faker.date_object(),
            rules=(rule,),
        )

    return create


class RecordingPeriodUsage(PeriodUsage):
    """Nothing used, ever. Keeps the days usage was asked since, to see where quota periods start."""

    def __init__(self) -> None:
        self.asked_since: list[date] = []

    async def used_since(self, identity: Identity, since: date, /) -> Usage:
        self.asked_since.append(since)
        return Usage()


@pytest.fixture
def recording_period_usage() -> RecordingPeriodUsage:
    return RecordingPeriodUsage()


@pytest.fixture
def rule_set_builder(recording_period_usage: RecordingPeriodUsage) -> RuleSetBuilder:
    return RuleSetBuilder(recording_period_usage)
