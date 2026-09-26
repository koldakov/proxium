from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import TYPE_CHECKING, Final

from ._policies import Forbidden

if TYPE_CHECKING:
    from collections.abc import Iterable

type IPAddress = IPv4Address | IPv6Address
type IPNetwork = IPv4Network | IPv6Network

# RFC 6052: IPv6 addresses that a NAT64 gateway translates to the IPv4 address in the last 32 bits.
NAT64: Final[IPv6Network] = IPv6Network("64:ff9b::/96")


class ForbiddenAddress(Forbidden):
    pass


def _unwrap(ip: IPAddress, /) -> IPAddress:
    """The IPv4 address an IPv6 one leads to, e.g. ::ffff:127.0.0.1 leads to 127.0.0.1."""
    if not isinstance(ip, IPv6Address):
        return ip
    if ip in NAT64:
        return IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.ipv4_mapped or ip.sixtofour or ip


class AddressGuard:
    """Decides which IP addresses the proxy may connect to, against SSRF.

    Only the public internet is allowed by default: loopback, private, link-local (cloud metadata at 169.254.169.254),
    shared, reserved and multicast addresses are blocked. Networks in `allow` go through anyway.
    """

    def __init__(
        self,
        *,
        allow: Iterable[IPNetwork] = (),
    ) -> None:
        self._allow: tuple[IPNetwork, ...] = tuple(allow)

    def is_allowed(self, ip: IPAddress, /) -> bool:
        ip = _unwrap(ip)
        if any(ip in network for network in self._allow):
            return True
        return ip.is_global and not ip.is_multicast


DEFAULT_GUARD: Final[AddressGuard] = AddressGuard()
