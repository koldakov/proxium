from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from proxium.db import QuotaPeriod
from proxium.policies import period_start

if TYPE_CHECKING:
    from faker import Faker


class TestPeriodStart:
    def test_period_start_returns_last_period_boundary_when_days(self, faker: Faker) -> None:
        # Arrange
        anchor = faker.date_object()
        length = faker.pyint(min_value=1, max_value=90)
        today = anchor + timedelta(days=faker.pyint(min_value=0, max_value=3650))

        # Act
        start = period_start(anchor, today, QuotaPeriod.DAY, length=length)

        # Assert
        assert (start - anchor).days % length == 0
        assert 0 <= (today - start).days < length

    def test_period_start_returns_period_before_anchor_when_anchor_in_future(self, faker: Faker) -> None:
        # Arrange
        today = faker.date_object()
        length = faker.pyint(min_value=1, max_value=90)
        anchor = today + timedelta(days=faker.pyint(min_value=1, max_value=3650))

        # Act
        start = period_start(anchor, today, QuotaPeriod.DAY, length=length)

        # Assert
        assert (anchor - start).days % length == 0
        assert 0 <= (today - start).days < length

    # Fixed dates: month ends are the case, a random day rarely hits them.
    def test_period_start_returns_month_end_when_anchor_day_missing_in_month(self) -> None:
        # Act
        start = period_start(date(2027, 1, 31), date(2027, 3, 15), QuotaPeriod.MONTH)

        # Assert
        assert start == date(2027, 2, 28)

    def test_period_start_returns_anchor_day_again_when_month_long_enough(self) -> None:
        # Act
        start = period_start(date(2027, 1, 31), date(2027, 3, 31), QuotaPeriod.MONTH)

        # Assert
        assert start == date(2027, 3, 31)

    def test_period_start_returns_previous_start_when_day_before_boundary(self) -> None:
        # Act
        start = period_start(date(2026, 1, 15), date(2026, 4, 14), QuotaPeriod.MONTH, length=3)

        # Assert
        assert start == date(2026, 1, 15)

    def test_period_start_returns_new_start_when_on_boundary(self) -> None:
        # Act
        start = period_start(date(2026, 1, 15), date(2026, 4, 15), QuotaPeriod.MONTH, length=3)

        # Assert
        assert start == date(2026, 4, 15)

    def test_period_start_returns_anchor_when_total(self, faker: Faker) -> None:
        # Arrange
        anchor = faker.date_object()
        today = anchor + timedelta(days=faker.pyint(min_value=0, max_value=3650))

        # Act
        start = period_start(anchor, today, QuotaPeriod.TOTAL)

        # Assert
        assert start == anchor
