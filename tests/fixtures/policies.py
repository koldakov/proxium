from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from proxium.db import Direction, LimitScope, QuotaPeriod
from proxium.policies import Condition, PeriodUsage, RuleSetBuilder
from proxium.proxy import Usage
from proxium.watchers import (
    ConnectionLimitSnapshot,
    PolicySnapshot,
    RuleSnapshot,
    SpeedLimitSnapshot,
    TrafficQuotaSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import date, datetime

    from faker import Faker

    from proxium.proxy import Identity, Request, Session


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
    """Policies of one rule that applies these limits, always unless `condition` is given, global unless told.
    A new one on every call unless `id` is given, the same rule for equal `id`.
    """

    # Keyword-only, one per field of the snapshot a test may set.
    def create(  # noqa: PLR0913
        *,
        id: int | None = None,  # noqa: A002
        is_global: bool = True,
        condition: Mapping[str, Any] | None = None,
        connection_limits: tuple[ConnectionLimitSnapshot, ...] = (),
        speed_limits: tuple[SpeedLimitSnapshot, ...] = (),
        traffic_quotas: tuple[TrafficQuotaSnapshot, ...] = (),
    ) -> PolicySnapshot:
        policy_id = faker.unique.random_int() if id is None else id
        rule = RuleSnapshot(
            id=policy_id,
            condition={"kind": "always"} if condition is None else condition,
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


class SwitchCondition(Condition):
    """Matches while `matching` is on, switched by the test as it goes, e.g. as a schedule would at night."""

    def __init__(self, *, matching: bool) -> None:
        self.matching: bool = matching

    def matches(self, request: Request, session: Session, /) -> bool:
        return self.matching


@pytest.fixture
def switch_condition() -> SwitchCondition:
    return SwitchCondition(matching=True)


class ManualClock:
    """The time `now`, set by the test: a schedule checked at any moment without waiting for it."""

    def __init__(self, now: datetime, /) -> None:
        self.now: datetime = now

    def __call__(self) -> datetime:
        return self.now
