from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from proxium.proxy import EMPTY_GRANT, Grant, Policy

from ._claims import POLICIES_CLAIM

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from proxium.proxy import Request, Session

    from ._conditions import Condition


@dataclass(frozen=True, slots=True)
class Rule:
    """When `condition` matches, every one of `limits` applies."""

    condition: Condition
    limits: tuple[Policy, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    """The rules of every active policy by its id, in order, and the ids of the global ones."""

    policies: Mapping[int, tuple[Rule, ...]] = field(default_factory=dict)
    global_ids: tuple[int, ...] = ()


EMPTY_RULE_SET: Final[RuleSet] = RuleSet()


class _Grants(Grant):
    """The grants of all limits that apply to one connection, as one."""

    def __init__(self, grants: Sequence[Grant], releases: contextlib.AsyncExitStack, /) -> None:
        self._grants: tuple[Grant, ...] = tuple(grants)
        self._releases: contextlib.AsyncExitStack = releases

    async def on_sent(self, n: int, /) -> None:
        for grant in self._grants:
            await grant.on_sent(n)

    async def on_received(self, n: int, /) -> None:
        for grant in self._grants:
            await grant.on_received(n)

    async def release(self) -> None:
        await self._releases.aclose()


class RuleSetPolicy(Policy):
    """Applies the client's policies: the global ones and those in its identity claims, all at once.

    In each policy the first rule whose condition matches applies its limits. A policy missing from the rule set,
    e.g. turned off, is skipped. `update` swaps the rules for new connections, open ones keep their grants.
    """

    def __init__(
        self,
        rule_set: RuleSet = EMPTY_RULE_SET,
        /,
    ) -> None:
        self._rule_set: RuleSet = rule_set

    def update(self, rule_set: RuleSet, /) -> None:
        self._rule_set = rule_set

    def _get_policy_ids(self, request: Request, rule_set: RuleSet, /) -> list[int]:
        # An identity without assigned policies has no claim, e.g. anonymous: only global ones apply.
        # The claim maps ids to start days, iterating it gives the ids.
        assigned = request.identity.claims.get(POLICIES_CLAIM, {})
        # Once each: a global policy may be assigned as well.
        return list(dict.fromkeys([*rule_set.global_ids, *assigned]))

    def _get_limits(self, request: Request, session: Session, /) -> list[Policy]:
        # Read once: an update meanwhile must not mix two rule sets in one connection.
        rule_set = self._rule_set
        limits: list[Policy] = []
        for policy_id in self._get_policy_ids(request, rule_set):
            rules = rule_set.policies.get(policy_id, ())
            rule = next((rule for rule in rules if rule.condition.matches(request, session)), None)
            if rule is not None:
                limits.extend(rule.limits)
        return limits

    async def admit(self, request: Request, session: Session, /) -> Grant:
        limits = self._get_limits(request, session)
        if not limits:
            return EMPTY_GRANT

        grants: list[Grant] = []
        # A limit refusing releases those that admitted before it.
        async with contextlib.AsyncExitStack() as stack:
            for limit in limits:
                grant = await limit.admit(request, session)
                stack.push_async_callback(grant.release)
                grants.append(grant)
            releases = stack.pop_all()

        return _Grants(grants, releases)
