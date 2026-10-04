from datetime import datetime
from ipaddress import ip_address
from typing import Annotated, ClassVar, Literal

from asyncpg import UniqueViolationError
from fastapi import HTTPException, status
from pydantic import Field, StringConstraints, field_validator
from sqlalchemy import Result, Select, Update, select, update
from sqlalchemy.exc import IntegrityError

from proxium.api.services import BaseUserAuthenticatedService
from proxium.certificates import CertificateInfo, InvalidCertificateError, generate_self_signed, read_certificate
from proxium.core import Hostname
from proxium.db import CertificateModel, Encrypted
from proxium.helpers import BaseSchema


class UploadCertificateRequest(BaseSchema):
    """A certificate issued elsewhere, e.g. by Let's Encrypt or a company CA, or a self-signed one."""

    source: Literal["upload"]
    # PEM chain, the server's certificate first, e.g. the contents of `fullchain.pem`.
    certificate: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=65536,
        ),
    ]
    # PEM key without a password, e.g. the contents of `privkey.pem`. Stored encrypted, never returned.
    private_key: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=65536,
        ),
    ]
    # Give it to TLS clients right away, turning the active one off in the same transaction.
    activate: bool = False
    # With `activate`: the id of the active certificate the client saw, null if none. If it has changed since,
    # e.g. another admin activated one, the request fails: a stale confirmation never turns off an unseen one.
    replaces: int | None = None


class GenerateCertificateRequest(BaseSchema):
    """A new self-signed certificate: clients trust it only if told to."""

    source: Literal["generate"]
    # Host names and IPs clients connect to, e.g. `proxy.example.com`.
    names: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=100,
        ),
    ]
    days: Annotated[
        int,
        Field(
            ge=1,
            le=3650,
        ),
    ] = 365
    # Give it to TLS clients right away, turning the active one off in the same transaction.
    activate: bool = False
    # With `activate`: the id of the active certificate the client saw, null if none. If it has changed since,
    # e.g. another admin activated one, the request fails: a stale confirmation never turns off an unseen one.
    replaces: int | None = None

    @classmethod
    def _check_name(cls, name: str, /) -> str:
        try:
            return str(ip_address(name))
        except ValueError:
            return str(Hostname(name))

    @field_validator(
        "names",
        mode="after",
    )
    @classmethod
    def _check_names(cls, names: list[str]) -> list[str]:
        # The same name twice is kept once.
        return list(dict.fromkeys(cls._check_name(name.strip()) for name in names))


# A plain alias, not `type`: FastAPI reads the union and its discriminator straight from it.
CreateCertificateRequest = Annotated[
    UploadCertificateRequest | GenerateCertificateRequest,
    Field(
        discriminator="source",
    ),
]


class CreateCertificateResponse(BaseSchema):
    id: int
    names: list[str]
    fingerprint: str
    is_self_signed: bool
    not_valid_before: datetime
    not_valid_after: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateCertificateService(BaseUserAuthenticatedService[CreateCertificateResponse]):
    """Added inactive, unless `activate`: then it replaces the active one, if that's still `replaces`."""

    # Partial unique index of the one active certificate.
    active_index: ClassVar[str] = "uq_certificates_active"

    data: CreateCertificateRequest

    @property
    def _lock_active_certificate_statement(self) -> Select[tuple[int]]:
        # Held till commit: a concurrent activation waits for it, then finds the active one changed.
        return select(CertificateModel.id).where(CertificateModel.is_active.is_(True)).with_for_update()

    @property
    def _deactivate_all_statement(self) -> Update:
        return update(CertificateModel).where(CertificateModel.is_active.is_(True)).values(is_active=False)

    async def _deactivate_replaced(self) -> None:
        result: Result[tuple[int]] = await self.session.execute(self._lock_active_certificate_statement)
        if result.scalars().one_or_none() != self.data.replaces:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The active certificate has changed meanwhile, reload and try again.",
            )
        await self.session.execute(self._deactivate_all_statement)

    def _read(self) -> CertificateInfo:
        if isinstance(self.data, UploadCertificateRequest):
            return read_certificate(self.data.certificate, self.data.private_key)
        return read_certificate(*generate_self_signed(self.data.names, days=self.data.days))

    async def process(self, *args, **kwargs) -> CreateCertificateResponse:
        try:
            info: CertificateInfo = self._read()
        except InvalidCertificateError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(err),
            ) from None

        certificate: CertificateModel = CertificateModel(
            certificate=info.certificate,
            private_key=Encrypted.create(info.private_key),
            names=info.names,
            fingerprint=info.fingerprint,
            is_self_signed=info.is_self_signed,
            not_valid_before=info.not_valid_before,
            not_valid_after=info.not_valid_after,
            is_active=self.data.activate,
        )
        if self.data.activate:
            await self._deactivate_replaced()
        self.session.add(certificate)

        # Checking the fingerprint first would race. With no active certificate there's no row to lock:
        # two first activations meet at the unique index of the active one.
        try:
            await self.session.commit()
        except IntegrityError as err:
            if err.orig.sqlstate != UniqueViolationError.sqlstate:
                raise
            # The driver's own error names the constraint, SQLAlchemy keeps it as the cause.
            cause = err.orig.__cause__
            if isinstance(cause, UniqueViolationError) and cause.constraint_name == self.active_index:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The active certificate has changed meanwhile, reload and try again.",
                ) from None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This certificate is already uploaded.",
            ) from None

        # Timestamps come from the database.
        await self.session.refresh(certificate)
        return CreateCertificateResponse.model_validate(certificate)
