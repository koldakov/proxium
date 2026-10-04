from datetime import date
from typing import ClassVar

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, TrustedNetworkModel, TrustedNetworkTrafficModel
from proxium.helpers import BaseSchema


class ListTrustedNetworkTrafficRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class ListTrustedNetworkTrafficResponse(BaseSchema):
    id: int
    day: date
    bytes_sent: int
    bytes_received: int


class ListTrustedNetworkTrafficService(BaseUserAuthenticatedService[Page[ListTrustedNetworkTrafficResponse]]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRAFFIC_VIEW})

    id: int
    data: ListTrustedNetworkTrafficRequest

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _list_traffic_statement(self) -> Select[tuple[TrustedNetworkTrafficModel]]:
        statement: Select[tuple[TrustedNetworkTrafficModel]] = (
            select(TrustedNetworkTrafficModel)
            .where(TrustedNetworkTrafficModel.trusted_network_id == self.id)
            .order_by(TrustedNetworkTrafficModel.day.desc())
        )
        if self.data.since is not None:
            statement = statement.where(TrustedNetworkTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(TrustedNetworkTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListTrustedNetworkTrafficResponse]:
        # A network without traffic gives an empty page, a missing one a 404.
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

        return await apaginate(
            self.session,
            self._list_traffic_statement,
        )
