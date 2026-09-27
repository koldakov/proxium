import sys
from typing import TYPE_CHECKING

from hypercorn.__main__ import main

if TYPE_CHECKING:
    from collections.abc import Sequence


class HypercornConfig:
    worker_class = "uvloop"


hypercorn_config: HypercornConfig = HypercornConfig()


def run_api(args: Sequence[str] | None = None) -> int:
    """Serve the API with hypercorn. Extra args go to hypercorn as is, e.g. `--bind 0.0.0.0:8000`."""
    argv: Sequence[str] = args if args is not None else sys.argv[1:]
    return main(
        [
            "proxium.api:app",
            "--config=python:proxium.runners._api.hypercorn_config",
            *argv,
        ],
    )
