from __future__ import annotations

import socket
from ipaddress import IPv4Address, IPv4Network
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
    with socket.socket() as sock:
        sock.bind((str(LOOPBACK), 0))
        _, port = sock.getsockname()
    return Address(str(LOOPBACK), port)


@pytest.fixture
def running_proxy(loop_runner: asyncio.Runner, database: None, proxy_address: Address) -> Iterator[Address]:
    """The proxy as `proxium proxy` runs it, everything from the database, listening on `proxy_address`.

    Loopback is allowed in the settings: test websites run there.
    """
    loop_runner.run(_allow_loopback())
    runner = ProxyRunner(
        listen=[ListenAddress(hosts=[LOOPBACK], ports=range(proxy_address.port, proxy_address.port + 1))],
        # Off: a port taken by mistake must fail, not be shared.
        reuse_port=False,
        # Clients are done by the teardown, a connection still open is a leak: cut it.
        graceful_timeout=0,
    )
    loop_runner.run(runner.start())

    yield proxy_address

    loop_runner.run(runner.close())
