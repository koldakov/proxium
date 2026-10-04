from datetime import datetime
from typing import Annotated, ClassVar

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyAddress, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import OutgoingIPModel, Permission
from proxium.helpers import BaseSchema


class CreateOutgoingIPRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    # An address of the proxy server, e.g. `203.0.113.11`. Not checked: the API may run on another host.
    ip: IPvAnyAddress


class CreateOutgoingIPResponse(BaseSchema):
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


class CreateOutgoingIPService(BaseUserAuthenticatedService[CreateOutgoingIPResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.OUTGOING_IPS_ADD})

    data: CreateOutgoingIPRequest

    async def process(self, *args, **kwargs) -> CreateOutgoingIPResponse:
        outgoing_ip: OutgoingIPModel = OutgoingIPModel(
            name=self.data.name,
            ip=self.data.ip,
            created_by_id=self.user.id,
        )
        self.session.add(outgoing_ip)

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

        # Timestamps come from the database.
        await self.session.refresh(outgoing_ip)
        return CreateOutgoingIPResponse.model_validate(outgoing_ip)
