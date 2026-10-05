from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.outgoing_ips import (
    CreateOutgoingIPRequest,
    CreateOutgoingIPResponse,
    CreateOutgoingIPService,
    DeleteOutgoingIPService,
    GetOutgoingIPResponse,
    GetOutgoingIPService,
    ListOutgoingIPsRequest,
    ListOutgoingIPsResponse,
    ListOutgoingIPsService,
    UpdateOutgoingIPRequest,
    UpdateOutgoingIPResponse,
    UpdateOutgoingIPService,
)

from ._security import bearer_scheme

outgoing_ips_router: APIRouter = APIRouter(
    prefix="/outgoing-ips",
    tags=["outgoing-ips"],
)


@outgoing_ips_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The added IP, ready for pools.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `outgoing_ips.add`.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The IP is already added.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty or the IP invalid.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateOutgoingIPRequest,
) -> CreateOutgoingIPResponse:
    """Add an IP of the proxy server to go out from. Owned by the logged-in user.

    Not checked against the server: an IP that isn't on it fails every connection of the pools with it.
    """
    service: CreateOutgoingIPService = CreateOutgoingIPService(token=credentials.credentials, data=data)
    return await service()


@outgoing_ips_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of IPs.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `outgoing_ips.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size or the version is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_outgoing_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListOutgoingIPsRequest, Depends()],
) -> Page[ListOutgoingIPsResponse]:
    """List outgoing IPs, newest first. Filters combine with AND.

    - `query`: search by name or IP.
    - `version`: only IPv4 or only IPv6, `4` or `6`.
    """
    service: ListOutgoingIPsService = ListOutgoingIPsService(token=credentials.credentials, data=data)
    return await service()


@outgoing_ips_router.get(
    "/{outgoing_ip_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The IP.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `outgoing_ips.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "IP not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The IP id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    outgoing_ip_id: int,
) -> GetOutgoingIPResponse:
    """Get an outgoing IP."""
    service: GetOutgoingIPService = GetOutgoingIPService(token=credentials.credentials, id=outgoing_ip_id)
    return await service()


@outgoing_ips_router.patch(
    "/{outgoing_ip_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated IP. New connections of its pools use it right away, open ones are never cut.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `outgoing_ips.change`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "IP not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The new IP is already added.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The IP id is not an integer, the body is malformed or the IP changes its family.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    outgoing_ip_id: int,
    data: UpdateOutgoingIPRequest,
) -> UpdateOutgoingIPResponse:
    """Rename or change an outgoing IP within its family. Pools with it go out from the new one."""
    service: UpdateOutgoingIPService = UpdateOutgoingIPService(
        token=credentials.credentials,
        id=outgoing_ip_id,
        data=data,
    )
    return await service()


@outgoing_ips_router.delete(
    "/{outgoing_ip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The IP is deleted.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `outgoing_ips.delete`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "IP not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The IP is in pools: take it out of them first.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The IP id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def delete_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    outgoing_ip_id: int,
) -> None:
    """Delete an outgoing IP that is in no pool."""
    service: DeleteOutgoingIPService = DeleteOutgoingIPService(
        token=credentials.credentials,
        id=outgoing_ip_id,
    )
    return await service()
