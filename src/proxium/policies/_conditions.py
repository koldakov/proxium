from __future__ import annotations

from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from proxium.proxy import Request, Session


class UnknownConditionError(Exception):
    """A condition block of a kind no parser handles, e.g. stored by a newer version."""


class Condition(ABC):
    """When a rule applies.

    One instance serves all connections at once: keep no per-connection state on it,
    otherwise concurrent connections overwrite each other's data.
    """

    @abstractmethod
    def matches(self, request: Request, session: Session, /) -> bool:
        pass


class AlwaysCondition(Condition):
    def matches(self, request: Request, session: Session, /) -> bool:
        return True


ALWAYS: Final[Condition] = AlwaysCondition()


type ConditionFactory = Callable[[Mapping[str, Any], ConditionParser], Condition]


def _parse_always(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    return ALWAYS


DEFAULT_CONDITION_KINDS: Final[Mapping[str, ConditionFactory]] = MappingProxyType(
    {
        "always": _parse_always,
    },
)


class ConditionParser:
    """Builds a condition from its stored form: a tree of blocks, each with a `kind`.

    Pass more kinds to support new blocks. A factory gets the parser, so a block may hold other blocks.
    """

    def __init__(
        self,
        kinds: Mapping[str, ConditionFactory] = DEFAULT_CONDITION_KINDS,
        /,
    ) -> None:
        self._kinds: dict[str, ConditionFactory] = dict(kinds)

    def parse(self, data: Mapping[str, Any], /) -> Condition:
        try:
            factory = self._kinds[data["kind"]]
        except KeyError as err:
            raise UnknownConditionError(f"Unknown condition: {data!r}.") from err

        return factory(data, self)


DEFAULT_CONDITION_PARSER: Final[ConditionParser] = ConditionParser()
