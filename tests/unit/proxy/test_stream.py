from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from faker import Faker

    from proxium.proxy import Stream

SEPARATOR = b"\r\n\r\n"


def _receive_all(peer: socket.socket, /) -> bytes:
    """Everything `peer` gets until the other end says nothing more comes."""
    received = bytearray()
    while chunk := peer.recv(4096):
        received += chunk
    return bytes(received)


class TestStream:
    async def test_read_returns_peeked_bytes_first(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        # Peeked to choose the protocol: the protocol must still get them.
        data = faker.pystr(min_chars=2, max_chars=100).encode()
        peer_socket.sendall(data)
        await stream.peek(faker.pyint(min_value=1, max_value=len(data)))

        # Act
        read = await stream.readexactly(len(data))

        # Assert
        assert read == data

    async def test_peek_raises_incomplete_read_when_eof_before_n(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        data = faker.pystr(min_chars=1, max_chars=100).encode()
        peer_socket.sendall(data)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act & Assert
        with pytest.raises(asyncio.IncompleteReadError):
            await stream.peek(len(data) + 1)

    async def test_readexactly_returns_n_bytes_and_keeps_rest(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        first = faker.pystr(min_chars=1, max_chars=100).encode()
        rest = faker.pystr(min_chars=1, max_chars=100).encode()
        peer_socket.sendall(first + rest)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act
        read = await stream.readexactly(len(first))

        # Assert
        assert read == first
        assert await stream.read() == rest

    async def test_readexactly_raises_incomplete_read_when_eof_before_n(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        data = faker.pystr(min_chars=1, max_chars=100).encode()
        peer_socket.sendall(data)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act & Assert
        with pytest.raises(asyncio.IncompleteReadError):
            await stream.readexactly(len(data) + 1)

    async def test_readuntil_returns_through_separator_and_keeps_rest(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        # A request head and the body after it: the body is the target's.
        head = faker.pystr(min_chars=1, max_chars=100).encode() + SEPARATOR
        body = faker.pystr(min_chars=1, max_chars=100).encode()
        peer_socket.sendall(head + body)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act
        read = await stream.readuntil(SEPARATOR, limit=len(head))

        # Assert
        assert read == head
        assert await stream.read() == body

    async def test_readuntil_raises_limit_overrun_when_no_separator_within_limit(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        # A client sending a head that never ends: it must not fill the memory.
        limit = faker.pyint(min_value=1, max_value=100)
        peer_socket.sendall(faker.pystr(min_chars=limit + 1, max_chars=limit + 100).encode())

        # Act & Assert
        with pytest.raises(asyncio.LimitOverrunError):
            await stream.readuntil(SEPARATOR, limit=limit)

    async def test_readuntil_raises_limit_overrun_when_separator_beyond_limit(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        # In one chunk with the separator: the limit holds even if the separator came in the same read.
        limit = faker.pyint(min_value=1, max_value=100)
        head = faker.pystr(min_chars=limit + 1, max_chars=limit + 100).encode() + SEPARATOR
        peer_socket.sendall(head)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act & Assert
        with pytest.raises(asyncio.LimitOverrunError):
            await stream.readuntil(SEPARATOR, limit=limit)

    async def test_readuntil_raises_incomplete_read_when_eof_without_separator(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        data = faker.pystr(min_chars=1, max_chars=100).encode()
        peer_socket.sendall(data)
        peer_socket.shutdown(socket.SHUT_WR)

        # Act & Assert
        with pytest.raises(asyncio.IncompleteReadError):
            await stream.readuntil(SEPARATOR, limit=len(data) + len(SEPARATOR))

    async def test_write_eof_lets_peer_see_end_after_data(
        self,
        faker: Faker,
        stream: Stream,
        peer_socket: socket.socket,
    ) -> None:
        # Arrange
        # The relay ends a direction this way: the client waiting for the end must get it.
        data = faker.pystr(min_chars=1, max_chars=100).encode()
        stream.write(data)
        await stream.drain()

        # Act
        stream.write_eof()

        # Assert
        assert _receive_all(peer_socket) == data
