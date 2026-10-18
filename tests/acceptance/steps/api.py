from __future__ import annotations

import json
import re
import ssl
from typing import TYPE_CHECKING, Any, Final

import httpx
from pytest_bdd import given, parsers, then, when
from sqlalchemy import update

from proxium.certificates import generate_self_signed
from proxium.db import (
    GroupModel,
    GroupPermissionModel,
    Hash,
    Permission,
    UserGroupModel,
    UserModel,
    UserPermissionModel,
    session_manager,
)
from proxium.proxy import BasicCredentials

from ._async import async_step
from .proxy import PROTOCOL_CONVERTERS, ProxyProtocol, request_website

if TYPE_CHECKING:
    from collections.abc import Iterable

    from faker import Faker

    from proxium.proxy import Address
    from tests.fixtures.api import ApiClient
    from tests.fixtures.websites import Website

    from .proxy import Outcome

# `${office.id}`: a field of what a step kept under a name, deeper by dots, numbers index lists: `${plan.rules.0.id}`.
# In a path it's the value as text, in a body its JSON.
REFERENCE: Final[re.Pattern[str]] = re.compile(r"\$\{(?P<alias>\w+)(?P<path>(?:\.\w+)+)\}")
# Not a JWT at all: the API can't even read it.
INVALID_TOKEN: Final[str] = "not-a-token"  # noqa: S105, a deliberately invalid token.


def _resolve(api_client: ApiClient, match: re.Match[str], /) -> Any:
    value: Any = api_client.items[match["alias"]]
    for key in match["path"].removeprefix(".").split("."):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _format_path(api_client: ApiClient, path: str, /) -> str:
    return REFERENCE.sub(lambda match: str(_resolve(api_client, match)), path)


def _format_body(api_client: ApiClient, text: str, /) -> Any:
    return json.loads(REFERENCE.sub(lambda match: json.dumps(_resolve(api_client, match)), text))


