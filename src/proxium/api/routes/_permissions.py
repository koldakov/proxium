from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.permissions import ListPermissionsResponse, ListPermissionsService

from ._security import bearer_scheme

permissions_router: APIRouter = APIRouter(
    prefix="/permissions",
    tags=["permissions"],
)


@permissions_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Every permission, not paged: there are a few dozen.",
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
async def list_permissions(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> list[ListPermissionsResponse]:
    """Permissions for groups and users, `<resource>.<action>`. A superuser has them all."""
    service: ListPermissionsService = ListPermissionsService(token=credentials.credentials)
    return await service()
