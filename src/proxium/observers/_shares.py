from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from datetime import date

    from proxium.proxy import Usage


class TrafficShareUnavailable(Exception):
    """The share can't be reached, e.g. Redis is down."""


@dataclass(frozen=True, slots=True)
class SharedTraffic:
    """What other processes counted for an owner and haven't written yet, per UTC day, and which processes those are.

    `version` changes whenever a process announces it wrote bytes of the owner, None if none did lately. A process
    that wrote bytes and crashed before announcing them leaves `processes` instead, once its bytes expire. So sums
    read from the database under the same version, with none of the processes gone since, include every written byte.
    """

    version: str | None
    processes: frozenset[str]
    days: Mapping[date, Usage]


class TrafficShare(ABC):
    """Where processes counting traffic into the same tables tell each other what they haven't written yet.

    Owners are strings, e.g. `basic_proxy_account_traffic:42`. One per process, shared by nothing else.
    """

    @property
    @abstractmethod
    def lease(self) -> float:
        """Seconds what's published lives unless published again, versions included: a reader away longer may miss
        them come and go.
        """

    @abstractmethod
    async def publish(self, unwritten: Mapping[str, Mapping[date, Usage]], /, *, written: Collection[str]) -> None:
        """Replace what this process published: its unwritten bytes per owner and day, owners left out have none.
        Change the version of the owners in `written` at once with their bytes: bytes of them were written. Reach the
        share even with nothing to publish, so it tells whether it's back. Raise `TrafficShareUnavailable` if it
        can't be reached.
        """

    @abstractmethod
    async def read(self, owners: Collection[str], /) -> dict[str, SharedTraffic]:
        """What the other processes published for each of `owners`, each owner read at once with its version.
        Reach the share even with no owners, so it tells whether it's back. Raise `TrafficShareUnavailable` if it
        can't be reached.
        """
