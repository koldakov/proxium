import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from asyncpg import UniqueViolationError
from sqlalchemy import Result, Select, Update, select, update
from sqlalchemy.exc import IntegrityError

from proxium.certificates import CertificateInfo, InvalidCertificateError, read_certificate
from proxium.db import CertificateModel, Encrypted, session_manager
from proxium.management._base import BaseAsyncCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from sqlalchemy.sql.dml import ReturningUpdate


class ImportCertificateCommand(BaseAsyncCommand):
    """Add a certificate from PEM files and activate it, e.g. from certbot's `--deploy-hook` after a renewal.

    Activating turns the active certificate off: it asks first, unless --no-input. The same certificate
    imported again is only activated. New TLS connections get it within a few seconds, no proxy restart.
    """

    name: ClassVar[str] = "importcert"
    help: ClassVar[str] = "Add a TLS certificate from PEM files and activate it, turning the active one off."

    @staticmethod
    def _get_certificate_statement(info: CertificateInfo, /) -> Select[tuple[CertificateModel]]:
        return select(CertificateModel).where(CertificateModel.fingerprint == info.fingerprint)

    @property
    def _get_active_certificate_statement(self) -> Select[tuple[CertificateModel]]:
        return select(CertificateModel).where(CertificateModel.is_active.is_(True))

    @property
    def _lock_active_certificate_statement(self) -> Select[tuple[int]]:
        return select(CertificateModel.id).where(CertificateModel.is_active.is_(True)).with_for_update()

    @property
    def _deactivate_all_statement(self) -> Update:
        return update(CertificateModel).where(CertificateModel.is_active.is_(True)).values(is_active=False)

    @staticmethod
    def _activate_statement(certificate_id: int, /) -> ReturningUpdate[tuple[int]]:
        return (
            update(CertificateModel)
            .where(CertificateModel.id == certificate_id)
            .values(is_active=True)
            .returning(CertificateModel.id)
        )

    @staticmethod
    def _describe(names: list[str], /) -> str:
        return ", ".join(names) if names else "no names"

    def _read(self, cert: Path, key: Path, /) -> CertificateInfo:
        try:
            certificate = cert.read_text()
        except OSError as err:
            raise CommandError(f"Can't read {cert}: {err.strerror}.") from None
        try:
            private_key = key.read_text()
        except OSError as err:
            raise CommandError(f"Can't read {key}: {err.strerror}.") from None

        try:
            return read_certificate(certificate, private_key)
        except InvalidCertificateError as err:
            raise CommandError(str(err)) from None

    def _confirm(self, active: CertificateModel, /) -> None:
        answer = input(
            f"The certificate for {self._describe(active.names)}, valid until {active.not_valid_after:%Y-%m-%d}, "
            "is active and will be turned off. Continue? [y/N] ",
        )
        if answer.strip().lower() not in {"y", "yes"}:
            raise CommandError("Nothing changed.")

    @staticmethod
    def _create_model(info: CertificateInfo, /) -> CertificateModel:
        return CertificateModel(
            certificate=info.certificate,
            private_key=Encrypted.create(info.private_key),
            names=info.names,
            fingerprint=info.fingerprint,
            is_self_signed=info.is_self_signed,
            not_valid_before=info.not_valid_before,
            not_valid_after=info.not_valid_after,
            is_active=True,
        )

    def add_arguments(self, parser: ArgumentParser, /) -> None:
        parser.add_argument(
            "--cert",
            required=True,
            type=Path,
            help="PEM chain, the server's certificate first, e.g. fullchain.pem.",
        )
        parser.add_argument(
            "--key",
            required=True,
            type=Path,
            help="PEM private key without a password, e.g. privkey.pem.",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Don't ask before turning the active certificate off.",
        )

    async def ahandle(self, args: Namespace, /) -> None:
        if args.interactive and not sys.stdin.isatty():
            raise CommandError("Not running in a TTY, use --no-input.")

        info: CertificateInfo = self._read(args.cert, args.key)
        # Looked up before asking: no transaction stays open while a person thinks.
        async with session_manager.session() as session:
            result: Result[tuple[CertificateModel]] = await session.execute(self._get_certificate_statement(info))
            existing: CertificateModel | None = result.scalars().one_or_none()
            result = await session.execute(self._get_active_certificate_statement)
            active: CertificateModel | None = result.scalars().one_or_none()

        if existing is not None and existing.is_active:
            self.stdout.write(f"The certificate for {self._describe(existing.names)} is already active.\n")
            return

        if active is not None and args.interactive:
            self._confirm(active)

        async with session_manager.session() as session:
            # Held till commit: a concurrent activation waits for it.
            locked: Result[tuple[int]] = await session.execute(self._lock_active_certificate_statement)
            # The one turned off must be the one asked about. Without asking, whichever is active is replaced.
            if args.interactive and locked.scalars().one_or_none() != (None if active is None else active.id):
                raise CommandError("The active certificate has changed meanwhile, run the command again.")

            await session.execute(self._deactivate_all_statement)
            if existing is None:
                session.add(self._create_model(info))
            else:
                activated: Result[tuple[int]] = await session.execute(self._activate_statement(existing.id))
                if activated.scalars().one_or_none() is None:
                    raise CommandError("The certificate was deleted meanwhile, run the command again.")

            # With no active certificate there's no row to lock: two first activations meet at the unique index.
            try:
                await session.commit()
            except IntegrityError as err:
                if err.orig.sqlstate == UniqueViolationError.sqlstate:
                    raise CommandError("Certificates changed meanwhile, run the command again.") from None
                raise

        self.stdout.write(
            f"The certificate for {self._describe(info.names)} is active, "
            f"valid until {info.not_valid_after:%Y-%m-%d}.\n",
        )
