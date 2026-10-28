from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from pytest_bdd import given, parsers

from proxium.db import ProxyInstanceModel, ProxyInstanceStatus, session_manager

from ._async import async_step

if TYPE_CHECKING:
    from faker import Faker

    from tests.fixtures.api import ApiClient

# What the admin sees by what the process reported and whether its next report is still due: unknown is a process
# that went silent.
STATES: Final[dict[str, tuple[ProxyInstanceStatus, bool]]] = {
    "pending": (ProxyInstanceStatus.PENDING, True),
    "running": (ProxyInstanceStatus.RUNNING, True),
    "stopped": (ProxyInstanceStatus.STOPPED, True),
    "unknown": (ProxyInstanceStatus.RUNNING, False),
}
# Far from the database's clock either way: the step's clock may differ from it a little.
_DUE: Final[timedelta] = timedelta(minutes=10)


@given(parsers.re(r'an? (?P<state>\w+) proxy instance "(?P<alias>[^"]+)"'))
@async_step
async def _(faker: Faker, api_client: ApiClient, state: str, alias: str) -> None:
    """As its process reports it, kept as `alias`."""
    status, is_due = STATES[state]
    now = datetime.now(UTC)
    instance = ProxyInstanceModel(
        key=faker.unique.sha256(),
        hostname=faker.hostname(),
        started_at=now - timedelta(hours=1),
        name=faker.word(),
        version=faker.numerify("#.#.#"),
        status=status,
        last_seen_at=now,
        expires_at=now + _DUE if is_due else now - _DUE,
    )
    async with session_manager.session() as session:
        session.add(instance)
        await session.commit()
    api_client.items[alias] = {"id": instance.id}