def _contains(actual: Any, expected: Any, /) -> bool:
    """`expected` is `actual` or a part of it: objects may have more fields, lists have as many items."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_contains(item, value) for item, value in zip(actual, expected, strict=True))
        )
    return actual == expected


def _get_page_ids(response: httpx.Response, /) -> list[int]:
    return [item["id"] for item in response.json()["items"]]


async def _create_user(
    faker: Faker,
    /,
    *,
    is_superuser: bool = False,
    permissions: Iterable[Permission] = (),
    group_permissions: Iterable[Permission] = (),
) -> dict[str, Any]:
    """An active user with `permissions` of their own and `group_permissions` through a group of theirs.

    What the steps keep of them: the id, the email and the password.
    """
    password = faker.password(length=16)
    user = UserModel(
        email=faker.unique.email(),
        name=faker.first_name(),
        surname=faker.last_name(),
        password=Hash.create(password),
        is_active=True,
        is_superuser=is_superuser,
    )
    async with session_manager.session() as session:
        session.add(user)
        await session.flush()
        session.add_all(UserPermissionModel(user_id=user.id, permission=permission) for permission in permissions)
        if group_permissions:
            group = GroupModel(name=faker.unique.word())
            session.add(group)
            await session.flush()
            session.add_all(
                GroupPermissionModel(group_id=group.id, permission=permission) for permission in group_permissions
            )
            session.add(UserGroupModel(user_id=user.id, group_id=group.id))
        await session.commit()
    return {"id": user.id, "email": user.email, "password": password}


async def _log_in(api_client: ApiClient, user: dict[str, Any], /) -> None:
    response = await api_client.send("POST", "/api/tokens", json={"email": user["email"], "password": user["password"]})
    assert response.status_code == httpx.codes.OK, response.text
    api_client.token = response.json()["access"]


@given("an admin logged in to the API")
@async_step
async def _(faker: Faker, api_client: ApiClient) -> None:
    """A superuser, kept as "admin"."""
    admin = await _create_user(faker, is_superuser=True)
    api_client.items["admin"] = admin
    await _log_in(api_client, admin)


@given(parsers.parse('a user with "{permission}" logged in to the API'))
@async_step
async def _(faker: Faker, api_client: ApiClient, permission: str) -> None:
    """Kept as "user", like every user but the admin."""
    user = await _create_user(faker, permissions=[Permission(permission)])
    api_client.items["user"] = user
    await _log_in(api_client, user)


@given(parsers.parse('a user in a group with "{permission}" logged in to the API'))
@async_step
async def _(faker: Faker, api_client: ApiClient, permission: str) -> None:
    user = await _create_user(faker, group_permissions=[Permission(permission)])
    api_client.items["user"] = user
    await _log_in(api_client, user)


@given("a user without permissions logged in to the API")
@async_step
async def _(faker: Faker, api_client: ApiClient) -> None:
    user = await _create_user(faker)
    api_client.items["user"] = user
    await _log_in(api_client, user)


@given("a user")
@async_step
async def _(faker: Faker, api_client: ApiClient) -> None:
    """Not logged in."""
    api_client.items["user"] = await _create_user(faker)


@given("the user is turned off")
@async_step
async def _(api_client: ApiClient) -> None:
    user_id = api_client.items["user"]["id"]
    async with session_manager.session() as session:
        await session.execute(update(UserModel).where(UserModel.id == user_id).values(is_active=False))
        await session.commit()


@given(parsers.parse('the admin added "{alias}" at "{path}":'))
@async_step
async def _(api_client: ApiClient, alias: str, path: str, docstring: str) -> None:
    """POSTed to `path`, the answer kept as `alias`."""
    response = await api_client.send("POST", _format_path(api_client, path), json=_format_body(api_client, docstring))
    assert response.status_code == httpx.codes.CREATED, response.text
    api_client.items[alias] = response.json()


@given(parsers.parse('the admin sent {method} "{path}"'))
@async_step
async def _(api_client: ApiClient, method: str, path: str) -> None:
    response = await api_client.send(method, _format_path(api_client, path))
    assert response.is_success, response.text


@given(parsers.parse('a self-signed certificate "{alias}" for "{name}"'))
def _(api_client: ApiClient, alias: str, name: str) -> None:
    """Made aside, not uploaded yet: its PEM as the API takes it."""
    certificate, private_key = generate_self_signed([name], days=1)
    api_client.items[alias] = {"certificate": certificate, "privateKey": private_key}


@when(parsers.re(r'the (?:admin|user) sends (?P<method>[A-Z]+) "(?P<path>[^"]+)"'), target_fixture="api_response")
@async_step
async def _(api_client: ApiClient, method: str, path: str) -> httpx.Response:
    return await api_client.send(method, _format_path(api_client, path))


@when(
    parsers.re(r'the (?:admin|user) sends (?P<method>[A-Z]+) "(?P<path>[^"]+)" with:'),
    target_fixture="api_response",
)
@async_step
async def _(api_client: ApiClient, method: str, path: str, docstring: str) -> httpx.Response:
    return await api_client.send(method, _format_path(api_client, path), json=_format_body(api_client, docstring))


@when(parsers.parse('a client without a token sends {method} "{path}"'), target_fixture="api_response")
@async_step
async def _(api_client: ApiClient, method: str, path: str) -> httpx.Response:
    return await api_client.http.request(method, _format_path(api_client, path))


@when(parsers.parse('a client with an invalid token sends {method} "{path}"'), target_fixture="api_response")
@async_step
async def _(api_client: ApiClient, method: str, path: str) -> httpx.Response:
    return await api_client.send(method, _format_path(api_client, path), token=INVALID_TOKEN)


@when(parsers.parse('the client uses the access token of "{alias}"'))
def _(api_client: ApiClient, alias: str) -> None:
    api_client.token = api_client.items[alias]["access"]


@when(
    parsers.parse('the client requests the website over {protocol} with the credentials of "{alias}"'),
    target_fixture="outcome",
    converters=PROTOCOL_CONVERTERS,
)
@async_step
async def _(
    api_client: ApiClient,
    website: Website,
    running_proxy: Address,
    protocol: ProxyProtocol,
    alias: str,
) -> Outcome:
    account = api_client.items[alias]
    credentials = BasicCredentials(username=account["username"], password=account["password"])
    return await request_website(website, running_proxy, protocol, credentials=credentials)


@when(parsers.parse('the client requests the website over HTTP with the token of "{alias}"'), target_fixture="outcome")
@async_step
async def _(api_client: ApiClient, website: Website, running_proxy: Address, alias: str) -> Outcome:
    token = api_client.items[alias]["token"]
    return await request_website(website, running_proxy, ProxyProtocol.HTTP, token=token)


@given(parsers.parse('the client trusts the certificate "{alias}"'), target_fixture="client_ssl_context")
@async_step
async def _(api_client: ApiClient, alias: str) -> ssl.SSLContext:
    """As the admin shows it: its PEM from the API."""
    response = await api_client.send("GET", f"/api/certificates/{api_client.items[alias]['id']}")
    assert response.status_code == httpx.codes.OK, response.text
    return ssl.create_default_context(cadata=response.json()["certificate"])


@then(parsers.parse("the API answers {status:d}"))
def _(api_response: httpx.Response, status: int) -> None:
    assert api_response.status_code == status, api_response.text


@then("the answer has:")
def _(api_client: ApiClient, api_response: httpx.Response, docstring: str) -> None:
    expected = _format_body(api_client, docstring)
    assert _contains(api_response.json(), expected), api_response.text


@then(parsers.parse('the answer has "{field}"'))
def _(api_response: httpx.Response, field: str) -> None:
    assert api_response.json()[field], api_response.text


@then(parsers.parse('the answer has no "{field}"'))
def _(api_response: httpx.Response, field: str) -> None:
    assert field not in api_response.json(), api_response.text


# A When too: kept right after a request, to use it in the next one.
@when(parsers.parse('the answer is kept as "{alias}"'))
@then(parsers.parse('the answer is kept as "{alias}"'))
def _(api_client: ApiClient, api_response: httpx.Response, alias: str) -> None:
    api_client.items[alias] = api_response.json()


@then(parsers.parse('the answer lists "{alias}"'))
def _(api_client: ApiClient, api_response: httpx.Response, alias: str) -> None:
    assert api_client.items[alias]["id"] in _get_page_ids(api_response), api_response.text


@then(parsers.parse('the answer doesn\'t list "{alias}"'))
def _(api_client: ApiClient, api_response: httpx.Response, alias: str) -> None:
    assert api_client.items[alias]["id"] not in _get_page_ids(api_response), api_response.text
