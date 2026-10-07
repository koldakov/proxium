from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from datetime import UTC, datetime, time
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, Any, Final, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    ConfigDict,
    Field,
    IPvAnyNetwork,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from proxium.proxy import IPAddress, IPNetwork, Request, Session


class InvalidConditionError(Exception):
    """A condition block that can't be built, e.g. of a wrong shape. `path` leads to it from the root block."""

    def __init__(self, reason: str, /, *, path: tuple[str | int, ...] = ()) -> None:
        super().__init__(reason, path)
        self.reason: str = reason
        self.path: tuple[str | int, ...] = path

    def __str__(self) -> str:
        if not self.path:
            return self.reason
        return f"{'.'.join(map(str, self.path))}: {self.reason}"

    def within(self, *path: str | int) -> InvalidConditionError:
        """The same error seen from the block holding this one under `path`."""
        return type(self)(self.reason, path=(*path, *self.path))


class UnknownConditionError(InvalidConditionError):
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


class AllCondition(Condition):
    """Every one of `conditions` matches."""

    def __init__(self, conditions: Iterable[Condition], /) -> None:
        self._conditions: tuple[Condition, ...] = tuple(conditions)

    def matches(self, request: Request, session: Session, /) -> bool:
        return all(condition.matches(request, session) for condition in self._conditions)


class AnyCondition(Condition):
    """At least one of `conditions` matches."""

    def __init__(self, conditions: Iterable[Condition], /) -> None:
        self._conditions: tuple[Condition, ...] = tuple(conditions)

    def matches(self, request: Request, session: Session, /) -> bool:
        return any(condition.matches(request, session) for condition in self._conditions)


class NotCondition(Condition):
    def __init__(self, condition: Condition, /) -> None:
        self._condition: Condition = condition

    def matches(self, request: Request, session: Session, /) -> bool:
        return not self._condition.matches(request, session)


def _normalize_host(host: str, /) -> str:
    """Hosts compare case-insensitively, with or without the root dot."""
    return host.lower().rstrip(".")


def _parse_ip(host: str, /) -> IPAddress:
    """Raises `ValueError` if `host` is a name, not an IP. An IPv4-mapped IPv6 is the IPv4 it carries."""
    ip = ipaddress.ip_address(host)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _in_networks(host: str, networks: Sequence[IPNetwork], /) -> bool:
    try:
        ip = _parse_ip(host)
    except ValueError:
        return False

    return any(ip in network for network in networks)


class TargetHostCondition(Condition):
    """The target is one of `domains` or their subdomains, e.g. `example.com` matches `api.example.com` too.

    Compared by name as the client sent it: an IP target doesn't match a domain, see `TargetNetworkCondition`.
    """

    def __init__(self, domains: Iterable[str], /) -> None:
        self._domains: tuple[str, ...] = tuple(_normalize_host(domain) for domain in domains)

    def matches(self, request: Request, session: Session, /) -> bool:
        host = _normalize_host(request.target.host)
        return any(host == domain or host.endswith(f".{domain}") for domain in self._domains)


class TargetNetworkCondition(Condition):
    """The client asked for an IP in one of `networks`. A target given by name doesn't match: it's not resolved yet."""

    def __init__(self, networks: Iterable[IPNetwork], /) -> None:
        self._networks: tuple[IPNetwork, ...] = tuple(networks)

    def matches(self, request: Request, session: Session, /) -> bool:
        return _in_networks(request.target.host, self._networks)


class TargetPortCondition(Condition):
    """The target port is in one of `ranges`, both ends included."""

    def __init__(self, ranges: Iterable[tuple[int, int]], /) -> None:
        self._ranges: tuple[tuple[int, int], ...] = tuple(ranges)

    def matches(self, request: Request, session: Session, /) -> bool:
        port = request.target.port
        return any(first <= port <= last for first, last in self._ranges)


class ProtocolCondition(Condition):
    """The request came in over one of `protocols`, as the inbounds name them, e.g. `socks5`."""

    def __init__(self, protocols: Iterable[str], /) -> None:
        self._protocols: frozenset[str] = frozenset(protocols)

    def matches(self, request: Request, session: Session, /) -> bool:
        return request.protocol in self._protocols


