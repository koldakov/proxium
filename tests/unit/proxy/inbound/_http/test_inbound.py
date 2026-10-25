from __future__ import annotations

import asyncio
from email.parser import BytesHeaderParser
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from proxium.proxy import (
    ConnectionCountUnavailable,
    ConnectionLimitExceeded,
    CredentialsExpired,
    ForbiddenAddress,
    ProxyError,
    QuotaExceeded,
    ResolveTimeout,
    SourceUnavailable,
    TargetNotResolved,
    TargetRefused,
    TargetTimeout,
    TargetUnreachable,
    UsageUnavailable,
)
from proxium.proxy.inbound import (
    BadRequest,
    BadResponse,
    HttpInbound,
    HttpProtocol,
    NoResponse,
    RequestTimeout,
    ResponseHeadTooLarge,
    ResponseIncomplete,
    ResponseTimeout,
)
from proxium.proxy.inbound._http._head import HTTPVersion
from proxium.proxy.inbound._http._inbound import DEFAULT_STATUSES
from tests.fixtures.proxy import ScriptedStream, StalledStream

if TYPE_CHECKING:
    from collections.abc import Callable
    from email.message import Message

    from faker import Faker

    from proxium.proxy import Request, Stream


def _parse_headers(raw: bytes | bytearray, /) -> Message:
    """Headers of a response head, the status line skipped."""
    _, _, headers = raw.partition(b"\r\n")
    return BytesHeaderParser().parsebytes(headers)


def _parse_status_line(raw: bytes | bytearray, /) -> tuple[int, str]:
    """Status and reason of a response head."""
    line, _, _ = raw.partition(b"\r\n")
    _, status, reason = line.decode().split(" ", 2)
    return int(status), reason


async def _read_all(stream: Stream, /) -> bytes:
    """What the relay passes on to the client from `stream`, up to EOF."""
    data = b""
    while chunk := await stream.read():
        data += chunk
    return data


