from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

# The fixture with the shared loop, see `tests.fixtures.database.loop_runner`.
LOOP_RUNNER_FIXTURE: Final[str] = "loop_runner"


def async_step[R](step: Callable[..., Coroutine[Any, Any, R]], /) -> Callable[..., R]:
    """Run an async step on the shared loop: pytest-bdd calls only sync ones. Goes under `@given`/`@when`/`@then`.

    The step's arguments are filled as usual: fixtures and values parsed from the step text.
    """

    @functools.wraps(step)
    def run(**kwargs: Any) -> R:
        runner: asyncio.Runner = kwargs.pop(LOOP_RUNNER_FIXTURE)
        return runner.run(step(**kwargs))

    # pytest-bdd fills the arguments by the signature: the loop is asked for as one more fixture.
    signature = inspect.signature(step)
    runner_parameter = inspect.Parameter(LOOP_RUNNER_FIXTURE, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    run.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[*signature.parameters.values(), runner_parameter],
    )
    return run
