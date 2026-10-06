from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.configs import GetConfigsResponse, GetConfigsService

from ._security import bearer_scheme

configs_router: APIRouter = APIRouter(
    prefix="/configs",
    tags=["configs"],
)


@configs_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The configs from the environment.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_configs(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> GetConfigsResponse:
    """Configs set in the environment, read-only, for any active user. They change only with a restart.

    - `policiesMaxPerOwner`: policies assigned to one account or trusted network at most, global ones aside.
    """
    service: GetConfigsService = GetConfigsService(token=credentials.credentials)
    return await service()