class ClientNetworkCondition(Condition):
    """The client connects from an IP in one of `networks`."""

    def __init__(self, networks: Iterable[IPNetwork], /) -> None:
        self._networks: tuple[IPNetwork, ...] = tuple(networks)

    def matches(self, request: Request, session: Session, /) -> bool:
        if session.client is None:
            return False
        return _in_networks(session.client.host, self._networks)


class EncryptedCondition(Condition):
    """The client came over TLS."""

    def matches(self, request: Request, session: Session, /) -> bool:
        return session.encrypted


ENCRYPTED: Final[Condition] = EncryptedCondition()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScheduleCondition(Condition):
    """The time in `zone` is from `start` till `end` on one of `days`, ISO weekdays: 1 is Monday.

    `end` before `start` runs past midnight, and the day is the one it starts on: Friday 22:00 to 06:00 matches early
    Saturday too. `end` equal to `start` is the whole day. Rules are chosen on the clock of `clock`, an aware time.
    """

    def __init__(
        self,
        days: Iterable[int],
        /,
        *,
        start: time,
        end: time,
        zone: ZoneInfo,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._days: frozenset[int] = frozenset(days)
        self._start: time = start
        self._end: time = end
        self._zone: ZoneInfo = zone
        self._clock: Callable[[], datetime] = clock

    def matches(self, request: Request, session: Session, /) -> bool:
        now = self._clock().astimezone(self._zone)
        day = now.isoweekday()
        at = now.time()
        if self._start == self._end:
            return day in self._days
        if self._start < self._end:
            return day in self._days and self._start <= at < self._end

        # Past midnight: the late part of the starting day or the early part of the next one.
        previous_day = (day - 2) % 7 + 1
        return (day in self._days and at >= self._start) or (previous_day in self._days and at < self._end)


type ConditionFactory = Callable[[Mapping[str, Any], ConditionParser], Condition]

# A misspelled field is an error rather than skipped. Numbers and text are strict, see the fields.
_PARAMS_CONFIG: Final[ConfigDict] = ConfigDict(extra="forbid")

# Bounded: a condition is checked on every connection.
_MAX_ITEMS: Final[int] = 256


def _parse_params[T](params_type: type[T], data: Mapping[str, Any], /) -> T:
    """`data` without its `kind` as `params_type`, a pydantic dataclass."""
    params = {key: value for key, value in data.items() if key != "kind"}
    try:
        return TypeAdapter(params_type).validate_python(params)
    except ValidationError as err:
        error = err.errors()[0]
        # A check of ours says what's wrong itself, without pydantic's "Value error," before it.
        reason = str(error["ctx"]["error"]) if error["type"] == "value_error" else error["msg"]
        raise InvalidConditionError(reason, path=tuple(error["loc"])) from None


def _parse_children(data: Sequence[Mapping[str, Any]], parser: ConditionParser, /) -> list[Condition]:
    conditions: list[Condition] = []
    for index, child in enumerate(data):
        try:
            conditions.append(parser.parse(child))
        except InvalidConditionError as err:
            raise err.within("conditions", index) from None
    return conditions


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _EmptyParams:
    pass


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _GroupParams:
    # Of any kinds: each is parsed on its own.
    conditions: Annotated[list[dict[StrictStr, Any]], Field(min_length=1, max_length=_MAX_ITEMS)]


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _NotParams:
    condition: dict[StrictStr, Any]


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _DomainsParams:
    domains: Annotated[
        list[Annotated[StrictStr, Field(min_length=1, max_length=253)]],
        Field(min_length=1, max_length=_MAX_ITEMS),
    ]

    @model_validator(mode="after")
    def _check_domains(self) -> Self:
        # Punycode: clients send internationalized names that way.
        for domain in self.domains:
            try:
                domain.encode("idna")
            except UnicodeError as err:
                raise ValueError(f"Not a domain: {domain!r}.") from err
        return self


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _NetworksParams:
    networks: Annotated[
        list[IPvAnyNetwork],
        Field(min_length=1, max_length=_MAX_ITEMS),
    ]


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _PortRange:
    first: Annotated[StrictInt, Field(ge=1, le=65535)]
    last: Annotated[StrictInt, Field(ge=1, le=65535)]

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.first > self.last:
            raise ValueError("The first port goes before the last.")
        return self


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _PortsParams:
    ports: Annotated[list[_PortRange], Field(min_length=1, max_length=_MAX_ITEMS)]


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _ProtocolsParams:
    protocols: Annotated[
        list[Annotated[StrictStr, Field(min_length=1, max_length=64)]],
        Field(min_length=1, max_length=_MAX_ITEMS),
    ]


@dataclass(frozen=True, slots=True, config=_PARAMS_CONFIG)
class _ScheduleParams:
    days: Annotated[list[Annotated[StrictInt, Field(ge=1, le=7)]], Field(min_length=1, max_length=7)]
    # `HH:MM` in `timezone`.
    start: time
    end: time
    # IANA, e.g. `Europe/Berlin`.
    timezone: Annotated[StrictStr, Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Times go without an offset: the time zone is given apart.")
        return self


def _parse_always(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    return ALWAYS


def _parse_all(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_GroupParams, data)
    return AllCondition(_parse_children(params.conditions, parser))


def _parse_any(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_GroupParams, data)
    return AnyCondition(_parse_children(params.conditions, parser))


def _parse_not(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_NotParams, data)
    try:
        condition = parser.parse(params.condition)
    except InvalidConditionError as err:
        raise err.within("condition") from None
    return NotCondition(condition)


def _parse_target_host(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_DomainsParams, data)
    return TargetHostCondition(domain.encode("idna").decode() for domain in params.domains)


def _parse_target_network(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_NetworksParams, data)
    return TargetNetworkCondition(params.networks)


def _parse_target_port(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_PortsParams, data)
    return TargetPortCondition((port_range.first, port_range.last) for port_range in params.ports)


def _parse_protocol(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_ProtocolsParams, data)
    return ProtocolCondition(params.protocols)


def _parse_client_network(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_NetworksParams, data)
    return ClientNetworkCondition(params.networks)


def _parse_encrypted(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    _parse_params(_EmptyParams, data)
    return ENCRYPTED


def _parse_schedule(data: Mapping[str, Any], parser: ConditionParser, /) -> Condition:
    params = _parse_params(_ScheduleParams, data)
    try:
        zone = ZoneInfo(params.timezone)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise InvalidConditionError(f"Unknown time zone: {params.timezone!r}.", path=("timezone",)) from err
    return ScheduleCondition(params.days, start=params.start, end=params.end, zone=zone)


DEFAULT_CONDITION_KINDS: Final[Mapping[str, ConditionFactory]] = MappingProxyType(
    {
        "always": _parse_always,
        "all": _parse_all,
        "any": _parse_any,
        "not": _parse_not,
        "target_host": _parse_target_host,
        "target_network": _parse_target_network,
        "target_port": _parse_target_port,
        "protocol": _parse_protocol,
        "client_network": _parse_client_network,
        "encrypted": _parse_encrypted,
        "schedule": _parse_schedule,
    },
)


class ConditionParser:
    """Builds a condition from its stored form: a tree of blocks, each with a `kind`.

    Pass more kinds to support new blocks. A factory gets the parser, so a block may hold other blocks.
    Raises `InvalidConditionError` for a block it can't build, `UnknownConditionError` for an unknown kind.
    """

    def __init__(
        self,
        kinds: Mapping[str, ConditionFactory] = DEFAULT_CONDITION_KINDS,
        /,
    ) -> None:
        self._kinds: dict[str, ConditionFactory] = dict(kinds)

    def _get_factory(self, data: Mapping[str, Any], /) -> ConditionFactory:
        try:
            kind = data["kind"]
        except KeyError:
            raise InvalidConditionError("A block needs a kind.") from None

        try:
            return self._kinds[kind]
        except KeyError, TypeError:
            raise UnknownConditionError(f"Unknown condition kind: {kind!r}.", path=("kind",)) from None

    def parse(self, data: Mapping[str, Any], /) -> Condition:
        factory = self._get_factory(data)
        return factory(data, self)


DEFAULT_CONDITION_PARSER: Final[ConditionParser] = ConditionParser()
