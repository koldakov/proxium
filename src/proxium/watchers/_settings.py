from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Result, Select, select

from proxium.db import SettingsModel, session_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from proxium.proxy import IPNetwork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheTtlsSnapshot:
    """Seconds the proxy reuses each kind of check: passed ones and refusals of every client kind, the certificate."""

    basic_account: float
    basic_account_refusal: float
    token_account: float
    token_account_refusal: float
    trusted_network: float
    trusted_network_refusal: float
    certificate: float


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """The settings row at one moment, detached from the database. Equal snapshots mean nothing changed."""

    guard_allow: tuple[IPNetwork, ...]
    handshake_timeout: float
    idle_timeout: float
    connect_timeout: float
    cache_ttls: CacheTtlsSnapshot


type SettingsCallback = Callable[[SettingsSnapshot], Awaitable[None]]


class SettingsNotLoadedError(Exception):
    """`start` was called before `load`: there are no applied settings to compare changes with."""


class SettingsWatcher:
    """Looks up the settings every `interval` seconds and calls `on_change` when they differ from the last applied.

    Call `load` before serving: the proxy must not start on guesses, so it raises if the settings can't be applied.
    Then `start` in the running loop, and `close` before the server shuts down.
    A failed lookup or `on_change` is logged and the old settings stay, the next lookup retries.
    """

    def __init__(
        self,
        on_change: SettingsCallback,
        /,
        *,
        interval: float = 5.0,
    ) -> None:
        self._on_change: SettingsCallback = on_change
        self._interval: float = interval
        self._current: SettingsSnapshot | None = None
        self._closing: asyncio.Event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def _get_settings_statement(self) -> Select[tuple[SettingsModel]]:
        return select(SettingsModel)

    async def load(self) -> None:
        """Read and apply the current settings by `on_change`, raising if either fails."""
        snapshot = await self._read()
        await self._on_change(snapshot)
        self._current = snapshot

    def start(self) -> None:
        if self._current is None:
            raise SettingsNotLoadedError()

        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop looking up. A change being applied finishes, never cut halfway."""
        self._closing.set()
        if self._task is not None:
            await self._task

    async def _read(self) -> SettingsSnapshot:
        async with session_manager.session() as session:
            result: Result[tuple[SettingsModel]] = await session.execute(self._get_settings_statement)
            # The migration adds the only row: none is a broken database.
            settings: SettingsModel = result.scalars().one()

        return SettingsSnapshot(
            guard_allow=tuple(settings.guard_allow),
            handshake_timeout=settings.handshake_timeout,
            idle_timeout=settings.idle_timeout,
            connect_timeout=settings.connect_timeout,
            cache_ttls=CacheTtlsSnapshot(
                basic_account=settings.basic_account_cache_ttl,
                basic_account_refusal=settings.basic_account_refusal_cache_ttl,
                token_account=settings.token_account_cache_ttl,
                token_account_refusal=settings.token_account_refusal_cache_ttl,
                trusted_network=settings.trusted_network_cache_ttl,
                trusted_network_refusal=settings.trusted_network_refusal_cache_ttl,
                certificate=settings.certificate_cache_ttl,
            ),
        )

    async def _run(self) -> None:
        while not self._closing.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._closing.wait(), self._interval)
            if not self._closing.is_set():
                await self._check()

    async def _check(self) -> None:
        try:
            snapshot = await self._read()
        except Exception:
            logger.exception("Can't look up settings, keeping the current ones")
            return

        if snapshot == self._current:
            return

        try:
            await self._on_change(snapshot)
        except Exception:
            logger.exception("Can't apply settings, retrying on the next lookup")
            return

        self._current = snapshot
        logger.info("Settings applied to new connections")
