from typing import ClassVar

from proxium.api.services import BaseUserAuthenticatedService
from proxium.core import api_settings
from proxium.db import Permission  # noqa: TC001, pydantic reads annotations at runtime.
from proxium.helpers import BaseSchema


class GetConfigsResponse(BaseSchema):
    policies_max_per_owner: int


class GetConfigsService(BaseUserAuthenticatedService[GetConfigsResponse]):
    """Read-only configs from the environment: the admin UI tells the caps before the API refuses."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset()

    async def process(self, *args, **kwargs) -> GetConfigsResponse:
        return GetConfigsResponse(
            policies_max_per_owner=api_settings.policies_max_per_owner,
        )
