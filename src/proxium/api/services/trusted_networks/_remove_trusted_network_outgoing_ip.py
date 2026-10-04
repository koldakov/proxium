from typing import TYPE_CHECKING, ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, delete, exists, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingMode, Permission, TrustedNetworkModel, TrustedNetworkOutgoingIPModel

if TYPE_CHECKING:
    from sqlalchemy.sql.dml import ReturningDelete


class RemoveTrustedNetworkOutgoingIPService(BaseUserAuthenticatedService[None]):
    """Take an IP out of the outgoing IP pool, the IP itself stays. The last one stays while the pool is in use."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_CHANGE})

    id: int
    outgoing_ip_id: int

    @property
    def _lock_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        # Held till commit: pool and mode changes of the network take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id).with_for_update(key_share=True)

    @property
    def _delete_outgoing_ip_statement(self) -> ReturningDelete[tuple[int]]:
        return (
            delete(TrustedNetworkOutgoingIPModel)
            .where(
                TrustedNetworkOutgoingIPModel.trusted_network_id == self.id,
                TrustedNetworkOutgoingIPModel.outgoing_ip_id == self.outgoing_ip_id,
            )
            .returning(TrustedNetworkOutgoingIPModel.id)
        )

    @property
    def _has_pool_ips_statement(self) -> Select[tuple[bool]]:
        return select(
            exists().where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id),
        )

    async def _lock_network(self) -> TrustedNetworkModel:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._lock_network_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def _check_pool_not_empty(self) -> None:
        """Raise 409 if the pool has no IPs: the `pool` mode needs one."""
        result: Result[tuple[bool]] = await self.session.execute(self._has_pool_ips_statement)
        if not result.scalars().one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last IP of a pool in use, switch the outgoing mode first.",
            )

    async def process(self, *args, **kwargs) -> None:
        network: TrustedNetworkModel = await self._lock_network()

        result: Result[tuple[int]] = await self.session.execute(self._delete_outgoing_ip_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outgoing IP is not in the pool.",
            ) from None

        # Raised before the commit, so the delete is rolled back.
        if network.outgoing_mode == OutgoingMode.POOL:
            await self._check_pool_not_empty()

        await self.session.commit()
