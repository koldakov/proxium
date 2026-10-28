from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

import pytest

from proxium.instances import InstanceHeartbeat

if TYPE_CHECKING:
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
