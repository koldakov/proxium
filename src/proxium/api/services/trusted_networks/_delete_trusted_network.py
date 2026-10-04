from typing import ClassVar

from asyncpg import RestrictViolationError
from fastapi import HTTPException, status
from sqlalchemy import Delete, Result, Select, delete, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, TrustedNetworkModel, TrustedNetworkOutgoingIPModel


class DeleteTrustedNetworkService(BaseUserAuthenticatedService[None]):
    """New connections from the network need credentials again. Open ones are never cut.

    A network with traffic stays: its history is kept, turn it off instead. Its outgoing IP pool goes, the IPs stay.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_DELETE})

    id: int

    @property
    def _lock_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        # Held till commit: an IP being added to the pool waits, so the cleared pool stays empty.
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id).with_for_update()

    @property
    def _clear_pool_statement(self) -> Delete:
        return delete(TrustedNetworkOutgoingIPModel).where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id)

    async def _lock_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._lock_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def process(self, *args, **kwargs) -> None:
        network: TrustedNetworkModel = await self._lock_network()

        # In one statement, nothing is loaded. Rolled back with the network if it has traffic.
        await self.session.execute(self._clear_pool_statement)
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
