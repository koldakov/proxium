from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy.inbound import BadRequest, RequestTimeout
from proxium.proxy.inbound._http._body import RequestBody
from proxium.proxy.inbound._http._head import HTTPVersion, RequestHead

if TYPE_CHECKING:
    from faker import Faker


def _head(*headers: tuple[str, str], version: HTTPVersion = HTTPVersion.HTTP_1_1) -> RequestHead:
    return RequestHead(method="POST", target="/", version=version, headers=(("Host", "example.com"), *headers))


def _chunk(data: bytes, /) -> bytes:
    return b"%x\r\n%b\r\n" % (len(data), data)


def _pipelined(faker: Faker, /) -> bytes:
    """A next request after the body, to another host with the client's credentials."""
    return b"GET http://%b/ HTTP/1.1\r\nProxy-Authorization: Basic %b\r\n\r\n" % (
        faker.hostname().encode(),
        faker.pystr().encode(),
    )


class TestRequestBody:
    def test_check_complete_passes_when_request_has_no_body(self) -> None:
        # Arrange
        body = RequestBody(_head())

        # Act & Assert
        # No Content-Length nor Transfer-Encoding: a request without a body (RFC 9112, 6.3).
        body.check_complete(continued=False)

    def test_check_complete_passes_when_content_length_bytes_came(self, faker: Faker) -> None:
        # Arrange
        data = faker.binary(length=faker.pyint(min_value=2, max_value=1024))
        split = faker.pyint(min_value=1, max_value=len(data) - 1)
        body = RequestBody(_head(("Content-Length", str(len(data)))))

        # Act
        body.feed(data[:split])
        body.feed(data[split:])

        # Assert
        body.check_complete(continued=False)

    def test_check_complete_raises_request_timeout_when_body_shorter_than_content_length(self, faker: Faker) -> None:
        # Arrange
        data = faker.binary(length=faker.pyint(min_value=2, max_value=1024))
        body = RequestBody(_head(("Content-Length", str(len(data)))))

        # Act
        body.feed(data[:-1])

        # Assert
        with pytest.raises(RequestTimeout):
            body.check_complete(continued=False)

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param([("Transfer-Encoding", "chunked")], id="chunked"),
            pytest.param([("Transfer-Encoding", "gzip, chunked")], id="chunked-last"),
            pytest.param([("Transfer-Encoding", "gzip"), ("Transfer-Encoding", "chunked")], id="chunked-in-last-field"),
        ],
    )
    def test_check_complete_passes_when_last_chunk_came(self, faker: Faker, headers: list[tuple[str, str]]) -> None:
        # Arrange
        body = RequestBody(_head(*headers))
        data = _chunk(faker.binary(length=faker.pyint(min_value=1, max_value=1024))) + b"0\r\n\r\n"

        # Act
        # Byte by byte: a chunk split anywhere is still followed.
        for i in range(len(data)):
            body.feed(data[i : i + 1])

        # Assert
        body.check_complete(continued=False)

    def test_check_complete_raises_request_timeout_when_last_chunk_missing(self, faker: Faker) -> None:
        # Arrange
        body = RequestBody(_head(("Transfer-Encoding", "chunked")))

        # Act
        body.feed(_chunk(faker.binary(length=faker.pyint(min_value=1, max_value=1024))))

        # Assert
        with pytest.raises(RequestTimeout):
            body.check_complete(continued=False)

    def test_feed_raises_bad_request_when_chunk_malformed(self) -> None:
        # Arrange
        body = RequestBody(_head(("Transfer-Encoding", "chunked")))

        # Act & Assert
        # Nothing more of the body may go on: the target would find another end.
        with pytest.raises(BadRequest):
            body.feed(b"not-a-size\r\n")

    def test_check_followed_raises_what_feed_raised(self) -> None:
        # Arrange
        body = RequestBody(_head(("Transfer-Encoding", "chunked")))
        with pytest.raises(BadRequest) as error_info:
            body.feed(b"not-a-size\r\n")

        # Act & Assert
        # The client gets told its body is bad, not that it's late.
        with pytest.raises(BadRequest) as followed_info:
            body.check_followed()
        assert followed_info.value is error_info.value

    def test_check_complete_passes_when_client_waits_for_continue(self, faker: Faker) -> None:
        # Arrange
        body = RequestBody(_head(("Expect", "100-continue"), ("Content-Length", str(faker.pyint(min_value=1)))))

        # Act & Assert
        # No interim head came: the client waits for the target, not the other way round.
        body.check_complete(continued=False)

    def test_check_complete_raises_request_timeout_when_continue_came_and_body_missing(self, faker: Faker) -> None:
        # Arrange
        body = RequestBody(_head(("Expect", "100-continue"), ("Content-Length", str(faker.pyint(min_value=1)))))

        # Act & Assert
        # The target let the body come: now the client is late.
        with pytest.raises(RequestTimeout):
            body.check_complete(continued=True)

    def test_check_complete_raises_request_timeout_when_http_1_0_client_expects_continue(self, faker: Faker) -> None:
        # Arrange
        body = RequestBody(
            _head(
                ("Expect", "100-continue"),
                ("Content-Length", str(faker.pyint(min_value=1))),
                version=HTTPVersion.HTTP_1_0,
            ),
        )

        # Act & Assert
        # RFC 9110, 10.1.1: the expectation is ignored in HTTP/1.0, the body is due at once.
        with pytest.raises(RequestTimeout):
            body.check_complete(continued=False)

    def test_feed_returns_zero_when_request_has_no_body(self, faker: Faker) -> None:
        # Arrange
        body = RequestBody(_head())

        # Act
        taken = body.feed(_pipelined(faker))

        # Assert
        assert taken == 0

    @pytest.mark.parametrize("chunked", [pytest.param(False, id="content-length"), pytest.param(True, id="chunked")])
    def test_feed_returns_body_length_when_pipelined_request_follows(self, faker: Faker, chunked: bool) -> None:
        # Arrange
        data = faker.binary(length=faker.pyint(min_value=1, max_value=1024))
        if chunked:
            body = RequestBody(_head(("Transfer-Encoding", "chunked")))
            data = _chunk(data) + b"0\r\n\r\n"
        else:
            body = RequestBody(_head(("Content-Length", str(len(data)))))

        # Act
        taken = body.feed(data + _pipelined(faker))

        # Assert
        assert taken == len(data)

    def test_feed_returns_zero_when_body_already_came(self, faker: Faker) -> None:
        # Arrange
        data = faker.binary(length=faker.pyint(min_value=1, max_value=1024))
        body = RequestBody(_head(("Content-Length", str(len(data)))))
        body.feed(data)

        # Act
        taken = body.feed(_pipelined(faker))

        # Assert
        assert taken == 0

    @pytest.mark.parametrize(
        ("headers", "version"),
        [
            pytest.param([("Transfer-Encoding", "gzip")], HTTPVersion.HTTP_1_1, id="not-chunked"),
            pytest.param([("Transfer-Encoding", "chunked, gzip")], HTTPVersion.HTTP_1_1, id="chunked-not-last"),
            pytest.param([("Transfer-Encoding", "chunked, chunked")], HTTPVersion.HTTP_1_1, id="chunked-twice"),
            # The target may count it as present or not.
            pytest.param([("Transfer-Encoding", "")], HTTPVersion.HTTP_1_1, id="empty-transfer-encoding"),
            pytest.param([("Transfer-Encoding", "chunked")], HTTPVersion.HTTP_1_0, id="http-1-0"),
            # A target may go by Content-Length (RFC 9112, 6.3).
            pytest.param(
                [("Content-Length", "1000"), ("Transfer-Encoding", "chunked")],
                HTTPVersion.HTTP_1_1,
                id="with-content-length",
            ),
            pytest.param([("Content-Length", "1"), ("Content-Length", "2")], HTTPVersion.HTTP_1_1, id="conflicting"),
            pytest.param([("Content-Length", "-1")], HTTPVersion.HTTP_1_1, id="negative-length"),
            pytest.param([("Content-Length", "ten")], HTTPVersion.HTTP_1_1, id="not-a-number"),
        ],
    )
    def test_init_raises_bad_request_when_body_end_unclear(
        self,
        headers: list[tuple[str, str]],
        version: HTTPVersion,
    ) -> None:
        # Act & Assert
        # The target and the proxy could find different ends: RFC 9112, 6.3 wants a 400.
        with pytest.raises(BadRequest):
            RequestBody(_head(*headers, version=version))
