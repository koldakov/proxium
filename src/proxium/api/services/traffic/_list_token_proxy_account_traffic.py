from datetime import date

from fastapi import HTTPException, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TokenProxyAccountModel, TokenProxyAccountTrafficModel
from proxium.helpers import BaseSchema


class ListTokenProxyAccountTrafficRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class ListTokenProxyAccountTrafficResponse(BaseSchema):
    id: int
    day: date
    bytes_sent: int
    bytes_received: int


class ListTokenProxyAccountTrafficService(BaseUserAuthenticatedService[Page[ListTokenProxyAccountTrafficResponse]]):
    id: int
    data: ListTokenProxyAccountTrafficRequest

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    @property
    def _list_traffic_statement(self) -> Select[tuple[TokenProxyAccountTrafficModel]]:
        statement: Select[tuple[TokenProxyAccountTrafficModel]] = (
            select(TokenProxyAccountTrafficModel)
            .where(TokenProxyAccountTrafficModel.token_proxy_account_id == self.id)
            .order_by(TokenProxyAccountTrafficModel.day.desc())
        )
        if self.data.since is not None:
            statement = statement.where(TokenProxyAccountTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(TokenProxyAccountTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> Page[ListTokenProxyAccountTrafficResponse]:
        # An account without traffic gives an empty page, a missing one a 404.
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
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
