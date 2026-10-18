from __future__ import annotations

from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Final

from pytest_bdd import given, then
from sqlalchemy import update

from proxium.db import (
    BasicProxyAccountModel,
    BasicProxyAccountOutgoingIPModel,
    OutgoingIPModel,
    OutgoingMode,
    TrustedNetworkModel,
    TrustedNetworkOutgoingIPModel,
    session_manager,
)
from tests.fixtures.runners import LOOPBACK

from ._async import async_step

if TYPE_CHECKING:
    from faker import Faker

    from proxium.db import UserModel
    from proxium.proxy import Address
    from tests.fixtures.websites import Website

    from .proxy import ProxyAccount

# An IP of no host here: TEST-NET-1, reserved for documentation.
FOREIGN_ADDRESS: Final[IPv4Address] = IPv4Address("192.0.2.1")


async def _create_outgoing_ip(faker: Faker, user: UserModel, ip: IPv4Address, /) -> int:
    """Store the IP for pools, return its id."""
    outgoing_ip = OutgoingIPModel(
        ip=ip,
        name=faker.word(),
        created_by_id=user.id,
    )
    async with session_manager.session() as session:
        session.add(outgoing_ip)
        await session.commit()
    return outgoing_ip.id


async def _set_account_pool(faker: Faker, user: UserModel, account: ProxyAccount, ip: IPv4Address, /) -> None:
    outgoing_ip_id = await _create_outgoing_ip(faker, user, ip)
    async with session_manager.session() as session:
        await session.execute(
            update(BasicProxyAccountModel)
            .where(BasicProxyAccountModel.id == account.id)
            .values(outgoing_mode=OutgoingMode.POOL),
        )
        session.add(BasicProxyAccountOutgoingIPModel(basic_proxy_account_id=account.id, outgoing_ip_id=outgoing_ip_id))
        await session.commit()


@given("the account goes out from a pool of the second address")
@async_step
async def _(faker: Faker, stored_user: UserModel, proxy_account: ProxyAccount, second_address: IPv4Address) -> None:
    await _set_account_pool(faker, stored_user, proxy_account, second_address)


@given("the account goes out from a pool of an address not on this host")
@async_step
async def _(faker: Faker, stored_user: UserModel, proxy_account: ProxyAccount) -> None:
    await _set_account_pool(faker, stored_user, proxy_account, FOREIGN_ADDRESS)


@given("the account goes out from the address the client came in through")
@async_step
async def _(proxy_account: ProxyAccount) -> None:
    async with session_manager.session() as session:
        await session.execute(
            update(BasicProxyAccountModel)
            .where(BasicProxyAccountModel.id == proxy_account.id)
            .values(outgoing_mode=OutgoingMode.LISTENER),
        )
        await session.commit()


@given("the network goes out from a pool of the second address")
@async_step
async def _(faker: Faker, stored_user: UserModel, trusted_network_id: int, second_address: IPv4Address) -> None:
    outgoing_ip_id = await _create_outgoing_ip(faker, stored_user, second_address)
    async with session_manager.session() as session:
        await session.execute(
            update(TrustedNetworkModel)
            .where(TrustedNetworkModel.id == trusted_network_id)
            .values(outgoing_mode=OutgoingMode.POOL),
        )
        session.add(TrustedNetworkOutgoingIPModel(trusted_network_id=trusted_network_id, outgoing_ip_id=outgoing_ip_id))
        await session.commit()


@given("the proxy listens on the second address", target_fixture="proxy_address")
def _(second_proxy_address: Address) -> Address:
    return second_proxy_address


@then("the website sees the proxy come from the main address")
def _(website: Website) -> None:
    assert website.visitors == [str(LOOPBACK)]


@then("the website sees the proxy come from the second address")
def _(website: Website, second_address: IPv4Address) -> None:
    assert website.visitors == [str(second_address)]
