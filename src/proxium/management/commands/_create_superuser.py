import asyncio
import getpass
import sys
from typing import TYPE_CHECKING, ClassVar, TextIO

from asyncpg import UniqueViolationError
from pydantic import SecretStr, ValidationError
from sqlalchemy import Result, Select, select
from sqlalchemy.exc import IntegrityError, NoResultFound

from proxium.core import SuperuserSettings, superuser_settings
from proxium.db import Hash, UserModel, session_manager
from proxium.management._base import BaseAsyncCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from pydantic_core import ErrorDetails


class EmailTakenError(Exception):
    pass


class PasswordMismatchError(Exception):
    pass


class CreateSuperuserCommand(BaseAsyncCommand):
    """Like Django's `createsuperuser`: prompts for the email and password, unless --no-input.

    `settings` (env) fill in missing flags only with --no-input: a prompt never gets skipped by a forgotten variable.
    Name and surname are never prompted, blank if unset.
    """

    name: ClassVar[str] = "createsuperuser"
    help: ClassVar[str] = "Create an active superuser."

    def __init__(
        self,
        *,
        settings: SuperuserSettings = superuser_settings,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        super().__init__(
            stdout=stdout,
            stderr=stderr,
        )
        self._settings: SuperuserSettings = settings

    def add_arguments(self, parser: ArgumentParser, /) -> None:
        parser.add_argument(
            "--email",
            help="Superuser's email, not prompted then. With --no-input SUPERUSER_EMAIL by default.",
        )
        parser.add_argument(
            "--name",
            help="Superuser's name, blank by default. With --no-input SUPERUSER_NAME by default.",
        )
        parser.add_argument(
            "--surname",
            help="Superuser's surname, blank by default. With --no-input SUPERUSER_SURNAME by default.",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Don't prompt, take what's missing from SUPERUSER_* variables. "
            "The email must be given, the password comes only from SUPERUSER_PASSWORD.",
        )
        parser.add_argument(
            "--if-missing",
            action="store_true",
            help="With --no-input: skip, not fail, if the email is taken. Other errors still fail. "
            "For start scripts, e.g. in Docker.",
        )

    async def ahandle(self, args: Namespace, /) -> None:
        if args.if_missing and args.interactive:
            raise CommandError("--if-missing works only with --no-input.")
        if args.interactive and not sys.stdin.isatty():
            raise CommandError("Not running in a TTY, use --no-input.")

        settings: SuperuserSettings = self._get_settings(args)
        if args.interactive:
            email = await self._prompt_email(settings)
            password = self._prompt_password(settings)
        else:
            if settings.email is None:
                raise CommandError("Pass --email or set SUPERUSER_EMAIL with --no-input.")
            if settings.password is None:
                raise CommandError("Set SUPERUSER_PASSWORD with --no-input.")
            email = settings.email
            password = settings.password

        user: UserModel = UserModel(
            email=email,
            name=settings.name or "",
            surname=settings.surname or "",
            # Hashing is slow CPU work, it would stall the loop.
            password=await asyncio.to_thread(Hash.create, password.get_secret_value()),
            is_active=True,
            is_superuser=True,
        )
        async with session_manager.session() as session:
            session.add(user)
            # The prompt's check may be stale by now.
            try:
                await session.commit()
            except IntegrityError as err:
                if err.orig.sqlstate == UniqueViolationError.sqlstate and args.if_missing:
                    self.stdout.write("That email is already taken, skipped.\n")
                    return
                if err.orig.sqlstate == UniqueViolationError.sqlstate:
                    raise CommandError(
                        "That email is already taken.",
                    ) from None
                raise

        self.stdout.write("Superuser created successfully.\n")

    def _get_settings(self, args: Namespace, /) -> SuperuserSettings:
        """The flags, checked against the same limits as env. Env fills in missing ones only with --no-input."""
        email: str | None = args.email
        password: SecretStr | None = None
        name: str | None = args.name
        surname: str | None = args.surname
        if not args.interactive:
            email = self._settings.email if email is None else email
            password = self._settings.password
            name = self._settings.name if name is None else name
            surname = self._settings.surname if surname is None else surname

        # Init values win over env, None included: interactively nothing comes from env.
        try:
            return SuperuserSettings(
                email=email,
                password=password,
                name=name,
                surname=surname,
            )
        except ValidationError as err:
            raise CommandError(self._format(err)) from None

    async def _prompt_email(self, settings: SuperuserSettings, /) -> str:
        """The given email if it's free, else ask until a valid free one."""
        email: str = settings.email if settings.email is not None else self._read_email(settings)
        while True:
            try:
                await self._check_email(email)
            except EmailTakenError:
                self._error("That email is already taken.")
            else:
                return email

            email = self._read_email(settings)

    def _read_email(self, settings: SuperuserSettings, /) -> str:
        while True:
            try:
                settings.email = input("Email: ")
            except ValidationError as err:
                self._error(self._format(err))
            else:
                break

        # Can't be None after a successful assignment of a value.
        if settings.email is None:
            raise RuntimeError("Email is not set.")

        return settings.email

    def _prompt_password(self, settings: SuperuserSettings, /) -> SecretStr:
        while True:
            password: SecretStr = self._read_password(settings)
            try:
                self._check_password(password)
            except PasswordMismatchError:
                self._error("Your passwords didn't match.")
            else:
                return password

    def _read_password(self, settings: SuperuserSettings, /) -> SecretStr:
        while True:
            try:
                settings.password = SecretStr(getpass.getpass())
            except ValidationError as err:
                self._error(self._format(err))
            else:
                break

        # Can't be None after a successful assignment of a value.
        if settings.password is None:
            raise RuntimeError("Password is not set.")

        return settings.password

    def _check_password(self, password: SecretStr, /) -> None:
        if getpass.getpass("Password (again): ") != password.get_secret_value():
            raise PasswordMismatchError()

    def _get_user_statement(self, email: str, /) -> Select[tuple[UserModel]]:
        return select(UserModel).where(UserModel.email == email)

    async def _check_email(self, email: str, /) -> None:
        async with session_manager.session() as session:
            result: Result[tuple[UserModel]] = await session.execute(self._get_user_statement(email))
            try:
                result.scalars().one()
            except NoResultFound:
                return

        raise EmailTakenError()

    def _format(self, err: ValidationError, /) -> str:
        """`Email: value is not a valid email address...`, one per field."""
        messages: list[ErrorDetails] = err.errors(include_url=False)
        return "; ".join(f"{str(message['loc'][0]).capitalize()}: {message['msg']}" for message in messages)

    def _error(self, message: str, /) -> None:
        self.stderr.write(f"Error: {message}\n")
