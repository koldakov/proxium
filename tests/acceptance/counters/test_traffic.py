from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from proxium.counters import RedisTrafficShare
from proxium.proxy import Usage

if TYPE_CHECKING:
    from faker import Faker

    from proxium.observers import SharedTraffic


class TestRedisTrafficShare:
    def test_check_support_passes_on_supported_redis(
        self,
        loop_runner: asyncio.Runner,
        shared_redis_manager: None,
    ) -> None:
        # Arrange
        share = RedisTrafficShare()

        # Act
        # Every Redis of the CI matrix supports quotas: nothing raised.
        loop_runner.run(share.check_support())

    def test_read_returns_bytes_of_other_processes_only(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        # Two instances on one Redis.
        publisher, reader = RedisTrafficShare(), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[]))

        # Act
        own = loop_runner.run(publisher.read([traffic_owner]))
        others = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        assert own[traffic_owner].days == {}
        assert own[traffic_owner].processes == frozenset()
        assert others[traffic_owner].days == days
        assert len(others[traffic_owner].processes) == 1

    def test_publish_changes_version_only_when_owner_written(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        publisher, reader = RedisTrafficShare(), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}

        async def publish_and_read(*, written: bool) -> SharedTraffic:
            await publisher.publish({traffic_owner: days}, written=[traffic_owner] if written else [])
            return (await reader.read([traffic_owner]))[traffic_owner]

        # Act
        first = loop_runner.run(publish_and_read(written=True))
        unwritten = loop_runner.run(publish_and_read(written=False))
        written = loop_runner.run(publish_and_read(written=True))

        # Assert
        assert first.version is not None
        assert unwritten.version == first.version
        assert written.version != first.version

    def test_publish_removes_process_of_owner_left_out(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        publisher, reader = RedisTrafficShare(), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[]))

        # Act
        # Everything written: the owner has no unwritten bytes left.
        loop_runner.run(publisher.publish({}, written=[traffic_owner]))
        shared = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        assert shared[traffic_owner].days == {}
        # Gone at once: not left to expire, readers would take it for a crash and read the database again.
        assert shared[traffic_owner].processes == frozenset()

    def test_read_drops_bytes_of_process_that_stopped_publishing_after_lease(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        lease = 0.05
        # Crashes after one publish: nothing renews its field.
        crashed, reader = RedisTrafficShare(lease=lease), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(crashed.publish({traffic_owner: days}, written=[]))

        # Act
        loop_runner.run(asyncio.sleep(lease * 2))
        shared = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        assert shared[traffic_owner].days == {}
        assert shared[traffic_owner].processes == frozenset()

    def test_publish_renews_bytes_of_process(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        lease = 1.0
        publisher, reader = RedisTrafficShare(lease=lease), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[]))
        loop_runner.run(asyncio.sleep(lease * 0.6))

        # Act
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[]))
        # Past the lease of the first publish, within the one of the second: read at 1.2 s, the field lives till 1.6 s.
        loop_runner.run(asyncio.sleep(lease * 0.6))
        shared = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        assert shared[traffic_owner].days == days

    def test_read_returns_no_version_once_its_lease_expired(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        lease = 0.05
        publisher, reader = RedisTrafficShare(lease=lease), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[traffic_owner]))

        # Act
        loop_runner.run(asyncio.sleep(lease * 2))
        shared = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        assert shared[traffic_owner].version is None

    def test_publish_renews_version_with_bytes(
        self,
        faker: Faker,
        loop_runner: asyncio.Runner,
        traffic_owner: str,
    ) -> None:
        # Arrange
        lease = 1.0
        publisher, reader = RedisTrafficShare(lease=lease), RedisTrafficShare()
        days = {datetime.now(UTC).date(): Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))}
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[traffic_owner]))
        version = loop_runner.run(reader.read([traffic_owner]))[traffic_owner].version
        loop_runner.run(asyncio.sleep(lease * 0.6))

        # Act
        # Bytes only, nothing written: the version stays and lives on with them.
        loop_runner.run(publisher.publish({traffic_owner: days}, written=[]))
        # Past the lease of the version's own publish: read at 1.2 s, renewed till 1.6 s.
        loop_runner.run(asyncio.sleep(lease * 0.6))
        shared = loop_runner.run(reader.read([traffic_owner]))

        # Assert
        # Expired, every reader would take it for a write and read the sums again.
        assert shared[traffic_owner].version == version
