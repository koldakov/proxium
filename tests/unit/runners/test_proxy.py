from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from proxium.proxy import CacheMiss

if TYPE_CHECKING:
    from faker import Faker

    from proxium.runners import ProxyCaches
    from proxium.watchers import CacheTtlsSnapshot

# Each TTL and the cache it's for: a mixed-up pair would leave a shortened TTL waiting the longer one out.
TTL_CACHES = [
    ("basic_account", "basic"),
    ("basic_account_refusal", "basic_refusals"),
    ("token_account", "bearer"),
    ("token_account_refusal", "bearer_refusals"),
    ("trusted_network", "trusted_network"),
    ("trusted_network_refusal", "trusted_network_refusals"),
    ("certificate", "encryption"),
]

CACHE_NAMES = [cache_name for _, cache_name in TTL_CACHES]


class TestProxyCaches:
    @pytest.mark.parametrize("ttl_cache", TTL_CACHES)
    async def test_clear_shortened_clears_only_cache_of_shortened_ttl(
        self,
        faker: Faker,
        proxy_caches: ProxyCaches,
        cache_key: bytes,
        cache_ttls: CacheTtlsSnapshot,
        ttl_cache: tuple[str, str],
    ) -> None:
        # Arrange
        ttl_name, cache_name = ttl_cache
        shorter = faker.pyfloat(min_value=1, max_value=getattr(cache_ttls, ttl_name) - 1)
        current = dataclasses.replace(cache_ttls, **{ttl_name: shorter})

        # Act
        await proxy_caches.clear_shortened(cache_ttls, current)

        # Assert
        with pytest.raises(CacheMiss):
            await getattr(proxy_caches, cache_name).get(cache_key)
        for other_name in CACHE_NAMES:
            if other_name != cache_name:
                await getattr(proxy_caches, other_name).get(cache_key)

    async def test_clear_shortened_keeps_every_cache_when_ttls_get_longer(
        self,
        faker: Faker,
        proxy_caches: ProxyCaches,
        cache_key: bytes,
        cache_ttls: CacheTtlsSnapshot,
    ) -> None:
        # Arrange
        longer = {
            ttl_name: faker.pyfloat(min_value=getattr(cache_ttls, ttl_name) + 1, max_value=7200)
            for ttl_name, _ in TTL_CACHES
        }
        current = dataclasses.replace(cache_ttls, **longer)

        # Act
        await proxy_caches.clear_shortened(cache_ttls, current)

        # Assert
        for cache_name in CACHE_NAMES:
            await getattr(proxy_caches, cache_name).get(cache_key)
