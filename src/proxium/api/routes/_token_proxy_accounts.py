from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.token_proxy_accounts import (
    AddTokenProxyAccountOutgoingIPService,
    CreateTokenProxyAccountRequest,
    CreateTokenProxyAccountResponse,
    CreateTokenProxyAccountService,
    GetTokenProxyAccountResponse,
    GetTokenProxyAccountService,
    ListTokenProxyAccountAvailableOutgoingIPsRequest,
    ListTokenProxyAccountAvailableOutgoingIPsResponse,
    ListTokenProxyAccountAvailableOutgoingIPsService,
    ListTokenProxyAccountOutgoingIPsResponse,
    ListTokenProxyAccountOutgoingIPsService,
    ListTokenProxyAccountsResponse,
    ListTokenProxyAccountsService,
    RemoveTokenProxyAccountOutgoingIPService,
    RevokeTokenProxyAccountService,
    UpdateTokenProxyAccountRequest,
    UpdateTokenProxyAccountResponse,
    UpdateTokenProxyAccountService,
)

from ._security import bearer_scheme

token_proxy_accounts_router: APIRouter = APIRouter(
    prefix="/token-proxy-accounts",
    tags=["token-proxy-accounts"],
)


@token_proxy_accounts_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created account with its token. The token is shown only once.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.add`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. `expiresAt` is in the past or a pool IP is unknown.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_token_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateTokenProxyAccountRequest,
) -> CreateTokenProxyAccountResponse:
    """Create a bearer token proxy account, owned by the logged-in user.

    - `outgoingMode`, `outgoingIpIds`: the pool, IPs of one family, at least one with `pool` and none with the rest.
    """
    service: CreateTokenProxyAccountService = CreateTokenProxyAccountService(token=credentials.credentials, data=data)
    return await service()


@token_proxy_accounts_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of accounts.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_token_proxy_accounts(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    query: Annotated[
        str | None,
        Query(
            description="Search by name or key.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
) -> Page[ListTokenProxyAccountsResponse]:
    """List bearer token proxy accounts, newest first."""
    service: ListTokenProxyAccountsService = ListTokenProxyAccountsService(
        token=credentials.credentials,
        query=query,
    )
    return await service()


@token_proxy_accounts_router.get(
    "/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The account.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.view`.",
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
async def get_token_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> GetTokenProxyAccountResponse:
    """Get a bearer token proxy account."""
    service: GetTokenProxyAccountService = GetTokenProxyAccountService(token=credentials.credentials, id=account_id)
    return await service()


@token_proxy_accounts_router.patch(
    "/{account_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated account.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.change`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "`outgoingMode` is `pool` but the pool is empty.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or the body is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_token_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    data: UpdateTokenProxyAccountRequest,
) -> UpdateTokenProxyAccountResponse:
    """Rename a bearer token proxy account or change its outgoing IP. The token is immutable.

    - `outgoingMode`: `pool` needs IPs in the pool, see `/outgoing-ips` of the same path.
    """
    service: UpdateTokenProxyAccountService = UpdateTokenProxyAccountService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@token_proxy_accounts_router.post(
    "/{account_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The account is revoked, its token stops working for good.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.revoke`.",
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
async def revoke_token_proxy_account(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> None:
    """Revoke a bearer token proxy account. Irreversible, create a new account instead."""
    service: RevokeTokenProxyAccountService = RevokeTokenProxyAccountService(
        token=credentials.credentials,
        id=account_id,
    )
    return await service()


@token_proxy_accounts_router.get(
    "/{account_id}/outgoing-ips/available",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of IPs the pool can take: not in it yet and of its family.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.change` or `outgoing_ips.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or a query parameter is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_token_proxy_account_available_outgoing_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    # `Depends`, not `Query`: next to the pagination params, FastAPI documents a `Query` model as one `data` param.
    data: Annotated[ListTokenProxyAccountAvailableOutgoingIPsRequest, Depends()],
) -> Page[ListTokenProxyAccountAvailableOutgoingIPsResponse]:
    """Outgoing IPs to add to the pool of a bearer token proxy account.

    In the order they were added to the server. Leaves out the IPs already in the pool and, once it has one,
    the IPs of the other family.

    - `query`: search by name or IP.
    """
    service: ListTokenProxyAccountAvailableOutgoingIPsService = ListTokenProxyAccountAvailableOutgoingIPsService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@token_proxy_accounts_router.get(
    "/{account_id}/outgoing-ips",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of the outgoing IP pool, in the order the IPs were added to the server.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The account id is not an integer or the page parameters are malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_token_proxy_account_outgoing_ips(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> Page[ListTokenProxyAccountOutgoingIPsResponse]:
    """The outgoing IP pool of a bearer token proxy account. Used in the `pool` outgoing mode only."""
    service: ListTokenProxyAccountOutgoingIPsService = ListTokenProxyAccountOutgoingIPsService(
        token=credentials.credentials,
        id=account_id,
    )
    return await service()


@token_proxy_accounts_router.put(
    "/{account_id}/outgoing-ips/{outgoing_ip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The IP is in the pool, new connections may go out from it right away.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.change`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account or outgoing IP not found.",
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
async def add_token_proxy_account_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    outgoing_ip_id: int,
) -> None:
    """Add an IP to the outgoing IP pool of a bearer token proxy account. Adding it again changes nothing.

    A pool takes IPs of one family, IPv4 or IPv6.
    """
    service: AddTokenProxyAccountOutgoingIPService = AddTokenProxyAccountOutgoingIPService(
        token=credentials.credentials,
        id=account_id,
        outgoing_ip_id=outgoing_ip_id,
    )
    return await service()


@token_proxy_accounts_router.delete(
    "/{account_id}/outgoing-ips/{outgoing_ip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The IP is out of the pool. Open connections from it are never cut.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `token_proxy_accounts.change`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found, or the IP is not in its pool.",
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
async def remove_token_proxy_account_outgoing_ip(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
    outgoing_ip_id: int,
) -> None:
    """Take an IP out of the outgoing IP pool of a bearer token proxy account. The IP itself stays."""
    service: RemoveTokenProxyAccountOutgoingIPService = RemoveTokenProxyAccountOutgoingIPService(
        token=credentials.credentials,
        id=account_id,
        outgoing_ip_id=outgoing_ip_id,
    )
    return await service()
