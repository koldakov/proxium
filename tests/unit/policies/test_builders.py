from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.policies import RuleSetBuilder, RuleSetPolicy
from proxium.proxy import ConnectionLimitExceeded

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session
    from proxium.watchers import ConnectionLimitSnapshot, PolicySnapshot, SpeedLimitSnapshot


class TestRuleSetBuilder:
    async def test_build_keeps_counting_open_connections_when_max_connections_changed(
        self,
        faker: Faker,
        connection_limit_snapshot_factory: Callable[..., ConnectionLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        builder = RuleSetBuilder()
        policy_id = faker.unique.random_int()
        limit = connection_limit_snapshot_factory(max_connections=faker.pyint(min_value=2, max_value=10))
        changed_limit = connection_limit_snapshot_factory(id=limit.id, max_connections=1)
        old_policy = RuleSetPolicy(
            builder.build([policy_snapshot_factory(id=policy_id, connection_limits=(limit,))]),
        )
        await old_policy.admit(proxy_request, session)

        # Act
        policy = RuleSetPolicy(
            builder.build([policy_snapshot_factory(id=policy_id, connection_limits=(changed_limit,))]),
        )

        # Assert
        with pytest.raises(ConnectionLimitExceeded):
            await policy.admit(proxy_request, session)

    def test_build_reuses_speed_limit_when_unchanged(
        self,
        faker: Faker,
        speed_limit_snapshot: SpeedLimitSnapshot,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
    ) -> None:
        # Arrange
        builder = RuleSetBuilder()
        policy = policy_snapshot_factory(id=faker.unique.random_int(), speed_limits=(speed_limit_snapshot,))
        old_rule_set = builder.build([policy])

        # Act
        rule_set = builder.build([policy])

        # Assert
        assert rule_set.policies[policy.id][0].limits[0] is old_rule_set.policies[policy.id][0].limits[0]
