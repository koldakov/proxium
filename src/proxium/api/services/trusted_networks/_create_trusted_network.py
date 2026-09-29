from datetime import datetime
from typing import Annotated

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, IPvAnyNetwork, StringConstraints
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import TrustedNetworkModel
from proxium.helpers import BaseSchema


class CreateTrustedNetworkRequest(BaseSchema):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ]
    # `10.0.0.0/8`, or a single address like `10.0.0.1`. Host bits are rejected: `10.0.0.1/8` is a typo.
    network: IPvAnyNetwork
    is_active: bool = True


class CreateTrustedNetworkResponse(BaseSchema):
    id: int
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=255,
        ),
    ]
    network: IPvAnyNetwork
    is_active: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CreateTrustedNetworkService(BaseUserAuthenticatedService[CreateTrustedNetworkResponse]):
    data: CreateTrustedNetworkRequest

    async def process(self, *args, **kwargs) -> CreateTrustedNetworkResponse:
        network: TrustedNetworkModel = TrustedNetworkModel(
            name=self.data.name,
            network=self.data.network,
            is_active=self.data.is_active,
            created_by_id=self.user.id,
        )
        self.session.add(network)

        # Checking the network first would race.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Network is already trusted.",
                ) from None
            raise

        # Timestamps come from the database.
        await self.session.refresh(network)
        return CreateTrustedNetworkResponse.model_validate(network)
