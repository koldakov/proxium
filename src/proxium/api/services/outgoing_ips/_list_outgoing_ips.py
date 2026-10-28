from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Annotated, ClassVar, NamedTuple, cast

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import ColumnElement, ScalarSelect, Select, all_, and_, func, or_, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission, ProxyInstanceModel, ProxyInstanceStatus
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


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
    # True: IPs some live instance doesn't have. False: IPs every live instance has, every IP while none is live.
    missing: bool | None = None


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
    # Pending and running instances, not deregistered: the ones that connect.
    live_instances: int
    # Live instances that don't have the IP: connections from it fail there.
    instances_without_ip: int


class _OutgoingIPRow(NamedTuple):
    id: int
    name: str
    ip: IPv4Address | IPv6Address
    created_by_id: int
    created_at: datetime
    live_instances: int
    instances_without_ip: int


class ListOutgoingIPsService(BaseUserAuthenticatedService[Page[ListOutgoingIPsResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.OUTGOING_IPS_VIEW})

    data: ListOutgoingIPsRequest

    @property
    def _is_live_expression(self) -> ColumnElement[bool]:
        # Unknown ones are past `expires_at` by the database's clock.
        return and_(
            ProxyInstanceModel.is_deleted.is_(False),
            ProxyInstanceModel.status != ProxyInstanceStatus.STOPPED,
            ProxyInstanceModel.expires_at >= func.now(),
        )

    @property
    def _count_live_instances_statement(self) -> ScalarSelect[int]:
        return select(func.count()).where(self._is_live_expression).scalar_subquery()

    @property
    def _count_instances_without_ip_statement(self) -> ScalarSelect[int]:
        # Per listed IP. Both inet: an IP the API stored as /32 equals the one the instance reported. `<> ALL`, not
        # a negated `= ANY`: SQLAlchemy would turn that into `<> ANY`, true for any other IP in the array.
        return (
            select(func.count())
            .where(
                self._is_live_expression,
                OutgoingIPModel.ip != all_(ProxyInstanceModel.ips),
            )
            .correlate(OutgoingIPModel)
            .scalar_subquery()
        )

    @property
    def _list_outgoing_ips_statement(self) -> Select[_OutgoingIPRow]:
        instances_without_ip = self._count_instances_without_ip_statement
        # SQLAlchemy types rows by their columns, the labels make it this one.
        statement = cast(
            "Select[_OutgoingIPRow]",
            select(
                OutgoingIPModel.id,
                OutgoingIPModel.name,
                OutgoingIPModel.ip,
                OutgoingIPModel.created_by_id,
                OutgoingIPModel.created_at,
                self._count_live_instances_statement.label("live_instances"),
                instances_without_ip.label("instances_without_ip"),
            ).order_by(
                OutgoingIPModel.id.desc(),
            ),
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
        if self.data.missing is True:
            statement = statement.where(instances_without_ip > 0)
        if self.data.missing is False:
            statement = statement.where(instances_without_ip == 0)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListOutgoingIPsResponse]:
        return await apaginate(
            self.session,
            self._list_outgoing_ips_statement,
        )
