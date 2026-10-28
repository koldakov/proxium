from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from sqlalchemy import BigInteger, Date, Integer, and_, cast, column, func, select, values

from proxium.core import TRAFFIC_SYNC_INTERVAL, proxy_settings
from proxium.db import session_manager
from proxium.proxy import Usage, UsageUnavailable

from ._counts import Bytes, create_days, merge_days, merge_usages
from ._shares import SharedTraffic, TrafficShareUnavailable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
    from datetime import date

    from sqlalchemy import Select

    from proxium.db import BaseTrafficModel

    from ._counts import Days, Owner
    from ._shares import TrafficShare

logger = logging.getLogger(__name__)

# What a process hasn't written yet, per owner and UTC day.
type Unwritten = Mapping[Owner, Mapping[date, Usage]]
# A sum in the database: the owner's bytes since a day.
type _TotalKey = tuple[type[BaseTrafficModel], int, date]

# Of an owner whose others' bytes can't be read: no version, nor processes. The next sync the share answers reads its
# sums again if the owner has a version there; without one, no process announced a write within a lease, and with no
# process gone the sums are taken as read.
_NOTHING_SHARED: Final[SharedTraffic] = SharedTraffic(version=None, processes=frozenset(), days={})


def _get_key_owner(key: _TotalKey, /) -> Owner:
    return key[0], key[1]


def get_share_key(owner: Owner, /) -> str:
    """The owner's name in the share, e.g. `basic_proxy_account_traffic:42`: readers outside the proxy use it too."""
    model, owner_id = owner
    return f"{model.__tablename__}:{owner_id}"


async def _cancel(task: asyncio.Task[None], /) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@dataclass(frozen=True, slots=True)
class _Seen:
    """The others' bytes of an owner, and when the read that got them started, by `time.monotonic`."""

    traffic: SharedTraffic
    read_at: float


@dataclass(frozen=True, slots=True)
class _Started:
    """What `start` tells: the unwritten bytes of this process, and how often processes write them."""

    unwritten: Callable[[], Unwritten]
    flush_interval: float


@dataclass(slots=True)
class _Total:
    """An owner's bytes since a day as read from the database, the version and processes of the others' traffic
    read before it, when it was last checked against them, by the start of that read, and when a quota last asked
    for it.
    """

    written: Bytes
    version: str | None
    processes: frozenset[str]
    checked_at: float
    used_at: float


class TrafficTotals(ABC):
    """What quotas count besides the bytes this process hasn't written yet: the traffic tables, and whatever else
    tells, e.g. other processes. One per `TrafficObserver`, which writes the tables and calls it.
    """

    @abstractmethod
    def start(self, unwritten: Callable[[], Unwritten], /, *, flush_interval: float) -> None:
        """Start in the running loop. `unwritten` tells the bytes this process hasn't written yet, open sessions
        included, a copy on every call. Processes write every `flush_interval` seconds, this one and the others.
        """

    @abstractmethod
    async def close_reads(self) -> None:
        """Stop reading, before the last write: a hanging database mustn't hold the shutdown. Safe to call twice."""

    @abstractmethod
    async def close(self) -> None:
        """Stop, after the last write. Calls `close_reads` first."""

    @abstractmethod
    async def add_written(self, batch: Unwritten, /) -> None:
        """A batch of this process was just written. Counted before the first await: no quota misses it."""

    @abstractmethod
    async def used_since(self, owner: Owner, since: date, /) -> Usage:
        """Bytes of `owner` since the UTC day, but the ones this process hasn't written. Raise `UsageUnavailable` if
        they can't be told now.
        """


