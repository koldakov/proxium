from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.groups import (
    CreateGroupRequest,
    CreateGroupResponse,
    CreateGroupService,
    DeleteGroupService,
    GetGroupResponse,
    GetGroupService,
    ListGroupsResponse,
    ListGroupsService,
    UpdateGroupRequest,
    UpdateGroupResponse,
    UpdateGroupService,
)

from ._security import bearer_scheme

groups_router: APIRouter = APIRouter(
    prefix="/groups",
    tags=["groups"],
)


@groups_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created group.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `groups.add` or gives permissions they don't have.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Name is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty or a permission unknown.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_group(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    data: CreateGroupRequest,
) -> CreateGroupResponse:
    """Create a group of permissions, its users have them all.

    - `permissions`: codes from `/permissions`, only the ones the logged-in user has.
    """
    service: CreateGroupService = CreateGroupService(token=credentials.credentials, data=data)
    return await service()


@groups_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of groups.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `groups.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_groups(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    query: Annotated[
        str | None,
        Query(
            description="Search by name.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
) -> Page[ListGroupsResponse]:
    """List groups by name."""
    service: ListGroupsService = ListGroupsService(token=credentials.credentials, query=query)
    return await service()


@groups_router.get(
    "/{group_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The group.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `groups.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Group not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The group id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_group(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    group_id: int,
) -> GetGroupResponse:
    """Get a group."""
    service: GetGroupService = GetGroupService(token=credentials.credentials, id=group_id)
    return await service()


@groups_router.patch(
    "/{group_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated group. Its users get the permissions with their next request.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `groups.change` or gives permissions they don't have.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Group not found.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Name is already taken.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The group id is not an integer or the body is malformed.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_group(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    group_id: int,
    data: UpdateGroupRequest,
) -> UpdateGroupResponse:
    """Rename a group or change its permissions. Only the given fields change.

    - `permissions`: replaces the list. Only the ones the logged-in user has can be added.
    """
    service: UpdateGroupService = UpdateGroupService(token=credentials.credentials, id=group_id, data=data)
    return await service()


@groups_router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The group is deleted, its users lose its permissions with their next request.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "The access token is missing, invalid or expired, or the user is inactive.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `groups.delete`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Group not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The group id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def delete_group(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    group_id: int,
) -> None:
    """Delete a group. Its users stay."""
    service: DeleteGroupService = DeleteGroupService(token=credentials.credentials, id=group_id)
    return await service()
