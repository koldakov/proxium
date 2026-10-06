from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from proxium.policies import RuleSetBuilder, RuleSetPolicy, policy_claims
from proxium.proxy import ConnectionLimitExceeded

if TYPE_CHECKING:
    from collections.abc import Callable

    from proxium.proxy import Request, Session
    from proxium.watchers import ConnectionLimitSnapshot, PolicySnapshot, SpeedLimitSnapshot, TrafficQuotaSnapshot
    from tests.fixtures.policies import RecordingPeriodUsage


class TestRuleSetBuilder:
    async def test_build_keeps_counting_open_connections_when_max_connections_changed(
        self,
        rule_set_builder: RuleSetBuilder,
        connection_limit_snapshot_factory: Callable[..., ConnectionLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        limit = connection_limit_snapshot_factory()
        changed_limit = connection_limit_snapshot_factory(id=limit.id, max_connections=1)
        old_snapshot = policy_snapshot_factory(connection_limits=(limit,))
        old_policy = RuleSetPolicy(rule_set_builder.build([old_snapshot]))
        await old_policy.admit(proxy_request, session)

        # Act
        policy = RuleSetPolicy(
            rule_set_builder.build([policy_snapshot_factory(id=old_snapshot.id, connection_limits=(changed_limit,))]),
        )

        # Assert
        with pytest.raises(ConnectionLimitExceeded):
            await policy.admit(proxy_request, session)

    def test_build_reuses_speed_limit_when_unchanged(
        self,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot: SpeedLimitSnapshot,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
    ) -> None:
        # Arrange
        policy = policy_snapshot_factory(speed_limits=(speed_limit_snapshot,))
        old_rule_set = rule_set_builder.build([policy])

        # Act
        rule_set = rule_set_builder.build([policy])

        # Assert
        assert rule_set.policies[policy.id][0].limits[0] is old_rule_set.policies[policy.id][0].limits[0]

    async def test_build_counts_quota_of_global_policy_from_its_start(
        self,
        recording_period_usage: RecordingPeriodUsage,
        total_traffic_quota_snapshot: TrafficQuotaSnapshot,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        policy = policy_snapshot_factory(traffic_quotas=(total_traffic_quota_snapshot,))
        # Assigned as well, from another day: a global policy counts from its own.
        assigned_on = policy.global_starts_on - timedelta(days=1)
        proxy_request = proxy_request_factory(claims=policy_claims({policy.id: assigned_on}))
        rule_set_policy = RuleSetPolicy(RuleSetBuilder(recording_period_usage).build([policy]))

        # Act
        await rule_set_policy.admit(proxy_request, session)

        # Assert
        assert recording_period_usage.asked_since == [policy.global_starts_on]

    async def test_build_counts_quota_of_assigned_policy_from_assignment_start(
        self,
        recording_period_usage: RecordingPeriodUsage,
        total_traffic_quota_snapshot: TrafficQuotaSnapshot,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        policy = policy_snapshot_factory(is_global=False, traffic_quotas=(total_traffic_quota_snapshot,))
        # Another day than the policy's: an assigned policy counts from its assignment's.
        assigned_on = policy.global_starts_on + timedelta(days=1)
        proxy_request = proxy_request_factory(claims=policy_claims({policy.id: assigned_on}))
        rule_set_policy = RuleSetPolicy(RuleSetBuilder(recording_period_usage).build([policy]))

        # Act
        await rule_set_policy.admit(proxy_request, session)

        # Assert
        assert recording_period_usage.asked_since == [assigned_on]