class _ShareHealth:
    """Whether the share answers, by what publishes and reads of the others' bytes tell: down once either fails, back
    once both go through, whichever loop sees it last. Down, quotas count alone for `outage_timeout` seconds. `on_down`
    and `on_back` run on the change.

    A read on a connection's way doesn't tell: one slow answer mustn't take every quota off the share. A failed one
    only keeps new owners off the share for `lazy_pause` seconds, or until a read of a sync goes through: else each
    would wait for the timeouts.
    """

    def __init__(
        self,
        *,
        outage_timeout: float,
        lazy_pause: float,
        on_down: Callable[[], None],
        on_back: Callable[[], None],
    ) -> None:
        self._outage_timeout: float = outage_timeout
        self._lazy_pause: float = lazy_pause
        self._on_down: Callable[[], None] = on_down
        self._on_back: Callable[[], None] = on_back
        # When the share failed, by `time.monotonic`. None while it answers.
        self._down_since: float | None = None
        # The last publish failed: a share that answers reads but refuses writes, e.g. a full Redis, is still down.
        self._publish_failed: bool = False
        # The last read of the others' bytes failed.
        self._read_failed: bool = False
        # Till then, by `time.monotonic`, new owners don't wait for the share.
        self._lazy_off_until: float = 0.0

    @property
    def down(self) -> bool:
        return self._down_since is not None

    def is_past_timeout(self) -> bool:
        return self._down_since is not None and time.monotonic() - self._down_since > self._outage_timeout

    def lazy_reads_allowed(self) -> bool:
        return self._down_since is None and time.monotonic() >= self._lazy_off_until

    def _mark_down(self) -> None:
        """Logs the error being handled the first time."""
        if self._down_since is not None:
            return

        self._down_since = time.monotonic()
        logger.error(
            "Can't share traffic with other processes, quotas count this process alone for %s s",
            self._outage_timeout,
            exc_info=True,
        )
        self._on_down()

    def _mark_up(self) -> None:
        if self._down_since is None or self._publish_failed or self._read_failed:
            return

        logger.info("Traffic is shared with other processes again")
        self._down_since = None
        self._on_back()

    def fail_publish(self) -> None:
        """Call while handling the error: it's logged once the share goes down."""
        self._publish_failed = True
        self._mark_down()

    def pass_publish(self) -> None:
        self._publish_failed = False
        self._mark_up()

    def fail_read(self) -> None:
        """Call while handling the error: it's logged once the share goes down."""
        self._read_failed = True
        self._mark_down()

    def pass_read(self) -> None:
        self._read_failed = False
        # It answers: new owners may read it again.
        self._lazy_off_until = 0.0
        self._mark_up()

    def fail_lazy_read(self) -> None:
        """Call while handling the error: logged once for reads failing at once."""
        now = time.monotonic()
        if now >= self._lazy_off_until:
            logger.warning(
                "Can't read traffic of other processes for a new client, counted from the next sync",
                exc_info=True,
            )
        self._lazy_off_until = now + self._lazy_pause


