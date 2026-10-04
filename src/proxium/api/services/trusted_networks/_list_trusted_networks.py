from datetime import datetime
from typing import Annotated, ClassVar

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyNetwork
from sqlalchemy import Select, String, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import CIDR

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TrustedNetworkModel
from proxium.helpers import BaseSchema


class ListTrustedNetworksRequest(BaseSchema):
    """Filters from the query string, all optional and combined with AND."""

    # Matches name or network text, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None
    # Strict: the same network isn't in either. At most one per prefix length contains it, any number are inside.
    contains: IPvAnyNetwork | None = None
    within: IPvAnyNetwork | None = None
    is_active: bool | None = None
    # E.g. 0 finds networks open to the whole internet.
    prefix_length: Annotated[
        int | None,
        Field(
            ge=0,
            le=128,
        ),
    ] = None


class ListTrustedNetworksResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    network: IPvAnyNetwork
    is_active: bool
    outgoing_mode: OutgoingMode
    created_by_id: int
    created_at: datetime


class ListTrustedNetworksService(BaseUserAuthenticatedService[Page[ListTrustedNetworksResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_VIEW})

    data: ListTrustedNetworksRequest

    @property
    def _list_networks_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        statement: Select[tuple[TrustedNetworkModel]] = select(TrustedNetworkModel).order_by(
            TrustedNetworkModel.id.desc(),
        )
        if self.data.query is not None:
            statement = statement.where(
                or_(
                    TrustedNetworkModel.name.icontains(self.data.query, autoescape=True),
                    cast(TrustedNetworkModel.network, String).icontains(self.data.query, autoescape=True),
                ),
            )
        if self.data.contains is not None:
            statement = statement.where(TrustedNetworkModel.network.op(">>")(literal(self.data.contains, CIDR())))
        if self.data.within is not None:
            statement = statement.where(TrustedNetworkModel.network.op("<<")(literal(self.data.within, CIDR())))
        if self.data.is_active is not None:
            statement = statement.where(TrustedNetworkModel.is_active.is_(self.data.is_active))
        if self.data.prefix_length is not None:
            statement = statement.where(func.masklen(TrustedNetworkModel.network) == self.data.prefix_length)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListTrustedNetworksResponse]:
        return await apaginate(
            self.session,
            self._list_networks_statement,
        )
