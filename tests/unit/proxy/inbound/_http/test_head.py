from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.proxy.inbound import BadRequest
from proxium.proxy.inbound._http._head import HTTPVersion, RequestHead

if TYPE_CHECKING:
    from faker import Faker


class TestRequestHead:
    @pytest.mark.parametrize("line_end", ["\r", "\n"])
    def test_from_bytes_raises_bad_request_when_line_ends_with_bare_cr_or_lf(
        self,
        faker: Faker,
        line_end: str,
    ) -> None:
        # Arrange
        raw = (
            f"GET {faker.url()} HTTP/1.1\r\n"
            f"{faker.word()}: {faker.word()}{line_end}"
            f"{faker.word()}: {faker.word()}\r\n\r\n"
        ).encode()

        # Act & Assert
        with pytest.raises(BadRequest):
            RequestHead.from_bytes(raw)

    @pytest.mark.parametrize(
        "header",
        [
            pytest.param("Transfer-Encoding : chunked", id="space-before-colon"),
            pytest.param(" Transfer-Encoding: chunked", id="obsolete-line-folding"),
        ],
    )
    def test_from_bytes_raises_bad_request_when_header_name_has_whitespace(self, faker: Faker, header: str) -> None:
        # Arrange
        raw = f"POST {faker.url()} HTTP/1.1\r\n{header}\r\n\r\n".encode()

        # Act & Assert
        with pytest.raises(BadRequest):
            RequestHead.from_bytes(raw)

    def test_to_origin_drops_proxy_authorization(self, faker: Faker) -> None:
        # Arrange
        head = RequestHead(
            method="GET",
            target=faker.url(),
            version=HTTPVersion.HTTP_1_1,
            headers=(("Proxy-Authorization", f"Basic {faker.sha256()}"),),
        )

        # Act
        origin = head.to_origin()

        # Assert
        assert origin.get("Proxy-Authorization") is None

    def test_to_origin_drops_given_headers(self, faker: Faker) -> None:
        # Arrange
        name = faker.word()
        head = RequestHead(
            method="GET",
            target=faker.url(),
            version=HTTPVersion.HTTP_1_1,
            headers=((name, faker.sha256()),),
        )

        # Act
        origin = head.to_origin(drop=[name.upper()])

        # Assert
        assert origin.get(name) is None

    def test_to_origin_drops_headers_listed_in_connection(self, faker: Faker) -> None:
        # Arrange
        name = faker.word()
        head = RequestHead(
            method="GET",
            target=faker.url(),
            version=HTTPVersion.HTTP_1_1,
            headers=(("Connection", f"keep-alive, {name.upper()}"), (name, faker.word())),
        )

        # Act
        origin = head.to_origin()

        # Assert
        assert origin.get(name) is None

    def test_to_origin_takes_host_from_target_without_userinfo(self, faker: Faker) -> None:
        # Arrange
        host = f"{faker.domain_name()}:{faker.port_number()}"
        head = RequestHead(
            method="GET",
            target=f"http://{faker.user_name()}:{faker.password()}@{host}/",
            version=HTTPVersion.HTTP_1_1,
            headers=(("Host", faker.domain_name()),),
        )

        # Act
        origin = head.to_origin()

        # Assert
        assert [value for name, value in origin.headers if name.lower() == "host"] == [host]

    def test_to_origin_returns_origin_form_target(self, faker: Faker) -> None:
        # Arrange
        path = f"/{faker.uri_path()}?{faker.word()}={faker.word()}"
        head = RequestHead(
            method="GET",
            target=f"http://{faker.domain_name()}{path}",
            version=HTTPVersion.HTTP_1_1,
        )

        # Act
        origin = head.to_origin()

        # Assert
        assert origin.target == path
