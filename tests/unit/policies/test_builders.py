from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from proxium.db import LimitScope
from proxium.policies import (
    InvalidPolicyError,
    RuleSetBuilder,
    RuleSetPolicy,
    UnknownScopeError,
    UnsupportedQuotaScopeError,
    policy_claims,
)
from proxium.proxy import ConnectionLimitExceeded
from tests.fixtures.policies import MemoryConnectionCounters, MemorySpeedBuckets

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from faker import Faker

    from proxium.policies import RuleSet
    from proxium.proxy import Grant, Request, Session
    from proxium.watchers import ConnectionLimitSnapshot, PolicySnapshot, SpeedLimitSnapshot, TrafficQuotaSnapshot
    from tests.fixtures.policies import RecordingPeriodUsage


class TestRuleSetBuilder:
    def test_build_raises_invalid_policy_error_naming_policy_and_rule_when_condition_unknown(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
    ) -> None:
        # Arrange
        policy = policy_snapshot_factory(condition={"kind": f"unknown-{faker.word()}"})

        # Act & Assert
        with pytest.raises(InvalidPolicyError, match=f"Policy {policy.id}, rule {policy.rules[0].id}:"):
            rule_set_builder.build([policy])

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

    async def test_build_gives_open_connections_new_rate_when_speed_limit_rate_changed(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Before: a burst a second, the bytes would take seconds. After: 5 ms per burst.
        old_rate = burst
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=old_rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        rule_set_builder.build(
            [policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, rate=burst * 200),))],
        )
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started < (size - burst) / old_rate

    async def test_build_keeps_old_speed_limit_for_open_connections_when_scope_changed(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        # Open connections are counted by the keys of the old scope: they can't move to the new one.
        rule_set_builder.build(
            [policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, scope=LimitScope.CONNECTION),))],
        )
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_build_gives_new_rate_to_old_scope_connections_when_scope_changed_back(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Before: a burst a second, the bytes would take seconds. After: 5 ms per burst.
        old_rate = burst
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=old_rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        rule_set_builder.build(
            [policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, scope=LimitScope.CONNECTION),))],
        )
        # Back to the first scope: its policy, kept for the open connection, is reused and gets the edit.
        rule_set_builder.build(
            [policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, rate=burst * 200),))],
        )
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started < (size - burst) / old_rate

    async def test_build_stops_slowing_connections_of_both_scopes_when_removed_after_scope_changed(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # A burst a second: still limited, the bytes would take seconds.
        rate = burst
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        old_scope_grant = await open_connection(rule_set_builder.build([old_snapshot]))
        new_scope_rule_set = rule_set_builder.build(
            [policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, scope=LimitScope.CONNECTION),))],
        )
        new_scope_grant = await open_connection(new_scope_rule_set)
        rule_set_builder.build([policy_snapshot_factory(id=old_snapshot.id)])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await asyncio.gather(old_scope_grant.on_received(size), new_scope_grant.on_received(size))

        # Assert
        assert loop.time() - started < (size - burst) / rate

    async def test_build_slows_open_connections_again_when_policy_turned_on_again(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = policy_snapshot_factory(speed_limits=(speed_limit_snapshot_factory(rate=rate, burst=burst),))
        grant = await open_connection(rule_set_builder.build([policy]))
        # Turned off: the proxy reads active policies only.
        rule_set_builder.build([])
        rule_set_builder.build([policy])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_build_keeps_speed_limit_rate_when_other_speed_limit_edited_to_invalid(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms. The failed edit would make it 1 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        other_limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        snapshot = policy_snapshot_factory(speed_limits=(limit,))
        # Not assigned to the client: only `limit` slows its connection.
        other_snapshot = policy_snapshot_factory(is_global=False, speed_limits=(other_limit,))
        # Held as the proxy holds its current rule set: `other_limit` stays an existing policy, edited, not built anew.
        rule_set = rule_set_builder.build([snapshot, other_snapshot])
        grant = await open_connection(rule_set)
        # Both exist and both are edited, the second to an invalid rate: applied one by one, the first edit would be
        # in effect by the time the second fails.
        edited = policy_snapshot_factory(id=snapshot.id, speed_limits=(replace(limit, rate=burst * 1_000),))
        invalid = policy_snapshot_factory(
            id=other_snapshot.id,
            is_global=False,
            speed_limits=(replace(other_limit, rate=0),),
        )
        with pytest.raises(InvalidPolicyError):
            rule_set_builder.build([edited, invalid])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_build_slows_rule_set_in_use_again_when_policy_turned_on_again(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        policy = policy_snapshot_factory(speed_limits=(speed_limit_snapshot_factory(rate=rate, burst=burst),))
        # Held as an open connection holds its rule set, with no grant of the limit: e.g. its rule applies at night.
        rule_set = rule_set_builder.build([policy])
        rule_set_builder.build([])
        rule_set_builder.build([policy])
        # Night comes: the connection takes the limits of that rule.
        grant = await open_connection(rule_set)
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_build_slows_old_scope_connections_again_when_policy_turned_on_after_scope_changed(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        new_scope = policy_snapshot_factory(
            id=old_snapshot.id,
            speed_limits=(replace(limit, scope=LimitScope.CONNECTION),),
        )
        rule_set_builder.build([new_scope])
        # Turned off and on: both scopes are retired, then only the new one is in the build.
        rule_set_builder.build([])
        rule_set_builder.build([new_scope])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

    async def test_build_stops_slowing_open_connections_when_speed_limit_removed(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # A burst a second: still limited, the bytes would take seconds.
        rate = burst
        size = burst * faker.pyint(min_value=2, max_value=3)
        old_snapshot = policy_snapshot_factory(speed_limits=(speed_limit_snapshot_factory(rate=rate, burst=burst),))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        rule_set_builder.build([policy_snapshot_factory(id=old_snapshot.id)])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started < (size - burst) / rate

    async def test_build_keeps_speed_limit_rate_when_build_fails(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        speed_limit_snapshot_factory: Callable[..., SpeedLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
        open_connection: Callable[[RuleSet], Awaitable[Grant]],
    ) -> None:
        # Arrange
        burst = faker.pyint(min_value=1_000, max_value=10_000)
        # Every burst after the first takes 50 ms. The failed edit would make it 1 ms.
        rate = burst * 20
        size = burst * faker.pyint(min_value=2, max_value=3)
        limit = speed_limit_snapshot_factory(rate=rate, burst=burst)
        old_snapshot = policy_snapshot_factory(speed_limits=(limit,))
        grant = await open_connection(rule_set_builder.build([old_snapshot]))
        edited = policy_snapshot_factory(id=old_snapshot.id, speed_limits=(replace(limit, rate=burst * 1_000),))
        invalid = policy_snapshot_factory(condition={"kind": f"unknown-{faker.word()}"})
        with pytest.raises(InvalidPolicyError):
            rule_set_builder.build([edited, invalid])
        loop = asyncio.get_running_loop()
        started = loop.time()

        # Act
        await grant.on_received(size)

        # Assert
        assert loop.time() - started >= (size - burst) / rate

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
        builder = RuleSetBuilder(
            recording_period_usage,
            counters=MemoryConnectionCounters(),
            buckets=MemorySpeedBuckets(),
        )
        rule_set_policy = RuleSetPolicy(builder.build([policy]))

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
        builder = RuleSetBuilder(
            recording_period_usage,
            counters=MemoryConnectionCounters(),
            buckets=MemorySpeedBuckets(),
        )
        rule_set_policy = RuleSetPolicy(builder.build([policy]))

        # Act
        await rule_set_policy.admit(proxy_request, session)

        # Assert
        assert recording_period_usage.asked_since == [assigned_on]

    def test_build_raises_invalid_policy_error_when_scope_has_no_scope_object(
        self,
        recording_period_usage: RecordingPeriodUsage,
        connection_limit_snapshot_factory: Callable[..., ConnectionLimitSnapshot],
        policy_snapshot_factory: Callable[..., PolicySnapshot],
    ) -> None:
        # Arrange
        # E.g. a scope added to the database before the proxy learned it.
        builder = RuleSetBuilder(
            recording_period_usage,
            counters=MemoryConnectionCounters(),
            buckets=MemorySpeedBuckets(),
            scopes={},
        )
        policy = policy_snapshot_factory(connection_limits=(connection_limit_snapshot_factory(),))

        # Act
        with pytest.raises(InvalidPolicyError) as error:
            builder.build([policy])

        # Assert
        assert isinstance(error.value.__cause__, UnknownScopeError)

    def test_build_raises_invalid_policy_error_when_quota_scope_not_identity(
        self,
        faker: Faker,
        rule_set_builder: RuleSetBuilder,
        total_traffic_quota_snapshot: TrafficQuotaSnapshot,
        policy_snapshot_factory: Callable[..., PolicySnapshot],
    ) -> None:
        # Arrange
        # Usage is counted per identity only: another scope would be counted wrong, not refused.
        scope = faker.random_element([scope for scope in LimitScope if scope != LimitScope.IDENTITY])
        quota = replace(total_traffic_quota_snapshot, scope=scope)
        policy = policy_snapshot_factory(traffic_quotas=(quota,))

        # Act
        with pytest.raises(InvalidPolicyError) as error:
            rule_set_builder.build([policy])

        # Assert
        assert isinstance(error.value.__cause__, UnsupportedQuotaScopeError)
