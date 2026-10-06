from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from proxium.db import Direction, LimitScope
from proxium.proxy import (
    ClientIPScope,
    ConnectionLimitPolicy,
    ConnectionScope,
    GlobalScope,
    IdentityScope,
    QuotaPolicy,
    SpeedLimitPolicy,
    TargetHostScope,
)
from proxium.proxy import Direction as ProxyDirection

from ._conditions import DEFAULT_CONDITION_PARSER
from ._quotas import Anchor, AssignmentAnchor, FixedAnchor, PeriodMeter
from ._rule_sets import Rule, RuleSet

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Hashable, Mapping, Sequence

    from proxium.proxy import Policy, Scope
    from proxium.watchers import (
        ConnectionLimitSnapshot,
        PolicySnapshot,
        RuleSnapshot,
        SpeedLimitSnapshot,
        TrafficQuotaSnapshot,
    )

    from ._conditions import ConditionParser
    from ._quotas import PeriodUsage


class UnknownScopeError(Exception):
    """A limit has a scope the builder has no `Scope` for."""


class UnsupportedQuotaScopeError(Exception):
    """A quota has a scope other than the identity: usage is counted per account and trusted network only."""


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


class RuleSetBuilder:
    """Turns policies read from the database into a rule set for `RuleSetPolicy`.

    Limits keep their state across builds: an unchanged speed limit is reused with its buckets, a connection limit
    keeps counting the connections open under its previous value. Build anew on every change, from the same builder.
    Quotas keep no state: `usage` counts the traffic, they measure it.
    """

    def __init__(
        self,
        usage: PeriodUsage,
        /,
        *,
        conditions: ConditionParser = DEFAULT_CONDITION_PARSER,
        scopes: Mapping[LimitScope, Scope] = DEFAULT_SCOPES,
    ) -> None:
        self._usage: PeriodUsage = usage
        self._conditions: ConditionParser = conditions
        self._scopes: dict[LimitScope, Scope] = dict(scopes)
        # Open connections per limit and scope: a new scope counts other keys, so it starts anew.
        self._connection_counts: dict[tuple[int, LimitScope], Counter[Hashable]] = {}
        # Equal snapshots, equal limits: any change gets fresh buckets, open connections keep the old ones.
        self._speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy] = {}

    def _get_scope(self, scope: LimitScope, /) -> Scope:
        try:
            return self._scopes[scope]
        except KeyError as err:
            raise UnknownScopeError(f"No scope for {scope}.") from err

    def _build_connection_limit(
        self,
        limit: ConnectionLimitSnapshot,
        counts: dict[tuple[int, LimitScope], Counter[Hashable]],
        /,
    ) -> ConnectionLimitPolicy:
        key = (limit.id, limit.scope)
        policy = ConnectionLimitPolicy(
            self._get_scope(limit.scope),
            limit=limit.max_connections,
            counts=self._connection_counts.get(key),
        )
        counts[key] = policy.counts
        return policy

    def _build_speed_limit(
        self,
        limit: SpeedLimitSnapshot,
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy],
        /,
    ) -> SpeedLimitPolicy:
        try:
            policy = self._speed_limits[limit]
        except KeyError:
            policy = SpeedLimitPolicy(
                self._get_scope(limit.scope),
                rate=limit.rate,
                burst=limit.burst,
                direction=DIRECTIONS[limit.direction],
            )
        speed_limits[limit] = policy
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
                period=quota.period,
                length=quota.period_length,
            ),
            limit=quota.max_bytes,
            direction=DIRECTIONS[quota.direction],
        )

    def _build_rule(
        self,
        rule: RuleSnapshot,
        anchor: Anchor,
        counts: dict[tuple[int, LimitScope], Counter[Hashable]],
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy],
        /,
    ) -> Rule:
        limits: list[Policy] = [
            *(self._build_connection_limit(limit, counts) for limit in rule.connection_limits),
            *(self._build_speed_limit(limit, speed_limits) for limit in rule.speed_limits),
            *(self._build_traffic_quota(quota, anchor) for quota in rule.traffic_quotas),
        ]
        return Rule(
            condition=self._conditions.parse(rule.condition),
            limits=tuple(limits),
        )

    def build(self, policies: Sequence[PolicySnapshot], /) -> RuleSet:
        """The rule set of `policies`. Raises, keeping the state of the last build, if one can't be built."""
        counts: dict[tuple[int, LimitScope], Counter[Hashable]] = {}
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy] = {}
        rule_set = RuleSet(
            policies={
                policy.id: tuple(
                    self._build_rule(rule, self._get_anchor(policy), counts, speed_limits) for rule in policy.rules
                )
                for policy in policies
            },
            global_ids=tuple(policy.id for policy in policies if policy.is_global),
        )

        # Only what this build uses: limits removed since are dropped, their open connections keep their grants.
        self._connection_counts = counts
        self._speed_limits = speed_limits
        return rule_set
