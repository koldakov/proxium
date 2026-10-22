from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import OutOfMemoryError, ReadOnlyError, RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from proxium.core import proxy_settings
from proxium.db import redis_manager
from proxium.proxy import Direction, MemorySpeedBucket, SpeedBucket

if TYPE_CHECKING:
    from collections.abc import Hashable

    from redis.commands.core import AsyncScript

logger = logging.getLogger(__name__)

# KEYS[1]: the bucket of one limit key and direction. ARGV: the rate in bytes per second, the burst, the batch.
# Takes the batch at once, in debt if the bucket hasn't got it, and returns the microseconds until the debt is paid:
# the caller waits that long, then spends it. One round trip per batch, and instances queue in the order their takes
# reach Redis. Refilled by Redis time: the clocks of instances don't matter. A new bucket is full. The key lives until
# the bucket is full again: then it's no different from a new one. The TTL goes as a string: a number may be
# formatted as 1e+08, which PEXPIRE refuses. Edited terms cap the debt at one burst of the new ones: taken by the old
# terms, it would hold the client back for long, e.g. 12.5 MB of 1 Gbit/s paid by 1 Mbit/s for 100 s. Capped, not
# forgiven: instances see an edit up to PROXY_SETTINGS_POLL_INTERVAL apart, and each forgiving the others' debt
# would let each of them through as if alone. Not exact either: with a batch as big as the burst, e.g. a small burst
# at a high rate, the debt of several instances is over a burst, and the cap drops some of it while they see the edit.
# With the shebang Redis checks memory before running it: a full Redis refuses with OOM, an outage, not with an error
# of the script.
_TAKE: Final[str] = """#!lua
local now = redis.call('TIME')
local ms = tonumber(now[1]) * 1000 + tonumber(now[2]) / 1000
local rate = tonumber(ARGV[1]) / 1000
local burst = tonumber(ARGV[2])
local batch = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at', 'rate', 'burst')
local tokens = burst
if state[1] then
    tokens = math.min(burst, tonumber(state[1]) + math.max(0, ms - tonumber(state[2])) * rate)
    if state[3] ~= ARGV[1] or state[4] ~= ARGV[2] then
        tokens = math.max(-burst, tokens)
    end
end
tokens = tokens - batch
redis.call('HSET', KEYS[1], 'tokens', tokens, 'at', ms, 'rate', ARGV[1], 'burst', ARGV[2])
redis.call('PEXPIRE', KEYS[1], string.format('%.0f', math.ceil((burst - tokens) / rate) + 1))
return math.ceil(math.max(0, -tokens) * 1000 / rate)
"""

# Redis can't be used now: down, hanging, full or a replica after a failover. Other errors are of one call, e.g. of
# the script for a key: they mustn't take every key off Redis.
_OUTAGE_ERRORS: Final[tuple[type[RedisError], ...]] = (
    RedisConnectionError,
    RedisTimeoutError,
    OutOfMemoryError,
    ReadOnlyError,
)

_DIRECTION_NAMES: Final[dict[Direction, str]] = {
    Direction.SENT: "sent",
    Direction.RECEIVED: "received",
}


