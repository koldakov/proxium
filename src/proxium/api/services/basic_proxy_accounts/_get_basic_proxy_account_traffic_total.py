from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import BasicProxyAccountModel, BasicProxyAccountTrafficModel
from proxium.helpers import BaseSchema


class GetBasicProxyAccountTrafficTotalRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class GetBasicProxyAccountTrafficTotalResponse(BaseSchema):
    bytes_sent: int
    bytes_received: int


class GetBasicProxyAccountTrafficTotalService(BaseUserAuthenticatedService[GetBasicProxyAccountTrafficTotalResponse]):
    id: int
    data: GetBasicProxyAccountTrafficTotalRequest

    @property
    def _get_account_statement(self) -> Select[tuple[BasicProxyAccountModel]]:
        return select(BasicProxyAccountModel).where(BasicProxyAccountModel.id == self.id)

    @property
    def _get_total_statement(self) -> Select[tuple[int, int]]:
        # The sum of bigints is numeric in PostgreSQL, it never overflows. No rows give zeros.
        statement: Select[tuple[int, int]] = select(
            func.coalesce(func.sum(BasicProxyAccountTrafficModel.bytes_sent), 0).label("bytes_sent"),
            func.coalesce(func.sum(BasicProxyAccountTrafficModel.bytes_received), 0).label("bytes_received"),
        ).where(BasicProxyAccountTrafficModel.basic_proxy_account_id == self.id)
        if self.data.since is not None:
            statement = statement.where(BasicProxyAccountTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(BasicProxyAccountTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> GetBasicProxyAccountTrafficTotalResponse:
        # An account without traffic gives zeros, a missing one a 404.
        result: Result[tuple[BasicProxyAccountModel]] = await self.session.execute(self._get_account_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found.",
            ) from None

        total_result: Result[tuple[int, int]] = await self.session.execute(self._get_total_statement)
        return GetBasicProxyAccountTrafficTotalResponse.model_validate(total_result.one())
