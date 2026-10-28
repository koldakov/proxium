from __future__ import annotations

import weakref
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from proxium.db import Direction, LimitScope
from proxium.proxy import (
    ClientIPScope,
    ConnectionLimitPolicy,
    ConnectionScope,
    GlobalScope,
    IdentityScope,
    MemoryConnectionCounter,
    MemorySpeedBucket,
    QuotaPolicy,
    SpeedLimitPolicy,
    TargetHostScope,
)
from proxium.proxy import Direction as ProxyDirection

from ._conditions import DEFAULT_CONDITION_PARSER, InvalidConditionError
from ._quotas import DEFAULT_PERIODS, Anchor, AssignmentAnchor, FixedAnchor, PeriodMeter
from ._rule_sets import Rule, RuleSet

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from proxium.db import QuotaPeriod
    from proxium.proxy import ConnectionCounter, Policy, Scope, SpeedBucket
    from proxium.watchers import (
        ConnectionLimitSnapshot,
        PolicySnapshot,
        RuleSnapshot,
        SpeedLimitSnapshot,
        TrafficQuotaSnapshot,
    )

    from ._conditions import ConditionParser
    from ._quotas import Period, PeriodUsage


class UnknownScopeError(Exception):
    """A limit has a scope the builder has no `Scope` for."""


class UnknownPeriodError(Exception):
    """A quota has a period the builder has no `Period` for."""


class UnsupportedQuotaScopeError(Exception):
    """A quota has a scope other than the identity: usage is counted per account and trusted network only."""


class InvalidSpeedLimitError(Exception):
    """A speed limit's rate or burst isn't positive."""


class InvalidPolicyError(Exception):
    """A policy can't be built, e.g. a rule's condition is of a kind this version doesn't know. Names the policy
    and the rule, the cause has the details.
    """


# Every scope, as the admin describes it.
DEFAULT_SCOPES: Final[Mapping[LimitScope, Scope]] = MappingProxyType(
    {
        LimitScope.CONNECTION: ConnectionScope(),
        LimitScope.IDENTITY: IdentityScope(),
        LimitScope.CLIENT_IP: ClientIPScope(),
        LimitScope.TARGET_HOST: TargetHostScope(),
        LimitScope.GLOBAL: GlobalScope(),
    },
)

DIRECTIONS: Final[Mapping[Direction, ProxyDirection]] = MappingProxyType(
    {
        Direction.SENT: ProxyDirection.SENT,
        Direction.RECEIVED: ProxyDirection.RECEIVED,
        Direction.BOTH: ProxyDirection.BOTH,
    },
)


# A speed limit's policy: an edited limit is the same one, one of another scope is new.
type _SpeedLimitKey = tuple[int, LimitScope]


def _get_limit_name(limit: ConnectionLimitSnapshot | SpeedLimitSnapshot, /) -> str:
    """What a limit's state is kept under. With the scope: a new scope counts other keys, so it starts anew."""
    return f"{limit.id}:{limit.scope}"


