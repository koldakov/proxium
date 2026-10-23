from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert

from proxium.db import session_manager
from proxium.policies import PeriodUsage
from proxium.proxy import Observer, Unmetered, Usage

from ._counts import Bytes, create_days, merge_days, to_usages

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.dialects.postgresql import Insert

    from proxium.db import BaseTrafficModel
    from proxium.proxy import Identity, Session

    from ._counts import Days, Owner
    from ._totals import TrafficTotals

logger = logging.getLogger(__name__)


class UntrackedIdentityError(Exception):
    """The identity has no owner with a traffic table, e.g. anonymous."""


class UntrackedSessionError(Exception):
    """The session has no owner with a traffic table, e.g. it was rejected or is anonymous."""


@dataclass(slots=True)
class _Tracked:
    """An open session and how much of it is already counted."""

    session: Session
    owner: Owner
    counted: Bytes

    def get_uncounted(self) -> Bytes:
        """Bytes the session moved since its last count."""
        return Bytes(
            sent=self.session.bytes_sent - self.counted.sent,
            received=self.session.bytes_received - self.counted.received,
        )


@dataclass(frozen=True, slots=True)
class _Row:
    """One upsert into a traffic table, whichever it is."""

    owner_id: int
    day: date
    bytes_sent: int
    bytes_received: int


# Rows to write, per table.
type _Rows = dict[type[BaseTrafficModel], list[_Row]]


