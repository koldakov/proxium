from __future__ import annotations

import calendar
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from proxium.db import QuotaPeriod
from proxium.proxy import Meter

from ._claims import POLICIES_CLAIM

if TYPE_CHECKING:
    from proxium.proxy import Identity, Request, Session, Usage


class UnassignedPolicyError(Exception):
    """The identity has no start day for the policy: it isn't assigned to it."""


def _add_months(day: date, months: int, /) -> date:
    """The same day `months` later, or the month's last one if it's shorter, e.g. Jan 31 + 1 month is Feb 28."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _months_since(anchor: date, today: date, /) -> int:
    """Whole months from `anchor` to `today`, negative if `anchor` is later."""
    months = (today.year - anchor.year) * 12 + today.month - anchor.month
    if _add_months(anchor, months) > today:
        months -= 1
    return months


def period_start(anchor: date, today: date, period: QuotaPeriod, /, *, length: int = 1) -> date:
    """The first day of the period `today` is in: periods of `length` days or months follow one another from `anchor`.

    The grid goes both ways: with `anchor` in the future, today is in a period before it. A `TOTAL` period never
    resets: it starts on `anchor`, nothing is counted before.
    """
    if length < 1:
        raise ValueError("A period is at least one day or month long.")

    match period:
        case QuotaPeriod.DAY:
            return anchor + timedelta(days=(today - anchor).days // length * length)
        case QuotaPeriod.MONTH:
            return _add_months(anchor, _months_since(anchor, today) // length * length)
        case QuotaPeriod.TOTAL:
            return anchor


class Anchor(ABC):
    """The day quota periods of a policy count from, for one client."""

    @abstractmethod
    def starts_on(self, request: Request, /) -> date:
        pass


class FixedAnchor(Anchor):
    """One day for every client, e.g. of a global policy."""

    def __init__(self, day: date, /) -> None:
        self._day: date = day

    def starts_on(self, request: Request, /) -> date:
        return self._day


class AssignmentAnchor(Anchor):
    """The day the policy is assigned from to the client's account or network, from its identity claims."""

    def __init__(self, policy_id: int, /) -> None:
        self._policy_id: int = policy_id

    def starts_on(self, request: Request, /) -> date:
        try:
            return request.identity.claims[POLICIES_CLAIM][self._policy_id]
        except KeyError as err:
            raise UnassignedPolicyError(
                f"Policy {self._policy_id} isn't assigned to {request.identity.subject}.",
            ) from err


class PeriodUsage(ABC):
    """What an identity used since a day, e.g. from daily traffic sums."""

    @abstractmethod
    async def used_since(self, identity: Identity, since: date, /) -> Usage:
        """Include open connections. Raise `Unmetered` if the identity isn't counted, e.g. anonymous,
        `UsageUnavailable` if the usage can't be read now.
        """


class PeriodMeter(Meter):
    """Usage in the current period: `length` days or months from the client's `anchor`, by UTC days."""

    def __init__(
        self,
        usage: PeriodUsage,
        anchor: Anchor,
        /,
        *,
        period: QuotaPeriod,
        length: int = 1,
    ) -> None:
        self._usage: PeriodUsage = usage
        self._anchor: Anchor = anchor
        self._period: QuotaPeriod = period
        self._length: int = length

    async def measure(self, request: Request, session: Session, /) -> Usage:
        since = period_start(
            self._anchor.starts_on(request),
            datetime.now(UTC).date(),
            self._period,
            length=self._length,
        )
        return await self._usage.used_since(request.identity, since)
