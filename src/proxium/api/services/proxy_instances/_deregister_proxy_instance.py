from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Result, Select, and_, func, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import Permission, ProxyInstanceModel, ProxyInstanceStatus


class DeregisterProxyInstanceService(BaseUserAuthenticatedService[None]):
    """Take a stopped or unknown instance off the lists. Kept in the database: a report of its process registers it
    again, it's alive after all.
    """

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.PROXY_INSTANCES_DEREGISTER})

    id: int

    @property
    def _get_proxy_instance_statement(self) -> Select[tuple[ProxyInstanceModel, bool]]:
        is_alive = and_(
            ProxyInstanceModel.status != ProxyInstanceStatus.STOPPED,
            ProxyInstanceModel.expires_at >= func.now(),
        )
        return select(
            ProxyInstanceModel,
            is_alive,
        ).where(
            ProxyInstanceModel.id == self.id,
            ProxyInstanceModel.is_deleted.is_(False),
        )

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[ProxyInstanceModel, bool]] = await self.session.execute(
            self._get_proxy_instance_statement,
        )
        try:
            instance, is_alive = result.tuples().one()
        except NoResultFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proxy instance not found.",
            ) from None

        # No lock: one that reports meanwhile registers again on its next report anyway.
        if is_alive:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The instance is alive: only stopped and unknown ones can be deregistered.",
            )

        instance.is_deleted = True
        await self.session.commit()
