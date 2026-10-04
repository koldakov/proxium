from datetime import UTC, datetime
from typing import ClassVar

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from sqlalchemy import Result, Select, Update, select, update
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import CertificateModel, Permission
from proxium.helpers import BaseSchema


class ActivateCertificateRequest(BaseSchema):
    # The id of the active certificate the client saw, null if none. If it has changed since, e.g. another admin
    # activated one, the request fails: a stale confirmation never turns off a certificate nobody saw.
    replaces: int | None = None


class ActivateCertificateService(BaseUserAuthenticatedService[None]):
    """Make it the one TLS clients get, turning the active one off in the same transaction.

    New connections get it within a few seconds, open ones keep the old one. Activating the active one changes nothing.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.CERTIFICATES_ACTIVATE})

    id: int
    data: ActivateCertificateRequest

    @property
    def _lock_certificate_statement(self) -> Select[tuple[CertificateModel]]:
        # Held till commit: a delete can't remove it while it's being activated.
        return select(CertificateModel).where(CertificateModel.id == self.id).with_for_update()

    @property
    def _lock_active_certificate_statement(self) -> Select[tuple[int]]:
        # Held till commit: a concurrent activation waits for it, then finds the active one changed.
        return select(CertificateModel.id).where(CertificateModel.is_active.is_(True)).with_for_update()

    @property
    def _deactivate_all_statement(self) -> Update:
        return update(CertificateModel).where(CertificateModel.is_active.is_(True)).values(is_active=False)

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
            return

        if certificate.not_valid_after <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The certificate has expired, clients would refuse it.",
            )

        active: Result[tuple[int]] = await self.session.execute(self._lock_active_certificate_statement)
        if active.scalars().one_or_none() != self.data.replaces:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The active certificate has changed meanwhile, reload and try again.",
            )

        await self.session.execute(self._deactivate_all_statement)
        certificate.is_active = True

        # With no active certificate there's no row to lock: two first activations meet at the unique index.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate == UniqueViolationError.sqlstate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The active certificate has changed meanwhile, reload and try again.",
                ) from None
            raise
