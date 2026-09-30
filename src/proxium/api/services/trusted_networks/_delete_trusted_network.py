from asyncpg import RestrictViolationError
from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TrustedNetworkModel


class DeleteTrustedNetworkService(BaseUserAuthenticatedService[None]):
    """New connections from the network need credentials again. Open ones are never cut.

    A network with traffic stays: its history is kept, turn it off instead.
    """

    id: int

    @property
    def _get_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._get_network_statement)
        try:
            network: TrustedNetworkModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

        await self.session.delete(network)

        # Checking the traffic first would race with the proxy writing it.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == RestrictViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Network has traffic, turn it off instead.",
                ) from None
            raise
