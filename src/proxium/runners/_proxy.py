import asyncio
import logging
import signal
from typing import TYPE_CHECKING, ClassVar, Final

import uvloop

from proxium.auth import BasicAccountAuthenticator, TokenAccountAuthenticator, TrustedNetworkAuthenticator
from proxium.core import proxy_settings
from proxium.db import session_manager
from proxium.proxy import (
    BasicCredentials,
    BearerCredentials,
    DirectConnector,
    DispatchAuthenticator,
    HttpInbound,
    Listener,
    ListenError,
    LoggingObserver,
    Profile,
    ProxyServer,
    Socks5Inbound,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from proxium.core import ListenAddress, LogLevel

logger = logging.getLogger(__name__)

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class ProxyRunner:
    """Runs the proxy until SIGINT/SIGTERM, then shuts it down gracefully. A second signal forces the stop."""

    signals: ClassVar[tuple[signal.Signals, ...]] = (
        signal.SIGINT,
        signal.SIGTERM,
    )

    def __init__(
        self,
        *,
        listen: Sequence[ListenAddress] = proxy_settings.listen,
        graceful_timeout: float = proxy_settings.graceful_timeout,
        log_level: LogLevel = proxy_settings.log_level,
    ) -> None:
        self._log_level: LogLevel = log_level
        profile = self._create_default_profile()
        self._graceful_timeout: float = graceful_timeout
        self._listeners: list[Listener] = [
            Listener(
                host=host,
                ports=address.ports,
                profile=profile,
            )
            for address in listen
            for host in address.hosts
        ]

        self._server: ProxyServer = ProxyServer()
        self._stop: asyncio.Event = asyncio.Event()

    def _create_default_profile(self) -> Profile:
        """HTTP and SOCKS5 proxy for accounts and trusted networks from the database, going straight to targets."""
        return Profile(
            inbounds=[
                HttpInbound(),
                Socks5Inbound(),
            ],
            authenticator=DispatchAuthenticator(
                {
                    BasicCredentials: BasicAccountAuthenticator(),
                    BearerCredentials: TokenAccountAuthenticator(),
                },
                without_credentials=TrustedNetworkAuthenticator(),
            ),
            connector=DirectConnector(),
            observers=[LoggingObserver()],
        )

    def run(self) -> None:
        logging.basicConfig(level=self._log_level, format=LOG_FORMAT)
        try:
            uvloop.run(self._serve())
        except asyncio.CancelledError:
            logger.warning("Forced shutdown")
        except ListenError as error:
            logger.error("%s", error)
            raise SystemExit(1) from None

    async def _serve(self) -> None:
        self._on_signal(self._stop.set)
        await self._server.update(self._listeners)
        await self._stop.wait()

        # A second signal cuts the graceful wait short.
        if task := asyncio.current_task():
            self._on_signal(task.cancel)

        logger.info("Shutting down, press Ctrl+C again to force")
        await self._server.shutdown(timeout=self._graceful_timeout)
        await session_manager.close()

    def _on_signal(self, callback: Callable[[], object], /) -> None:
        loop = asyncio.get_running_loop()
        for sig in self.signals:
            loop.add_signal_handler(sig, callback)


def run_proxy() -> None:
    runner: ProxyRunner = ProxyRunner()
    runner.run()
