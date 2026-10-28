from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.proxy_instances import (
    DeregisterProxyInstanceService,
    GetProxyInstanceCountsResponse,
    GetProxyInstanceCountsService,
    ListProxyInstanceIPsResponse,
    ListProxyInstanceIPsService,
    ListProxyInstancesRequest,
    ListProxyInstancesResponse,
    ListProxyInstancesService,
)

from ._security import bearer_scheme

proxy_instances_router: APIRouter = APIRouter(
    prefix="/proxy-instances",
    tags=["proxy instances"],
)


@proxy_instances_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of proxy instances.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `proxy_instances.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. an unknown status or the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_proxy_instances(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListProxyInstancesRequest, Depends()],
) -> Page[ListProxyInstancesResponse]:
    """List proxy instances, newest first, deregistered ones left out.

    - `status`: `pending` starting, `running` serving, `stopped` shut down, `unknown` missed its reports: crashed,
      hung or cut off from the database.
    """
    service: ListProxyInstancesService = ListProxyInstancesService(token=credentials.credentials, data=data)
    return await service()


@proxy_instances_router.get(
    "/counts",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The number of proxy instances in each status.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `proxy_instances.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The request is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_proxy_instance_counts(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> GetProxyInstanceCountsResponse:
    """Count proxy instances by status, deregistered ones left out."""
    service: GetProxyInstanceCountsService = GetProxyInstanceCountsService(token=credentials.credentials)
    return await service()


@proxy_instances_router.get(
    "/{proxy_instance_id}/ips",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of the instance's IPs.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `proxy_instances.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Proxy instance not found, or deregistered.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The proxy instance id is not an integer, or the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_proxy_instance_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    proxy_instance_id: int,
) -> Page[ListProxyInstanceIPsResponse]:
    """List IPs on the interfaces of a proxy instance as of its last report, IPv4 first: the outgoing IPs it can
    connect from. In Docker bridge networking these are the container's IPs, not the host's.
    """
    service: ListProxyInstanceIPsService = ListProxyInstanceIPsService(
        token=credentials.credentials,
        id=proxy_instance_id,
    )
    return await service()


@proxy_instances_router.post(
    "/{proxy_instance_id}/deregister",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The instance is left out of lists until its process reports again.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `proxy_instances.deregister`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Proxy instance not found, or deregistered already.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "The instance is pending or running: only stopped and unknown ones can be deregistered.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The proxy instance id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def deregister_proxy_instance(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    proxy_instance_id: int,
) -> None:
    """Take a stopped or unknown instance off the lists, e.g. a removed server. Nothing is deleted: if its process
    reports again, the instance registers again.
    """
    service: DeregisterProxyInstanceService = DeregisterProxyInstanceService(
        token=credentials.credentials,
        id=proxy_instance_id,
    )
    return await service()
