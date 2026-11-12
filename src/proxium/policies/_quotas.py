from __future__ import annotations

import calendar
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from proxium.db import QuotaPeriod
from proxium.proxy import Meter

from ._claims import POLICIES_CLAIM

if TYPE_CHECKING:
    from collections.abc import Mapping

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


class EndlessPeriodError(Exception):
    """The period never resets: there is no next one."""


class Period(ABC):
    """How quota periods of `length` units follow one another from `anchor`, by UTC days.

    The grid goes both ways: with `anchor` in the future, today is in a period before it.
    """

    @staticmethod
    def _check_length(length: int, /) -> None:
        if length < 1:
            raise ValueError("A period is at least one unit long.")

    @abstractmethod
    def _get_start(self, anchor: date, today: date, length: int, /) -> date:
        pass

    @abstractmethod
    def _get_next_start(self, anchor: date, today: date, length: int, /) -> date:
        pass

    def start(self, anchor: date, today: date, /, *, length: int = 1) -> date:
        """The first day of the period `today` is in."""
        self._check_length(length)
        return self._get_start(anchor, today, length)

    def next_start(self, anchor: date, today: date, /, *, length: int = 1) -> date:
        """The first day of the period after the one `today` is in: the day the usage resets. Raise
        `EndlessPeriodError` if it never does.
        """
        self._check_length(length)
        return self._get_next_start(anchor, today, length)


class DayPeriod(Period):
    """Units of `days` days, e.g. 7 for weeks."""

    def __init__(self, *, days: int = 1) -> None:
        self._days: int = days

    def _get_start(self, anchor: date, today: date, length: int, /) -> date:
        step = self._days * length
        return anchor + timedelta(days=(today - anchor).days // step * step)

    def _get_next_start(self, anchor: date, today: date, length: int, /) -> date:
        return self._get_start(anchor, today, length) + timedelta(days=self._days * length)


class MonthPeriod(Period):
    """Units of `months` months, e.g. 12 for years. Counted from `anchor`, not from a period's start: with Jan 31,
    periods start on Feb 28, then Mar 31.
    """

    def __init__(self, *, months: int = 1) -> None:
        self._months: int = months

    def _get_index(self, anchor: date, today: date, length: int, /) -> int:
        """Of the period `today` is in, from 0 for the one starting on `anchor`."""
        return _months_since(anchor, today) // (self._months * length)

    def _get_start(self, anchor: date, today: date, length: int, /) -> date:
        return _add_months(anchor, self._get_index(anchor, today, length) * self._months * length)

    def _get_next_start(self, anchor: date, today: date, length: int, /) -> date:
        return _add_months(anchor, (self._get_index(anchor, today, length) + 1) * self._months * length)


class TotalPeriod(Period):
    """Never resets: one allowance since `anchor`, nothing is counted before. `length` is ignored."""

    def _get_start(self, anchor: date, today: date, length: int, /) -> date:
        return anchor

    def _get_next_start(self, anchor: date, today: date, length: int, /) -> date:
        raise EndlessPeriodError()


# Every period, as the admin describes it.
DEFAULT_PERIODS: Final[Mapping[QuotaPeriod, Period]] = MappingProxyType(
    {
        QuotaPeriod.DAY: DayPeriod(),
        QuotaPeriod.MONTH: MonthPeriod(),
        QuotaPeriod.TOTAL: TotalPeriod(),
    },
)


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
    """Usage in the current period: `length` units of `period` from the client's `anchor`, by UTC days."""

    def __init__(
        self,
        usage: PeriodUsage,
        anchor: Anchor,
        /,
        *,
        period: Period,
        length: int = 1,
    ) -> None:
        self._usage: PeriodUsage = usage
        self._anchor: Anchor = anchor
        self._period: Period = period
        self._length: int = length

    async def measure(self, request: Request, session: Session, /) -> Usage:
        since = self._period.start(
            self._anchor.starts_on(request),
            datetime.now(UTC).date(),
            length=self._length,
        )
        return await self._usage.used_since(request.identity, since)
