from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TokenProxyAccountModel, TokenProxyAccountTrafficModel
from proxium.helpers import BaseSchema


class GetTokenProxyAccountTrafficTotalRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class GetTokenProxyAccountTrafficTotalResponse(BaseSchema):
    bytes_sent: int
    bytes_received: int


class GetTokenProxyAccountTrafficTotalService(BaseUserAuthenticatedService[GetTokenProxyAccountTrafficTotalResponse]):
    id: int
    data: GetTokenProxyAccountTrafficTotalRequest

    @property
    def _get_account_statement(self) -> Select[tuple[TokenProxyAccountModel]]:
        return select(TokenProxyAccountModel).where(TokenProxyAccountModel.id == self.id)

    @property
    def _get_total_statement(self) -> Select[tuple[int, int]]:
        # The sum of bigints is numeric in PostgreSQL, it never overflows. No rows give zeros.
        statement: Select[tuple[int, int]] = select(
            func.coalesce(func.sum(TokenProxyAccountTrafficModel.bytes_sent), 0).label("bytes_sent"),
            func.coalesce(func.sum(TokenProxyAccountTrafficModel.bytes_received), 0).label("bytes_received"),
        ).where(TokenProxyAccountTrafficModel.token_proxy_account_id == self.id)
        if self.data.since is not None:
            statement = statement.where(TokenProxyAccountTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(TokenProxyAccountTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> GetTokenProxyAccountTrafficTotalResponse:
        # An account without traffic gives zeros, a missing one a 404.
        result: Result[tuple[TokenProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        total_result: Result[tuple[int, int]] = await self.session.execute(self._get_total_statement)
        return GetTokenProxyAccountTrafficTotalResponse.model_validate(total_result.one())
