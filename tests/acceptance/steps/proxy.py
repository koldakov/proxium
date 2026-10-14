from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import httpx
from pytest_bdd import given, parsers, then, when

from proxium.auth import USERNAME_PREFIX
from proxium.db import BasicProxyAccountModel, Hash, session_manager
from proxium.proxy import BasicCredentials

from ._async import async_step

if TYPE_CHECKING:
    from faker import Faker

    from proxium.db import UserModel
    from proxium.proxy import Address
    from tests.fixtures.websites import Website

# What a client gets back: an answer, or a proxy that refused to connect it at all.
type Outcome = httpx.Response | httpx.ProxyError


class ProxyProtocol(StrEnum):
    """How the client talks to the proxy, by name in the steps. Values are the proxy URL schemes."""

    HTTP = "http"
    SOCKS5 = "socks5"


def _parse_protocol(name: str, /) -> ProxyProtocol:
    # By name: `ProxyProtocol.__getitem__` of a StrEnum is `str.__getitem__`.
    return ProxyProtocol[name]


PROTOCOL_CONVERTERS = {
    "protocol": _parse_protocol,
}


async def _request(
    website: Website,
    proxy: Address,
    protocol: ProxyProtocol,
    *,
    credentials: BasicCredentials | None = None,
) -> Outcome:
    auth = None if credentials is None else (credentials.username, credentials.password)
    # trust_env off: proxy variables of the machine running the tests mustn't take over.
    async with httpx.AsyncClient(
        proxy=httpx.Proxy(f"{protocol}://{proxy}", auth=auth),
        trust_env=False,
    ) as client:
        try:
            return await client.get(website.url)
        except httpx.ProxyError as error:
            return error


@given("a website")
def _(website: Website) -> None:
    """Started by the fixture."""


@given("the proxy is running")
def _(running_proxy: Address) -> None:
    """Started by the fixture."""


@given("a proxy account", target_fixture="proxy_account")
@async_step
async def _(faker: Faker, stored_user: UserModel) -> BasicCredentials:
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
    return credentials


@when(
    parsers.parse("the client requests the website over {protocol} with the account credentials"),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(
    website: Website,
    running_proxy: Address,
    proxy_account: BasicCredentials,
    protocol: ProxyProtocol,
) -> Outcome:
    return await _request(website, running_proxy, protocol, credentials=proxy_account)


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
    proxy_account: BasicCredentials,
    protocol: ProxyProtocol,
) -> Outcome:
    credentials = BasicCredentials(username=proxy_account.username, password=faker.password())
    return await _request(website, running_proxy, protocol, credentials=credentials)


@when(
    parsers.parse("the client requests the website over {protocol} without credentials"),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(website: Website, running_proxy: Address, protocol: ProxyProtocol) -> Outcome:
    return await _request(website, running_proxy, protocol)


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
