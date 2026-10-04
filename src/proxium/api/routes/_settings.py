from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.settings import (
    GetSettingsResponse,
    GetSettingsService,
    UpdateSettingsRequest,
    UpdateSettingsResponse,
    UpdateSettingsService,
)

from ._security import bearer_scheme

settings_router: APIRouter = APIRouter(
    prefix="/settings",
    tags=["settings"],
)


@settings_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The proxy settings.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_settings(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> GetSettingsResponse:
    """The proxy settings."""
    service: GetSettingsService = GetSettingsService(token=credentials.credentials)
    return await service()


@settings_router.put(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated settings. The proxy applies them to new connections within a few seconds.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The body is malformed, e.g. a network has host bits or repeats, or a timeout is out of range."
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_settings(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: UpdateSettingsRequest,
) -> UpdateSettingsResponse:
    """Replace the proxy settings. Open connections keep the old ones.

    - `guardAllow`: private networks the proxy may connect to, e.g. 10.0.0.0/8. Empty: the public internet only.
    - Timeouts, seconds: `handshakeTimeout` to authenticate and send a request, `idleTimeout` for a silent tunnel,
      `connectTimeout` to reach a target.
    """
    service: UpdateSettingsService = UpdateSettingsService(token=credentials.credentials, data=data)
    return await service()
