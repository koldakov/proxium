from typing import ClassVar

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission
from proxium.helpers import BaseSchema


class ListPermissionsResponse(BaseSchema):
    # The code, e.g. `trusted_networks.view`: resource and action.
    id: Permission


class ListPermissionsService(BaseUserAuthenticatedService[list[ListPermissionsResponse]]):
    """Every permission there is, from the code: the admin UI builds its checkboxes from them."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset()

    async def process(self, *args, **kwargs) -> list[ListPermissionsResponse]:
        return [ListPermissionsResponse(id=permission) for permission in Permission]
