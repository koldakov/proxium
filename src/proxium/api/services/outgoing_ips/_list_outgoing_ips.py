from datetime import datetime
from enum import IntEnum
from typing import Annotated, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import Select, func, or_, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission
from proxium.helpers import BaseSchema


class IPVersion(IntEnum):
    IPV4 = 4
    IPV6 = 6


class ListOutgoingIPsRequest(BaseSchema):
    """Filters from the query string, all optional and combined with AND."""

    # Matches name or IP text, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None
    # A pool takes IPs of one family.
    version: IPVersion | None = None


class ListOutgoingIPsResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    ip: IPvAnyAddress
    created_by_id: int
    created_at: datetime


class ListOutgoingIPsService(BaseUserAuthenticatedService[Page[ListOutgoingIPsResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.OUTGOING_IPS_VIEW})

    data: ListOutgoingIPsRequest

    @property
    def _list_outgoing_ips_statement(self) -> Select[tuple[OutgoingIPModel]]:
        statement: Select[tuple[OutgoingIPModel]] = select(OutgoingIPModel).order_by(
            OutgoingIPModel.id.desc(),
        )
        if self.data.query is not None:
            statement = statement.where(
                or_(
                    OutgoingIPModel.name.icontains(self.data.query, autoescape=True),
                    # host() drops the /32 that the text of an inet would have.
                    func.host(OutgoingIPModel.ip).icontains(self.data.query, autoescape=True),
                ),
            )
        if self.data.version is not None:
            statement = statement.where(func.family(OutgoingIPModel.ip) == self.data.version)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListOutgoingIPsResponse]:
        return await apaginate(
            self.session,
            self._list_outgoing_ips_statement,
        )
