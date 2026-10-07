from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy import AuthenticationRequired, EncryptionUnavailable, Identity, MemoryCache
from proxium.runners import ProxyCaches
from proxium.watchers import CacheTtlsSnapshot

if TYPE_CHECKING:
    from faker import Faker


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
