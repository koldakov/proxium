from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.runners import ProxyWorkers

if TYPE_CHECKING:
    from faker import Faker


class TestProxyWorkers:
    def test_init_raises_value_error_on_less_than_one_worker(self, faker: Faker) -> None:
        # Arrange
        workers = faker.pyint(min_value=-10, max_value=0)

        # Act
        with pytest.raises(ValueError, match="Workers must be at least 1"):
            ProxyWorkers(workers=workers)

    def test_init_raises_value_error_on_max_restart_delay_under_restart_delay(self, faker: Faker) -> None:
        # Arrange
        restart_delay = faker.pyfloat(min_value=2, max_value=60)
        max_restart_delay = faker.pyfloat(min_value=0, max_value=restart_delay - 1)

        # Act
        with pytest.raises(ValueError, match="shorter than restart delay"):
            ProxyWorkers(restart_delay=restart_delay, max_restart_delay=max_restart_delay)

    def test_init_raises_value_error_on_several_workers_without_reuse_port(self, faker: Faker) -> None:
        # Arrange
        workers = faker.pyint(min_value=2, max_value=64)

        # Act
        # Every worker but the first would fail to listen.
        with pytest.raises(ValueError, match="PROXY_REUSE_PORT=true"):
            ProxyWorkers(workers=workers, reuse_port=False)
