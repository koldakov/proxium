from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from proxium.proxy._relay import Relay
from tests.fixtures.proxy import CuttingGrant, HoldingGrant, ScriptedStream, StalledStream

if TYPE_CHECKING:
    from faker import Faker

    from proxium.proxy import Session

# Timing tests: short enough for the suite, apart enough for a busy CI runner.
IDLE_TIMEOUT = 0.05
HOLD_DELAY = IDLE_TIMEOUT * 3
# A broken idle timeout must fail the test, not hang the suite.
TEST_TIMEOUT = 1


class TestRelay:
    async def test_run_counts_bytes_of_each_direction(self, faker: Faker, session: Session) -> None:
        # Arrange
        # Of different sizes: swapped directions show up.
        sent = [faker.binary(length=faker.pyint(min_value=1, max_value=100)) for _ in range(3)]
        received = [faker.binary(length=faker.pyint(min_value=101, max_value=200)) for _ in range(3)]
        client = ScriptedStream(sent)
        target = ScriptedStream(received)
        relay = Relay(client, target, session, idle_timeout=TEST_TIMEOUT)

        # Act
        await relay.run()

        # Assert
        assert session.bytes_sent == sum(map(len, sent))
        assert session.bytes_received == sum(map(len, received))

    async def test_run_sets_session_error_when_grant_cuts(self, faker: Faker, session: Session) -> None:
        # Arrange
        grant = CuttingGrant()
        client = ScriptedStream([faker.binary(length=faker.pyint(min_value=1, max_value=100))])
        target = StalledStream()
        relay = Relay(client, target, session, idle_timeout=TEST_TIMEOUT, grants=[grant])

        # Act
        await asyncio.wait_for(relay.run(), timeout=TEST_TIMEOUT)

        # Assert
        assert session.error is grant.error

    async def test_run_drops_chunk_when_grant_cuts(self, faker: Faker, session: Session) -> None:
        # Arrange
        client = ScriptedStream([faker.binary(length=faker.pyint(min_value=1, max_value=100))])
        target = StalledStream()
        relay = Relay(client, target, session, idle_timeout=TEST_TIMEOUT, grants=[CuttingGrant()])

        # Act
        await asyncio.wait_for(relay.run(), timeout=TEST_TIMEOUT)

        # Assert
        # Over a quota, not a byte more reaches the target or the count.
        assert not target.written
        assert session.bytes_sent == 0

    async def test_run_records_timeout_when_nothing_moves_for_idle_timeout(self, session: Session) -> None:
        # Arrange
        relay = Relay(StalledStream(), StalledStream(), session, idle_timeout=IDLE_TIMEOUT)

        # Act
        await asyncio.wait_for(relay.run(), timeout=TEST_TIMEOUT)

        # Assert
        assert isinstance(session.error, TimeoutError)

    async def test_run_delivers_chunk_when_grant_holds_it_longer_than_idle_timeout(
        self,
        faker: Faker,
        session: Session,
    ) -> None:
        # Arrange
        data = faker.binary(length=faker.pyint(min_value=1, max_value=100))
        client = ScriptedStream([data])
        target = ScriptedStream()
        relay = Relay(client, target, session, idle_timeout=IDLE_TIMEOUT, grants=[HoldingGrant(HOLD_DELAY)])

        # Act
        await asyncio.wait_for(relay.run(), timeout=TEST_TIMEOUT)

        # Assert
        # A slow tunnel isn't an idle one.
        assert target.written == data

    async def test_run_records_reset_when_peer_resets(self, faker: Faker, session: Session) -> None:
        # Arrange
        error = ConnectionResetError()
        client = ScriptedStream(error=error)
        target = ScriptedStream([faker.binary(length=faker.pyint(min_value=1, max_value=100))])
        relay = Relay(client, target, session, idle_timeout=TEST_TIMEOUT)

        # Act
        await asyncio.wait_for(relay.run(), timeout=TEST_TIMEOUT)

        # Assert
        assert session.error is error

    async def test_timeout_raises_runtime_error_when_not_running(self, session: Session) -> None:
        # Arrange
        relay = Relay(ScriptedStream(), ScriptedStream(), session, idle_timeout=TEST_TIMEOUT)

        # Act & Assert
        with pytest.raises(RuntimeError):
            _ = relay.timeout
