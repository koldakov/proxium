from datetime import datetime
from typing import ClassVar

from pydantic import IPvAnyNetwork
from sqlalchemy import Result, Select, select

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, SettingsModel
from proxium.helpers import BaseSchema


class GetSettingsResponse(BaseSchema):
    id: int
    guard_allow: list[IPvAnyNetwork]
    handshake_timeout: float
    idle_timeout: float
    connect_timeout: float
    basic_account_cache_ttl: float
    basic_account_refusal_cache_ttl: float
    token_account_cache_ttl: float
    token_account_refusal_cache_ttl: float
    trusted_network_cache_ttl: float
    trusted_network_refusal_cache_ttl: float
    certificate_cache_ttl: float
    created_at: datetime
    updated_at: datetime


class GetSettingsService(BaseUserAuthenticatedService[GetSettingsResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.SETTINGS_VIEW})

    @property
    def _get_settings_statement(self) -> Select[tuple[SettingsModel]]:
        return select(SettingsModel)

    async def _get_settings(self) -> SettingsModel:
        result: Result[tuple[SettingsModel]] = await self.session.execute(self._get_settings_statement)
        # The migration adds the only row: none is a broken database, a 500.
        return result.scalars().one()

    async def process(self, *args, **kwargs) -> GetSettingsResponse:
        settings: SettingsModel = await self._get_settings()
        return GetSettingsResponse.model_validate(settings)
