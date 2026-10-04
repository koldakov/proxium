from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, func, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.core import api_settings
from proxium.db import OutgoingIPModel, Permission, TrustedNetworkModel, TrustedNetworkOutgoingIPModel


class AddTrustedNetworkOutgoingIPService(BaseUserAuthenticatedService[None]):
    """Add an IP to the outgoing IP pool. Adding it again changes nothing. A pool is of one IP family."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.TRUSTED_NETWORKS_CHANGE})

    id: int
    outgoing_ip_id: int

    @property
    def _lock_network_statement(self) -> Select[tuple[TrustedNetworkModel]]:
        # Held till commit: pool and mode changes of the network take turns.
        # NO KEY UPDATE: inserts referencing the row, e.g. its traffic, don't wait for it.
        return select(TrustedNetworkModel).where(TrustedNetworkModel.id == self.id).with_for_update(key_share=True)

    @property
    def _lock_outgoing_ip_statement(self) -> Select[tuple[OutgoingIPModel]]:
        # Shared lock: the IP can't be deleted or change its family until it's in the pool.
        return select(OutgoingIPModel).where(OutgoingIPModel.id == self.outgoing_ip_id).with_for_update(read=True)

    @property
    def _get_pool_family_statement(self) -> Select[tuple[int]]:
        # One IP tells the family of the whole pool.
        return (
            select(func.family(OutgoingIPModel.ip))
            .join(
                TrustedNetworkOutgoingIPModel,
                TrustedNetworkOutgoingIPModel.outgoing_ip_id == OutgoingIPModel.id,
            )
            .where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id)
            .limit(1)
        )

    @property
    def _insert_outgoing_ip_statement(self) -> Insert:
        return (
            insert(TrustedNetworkOutgoingIPModel)
            .values(
                trusted_network_id=self.id,
                outgoing_ip_id=self.outgoing_ip_id,
            )
            .on_conflict_do_nothing()
        )

    @property
    def _count_pool_statement(self) -> Select[tuple[int]]:
        return (
            select(func.count())
            .select_from(TrustedNetworkOutgoingIPModel)
            .where(TrustedNetworkOutgoingIPModel.trusted_network_id == self.id)
        )

    async def _lock_network(self) -> None:
        result: Result[tuple[TrustedNetworkModel]] = await self.session.execute(self._lock_network_statement)
        try:
            result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Network not found.",
            ) from None

    async def _lock_outgoing_ip(self) -> OutgoingIPModel:
        result: Result[tuple[OutgoingIPModel]] = await self.session.execute(self._lock_outgoing_ip_statement)
        try:
            return result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outgoing IP not found.",
            ) from None

    async def _check_family(self, outgoing_ip: OutgoingIPModel, /) -> None:
        result: Result[tuple[int]] = await self.session.execute(self._get_pool_family_statement)
        # An empty pool takes either family.
        try:
            family: int = result.scalars().one()
        except NoResultFound:
            return

        # An IPv4 source can't reach IPv6 targets: a mixed pool would fail at random.
        if family != outgoing_ip.ip.version:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The pool is of IPv{family} addresses.",
            )

    async def process(self, *args, **kwargs) -> None:
        await self._lock_network()
        outgoing_ip: OutgoingIPModel = await self._lock_outgoing_ip()
        await self._check_family(outgoing_ip)

        # Counted after the insert, so adding an IP already there never hits the cap.
        await self.session.execute(self._insert_outgoing_ip_statement)
        result: Result[tuple[int]] = await self.session.execute(self._count_pool_statement)
        if result.scalars().one() > api_settings.outgoing_pool_max_size:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The pool is full, at most {api_settings.outgoing_pool_max_size} IPs.",
            )

        await self.session.commit()
