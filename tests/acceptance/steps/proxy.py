from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import httpx
from pytest_bdd import given, parsers, then, when

from proxium.auth import USERNAME_PREFIX
from proxium.db import BasicProxyAccountModel, Hash, session_manager
from proxium.proxy import BasicCredentials

from ._async import async_step

if TYPE_CHECKING:
    import ssl
    from collections.abc import Callable

    from faker import Faker

    from proxium.db import UserModel
    from proxium.proxy import Address
    from tests.fixtures.websites import Website

# What a client gets back: an answer, or no answer at all, e.g. a proxy that refused to connect it or a failed TLS
# handshake.
type Outcome = httpx.Response | httpx.TransportError


class ProxyProtocol(StrEnum):
    """How the client talks to the proxy, by name in the steps. Values are the proxy URL schemes.

    HTTPS is the HTTP proxy wrapped in TLS: the website itself is plain HTTP either way.
    """

    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


@dataclass(frozen=True, slots=True)
class ProxyAccount:
    """A basic proxy account in the database and the credentials it was created with."""

    id: int
    credentials: BasicCredentials


def _parse_protocol(name: str, /) -> ProxyProtocol:
    # By name: `ProxyProtocol.__getitem__` of a StrEnum is `str.__getitem__`.
    return ProxyProtocol[name]


PROTOCOL_CONVERTERS = {
    "protocol": _parse_protocol,
}


# Keyword-only after the target, one per way a client may come.
async def request_website(  # noqa: PLR0913
    website: Website,
    proxy: Address,
    protocol: ProxyProtocol,
    *,
    credentials: BasicCredentials | None = None,
    token: str | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> Outcome:
    """With a username and password, or a bearer token over HTTP. `ssl_context` is what the client trusts over HTTPS."""
    auth = None if credentials is None else (credentials.username, credentials.password)
    headers = None if token is None else {"Proxy-Authorization": f"Bearer {token}"}
    # httpx refuses a context for a proxy it doesn't reach over TLS.
    if protocol != ProxyProtocol.HTTPS:
        ssl_context = None
    # trust_env off: proxy variables of the machine running the tests mustn't take over.
    async with httpx.AsyncClient(
        proxy=httpx.Proxy(f"{protocol}://{proxy}", auth=auth, headers=headers, ssl_context=ssl_context),
        trust_env=False,
    ) as client:
        try:
            return await client.get(website.url)
        except httpx.TransportError as error:
            return error


@given("a website")
def _(website: Website) -> None:
    """Started by the fixture."""


@given(parsers.parse("a website of {size:d} bytes"), target_fixture="website")
def _(faker: Faker, website_factory: Callable[[str], Website], size: int) -> Website:
    return website_factory(faker.pystr(min_chars=size, max_chars=size))


@given("the proxy is running")
def _(running_proxy: Address) -> None:
    """Started by the fixture."""


@given("a proxy account", target_fixture="proxy_account")
@async_step
async def _(faker: Faker, stored_user: UserModel) -> ProxyAccount:
    credentials = BasicCredentials(username=f"{USERNAME_PREFIX}{faker.uuid4()}", password=faker.password())
    account = BasicProxyAccountModel(
        name=faker.word(),
        username=credentials.username,
        password=Hash.create(credentials.password),
        expires_at=None,
        created_by_id=stored_user.id,
    )
    async with session_manager.session() as session:
        session.add(account)
        await session.commit()
    return ProxyAccount(id=account.id, credentials=credentials)


@when(
    parsers.parse("the client requests the website over {protocol} with the account credentials"),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(
    website: Website,
    running_proxy: Address,
    proxy_account: ProxyAccount,
    client_ssl_context: ssl.SSLContext,
    protocol: ProxyProtocol,
) -> Outcome:
    return await request_website(
        website,
        running_proxy,
        protocol,
        credentials=proxy_account.credentials,
        ssl_context=client_ssl_context,
    )


@when(
    parsers.parse("the client requests the website over {protocol} with a wrong password"),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(
    faker: Faker,
    website: Website,
    running_proxy: Address,
    proxy_account: ProxyAccount,
    protocol: ProxyProtocol,
) -> Outcome:
    credentials = BasicCredentials(username=proxy_account.credentials.username, password=faker.password())
    return await request_website(website, running_proxy, protocol, credentials=credentials)


@when(
    parsers.parse("the client requests the website over {protocol} without credentials"),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(website: Website, running_proxy: Address, protocol: ProxyProtocol) -> Outcome:
    return await request_website(website, running_proxy, protocol)


@then("the client gets the website")
def _(website: Website, outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.Response)
    assert outcome.status_code == httpx.codes.OK
    assert outcome.text == website.body


@then("the proxy asks for credentials")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.Response)
    assert outcome.status_code == httpx.codes.PROXY_AUTHENTICATION_REQUIRED
    assert "Proxy-Authenticate" in outcome.headers


@then("the proxy refuses the connection")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.ProxyError)


@then("the proxy can't reach the website")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.Response)
    assert outcome.status_code == httpx.codes.BAD_GATEWAY
