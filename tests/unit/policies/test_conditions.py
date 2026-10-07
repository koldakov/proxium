from __future__ import annotations

import ipaddress
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

import pytest

from proxium.policies import (
    DEFAULT_CONDITION_PARSER,
    ClientNetworkCondition,
    InvalidConditionError,
    ScheduleCondition,
    TargetHostCondition,
    TargetNetworkCondition,
    UnknownConditionError,
)
from proxium.proxy import Address
from tests.fixtures.policies import ManualClock

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session

# A Monday of a week without daylight saving changes anywhere: local times exist and last an hour.
MONDAY: Final[datetime] = datetime(2026, 1, 12)  # Naive: placed in a zone by each test.


def _at(zone: ZoneInfo, day: int, hour: int, /) -> datetime:
    """The time `hour`:00 in `zone` on ISO weekday `day` of the week of `MONDAY`."""
    return (MONDAY + timedelta(days=day - 1, hours=hour)).replace(tzinfo=zone)


class TestConditionParser:
    def test_parse_raises_unknown_condition_error_when_kind_unknown(self, faker: Faker) -> None:
        # Act & Assert
        with pytest.raises(UnknownConditionError):
            DEFAULT_CONDITION_PARSER.parse({"kind": f"unknown-{faker.word()}"})

    def test_parse_raises_error_with_path_to_invalid_nested_block(self, faker: Faker) -> None:
        # Arrange
        last = faker.pyint(min_value=1, max_value=65534)
        condition = {
            "kind": "all",
            "conditions": [
                {"kind": "always"},
                {"kind": "not", "condition": {"kind": "target_port", "ports": [{"first": last + 1, "last": last}]}},
            ],
        }

        # Act
        with pytest.raises(InvalidConditionError) as error:
            DEFAULT_CONDITION_PARSER.parse(condition)

        # Assert
        assert error.value.path == ("conditions", 1, "condition", "ports", 0)

    def test_parse_raises_invalid_condition_error_when_field_unexpected(self, faker: Faker) -> None:
        # Arrange
        field = f"unexpected_{faker.word()}"

        # Act
        with pytest.raises(InvalidConditionError) as error:
            DEFAULT_CONDITION_PARSER.parse({"kind": "encrypted", field: faker.word()})

        # Assert
        assert error.value.path == (field,)

    def test_parse_raises_invalid_condition_error_when_time_zone_unknown(self, faker: Faker) -> None:
        # Arrange
        condition = {
            "kind": "schedule",
            "days": [faker.pyint(min_value=1, max_value=7)],
            "start": "09:00",
            "end": "18:00",
            "timezone": f"Unknown/{faker.word()}",
        }

        # Act
        with pytest.raises(InvalidConditionError) as error:
            DEFAULT_CONDITION_PARSER.parse(condition)

        # Assert
        assert error.value.path == ("timezone",)

    def test_parse_builds_condition_matching_as_its_blocks_combine(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        domain = faker.domain_name()
        port = faker.port_number()
        condition = DEFAULT_CONDITION_PARSER.parse(
            {
                "kind": "all",
                "conditions": [
                    {"kind": "target_host", "domains": [domain]},
                    {"kind": "not", "condition": {"kind": "target_port", "ports": [{"first": port, "last": port}]}},
                ],
            },
        )
        other_port = port % 65535 + 1

        # Act
        to_other_port = condition.matches(proxy_request_factory(target=Address(domain, other_port)), session)
        to_port = condition.matches(proxy_request_factory(target=Address(domain, port)), session)

        # Assert
        assert to_other_port
        assert not to_port


class TestTargetHostCondition:
    def test_matches_returns_true_when_target_is_subdomain(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        domain = faker.domain_name()
        condition = TargetHostCondition([domain])
        request = proxy_request_factory(target=Address(f"{faker.word()}.{domain}", faker.port_number()))

        # Act
        matches = condition.matches(request, session)

        # Assert
        assert matches

    def test_matches_returns_false_when_target_only_ends_like_domain(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        domain = faker.domain_name()
        condition = TargetHostCondition([domain])
        request = proxy_request_factory(target=Address(f"{faker.word()}{domain}", faker.port_number()))

        # Act
        matches = condition.matches(request, session)

        # Assert
        assert not matches

    def test_matches_returns_true_when_target_differs_in_case_and_root_dot(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        domain = faker.domain_name()
        condition = TargetHostCondition([domain.upper()])
        request = proxy_request_factory(target=Address(f"{domain}.", faker.port_number()))

        # Act
        matches = condition.matches(request, session)

        # Assert
        assert matches


class TestTargetNetworkCondition:
    def test_matches_returns_false_when_target_is_name(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        condition = TargetNetworkCondition([ipaddress.ip_network(faker.ipv4(network=True))])
        request = proxy_request_factory(target=Address(faker.domain_name(), faker.port_number()))

        # Act
        matches = condition.matches(request, session)

        # Assert
        assert not matches


class TestClientNetworkCondition:
    def test_matches_returns_true_when_client_ipv4_comes_mapped_to_ipv6(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        client_ip = faker.ipv4()
        condition = ClientNetworkCondition([ipaddress.ip_network(client_ip)])
        session.client = Address(f"::ffff:{client_ip}", faker.port_number())

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert matches

    def test_matches_returns_false_when_client_address_unknown(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        condition = ClientNetworkCondition([ipaddress.ip_network("0.0.0.0/0")])  # Every IPv4 client.
        session.client = None

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert not matches


class TestScheduleCondition:
    def test_matches_returns_true_when_inside_window(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        zone = ZoneInfo(faker.timezone())
        day = faker.pyint(min_value=1, max_value=7)
        start = faker.pyint(min_value=0, max_value=20)
        end = faker.pyint(min_value=start + 2, max_value=23)
        clock = ManualClock(_at(zone, day, faker.pyint(min_value=start, max_value=end - 1)))
        condition = ScheduleCondition([day], start=time(start), end=time(end), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert matches

    def test_matches_returns_false_when_day_not_listed(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        zone = ZoneInfo(faker.timezone())
        day = faker.pyint(min_value=1, max_value=7)
        other_day = day % 7 + 1
        clock = ManualClock(_at(zone, other_day, faker.pyint(min_value=0, max_value=23)))
        condition = ScheduleCondition([day], start=time(0), end=time(0), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert not matches

    def test_matches_returns_true_next_morning_when_window_runs_past_midnight(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        zone = ZoneInfo(faker.timezone())
        # Sunday too: its night runs into Monday of the next week.
        day = faker.pyint(min_value=1, max_value=7)
        clock = ManualClock(_at(zone, day + 1, faker.pyint(min_value=0, max_value=5)))
        condition = ScheduleCondition([day], start=time(22), end=time(6), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert matches

    def test_matches_returns_false_early_on_start_day_when_window_runs_past_midnight(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        zone = ZoneInfo(faker.timezone())
        day = faker.pyint(min_value=1, max_value=7)
        clock = ManualClock(_at(zone, day, faker.pyint(min_value=0, max_value=5)))
        condition = ScheduleCondition([day], start=time(22), end=time(6), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert not matches

    def test_matches_returns_true_all_day_when_start_equals_end(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        zone = ZoneInfo(faker.timezone())
        day = faker.pyint(min_value=1, max_value=7)
        hour = faker.pyint(min_value=0, max_value=23)
        clock = ManualClock(_at(zone, day, faker.pyint(min_value=0, max_value=23)))
        condition = ScheduleCondition([day], start=time(hour), end=time(hour), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert matches

    def test_matches_returns_true_when_window_holds_by_zone_time_not_by_clock_time(
        self,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        # Tokyo is UTC+9 all year: Monday 01:00 UTC is 10:00 there.
        zone = ZoneInfo("Asia/Tokyo")
        clock = ManualClock(_at(ZoneInfo("UTC"), 1, 1))
        condition = ScheduleCondition([1], start=time(9), end=time(11), zone=zone, clock=clock)

        # Act
        matches = condition.matches(proxy_request, session)

        # Assert
        assert matches
