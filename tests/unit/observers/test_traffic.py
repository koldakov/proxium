from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from proxium.db import BasicProxyAccountTrafficModel
from proxium.observers import SharedTrafficTotals, TrafficObserver
from proxium.proxy import Identity, Usage

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session
    from tests.fixtures.observers import FakeTrafficShare


class TestTrafficObserver:
    async def test_used_since_adds_unwritten_bytes_to_totals(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
        session_factory: Callable[[], Session],
        proxy_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        claims = {BasicProxyAccountTrafficModel.owner_column: owner_id}
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        session = session_factory()
        session.request = proxy_request_factory(claims=claims)
        session.bytes_sent = faker.pyint(min_value=1)
        session.bytes_received = faker.pyint(min_value=1)
        observer = TrafficObserver([BasicProxyAccountTrafficModel], totals=SharedTrafficTotals(traffic_share))
        # Closed, not written yet: pending.
        await observer.on_close(session)

        # Act
        # Sums of the database, whatever the tables hold. Read, never changed: a `Usage` stands for them.
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, written),
        ):
            usage = await observer.used_since(Identity(subject=str(owner_id), claims=claims), datetime.now(UTC).date())

        # Assert
        assert usage == Usage(
            sent=written.sent + session.bytes_sent,
            received=written.received + session.bytes_received,
        )

    async def test_close_goes_on_publishing_while_last_write_waits_for_database(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
        session_factory: Callable[[], Session],
        proxy_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        session = session_factory()
        session.request = proxy_request_factory(
            claims={BasicProxyAccountTrafficModel.owner_column: faker.pyint(min_value=1)},
        )
        session.bytes_sent = faker.pyint(min_value=1)
        session.bytes_received = faker.pyint(min_value=1)
        writing = asyncio.Event()
        written = asyncio.Event()

        async def write(rows: object) -> None:
            writing.set()
            await written.wait()

        observer = TrafficObserver(
            [BasicProxyAccountTrafficModel],
            totals=SharedTrafficTotals(traffic_share, sync_interval=0.001),
        )
        await observer.on_close(session)

        with patch.object(TrafficObserver, "_write", new_callable=AsyncMock, side_effect=write):
            observer.start()
            closing = asyncio.create_task(observer.close())
            await writing.wait()

            # Act & Assert
            # Stopped before the write, the bytes would expire for the others before they're in the sums.
            await asyncio.wait_for(traffic_share.wait_attempts(traffic_share.attempts + 3), timeout=1.0)
            written.set()
            await closing
