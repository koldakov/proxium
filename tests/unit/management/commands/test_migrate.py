from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from redis.exceptions import LockNotOwnedError

from proxium.management.commands import MigrateCommand

if TYPE_CHECKING:
    from argparse import Namespace
    from unittest.mock import MagicMock

UPGRADE_TARGET = "proxium.management.commands._migrate.command.upgrade"


class TestMigrateCommandLock:
    def test_handle_migrates_holding_lock(
        self,
        migration_args: Namespace,
        mocked_redis_manager: MagicMock,
        redis_lock: MagicMock,
    ) -> None:
        # Arrange
        command = MigrateCommand(stdout=StringIO(), stderr=StringIO())

        # Act
        with patch(UPGRADE_TARGET) as upgrade:
            command.handle(migration_args)

        # Assert
        upgrade.assert_called_once()
        redis_lock.acquire.assert_awaited_once()
        redis_lock.release.assert_awaited_once()
        mocked_redis_manager.close.assert_awaited_once()

    def test_handle_waits_when_lock_taken(
        self,
        migration_args: Namespace,
        mocked_redis_manager: MagicMock,
        redis_lock: MagicMock,
    ) -> None:
        # Arrange
        # Taken by another instance, then free.
        acquired = [False, True]
        redis_lock.acquire.side_effect = acquired
        stderr = StringIO()
        command = MigrateCommand(stdout=StringIO(), stderr=stderr)

        # Act
        with patch(UPGRADE_TARGET) as upgrade:
            command.handle(migration_args)

        # Assert
        assert redis_lock.acquire.await_count == len(acquired)
        assert "Another instance is migrating" in stderr.getvalue()
        upgrade.assert_called_once()

    def test_handle_releases_lock_when_migration_fails(
        self,
        migration_args: Namespace,
        mocked_redis_manager: MagicMock,
        redis_lock: MagicMock,
    ) -> None:
        # Arrange
        command = MigrateCommand(stdout=StringIO(), stderr=StringIO())

        # Act
        with patch(UPGRADE_TARGET, side_effect=RuntimeError()), pytest.raises(RuntimeError):
            command.handle(migration_args)

        # Assert
        redis_lock.release.assert_awaited_once()

    def test_run_fails_when_lock_expired(
        self,
        migration_args: Namespace,
        mocked_redis_manager: MagicMock,
        redis_lock: MagicMock,
    ) -> None:
        # Arrange
        redis_lock.release.side_effect = LockNotOwnedError()
        stderr = StringIO()
        command = MigrateCommand(stdout=StringIO(), stderr=stderr)

        # Act
        with patch(UPGRADE_TARGET):
            exit_code = command.run(migration_args)

        # Assert
        assert exit_code == 1
        assert "outlived its lock" in stderr.getvalue()
