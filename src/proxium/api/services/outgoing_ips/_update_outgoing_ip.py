from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyAddress, StringConstraints
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel
from proxium.helpers import BaseSchema


class UpdateOutgoingIPRequest(BaseSchema):
    """Partial update: missing or null fields stay as they are."""

    name: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = None
    # Every pool with the IP goes out from the new one. Of the same family: a pool is of one.
    ip: IPvAnyAddress | None = None


class UpdateOutgoingIPResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    ip: IPvAnyAddress
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class UpdateOutgoingIPService(BaseUserAuthenticatedService[UpdateOutgoingIPResponse]):
    id: int
    data: UpdateOutgoingIPRequest

    @property
    def _lock_outgoing_ip_statement(self) -> Select[tuple[OutgoingIPModel]]:
        # Held till commit: FOR UPDATE waits for pools taking the IP, so it can't change family under them.
        return select(OutgoingIPModel).where(OutgoingIPModel.id == self.id).with_for_update()

    async def process(self, *args, **kwargs) -> UpdateOutgoingIPResponse:
        result: Result[tuple[OutgoingIPModel]] = await self.session.execute(self._lock_outgoing_ip_statement)
        try:
            outgoing_ip: OutgoingIPModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP not found.",
            ) from None

        if self.data.ip is not None and self.data.ip.version != outgoing_ip.ip.version:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The IP stays IPv{outgoing_ip.ip.version}, add an IPv{self.data.ip.version} one instead.",
            )

        # Python mode keeps the IP an `ipaddress` object, the column takes it as is.
        for field, value in self.data.model_dump(exclude_none=True).items():
            setattr(outgoing_ip, field, value)

        # Checking the IP first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="IP is already added.",
                ) from None
            raise

        # `updated_at` comes from the database.
        await self.session.refresh(outgoing_ip)
        return UpdateOutgoingIPResponse.model_validate(outgoing_ip)
