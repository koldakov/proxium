from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from redis.asyncio.client import Pipeline
from redis.exceptions import ReadOnlyError, ResponseError

from proxium.counters import RedisTrafficShare, UnsupportedRedisError
from proxium.db import redis_manager
from proxium.observers import TrafficShareUnavailable
from proxium.proxy import Usage

if TYPE_CHECKING:
    from faker import Faker


class TestRedisTrafficShare:
    async def test_check_support_raises_unsupported_redis_error_on_unknown_command(self) -> None:
        # Arrange
        share = RedisTrafficShare()
        error = ResponseError("unknown command 'hpexpire', with args beginning with: ")

        # Act
        with (
            patch.object(redis_manager.client, "hpexpire", side_effect=error),
            pytest.raises(UnsupportedRedisError),
        ):
            await share.check_support()

    async def test_check_support_raises_traffic_share_unavailable_on_other_refusal(self) -> None:
        # Arrange
        share = RedisTrafficShare()
        # A replica after a failover: an outage, not a reason to refuse to start.
        error = ReadOnlyError("You can't write against a read only replica.")

        # Act
        with (
            patch.object(redis_manager.client, "hpexpire", side_effect=error),
            pytest.raises(TrafficShareUnavailable),
        ):
            await share.check_support()

    async def test_publish_logs_unknown_command_once(self, faker: Faker, caplog: pytest.LogCaptureFixture) -> None:
        # Arrange
        share = RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        # As a pipeline reports it: prefixed with the command's number.
        error = ResponseError(
            "Command # 2 (HPEXPIRE key 30000 FIELDS 1 field) of pipeline caused error: unknown command 'hpexpire'",
        )

        # Act
        with patch.object(Pipeline, "execute", side_effect=error), caplog.at_level(logging.ERROR):
            for _ in range(2):
                with pytest.raises(TrafficShareUnavailable):
                    await share.publish({faker.pystr(): days}, written=[])

        # Assert
        assert len([record for record in caplog.records if "Redis 7.4" in record.getMessage()]) == 1
