from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from proxium.proxy import Usage

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from proxium.db import BaseTrafficModel

# Whose traffic: the table and the owner's id in it.
type Owner = tuple[type[BaseTrafficModel], int]


@dataclass(slots=True)
class Bytes:
    """Bytes counted so far, added to as more come."""

    sent: int = 0
    received: int = 0

    def add(self, other: Bytes, /) -> None:
        self.sent += other.sent
        self.received += other.received


# Counted bytes per owner and UTC day.
type Days = defaultdict[Owner, defaultdict[date, Bytes]]


def create_days() -> Days:
    return defaultdict(lambda: defaultdict(Bytes))


def merge_days(target: Days, source: Mapping[Owner, Mapping[date, Bytes]], /) -> None:
    for owner, days in source.items():
        for day, counted in days.items():
            target[owner][day].add(counted)


def merge_usages(target: Days, source: Mapping[Owner, Mapping[date, Usage]], /) -> None:
    for owner, days in source.items():
        for day, usage in days.items():
            target[owner][day].add(Bytes(sent=usage.sent, received=usage.received))


def to_usages(source: Mapping[Owner, Mapping[date, Bytes]], /) -> dict[Owner, dict[date, Usage]]:
    """Frozen copies of the days with bytes: what's handed over can't change under the receiver."""
    usages: dict[Owner, dict[date, Usage]] = {}
    for owner, days in source.items():
        owner_usages = {
            day: Usage(sent=counted.sent, received=counted.received)
            for day, counted in days.items()
            if counted.sent or counted.received
        }
        if owner_usages:
            usages[owner] = owner_usages
    return usages
