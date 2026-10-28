from datetime import datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, NamedTuple, cast

from fastapi import HTTPException, status
from pydantic import Field, IPvAnyAddress
from sqlalchemy import ColumnElement, Result, ScalarSelect, Select, all_, and_, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission, ProxyInstanceModel, ProxyInstanceStatus
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


class GetOutgoingIPResponse(BaseSchema):
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
    updated_at: datetime
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
    updated_at: datetime
    live_instances: int
    instances_without_ip: int


class GetOutgoingIPService(BaseUserAuthenticatedService[GetOutgoingIPResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.OUTGOING_IPS_VIEW})

    id: int

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
        # Both inet: an IP the API stored as /32 equals the one the instance reported. `<> ALL`, not a negated
        # `= ANY`: SQLAlchemy would turn that into `<> ANY`, true for any other IP in the array.
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
    def _get_outgoing_ip_statement(self) -> Select[_OutgoingIPRow]:
        # SQLAlchemy types rows by their columns, the labels make it this one.
        return cast(
            "Select[_OutgoingIPRow]",
            select(
                OutgoingIPModel.id,
                OutgoingIPModel.name,
                OutgoingIPModel.ip,
                OutgoingIPModel.created_by_id,
                OutgoingIPModel.created_at,
                OutgoingIPModel.updated_at,
                self._count_live_instances_statement.label("live_instances"),
                self._count_instances_without_ip_statement.label("instances_without_ip"),
            ).where(OutgoingIPModel.id == self.id),
        )

    async def process(self, *args, **kwargs) -> GetOutgoingIPResponse:
        result: Result[_OutgoingIPRow] = await self.session.execute(self._get_outgoing_ip_statement)
        try:
            outgoing_ip: _OutgoingIPRow = result.one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP not found.",
            ) from None

        return GetOutgoingIPResponse.model_validate(outgoing_ip)
