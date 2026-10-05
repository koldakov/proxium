from fastapi import APIRouter, status

from proxium.api.services.tokens import (
    GetAuthUserTokenRequest,
    GetAuthUserTokenResponse,
    GetAuthUserTokenService,
    GetRefreshedAuthUserTokenRequest,
    GetRefreshedAuthUserTokenResponse,
    GetRefreshedAuthUserTokenService,
)

tokens_router: APIRouter = APIRouter(
    prefix="/tokens",
    tags=["tokens"],
)


@tokens_router.post(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A new access and refresh token pair.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Wrong email or password, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the email is invalid.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_user_auth_token(data: GetAuthUserTokenRequest) -> GetAuthUserTokenResponse:
    """Log in with email and password."""
    service: GetAuthUserTokenService = GetAuthUserTokenService(data=data)
    return await service()


@tokens_router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A new access and refresh token pair.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The refresh token is invalid or expired, or the user is inactive or has a new password.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_refreshed_user_auth_token(data: GetRefreshedAuthUserTokenRequest) -> GetRefreshedAuthUserTokenResponse:
    """Swap a refresh token for a new pair."""
    service: GetRefreshedAuthUserTokenService = GetRefreshedAuthUserTokenService(data=data)
    return await service()