class TrafficObserver(Observer, PeriodUsage):
    """Adds the bytes of every session to per-day traffic tables, written in batches every `flush_interval` seconds.

    Open tunnels are counted on every flush, so a long one lands on the days it actually ran.
    The owner comes from the identity claim named after `model.owner_column`, the first model that matches wins.
    A failed write is retried on the next flush.

    Tells quotas the usage since a day: what this process hasn't written yet, open tunnels included, plus what
    `totals` tells, e.g. the tables and other processes. `totals` is told of every write and asks for the unwritten
    bytes.

    Call `start` in the running loop before serving and `close` after the server shut down, to write the rest.
    """

    def __init__(
        self,
        models: Sequence[type[BaseTrafficModel]],
        /,
        *,
        totals: TrafficTotals,
        flush_interval: float = 60.0,
    ) -> None:
        self._models: tuple[type[BaseTrafficModel], ...] = tuple(models)
        self._totals: TrafficTotals = totals
        self._flush_interval: float = flush_interval
        # Per owner, by id: sessions are mutable dataclasses, not hashable.
        self._open: defaultdict[Owner, dict[int, _Tracked]] = defaultdict(dict)
        self._pending: Days = create_days()
        # The batch being written: not in the sums yet.
        self._writing: Days = create_days()
        # Set by `close`: a flush in progress finishes, never cut halfway.
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def _get_unwritten(self) -> dict[Owner, dict[date, Usage]]:
        """What this process hasn't written: pending, being written, and open tunnels since their last count."""
        unwritten = create_days()
        for counts in (self._pending, self._writing):
            merge_days(unwritten, counts)

        today = datetime.now(UTC).date()
        for owner, opened in self._open.items():
            for tracked in opened.values():
                unwritten[owner][today].add(tracked.get_uncounted())
        return to_usages(unwritten)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        self._totals.start(self._get_unwritten, flush_interval=self._flush_interval)

    async def close(self) -> None:
        """Stop flushing on schedule and write what's left. Sessions still open are counted up to now."""
        self._closing.set()
        await self._totals.close_reads()
        if self._task is not None:
            await self._task
        # Always: sessions closed while the last scheduled flush was writing aren't in it.
        await self._flush()

        if self._pending:
            logger.error("Traffic lost on shutdown: %s", self._describe_pending())

        await self._totals.close()

    def _get_owner(self, identity: Identity, /) -> Owner:
        for model in self._models:
            if model.owner_column in identity.claims:
                return model, identity.claims[model.owner_column]

        raise UntrackedIdentityError()

    def _track(self, session: Session, /) -> _Tracked:
        if session.request is None:
            raise UntrackedSessionError()

        try:
            owner = self._get_owner(session.request.identity)
        except UntrackedIdentityError as err:
            raise UntrackedSessionError() from err

        return _Tracked(
            session=session,
            owner=owner,
            counted=Bytes(),
        )

    async def on_open(self, session: Session, /) -> None:
        try:
            tracked = self._track(session)
        except UntrackedSessionError:
            return

        self._open[tracked.owner][id(session)] = tracked

    def _count(self, tracked: _Tracked, /) -> None:
        """Move the bytes not counted yet to the pending ones of today."""
        self._pending[tracked.owner][datetime.now(UTC).date()].add(tracked.get_uncounted())
        tracked.counted.sent = tracked.session.bytes_sent
        tracked.counted.received = tracked.session.bytes_received

    async def on_close(self, session: Session, /) -> None:
        try:
            tracked = self._track(session)
        except UntrackedSessionError:
            return

        opened = self._open.get(tracked.owner, {})
        # Never opened, but a request payload may have reached the target: counted from zero.
        tracked = opened.pop(id(session), tracked)
        if not opened:
            self._open.pop(tracked.owner, None)
        self._count(tracked)

    def _get_unwritten_since(self, owner: Owner, since: date, /) -> Bytes:
        """Bytes of this process since the day not written yet: pending, being written, or moved by open tunnels."""
        unwritten = Bytes()
        for counts in (self._pending, self._writing):
            # `get`: looking up mustn't add empty owners.
            days: Mapping[date, Bytes] = counts.get(owner, {})
            for day, counted in days.items():
                if day >= since:
                    unwritten.add(counted)

        # Open tunnels moved bytes since their last count, today's.
        for tracked in self._open.get(owner, {}).values():
            unwritten.add(tracked.get_uncounted())
        return unwritten

    async def used_since(self, identity: Identity, since: date, /) -> Usage:
        try:
            owner = self._get_owner(identity)
        except UntrackedIdentityError as err:
            raise Unmetered() from err

        totals = await self._totals.used_since(owner, since)
        unwritten = self._get_unwritten_since(owner, since)
        return Usage(
            sent=totals.sent + unwritten.sent,
            received=totals.received + unwritten.received,
        )

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._flush_interval)
            await self._flush()

    def _get_rows(self, batch: Days, /) -> _Rows:
        rows: _Rows = defaultdict(list)
        for (model, owner_id), days in batch.items():
            for day, counted in days.items():
                if counted.sent or counted.received:
                    rows[model].append(
                        _Row(
                            owner_id=owner_id,
                            day=day,
                            bytes_sent=counted.sent,
                            bytes_received=counted.received,
                        ),
                    )
        return rows

    async def _flush(self) -> None:
        for opened in self._open.values():
            for tracked in opened.values():
                self._count(tracked)

        # Taken before the write: sessions closing meanwhile count into a fresh batch.
        batch, self._pending = self._pending, create_days()
        rows = self._get_rows(batch)
        if not rows:
            return

        self._writing = batch
        try:
            await self._write(rows)
        except Exception:
            logger.exception("Can't write traffic, retrying on the next flush")
            merge_days(self._pending, batch)
            return
        finally:
            self._writing = create_days()

        # No await since the write: `totals` counts the batch before its first await, no quota misses it. It may wait
        # for a publish in progress, up to twice the Redis timeouts while Redis hangs: the write is done by then.
        await self._totals.add_written(to_usages(batch))

    async def _write(self, rows: _Rows, /) -> None:
        """All tables in one transaction: a failed batch is retried whole, never counted twice."""
        async with session_manager.session() as session:
            for model, model_rows in rows.items():
                await session.execute(
                    self._get_upsert_statement(model),
                    [self._get_row_values(model, row) for row in model_rows],
                )
            await session.commit()

    def _get_upsert_statement(self, model: type[BaseTrafficModel], /) -> Insert:
        statement = insert(model)
        return statement.on_conflict_do_update(
            index_elements=[model.owner_column, model.day],
            set_={
                model.bytes_sent: model.bytes_sent + statement.excluded.bytes_sent,
                model.bytes_received: model.bytes_received + statement.excluded.bytes_received,
            },
        )

    def _get_row_values(self, model: type[BaseTrafficModel], row: _Row, /) -> dict[str, object]:
        # The owner column is named by the table, so the row doesn't know it.
        return {
            model.owner_column: row.owner_id,
            "day": row.day,
            "bytes_sent": row.bytes_sent,
            "bytes_received": row.bytes_received,
        }

    def _describe_pending(self) -> str:
        return ", ".join(
            f"{model.__tablename__} #{owner_id} {day}: sent={counted.sent} received={counted.received}"
            for (model, owner_id), days in self._pending.items()
            for day, counted in days.items()
        )
