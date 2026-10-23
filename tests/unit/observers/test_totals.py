from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from proxium.db import BasicProxyAccountTrafficModel
from proxium.observers import SharedTraffic, SharedTrafficTotals
from proxium.proxy import Usage, UsageUnavailable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from faker import Faker

    from tests.fixtures.observers import FakeTrafficShare


def _get_share_key(owner_id: int, /) -> str:
    return f"{BasicProxyAccountTrafficModel.__tablename__}:{owner_id}"


def _add(*usages: Usage) -> Usage:
    return Usage(sent=sum(usage.sent for usage in usages), received=sum(usage.received for usage in usages))


class TestSharedTrafficTotals:
    def test_init_raises_value_error_when_lease_fits_fewer_than_three_syncs(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        sync_interval = faker.pyfloat(min_value=1.0, max_value=10.0)
        traffic_share.lease = sync_interval * 3 - 0.1

        # Act & Assert
        # Bytes of live processes would expire between their publishes.
        with pytest.raises(ValueError, match="three sync intervals"):
            SharedTrafficTotals(traffic_share, sync_interval=sync_interval)

    async def test_used_since_counts_bytes_other_processes_havent_written(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        unwritten = Usage(sent=faker.pyint(), received=faker.pyint())
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset({faker.uuid4()}),
            days={today: unwritten},
        )
        totals = SharedTrafficTotals(traffic_share)

        # Act
        # Sums of the database, whatever the tables hold. Read, never changed: a `Usage` stands for them.
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, written),
        ):
            usage = await totals.used_since((BasicProxyAccountTrafficModel, owner_id), today)

        # Assert
        assert usage == _add(written, unwritten)

    async def test_used_since_keeps_bytes_of_other_process_until_sums_include_them(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        process = faker.uuid4()
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset({process}),
            days={today: batch},
        )
        rereading = asyncio.Event()
        reread = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads == 1:
                return dict.fromkeys(keys, written)
            # Read again once the other process wrote the batch: held until the test lets it go.
            rereading.set()
            await reread.wait()
            return dict.fromkeys(keys, _add(written, batch))

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # The other process writes the batch: out of its unwritten bytes, into the database, a new version.
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=faker.uuid4(),
                processes=frozenset(),
                days={},
            )
            await rereading.wait()

            # Act
            while_reading = await totals.used_since(owner, today)
            reread.set()
            # Syncs go on meanwhile: two later, the read let go is done.
            await traffic_share.wait_reads(traffic_share.reads + 2)
            after_reading = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        # Never without the batch: the old sum goes with the old bytes, the new sum with the new ones.
        assert while_reading == _add(written, batch)
        assert after_reading == _add(written, batch)

    async def test_used_since_counts_batch_of_process_that_crashed_before_announcing_it(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        version = faker.uuid4()
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=version,
            processes=frozenset({faker.uuid4()}),
            days={today: batch},
        )
        # What the tables hold, the last one: changed by the test.
        sums = [written]
        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, sums[-1]),
        ):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # The process writes the batch and crashes before announcing it: the version stays, its bytes expire.
            sums.append(_add(written, batch))
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=version,
                processes=frozenset(),
                days={},
            )

            # Act
            # Two syncs started after the change: one of them read it whole.
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, batch)

    async def test_used_since_counts_batch_of_process_that_appeared_after_read_and_crashed_before_announcing_it(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        version = faker.uuid4()
        # No other process at the read.
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(version=version, processes=frozenset(), days={})
        sums = [written]
        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, sums[-1]),
        ):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # Another process gets traffic of the owner later.
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=version,
                processes=frozenset({faker.uuid4()}),
                days={today: batch},
            )
            await traffic_share.wait_reads(traffic_share.reads + 2)
            # It writes the batch and crashes before announcing it: the version stays, its bytes expire.
            sums.append(_add(written, batch))
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=version,
                processes=frozenset(),
                days={},
            )

            # Act
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, batch)

    async def test_used_since_counts_batch_written_and_announced_while_sync_was_away_longer_than_lease(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        traffic_share.lease = 0.05
        # No version: none written lately.
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(version=None, processes=frozenset(), days={})
        sums = [written]
        read_shared = traffic_share.read
        holding = False
        hanging = asyncio.Event()
        answered = asyncio.Event()

        async def read(owners: Sequence[str]) -> dict[str, SharedTraffic]:
            # Once held, a read of the sync hangs until the test lets it go, e.g. a stalled loop.
            if holding:
                hanging.set()
                await answered.wait()
            return await read_shared(owners)

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with (
            patch.object(
                SharedTrafficTotals,
                "_read_totals",
                new_callable=AsyncMock,
                side_effect=lambda keys: dict.fromkeys(keys, sums[-1]),
            ),
            patch.object(traffic_share, "read", new_callable=AsyncMock, side_effect=read),
        ):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            holding = True
            await hanging.wait()
            # Meanwhile a process writes a batch of the owner and announces it, and the version expires: the share
            # looks as it did.
            sums.append(_add(written, batch))
            await asyncio.sleep(traffic_share.lease * 2)
            answered.set()

            # Act
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, batch)

    async def test_used_since_counts_batch_written_and_announced_while_first_read_of_sum_was_longer_than_lease(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        traffic_share.lease = 0.05
        # No version: none written lately.
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(version=None, processes=frozenset(), days={})
        reading = asyncio.Event()
        answered = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads > 1:
                return dict.fromkeys(keys, _add(written, batch))
            # The first read answers late, with the sum as it was before the batch.
            reading.set()
            await answered.wait()
            return dict.fromkeys(keys, written)

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            first_check = asyncio.create_task(totals.used_since(owner, today))
            await reading.wait()
            # Meanwhile a process writes a batch of the owner and announces it, and the version expires: the share
            # looks as it did when the sum was asked for.
            await asyncio.sleep(traffic_share.lease * 2)
            answered.set()
            await first_check

            # Act
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, batch)

    async def test_used_since_counts_writes_of_other_processes_during_outage_once_share_is_back(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        written_during_outage = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        sums = [written]
        traffic_share.available = False
        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, sums[-1]),
        ):
            totals.start(dict, flush_interval=60.0)
            # Read while the share is down: no version, and none when it's back, every one expired.
            await totals.used_since(owner, today)
            await traffic_share.wait_reads(traffic_share.reads + 2)
            sums.append(_add(written, written_during_outage))

            # Act
            traffic_share.available = True
            # Publishes go through first, then a sync reads the share.
            await traffic_share.wait_attempts(traffic_share.attempts + 1)
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, written_during_outage)

    async def test_used_since_keeps_bytes_of_other_processes_when_share_fails(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        unwritten = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset({faker.uuid4()}),
            days={today: unwritten},
        )
        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, written),
        ):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)

            # Act
            # A blip: a sync fails, the next one may not.
            traffic_share.available = False
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        assert usage == _add(written, unwritten)

    async def test_publish_goes_on_while_database_hangs(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset(),
            days={},
        )
        rereading = asyncio.Event()
        # Never set: the database hangs on every read after the first.
        answered = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads > 1:
                rereading.set()
                await answered.wait()
            return dict.fromkeys(keys, Usage())

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # Another process wrote: the sum is read again, and the database hangs.
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=faker.uuid4(),
                processes=frozenset(),
                days={},
            )
            await rereading.wait()

            # Act & Assert
            # Held by the read, publishes would stop and this process's bytes expire in the share.
            await asyncio.wait_for(traffic_share.wait_attempts(traffic_share.attempts + 3), timeout=1.0)
            await totals.close()

    async def test_used_since_counts_shared_again_when_share_is_back_while_database_hangs(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        unwritten = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        process = faker.uuid4()
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset({process}),
            days={today: unwritten},
        )
        outage_timeout = 0.05
        rereading = asyncio.Event()
        # Never set: the database hangs on every read after the first.
        answered = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads > 1:
                rereading.set()
                await answered.wait()
            return dict.fromkeys(keys, written)

        totals = SharedTrafficTotals(
            traffic_share,
            sync_interval=0.001,
            outage_timeout=outage_timeout,
        )
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # Another process wrote: the sum is read again, and the database hangs.
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=faker.uuid4(),
                processes=frozenset({process}),
                days={today: unwritten},
            )
            await rereading.wait()
            # A blip: a publish fails, the share is down.
            traffic_share.available = False
            await traffic_share.wait_attempts(traffic_share.attempts + 1)
            traffic_share.available = True
            await traffic_share.wait_attempts(traffic_share.attempts + 1)
            await asyncio.sleep(outage_timeout * 2)

            # Act
            # Held down by the hanging read, quotas would be refused past the timeout though the share answers.
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        # Not refused, and the others' bytes counted: the old sum goes with them until it's read again.
        assert usage == _add(written, unwritten)

    async def test_used_since_counts_shared_again_when_share_is_back_while_database_hangs_after_outage(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        unwritten = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=faker.uuid4(),
            processes=frozenset({faker.uuid4()}),
            days={today: unwritten},
        )
        # Every sum is read again a flush interval after the share failed: there the database hangs.
        flush_interval = 0.05
        outage_timeout = flush_interval * 4
        rereading = asyncio.Event()
        # Never set: the database hangs on every read after the first.
        answered = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads > 1:
                rereading.set()
                await answered.wait()
            return dict.fromkeys(keys, written)

        totals = SharedTrafficTotals(
            traffic_share,
            sync_interval=0.001,
            outage_timeout=outage_timeout,
        )
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=flush_interval)
            await totals.used_since(owner, today)
            # Down whole: reads and publishes fail, the sync counts alone.
            traffic_share.available = False
            # Asked for meanwhile, the sum isn't dropped as unused before it's read again.
            while not rereading.is_set():
                await totals.used_since(owner, today)
                await asyncio.sleep(flush_interval / 10)
            traffic_share.available = True
            await traffic_share.wait_attempts(traffic_share.attempts + 1)
            await asyncio.sleep(outage_timeout * 2)

            # Act
            # The read of every sum started in the outage hangs: the others' bytes, kept through it, aren't dropped.
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        # Not refused, and the others' bytes counted: the old sum goes with them until it's read again.
        assert usage == _add(written, unwritten)

    async def test_used_since_raises_usage_unavailable_when_share_down_longer_than_timeout(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        traffic_share.available = False
        outage_timeout = 0.01
        totals = SharedTrafficTotals(
            traffic_share,
            sync_interval=0.001,
            outage_timeout=outage_timeout,
        )

        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, Usage()),
        ):
            totals.start(dict, flush_interval=60.0)
            # A failed sync marks the share down, the next one starts after it.
            await traffic_share.wait_attempts(2)
            await asyncio.sleep(outage_timeout * 2)

            # Act & Assert
            with pytest.raises(UsageUnavailable):
                await totals.used_since(owner, today)
            await totals.close()

    async def test_used_since_keeps_own_batch_until_sums_include_it(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner = (BasicProxyAccountTrafficModel, faker.pyint(min_value=1))
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        rereading = asyncio.Event()
        reread = asyncio.Event()
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads == 1:
                return dict.fromkeys(keys, written)
            # Read again once this process wrote the batch: held until the test lets it go.
            rereading.set()
            await reread.wait()
            return dict.fromkeys(keys, _add(written, batch))

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            await totals.add_written({owner: {today: batch}})
            await rereading.wait()

            # Act
            while_reading = await totals.used_since(owner, today)
            reread.set()
            await traffic_share.wait_reads(traffic_share.reads + 2)
            after_reading = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        # Never without the batch: the old sum goes with it, the new sum has it.
        assert while_reading == _add(written, batch)
        assert after_reading == _add(written, batch)

    async def test_publish_announces_written_batch_after_share_failed(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        today = datetime.now(UTC).date()
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        traffic_share.available = False
        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        totals.start(dict, flush_interval=60.0)
        await totals.add_written({(BasicProxyAccountTrafficModel, owner_id): {today: batch}})
        # A publish fails with the batch written: it must stay to be announced.
        await traffic_share.wait_attempts(traffic_share.attempts + 1)

        # Act
        traffic_share.available = True
        await traffic_share.wait_attempts(traffic_share.attempts + 1)
        await totals.close()

        # Assert
        # Lost, the others would keep the sums without the batch and stop counting it as unwritten.
        assert _get_share_key(owner_id) in traffic_share.announced[0]

    async def test_used_since_counts_new_bytes_of_other_processes_while_database_is_away(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        owner = (BasicProxyAccountTrafficModel, owner_id)
        today = datetime.now(UTC).date()
        written = Usage(sent=faker.pyint(), received=faker.pyint())
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        unwritten = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        version, process = faker.uuid4(), faker.uuid4()
        traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
            version=version,
            processes=frozenset({process}),
            days={},
        )
        # Past it, sums not checked would be read again: checks must go on without the database.
        traffic_share.lease = 0.05
        reads = 0

        async def read_totals(keys: Sequence[tuple[object, ...]]) -> dict[tuple[object, ...], Usage]:
            nonlocal reads
            reads += 1
            if reads > 1:
                # The database is away from the first read on.
                raise ConnectionError()
            return dict.fromkeys(keys, written)

        totals = SharedTrafficTotals(traffic_share, sync_interval=0.001)
        with patch.object(SharedTrafficTotals, "_read_totals", new_callable=AsyncMock, side_effect=read_totals):
            totals.start(dict, flush_interval=60.0)
            await totals.used_since(owner, today)
            # A write of this process makes the sum stale: read again, it fails.
            await totals.add_written({owner: {today: batch}})
            # The other process can't write either: its bytes grow, the version stays.
            traffic_share.shared[_get_share_key(owner_id)] = SharedTraffic(
                version=version,
                processes=frozenset({process}),
                days={today: unwritten},
            )
            await asyncio.sleep(traffic_share.lease * 2)

            # Act
            await traffic_share.wait_reads(traffic_share.reads + 2)
            usage = await totals.used_since(owner, today)
            await totals.close()

        # Assert
        # Frozen at the last read, quotas would count this process alone while the database is away.
        assert usage == _add(written, batch, unwritten)

    async def test_add_written_keeps_batch_to_announce_when_publish_fails_unexpectedly(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner_id = faker.pyint(min_value=1)
        batch = Usage(sent=faker.pyint(min_value=1), received=faker.pyint(min_value=1))
        # Loops that don't run within the test: only the announce and the last publish do.
        totals = SharedTrafficTotals(traffic_share, sync_interval=traffic_share.lease / 3)
        totals.start(dict, flush_interval=60.0)

        # Act
        # A bug, not an outage: raised, it would end the writes of `TrafficObserver`.
        with patch.object(traffic_share, "publish", side_effect=RuntimeError()):
            await totals.add_written({(BasicProxyAccountTrafficModel, owner_id): {datetime.now(UTC).date(): batch}})
        await totals.close()

        # Assert
        assert _get_share_key(owner_id) in traffic_share.announced[0]

    async def test_used_since_doesnt_wait_for_share_for_new_owner_after_failed_read(
        self,
        faker: Faker,
        traffic_share: FakeTrafficShare,
    ) -> None:
        # Arrange
        owner = (BasicProxyAccountTrafficModel, faker.unique.pyint(min_value=1))
        other_owner = (BasicProxyAccountTrafficModel, faker.unique.pyint(min_value=1))
        today = datetime.now(UTC).date()
        # Failing, not marked down yet: no sync ran.
        traffic_share.available = False
        totals = SharedTrafficTotals(traffic_share)
        with patch.object(
            SharedTrafficTotals,
            "_read_totals",
            new_callable=AsyncMock,
            side_effect=lambda keys: dict.fromkeys(keys, Usage()),
        ):
            await totals.used_since(owner, today)
            reads = traffic_share.reads

            # Act
            await totals.used_since(other_owner, today)

        # Assert
        # Asked again, every new client would wait for the Redis timeouts until a sync marks it down.
        assert traffic_share.reads == reads
