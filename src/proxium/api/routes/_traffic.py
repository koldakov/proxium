from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.traffic import (
    GetBasicProxyAccountTrafficTotalRequest,
    GetBasicProxyAccountTrafficTotalResponse,
    GetBasicProxyAccountTrafficTotalService,
    GetTokenProxyAccountTrafficTotalRequest,
    GetTokenProxyAccountTrafficTotalResponse,
    GetTokenProxyAccountTrafficTotalService,
    GetTrustedNetworkTrafficTotalRequest,
    GetTrustedNetworkTrafficTotalResponse,
    GetTrustedNetworkTrafficTotalService,
    ListBasicProxyAccountTrafficRequest,
    ListBasicProxyAccountTrafficResponse,
    ListBasicProxyAccountTrafficService,
    ListTokenProxyAccountTrafficRequest,
    ListTokenProxyAccountTrafficResponse,
    ListTokenProxyAccountTrafficService,
    ListTrustedNetworkTrafficRequest,
    ListTrustedNetworkTrafficResponse,
    ListTrustedNetworkTrafficService,
)

from ._security import bearer_scheme

# Its own domain with its own permission: seeing an account doesn't mean seeing its traffic.
traffic_router: APIRouter = APIRouter(
    prefix="/traffic",
    tags=["traffic"],
)


@traffic_router.get(
    "/basic-proxy-accounts/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of days with traffic, newest first. Days without traffic are left out.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_basic_proxy_account_traffic(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListBasicProxyAccountTrafficRequest, Depends()],
) -> Page[ListBasicProxyAccountTrafficResponse]:
    """Traffic of a username and password proxy account per UTC day. The proxy writes it about once a minute.

    - `since`, `until`: only days in this range, both inclusive.
    """
    service: ListBasicProxyAccountTrafficService = ListBasicProxyAccountTrafficService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@traffic_router.get(
    "/basic-proxy-accounts/{account_id}/total",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Bytes sent and received in the range, zeros without traffic.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_basic_proxy_account_traffic_total(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    data: Annotated[GetBasicProxyAccountTrafficTotalRequest, Depends()],
) -> GetBasicProxyAccountTrafficTotalResponse:
    """Total traffic of a username and password proxy account.

    - `since`, `until`: only days in this range, both inclusive. All time without them.
    """
    service: GetBasicProxyAccountTrafficTotalService = GetBasicProxyAccountTrafficTotalService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@traffic_router.get(
    "/token-proxy-accounts/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of days with traffic, newest first. Days without traffic are left out.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_token_proxy_account_traffic(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListTokenProxyAccountTrafficRequest, Depends()],
) -> Page[ListTokenProxyAccountTrafficResponse]:
    """Traffic of a token proxy account per UTC day. The proxy writes it about once a minute.

    - `since`, `until`: only days in this range, both inclusive.
    """
    service: ListTokenProxyAccountTrafficService = ListTokenProxyAccountTrafficService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@traffic_router.get(
    "/token-proxy-accounts/{account_id}/total",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Bytes sent and received in the range, zeros without traffic.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_token_proxy_account_traffic_total(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    data: Annotated[GetTokenProxyAccountTrafficTotalRequest, Depends()],
) -> GetTokenProxyAccountTrafficTotalResponse:
    """Total traffic of a token proxy account.

    - `since`, `until`: only days in this range, both inclusive. All time without them.
    """
    service: GetTokenProxyAccountTrafficTotalService = GetTokenProxyAccountTrafficTotalService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@traffic_router.get(
    "/trusted-networks/{network_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of days with traffic, newest first. Days without traffic are left out.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_trusted_network_traffic(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListTrustedNetworkTrafficRequest, Depends()],
) -> Page[ListTrustedNetworkTrafficResponse]:
    """Traffic of clients from a trusted network per UTC day. The proxy writes it about once a minute.

    - `since`, `until`: only days in this range, both inclusive.
    """
    service: ListTrustedNetworkTrafficService = ListTrustedNetworkTrafficService(
        token=credentials.credentials,
        id=network_id,
        data=data,
    )
    return await service()


@traffic_router.get(
    "/trusted-networks/{network_id}/total",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Bytes sent and received in the range, zeros without traffic.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `traffic.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Network not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The network id is not an integer or a query parameter is malformed, e.g. a date.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_trusted_network_traffic_total(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    network_id: int,
    data: Annotated[GetTrustedNetworkTrafficTotalRequest, Depends()],
) -> GetTrustedNetworkTrafficTotalResponse:
    """Total traffic of clients from a trusted network.

    - `since`, `until`: only days in this range, both inclusive. All time without them.
    """
    service: GetTrustedNetworkTrafficTotalService = GetTrustedNetworkTrafficTotalService(
        token=credentials.credentials,
        id=network_id,
        data=data,
    )
    return await service()
