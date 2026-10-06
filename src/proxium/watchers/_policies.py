from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from proxium.db import PolicyModel, PolicyRuleModel, session_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from datetime import date

    from sqlalchemy import Result, Select

    from proxium.db import (
        Direction,
        LimitScope,
        PolicyConnectionLimitModel,
        PolicySpeedLimitModel,
        PolicyTrafficQuotaModel,
        QuotaPeriod,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConnectionLimitSnapshot:
    id: int
    scope: LimitScope
    max_connections: int


@dataclass(frozen=True, slots=True)
class SpeedLimitSnapshot:
    id: int
    scope: LimitScope
    direction: Direction
    rate: int
    burst: int


@dataclass(frozen=True, slots=True)
class TrafficQuotaSnapshot:
    id: int
    scope: LimitScope
    direction: Direction
    max_bytes: int
    period: QuotaPeriod
    period_length: int


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    id: int
    condition: Mapping[str, Any]
    connection_limits: tuple[ConnectionLimitSnapshot, ...]
    speed_limits: tuple[SpeedLimitSnapshot, ...]
    traffic_quotas: tuple[TrafficQuotaSnapshot, ...]


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """An active policy at one moment, detached from the database. Equal snapshots mean nothing changed."""

    id: int
    is_global: bool
    # Quota periods of a global policy count from it, of an assigned one from the assignment's day.
    global_starts_on: date
    # In order: the first that matches applies.
    rules: tuple[RuleSnapshot, ...]


def _by_id(limit: PolicyConnectionLimitModel | PolicySpeedLimitModel | PolicyTrafficQuotaModel, /) -> int:
    return limit.id


type PoliciesCallback = Callable[[tuple[PolicySnapshot, ...]], Awaitable[None]]


class PoliciesNotLoadedError(Exception):
    """`start` was called before `load`: there are no applied policies to compare changes with."""


class PolicyWatcher:
    """Looks up active policies every `interval` seconds and calls `on_change` when they differ from the last applied.

    All of them are read every time, `chunk_size` policies per query: a change anywhere in a policy, its rules or
    limits shows up without the API marking it. Call `load` before serving: the proxy must not start without its
    limits, so it raises if the policies can't be applied. Then `start` in the running loop, and `close` before
    the server shuts down. A failed lookup or `on_change` is logged and the old policies stay, the next lookup retries.
    """

    def __init__(
        self,
        on_change: PoliciesCallback,
        /,
        *,
        interval: float = 5.0,
        chunk_size: int = 500,
    ) -> None:
        self._on_change: PoliciesCallback = on_change
        self._interval: float = interval
        self._chunk_size: int = chunk_size
        self._current: tuple[PolicySnapshot, ...] | None = None
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def load(self) -> None:
        """Read and apply the current policies by `on_change`, raising if either fails."""
        snapshot = await self._read()
        await self._on_change(snapshot)
        self._current = snapshot

    def start(self) -> None:
        if self._current is None:
            raise PoliciesNotLoadedError()

        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop looking up. A change being applied finishes, never cut halfway."""
        self._closing.set()
        if self._task is not None:
            await self._task

    def _get_policies_statement(self, after_id: int, /) -> Select[tuple[PolicyModel]]:
        rules = selectinload(PolicyModel.rules)
        return (
            select(PolicyModel)
            .where(
                PolicyModel.is_active.is_(True),
                PolicyModel.id > after_id,
            )
            .order_by(PolicyModel.id)
            .limit(self._chunk_size)
            .options(
                rules.selectinload(PolicyRuleModel.connection_limits),
                rules.selectinload(PolicyRuleModel.speed_limits),
                rules.selectinload(PolicyRuleModel.traffic_quotas),
            )
        )

    def _snapshot_connection_limit(self, limit: PolicyConnectionLimitModel, /) -> ConnectionLimitSnapshot:
        return ConnectionLimitSnapshot(
            id=limit.id,
            scope=limit.scope,
            max_connections=limit.max_connections,
        )

    def _snapshot_speed_limit(self, limit: PolicySpeedLimitModel, /) -> SpeedLimitSnapshot:
        return SpeedLimitSnapshot(
            id=limit.id,
            scope=limit.scope,
            direction=limit.direction,
            rate=limit.rate,
            burst=limit.burst,
        )

    def _snapshot_traffic_quota(self, quota: PolicyTrafficQuotaModel, /) -> TrafficQuotaSnapshot:
        return TrafficQuotaSnapshot(
            id=quota.id,
            scope=quota.scope,
            direction=quota.direction,
            max_bytes=quota.max_bytes,
            period=quota.period,
            period_length=quota.period_length,
        )

    def _snapshot_rule(self, rule: PolicyRuleModel, /) -> RuleSnapshot:
        # Sorted by id: the database returns limits in no particular order, equal rules must compare equal.
        return RuleSnapshot(
            id=rule.id,
            condition=rule.condition,
            connection_limits=tuple(
                self._snapshot_connection_limit(limit) for limit in sorted(rule.connection_limits, key=_by_id)
            ),
            speed_limits=tuple(self._snapshot_speed_limit(limit) for limit in sorted(rule.speed_limits, key=_by_id)),
            traffic_quotas=tuple(
                self._snapshot_traffic_quota(quota) for quota in sorted(rule.traffic_quotas, key=_by_id)
            ),
        )

    def _snapshot_policy(self, policy: PolicyModel, /) -> PolicySnapshot:
        return PolicySnapshot(
            id=policy.id,
            is_global=policy.is_global,
            global_starts_on=policy.global_starts_on,
            rules=tuple(self._snapshot_rule(rule) for rule in policy.rules),
        )

    async def _read_chunk(self, after_id: int, /) -> list[PolicySnapshot]:
        async with session_manager.session() as session:
            result: Result[tuple[PolicyModel]] = await session.execute(self._get_policies_statement(after_id))
            # Within the session: the rules and limits are loaded into it.
            return [self._snapshot_policy(policy) for policy in result.scalars()]

    async def _read(self) -> tuple[PolicySnapshot, ...]:
        policies: list[PolicySnapshot] = []
        chunk = await self._read_chunk(0)
        policies.extend(chunk)
        # A short chunk is the last one.
        while len(chunk) == self._chunk_size:
            chunk = await self._read_chunk(chunk[-1].id)
            policies.extend(chunk)
        return tuple(policies)

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._interval)
            if not self._closing.is_set():
                await self._check()

    async def _check(self) -> None:
        try:
            snapshot = await self._read()
        except Exception:
            logger.exception("Can't look up policies, keeping the current ones")
            return

        if snapshot == self._current:
            return

        try:
            await self._on_change(snapshot)
        except Exception:
            logger.exception("Can't apply policies, retrying on the next lookup")
            return

        self._current = snapshot
        logger.info("Policies applied to new connections")
