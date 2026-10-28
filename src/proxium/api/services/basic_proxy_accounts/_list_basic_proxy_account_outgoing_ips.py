from datetime import datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, NamedTuple, cast

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import ColumnElement, Result, ScalarSelect, Select, all_, and_, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import (
    BasicProxyAccountModel,
    BasicProxyAccountOutgoingIPModel,
    OutgoingIPModel,
    Permission,
    ProxyInstanceModel,
    ProxyInstanceStatus,
)
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


class ListBasicProxyAccountOutgoingIPsResponse(BaseSchema):
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


class ListBasicProxyAccountOutgoingIPsService(
    BaseUserAuthenticatedService[Page[ListBasicProxyAccountOutgoingIPsResponse]],
):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.BASIC_PROXY_ACCOUNTS_VIEW})

    id: int

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

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
        # In the order the IPs were added to the server. SQLAlchemy types rows by their columns, the labels make
        # it this one.
        return (
            cast(
                "Select[_OutgoingIPRow]",
                select(
                    OutgoingIPModel.id,
                    OutgoingIPModel.name,
                    OutgoingIPModel.ip,
                    OutgoingIPModel.created_by_id,
                    OutgoingIPModel.created_at,
                    self._count_live_instances_statement.label("live_instances"),
                    self._count_instances_without_ip_statement.label("instances_without_ip"),
                ),
            )
            .join(
                BasicProxyAccountOutgoingIPModel,
                BasicProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(BasicProxyAccountOutgoingIPModel.basic_proxy_account_id == self.id)
            .order_by(OutgoingIPModel.id)
        )

    async def _get_account(self) -> BasicProxyAccountModel:
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListBasicProxyAccountOutgoingIPsResponse]:
        # An empty pool gives an empty page, a missing account a 404.
        await self._get_account()

        return await apaginate(
            self.session,
            self._list_outgoing_ips_statement,
        )
