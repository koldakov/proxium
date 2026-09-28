import signal
import sys
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING, ClassVar, TextIO

import uvloop

from proxium.db import session_manager

if TYPE_CHECKING:
    from collections.abc import Sequence


class CommandError(Exception):
    """Stops the command: the message goes to stderr, the exit code is 1."""


class BaseCommand(ABC):
    """One management command, like Django's. `name` is what goes on the command line.

    Output goes to `self.stdout` and `self.stderr`: the given streams, or the current `sys` ones.
    """

    name: ClassVar[str]
    help: ClassVar[str] = ""

    def __init__(
        self,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self._stdout: TextIO | None = stdout
        self._stderr: TextIO | None = stderr

    # Looked up on use, not on init: `sys` streams may be swapped later, e.g. to capture output.
    @property
    def stdout(self) -> TextIO:
        return self._stdout or sys.stdout

    @property
    def stderr(self) -> TextIO:
        return self._stderr or sys.stderr

    def add_arguments(self, parser: ArgumentParser, /) -> None:  # noqa: B027
        """Add the command's own arguments to `parser`."""

    @abstractmethod
    def handle(self, args: Namespace, /) -> None:
        """Run the command. Raise `CommandError` to fail with a message."""

    def run(self, args: Namespace, /) -> int:
        """`handle` with failures turned into a message on stderr. Returns the exit code."""
        try:
            self.handle(args)
        except CommandError as err:
            self.stderr.write(f"Error: {err}\n")
            return 1
        # Ctrl+C anywhere, Ctrl+D at a prompt.
        except KeyboardInterrupt, EOFError:
            self.stderr.write("\nOperation cancelled.\n")
            return 1
        return 0


class BaseAsyncCommand(BaseCommand, ABC):
    """A command with async `ahandle`, e.g. for the database. `session_manager` is closed once it returns."""

    @abstractmethod
    async def ahandle(self, args: Namespace, /) -> None:
        """Run the command in the event loop. Raise `CommandError` to fail with a message."""

    def handle(self, args: Namespace, /) -> None:
        uvloop.run(self._handle(args))

    async def _handle(self, args: Namespace, /) -> None:
        # The loop's SIGINT handler only cancels the task: a blocking prompt would wait for Enter.
        # The default one raises KeyboardInterrupt right where it hits, prompts included.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            await self.ahandle(args)
        finally:
            await session_manager.close()


class ManagementUtility:
    """Picks a command by the first argument and runs it with the rest."""

    def __init__(
        self,
        commands: Sequence[BaseCommand],
        /,
        *,
        prog: str = "proxium-manage",
    ) -> None:
        self._commands: dict[str, BaseCommand] = {command.name: command for command in commands}
        self._prog: str = prog

    def _create_parser(self) -> ArgumentParser:
        parser = ArgumentParser(prog=self._prog)
        subparsers = parser.add_subparsers(
            dest="command",
            metavar="command",
            required=True,
        )
        for command in self._commands.values():
            subparser = subparsers.add_parser(
                command.name,
                help=command.help,
                description=command.help,
            )
            command.add_arguments(subparser)
        return parser

    def run(self, args: Sequence[str] | None = None, /) -> int:
        namespace: Namespace = self._create_parser().parse_args(args)
        command: BaseCommand = self._commands[namespace.command]
        return command.run(namespace)
