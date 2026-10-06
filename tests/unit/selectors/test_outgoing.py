from __future__ import annotations

from ipaddress import IPv4Address
from typing import TYPE_CHECKING

import pytest

from proxium.db import OutgoingMode
from proxium.proxy import SourceUnavailable
from proxium.selectors import OutgoingSourceSelector, outgoing_claims

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session


class TestOutgoingSourceSelector:
    def test_select_raises_source_unavailable_when_outgoing_mode_missing(
        self,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        selector = OutgoingSourceSelector()

        # Act & Assert
        with pytest.raises(SourceUnavailable):
            selector.select(proxy_request, session)

    def test_select_returns_pool_ip_when_outgoing_mode_pool(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        selector = OutgoingSourceSelector()
        pool = [IPv4Address(faker.unique.ipv4_public()) for _ in range(faker.pyint(min_value=1, max_value=5))]
        proxy_request = proxy_request_factory(claims=outgoing_claims(OutgoingMode.POOL, ips=pool))

        # Act
        ip = selector.select(proxy_request, session)

        # Assert
        assert ip in pool
