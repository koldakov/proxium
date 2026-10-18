from __future__ import annotations

import socket
from ipaddress import IPv4Address, IPv4Network, ip_address
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import update

from proxium.core import ListenAddress
from proxium.db import SettingsModel, session_manager
from proxium.proxy import Address, AuthenticationRequired, EncryptionUnavailable, Identity, MemoryCache
from proxium.runners import ProxyCaches, ProxyRunner
from proxium.watchers import CacheTtlsSnapshot

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Iterator

    from faker import Faker

LOOPBACK: IPv4Address = IPv4Address("127.0.0.1")
# Another address of this host: Linux has all of 127.0.0.0/8 on loopback, macOS only 127.0.0.1.
SECOND_LOOPBACK: IPv4Address = IPv4Address("127.0.0.2")


def _get_free_port(host: IPv4Address, /) -> int:
    with socket.socket() as sock:
        sock.bind((str(host), 0))
        _, port = sock.getsockname()
    return port


async def _allow_loopback() -> None:
    async with session_manager.session() as session:
        await session.execute(update(SettingsModel).values(guard_allow=[IPv4Network("127.0.0.0/8")]))
        await session.commit()


@pytest.fixture
def cache_key(faker: Faker) -> bytes:
    return faker.binary(length=32)


@pytest.fixture
def cache_ttls(faker: Faker) -> CacheTtlsSnapshot:
    """Every TTL the same, above 1 second: room to make any of them shorter."""
    ttl = faker.pyfloat(min_value=2, max_value=3600)
    return CacheTtlsSnapshot(
        basic_account=ttl,
        basic_account_refusal=ttl,
        token_account=ttl,
        token_account_refusal=ttl,
        trusted_network=ttl,
        trusted_network_refusal=ttl,
        certificate=ttl,
    )


@pytest.fixture
async def proxy_caches(faker: Faker, cache_key: bytes, cache_ttls: CacheTtlsSnapshot) -> ProxyCaches:
    """Caches each holding a value under `cache_key`, kept longer than the test runs."""
    caches = ProxyCaches(
        basic=MemoryCache(),
        basic_refusals=MemoryCache(),
        bearer=MemoryCache(),
        bearer_refusals=MemoryCache(),
        trusted_network=MemoryCache(),
        trusted_network_refusals=MemoryCache(),
        encryption=MemoryCache(),
    )
    identity = Identity(subject=faker.uuid4(), claims={})
    ttl = cache_ttls.certificate
    await caches.basic.set(cache_key, identity, ttl=ttl)
    await caches.basic_refusals.set(cache_key, AuthenticationRequired(), ttl=ttl)
    await caches.bearer.set(cache_key, identity, ttl=ttl)
    await caches.bearer_refusals.set(cache_key, AuthenticationRequired(), ttl=ttl)
    await caches.trusted_network.set(cache_key, identity, ttl=ttl)
    await caches.trusted_network_refusals.set(cache_key, AuthenticationRequired(), ttl=ttl)
    await caches.encryption.set(cache_key, EncryptionUnavailable(), ttl=ttl)
    return caches


@pytest.fixture
def proxy_address() -> Address:
    """A free port on loopback. Taken by someone else before the proxy listens, the proxy fails with `ListenError`."""
    return Address(str(LOOPBACK), _get_free_port(LOOPBACK))


@pytest.fixture
def second_address() -> IPv4Address:
    """Another loopback address of this host, the test is skipped where there's none, see `SECOND_LOOPBACK`."""
    with socket.socket() as sock:
        try:
            sock.bind((str(SECOND_LOOPBACK), 0))
        except OSError:
            pytest.skip(f"{SECOND_LOOPBACK} isn't on this host.")
    return SECOND_LOOPBACK


@pytest.fixture
def second_proxy_address(second_address: IPv4Address) -> Address:
    """A free port on the second address, like `proxy_address`."""
    return Address(str(second_address), _get_free_port(second_address))


@pytest.fixture
def running_proxy(loop_runner: asyncio.Runner, database: None, proxy_address: Address) -> Iterator[Address]:
    """The proxy as `proxium proxy` runs it, everything from the database, listening on `proxy_address`.

    Loopback is allowed in the settings: test websites run there.
    """
    loop_runner.run(_allow_loopback())
    host = ip_address(proxy_address.host)
    runner = ProxyRunner(
        listen=[ListenAddress(hosts=[host], ports=range(proxy_address.port, proxy_address.port + 1))],
        # Off: a port taken by mistake must fail, not be shared.
        reuse_port=False,
        # Clients are done by the teardown, a connection still open is a leak: cut it.
        graceful_timeout=0,
    )
    loop_runner.run(runner.start())

    yield proxy_address

    loop_runner.run(runner.close())
