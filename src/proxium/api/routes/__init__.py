from fastapi import APIRouter

from ._tokens import tokens_router
from ._users import users_router

__all__ = [
    "api_router",
]

api_router: APIRouter = APIRouter(prefix="/api")
api_router.include_router(tokens_router)
api_router.include_router(users_router)
