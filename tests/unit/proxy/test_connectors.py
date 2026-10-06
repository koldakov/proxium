from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy import Address, DirectConnector, ForbiddenAddress

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session


class TestDirectConnector:
    async def test_connect_raises_forbidden_address_when_host_name_resolves_to_loopback(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        connector = DirectConnector()
        # The guard must check what the name resolves to, not the name: it's refused before any connection.
        proxy_request = proxy_request_factory(target=Address("localhost", faker.port_number()))

        # Act & Assert
        with pytest.raises(ForbiddenAddress):
            await connector.connect(proxy_request, session)
