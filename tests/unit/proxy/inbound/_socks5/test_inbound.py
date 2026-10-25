from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy import (
    ResolveTimeout,
    SourceUnavailable,
    TargetNotResolved,
    TargetRefused,
    TargetTimeout,
    TargetUnreachable,
)
from proxium.proxy.inbound import Socks5Inbound
from proxium.proxy.inbound._socks5._inbound import DEFAULT_REPLIES, Reply
from tests.fixtures.proxy import ScriptedStream

if TYPE_CHECKING:
    from proxium.proxy import ProxyError


class TestSocks5Inbound:
    @pytest.mark.parametrize(
        ("error", "reply"),
        [
            pytest.param(TargetUnreachable(), Reply.HOST_UNREACHABLE, id="target-unreachable"),
            pytest.param(TargetNotResolved(), Reply.HOST_UNREACHABLE, id="target-not-resolved"),
            pytest.param(TargetRefused(), Reply.CONNECTION_REFUSED, id="target-refused"),
            pytest.param(TargetTimeout(), Reply.TTL_EXPIRED, id="target-timeout"),
            pytest.param(ResolveTimeout(), Reply.TTL_EXPIRED, id="resolve-timeout"),
            # The proxy's setup is at fault, not the target.
            pytest.param(SourceUnavailable(), Reply.GENERAL_FAILURE, id="source-unavailable"),
        ],
    )
    async def test_reject_sends_reply_of_closest_error_class(self, error: ProxyError, reply: Reply) -> None:
        # Arrange
        inbound = Socks5Inbound()
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, error)

        # Assert
        # VER, REP, RSV, ATYP, BND.ADDR, BND.PORT.
        assert stream.written[1] == reply

    async def test_reject_sends_ttl_expired_on_resolve_timeout_when_not_resolved_has_own_reply(self) -> None:
        # Arrange
        # A timeout, not a `TargetNotResolved`: its reply doesn't apply.
        inbound = Socks5Inbound(replies={**DEFAULT_REPLIES, TargetNotResolved: Reply.NETWORK_UNREACHABLE})
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, ResolveTimeout())

        # Assert
        assert stream.written[1] == Reply.TTL_EXPIRED
