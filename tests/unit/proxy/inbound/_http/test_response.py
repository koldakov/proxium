from __future__ import annotations

from http import HTTPMethod
from typing import TYPE_CHECKING

import pytest

from proxium.proxy.inbound import BadResponse
from proxium.proxy.inbound._http._head import HTTPVersion
from proxium.proxy.inbound._http._response import TargetResponseHead

if TYPE_CHECKING:
    from faker import Faker


def _head(
    *headers: tuple[str, str],
    status: int = 200,
    version: HTTPVersion = HTTPVersion.HTTP_1_1,
) -> TargetResponseHead:
    return TargetResponseHead(status=status, reason="", version=version, headers=headers)


def _values(head: TargetResponseHead, name: str, /) -> list[str]:
    return [value for key, value in head.headers if key.lower() == name.lower()]


class TestTargetResponseHead:
    def test_from_bytes_keeps_status_and_reason_as_sent(self, faker: Faker) -> None:
        # Arrange
        reason = faker.word()

        # Act
        # Not in `HTTPStatus`, still valid.
        head = TargetResponseHead.from_bytes(b"HTTP/1.1 299 %b\r\n\r\n" % reason.encode())

        # Assert
        assert (head.status, head.reason) == (299, reason)

    def test_from_bytes_takes_empty_reason_when_missing(self) -> None:
        # Act
        head = TargetResponseHead.from_bytes(b"HTTP/1.1 204\r\n\r\n")

        # Assert
        # RFC 9112, 4: the reason is optional.
        assert head.reason == ""

    def test_from_bytes_strips_whitespace_before_colon(self, faker: Faker) -> None:
        # Arrange
        name = faker.word()
        value = faker.word()

        # Act
        head = TargetResponseHead.from_bytes(b"HTTP/1.1 200 OK\r\n%b \t: %b\r\n\r\n" % (name.encode(), value.encode()))

        # Assert
        # RFC 9112, 5.1: a proxy removes it before forwarding.
        assert head.headers == ((name, value),)

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(b"HTTP/1.1 OK\r\n\r\n", id="no-status"),
            pytest.param(b"HTTP/1.1 600 X\r\n\r\n", id="status-over-599"),
            pytest.param(b"HTTP/1.1 099 X\r\n\r\n", id="status-under-100"),
            pytest.param(b"HTTP/1.1 200 O\x00K\r\n\r\n", id="control-in-reason"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA: b\r\n c\r\n\r\n", id="obsolete-line-folding"),
            pytest.param(b"HTTP/1.1 200 OK\r\n A: b\r\n\r\n", id="whitespace-before-first-field"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA: b\x00c\r\n\r\n", id="nul-in-value"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA b: c\r\n\r\n", id="space-in-name"),
            pytest.param(b"HTTP/1.1 200 OK\r\nA\r\n\r\n", id="no-colon"),
            pytest.param(b"HTTP/1.1 200 OK\r\n: b\r\n\r\n", id="empty-name"),
        ],
    )
    def test_from_bytes_raises_bad_response_when_head_invalid(self, raw: bytes) -> None:
        # Act & Assert
        with pytest.raises(BadResponse):
            TargetResponseHead.from_bytes(raw)

    @pytest.mark.parametrize(
        "name",
        [
            "Connection",
            "Keep-Alive",
            "Proxy-Authenticate",
            "Proxy-Authentication-Info",
            "Proxy-Connection",
            "TE",
            "Upgrade",
        ],
    )
    def test_to_client_drops_hop_by_hop_field(self, faker: Faker, name: str) -> None:
        # Arrange
        head = _head((name, faker.word()))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9110, 7.6.1: the target-proxy hop's own. The proxy's `Connection: close` stands alone.
        assert _values(client_head, name) == (["close"] if name == "Connection" else [])

    def test_to_client_drops_fields_listed_in_connection(self, faker: Faker) -> None:
        # Arrange
        name = faker.word()
        head = _head(("Connection", f"keep-alive, {name.upper()}"), (name, faker.word()))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        assert _values(client_head, name) == []

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            pytest.param("Content-Length", "5", id="content-length"),
            pytest.param("Transfer-Encoding", "chunked", id="transfer-encoding"),
        ],
    )
    def test_to_client_keeps_framing_field_listed_in_connection(self, faker: Faker, name: str, value: str) -> None:
        # Arrange
        head = _head(("Connection", name), (name, value))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # The body passes as is: without it the client would misread it.
        assert _values(client_head, name) == [value]

    @pytest.mark.parametrize(
        ("status", "connection"),
        [
            pytest.param(200, ["close"], id="final"),
            # The final head is still due on the connection.
            pytest.param(100, [], id="interim"),
        ],
    )
    def test_to_client_says_connection_closes_only_in_final_head(
        self,
        faker: Faker,
        status: int,
        connection: list[str],
    ) -> None:
        # Arrange
        head = _head(status=status)

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9112, 9.6: the proxy forwards one response per connection.
        assert _values(client_head, "Connection") == connection

    def test_to_client_puts_proxy_status_last(self, faker: Faker) -> None:
        # Arrange
        proxy_status = faker.domain_word()
        head = _head((faker.word(), faker.word()), ("Proxy-Status", faker.domain_word()))

        # Act
        client_head = head.to_client(
            proxy_status=proxy_status,
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9209, 2: the member of the proxy closest to the client comes last.
        assert client_head.headers[-1] == ("Proxy-Status", proxy_status)

    def test_to_client_drops_content_length_next_to_transfer_encoding(self, faker: Faker) -> None:
        # Arrange
        head = _head(("Content-Length", str(faker.pyint())), ("Transfer-Encoding", "chunked"))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9112, 6.3: Transfer-Encoding overrides it, an intermediary removes it.
        assert _values(client_head, "Content-Length") == []

    def test_to_client_sends_repeated_content_length_once(self, faker: Faker) -> None:
        # Arrange
        length = str(faker.pyint())
        head = _head(("Content-Length", f"{length}, {length}"), ("Content-Length", length))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9110, 8.6: valid, and unambiguous as one field.
        assert _values(client_head, "Content-Length") == [length]

    @pytest.mark.parametrize(
        ("headers", "version"),
        [
            pytest.param([("Content-Length", "1"), ("Content-Length", "2")], HTTPVersion.HTTP_1_1, id="conflicting"),
            pytest.param([("Content-Length", "1, 2")], HTTPVersion.HTTP_1_1, id="conflicting-in-list"),
            pytest.param([("Content-Length", "")], HTTPVersion.HTTP_1_1, id="empty-length"),
            pytest.param([("Content-Length", "-1")], HTTPVersion.HTTP_1_1, id="negative-length"),
            # A digit for `str.isdigit`, not for HTTP.
            pytest.param([("Content-Length", "²")], HTTPVersion.HTTP_1_1, id="non-ascii-digit"),
            pytest.param([("Transfer-Encoding", "chunked")], HTTPVersion.HTTP_1_0, id="transfer-encoding-in-http-1-0"),
            pytest.param([("Transfer-Encoding", "chunked, chunked")], HTTPVersion.HTTP_1_1, id="chunked-twice"),
            pytest.param([("Transfer-Encoding", "")], HTTPVersion.HTTP_1_1, id="empty-transfer-encoding"),
        ],
    )
    def test_to_client_raises_bad_response_when_framing_invalid(
        self,
        faker: Faker,
        headers: list[tuple[str, str]],
        version: HTTPVersion,
    ) -> None:
        # Arrange
        head = _head(*headers, version=version)

        # Act & Assert
        # RFC 9112, 6.3: a proxy answers 502 instead.
        with pytest.raises(BadResponse):
            head.to_client(
                proxy_status=faker.domain_word(),
                client_version=HTTPVersion.HTTP_1_1,
                request_method=HTTPMethod.GET,
            )

    def test_to_client_keeps_transfer_encoding_without_chunked_last(self, faker: Faker) -> None:
        # Arrange
        head = _head(("Transfer-Encoding", "gzip"))

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_1,
            request_method=HTTPMethod.GET,
        )

        # Assert
        # RFC 9112, 6.3: valid for a response, the body ends with the connection.
        assert _values(client_head, "Transfer-Encoding") == ["gzip"]

    @pytest.mark.parametrize(
        ("method", "status"),
        [
            pytest.param(HTTPMethod.HEAD, 200, id="head"),
            pytest.param(HTTPMethod.GET, 204, id="no-content"),
            pytest.param(HTTPMethod.GET, 304, id="not-modified"),
        ],
    )
    def test_to_client_drops_transfer_encoding_when_http_1_0_client_gets_no_body(
        self,
        faker: Faker,
        method: HTTPMethod,
        status: int,
    ) -> None:
        # Arrange
        head = _head(("Transfer-Encoding", "chunked"), status=status)

        # Act
        client_head = head.to_client(
            proxy_status=faker.domain_word(),
            client_version=HTTPVersion.HTTP_1_0,
            request_method=method,
        )

        # Assert
        # RFC 9112, 6.1: not for an HTTP/1.0 client, and there's no body to misread.
        assert _values(client_head, "Transfer-Encoding") == []

    def test_to_client_raises_bad_response_when_http_1_0_client_gets_chunked_body(self, faker: Faker) -> None:
        # Arrange
        head = _head(("Transfer-Encoding", "chunked"))

        # Act & Assert
        # The client would read the chunks as the body.
        with pytest.raises(BadResponse):
            head.to_client(
                proxy_status=faker.domain_word(),
                client_version=HTTPVersion.HTTP_1_0,
                request_method=HTTPMethod.GET,
            )
