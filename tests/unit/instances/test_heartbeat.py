from __future__ import annotations

import asyncio
import logging
from ipaddress import ip_address
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

import pytest

from proxium.instances import InstanceHeartbeat, read_interface_ips

if TYPE_CHECKING:
    from collections.abc import Callable
    from ipaddress import IPv4Address, IPv6Address

    import ifaddr
    from faker import Faker

# Pending on start, then the stop.
_REPORTS_TILL_STOP: Final[int] = 2


class TestInstanceHeartbeat:
    def test_init_raises_value_error_on_negative_spare_reports(self, faker: Faker) -> None:
        # Arrange
        spare_reports = faker.pyint(min_value=-10, max_value=-1)

        # Act
        with pytest.raises(ValueError, match="Spare reports can't be negative"):
            InstanceHeartbeat(spare_reports=spare_reports)

    async def test_close_returns_and_warns_once_when_database_fails(self, caplog: pytest.LogCaptureFixture) -> None:
        # Arrange
        heartbeat = InstanceHeartbeat(interval=60.0)

        # Act
        # Every report fails as if the database were down: the proxy still shuts down.
        with (
            patch("proxium.instances._heartbeat.session_manager") as session_manager,
            caplog.at_level(logging.WARNING),
        ):
            session_manager.session.side_effect = OSError()
            heartbeat.start()
            # The first report runs: it fails at once, then waits for the next one.
            await asyncio.sleep(0)
            await heartbeat.close()

        # Assert
        # One warning for the whole outage.
        assert session_manager.session.call_count == _REPORTS_TILL_STOP
        assert len([record for record in caplog.records if "Can't report" in record.getMessage()]) == 1


class TestReadInterfaceIps:
    def test_read_interface_ips_returns_ipv6_without_flow_info_and_scope(
        self,
        faker: Faker,
        adapter_factory: Callable[[list[IPv4Address | IPv6Address]], ifaddr.Adapter],
    ) -> None:
        # Arrange
        ip = ip_address(faker.ipv6())
        adapter = adapter_factory([ip])

        # Act
        with patch("proxium.instances._heartbeat.ifaddr.get_adapters", return_value=[adapter]):
            ips = read_interface_ips()

        # Assert
        assert ips == [ip]

    def test_read_interface_ips_returns_each_ip_once_ipv4_first(
        self,
        faker: Faker,
        adapter_factory: Callable[[list[IPv4Address | IPv6Address]], ifaddr.Adapter],
    ) -> None:
        # Arrange
        # Both families together: sorting them as they are would raise.
        ipv4, ipv6 = ip_address(faker.ipv4()), ip_address(faker.ipv6())
        adapters = [adapter_factory([ipv6, ipv4]), adapter_factory([ipv4])]

        # Act
        with patch("proxium.instances._heartbeat.ifaddr.get_adapters", return_value=adapters):
            ips = read_interface_ips()

        # Assert
        assert ips == [ipv4, ipv6]
