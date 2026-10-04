from datetime import date

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, BasicProxyAccountTrafficModel
from proxium.helpers import BaseSchema


class ListBasicProxyAccountTrafficRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class ListBasicProxyAccountTrafficResponse(BaseSchema):
    id: int
    day: date
    bytes_sent: int
    bytes_received: int


class ListBasicProxyAccountTrafficService(BaseUserAuthenticatedService[Page[ListBasicProxyAccountTrafficResponse]]):
    id: int
    data: ListBasicProxyAccountTrafficRequest

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    @property
    def _list_traffic_statement(self) -> Select[tuple[BasicProxyAccountTrafficModel]]:
        statement: Select[tuple[BasicProxyAccountTrafficModel]] = (
            select(BasicProxyAccountTrafficModel)
            .where(BasicProxyAccountTrafficModel.basic_proxy_account_id == self.id)
            .order_by(BasicProxyAccountTrafficModel.day.desc())
        )
        if self.data.since is not None:
            statement = statement.where(BasicProxyAccountTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(BasicProxyAccountTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListBasicProxyAccountTrafficResponse]:
        # An account without traffic gives an empty page, a missing one a 404.
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        return await apaginate(
            self.session,
            self._list_traffic_statement,
        )
