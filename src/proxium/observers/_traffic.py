from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, Integer, and_, cast, column, func, select, values
from sqlalchemy.dialects.postgresql import insert

from proxium.db import session_manager
from proxium.policies import PeriodUsage
from proxium.proxy import Observer, Unmetered, Usage, UsageUnavailable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import Select
    from sqlalchemy.dialects.postgresql import Insert

    from proxium.db import BaseTrafficModel
    from proxium.proxy import Identity, Session

logger = logging.getLogger(__name__)


class UntrackedIdentityError(Exception):
    """The identity has no owner with a traffic table, e.g. anonymous."""


class UntrackedSessionError(Exception):
    """The session has no owner with a traffic table, e.g. it was rejected or is anonymous."""


@dataclass(slots=True)
class _Bytes:
    sent: int = 0
    received: int = 0

    def add(self, other: _Bytes, /) -> None:
        self.sent += other.sent
        self.received += other.received


# Whose traffic: the table and the owner's id in it.
type _Owner = tuple[type[BaseTrafficModel], int]
# Counted bytes per owner and UTC day.
type _Days = defaultdict[_Owner, defaultdict[date, _Bytes]]
# A sum in the database: the owner's bytes since a day.
type _TotalKey = tuple[type[BaseTrafficModel], int, date]


def _create_days() -> _Days:
    return defaultdict(lambda: defaultdict(_Bytes))


def _merge(target: _Days, source: _Days, /) -> None:
    for owner, days in source.items():
        for day, counted in days.items():
            target[owner][day].add(counted)


@dataclass(slots=True)
class _Tracked:
    """An open session and how much of it is already counted."""

    session: Session
    owner: _Owner
    counted: _Bytes


