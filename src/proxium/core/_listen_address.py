import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from ipaddress import ip_network
from typing import ClassVar, Final, Self

from proxium.proxy import Host, Hostname

RANGE_SEPARATOR: Final[str] = "-"
LIST_SEPARATOR: Final[str] = ","
MIN_PORT: Final[int] = 1
MAX_PORT: Final[int] = 65535
# Guards against a typo like 10.0.0.0/8:1-65535 opening millions of sockets, per item and in total.
MAX_SOCKETS: Final[int] = 65_536
IPV6: Final[int] = 6


class HostParser(ABC):
    """Turns the host part of `host:port` into hosts to listen on."""

    @abstractmethod
    def detect(self, value: str, /) -> bool:
        """Whether `value` is in this parser's format, valid or not."""

    @abstractmethod
    def parse(self, value: str, /) -> list[Host]:
        """Raise `ValueError` if `value` is invalid."""


class IPParser(HostParser):
    """An address or a network, IPv6 in brackets: `127.0.0.1`, `10.0.0.0/29`, `[::1]`, `[2001:db8::/125]`."""

    # Digits, dots and a prefix: IPv4-like, even if invalid, so `10.0.0.256` isn't taken for a host name.
    ipv4_like: ClassVar[re.Pattern[str]] = re.compile(r"[\d./]+")

    def detect(self, value: str, /) -> bool:
        return value.startswith("[") or ":" in value or bool(self.ipv4_like.fullmatch(value))

    def parse(self, value: str, /) -> list[Host]:
        bracketed = value.startswith("[") and value.endswith("]")
        try:
            # A single address is a network of one.
            network = ip_network(value[1:-1] if bracketed else value)
        except ValueError as error:
            raise ValueError(f"Invalid IP address or network {value!r}.") from error
        if network.version == IPV6 and not bracketed:
            raise ValueError(f"IPv6 goes in brackets, e.g. [::1]:8080, got {value!r}.")
        if network.version != IPV6 and bracketed:
            raise ValueError(f"Only IPv6 goes in brackets, got {value!r}.")
        if network.num_addresses > MAX_SOCKETS:
            raise ValueError(f"Network {value!r} is too large.")
        return list(network.hosts())


class HostnameParser(HostParser):
    """A host name, resolved when the socket is opened: `localhost`."""

    def detect(self, value: str, /) -> bool:
        # Everything that isn't an IP.
        return True

    def parse(self, value: str, /) -> list[Host]:
        return [Hostname(value)]


def _parse_port(value: str, /) -> int:
    # ASCII digits only: isdigit() also takes superscripts and isdecimal() takes fullwidth digits.
    if not (value.isascii() and value.isdecimal()) or not MIN_PORT <= int(value) <= MAX_PORT:
        raise ValueError(f"Invalid port {value!r}.")
    return int(value)


def _parse_ports(value: str, /) -> range:
    """A port or an inclusive range: `10000-10999`."""
    first, separator, last = value.partition(RANGE_SEPARATOR)
    start = _parse_port(first)
    end = _parse_port(last) if separator else start
    if end < start:
        raise ValueError(f"Invalid port range {value!r}.")
    return range(start, end + 1)


@dataclass(frozen=True, slots=True)
class ListenAddress:
    """Hosts and ports to listen on, every host on every port."""

    hosts: list[Host]
    ports: range

    # Tried in order, the first to detect the format parses it.
    host_parsers: ClassVar[tuple[HostParser, ...]] = (
        IPParser(),
        HostnameParser(),
    )

    @classmethod
    def parse(cls, value: str, /) -> Self:
        """Parse `host:port`, e.g. `localhost:8080` or `10.0.0.0/29:10000-10999`."""
        value = value.strip()
        hosts, colon, ports = value.rpartition(":")
        if not colon or not hosts:
            raise ValueError(f"Expected host:port, got {value!r}.")
        address = cls(hosts=cls._parse_hosts(hosts), ports=_parse_ports(ports))
        if len(address.hosts) * len(address.ports) > MAX_SOCKETS:
            raise ValueError(f"{value!r} opens more than {MAX_SOCKETS} sockets.")
        return address

    @classmethod
    def parse_list(cls, value: str, /) -> list[Self]:
        """Parse comma-separated addresses: `localhost:8080,[::1]:8080`. Fails on any invalid or empty item."""
        if not value.strip():
            raise ValueError("Expected at least one host:port.")
        addresses = [cls.parse(item) for item in value.split(LIST_SEPARATOR)]
        if sum(len(address.hosts) * len(address.ports) for address in addresses) > MAX_SOCKETS:
            raise ValueError(f"{value!r} opens more than {MAX_SOCKETS} sockets in total.")
        return addresses

    @classmethod
    def _parse_hosts(cls, value: str, /) -> list[Host]:
        parser = next((parser for parser in cls.host_parsers if parser.detect(value)), None)
        if parser is None:
            raise ValueError(f"Unsupported host {value!r}.")
        return parser.parse(value)
