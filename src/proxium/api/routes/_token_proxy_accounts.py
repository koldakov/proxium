from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.token_proxy_accounts import (
    CreateTokenProxyAccountRequest,
    CreateTokenProxyAccountResponse,
    CreateTokenProxyAccountService,
    GetTokenProxyAccountResponse,
    GetTokenProxyAccountService,
    ListTokenProxyAccountsResponse,
    ListTokenProxyAccountsService,
    UpdateTokenProxyAccountRequest,
    UpdateTokenProxyAccountResponse,
    UpdateTokenProxyAccountService,
    UpdateTokenProxyAccountTokenResponse,
    UpdateTokenProxyAccountTokenService,
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
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Name is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty.",
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
    """Create a bearer token proxy account, owned by the logged-in user."""
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
async def list_token_proxy_accounts(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    query: Annotated[
        str | None,
        Query(
            description="Search by name.",
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
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Account not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Name is already taken.",
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
    """Update a bearer token proxy account. Only the given fields change, the token has its own endpoint."""
    service: UpdateTokenProxyAccountService = UpdateTokenProxyAccountService(
        token=credentials.credentials,
        id=account_id,
        data=data,
    )
    return await service()


@token_proxy_accounts_router.post(
    "/{account_id}/token",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The new token, shown only once. The old one stops working.",
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
async def update_token_proxy_account_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    account_id: int,
) -> UpdateTokenProxyAccountTokenResponse:
    """Issue a new token for a bearer token proxy account."""
    service: UpdateTokenProxyAccountTokenService = UpdateTokenProxyAccountTokenService(
        token=credentials.credentials,
        id=account_id,
    )
    return await service()
