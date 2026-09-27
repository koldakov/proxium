from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page, Params  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.services.users import (
    CreateUserRequest,
    CreateUserResponse,
    CreateUserService,
    GetUserMeResponse,
    GetUserMeService,
    GetUserResponse,
    GetUserService,
    ListUsersResponse,
    ListUsersService,
    UpdateUserPasswordRequest,
    UpdateUserPasswordService,
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
            "description": "The created user. It is inactive until activated.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Email is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the email is invalid or the password is too short.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_user(data: CreateUserRequest) -> CreateUserResponse:
    """Create a user."""
    service: CreateUserService = CreateUserService(data=data)
    return await service()


@users_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of users.",
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
    params: Annotated[Params, Depends()],
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
    service: ListUsersService = ListUsersService(params=params, query=query)
    return await service()


@users_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The logged-in user.",
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
    """The logged-in user."""
    service: GetUserMeService = GetUserMeService(token=credentials.credentials)
    return await service()


@users_router.patch(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated user.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Email is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the email is invalid.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: UpdateUserRequest,
) -> UpdateUserResponse:
    """Update the logged-in user. Only the given fields change, the password has its own endpoint."""
    service: UpdateUserService = UpdateUserService(token=credentials.credentials, data=data)
    return await service()


@users_router.put(
    "/password",
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
async def update_user_password(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: UpdateUserPasswordRequest,
) -> None:
    """Change the logged-in user's password. The old one must match."""
    service: UpdateUserPasswordService = UpdateUserPasswordService(token=credentials.credentials, data=data)
    return await service()


@users_router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The user.",
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
async def get_user(user_id: int) -> GetUserResponse:
    """Get a user."""
    service: GetUserService = GetUserService(id=user_id)
    return await service()