class SharedTrafficTotals(TrafficTotals):
    """The sums in the tables and what other processes haven't written yet, from `share`.

    Every `sync_interval` seconds, and right after each write, this process publishes its unwritten bytes there,
    never held by a slow database: they'd expire. Every `sync_interval` it reads the others' too: their traffic
    counts within about two intervals. A sum is read once, at most `read_chunk_size` per query, and again once some
    process wrote bytes of its owner, apart from the syncs: a slow database holds only the owners read again, the
    others' bytes of the rest stay fresh. Sums and the others' bytes change together: a byte moving from one to the
    other is never missed, at most counted twice for a moment. Only if the share fails to answer the first read of an
    owner, the others' bytes of it count from the next sync. Processes write every `flush_interval` seconds: a sum no
    quota asked for that long is dropped, checked once per `flush_interval`.

    If the share fails, this process counts alone: the others' bytes as last read, and every sum read again once per
    `flush_interval`, when their writes are in the database, without their bytes from then on. After `outage_timeout`
    seconds it refuses quotas with `UsageUnavailable` until the share is back, tried every `sync_interval`. Open
    tunnels are cut too, on their next check: unlike a connection count, traffic over a quota grows as long as they
    run, and can't be taken back. Once the share is back, every sum is read again.

    Invariants every change must keep:

    - A written batch of this process is always in `_unread` or `_rereading` until the sums of its owner have it: no
      await between taking it out of one and storing the other, or the new sums.
    - The others' bytes of an owner change only together with its sums: new bytes with old sums may miss a write.
    - A sum keeps the version and processes seen before its read: a read of the share comes first, then the database.
    - Bytes published leave the share only with a new version, in one transaction: see `TrafficShare.publish`.
    - One publish at a time, and a failed or cancelled one puts back what it was announcing.
    - One read of sums again at a time, and no sum dropped meanwhile: it stores into them, `_rereading` is its own.
    - An owner the share shows written for stays so until its sums are read again: no sync takes its new bytes before.
    """

    def __init__(
        self,
        share: TrafficShare,
        /,
        *,
        sync_interval: float = TRAFFIC_SYNC_INTERVAL,
        outage_timeout: float = proxy_settings.redis_outage_timeout,
        read_chunk_size: int = 500,
    ) -> None:
        # Three publishes fit in a lease, as renewals of connections do: else bytes of live processes expire between
        # them, and quotas miss them without a word. `Settings` checks PROXY_CONNECTION_LEASE against the default,
        # TRAFFIC_SYNC_INTERVAL, with the Redis timeouts on top.
        if share.lease < 3 * sync_interval:
            raise ValueError(f"The lease of {share.lease} s is shorter than three sync intervals of {sync_interval} s.")

        self._share: TrafficShare = share
        self._sync_interval: float = sync_interval
        self._read_chunk_size: int = read_chunk_size
        self._health: _ShareHealth = _ShareHealth(
            outage_timeout=outage_timeout,
            lazy_pause=sync_interval,
            on_down=self._on_share_down,
            on_back=self._on_share_back,
        )
        # Given by `start`: None before, nothing tells the unwritten bytes nor how often they're written.
        self._started: _Started | None = None
        # When the sums no quota uses were dropped last, by `time.monotonic`.
        self._pruned_at: float = 0.0
        # Batches written since the sums of their owner were last read: not in them either.
        self._unread: Days = create_days()
        # Unread batches of the sums being read again: counted until the new sums have them.
        self._rereading: Days = create_days()
        # Batches written but not announced in the share yet: the others still see them as unwritten.
        self._unannounced: Days = create_days()
        # One publish at a time: an older one finishing last would put back bytes already announced as written.
        self._publishing: asyncio.Lock = asyncio.Lock()
        self._totals: dict[_TotalKey, _Total] = {}
        # The keys of `_totals` by owner: looking one owner up mustn't go through every sum.
        self._keys_by_owner: defaultdict[Owner, set[_TotalKey]] = defaultdict(set)
        # Reads in progress, so quotas asking for the same sum at once share one.
        self._reading: dict[_TotalKey, asyncio.Task[Bytes]] = {}
        # Unwritten bytes of other processes, for owners of the sums.
        self._shared: dict[Owner, _Seen] = {}
        # Owners whose sums are read again on the next sync whatever the share says, e.g. once it's back.
        self._forced: set[Owner] = set()
        # Changes whenever every owner is forced: a read started before keeps them forced.
        self._forced_generation: int = 0
        # While the share is down: when every sum is read again next, by `time.monotonic`.
        self._reread_all_at: float = 0.0
        # The last read of sums by a sync failed: logged once, not every sync while the database is away.
        self._reread_failed: bool = False
        # Unchecked sums were logged: once, not every sync while they stay so.
        self._unchecked_logged: bool = False
        # Publishes apart from syncs: a sync waits for the database, and a hanging one mustn't let this process's
        # bytes expire in the share.
        self._publish_task: asyncio.Task[None] | None = None
        self._sync_task: asyncio.Task[None] | None = None
        # Sums read again apart from syncs: a hanging database mustn't freeze the others' bytes of every owner.
        self._reread_task: asyncio.Task[None] | None = None

    def _get_started(self) -> _Started:
        """Raise `RuntimeError` before `start`: guessing instead, e.g. publishing nothing, would hide bytes."""
        if self._started is None:
            raise RuntimeError("Call `start` first: it tells the unwritten bytes and how often they're written.")
        return self._started

    def _on_share_down(self) -> None:
        """The others' bytes as last read stay: dropped now, quotas would miss them on any blip of the share. Every
        sum is read again a flush interval on: the others have written what they had by then, the sums show it. Past
        the outage timeout quotas are refused anyway: with the defaults, 30 s under a minute, this matters only for a
        longer timeout.
        """
        self._reread_all_at = time.monotonic() + self._get_started().flush_interval

    async def _read_shared(self, owners: Collection[Owner], /) -> dict[Owner, SharedTraffic]:
        """What other processes haven't written for `owners`. Raise `TrafficShareUnavailable` if the share fails."""
        by_key = {get_share_key(owner): owner for owner in owners}
        shared = await self._share.read(list(by_key))
        return {by_key[key]: traffic for key, traffic in shared.items()}

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

    async def _read_totals(self, keys: Sequence[_TotalKey], /) -> dict[_TotalKey, Bytes]:
        by_model: defaultdict[type[BaseTrafficModel], list[tuple[int, date]]] = defaultdict(list)
        for model, owner_id, since in keys:
            by_model[model].append((owner_id, since))

        totals: dict[_TotalKey, Bytes] = {}
        async with session_manager.session() as session:
            for model, model_keys in by_model.items():
                for start in range(0, len(model_keys), self._read_chunk_size):
                    chunk = model_keys[start : start + self._read_chunk_size]
                    result = await session.execute(self._get_totals_statement(model, chunk))
                    for owner_id, since, sent, received in result.tuples():
                        totals[model, owner_id, since] = Bytes(sent=sent, received=received)
        return totals

    async def _read_shared_once(self, owner: Owner, /) -> _Seen:
        """The others' bytes of `owner`, read first if they aren't yet. Raise `TrafficShareUnavailable` if they can't
        be: while the share is down, on a failed read, or for a sync interval after one. Whether it's down is the
        call of the sync, not of one slow answer on a connection's way.
        """
        with contextlib.suppress(KeyError):
            return self._shared[owner]
        if not self._health.lazy_reads_allowed():
            raise TrafficShareUnavailable()

        started = time.monotonic()
        try:
            shared = await self._read_shared([owner])
        except TrafficShareUnavailable:
            self._health.fail_lazy_read()
            raise
        seen = _Seen(traffic=shared[owner], read_at=started)
        # Kept only for an owner without sums: its sums go with the bytes of the next sync, newer bytes would lack
        # what moved meanwhile. The first of reads at once is kept: older than the sums they read after it, it may
        # count bytes twice, never miss them. Down meanwhile, what was read may go stale without a word.
        if not self._health.down and owner not in self._keys_by_owner:
            self._shared.setdefault(owner, seen)
        return seen

    async def _read_fresh_total(self, key: _TotalKey, /) -> _Total:
        # The others' bytes before the sum: once their version or processes change, the sum may lack what was written.
        started = time.monotonic()
        try:
            seen = await self._read_shared_once(_get_key_owner(key))
        except TrafficShareUnavailable:
            # Logged by `_ShareHealth`. Checked by the next sync the share answers, see `_NOTHING_SHARED`.
            seen = _Seen(traffic=_NOTHING_SHARED, read_at=started)
        totals = await self._read_totals([key])
        return _Total(
            written=totals[key],
            version=seen.traffic.version,
            processes=seen.traffic.processes,
            checked_at=seen.read_at,
            used_at=time.monotonic(),
        )

    async def _read_total(self, key: _TotalKey, /) -> Bytes:
        # Reading until stored: a quota asking in between would start a read of its own.
        try:
            total = await self._read_fresh_total(key)
        finally:
            del self._reading[key]

        self._totals[key] = total
        self._keys_by_owner[_get_key_owner(key)].add(key)
        return total.written

    @staticmethod
    def _retrieve_error(task: asyncio.Task[Bytes], /) -> None:
        # Quotas still waiting report the error, ones that gave up have no one to report it to.
        if not task.cancelled():
            task.exception()

    async def _wait_total(self, key: _TotalKey, /) -> Bytes:
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

    async def _get_written(self, owner: Owner, since: date, /) -> Bytes:
        key = (*owner, since)
        try:
            total = self._totals[key]
        except KeyError:
            return await self._wait_total(key)

        total.used_at = time.monotonic()
        return total.written

    def _get_unread(self, owner: Owner, since: date, /) -> Bytes:
        """Bytes of this process since the day written after the last read sums."""
        unread = Bytes()
        for counts in (self._unread, self._rereading):
            # `get`: looking up mustn't add empty owners.
            days: Mapping[date, Bytes] = counts.get(owner, {})
            for day, counted in days.items():
                if day >= since:
                    unread.add(counted)
        return unread

    def _get_shared(self, owner: Owner, since: date, /) -> Bytes:
        """Bytes of other processes since the day they haven't written yet."""
        shared = Bytes()
        try:
            seen = self._shared[owner]
        except KeyError:
            return shared

        for day, usage in seen.traffic.days.items():
            if day >= since:
                shared.sent += usage.sent
                shared.received += usage.received
        return shared

    async def used_since(self, owner: Owner, since: date, /) -> Usage:
        if self._health.is_past_timeout():
            raise UsageUnavailable()

        written = await self._get_written(owner, since)
        unread = self._get_unread(owner, since)
        shared = self._get_shared(owner, since)
        return Usage(
            sent=written.sent + unread.sent + shared.sent,
            received=written.received + unread.received + shared.received,
        )

    def _get_unwritten(self) -> Unwritten:
        return self._get_started().unwritten()

    def _get_published(self) -> dict[str, Mapping[date, Usage]]:
        """The unwritten bytes. Written ones aren't, even unannounced: each publish announces all of them at once, see
        `_publish`.
        """
        return {get_share_key(owner): owner_days for owner, owner_days in self._get_unwritten().items()}

    async def _publish(self) -> None:
        """Publish the unwritten bytes and announce the written ones. Raise `TrafficShareUnavailable` if the share
        fails.
        """
        async with self._publishing:
            # Taken before: batches written meanwhile are still in the bytes published now, announced next time.
            announcing, self._unannounced = self._unannounced, create_days()
            try:
                await self._share.publish(
                    self._get_published(),
                    written=[get_share_key(owner) for owner in announcing],
                )
            except BaseException:
                # Failed or cancelled: announced next time. Lost, the others would miss these bytes until another
                # write.
                merge_days(self._unannounced, announcing)
                raise

    async def _announce(self) -> None:
        """Announce a batch right after its write: until then, others reading the sums count it twice.

        While the share is down, the next publish announces it once the share is back. A process that stops before,
        or that only loses the share while the others still reach it and stops, never does: the others miss the
        batch until a process writes bytes of the same owner, theirs included, within about `flush_interval` for a
        client still under a quota there.
        """
        # Down, every attempt would wait for the timeouts: the next publish tries.
        if self._health.down:
            return

        try:
            await self._publish()
        except TrafficShareUnavailable:
            logger.warning("Can't announce written traffic, retrying on the next publish", exc_info=True)
        # A bug mustn't stop the writes: `TrafficObserver` waits for this after each one, an error would end its
        # loop. What it was announcing goes back, the next publish tries.
        except Exception:
            logger.exception("Can't announce written traffic, retrying on the next publish")

    async def add_written(self, batch: Unwritten, /) -> None:
        merge_usages(self._unread, batch)
        merge_usages(self._unannounced, batch)
        await self._announce()

    def _prune_totals(self) -> None:
        """Drop the sums no quota asked for within `flush_interval`, and what goes with them: memory stays bounded by
        the owners in use. Once per `flush_interval`, not every sync: it walks every sum. Unused, one lives up to twice
        that.
        """
        flush_interval = self._get_started().flush_interval
        now = time.monotonic()
        if now < self._pruned_at + flush_interval:
            return

        self._pruned_at = now
        cutoff = now - flush_interval
        self._totals = {key: total for key, total in self._totals.items() if total.used_at >= cutoff}
        self._keys_by_owner = defaultdict(set)
        for key in self._totals:
            self._keys_by_owner[_get_key_owner(key)].add(key)
        in_use = self._keys_by_owner.keys() | {_get_key_owner(key) for key in self._reading}
        # Later reads include the written batches. Not of owners read now: a read started before a write lacks it.
        for owner in self._unread.keys() - in_use:
            del self._unread[owner]
        self._shared = {owner: shared for owner, shared in self._shared.items() if owner in in_use}
        self._forced &= in_use

    def _is_changed(self, key: _TotalKey, total: _Total, shared: Mapping[Owner, SharedTraffic], /) -> bool:
        """Whether other processes may have written bytes the sum lacks, by `shared` just read."""
        owner = _get_key_owner(key)
        if owner in self._forced:
            return True
        # Read meanwhile, after the others' bytes: its own read tells.
        if owner not in shared:
            return False
        # A process gone, e.g. crashed between its write and the announce: its written bytes left with it. A version
        # gone too: expired after a client idle for a lease, it changes nothing, but a version seen changing and then
        # expiring while the database was away looks the same, and the sum lacks that write. So the owner keeps the
        # others' bytes as last read until the database is back: less counted for a while, never more.
        return shared[owner].version != total.version or not total.processes <= shared[owner].processes

    async def _reread_totals(self, owners: Collection[Owner], /) -> set[Owner]:
        """Read again every sum of `owners`, all of an owner at once: its unread batches are dropped only once all of
        its sums include them. Not of owners read now: a read started before a write lacks it, they're read next time.
        Return the owners read. Raise the error of the database, the unread batches kept.
        """
        rereading = set(owners) - {_get_key_owner(key) for key in self._reading}
        keys = [key for owner in rereading for key in self._keys_by_owner.get(owner, ())]
        if not keys:
            return set()

        generation = self._forced_generation
        # Before the read: batches written meanwhile stay unread, the sums may or may not have them. Counted in
        # `_rereading` meanwhile: the old sums lack them.
        self._rereading = create_days()
        for owner in rereading & self._unread.keys():
            self._rereading[owner] = self._unread.pop(owner)
        try:
            totals = await self._read_totals(keys)
        except BaseException:
            merge_days(self._unread, self._rereading)
            raise
        finally:
            # No await until the new sums are stored: no quota sees the batches missing from both.
            self._rereading = create_days()

        for key, written in totals.items():
            self._totals[key].written = written
        # Forced again meanwhile, e.g. the share came back: this read started before.
        if generation == self._forced_generation:
            self._forced -= rereading
        return rereading

    def _get_unchecked(self) -> set[Owner]:
        """Owners with a sum not checked against the others' bytes for about a lease, e.g. a read of sums held by the
        database, or syncs by a stalled loop: a version or a process may have come and gone unseen, and with it a
        write the sum lacks. A sync interval spare: what's published expires by the clock of the share.
        """
        cutoff = time.monotonic() - (self._share.lease - self._sync_interval)
        unchecked = {_get_key_owner(key) for key, total in self._totals.items() if total.checked_at <= cutoff}
        # Forced ones are read again anyway, e.g. once the share is back: not a sign of slow syncs.
        unchecked -= self._forced
        # Read again, they're slower still: seen in the log before every sync reads every sum. Once until there are
        # none: while the database is away they stay unchecked.
        if unchecked and not self._unchecked_logged:
            logger.warning(
                "Traffic of other processes went unchecked for about %s s for %d owners, e.g. reads of sums held by "
                "the database: their sums are read again",
                self._share.lease,
                len(unchecked),
            )
        self._unchecked_logged = bool(unchecked)
        return unchecked

    async def _reread_or_log(self, owners: Collection[Owner], /) -> set[Owner]:
        """`_reread_totals`, its error logged instead: once until a read goes through. None read if it fails, the
        next sync tries again.
        """
        try:
            reread = await self._reread_totals(owners)
        except Exception:
            if not self._reread_failed:
                logger.exception(
                    "Can't read traffic sums for quotas, retrying every %s s. Later errors aren't logged until it "
                    "reads them again",
                    self._sync_interval,
                )
            self._reread_failed = True
            return set()

        if self._reread_failed:
            logger.info("Traffic sums for quotas are read again")
            self._reread_failed = False
        return reread

    def _take_unchanged(
        self,
        owners: Collection[Owner],
        shared: Mapping[Owner, SharedTraffic],
        read_at: float,
        /,
    ) -> None:
        """Take the others' bytes of `owners`, whose sums lack no write of others, from `shared` read by a read started
        at `read_at`. Ones stale only by writes of this process too, even if not read again, e.g. while the database
        is away: its batches stay counted unread.
        """
        for owner in owners:
            self._shared[owner] = _Seen(traffic=shared[owner], read_at=read_at)
            for key in self._keys_by_owner.get(owner, ()):
                total = self._totals[key]
                total.checked_at = read_at
                # Every process seen since the sum was read: one that appeared later may write and crash too. Added,
                # not replaced: a sum read meanwhile may have seen processes this read hasn't.
                total.processes |= shared[owner].processes

    def _take_reread(
        self,
        owners: Collection[Owner],
        shared: Mapping[Owner, SharedTraffic],
        read_at: float,
        /,
    ) -> None:
        """Take the others' bytes of `owners`, whose sums were read again after `shared`, read by a read started at
        `read_at`, with its versions and processes.
        """
        for owner in owners:
            self._shared[owner] = _Seen(traffic=shared[owner], read_at=read_at)
            for key in self._keys_by_owner.get(owner, ()):
                total = self._totals[key]
                total.checked_at = read_at
                total.version = shared[owner].version
                total.processes = shared[owner].processes

    def _is_rereading(self) -> bool:
        return self._reread_task is not None and not self._reread_task.done()

    async def _run_reread(self, reread: Callable[[], Awaitable[None]], /) -> None:
        # A callable, not a coroutine: a task cancelled before its first step would leave one never awaited.
        # A bug mustn't go unseen in a task no one awaits. The next sync starts another read.
        try:
            await reread()
        except Exception:
            logger.exception("Can't read traffic sums again, retrying in %s s", self._sync_interval)

    async def _reread_shared(
        self,
        owners: Collection[Owner],
        changed: set[Owner],
        shared: Mapping[Owner, SharedTraffic],
        read_at: float,
        /,
    ) -> None:
        """Read again the sums of `owners`, then take `shared` for the ones `changed`, see `_refresh_totals`: new bytes
        of others with old sums would miss what they wrote meanwhile. Changed owners not read again keep the old
        bytes: they go with the old sums.
        """
        reread = await self._reread_or_log(owners)
        self._take_reread(reread & changed & shared.keys(), shared, read_at)

    def _refresh_totals(self, shared: Mapping[Owner, SharedTraffic], read_at: float, /) -> None:
        """Take `shared`, just read by a read started at `read_at`, for the owners no process wrote bytes for since
        their sums. Start a read of the others' sums again, unless one is in progress, and take `shared` for them once
        it's done. A failed read keeps the old sums, the batches written since counted on top.
        """
        changed = {_get_key_owner(key) for key, total in self._totals.items() if self._is_changed(key, total, shared)}
        changed |= self._get_unchecked()
        # At once, not after the sums: a hanging database mustn't freeze the others' bytes of every owner.
        self._take_unchanged(shared.keys() - changed, shared, read_at)

        # Changed owners stay so until read again: their version, processes or check are as before.
        if self._is_rereading():
            return
        # Stale by writes of this process too: read again so that its unread batches can go.
        stale = changed | (self._keys_by_owner.keys() & self._unread.keys())
        if stale:
            self._reread_task = asyncio.create_task(
                self._run_reread(functools.partial(self._reread_shared, stale, changed, shared, read_at)),
            )

    def _force_all(self) -> None:
        """Read every sum again on the next sync whatever the share says."""
        self._forced = set(self._keys_by_owner)
        self._forced_generation += 1

    def _on_share_back(self) -> None:
        """Versions and processes may have come and gone unseen meanwhile, e.g. all expired in a long outage: every sum
        is read again. Until then, sums keep the others' bytes they go with.
        """
        self._force_all()

    async def _reread_alone(self, owners: Collection[Owner], forced: set[Owner], /) -> None:
        """Read again the sums of `owners`, then count the ones `forced` alone."""
        reread = await self._reread_or_log(owners)

        # Back meanwhile: the others' bytes stay until these owners are read again by the share, with sums read
        # while it was down they may only count twice.
        if not self._health.down:
            return

        # Sums read all at once have what the others wrote by then: from now on counted alone. Read for a write of
        # this process, they keep the others' bytes, maybe counted twice: a blip of the share mustn't make quotas
        # miss them.
        for owner in reread & forced:
            self._shared.pop(owner, None)

    def _refresh_totals_alone(self) -> None:
        """While the share is down: read again the sums this process wrote bytes for, and every sum once per
        `flush_interval`. Versions stay: no write of others was seen, and when the share is back every sum is read
        again.
        """
        # The others' writes show up only in the database meanwhile.
        if time.monotonic() >= self._reread_all_at:
            self._reread_all_at = time.monotonic() + self._get_started().flush_interval
            self._force_all()
        # Forced ones stay so for the next read.
        if self._is_rereading():
            return
        forced = set(self._forced)
        stale = self._keys_by_owner.keys() & (self._unread.keys() | forced)
        if stale:
            self._reread_task = asyncio.create_task(
                self._run_reread(functools.partial(self._reread_alone, stale, forced)),
            )

    async def _publish_and_report(self) -> None:
        try:
            await self._publish()
        except TrafficShareUnavailable:
            self._health.fail_publish()
            return

        self._health.pass_publish()

    async def _run_publish(self) -> None:
        # Not stopped by `close_reads`: `close` cancels it once the last write is done, so the bytes don't expire
        # meanwhile. Cancelled mid-publish, what it announced goes back for the last publish.
        while True:
            await asyncio.sleep(self._sync_interval)
            try:
                await self._publish_and_report()
            # A bug mustn't end the loop. The share is down for this process all the same: its bytes expire there, so
            # it counts alone, as the others do it.
            except Exception:
                # Logged with its traceback by `_ShareHealth` the first time, here while the share stays down: a bug,
                # unlike an outage, is logged every time.
                if self._health.down:
                    logger.exception("Can't publish traffic, retrying in %s s", self._sync_interval)
                self._health.fail_publish()

    async def _sync(self) -> None:
        # Not while sums are read again: the read stores into what it'd drop.
        if not self._is_rereading():
            self._prune_totals()
        started = time.monotonic()
        try:
            shared = await self._read_shared(self._keys_by_owner.keys())
        except TrafficShareUnavailable:
            self._health.fail_read()
            self._refresh_totals_alone()
            return

        self._health.pass_read()
        # Down until publishes go through too: the others don't see this process meanwhile.
        if self._health.down:
            self._refresh_totals_alone()
            return

        self._refresh_totals(shared, started)

    async def _run_sync(self) -> None:
        # Stopped by `close_reads`.
        while True:
            await asyncio.sleep(self._sync_interval)
            # A bug mustn't end the loop: quotas would stop seeing other processes without a word.
            try:
                await self._sync()
            except Exception:
                logger.exception("Can't sync traffic, retrying in %s s", self._sync_interval)

    def start(self, unwritten: Callable[[], Unwritten], /, *, flush_interval: float) -> None:
        self._started = _Started(unwritten=unwritten, flush_interval=flush_interval)
        self._publish_task = asyncio.create_task(self._run_publish())
        self._sync_task = asyncio.create_task(self._run_sync())

    async def close_reads(self) -> None:
        # Cut a sync first, then a read of sums in progress: what it took goes back, and no sync starts another.
        if self._sync_task is not None:
            await _cancel(self._sync_task)
        if self._reread_task is not None:
            await _cancel(self._reread_task)

    async def close(self) -> None:
        """Then publish once more, unless the last write announced it all: the others stop counting what was
        written. Never started, nothing was published.
        """
        if self._publish_task is None:
            return

        await self.close_reads()
        # Only now: publishes renew the bytes in the share while the last writes wait for the database. Stopped
        # before, the bytes would expire for the others before they're in the sums.
        await _cancel(self._publish_task)

        # Announced by the last write, and nothing left: the share holds nothing of this process.
        if not self._get_unwritten() and not self._unannounced:
            return

        # Down, it would wait for the timeouts of the share: the others count alone already. Writes they haven't
        # seen announced reach them once a process writes bytes of the same owners, see `_announce`.
        if self._health.down:
            logger.warning("Can't publish the last traffic, the share is down")
            return

        try:
            await self._publish()
        except TrafficShareUnavailable:
            logger.warning("Can't publish the last traffic, other processes count it twice until it expires")
        # A bug mustn't stop the shutdown: what's closed after, e.g. connection leases, would stay open.
        except Exception:
            logger.exception("Can't publish the last traffic, other processes count it twice until it expires")
