from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TrustedNetworkModel, TrustedNetworkTrafficModel
from proxium.helpers import BaseSchema


class GetTrustedNetworkTrafficTotalRequest(BaseSchema):
    """Filters from the query string, both optional and inclusive. Days are UTC."""

    since: date | None = None
    until: date | None = None


class GetTrustedNetworkTrafficTotalResponse(BaseSchema):
    bytes_sent: int
    bytes_received: int


class GetTrustedNetworkTrafficTotalService(BaseUserAuthenticatedService[GetTrustedNetworkTrafficTotalResponse]):
    id: int
    data: GetTrustedNetworkTrafficTotalRequest

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    @property
    def _get_total_statement(self) -> Select[tuple[int, int]]:
        # The sum of bigints is numeric in PostgreSQL, it never overflows. No rows give zeros.
        statement: Select[tuple[int, int]] = select(
            func.coalesce(func.sum(TrustedNetworkTrafficModel.bytes_sent), 0).label("bytes_sent"),
            func.coalesce(func.sum(TrustedNetworkTrafficModel.bytes_received), 0).label("bytes_received"),
        ).where(TrustedNetworkTrafficModel.trusted_network_id == self.id)
        if self.data.since is not None:
            statement = statement.where(TrustedNetworkTrafficModel.day >= self.data.since)
        if self.data.until is not None:
            statement = statement.where(TrustedNetworkTrafficModel.day <= self.data.until)

        return statement

    async def process(self, *args, **kwargs) -> GetTrustedNetworkTrafficTotalResponse:
        # A network without traffic gives zeros, a missing one a 404.
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

        total_result: Result[tuple[int, int]] = await self.session.execute(self._get_total_statement)
        return GetTrustedNetworkTrafficTotalResponse.model_validate(total_result.one())
