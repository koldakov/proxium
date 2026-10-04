from typing import ClassVar

from asyncpg import RestrictViolationError
from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission


class DeleteOutgoingIPService(BaseUserAuthenticatedService[None]):
    """An IP in a pool stays: take it out of the pools first."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.OUTGOING_IPS_DELETE})

    id: int

    @property
    def _get_outgoing_ip_statement(self) -> Select[tuple[OutgoingIPModel]]:
        return select(OutgoingIPModel).where(OutgoingIPModel.id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[OutgoingIPModel]] = await self.session.execute(self._get_outgoing_ip_statement)
        try:
            outgoing_ip: OutgoingIPModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP not found.",
            ) from None

        await self.session.delete(outgoing_ip)

        # Checking the pools first would race with an account taking the IP.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == RestrictViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="IP is in pools, take it out of them first.",
                ) from None
            raise
