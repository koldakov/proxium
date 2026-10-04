from datetime import datetime
from typing import Annotated

from pydantic import Field, IPvAnyNetwork, field_validator
from sqlalchemy import Result, Select, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import SettingsModel
from proxium.helpers import BaseSchema


class UpdateSettingsRequest(BaseSchema):
    """All settings at once, as the settings page sends them. Timeouts are in seconds, up to a day."""

    # Host bits are refused, e.g. 10.0.0.1/8.
    guard_allow: Annotated[
        list[IPvAnyNetwork],
        Field(
            max_length=100,
        ),
    ]
    handshake_timeout: Annotated[
        float,
        Field(
            gt=0,
            le=86400,
        ),
    ]
    idle_timeout: Annotated[
        float,
        Field(
            gt=0,
            le=86400,
        ),
    ]
    connect_timeout: Annotated[
        float,
        Field(
            gt=0,
            le=86400,
        ),
    ]
    # Seconds, up to an hour: a revoked account keeps working for this long.
    cache_ttl: Annotated[
        float,
        Field(
            gt=0,
            le=3600,
        ),
    ]

    @field_validator(
        "guard_allow",
        mode="after",
    )
    @classmethod
    def _check_unique(cls, value: list[IPvAnyNetwork]) -> list[IPvAnyNetwork]:
        if len(set(value)) != len(value):
            raise ValueError("Networks must be unique.")
        return value


class UpdateSettingsResponse(BaseSchema):
    id: int
    guard_allow: list[IPvAnyNetwork]
    handshake_timeout: float
    idle_timeout: float
    connect_timeout: float
    cache_ttl: float
    created_at: datetime
    updated_at: datetime


class UpdateSettingsService(BaseUserAuthenticatedService[UpdateSettingsResponse]):
    data: UpdateSettingsRequest

    @property
    def _get_settings_statement(self) -> Select[tuple[SettingsModel]]:
        return select(SettingsModel)

    async def _get_settings(self) -> SettingsModel:
        result: Result[tuple[SettingsModel]] = await self.session.execute(self._get_settings_statement)
        # The migration adds the only row: none is a broken database, a 500.
        return result.scalars().one()

    async def process(self, *args, **kwargs) -> UpdateSettingsResponse:
        settings: SettingsModel = await self._get_settings()
        # Python mode keeps networks `ipaddress` objects, the column takes them as is.
        for field, value in self.data.model_dump().items():
            setattr(settings, field, value)

        await self.session.commit()

        # `updated_at` comes from the database.
        await self.session.refresh(settings)
        return UpdateSettingsResponse.model_validate(settings)
