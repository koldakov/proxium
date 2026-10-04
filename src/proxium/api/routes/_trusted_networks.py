from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.trusted_networks import (
    AddTrustedNetworkOutgoingIPService,
    CreateTrustedNetworkRequest,
    CreateTrustedNetworkResponse,
    CreateTrustedNetworkService,
    DeleteTrustedNetworkService,
    GetTrustedNetworkResponse,
    GetTrustedNetworkService,
    ListTrustedNetworkAvailableOutgoingIPsRequest,
    ListTrustedNetworkAvailableOutgoingIPsResponse,
    ListTrustedNetworkAvailableOutgoingIPsService,
    ListTrustedNetworkOutgoingIPsResponse,
    ListTrustedNetworkOutgoingIPsService,
    ListTrustedNetworksRequest,
    ListTrustedNetworksResponse,
    ListTrustedNetworksService,
    RemoveTrustedNetworkOutgoingIPService,
    UpdateTrustedNetworkRequest,
    UpdateTrustedNetworkResponse,
    UpdateTrustedNetworkService,
)

from ._security import bearer_scheme

trusted_networks_router: APIRouter = APIRouter(
    prefix="/trusted-networks",
    tags=["trusted-networks"],
)


@trusted_networks_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created network. Its clients connect without credentials right away, if active.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The network is already trusted.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the network has host bits set or a pool IP is unknown.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_trusted_network(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateTrustedNetworkRequest,
) -> CreateTrustedNetworkResponse:
    """Trust a network: its clients use the proxy without credentials. Owned by the logged-in user.

    - `outgoingMode`, `outgoingIpIds`: the pool, IPs of one family, at least one with `pool` and none with the rest.
    """
    service: CreateTrustedNetworkService = CreateTrustedNetworkService(token=credentials.credentials, data=data)
    return await service()


@trusted_networks_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of networks.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range or the network invalid.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_trusted_networks(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListTrustedNetworksRequest, Depends()],
) -> Page[ListTrustedNetworksResponse]:
    """List trusted networks, newest first. Filters combine with AND.

    - `query`: search by name or network.
    - `contains`: networks wider than this one that contain it, e.g. `10.1.2.0/24` finds `10.0.0.0/8`.
    - `within`: networks narrower than this one inside it, e.g. `10.0.0.0/8` finds `10.1.2.0/24`.
    - `isActive`: only active or only turned off networks.
    - `prefixLength`: networks with this prefix length, e.g. `0` for ones open to the whole internet.
    """
    service: ListTrustedNetworksService = ListTrustedNetworksService(token=credentials.credentials, data=data)
    return await service()


@trusted_networks_router.get(
    "/{network_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The network.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_trusted_network(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
) -> GetTrustedNetworkResponse:
    """Get a trusted network."""
    service: GetTrustedNetworkService = GetTrustedNetworkService(token=credentials.credentials, id=network_id)
    return await service()


@trusted_networks_router.patch(
    "/{network_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated network. New connections follow it right away, open ones are never cut.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The new network is already trusted, or `outgoingMode` is `pool` but the pool is empty.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer or the body is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_trusted_network(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    data: UpdateTrustedNetworkRequest,
) -> UpdateTrustedNetworkResponse:
    """Rename, change or turn on and off a trusted network, or change its outgoing IP.

    - `outgoingMode`: `pool` needs IPs in the pool, see `/outgoing-ips` of the same path.
    """
    service: UpdateTrustedNetworkService = UpdateTrustedNetworkService(
        token=credentials.credentials,
        id=network_id,
        data=data,
    )
    return await service()


@trusted_networks_router.delete(
    "/{network_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The network is deleted, its new connections need credentials again.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The network has traffic: its history is kept, turn the network off instead.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def delete_trusted_network(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
) -> None:
    """Delete a trusted network without traffic. Open connections from it are never cut."""
    service: DeleteTrustedNetworkService = DeleteTrustedNetworkService(
        token=credentials.credentials,
        id=network_id,
    )
    return await service()


@trusted_networks_router.get(
    "/{network_id}/outgoing-ips/available",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of IPs the pool can take: not in it yet and of its family.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer or a query parameter is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_trusted_network_available_outgoing_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListTrustedNetworkAvailableOutgoingIPsRequest, Depends()],
) -> Page[ListTrustedNetworkAvailableOutgoingIPsResponse]:
    """Outgoing IPs to add to the pool of a trusted network.

    In the order they were added to the server. Leaves out the IPs already in the pool and, once it has one,
    the IPs of the other family.

    - `query`: search by name or IP.
    """
    service: ListTrustedNetworkAvailableOutgoingIPsService = ListTrustedNetworkAvailableOutgoingIPsService(
        token=credentials.credentials,
        id=network_id,
        data=data,
    )
    return await service()


@trusted_networks_router.get(
    "/{network_id}/outgoing-ips",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of the outgoing IP pool, in the order the IPs were added to the server.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer or the page parameters are malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_trusted_network_outgoing_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
) -> Page[ListTrustedNetworkOutgoingIPsResponse]:
    """The outgoing IP pool of a trusted network. Used in the `pool` outgoing mode only."""
    service: ListTrustedNetworkOutgoingIPsService = ListTrustedNetworkOutgoingIPsService(
        token=credentials.credentials,
        id=network_id,
    )
    return await service()


@trusted_networks_router.put(
    "/{network_id}/outgoing-ips/{outgoing_ip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The IP is in the pool, new connections may go out from it right away.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network or outgoing IP not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The pool is full.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "An id is not an integer, or the pool is of the other IP family.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def add_trusted_network_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    outgoing_ip_id: int,
) -> None:
    """Add an IP to the outgoing IP pool of a trusted network. Adding it again changes nothing.

    A pool takes IPs of one family, IPv4 or IPv6.
    """
    service: AddTrustedNetworkOutgoingIPService = AddTrustedNetworkOutgoingIPService(
        token=credentials.credentials,
        id=network_id,
        outgoing_ip_id=outgoing_ip_id,
    )
    return await service()


@trusted_networks_router.delete(
    "/{network_id}/outgoing-ips/{outgoing_ip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The IP is out of the pool. Open connections from it are never cut.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found, or the IP is not in its pool.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The last IP of a pool in use: switch the outgoing mode first.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "An id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def remove_trusted_network_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    outgoing_ip_id: int,
) -> None:
    """Take an IP out of the outgoing IP pool of a trusted network. The IP itself stays."""
    service: RemoveTrustedNetworkOutgoingIPService = RemoveTrustedNetworkOutgoingIPService(
        token=credentials.credentials,
        id=network_id,
        outgoing_ip_id=outgoing_ip_id,
    )
    return await service()
