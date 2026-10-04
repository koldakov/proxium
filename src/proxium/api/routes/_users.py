from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.users import (
    CreateUserRequest,
    CreateUserResponse,
    CreateUserService,
    GetUserMeResponse,
    GetUserMeService,
    GetUserResponse,
    GetUserService,
    ListUsersResponse,
    ListUsersService,
    UpdateUserMePasswordRequest,
    UpdateUserMePasswordService,
    UpdateUserMeRequest,
    UpdateUserMeResponse,
    UpdateUserMeService,
    UpdateUserRequest,
    UpdateUserResponse,
    UpdateUserService,
)

from ._security import bearer_scheme

users_router: APIRouter = APIRouter(
    prefix="/users",
    tags=["users"],
)


@users_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created user.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "The user lacks `users.add`, gives permissions they don't have, directly or through groups, "
                "or makes a superuser without being one."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "description": "Email is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the email is invalid or a group is unknown.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateUserRequest,
) -> CreateUserResponse:
    """Create a user of the admin.

    - `groupIds`, `permissions`: what the user may do, only what the logged-in user has.
    """
    service: CreateUserService = CreateUserService(token=credentials.credentials, data=data)
    return await service()


@users_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of users.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `users.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_users(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    query: Annotated[
        str | None,
        Query(
            description="Search by email, name or surname.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
) -> Page[ListUsersResponse]:
    """List users, newest first."""
    service: ListUsersService = ListUsersService(token=credentials.credentials, query=query)
    return await service()


@users_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The logged-in user with what they may do.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_user_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> GetUserMeResponse:
    """The logged-in user.

    - `permissions`: given directly and through groups, every permission for a superuser.
    """
    service: GetUserMeService = GetUserMeService(token=credentials.credentials)
    return await service()


@users_router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated user.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_user_me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: UpdateUserMeRequest,
) -> UpdateUserMeResponse:
    """Update the logged-in user's name and surname. Only the given fields change.

    The email is the login, an admin changes it. The password has its own endpoint.
    """
    service: UpdateUserMeService = UpdateUserMeService(token=credentials.credentials, data=data)
    return await service()


@users_router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The password is changed.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Old password is incorrect.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the new password is too short.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_user_me_password(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: UpdateUserMePasswordRequest,
) -> None:
    """Change the logged-in user's password. The old one must match."""
    service: UpdateUserMePasswordService = UpdateUserMePasswordService(token=credentials.credentials, data=data)
    return await service()


@users_router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The user.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `users.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "User not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The user id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    user_id: int,
) -> GetUserResponse:
    """Get a user.

    - `permissions`: given directly, the groups of `groupIds` have their own.
    """
    service: GetUserService = GetUserService(token=credentials.credentials, id=user_id)
    return await service()


@users_router.patch(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated user. Permissions apply to their next request.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "The user lacks `users.change`, gives permissions they don't have, directly or through groups, "
                "or changes a superuser without being one."
            ),
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "User not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Email is already taken, or the user deactivates or unmakes themselves as a superuser.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The user id is not an integer or the body is malformed, e.g. a group is unknown.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    user_id: int,
    data: UpdateUserRequest,
) -> UpdateUserResponse:
    """Update a user: profile, activity and access. Only the given fields change.

    - `groupIds`, `permissions`: replace the lists. Only what the logged-in user has can be added.
    """
    service: UpdateUserService = UpdateUserService(token=credentials.credentials, id=user_id, data=data)
    return await service()
