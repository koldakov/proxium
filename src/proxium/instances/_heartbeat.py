from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert

from proxium.core import proxy_settings
from proxium.db import ProxyInstanceModel, ProxyInstanceStatus, session_manager
from proxium.utils import metadata

if TYPE_CHECKING:
    from sqlalchemy.dialects.postgresql import Insert

logger = logging.getLogger(__name__)

# Where systemd keeps the id of the machine, and D-Bus on systems without it.
MACHINE_ID_PATHS: Final[tuple[Path, ...]] = (
    Path("/etc/machine-id"),
    Path("/var/lib/dbus/machine-id"),
)


def _read_machine_id() -> str:
    """The id of the machine, kept across reboots. Empty where there's none, e.g. in most containers: there the host
    name tells them apart.
    """
    for path in MACHINE_ID_PATHS:
        try:
            machine_id = path.read_text().strip()
        except OSError:
            continue
        if machine_id:
            return machine_id
    return ""


def _get_instance_key(machine_id: str, hostname: str, /) -> str:
    return hashlib.sha256(f"{machine_id}\n{hostname}".encode()).hexdigest()


class InstanceHeartbeat:
    """Reports this instance to `proxy_instances` every `interval` seconds, and at once when its status changes.
    The instance is the machine and the host name: a restart reports to the same row.

    Each report says the next is due within `spare_reports` missed ones: past that the admin shows the instance as
    unknown. A report is one statement off the connection path, cut after `timeout` seconds: a slow database delays
    nothing but the report. A failed one is logged and the next retries.

    Call `start` in the running loop, `set_status` as the process goes, `close` last: it reports the stop.
    """

    def __init__(
        self,
        *,
        name: str = proxy_settings.name,
        interval: float = proxy_settings.heartbeat_interval,
        spare_reports: int = 2,
        timeout: float = 5.0,
    ) -> None:
        if spare_reports < 0:
            raise ValueError("Spare reports can't be negative.")

        self._hostname: str = socket.gethostname()
        self._key: str = _get_instance_key(_read_machine_id(), self._hostname)
        self._started_at: datetime = datetime.now(UTC)
        self._name: str = name
        self._version: str = metadata["Version"]
        self._interval: float = interval
        # The report on time plus the spare ones.
        self._lease: timedelta = timedelta(seconds=interval * (spare_reports + 1))
        self._timeout: float = timeout
        self._status: ProxyInstanceStatus = ProxyInstanceStatus.PENDING
        # Set on a status change: reported at once, not on the next tick.
        self._wake: asyncio.Event = asyncio.Event()
        # Logged once per outage, not on every report.
        self._is_failing: bool = False
        self._task: asyncio.Task[None] | None = None

    def _get_report_instance_statement(self, status: ProxyInstanceStatus, /) -> Insert:
        # The database's time: clocks of instances don't matter.
        now = func.now()
        statement = insert(ProxyInstanceModel).values(
            key=self._key,
            hostname=self._hostname,
            started_at=self._started_at,
            name=self._name,
            version=self._version,
            status=status,
            last_seen_at=now,
            expires_at=now + self._lease,
        )
        # The whole state every time: a deregistered row, a restored database or a lost report heal on the next one.
        return statement.on_conflict_do_update(
            index_elements=[ProxyInstanceModel.key],
            set_={
                "started_at": statement.excluded.started_at,
                "name": statement.excluded.name,
                "version": statement.excluded.version,
                "status": statement.excluded.status,
                "last_seen_at": statement.excluded.last_seen_at,
                "expires_at": statement.excluded.expires_at,
                # Deregistered by an admin, yet alive.
                "is_deleted": False,
                "updated_at": now,
            },
            # The newer process owns the row: during a restart without downtime the old one's reports, its stop too,
            # don't hide the new one. A row whose process is gone is taken anyway, even if the clock went back.
            where=or_(
                ProxyInstanceModel.started_at <= statement.excluded.started_at,
                ProxyInstanceModel.status == ProxyInstanceStatus.STOPPED,
                ProxyInstanceModel.expires_at < now,
            ),
        )

    async def _write(self, status: ProxyInstanceStatus, /) -> None:
        async with asyncio.timeout(self._timeout), session_manager.session() as session:
            await session.execute(self._get_report_instance_statement(status))
            await session.commit()

    async def _report(self, status: ProxyInstanceStatus, /) -> None:
        try:
            await self._write(status)
        except Exception:
            if not self._is_failing:
                logger.warning("Can't report the instance, retrying every %s s", self._interval, exc_info=True)
            self._is_failing = True
            return

        if self._is_failing:
            logger.info("Instance reports are back")
        self._is_failing = False

    async def _run(self) -> None:
        while True:
            # Cleared before the status is read: a change during the report wakes the next one at once.
            self._wake.clear()
            status = self._status
            await self._report(status)
            if status is ProxyInstanceStatus.STOPPED:
                return

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self._interval)

    def start(self) -> None:
        """Report the process as pending, then keep reporting."""
        self._task = asyncio.create_task(self._run())

    def set_status(self, status: ProxyInstanceStatus, /) -> None:
        self._status = status
        self._wake.set()

    async def close(self) -> None:
        """Report the stop and quit. Takes up to two `timeout`s: a report in progress, then the stop."""
        self.set_status(ProxyInstanceStatus.STOPPED)
        if self._task is not None:
            await self._task
