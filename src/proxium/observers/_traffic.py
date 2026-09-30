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
from proxium.proxy import Observer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.dialects.postgresql import Insert

    from proxium.db import BaseTrafficModel
    from proxium.proxy import Session

logger = logging.getLogger(__name__)


class UntrackedSessionError(Exception):
    """The session has no owner with a traffic table, e.g. it was rejected or is anonymous."""


@dataclass(slots=True)
class _Bytes:
    sent: int = 0
    received: int = 0


@dataclass(slots=True)
class _Tracked:
    """An open session and how much of it is already counted."""

    session: Session
    model: type[BaseTrafficModel]
    owner_id: int
    counted: _Bytes


@dataclass(frozen=True, slots=True)
class _Row:
    """One upsert into a traffic table, whichever it is."""

    owner_id: int
    day: date
    bytes_sent: int
    bytes_received: int


# Where counted bytes go: the table, the owner and the UTC day.
type _Key = tuple[type[BaseTrafficModel], int, date]
# Rows to write, per table.
type _Rows = dict[type[BaseTrafficModel], list[_Row]]


class TrafficObserver(Observer):
    """Adds the bytes of every session to per-day traffic tables, written in batches every `flush_interval` seconds.

    Open tunnels are counted on every flush, so a long one lands on the days it actually ran.
    The owner comes from the identity claim named after `model.owner_column`, the first model that matches wins.
    A failed write is retried on the next flush.

    Call `start` in the running loop before serving and `close` after the server shut down, to write the rest.
    """

    def __init__(
        self,
        models: Sequence[type[BaseTrafficModel]],
        /,
        *,
        flush_interval: float = 60.0,
    ) -> None:
        self._models: tuple[type[BaseTrafficModel], ...] = tuple(models)
        self._flush_interval: float = flush_interval
        # By id: sessions are mutable dataclasses, not hashable.
        self._open: dict[int, _Tracked] = {}
        self._pending: defaultdict[_Key, _Bytes] = defaultdict(_Bytes)
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

    async def on_open(self, session: Session, /) -> None:
        try:
            tracked = self._track(session)
        except UntrackedSessionError:
            return

        self._open[id(session)] = tracked

    async def on_close(self, session: Session, /) -> None:
        try:
            tracked = self._open.pop(id(session))
        except KeyError:
            # Never opened, but a request payload may have reached the target.
            try:
                tracked = self._track(session)
            except UntrackedSessionError:
                return

        self._count(tracked)

    def _track(self, session: Session, /) -> _Tracked:
        if session.request is None:
            raise UntrackedSessionError()

        claims = session.request.identity.claims
        for model in self._models:
            if model.owner_column in claims:
                return _Tracked(
                    session=session,
                    model=model,
                    owner_id=claims[model.owner_column],
                    counted=_Bytes(),
                )

        raise UntrackedSessionError()

    def _count(self, tracked: _Tracked, /) -> None:
        """Move the bytes not counted yet to the pending ones of today."""
        key = (tracked.model, tracked.owner_id, datetime.now(UTC).date())
        pending = self._pending[key]
        pending.sent += tracked.session.bytes_sent - tracked.counted.sent
        pending.received += tracked.session.bytes_received - tracked.counted.received
        tracked.counted.sent = tracked.session.bytes_sent
        tracked.counted.received = tracked.session.bytes_received

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        for tracked in self._open.values():
            self._count(tracked)

        # Taken before the write: sessions closing meanwhile count into a fresh batch.
        batch, self._pending = self._pending, defaultdict(_Bytes)
        rows: _Rows = defaultdict(list)
        for (model, owner_id, day), pending in batch.items():
            if pending.sent or pending.received:
                rows[model].append(
                    _Row(
                        owner_id=owner_id,
                        day=day,
                        bytes_sent=pending.sent,
                        bytes_received=pending.received,
                    ),
                )

        if not rows:
            return

        try:
            await self._write(rows)
        except Exception:
            logger.exception("Can't write traffic, retrying on the next flush")
            for key, pending in batch.items():
                self._pending[key].sent += pending.sent
                self._pending[key].received += pending.received

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
            f"{model.__tablename__} #{owner_id} {day}: sent={pending.sent} received={pending.received}"
            for (model, owner_id, day), pending in self._pending.items()
        )
