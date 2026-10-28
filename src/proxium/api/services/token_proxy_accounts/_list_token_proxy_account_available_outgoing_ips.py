from datetime import datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, NamedTuple, cast

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import ColumnElement, Result, ScalarSelect, Select, all_, and_, exists, func, or_, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import aliased

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import (
    OutgoingIPModel,
    Permission,
    ProxyInstanceModel,
    ProxyInstanceStatus,
    TokenProxyAccountModel,
    TokenProxyAccountOutgoingIPModel,
)
from proxium.helpers import BaseSchema

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address


class ListTokenProxyAccountAvailableOutgoingIPsRequest(BaseSchema):
    """Filters from the query string."""

    # Matches name or IP text, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None


class ListTokenProxyAccountAvailableOutgoingIPsResponse(BaseSchema):
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


class ListTokenProxyAccountAvailableOutgoingIPsService(
    BaseUserAuthenticatedService[Page[ListTokenProxyAccountAvailableOutgoingIPsResponse]],
):
    """IPs the pool can take: not in it yet and of its family. Any family for an empty pool."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset(
        {
            Permission.TOKEN_PROXY_ACCOUNTS_CHANGE,
            Permission.OUTGOING_IPS_VIEW,
        },
    )

    id: int
    data: ListTokenProxyAccountAvailableOutgoingIPsRequest

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

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
    def _list_available_outgoing_ips_statement(self) -> Select[_OutgoingIPRow]:
        # Its own alias: the outer query lists outgoing IPs too.
        pool_ip = aliased(OutgoingIPModel)
        # One IP tells the family of the whole pool, NULL for an empty one.
        pool_family = (
            select(func.family(pool_ip.ip))
            .join(
                TokenProxyAccountOutgoingIPModel,
                TokenProxyAccountOutgoingIPModel.outgoing_ip_id == pool_ip.id,
            )
            .where(TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id)
            .limit(1)
            .scalar_subquery()
        )
        in_pool = exists().where(
            TokenProxyAccountOutgoingIPModel.token_proxy_account_id == self.id,
            TokenProxyAccountOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
        )

        # SQLAlchemy types rows by their columns, the labels make it this one.
        statement = (
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
            .where(
                ~in_pool,
                or_(
                    pool_family.is_(None),
                    func.family(OutgoingIPModel.ip) == pool_family,
                ),
            )
            .order_by(OutgoingIPModel.id)
        )
        if self.data.query is not None:
            statement = statement.where(
                or_(
                    OutgoingIPModel.name.icontains(self.data.query, autoescape=True),
                    # host() drops the /32 that the text of an inet would have.
                    func.host(OutgoingIPModel.ip).icontains(self.data.query, autoescape=True),
                ),
            )

        return statement

    async def _get_account(self) -> TokenProxyAccountModel:
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTokenProxyAccountAvailableOutgoingIPsResponse]:
        await self._get_account()

        return await apaginate(
            self.session,
            self._list_available_outgoing_ips_statement,
        )