class RuleSetBuilder:
    """Turns policies read from the database into a rule set for `RuleSetPolicy`.

    Build anew on every change, from the same builder. Connection limits are counted by `counters`, speed limits by
    `buckets`, both by the limit's name: under the same name an edited limit keeps counting the connections open
    under it. Except the connection scope: one connection has nothing to share, it's counted in memory. An edited
    speed limit applies to open connections too, a removed one stops slowing them, and slows them again once back.
    One of a new scope applies to new connections only: open ones are counted by the old scope's keys, they keep the
    old limit. Quotas keep no state: `usage` counts the traffic, they measure it.
    """

    def __init__(  # noqa: PLR0913
        self,
        usage: PeriodUsage,
        /,
        *,
        counters: Callable[[str], ConnectionCounter],
        buckets: Callable[[str], SpeedBucket],
        conditions: ConditionParser = DEFAULT_CONDITION_PARSER,
        scopes: Mapping[LimitScope, Scope] = DEFAULT_SCOPES,
        periods: Mapping[QuotaPeriod, Period] = DEFAULT_PERIODS,
    ) -> None:
        self._usage: PeriodUsage = usage
        self._counters: Callable[[str], ConnectionCounter] = counters
        self._buckets: Callable[[str], SpeedBucket] = buckets
        self._conditions: ConditionParser = conditions
        self._scopes: dict[LimitScope, Scope] = dict(scopes)
        self._periods: dict[QuotaPeriod, Period] = dict(periods)
        # An edited limit is the same policy, its open connections get the change. Weakly: one lives as long as a rule
        # set holds it, the current one or one of an open connection, which may switch to its rule any time, e.g. at
        # night. Memory is bounded by them.
        self._speed_limits: weakref.WeakValueDictionary[_SpeedLimitKey, SpeedLimitPolicy] = (
            weakref.WeakValueDictionary()
        )

    def _get_scope(self, scope: LimitScope, /) -> Scope:
        try:
            return self._scopes[scope]
        except KeyError as err:
            raise UnknownScopeError(f"No scope for {scope}.") from err

    def _get_period(self, period: QuotaPeriod, /) -> Period:
        try:
            return self._periods[period]
        except KeyError as err:
            raise UnknownPeriodError(f"No period for {period}.") from err

    def _create_counter(self, limit: ConnectionLimitSnapshot, /) -> ConnectionCounter:
        if limit.scope == LimitScope.CONNECTION:
            return MemoryConnectionCounter()
        return self._counters(_get_limit_name(limit))

    def _build_connection_limit(self, limit: ConnectionLimitSnapshot, /) -> ConnectionLimitPolicy:
        return ConnectionLimitPolicy(
            self._get_scope(limit.scope),
            limit=limit.max_connections,
            counter=self._create_counter(limit),
        )

    def _create_bucket(self, limit: SpeedLimitSnapshot, /) -> SpeedBucket:
        if limit.scope == LimitScope.CONNECTION:
            return MemorySpeedBucket()
        return self._buckets(_get_limit_name(limit))

    def _build_speed_limit(
        self,
        limit: SpeedLimitSnapshot,
        speed_limits: dict[_SpeedLimitKey, tuple[SpeedLimitPolicy, SpeedLimitSnapshot]],
        /,
    ) -> SpeedLimitPolicy:
        # Checked while building: a policy kept from the last build is updated only once all of them pass.
        try:
            SpeedLimitPolicy.check_terms(rate=limit.rate, burst=limit.burst)
        except ValueError as err:
            raise InvalidSpeedLimitError(f"Speed limit {limit.id}: {err}") from err

        key = (limit.id, limit.scope)
        try:
            policy = self._speed_limits[key]
        except KeyError:
            policy = SpeedLimitPolicy(
                self._get_scope(limit.scope),
                rate=limit.rate,
                burst=limit.burst,
                direction=DIRECTIONS[limit.direction],
                bucket=self._create_bucket(limit),
            )
        # Updated once the whole build succeeds: a failed one changes nothing.
        speed_limits[key] = (policy, limit)
        return policy

    def _get_anchor(self, policy: PolicySnapshot, /) -> Anchor:
        # Global: one day for all. Assigned: each account or network has its own, e.g. the day it paid.
        if policy.is_global:
            return FixedAnchor(policy.global_starts_on)
        return AssignmentAnchor(policy.id)

    def _build_traffic_quota(self, quota: TrafficQuotaSnapshot, anchor: Anchor, /) -> QuotaPolicy:
        if quota.scope != LimitScope.IDENTITY:
            raise UnsupportedQuotaScopeError(f"Quotas are per identity, got {quota.scope}.")

        return QuotaPolicy(
            PeriodMeter(
                self._usage,
                anchor,
                period=self._get_period(quota.period),
                length=quota.period_length,
            ),
            limit=quota.max_bytes,
            direction=DIRECTIONS[quota.direction],
        )

    def _build_rule(
        self,
        rule: RuleSnapshot,
        anchor: Anchor,
        speed_limits: dict[_SpeedLimitKey, tuple[SpeedLimitPolicy, SpeedLimitSnapshot]],
        /,
    ) -> Rule:
        limits: list[Policy] = [
            *(self._build_connection_limit(limit) for limit in rule.connection_limits),
            *(self._build_speed_limit(limit, speed_limits) for limit in rule.speed_limits),
            *(self._build_traffic_quota(quota, anchor) for quota in rule.traffic_quotas),
        ]
        return Rule(
            condition=self._conditions.parse(rule.condition),
            limits=tuple(limits),
        )

    def _build_policy(
        self,
        policy: PolicySnapshot,
        speed_limits: dict[_SpeedLimitKey, tuple[SpeedLimitPolicy, SpeedLimitSnapshot]],
        /,
    ) -> tuple[Rule, ...]:
        anchor = self._get_anchor(policy)
        rules: list[Rule] = []
        for rule in policy.rules:
            try:
                rules.append(self._build_rule(rule, anchor, speed_limits))
            except (
                InvalidConditionError,
                UnknownScopeError,
                UnknownPeriodError,
                UnsupportedQuotaScopeError,
                InvalidSpeedLimitError,
            ) as err:
                raise InvalidPolicyError(f"Policy {policy.id}, rule {rule.id}: {err}") from err
        return tuple(rules)

    def build(self, policies: Sequence[PolicySnapshot], /) -> RuleSet:
        """The rule set of `policies`. Raises `InvalidPolicyError`, keeping the state of the last build, if one
        can't be built: none of the changes apply until it's fixed.
        """
        speed_limits: dict[_SpeedLimitKey, tuple[SpeedLimitPolicy, SpeedLimitSnapshot]] = {}
        rule_set = RuleSet(
            policies={policy.id: self._build_policy(policy, speed_limits) for policy in policies},
            global_ids=tuple(policy.id for policy in policies if policy.is_global),
        )

        for speed_limit, limit in speed_limits.values():
            speed_limit.update(rate=limit.rate, burst=limit.burst, direction=DIRECTIONS[limit.direction])

        kept_ids = {limit.id for _, limit in speed_limits.values()}
        # Copied: entries go away as rule sets are dropped.
        for key, speed_limit in list(self._speed_limits.items()):
            if key in speed_limits:
                continue
            limit_id, _ = key
            # Its scope changed: open connections are counted by the old scope's keys, they keep the old limit, not
            # updated. Restored if it was retired, e.g. its policy turned off and on again.
            if limit_id in kept_ids:
                speed_limit.restore()
                continue
            # Gone, e.g. removed or its policy turned off: stops slowing open connections. Back with this scope, it's
            # updated and slows them again.
            speed_limit.retire()

        for key, (speed_limit, _) in speed_limits.items():
            self._speed_limits[key] = speed_limit
        return rule_set
