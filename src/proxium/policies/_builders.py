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
    MemoryConnectionCounter,
    QuotaPolicy,
    SpeedLimitPolicy,
    TargetHostScope,
)
from proxium.proxy import Direction as ProxyDirection

from ._conditions import DEFAULT_CONDITION_PARSER, InvalidConditionError
from ._quotas import Anchor, AssignmentAnchor, FixedAnchor, PeriodMeter
from ._rule_sets import Rule, RuleSet

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from proxium.proxy import ConnectionCounter, Policy, Scope
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


class RuleSetBuilder:
    """Turns policies read from the database into a rule set for `RuleSetPolicy`.

    Speed limits keep their state across builds: an unchanged one is reused with its buckets. Build anew on every
    change, from the same builder. Connection limits are counted by `counters`, by the limit's name: under the same
    name an edited limit keeps counting the connections open under it. Except the connection scope: one connection
    has nothing to share, it's counted in memory. Quotas keep no state: `usage` counts the traffic, they measure it.
    """

    def __init__(
        self,
        usage: PeriodUsage,
        /,
        *,
        counters: Callable[[str], ConnectionCounter],
        conditions: ConditionParser = DEFAULT_CONDITION_PARSER,
        scopes: Mapping[LimitScope, Scope] = DEFAULT_SCOPES,
    ) -> None:
        self._usage: PeriodUsage = usage
        self._counters: Callable[[str], ConnectionCounter] = counters
        self._conditions: ConditionParser = conditions
        self._scopes: dict[LimitScope, Scope] = dict(scopes)
        # Equal snapshots, equal limits: any change gets fresh buckets, open connections keep the old ones.
        self._speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy] = {}

    def _get_scope(self, scope: LimitScope, /) -> Scope:
        try:
            return self._scopes[scope]
        except KeyError as err:
            raise UnknownScopeError(f"No scope for {scope}.") from err

    def _create_counter(self, limit: ConnectionLimitSnapshot, /) -> ConnectionCounter:
        if limit.scope == LimitScope.CONNECTION:
            return MemoryConnectionCounter()
        # With the scope: a new scope counts other keys, so it starts anew.
        return self._counters(f"{limit.id}:{limit.scope}")

    def _build_connection_limit(self, limit: ConnectionLimitSnapshot, /) -> ConnectionLimitPolicy:
        return ConnectionLimitPolicy(
            self._get_scope(limit.scope),
            limit=limit.max_connections,
            counter=self._create_counter(limit),
        )

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
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy],
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
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy],
        /,
    ) -> tuple[Rule, ...]:
        anchor = self._get_anchor(policy)
        rules: list[Rule] = []
        for rule in policy.rules:
            try:
                rules.append(self._build_rule(rule, anchor, speed_limits))
            except (InvalidConditionError, UnknownScopeError, UnsupportedQuotaScopeError) as err:
                raise InvalidPolicyError(f"Policy {policy.id}, rule {rule.id}: {err}") from err
        return tuple(rules)

    def build(self, policies: Sequence[PolicySnapshot], /) -> RuleSet:
        """The rule set of `policies`. Raises `InvalidPolicyError`, keeping the state of the last build, if one
        can't be built: none of the changes apply until it's fixed.
        """
        speed_limits: dict[SpeedLimitSnapshot, SpeedLimitPolicy] = {}
        rule_set = RuleSet(
            policies={policy.id: self._build_policy(policy, speed_limits) for policy in policies},
            global_ids=tuple(policy.id for policy in policies if policy.is_global),
        )

        # Only what this build uses: limits removed since are dropped, their open connections keep their grants.
        self._speed_limits = speed_limits
        return rule_set
