from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from typing import TYPE_CHECKING

import pytest

from proxium.proxy import AddressGuard

if TYPE_CHECKING:
    from faker import Faker

    from proxium.proxy import IPNetwork


class TestAddressGuard:
    @pytest.mark.parametrize(
        "network",
        [
            pytest.param(IPv4Network("0.0.0.0/8"), id="this-network"),
            pytest.param(IPv4Network("10.0.0.0/8"), id="private-10"),
            pytest.param(IPv4Network("100.64.0.0/10"), id="shared"),
            pytest.param(IPv4Network("127.0.0.0/8"), id="loopback"),
            pytest.param(IPv4Network("169.254.0.0/16"), id="link-local"),
            pytest.param(IPv4Network("172.16.0.0/12"), id="private-172"),
            pytest.param(IPv4Network("192.168.0.0/16"), id="private-192"),
            pytest.param(IPv4Network("224.0.0.0/4"), id="multicast"),
            pytest.param(IPv4Network("240.0.0.0/4"), id="reserved"),
            pytest.param(IPv6Network("::1/128"), id="ipv6-loopback"),
            pytest.param(IPv6Network("fc00::/7"), id="ipv6-unique-local"),
            pytest.param(IPv6Network("fe80::/10"), id="ipv6-link-local"),
            pytest.param(IPv6Network("ff00::/8"), id="ipv6-multicast"),
        ],
    )
    def test_is_allowed_returns_false_when_address_not_public(self, faker: Faker, network: IPNetwork) -> None:
        # Arrange
        guard = AddressGuard()
        ip = network[faker.pyint(max_value=network.num_addresses - 1)]

        # Act
        allowed = guard.is_allowed(ip)

        # Assert
        assert not allowed

    def test_is_allowed_returns_true_when_address_public(self, faker: Faker) -> None:
        # Arrange
        guard = AddressGuard()

        # Act
        allowed = guard.is_allowed(IPv4Address(faker.ipv4_public()))

        # Assert
        assert allowed

    def test_is_allowed_returns_false_when_ipv4_mapped_address_not_public(self, faker: Faker) -> None:
        # Arrange
        guard = AddressGuard()
        ip = IPv6Address(f"::ffff:{faker.ipv4_private()}")

        # Act
        allowed = guard.is_allowed(ip)

        # Assert
        assert not allowed

    def test_is_allowed_returns_false_when_nat64_address_not_public(self, faker: Faker) -> None:
        # Arrange
        guard = AddressGuard()
        ip = IPv6Address(f"64:ff9b::{faker.ipv4_private()}")

        # Act
        allowed = guard.is_allowed(ip)

        # Assert
        assert not allowed

    def test_is_allowed_returns_false_when_6to4_address_not_public(self, faker: Faker) -> None:
        # Arrange
        guard = AddressGuard()
        # 2002::/16 carries the IPv4 address in the next 32 bits.
        ip = IPv6Address(0x2002 << 112 | int(IPv4Address(faker.ipv4_private())) << 80)

        # Act
        allowed = guard.is_allowed(ip)

        # Assert
        assert not allowed

    def test_is_allowed_returns_true_when_address_in_allowed_network(self, faker: Faker) -> None:
        # Arrange
        network = ip_network(faker.ipv4_private(network=True))
        guard = AddressGuard(allow=[network])
        ip = network[faker.pyint(max_value=network.num_addresses - 1)]

        # Act
        allowed = guard.is_allowed(ip)

        # Assert
        assert allowed
