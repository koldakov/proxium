from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import CertificateModel, Permission


class DeleteCertificateService(BaseUserAuthenticatedService[None]):
    """The active certificate stays: deactivate it first, so turning TLS off is a choice of its own."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.CERTIFICATES_DELETE})

    id: int

    @property
    def _lock_certificate_statement(self) -> Select[tuple[CertificateModel]]:
        # Held till commit: it can't be activated between the check and the delete.
        return select(CertificateModel).where(CertificateModel.id == self.id).with_for_update()

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[CertificateModel]] = await self.session.execute(self._lock_certificate_statement)
        try:
            certificate: CertificateModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Certificate not found.",
            ) from None

        if certificate.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The certificate is active, deactivate it first.",
            )

        await self.session.delete(certificate)
        await self.session.commit()
