from fastapi import APIRouter

from ._basic_proxy_accounts import basic_proxy_accounts_router
from ._certificates import certificates_router
from ._groups import groups_router
from ._outgoing_ips import outgoing_ips_router
from ._permissions import permissions_router
from ._policies import policies_router
from ._settings import settings_router
from ._token_proxy_accounts import token_proxy_accounts_router
from ._tokens import tokens_router
from ._traffic import traffic_router
from ._trusted_networks import trusted_networks_router
from ._users import users_router

__all__ = [
    "api_router",
]

api_router: APIRouter = APIRouter(prefix="/api")
api_router.include_router(tokens_router)
api_router.include_router(users_router)
api_router.include_router(groups_router)
api_router.include_router(permissions_router)
api_router.include_router(basic_proxy_accounts_router)
api_router.include_router(token_proxy_accounts_router)
api_router.include_router(trusted_networks_router)
api_router.include_router(traffic_router)
api_router.include_router(outgoing_ips_router)
api_router.include_router(policies_router)
api_router.include_router(certificates_router)
api_router.include_router(settings_router)