@dataclass(slots=True)
class _Batch:
    """What this process has of one Redis bucket: bytes left of the batch it took, and its connections."""

    tokens: float = 0.0
    # The terms `tokens` were taken by: left of a batch of another rate, they'd let a whole old batch through.
    rate: float = 0.0
    burst: float = 0.0
    connections: int = 0
    # When it may ask Redis again after an error of its own, by `time.monotonic`. Meanwhile it's limited here.
    retry_at: float = 0.0
    # One take at a time per bucket: connections waiting for bytes share it, in turn.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RedisSpeedBatches:
    """Bytes this process takes from speed limit buckets in Redis, `batch` seconds of the rate at a time, and spends
    on its connections. One round trip per batch, so each process may go over a limit by one batch.

    If Redis fails, it's left alone and checked every `probe_interval` seconds by a take of a bucket of its own: a
    write, as the buckets need, so a full Redis that answers PING but refuses writes stays down. Meanwhile each
    process limits its own connections, so with N processes a key may get up to N times the rate. Once Redis takes
    the probe, or answers it with an error other than an outage, the buckets are shared again. Other errors, e.g. of
    the script for a key or of permissions, leave the key alone for `probe_interval` the same way, logged at most once
    per interval.

    One per process, shared by its `RedisSpeedBucket`s. Call `start` in the running loop before serving and `close`
    after the server shut down.
    """

    def __init__(
        self,
        *,
        batch: float = proxy_settings.speed_batch,
        probe_interval: float = 1.0,
    ) -> None:
        if batch <= 0:
            raise ValueError("The batch must be positive.")

        self._batch: float = batch
        self._probe_interval: float = probe_interval
        # Per Redis key, only keys with open connections: memory is bounded by them.
        self._batches: dict[str, _Batch] = {}
        # While Redis is down, by the same keys.
        self._local: MemorySpeedBucket = MemorySpeedBucket()
        self._take_script: AsyncScript = redis_manager.client.register_script(_TAKE)
        self._probe_key: str = redis_manager.key("limit:speed:probe")
        self._down: bool = False
        # When an error of a key was logged last, by `time.monotonic`: one that breaks every key would flood the log.
        self._error_logged_at: float = -math.inf
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def _probe(self) -> None:
        # A byte a second: the bucket is gone within seconds, one per instance probing at once, nothing to clean up.
        try:
            await self._take_script(keys=[self._probe_key], args=[1.0, 1, 1])
        except _OUTAGE_ERRORS:
            return
        except RedisError as err:
            # It answers, only refuses the call, e.g. NOPERM in the ACL: not down. Kept down, the process would count
            # alone for good without a word. The keys handle such errors themselves, logged once a second.
            logger.warning("Redis answers the check with an error, speed limits go back to it: %s", err)

        logger.info("Redis is back, speed limits are shared again")
        self._down = False

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._probe_interval)
            if self._closing.is_set() or not self._down:
                continue

            # A bug mustn't end the loop: speed limits would stay unshared without a word.
            try:
                await self._probe()
            except Exception:
                logger.exception("Can't check Redis, retrying in %s s", self._probe_interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop checking Redis. Bytes left of the batches are dropped: buckets refill on their own."""
        self._closing.set()
        if self._task is None:
            return

        # Cut a check in progress: a hanging Redis mustn't hold the shutdown.
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    def open_key(self, key: str, /) -> None:
        try:
            batch = self._batches[key]
        except KeyError:
            batch = self._batches[key] = _Batch()
        batch.connections += 1
        self._local.open(key)

    def close_key(self, key: str, /) -> None:
        batch = self._batches[key]
        batch.connections -= 1
        # Bytes left of the batch go with it: at most one batch, the bucket refills anyway.
        if not batch.connections:
            del self._batches[key]
        self._local.close(key)

    def _mark_down(self, error: RedisError, /) -> None:
        if not self._down:
            self._down = True
            logger.error("Redis failed, speed limits are counted in this process alone: %s", error)

    async def _refill(self, key: str, batch: _Batch, /, *, rate: float, burst: float) -> None:
        """Take a batch for `key` and wait until the bucket has paid it. One connection of the key at a time, the
        others wait for its batch. An outage marks Redis down, other errors of Redis are raised.
        """
        # Whole bytes, at least one and at most the burst: more never fits the bucket.
        size = max(1, math.floor(min(rate * self._batch, burst)))
        async with batch.lock:
            # Another connection may have taken one meanwhile, or failed: then the key waits out `retry_at`.
            if batch.tokens > 0 or self._down or time.monotonic() < batch.retry_at:
                return

            try:
                wait_us = await self._take_script(keys=[key], args=[rate, burst, size])
            except _OUTAGE_ERRORS as err:
                self._mark_down(err)
                return

            # Under the lock: the other connections of the key wait for this batch. Cancelled meanwhile, it's lost:
            # the client gets less, never more.
            await asyncio.sleep(wait_us / 1_000_000)
            # Kept even if the terms changed meanwhile: at most one old batch, once. Dropped, this call would take
            # batches forever.
            batch.tokens += size

    def _log_key_error(self, key: str, /) -> None:
        """Log the error being handled, unless one was logged within `probe_interval`."""
        now = time.monotonic()
        if now - self._error_logged_at < self._probe_interval:
            return

        self._error_logged_at = now
        logger.exception(
            "Can't take bytes of %s from Redis, it's limited in this process for %s s. Other such errors in that time "
            "aren't logged",
            key,
            self._probe_interval,
        )

    async def take(self, key: str, direction: Direction, n: int, /, *, rate: float, burst: float) -> None:
        """Wait until `n` bytes of `key` fit the bucket, see `SpeedBucket.take`."""
        batch = self._batches[key]
        # The limit was edited: what's left was taken by the old terms, e.g. 12.5 MB of 1 Gbit/s cut to 1 Mbit/s.
        # Dropped, the client gets less, at most one batch: the shared bucket refills by the new terms.
        if (batch.rate, batch.burst) != (rate, burst):
            batch.tokens = 0.0
            batch.rate = rate
            batch.burst = burst
        remaining: float = n
        # Closed meanwhile, e.g. by the other direction switching rules: its state is gone, nothing to wait for.
        while remaining > 0 and batch.connections:
            # While Redis is down or failed for this key, it isn't asked: every chunk would wait for its timeout or
            # fail again.
            if self._down or time.monotonic() < batch.retry_at:
                await self._local.take(key, direction, math.ceil(remaining), rate=rate, burst=burst)
                return

            if batch.tokens <= 0:
                try:
                    await self._refill(key, batch, rate=rate, burst=burst)
                except RedisError:
                    # Not an outage, e.g. the script fails for this key, or every key, as when permissions are
                    # taken away: other keys go on in Redis, this one tries again after `probe_interval`. The loop
                    # limits it here, unless it was closed while the script ran.
                    batch.retry_at = time.monotonic() + self._probe_interval
                    self._log_key_error(key)
                continue

            spent = min(batch.tokens, remaining)
            batch.tokens -= spent
            remaining -= spent


class RedisSpeedBucket(SpeedBucket):
    """In Redis: the instances sharing it share the rate, in one round trip per batch of `batches`.

    Keys of the limit live under `name`, e.g. its id: a limit edited under the same name keeps its buckets. Rates and
    bursts in whole bytes, as the database keeps them: a burst under a byte never passes.
    """

    def __init__(self, name: str, /, *, batches: RedisSpeedBatches) -> None:
        self._name: str = name
        self._batches: RedisSpeedBatches = batches
        self._connections: Counter[Hashable] = Counter()
        # Built once per key, not on every chunk. Only keys with open connections: memory is bounded by them.
        self._redis_keys: dict[Hashable, dict[Direction, str]] = {}

    def _get_redis_key(self, key: Hashable, direction: Direction, /) -> str:
        # None, e.g. of the global scope, as empty: no other key of a scope is.
        return redis_manager.key(
            f"limit:speed:{self._name}:{_DIRECTION_NAMES[direction]}:{'' if key is None else key}",
        )

    def open(self, key: Hashable, /) -> None:
        if not self._connections[key]:
            self._redis_keys[key] = {direction: self._get_redis_key(key, direction) for direction in _DIRECTION_NAMES}
        self._connections[key] += 1
        for redis_key in self._redis_keys[key].values():
            self._batches.open_key(redis_key)

    def close(self, key: Hashable, /) -> None:
        for redis_key in self._redis_keys[key].values():
            self._batches.close_key(redis_key)
        self._connections[key] -= 1
        if not self._connections[key]:
            del self._connections[key]
            del self._redis_keys[key]

    async def take(self, key: Hashable, direction: Direction, n: int, /, *, rate: float, burst: float) -> None:
        await self._batches.take(self._redis_keys[key][direction], direction, n, rate=rate, burst=burst)
