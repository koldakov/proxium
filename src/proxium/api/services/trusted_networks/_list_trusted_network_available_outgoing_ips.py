from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import Field, IPvAnyAddress
from sqlalchemy import Result, Select, exists, func, or_, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import aliased

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, TrustedNetworkModel, TrustedNetworkOutgoingIPModel
from proxium.helpers import BaseSchema


class ListTrustedNetworkAvailableOutgoingIPsRequest(BaseSchema):
    """Filters from the query string."""

    # Matches name or IP text, case-insensitive.
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=255,
        ),
    ] = None


class ListTrustedNetworkAvailableOutgoingIPsResponse(BaseSchema):
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


class ListTrustedNetworkAvailableOutgoingIPsService(
    BaseUserAuthenticatedService[Page[ListTrustedNetworkAvailableOutgoingIPsResponse]],
):
    """IPs the pool can take: not in it yet and of its family. Any family for an empty pool."""

    id: int
    data: ListTrustedNetworkAvailableOutgoingIPsRequest

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _list_available_outgoing_ips_statement(self) -> Select[tuple[OutgoingIPModel]]:
        # Its own alias: the outer query lists outgoing IPs too.
        pool_ip = aliased(OutgoingIPModel)
        # One IP tells the family of the whole pool, NULL for an empty one.
        pool_family = (
            select(func.family(pool_ip.ip))
            .join(
                TrustedNetworkOutgoingIPModel,
                TrustedNetworkOutgoingIPModel.outgoing_ip_id == pool_ip.id,
            )
            .where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id)
            .limit(1)
            .scalar_subquery()
        )
        in_pool = exists().where(
            TrustedNetworkOutgoingIPModel.trusted_network_id == self.id,
            TrustedNetworkOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
        )

        statement: Select[tuple[OutgoingIPModel]] = (
            select(OutgoingIPModel)
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

    async def _get_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def process(self, *args, **kwargs) -> Page[ListTrustedNetworkAvailableOutgoingIPsResponse]:
        await self._get_network()

        return await apaginate(
            self.session,
            self._list_available_outgoing_ips_statement,
        )
