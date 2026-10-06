from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.db import Direction, LimitScope
from proxium.watchers import ConnectionLimitSnapshot, PolicySnapshot, RuleSnapshot, SpeedLimitSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker


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
def policy_snapshot_factory() -> Callable[..., PolicySnapshot]:
    """Global policies of one rule that always applies these limits. The same policy for equal `id`."""

    def create(
        *,
        id: int,  # noqa: A002
        connection_limits: tuple[ConnectionLimitSnapshot, ...] = (),
        speed_limits: tuple[SpeedLimitSnapshot, ...] = (),
    ) -> PolicySnapshot:
        rule = RuleSnapshot(
            id=id,
            condition={"kind": "always"},
            connection_limits=connection_limits,
            speed_limits=speed_limits,
        )
        return PolicySnapshot(id=id, is_global=True, rules=(rule,))

    return create
