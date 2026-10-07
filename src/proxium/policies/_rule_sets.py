from __future__ import annotations

import asyncio
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


@dataclass(slots=True)
class _Choice:
    """The rule one policy applies to a connection now, none if no rule matches, and the grants of its limits."""

    rules: tuple[Rule, ...]
    rule: Rule | None
    grants: tuple[Grant, ...]
    releases: contextlib.AsyncExitStack


def _choose_rule(rules: Sequence[Rule], request: Request, session: Session, /) -> Rule | None:
    return next((rule for rule in rules if rule.condition.matches(request, session)), None)


async def _admit_rule(
    rule: Rule | None,
    request: Request,
    session: Session,
    /,
) -> tuple[tuple[Grant, ...], contextlib.AsyncExitStack]:
    """The grants of every limit of `rule` and how to release them. A limit refusing releases those before it."""
    limits = rule.limits if rule is not None else ()
    grants: list[Grant] = []
    async with contextlib.AsyncExitStack() as stack:
        for limit in limits:
            grant = await limit.admit(request, session)
            stack.push_async_callback(grant.release)
            grants.append(grant)
        releases = stack.pop_all()
    return tuple(grants), releases


class _RuleSetGrant(Grant):
    """The grants of all policies that apply to one connection, as one.

    Chooses the rules again on the bytes of the tunnel, at most every `interval` seconds, e.g. a schedule turned
    to the night. A policy whose rule changed releases the old limits, then takes the new ones: taken first, a limit
    of open connections would count this one twice. If the new ones refuse, the tunnel is cut.
    Rules come from the rule set the connection started with: edits of policies reach new connections only.
    """

    def __init__(
        self,
        choices: Sequence[_Choice],
        request: Request,
        session: Session,
        /,
        *,
        interval: float,
    ) -> None:
        self._choices: tuple[_Choice, ...] = tuple(choices)
        self._request: Request = request
        self._session: Session = session
        self._interval: float = interval
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._checked_at: float = self._loop.time()
        # Both directions recheck: one at a time, the other goes on with the grants it finds.
        self._rechecking: bool = False

    async def _switch(self, choice: _Choice, rule: Rule | None, /) -> None:
        # Emptied before releasing: released once, even if the new limits refuse or the tunnel closes meanwhile.
        releases = choice.releases
        choice.grants = ()
        choice.releases = contextlib.AsyncExitStack()
        await releases.aclose()

        choice.grants, choice.releases = await _admit_rule(rule, self._request, self._session)
        choice.rule = rule

    async def _recheck(self) -> None:
        now = self._loop.time()
        if self._rechecking or now - self._checked_at < self._interval:
            return

        self._checked_at = now
        self._rechecking = True
        try:
            for choice in self._choices:
                rule = _choose_rule(choice.rules, self._request, self._session)
                if rule is not choice.rule:
                    await self._switch(choice, rule)
        finally:
            self._rechecking = False

    async def on_sent(self, n: int, /) -> None:
        await self._recheck()
        for choice in self._choices:
            for grant in choice.grants:
                await grant.on_sent(n)

    async def on_received(self, n: int, /) -> None:
        await self._recheck()
        for choice in self._choices:
            for grant in choice.grants:
                await grant.on_received(n)

    async def release(self) -> None:
        async with contextlib.AsyncExitStack() as stack:
            for choice in self._choices:
                stack.push_async_callback(choice.releases.aclose)


class RuleSetPolicy(Policy):
    """Applies the client's policies: the global ones and those in its identity claims, all at once.

    In each policy the first rule whose condition matches applies its limits. Open tunnels choose again every
    `check_interval` seconds, see `_RuleSetGrant`. A policy missing from the rule set, e.g. turned off, is skipped.
    `update` swaps the rules for new connections, open ones keep the rules they started with.
    """

    def __init__(
        self,
        rule_set: RuleSet = EMPTY_RULE_SET,
        /,
        *,
        check_interval: float = 1.0,
    ) -> None:
        self._rule_set: RuleSet = rule_set
        self._check_interval: float = check_interval

    def update(self, rule_set: RuleSet, /) -> None:
        self._rule_set = rule_set

    def _get_policy_ids(self, request: Request, rule_set: RuleSet, /) -> list[int]:
        # An identity without assigned policies has no claim, e.g. anonymous: only global ones apply.
        # The claim maps ids to start days, iterating it gives the ids.
        assigned = request.identity.claims.get(POLICIES_CLAIM, {})
        # Once each: a global policy may be assigned as well.
        return list(dict.fromkeys([*rule_set.global_ids, *assigned]))

    def _get_rules(self, request: Request, /) -> list[tuple[Rule, ...]]:
        # Read once: an update meanwhile must not mix two rule sets in one connection.
        rule_set = self._rule_set
        policies: list[tuple[Rule, ...]] = []
        for policy_id in self._get_policy_ids(request, rule_set):
            rules = rule_set.policies.get(policy_id, ())
            if rules:
                policies.append(rules)
        return policies

    async def admit(self, request: Request, session: Session, /) -> Grant:
        policies = self._get_rules(request)
        if not policies:
            return EMPTY_GRANT

        choices: list[_Choice] = []
        # A policy refusing releases those that admitted before it.
        async with contextlib.AsyncExitStack() as stack:
            for rules in policies:
                rule = _choose_rule(rules, request, session)
                grants, releases = await _admit_rule(rule, request, session)
                stack.push_async_callback(releases.aclose)
                choices.append(_Choice(rules=rules, rule=rule, grants=grants, releases=releases))
            stack.pop_all()

        return _RuleSetGrant(choices, request, session, interval=self._check_interval)
