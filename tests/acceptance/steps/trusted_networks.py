from __future__ import annotations

from ipaddress import IPv4Network
from typing import TYPE_CHECKING, Final

from pytest_bdd import given

from proxium.db import TrustedNetworkModel, session_manager

from ._async import async_step

if TYPE_CHECKING:
    from faker import Faker

    from proxium.db import UserModel

# Where the client connects from: the proxy runs on loopback, see `tests.fixtures.runners.running_proxy`.
CLIENT_NETWORK: Final[IPv4Network] = IPv4Network("127.0.0.0/8")
# A network without the client: TEST-NET-1, reserved for documentation, nobody connects from it.
OTHER_NETWORK: Final[IPv4Network] = IPv4Network("192.0.2.0/24")


async def _trust(faker: Faker, user: UserModel, network: IPv4Network, /, *, is_active: bool = True) -> int:
    """Store the network as trusted, return its id."""
    trusted = TrustedNetworkModel(
        network=network,
        name=faker.word(),
        is_active=is_active,
        created_by_id=user.id,
    )
    async with session_manager.session() as session:
        session.add(trusted)
        await session.commit()
    return trusted.id


@given("the client's network is trusted", target_fixture="trusted_network_id")
@async_step
async def _(faker: Faker, stored_user: UserModel) -> int:
    return await _trust(faker, stored_user, CLIENT_NETWORK)


@given("the client's network is trusted but turned off", target_fixture="trusted_network_id")
@async_step
async def _(faker: Faker, stored_user: UserModel) -> int:
    return await _trust(faker, stored_user, CLIENT_NETWORK, is_active=False)


@given("another network is trusted", target_fixture="trusted_network_id")
@async_step
async def _(faker: Faker, stored_user: UserModel) -> int:
    return await _trust(faker, stored_user, OTHER_NETWORK)
