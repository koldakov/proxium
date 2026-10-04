from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy import Delete, Result, Select, delete, select
from sqlalchemy.exc import NoResultFound

from proxium.api.services import BaseUserAuthenticatedService
from proxium.db import GroupModel, GroupPermissionModel, Permission, UserGroupModel


class DeleteGroupService(BaseUserAuthenticatedService[None]):
    """Its users lose its permissions with their next request, the users themselves stay."""

    required_permissions: ClassVar[frozenset[Permission]] = frozenset({Permission.GROUPS_DELETE})

    id: int

    @property
    def _get_group_statement(self) -> Select[tuple[GroupModel]]:
        # Locked: a user added to it meanwhile waits and then fails, instead of failing the delete.
        return select(GroupModel).where(GroupModel.id == self.id).with_for_update()

    @property
    def _delete_users_statement(self) -> Delete:
        return delete(UserGroupModel).where(UserGroupModel.group_id == self.id)

    @property
    def _delete_permissions_statement(self) -> Delete:
        return delete(GroupPermissionModel).where(GroupPermissionModel.group_id == self.id)

    async def process(self, *args, **kwargs) -> None:
        result: Result[tuple[GroupModel]] = await self.session.execute(self._get_group_statement)
        try:
            group: GroupModel = result.scalars().one()
        except NoResultFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.") from None

        # One statement each, nothing is loaded. The foreign keys keep a group with rows.
        await self.session.execute(self._delete_users_statement)
        await self.session.execute(self._delete_permissions_statement)
        await self.session.delete(group)
        await self.session.commit()
