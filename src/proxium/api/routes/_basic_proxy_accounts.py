from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.basic_proxy_accounts import (
    CreateBasicProxyAccountRequest,
    CreateBasicProxyAccountResponse,
    CreateBasicProxyAccountService,
    GetBasicProxyAccountResponse,
    GetBasicProxyAccountService,
    GetBasicProxyAccountTrafficTotalRequest,
    GetBasicProxyAccountTrafficTotalResponse,
    GetBasicProxyAccountTrafficTotalService,
    ListBasicProxyAccountsResponse,
    ListBasicProxyAccountsService,
    ListBasicProxyAccountTrafficRequest,
    ListBasicProxyAccountTrafficResponse,
    ListBasicProxyAccountTrafficService,
    RevokeBasicProxyAccountService,
    UpdateBasicProxyAccountRequest,
    UpdateBasicProxyAccountResponse,
    UpdateBasicProxyAccountService,
)

from ._security import bearer_scheme

basic_proxy_accounts_router: APIRouter = APIRouter(
    prefix="/basic-proxy-accounts",
    tags=["basic-proxy-accounts"],
)


@basic_proxy_accounts_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created account with its generated credentials. The password is shown only once.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty or `expiresAt` is in the past.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_basic_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateBasicProxyAccountRequest,
) -> CreateBasicProxyAccountResponse:
    """Create a username and password proxy account, owned by the logged-in user. Both are generated."""
    service: CreateBasicProxyAccountService = CreateBasicProxyAccountService(token=credentials.credentials, data=data)
    return await service()


@basic_proxy_accounts_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of accounts.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_basic_proxy_accounts(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    query: Annotated[
        str | None,
        Query(
            description="Search by name or username.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
) -> Page[ListBasicProxyAccountsResponse]:
    """List username and password proxy accounts, newest first."""
    service: ListBasicProxyAccountsService = ListBasicProxyAccountsService(
        token=credentials.credentials,
        query=query,
    )
    return await service()


@basic_proxy_accounts_router.get(
    "/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The account.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_basic_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> GetBasicProxyAccountResponse:
    """Get a username and password proxy account."""
    service: GetBasicProxyAccountService = GetBasicProxyAccountService(token=credentials.credentials, id=account_id)
    return await service()


@basic_proxy_accounts_router.get(
    "/{account_id}/traffic",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of days with traffic, newest first. Days without traffic are left out.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
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


@basic_proxy_accounts_router.get(
    "/{account_id}/traffic/total",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Bytes sent and received in the range, zeros without traffic.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
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


@basic_proxy_accounts_router.patch(
    "/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated account.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or the body is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_basic_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    data: UpdateBasicProxyAccountRequest,
) -> UpdateBasicProxyAccountResponse:
    """Rename a username and password proxy account. The credentials are immutable."""
    service: UpdateBasicProxyAccountService = UpdateBasicProxyAccountService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@basic_proxy_accounts_router.post(
    "/{account_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The account is revoked, its credentials stop working for good.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def revoke_basic_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> None:
    """Revoke a username and password proxy account. Irreversible, create a new account instead."""
    service: RevokeBasicProxyAccountService = RevokeBasicProxyAccountService(
        token=credentials.credentials,
        id=account_id,
    )
    return await service()
