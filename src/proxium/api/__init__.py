from typing import TYPE_CHECKING

from ._app import ProxiumAPI, proxium_api

if TYPE_CHECKING:
    from fastapi import FastAPI

app: FastAPI = proxium_api

__all__ = [
    "ProxiumAPI",
    "app",
    "proxium_api",
]