@dataclass(slots=True)
class _Total:
    """An owner's bytes since a day as read from the database, and when a quota last asked for them."""

    written: _Bytes
    used_at: float


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

    Tells quotas the usage since a day: the sum in the tables plus what this process hasn't written yet, open
    tunnels included. A sum is read once, at most `read_chunk_size` per query, and again after every flush while
    quotas ask for it: traffic of other processes shows up within `flush_interval`.

    Call `start` in the running loop before serving and `close` after the server shut down, to write the rest.
    """

    def __init__(
        self,
        models: Sequence[type[BaseTrafficModel]],
        /,
        *,
        flush_interval: float = 60.0,
        read_chunk_size: int = 500,
    ) -> None:
        self._models: tuple[type[BaseTrafficModel], ...] = tuple(models)
        self._flush_interval: float = flush_interval
        self._read_chunk_size: int = read_chunk_size
        # Per owner, by id: sessions are mutable dataclasses, not hashable.
        self._open: defaultdict[_Owner, dict[int, _Tracked]] = defaultdict(dict)
        self._pending: _Days = _create_days()
        # The batch being written: not in the sums yet.
        self._writing: _Days = _create_days()
        # Batches written since the sums were last read: not in them either.
        self._unread: _Days = _create_days()
        self._totals: dict[_TotalKey, _Total] = {}
        # Reads in progress, so quotas asking for the same sum at once share one.
        self._reading: dict[_TotalKey, asyncio.Task[_Bytes]] = {}
        self._refreshed_at: float = time.monotonic()
        # Set by `close`: a flush in progress finishes, never cut halfway.
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop flushing on schedule and write what's left. Sessions still open are counted up to now."""
        self._closing.set()
        if self._task is not None:
            await self._task
        # Always: sessions closed while the last scheduled flush was writing aren't in it.
        await self._flush()

        if self._pending:
            logger.error("Traffic lost on shutdown: %s", self._describe_pending())

    def _get_owner(self, identity: Identity, /) -> _Owner:
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
            counted=_Bytes(),
        )

    async def on_open(self, session: Session, /) -> None:
        try:
            tracked = self._track(session)
        except UntrackedSessionError:
            return

        self._open[tracked.owner][id(session)] = tracked

    def _count(self, tracked: _Tracked, /) -> None:
        """Move the bytes not counted yet to the pending ones of today."""
        pending = self._pending[tracked.owner][datetime.now(UTC).date()]
        pending.sent += tracked.session.bytes_sent - tracked.counted.sent
        pending.received += tracked.session.bytes_received - tracked.counted.received
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

    def _get_totals_statement(
        self,
        model: type[BaseTrafficModel],
        keys: Sequence[tuple[int, date]],
        /,
    ) -> Select[tuple[int, date, int, int]]:
        """Bytes of each owner since its day, zero for owners without traffic. Sums of bigint are numeric: cast."""
        requested = values(
            column("owner_id", Integer()),
            column("since", Date()),
            name="requested",
        ).data(list(keys))
        return (
            select(
                requested.c.owner_id,
                requested.c.since,
                cast(func.coalesce(func.sum(model.bytes_sent), 0), BigInteger()),
                cast(func.coalesce(func.sum(model.bytes_received), 0), BigInteger()),
            )
            .select_from(requested)
            .outerjoin(
                model,
                and_(
                    getattr(model, model.owner_column) == requested.c.owner_id,
                    model.day >= requested.c.since,
                ),
            )
            .group_by(requested.c.owner_id, requested.c.since)
        )

    async def _read_totals(self, keys: Sequence[_TotalKey], /) -> dict[_TotalKey, _Bytes]:
        by_model: defaultdict[type[BaseTrafficModel], list[tuple[int, date]]] = defaultdict(list)
        for model, owner_id, since in keys:
            by_model[model].append((owner_id, since))

        totals: dict[_TotalKey, _Bytes] = {}
        async with session_manager.session() as session:
            for model, model_keys in by_model.items():
                for start in range(0, len(model_keys), self._read_chunk_size):
                    chunk = model_keys[start : start + self._read_chunk_size]
                    result = await session.execute(self._get_totals_statement(model, chunk))
                    for owner_id, since, sent, received in result.tuples():
                        totals[model, owner_id, since] = _Bytes(sent=sent, received=received)
        return totals

    async def _read_total(self, key: _TotalKey, /) -> _Bytes:
        # Reading until stored: a quota asking in between would start a read of its own.
        try:
            totals = await self._read_totals([key])
        finally:
            del self._reading[key]

        self._totals[key] = _Total(written=totals[key], used_at=time.monotonic())
        return totals[key]

    @staticmethod
    def _retrieve_error(task: asyncio.Task[_Bytes], /) -> None:
        # Quotas still waiting report the error, ones that gave up have no one to report it to.
        if not task.cancelled():
            task.exception()

    async def _wait_total(self, key: _TotalKey, /) -> _Bytes:
        try:
            task = self._reading[key]
        except KeyError:
            task = asyncio.create_task(self._read_total(key))
            task.add_done_callback(self._retrieve_error)
            self._reading[key] = task

        # Not `await task`: a connection that gives up doesn't cancel the others' read.
        await asyncio.wait([task])
        error = task.exception()
        if error is not None:
            raise UsageUnavailable() from error
        return task.result()

    async def _get_written(self, owner: _Owner, since: date, /) -> _Bytes:
        key = (*owner, since)
        try:
            total = self._totals[key]
        except KeyError:
            return await self._wait_total(key)

        total.used_at = time.monotonic()
        return total.written

    def _get_unread(self, owner: _Owner, since: date, /) -> _Bytes:
        """Bytes since the day that the last read sums lack: not written yet, being written, or written after."""
        unread = _Bytes()
        for counts in (self._pending, self._writing, self._unread):
            # `get`: looking up mustn't add empty owners.
            days: Mapping[date, _Bytes] = counts.get(owner, {})
            for day, counted in days.items():
                if day >= since:
                    unread.add(counted)

        # Open tunnels moved bytes since their last count, today's.
        for tracked in self._open.get(owner, {}).values():
            unread.sent += tracked.session.bytes_sent - tracked.counted.sent
            unread.received += tracked.session.bytes_received - tracked.counted.received
        return unread

    async def used_since(self, identity: Identity, since: date, /) -> Usage:
        try:
            owner = self._get_owner(identity)
        except UntrackedIdentityError as err:
            raise Unmetered() from err

        written = await self._get_written(owner, since)
        unread = self._get_unread(owner, since)
        return Usage(
            sent=written.sent + unread.sent,
            received=written.received + unread.received,
        )

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._flush_interval)
            await self._flush()

    async def _refresh_totals(self) -> None:
        """Read again the sums quotas asked for since the last refresh, drop the rest: memory stays bounded by the
        owners in use. A failed read keeps the old sums with the batches written since counted on top.
        """
        cutoff, self._refreshed_at = self._refreshed_at, time.monotonic()
        self._totals = {key: total for key, total in self._totals.items() if total.used_at >= cutoff}
        if not self._totals:
            # Sums read later include every written batch.
            self._unread = _create_days()
            return

        try:
            totals = await self._read_totals(list(self._totals))
        except Exception:
            logger.exception("Can't read traffic sums for quotas, retrying on the next flush")
            return

        # Only refreshes drop sums, so every one read is still there.
        for key, written in totals.items():
            self._totals[key].written = written
        self._unread = _create_days()

    def _get_rows(self, batch: _Days, /) -> _Rows:
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
        batch, self._pending = self._pending, _create_days()
        rows = self._get_rows(batch)
        if rows:
            self._writing = batch
            try:
                await self._write(rows)
            except Exception:
                logger.exception("Can't write traffic, retrying on the next flush")
                _merge(self._pending, batch)
            else:
                _merge(self._unread, batch)
            finally:
                self._writing = _create_days()

        await self._refresh_totals()

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
