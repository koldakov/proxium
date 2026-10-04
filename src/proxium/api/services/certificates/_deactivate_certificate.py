from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import CertificateModel


class DeactivateCertificateService(BaseUserAuthenticatedService[None]):
    """Turn it off. Without an active certificate TLS is off: TLS clients are refused, open connections stay."""

    id: int

    @property
    def _get_certificate_statement(self) -> Select[tuple[CertificateModel]]:
        return select(CertificateModel).where(CertificateModel.id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[CertificateModel]] = await self.session.execute(self._get_certificate_statement)
        try:
            certificate: CertificateModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Certificate not found.",
            ) from None

        certificate.is_active = False
        await self.session.commit()
