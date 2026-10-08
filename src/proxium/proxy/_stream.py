from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import socket
    import ssl


class Stream:
    """Reader/writer pair with a pushback buffer, so data can be peeked before a protocol is chosen."""

    chunk_size: int = 64 * 1024

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        /,
    ) -> None:
        self._reader: asyncio.StreamReader = reader
        self._writer: asyncio.StreamWriter = writer
        self._buffer: bytearray = bytearray()

    @classmethod
    async def accept(cls, sock: socket.socket, /, *, encryption: ssl.SSLContext | None = None) -> Self:
        """Take over an accepted socket, after a TLS handshake if `encryption` is given.

        The socket belongs to the stream from here, even if the handshake fails: the loop closes it then.
        """
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
        transport, _ = await loop.connect_accepted_socket(lambda: protocol, sock, ssl=encryption)
        return cls(reader, asyncio.StreamWriter(transport, protocol, reader, loop))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def peek(self, n: int, /) -> bytes:
        """The next `n` bytes, left in the buffer for the next read."""
        while len(self._buffer) < n:
            if not await self._fill():
                raise asyncio.IncompleteReadError(bytes(self._buffer), n)
        return bytes(self._buffer[:n])

    async def read(self, n: int | None = None, /) -> bytes:
        n = self.chunk_size if n is None else n
        if self._buffer:
            return self._take(n)
        return await self._reader.read(n)

    async def readexactly(self, n: int, /) -> bytes:
        while len(self._buffer) < n:
            if not await self._fill():
                raise asyncio.IncompleteReadError(bytes(self._buffer), n)
        return self._take(n)

    async def readuntil(self, separator: bytes, /, *, limit: int) -> bytes:
        """Read up to and including `separator`, which must end within `limit` bytes."""
        while (index := self._buffer.find(separator)) < 0:
            if len(self._buffer) > limit:
                raise asyncio.LimitOverrunError("Separator is not found within limit.", len(self._buffer))
            if not await self._fill():
                raise asyncio.IncompleteReadError(bytes(self._buffer), None)
        # A single chunk may bring the separator from far beyond the limit.
        end = index + len(separator)
        if end > limit:
            raise asyncio.LimitOverrunError("Separator is found beyond limit.", end)
        return self._take(end)

    def _ensure_open(self) -> None:
        # The peer is gone: uvloop raises RuntimeError then, asyncio drops the data. Both become a reset.
        if self._writer.is_closing():
            raise ConnectionResetError("The connection is closed.")

    def write(self, data: bytes, /) -> None:
        self._ensure_open()
        self._writer.write(data)

    async def drain(self) -> None:
        await self._writer.drain()

    def write_eof(self) -> None:
        """Tell the other side nothing more comes. TLS can't half-close, so it closes the whole connection."""
        self._ensure_open()
        if self._writer.can_write_eof():
            self._writer.write_eof()
        else:
            self._writer.close()

    async def close(self) -> None:
        self._writer.close()
        with contextlib.suppress(OSError):
            await self._writer.wait_closed()

    async def _fill(self) -> bool:
        chunk = await self._reader.read(self.chunk_size)
        self._buffer += chunk
        return bool(chunk)

    def _take(self, n: int, /) -> bytes:
        data = bytes(self._buffer[:n])
        del self._buffer[:n]
        return data
