from __future__ import annotations

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import TYPE_CHECKING, Final

from pytest_bdd import given, parsers

from proxium.db import ProxyInstanceModel, ProxyInstanceStatus, session_manager

from ._async import async_step

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

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


async def _add_instance(  # noqa: PLR0913
    faker: Faker,
    api_client: ApiClient,
    state: str,
    alias: str,
    ips: list[IPv4Address | IPv6Address],
    /,
    *,
    workers: int = 1,
    running_workers: int = 1,
) -> None:
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
        workers=workers,
        running_workers=running_workers,
        ips=ips,
        last_seen_at=now,
        expires_at=now + _DUE if is_due else now - _DUE,
    )
    async with session_manager.session() as session:
        session.add(instance)
        await session.commit()
    api_client.items[alias] = {"id": instance.id}


@given(parsers.re(r'an? (?P<state>\w+) proxy instance "(?P<alias>[^"]+)"'))
@async_step
async def _(faker: Faker, api_client: ApiClient, state: str, alias: str) -> None:
    """With no IPs."""
    await _add_instance(faker, api_client, state, alias, [])


@given(parsers.re(r'an? (?P<state>\w+) proxy instance "(?P<alias>[^"]+)" with IPs "(?P<ips>[^"]+)"'))
@async_step
async def _(faker: Faker, api_client: ApiClient, state: str, alias: str, ips: str) -> None:
    """With the IPs, comma-separated, on its interfaces."""
    await _add_instance(faker, api_client, state, alias, [ip_address(ip.strip()) for ip in ips.split(",")])


@given(
    parsers.re(
        r'an? (?P<state>\w+) proxy instance "(?P<alias>[^"]+)" with (?P<running_workers>\d+) of (?P<workers>\d+) '
        r"workers serving",
    ),
)
@async_step
# pytest-bdd passes fixtures and step arguments by name: one parameter each.
async def _(  # noqa: PLR0913, PLR0917
    faker: Faker,
    api_client: ApiClient,
    state: str,
    alias: str,
    running_workers: str,
    workers: str,
) -> None:
    """With no IPs."""
    await _add_instance(
        faker,
        api_client,
        state,
        alias,
        [],
        workers=int(workers),
        running_workers=int(running_workers),
    )
