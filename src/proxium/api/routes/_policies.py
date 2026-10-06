from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002, FastAPI reads signatures at runtime.
from fastapi_pagination import Page  # noqa: TC002, FastAPI reads signatures at runtime.

from proxium.api.services.policies import (
    CreatePolicyRequest,
    CreatePolicyResponse,
    CreatePolicyService,
    DeletePolicyService,
    GetPolicyResponse,
    GetPolicyService,
    ListPoliciesResponse,
    ListPoliciesService,
    UpdatePolicyRequest,
    UpdatePolicyResponse,
    UpdatePolicyService,
)

from ._security import bearer_scheme

policies_router: APIRouter = APIRouter(
    prefix="/policies",
    tags=["policies"],
)


@policies_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "The created policy. The proxy applies it with its next lookup.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `policies.add`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The body is malformed, e.g. the name is empty or a limit isn't positive.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def create_policy(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    data: CreatePolicyRequest,
) -> CreatePolicyResponse:
    """Create a policy: rules on how clients may use the proxy.

    - `isGlobal`: applies to every client, otherwise only to the accounts and networks it's assigned to.
    - `rules`: in order, the first whose condition matches applies all its limits.
    - `scope`: what a limit is counted over, e.g. `identity` for all connections of one account together.
    - `rate`, `burst`: bytes per second, and bytes that go at once after a pause.
    - `trafficQuotas`: at most `maxBytes` per account or network in each period of `periodLength` days or months,
      or in `total`. Past it new connections are refused and open ones cut.
    - `globalStartsOn`: the UTC day quota periods of a global policy count from, today by default. Unused by
      others: an assigned policy counts from the day set on its assignment.
    """
    service: CreatePolicyService = CreatePolicyService(token=credentials.credentials, data=data)
    return await service()


@policies_router.get(
    "",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "A page of policies.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `policies.view`.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query parameters are malformed, e.g. the page size is out of range.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def list_policies(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    query: Annotated[
        str | None,
        Query(
            description="Search by name.",
            min_length=1,
            max_length=255,
        ),
    ] = None,
    is_global: Annotated[
        bool | None,
        Query(
            alias="isGlobal",
            description="Only global policies, or only the others.",
        ),
    ] = None,
) -> Page[ListPoliciesResponse]:
    """List policies by name, without their rules."""
    service: ListPoliciesService = ListPoliciesService(
        token=credentials.credentials,
        query=query,
        is_global=is_global,
    )
    return await service()


@policies_router.get(
    "/{policy_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The policy with its rules and limits.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `policies.view`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Policy not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The policy id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def get_policy(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    policy_id: int,
) -> GetPolicyResponse:
    """Get a policy with its rules and limits."""
    service: GetPolicyService = GetPolicyService(token=credentials.credentials, id=policy_id)
    return await service()


@policies_router.patch(
    "/{policy_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "The updated policy. The proxy applies it to new connections with its next lookup.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `policies.change`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Policy not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "The policy id is not an integer or the body is malformed, e.g. an id of a rule or limit "
                "is repeated or belongs to another policy or rule."
            ),
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def update_policy(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    policy_id: int,
    data: UpdatePolicyRequest,
) -> UpdatePolicyResponse:
    """Change a policy. Only the given fields change.

    - `rules`: the whole new list, in order. A rule or limit with an `id` changes in place, without one is added,
      left out is deleted. Keep the ids of what stays: a connection limit changed in place keeps counting
      the connections already open.
    - `globalStartsOn`: the UTC day quota periods of a global policy count from.
    """
    service: UpdatePolicyService = UpdatePolicyService(token=credentials.credentials, id=policy_id, data=data)
    return await service()


@policies_router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The policy is deleted and taken off its accounts and networks.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "The access token is missing, invalid or expired, or the user is inactive or has a new password."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "The user lacks `policies.delete`.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Policy not found.",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The policy id is not an integer.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error.",
        },
    },
)
async def delete_policy(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    policy_id: int,
) -> None:
    """Delete a policy. Its accounts and networks stay, without it."""
    service: DeletePolicyService = DeletePolicyService(token=credentials.credentials, id=policy_id)
    return await service()