class TestHttpInbound:
    @pytest.mark.parametrize(
        ("error", "status"),
        [
            pytest.param(TargetUnreachable(), 502, id="target-unreachable"),
            pytest.param(TargetNotResolved(), 502, id="target-not-resolved"),
            pytest.param(TargetRefused(), 502, id="target-refused"),
            pytest.param(TargetTimeout(), 504, id="target-timeout"),
            pytest.param(ResolveTimeout(), 504, id="resolve-timeout"),
            # The proxy's setup is at fault, not the target.
            pytest.param(SourceUnavailable(), 500, id="source-unavailable"),
            pytest.param(ConnectionCountUnavailable(), 503, id="connection-count-unavailable"),
            pytest.param(UsageUnavailable(), 503, id="usage-unavailable"),
            pytest.param(ResponseTimeout(), 504, id="response-timeout"),
            pytest.param(RequestTimeout(), 408, id="request-timeout"),
            pytest.param(BadResponse(), 502, id="bad-response"),
        ],
    )
    async def test_reject_sends_status_of_closest_error_class(self, error: ProxyError, status: int) -> None:
        # Arrange
        inbound = HttpInbound()
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, error)

        # Assert
        assert _parse_status_line(stream.written)[0] == status

    async def test_reject_sends_gateway_timeout_on_resolve_timeout_when_not_resolved_has_own_status(self) -> None:
        # Arrange
        # A timeout, not a `TargetNotResolved`: its status doesn't apply.
        inbound = HttpInbound(statuses={**DEFAULT_STATUSES, TargetNotResolved: HTTPStatus.BAD_GATEWAY})
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, ResolveTimeout())

        # Assert
        assert _parse_status_line(stream.written)[0] == HTTPStatus.GATEWAY_TIMEOUT

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(ConnectionCountUnavailable(), id="connection-count-unavailable"),
            pytest.param(UsageUnavailable(), id="usage-unavailable"),
        ],
    )
    async def test_reject_sends_limits_unavailable_reason_when_limits_cant_be_checked(self, error: ProxyError) -> None:
        # Arrange
        inbound = HttpInbound()
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, error)

        # Assert
        assert _parse_status_line(stream.written)[1] == "Limits Unavailable"

    @pytest.mark.parametrize(
        ("error", "proxy_status"),
        [
            pytest.param(BadRequest(), "http_request_error", id="bad-request"),
            pytest.param(CredentialsExpired(), "http_request_denied", id="credentials-expired"),
            pytest.param(ForbiddenAddress(), "destination_ip_prohibited", id="forbidden-address"),
            pytest.param(ConnectionLimitExceeded(), "http_request_denied", id="connection-limit"),
            pytest.param(QuotaExceeded(), "http_request_denied", id="quota"),
            pytest.param(ConnectionCountUnavailable(), "proxy_internal_error", id="connection-count-unavailable"),
            pytest.param(UsageUnavailable(), "proxy_internal_error", id="usage-unavailable"),
            pytest.param(TargetUnreachable(), "destination_unavailable", id="target-unreachable"),
            pytest.param(TargetNotResolved(), "dns_error", id="target-not-resolved"),
            pytest.param(TargetRefused(), "connection_refused", id="target-refused"),
            pytest.param(TargetTimeout(), "connection_timeout", id="target-timeout"),
            # A `TargetTimeout` with its own entry.
            pytest.param(ResolveTimeout(), "dns_timeout", id="resolve-timeout"),
            pytest.param(SourceUnavailable(), "proxy_configuration_error", id="source-unavailable"),
            pytest.param(ResponseTimeout(), "http_response_timeout", id="response-timeout"),
            pytest.param(BadResponse(), "http_protocol_error", id="bad-response"),
            pytest.param(ResponseIncomplete(), "http_response_incomplete", id="response-incomplete"),
            pytest.param(NoResponse(), "connection_terminated", id="no-response"),
            pytest.param(ResponseHeadTooLarge(), "http_response_header_section_size", id="response-head-too-large"),
            # The client's request never became a valid one.
            pytest.param(RequestTimeout(), "http_request_error", id="request-timeout"),
            pytest.param(ProxyError(), "proxy_internal_error", id="base-error"),
        ],
    )
    async def test_reject_sends_proxy_status_of_closest_error_class(
        self,
        faker: Faker,
        error: ProxyError,
        proxy_status: str,
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, error)

        # Assert
        assert _parse_headers(stream.written)["Proxy-Status"] == f"{proxy_name}; error={proxy_status}"

    @pytest.mark.parametrize(
        ("error", "retry_after"),
        [
            pytest.param(ConnectionCountUnavailable(), "5", id="connection-count-unavailable"),
            pytest.param(UsageUnavailable(), "5", id="usage-unavailable"),
            # Retrying won't help until the client's quota resets.
            pytest.param(QuotaExceeded(), None, id="quota"),
            pytest.param(ProxyError(), None, id="base-error"),
        ],
    )
    async def test_reject_sends_retry_after_only_when_limits_are_unavailable(
        self,
        error: ProxyError,
        retry_after: str | None,
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        stream = ScriptedStream()

        # Act
        await inbound.reject(stream, error)

        # Assert
        assert _parse_headers(stream.written)["Retry-After"] == retry_after

    async def test_accept_sends_proxy_status_without_error_when_tunnel_opens(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        stream = ScriptedStream()

        # Act
        await inbound.accept(stream, proxy_request_factory(protocol=HttpProtocol.CONNECT))

        # Assert
        assert _parse_headers(stream.written)["Proxy-Status"] == proxy_name

    async def test_accept_sends_nothing_when_forwarding(self, proxy_request_factory: Callable[..., Request]) -> None:
        # Arrange
        inbound = HttpInbound()
        stream = ScriptedStream()

        # Act
        await inbound.accept(stream, proxy_request_factory(protocol=HttpProtocol.FORWARD))

        # Assert
        # The target's response is the only one the client gets.
        assert stream.written == b""

    @pytest.mark.parametrize(
        ("proxy_name", "serialized"),
        [
            pytest.param("10.0.0.5", '"10.0.0.5"', id="ip"),
            pytest.param("my proxy", '"my proxy"', id="space"),
            pytest.param('a "b" \\c', '"a \\"b\\" \\\\c"', id="escaped"),
        ],
    )
    async def test_accept_sends_quoted_proxy_name_when_not_token(
        self,
        proxy_request_factory: Callable[..., Request],
        proxy_name: str,
        serialized: str,
    ) -> None:
        # Arrange
        inbound = HttpInbound(proxy_name=proxy_name)
        stream = ScriptedStream()

        # Act
        await inbound.accept(stream, proxy_request_factory(protocol=HttpProtocol.CONNECT))

        # Assert
        assert _parse_headers(stream.written)["Proxy-Status"] == serialized

    @pytest.mark.parametrize(
        "proxy_name",
        [
            pytest.param("proxium\r\nSet-Cookie: a=b", id="header-injection"),
            pytest.param("прокси", id="non-ascii"),
            pytest.param("", id="empty"),
        ],
    )
    def test_init_raises_value_error_when_proxy_name_cant_go_in_header(self, proxy_name: str) -> None:
        # Act & Assert
        with pytest.raises(ValueError, match="printable ASCII"):
            HttpInbound(proxy_name=proxy_name)

    async def test_exchange_adds_connection_close_and_proxy_status_to_response_head_when_forwarding(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        body = faker.binary(length=faker.random_int(1, 1024))
        inbound = HttpInbound(proxy_name=proxy_name)
        target = received_stream_factory(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%b" % (len(body), body))

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, forward_request_factory()).target)

        # Assert
        # One response per connection: the client is told it closes (RFC 9112, 9.6).
        assert data == (
            b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\nProxy-Status: %b\r\n\r\n%b"
            % (len(body), proxy_name.encode(), body)
        )

    async def test_exchange_puts_proxy_member_after_target_ones(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        next_proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        target = received_stream_factory(b"HTTP/1.1 200 OK\r\nProxy-Status: %b\r\n\r\n" % next_proxy_name.encode())

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, forward_request_factory()).target)

        # Assert
        # RFC 9209, 2: the member of the proxy closest to the client comes last.
        assert _parse_headers(data).get_all("Proxy-Status") == [next_proxy_name, proxy_name]

    async def test_exchange_adds_proxy_status_to_interim_and_final_heads(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        target = received_stream_factory(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 204 No Content\r\n\r\n")

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, forward_request_factory()).target)

        # Assert
        # An interim head doesn't close the connection: the final one is still due.
        assert data == (
            b"HTTP/1.1 100 Continue\r\nProxy-Status: %b\r\n\r\n"
            b"HTTP/1.1 204 No Content\r\nConnection: close\r\nProxy-Status: %b\r\n\r\n"
            % (proxy_name.encode(), proxy_name.encode())
        )

    async def test_exchange_skips_interim_heads_when_client_is_http_1_0(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        target = received_stream_factory(b"HTTP/1.1 103 Early Hints\r\n\r\nHTTP/1.1 204 No Content\r\n\r\n")
        request = forward_request_factory(version=HTTPVersion.HTTP_1_0)

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, request).target)

        # Assert
        # RFC 9110, 15.2: an HTTP/1.0 client doesn't know them.
        assert data == b"HTTP/1.1 204 No Content\r\nConnection: close\r\nProxy-Status: %b\r\n\r\n" % proxy_name.encode()

    async def test_exchange_skips_interim_head_with_invalid_framing_when_client_is_http_1_0(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name)
        target = received_stream_factory(
            b"HTTP/1.1 103 Early Hints\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n"
            b"HTTP/1.1 204 No Content\r\n\r\n",
        )
        request = forward_request_factory(version=HTTPVersion.HTTP_1_0)

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, request).target)

        # Assert
        # The client never sees the interim head: its framing can't fail the response.
        assert data == b"HTTP/1.1 204 No Content\r\nConnection: close\r\nProxy-Status: %b\r\n\r\n" % proxy_name.encode()

    async def test_exchange_passes_final_head_when_interim_heads_at_limit(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        proxy_name = faker.domain_word()
        inbound = HttpInbound(proxy_name=proxy_name, max_interim_heads=limit)
        target = received_stream_factory(
            b"HTTP/1.1 102 Processing\r\n\r\n" * limit + b"HTTP/1.1 204 No Content\r\n\r\n",
        )
        request = forward_request_factory(version=HTTPVersion.HTTP_1_0)

        # Act
        data = await _read_all(inbound.exchange(ScriptedStream(), target, request).target)

        # Assert
        assert data == b"HTTP/1.1 204 No Content\r\nConnection: close\r\nProxy-Status: %b\r\n\r\n" % proxy_name.encode()

    async def test_exchange_raises_bad_response_when_interim_heads_over_limit(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        limit = faker.pyint(min_value=1, max_value=10)
        inbound = HttpInbound(max_interim_heads=limit)
        target = received_stream_factory(
            b"HTTP/1.1 102 Processing\r\n\r\n" * (limit + 1) + b"HTTP/1.1 204 No Content\r\n\r\n",
        )
        request = forward_request_factory(version=HTTPVersion.HTTP_1_0)
        exchange = inbound.exchange(ScriptedStream(), target, request)

        # Act & Assert
        # Skipped, they'd hold the connection open without a byte counted.
        with pytest.raises(BadResponse):
            await exchange.target.read()

    async def test_exchange_client_read_waits_for_response_end_when_client_sends_past_head_size_after_request(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        max_head_size = faker.pyint(min_value=1, max_value=1024)
        inbound = HttpInbound(max_head_size=max_head_size)
        client = ScriptedStream([faker.binary(length=max_head_size), faker.binary(length=faker.pyint(min_value=1))])
        target = received_stream_factory(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        exchange = inbound.exchange(client, target, forward_request_factory())

        # Act
        read = asyncio.create_task(exchange.client.read())
        await asyncio.sleep(0)
        waited = not read.done()
        await _read_all(exchange.target)
        data = await read

        # Assert
        # Read on and dropped, what the client sends after its request would pass the grants by.
        assert waited
        assert data == b""

    async def test_exchange_client_read_ends_when_client_closes_after_request(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        client = ScriptedStream([faker.binary(length=faker.pyint(min_value=1, max_value=1024))])
        # The target never answers: the read mustn't wait for its response.
        exchange = inbound.exchange(client, StalledStream(), forward_request_factory())

        # Act
        data = await asyncio.wait_for(exchange.client.read(), timeout=1.0)

        # Assert
        # The relay passes the close on: a target that keeps the connection open hears of it.
        assert data == b""

    async def test_exchange_raises_bad_request_on_read_and_end_when_chunk_malformed(
        self,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        request = forward_request_factory(headers=[("Transfer-Encoding", "chunked")])
        exchange = inbound.exchange(ScriptedStream([b"not-a-size\r\n"]), ScriptedStream(), request)

        # Act
        # Ends the relay: nothing more of the body reaches the target.
        with pytest.raises(BadRequest) as error_info:
            await exchange.client.read()

        # Assert
        # The client is rejected with it, not with a timeout.
        with pytest.raises(BadRequest) as ended_info:
            exchange.check_ended(expired=True)
        assert ended_info.value is error_info.value

    @pytest.mark.parametrize(
        ("response", "error"),
        [
            pytest.param(b"HTTP/1.1 200 OK\r\nContent-Le", ResponseIncomplete, id="incomplete"),
            pytest.param(b"", NoResponse, id="empty"),
            pytest.param(b"HTTP/1.1 200 OK\r\nX-Big: %b\r\n\r\n" % (b"a" * 2048), ResponseHeadTooLarge, id="too-large"),
            pytest.param(b"garbage\r\n\r\n", BadResponse, id="not-http"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA: b\nC: d\r\n\r\n", BadResponse, id="bare-lf-mid-head"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA: b\rC: d\r\n\r\n", BadResponse, id="bare-cr-mid-head"),
            # The body's CRLFs must not pass for the end of the head.
            pytest.param(b"HTTP/1.1 200 OK\nContent-Length: 4\n\n\r\n\r\n", BadResponse, id="bare-lf-head-crlf-body"),
            # Upgrade isn't forwarded: the target can't switch (RFC 9110, 15.2.2).
            pytest.param(b"HTTP/1.1 101 Switching Protocols\r\n\r\n", BadResponse, id="switching-protocols"),
        ],
    )
    async def test_exchange_raises_on_read_and_end_when_response_is_bad(
        self,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
        response: bytes,
        error: type[BadResponse],
    ) -> None:
        # Arrange
        inbound = HttpInbound(max_response_head_size=1024)
        exchange = inbound.exchange(ScriptedStream(), received_stream_factory(response), forward_request_factory())

        # Act
        # Ends the relay.
        with pytest.raises(error) as error_info:
            await exchange.target.read()

        # Assert
        # The client is rejected with it.
        with pytest.raises(error) as ended_info:
            exchange.check_ended(expired=False)
        assert ended_info.value is error_info.value

    async def test_exchange_raises_no_response_when_connection_resets_before_response(
        self,
        forward_request_factory: Callable[..., Request],
        reset_stream: Stream,
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(ScriptedStream(), reset_stream, forward_request_factory())

        # Act & Assert
        with pytest.raises(NoResponse):
            await exchange.target.read()

    async def test_exchange_leaves_streams_as_is_when_tunnel(
        self,
        proxy_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        client = ScriptedStream()
        target = received_stream_factory(b"")

        # Act
        exchange = inbound.exchange(client, target, proxy_request_factory(protocol=HttpProtocol.CONNECT))

        # Assert
        # A tunnel's bytes aren't HTTP for the proxy.
        assert exchange.client is client
        assert exchange.target is target

    async def test_handshake_raises_bad_request_when_body_end_unclear(
        self,
        faker: Faker,
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        host = faker.hostname()
        stream = received_stream_factory(
            b"POST http://%b/ HTTP/1.1\r\nHost: %b\r\nTransfer-Encoding: gzip\r\n\r\n" % (host.encode(), host.encode()),
        )

        # Act & Assert
        # Refused before connecting: the proxy couldn't tell when the client is done.
        with pytest.raises(BadRequest):
            await inbound.handshake(stream, AsyncMock())

    def test_check_ended_raises_response_timeout_when_target_sent_nothing(
        self,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(ScriptedStream(), ScriptedStream(), forward_request_factory())

        # Act & Assert
        with pytest.raises(ResponseTimeout):
            exchange.check_ended(expired=True)

    async def test_check_ended_raises_response_timeout_when_body_came_whole(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        body = faker.binary(length=faker.pyint(min_value=1, max_value=1024))
        request = forward_request_factory(headers=[("Content-Length", str(len(body)))])
        exchange = inbound.exchange(ScriptedStream([body]), ScriptedStream(), request)
        await exchange.client.read()

        # Act & Assert
        with pytest.raises(ResponseTimeout):
            exchange.check_ended(expired=True)

    async def test_check_ended_raises_request_timeout_when_client_stalls_mid_body(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        body = faker.binary(length=faker.pyint(min_value=2, max_value=1024))
        request = forward_request_factory(headers=[("Content-Length", str(len(body)))])
        exchange = inbound.exchange(ScriptedStream([body[:-1]]), ScriptedStream(), request)
        await exchange.client.read()

        # Act & Assert
        # The target waits for the rest: the client is late, not the target.
        with pytest.raises(RequestTimeout):
            exchange.check_ended(expired=True)

    def test_check_ended_raises_response_timeout_when_client_waits_for_continue(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        request = forward_request_factory(
            headers=[("Expect", "100-continue"), ("Content-Length", str(faker.pyint(min_value=1)))],
        )
        exchange = inbound.exchange(ScriptedStream(), ScriptedStream(), request)

        # Act & Assert
        # No body, but no `100 Continue` either: the target is late, not the client.
        with pytest.raises(ResponseTimeout):
            exchange.check_ended(expired=True)

    async def test_exchange_drops_bytes_after_request(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        body = faker.binary(length=faker.pyint(min_value=1, max_value=1024))
        pipelined = b"GET http://%b/ HTTP/1.1\r\nProxy-Authorization: Basic %b\r\n\r\n" % (
            faker.hostname().encode(),
            faker.pystr().encode(),
        )
        request = forward_request_factory(headers=[("Content-Length", str(len(body)))])
        exchange = inbound.exchange(
            ScriptedStream([body + pipelined, pipelined]),
            received_stream_factory(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"),
            request,
        )
        # The client's reads end with the response.
        await _read_all(exchange.target)

        # Act
        data = await _read_all(exchange.client)

        # Assert
        # A pipelined request, credentials included, never reaches this target.
        assert data == body

    async def test_check_ended_raises_response_timeout_when_only_interim_head_came(
        self,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(
            ScriptedStream(),
            received_stream_factory(b"HTTP/1.1 100 Continue\r\n\r\n"),
            forward_request_factory(),
        )
        await exchange.target.read()

        # Act & Assert
        # The final head is still due.
        with pytest.raises(ResponseTimeout):
            exchange.check_ended(expired=True)

    async def test_check_ended_raises_response_timeout_when_client_waits_for_continue_after_other_interim_head(
        self,
        faker: Faker,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        request = forward_request_factory(
            headers=[("Expect", "100-continue"), ("Content-Length", str(faker.pyint(min_value=1)))],
        )
        exchange = inbound.exchange(
            ScriptedStream(),
            received_stream_factory(b"HTTP/1.1 103 Early Hints\r\n\r\n"),
            request,
        )
        await exchange.target.read()

        # Act & Assert
        # Only 100 Continue lets the body come: the target is late, not the client.
        with pytest.raises(ResponseTimeout):
            exchange.check_ended(expired=True)

    async def test_check_ended_raises_nothing_when_client_got_final_head(
        self,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(
            ScriptedStream(),
            received_stream_factory(b"HTTP/1.1 200 OK\r\n\r\n"),
            forward_request_factory(),
        )
        # As the relay passes it on.
        exchange.client.write(await exchange.target.read())

        # Act & Assert
        exchange.check_ended(expired=True)

    async def test_check_ended_raises_relay_error_when_final_head_read_but_not_sent(
        self,
        forward_request_factory: Callable[..., Request],
        received_stream_factory: Callable[[bytes], Stream],
    ) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(
            ScriptedStream(),
            received_stream_factory(b"HTTP/1.1 200 OK\r\n\r\n"),
            forward_request_factory(),
        )
        # A grant cuts the relay on the head's bytes, before it writes them to the client.
        await exchange.target.read()
        error = QuotaExceeded()

        # Act & Assert
        # The client has no answer yet: it's told why.
        with pytest.raises(QuotaExceeded) as ended_info:
            exchange.check_ended(expired=False, error=error)
        assert ended_info.value is error

    def test_check_ended_raises_nothing_when_tunnel(self, proxy_request_factory: Callable[..., Request]) -> None:
        # Arrange
        inbound = HttpInbound()
        exchange = inbound.exchange(
            ScriptedStream(),
            ScriptedStream(),
            proxy_request_factory(protocol=HttpProtocol.CONNECT),
        )

        # Act & Assert
        # A tunnel's client waits for no answer of the proxy.
        exchange.check_ended(expired=True)
