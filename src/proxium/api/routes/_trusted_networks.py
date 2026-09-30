from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.trusted_networks import (
    CreateTrustedNetworkRequest,
    CreateTrustedNetworkResponse,
    CreateTrustedNetworkService,
    DeleteTrustedNetworkService,
    GetTrustedNetworkResponse,
    GetTrustedNetworkService,
    ListTrustedNetworksRequest,
    ListTrustedNetworksResponse,
    ListTrustedNetworksService,
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
            "description": "The body is malformed, e.g. the name is empty or the network has host bits set.",
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
    """Trust a network: its clients use the proxy without credentials. Owned by the logged-in user."""
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
            "description": "The new network is already trusted.",
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
    """Rename, change or turn on and off a trusted network."""
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
