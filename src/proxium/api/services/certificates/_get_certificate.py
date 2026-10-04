from datetime import datetime
from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import CertificateModel, Permission
from proxium.helpers import BaseSchema


class GetCertificateResponse(BaseSchema):
    id: int
    # PEM chain, public: clients of a self-signed one need it to trust the proxy. The key is never returned.
    certificate: str
    names: list[str]
    fingerprint: str
    is_self_signed: bool
    not_valid_before: datetime
    not_valid_after: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GetCertificateService(BaseUserAuthenticatedService[GetCertificateResponse]):
    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.CERTIFICATES_VIEW})

    id: int

    @property
    def _get_certificate_statement(self) -> Select[tuple[CertificateModel]]:
        return select(CertificateModel).where(CertificateModel.id == self.id)

    async def process(self, *args, **kwargs) -> GetCertificateResponse:
        result: Result[tuple[CertificateModel]] = await self.session.execute(self._get_certificate_statement)
        try:
            certificate: CertificateModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Certificate not found.",
            ) from None

        return GetCertificateResponse.model_validate(certificate)
