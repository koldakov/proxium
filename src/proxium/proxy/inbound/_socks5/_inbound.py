import ipaddress
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Final

from proxium.proxy._auth import AuthenticationRequired
from proxium.proxy._connectors import (
    TargetTimeout,
    TargetUnreachable,
)
from proxium.proxy._policies import Forbidden
from proxium.proxy._types import (
    Address,
    BasicCredentials,
    Identity,
    ProxyError,
    Request,
)
from proxium.proxy.inbound._base import (
    BadRequest,
    Inbound,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from proxium.proxy._auth import Authenticate
    from proxium.proxy._stream import Stream

VERSION: Final[int] = 0x05
# Username/password subnegotiation, RFC 1929.
AUTH_VERSION: Final[int] = 0x01
# BND.ADDR and BND.PORT of a reply as IPv4 0.0.0.0:0. Clients of CONNECT don't use them.
UNSPECIFIED_BOUND: Final[bytes] = bytes(6)


class Socks5Protocol(StrEnum):
    CONNECT = "socks5"


class Method(IntEnum):
    NO_AUTH = 0x00
    USERNAME_PASSWORD = 0x02
    NO_ACCEPTABLE = 0xFF


class AuthStatus(IntEnum):
    SUCCESS = 0x00
    FAILURE = 0x01


class Command(IntEnum):
    CONNECT = 0x01


class AddressType(IntEnum):
    IPV4 = 0x01
    DOMAIN = 0x03
    IPV6 = 0x04


class Reply(IntEnum):
    SUCCEEDED = 0x00
    GENERAL_FAILURE = 0x01
    NOT_ALLOWED = 0x02
    NETWORK_UNREACHABLE = 0x03
    HOST_UNREACHABLE = 0x04
    CONNECTION_REFUSED = 0x05
    TTL_EXPIRED = 0x06
    COMMAND_NOT_SUPPORTED = 0x07
    ADDRESS_TYPE_NOT_SUPPORTED = 0x08


class NoAcceptableMethods(AuthenticationRequired):
    """The client offers no method it can pass: neither username/password nor no authentication."""


class BadCredentials(BadRequest):
    pass


class UnsupportedCommand(BadRequest):
    pass


class UnsupportedAddressType(BadRequest):
    pass


# Each error gets the reply of its closest class here. Pass your own to `Socks5Inbound` for new errors.
DEFAULT_REPLIES: Final[Mapping[type[ProxyError], Reply]] = {
    BadRequest: Reply.GENERAL_FAILURE,
    UnsupportedCommand: Reply.COMMAND_NOT_SUPPORTED,
    UnsupportedAddressType: Reply.ADDRESS_TYPE_NOT_SUPPORTED,
    Forbidden: Reply.NOT_ALLOWED,
    TargetUnreachable: Reply.HOST_UNREACHABLE,
    TargetTimeout: Reply.TTL_EXPIRED,
    ProxyError: Reply.GENERAL_FAILURE,
}


class Socks5Inbound(Inbound):
    """SOCKS5 proxy, RFC 1928: CONNECT only, username/password or no authentication."""

    def __init__(
        self,
        *,
        replies: Mapping[type[ProxyError], Reply] = DEFAULT_REPLIES,
    ) -> None:
        self._replies: dict[type[ProxyError], Reply] = dict(replies)

    def detect(self, head: bytes, /) -> bool:
        return head == bytes((VERSION,))

    async def handshake(self, stream: Stream, authenticate: Authenticate, /) -> Request:
        identity = await self._authenticate(stream, authenticate)
        return Request(
            protocol=Socks5Protocol.CONNECT,
            target=await self._read_target(stream),
            identity=identity,
        )

    async def accept(self, stream: Stream, request: Request, /) -> None:
        stream.write(self._reply(Reply.SUCCEEDED))
        await stream.drain()

    async def reject(self, stream: Stream, error: ProxyError, /) -> None:
        stream.write(self._answer_for(error))
        await stream.drain()

    async def _authenticate(self, stream: Stream, authenticate: Authenticate, /) -> Identity:
        """Authenticate with a method the client offers, username/password first."""
        # The version byte is already checked by `detect`.
        _, count = await stream.readexactly(2)
        methods = await stream.readexactly(count)
        if Method.USERNAME_PASSWORD in methods:
            return await self._authenticate_with_password(stream, authenticate)
        if Method.NO_AUTH in methods:
            return await self._authenticate_without_credentials(stream, authenticate)
        raise NoAcceptableMethods()

    async def _authenticate_with_password(self, stream: Stream, authenticate: Authenticate, /) -> Identity:
        await self._select_method(stream, Method.USERNAME_PASSWORD)
        identity = await authenticate(await self._read_credentials(stream))
        stream.write(bytes((AUTH_VERSION, AuthStatus.SUCCESS)))
        await stream.drain()
        return identity

    async def _authenticate_without_credentials(self, stream: Stream, authenticate: Authenticate, /) -> Identity:
        # Checked before the method is selected: after that the protocol has no way to refuse.
        try:
            identity = await authenticate(None)
        except AuthenticationRequired as error:
            raise NoAcceptableMethods() from error
        await self._select_method(stream, Method.NO_AUTH)
        return identity

    async def _select_method(self, stream: Stream, method: Method, /) -> None:
        stream.write(bytes((VERSION, method)))
        await stream.drain()

    async def _read_credentials(self, stream: Stream, /) -> BasicCredentials:
        version, length = await stream.readexactly(2)
        if version != AUTH_VERSION:
            raise BadCredentials(f"Unsupported auth version {version}.")
        username = await stream.readexactly(length)
        (length,) = await stream.readexactly(1)
        password = await stream.readexactly(length)
        try:
            return BasicCredentials(username.decode(), password.decode())
        except UnicodeDecodeError as error:
            raise BadCredentials("Credentials are not valid UTF-8.") from error

    async def _read_target(self, stream: Stream, /) -> Address:
        version, command, _, address_type = await stream.readexactly(4)
        if version != VERSION:
            raise BadRequest(f"Unsupported version {version}.")
        if command != Command.CONNECT:
            raise UnsupportedCommand(f"Unsupported command {command}.")
        host = await self._read_host(stream, address_type)
        port = int.from_bytes(await stream.readexactly(2))
        return Address(host, port)

    async def _read_host(self, stream: Stream, address_type: int, /) -> str:
        match address_type:
            case AddressType.IPV4:
                return str(ipaddress.IPv4Address(await stream.readexactly(4)))
            case AddressType.IPV6:
                return str(ipaddress.IPv6Address(await stream.readexactly(16)))
            case AddressType.DOMAIN:
                (length,) = await stream.readexactly(1)
                return self._decode_domain(await stream.readexactly(length))
            case _:
                raise UnsupportedAddressType(f"Unsupported address type {address_type}.")

    def _decode_domain(self, raw: bytes, /) -> str:
        try:
            domain = raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise BadRequest("Domain is not ASCII.") from error
        if not domain:
            raise BadRequest("Empty domain.")
        return domain

    def _answer_for(self, error: ProxyError, /) -> bytes:
        """Each handshake step fails with its own errors, so the error tells which message the client awaits."""
        if isinstance(error, NoAcceptableMethods):
            return bytes((VERSION, Method.NO_ACCEPTABLE))
        # Authenticators raise only `AuthenticationRequired`. Without credentials it becomes `NoAcceptableMethods`,
        # so what reaches here comes from the username/password subnegotiation.
        if isinstance(error, (AuthenticationRequired, BadCredentials)):
            return bytes((AUTH_VERSION, AuthStatus.FAILURE))
        return self._reply(self._reply_for(error))

    def _reply_for(self, error: ProxyError, /) -> Reply:
        """Reply of the closest error class in the table, general failure if none matches."""
        return next(
            (self._replies[cls] for cls in type(error).__mro__ if cls in self._replies),
            Reply.GENERAL_FAILURE,
        )

    def _reply(self, reply: Reply, /) -> bytes:
        return bytes((VERSION, reply, 0x00, AddressType.IPV4)) + UNSPECIFIED_BOUND
