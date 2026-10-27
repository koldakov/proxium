from __future__ import annotations

import asyncio
import base64
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

import httpx
from pytest_bdd import given, parsers, then
from sqlalchemy import update

from proxium.core import api_settings
from proxium.db import (
    BasicProxyAccountPolicyModel,
    Direction,
    LimitScope,
    PolicyConnectionLimitModel,
    PolicyModel,
    PolicyRuleModel,
    PolicySpeedLimitModel,
    PolicyTrafficQuotaModel,
    QuotaPeriod,
    TrustedNetworkPolicyModel,
    session_manager,
)

from ._async import async_step

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest
    from faker import Faker

    from proxium.db import UserModel
    from proxium.proxy import Address
    from tests.fixtures.websites import Website

    from .proxy import Outcome, ProxyAccount

# The protocol SOCKS5 requests come in over, as rule conditions name it.
SOCKS5_PROTOCOL: Final[str] = "socks5"


def _create_connection_limit_rule(max_connections: int, /) -> PolicyRuleModel:
    return PolicyRuleModel(
        connection_limits=[
            PolicyConnectionLimitModel(
                scope=LimitScope.IDENTITY,
                max_connections=max_connections,
            ),
        ],
    )


def _create_traffic_quota_rule(max_bytes: int, /) -> PolicyRuleModel:
    return PolicyRuleModel(
        traffic_quotas=[
            PolicyTrafficQuotaModel(
                scope=LimitScope.IDENTITY,
                direction=Direction.BOTH,
                max_bytes=max_bytes,
                period=QuotaPeriod.TOTAL,
                period_length=1,
            ),
        ],
    )


def _create_speed_limit_rule(rate: int, /) -> PolicyRuleModel:
    """A burst of one second: the first `rate` bytes go at once."""
    return PolicyRuleModel(
        speed_limits=[
            PolicySpeedLimitModel(
                scope=LimitScope.IDENTITY,
                direction=Direction.BOTH,
                rate=rate,
                burst=rate,
            ),
        ],
    )


# A policy's only rule by how the steps say it, per identity and always applying: e.g. "a traffic quota of 1 byte".
RULE_PATTERNS: Final[tuple[tuple[re.Pattern[str], Callable[[int], PolicyRuleModel]], ...]] = (
    (re.compile(r"a connection limit of (\d+)"), _create_connection_limit_rule),
    (re.compile(r"a traffic quota of (\d+) bytes?"), _create_traffic_quota_rule),
    (re.compile(r"a speed limit of (\d+) bytes per second"), _create_speed_limit_rule),
)


def _parse_rule(text: str, /) -> PolicyRuleModel:
    for pattern, create in RULE_PATTERNS:
        if match := pattern.fullmatch(text):
            return create(int(match[1]))
    raise ValueError(f"Unknown limit: {text!r}.")


RULE_CONVERTERS = {
    "rule": _parse_rule,
}


async def _create_policy(
    faker: Faker,
    user: UserModel,
    rule: PolicyRuleModel,
    /,
    *,
    is_global: bool = False,
) -> PolicyModel:
    rule.position = 0
    rule.name = faker.word()
    policy = PolicyModel(
        name=faker.word(),
        is_global=is_global,
        created_by_id=user.id,
        rules=[rule],
    )
    async with session_manager.session() as session:
        session.add(policy)
        await session.commit()
    return policy


def _encode_basic(account: ProxyAccount, /) -> str:
    pair = f"{account.credentials.username}:{account.credentials.password}"
    return base64.b64encode(pair.encode()).decode()


async def _open_tunnel(website: Website, proxy: Address, account: ProxyAccount, /) -> asyncio.StreamWriter:
    """CONNECT to the website and leave the tunnel open, sending nothing through it."""
    url = httpx.URL(website.url)
    authority = f"{url.host}:{url.port}"
    request = (
        f"CONNECT {authority} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        f"Proxy-Authorization: Basic {_encode_basic(account)}\r\n"
        "\r\n"
    )
    reader, writer = await asyncio.open_connection(proxy.host, proxy.port)
    writer.write(request.encode())
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 200 "), head
    return writer


@given(
    parsers.parse("the account has a policy with {rule}"),
    target_fixture="policy_id",
    converters=RULE_CONVERTERS,
)
@async_step
async def _(faker: Faker, stored_user: UserModel, proxy_account: ProxyAccount, rule: PolicyRuleModel) -> int:
    policy = await _create_policy(faker, stored_user, rule)
    async with session_manager.session() as session:
        session.add(BasicProxyAccountPolicyModel(policy_id=policy.id, basic_proxy_account_id=proxy_account.id))
        await session.commit()
    return policy.id


@given(
    parsers.parse("the network has a policy with {rule}"),
    target_fixture="policy_id",
    converters=RULE_CONVERTERS,
)
@async_step
async def _(faker: Faker, stored_user: UserModel, trusted_network_id: int, rule: PolicyRuleModel) -> int:
    policy = await _create_policy(faker, stored_user, rule)
    async with session_manager.session() as session:
        session.add(TrustedNetworkPolicyModel(policy_id=policy.id, trusted_network_id=trusted_network_id))
        await session.commit()
    return policy.id


@given(
    parsers.parse("a global policy with {rule}"),
    target_fixture="policy_id",
    converters=RULE_CONVERTERS,
)
@async_step
async def _(faker: Faker, stored_user: UserModel, rule: PolicyRuleModel) -> int:
    policy = await _create_policy(faker, stored_user, rule, is_global=True)
    return policy.id


@given(parsers.parse("the API allows {count:d} global policies at most"))
def _(request: pytest.FixtureRequest, count: int) -> None:
    """For the rest of the scenario: the API reads the cap on each request."""
    patcher = patch.object(api_settings, "global_policies_max", count)
    patcher.start()
    request.addfinalizer(patcher.stop)


@given("the policy is turned off")
@async_step
async def _(policy_id: int) -> None:
    async with session_manager.session() as session:
        await session.execute(update(PolicyModel).where(PolicyModel.id == policy_id).values(is_active=False))
        await session.commit()


@given("the policy applies over SOCKS5 only")
@async_step
async def _(policy_id: int) -> None:
    condition = {"kind": "protocol", "protocols": [SOCKS5_PROTOCOL]}
    async with session_manager.session() as session:
        await session.execute(
            update(PolicyRuleModel).where(PolicyRuleModel.policy_id == policy_id).values(condition=condition),
        )
        await session.commit()


@given("the client holds a tunnel to the website with the account credentials")
@async_step
async def _(
    website: Website,
    running_proxy: Address,
    proxy_account: ProxyAccount,
    tunnels: list[asyncio.StreamWriter],
) -> None:
    tunnels.append(await _open_tunnel(website, running_proxy, proxy_account))


@then("the proxy refuses with too many connections")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.Response)
    assert outcome.status_code == httpx.codes.TOO_MANY_REQUESTS
    assert outcome.reason_phrase == "Too Many Connections"


@then("the proxy refuses with the quota exceeded")
def _(outcome: Outcome) -> None:
    assert isinstance(outcome, httpx.Response)
    assert outcome.status_code == httpx.codes.TOO_MANY_REQUESTS
    assert outcome.reason_phrase == "Quota Exceeded"


@then(parsers.parse("the download takes at least {seconds:d} seconds"))
def _(outcome: Outcome, seconds: int) -> None:
    assert isinstance(outcome, httpx.Response)
    # From sending the request till the whole body is read.
    assert outcome.elapsed >= timedelta(seconds=seconds)
