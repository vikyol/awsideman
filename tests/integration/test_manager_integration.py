"""
Integration tests for backup manager with real components.

This module tests the BackupManager with actual implementations of
storage, validation, and other components to ensure proper integration.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.awsideman.backup_restore.backends import FileSystemStorageBackend
from src.awsideman.backup_restore.manager import BackupManager
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupOptions,
    BackupType,
    GroupData,
    PermissionSetData,
    ResourceType,
    UserData,
    ValidationResult,
)
from src.awsideman.backup_restore.storage import StorageEngine
from src.awsideman.backup_restore.validation import BackupValidator


class TestBackupManagerIntegration:
    """Integration tests for BackupManager with real components."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_collector(self):
        """Create mock collector with realistic data."""
        collector = AsyncMock()

        # Mock validation
        from src.awsideman.backup_restore.models import ValidationResult

        collector.validate_connection.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], details={}
        )

        # Mock data collection
        users = [
            UserData(
                user_id="12345678-1234-1234-1234-123456789012",
                user_name="testuser1",
                display_name="Test User 1",
                email="test1@example.com",
            ),
            UserData(
                user_id="12345678-1234-1234-1234-123456789013",
                user_name="testuser2",
                display_name="Test User 2",
                email="test2@example.com",
            ),
        ]

        groups = [
            GroupData(
                group_id="87654321-4321-4321-4321-210987654321",
                display_name="Test Group",
                members=["12345678-1234-1234-1234-123456789012"],
            )
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                name="TestPermissionSet",
                description="Test permission set",
            )
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                principal_type="USER",
                principal_id="12345678-1234-1234-1234-123456789012",
            )
        ]

        collector.collect_users.return_value = users
        collector.collect_groups.return_value = groups
        collector.collect_permission_sets.return_value = permission_sets
        collector.collect_assignments.return_value = assignments

        return collector

    @pytest.fixture
    def real_storage_engine(self, temp_storage_dir):
        """Create real storage engine with filesystem backend."""
        backend = FileSystemStorageBackend(str(temp_storage_dir))
        return StorageEngine(backend, encryption_provider=None, enable_compression=False)

    @pytest.fixture
    def real_validator(self):
        """Create real backup validator."""
        return BackupValidator()

    @pytest.fixture
    def backup_manager_integration(self, mock_collector, real_storage_engine, real_validator):
        """Create BackupManager with real storage and validation."""
        return BackupManager(
            collector=mock_collector,
            storage_engine=real_storage_engine,
            validator=real_validator,
            progress_reporter=None,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            source_account="123456789012",
            source_region="us-east-1",
        )

    @pytest.mark.asyncio
    async def test_full_backup_workflow_integration(self, backup_manager_integration):
        """Test complete backup workflow with real components."""
        # Create backup options
        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            include_inactive_users=False,
            encryption_enabled=False,  # Disabled for simplicity
            compression_enabled=False,  # Disabled for simplicity
            parallel_collection=True,
        )

        # Execute backup
        result = await backup_manager_integration.create_backup(options)

        # Verify backup was successful
        assert result.success is True
        assert result.backup_id is not None
        assert result.metadata is not None
        assert len(result.errors) == 0

        # Verify backup can be listed
        backups = await backup_manager_integration.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == result.backup_id

        # Verify backup can be validated
        validation_result = await backup_manager_integration.validate_backup(result.backup_id)
        assert validation_result.is_valid is True
        assert len(validation_result.errors) == 0

        # Verify backup metadata can be retrieved
        metadata = await backup_manager_integration.get_backup_metadata(result.backup_id)
        assert metadata is not None
        assert metadata.backup_id == result.backup_id
        assert metadata.backup_type == BackupType.FULL

        # Verify backup can be deleted
        delete_result = await backup_manager_integration.delete_backup(result.backup_id)
        assert delete_result is True

        # Verify backup is no longer listed
        backups_after_delete = await backup_manager_integration.list_backups()
        assert len(backups_after_delete) == 0

    @pytest.mark.asyncio
    async def test_backup_with_filtering(self, backup_manager_integration):
        """Test backup with selective resource types."""
        # Create backup options for users only
        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.USERS],
            include_inactive_users=False,
            encryption_enabled=False,
            compression_enabled=False,
            parallel_collection=False,
        )

        # Execute backup
        result = await backup_manager_integration.create_backup(options)

        # Verify backup was successful
        assert result.success is True
        assert result.backup_id is not None

        # Verify only users collection was called
        backup_manager_integration.collector.collect_users.assert_called_once()
        backup_manager_integration.collector.collect_groups.assert_not_called()
        backup_manager_integration.collector.collect_permission_sets.assert_not_called()
        backup_manager_integration.collector.collect_assignments.assert_not_called()

        # Clean up
        await backup_manager_integration.delete_backup(result.backup_id)

    @pytest.mark.asyncio
    async def test_backup_validation_with_real_validator(self, backup_manager_integration):
        """Test backup validation with real validator."""
        # Create backup
        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            encryption_enabled=False,
            compression_enabled=False,
        )

        result = await backup_manager_integration.create_backup(options)
        assert result.success is True

        # Validate backup with real validator
        validation_result = await backup_manager_integration.validate_backup(result.backup_id)

        # Should pass validation
        assert validation_result.is_valid is True
        assert len(validation_result.errors) == 0

        # Should have validation details
        assert "validated_items" in validation_result.details

        # Clean up
        await backup_manager_integration.delete_backup(result.backup_id)

    @pytest.mark.asyncio
    async def test_multiple_backups_management(self, backup_manager_integration):
        """Test managing multiple backups."""
        backup_ids = []

        try:
            # Create multiple backups
            for i in range(3):
                options = BackupOptions(
                    backup_type=BackupType.FULL,
                    resource_types=[ResourceType.USERS, ResourceType.GROUPS],
                    encryption_enabled=False,
                    compression_enabled=False,
                    skip_duplicate_check=True,  # Disable duplicate detection for testing
                )

                result = await backup_manager_integration.create_backup(options)
                assert result.success is True
                backup_ids.append(result.backup_id)

                # Small delay to ensure different timestamps
                await asyncio.sleep(0.01)

            # Verify all backups are listed
            backups = await backup_manager_integration.list_backups()
            assert len(backups) == 3

            # Verify backups are sorted by timestamp (newest first)
            timestamps = [backup.timestamp for backup in backups]
            assert timestamps == sorted(timestamps, reverse=True)

            # Test filtering by backup type
            filtered_backups = await backup_manager_integration.list_backups(
                {"backup_type": "full"}
            )
            assert len(filtered_backups) == 3

            # Validate each backup
            for backup_id in backup_ids:
                validation_result = await backup_manager_integration.validate_backup(backup_id)
                assert validation_result.is_valid is True

        finally:
            # Clean up all backups
            for backup_id in backup_ids:
                await backup_manager_integration.delete_backup(backup_id)

    @pytest.mark.asyncio
    async def test_backup_error_recovery(self, backup_manager_integration):
        """Test backup error recovery scenarios."""
        # Test with collector that fails
        from unittest.mock import AsyncMock

        failing_collector = AsyncMock()
        failing_collector.validate_connection.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], details={}
        )
        failing_collector.collect_users.side_effect = Exception("Collection failed")

        failing_manager = BackupManager(
            collector=failing_collector,
            storage_engine=backup_manager_integration.storage_engine,
            validator=backup_manager_integration.validator,
            progress_reporter=None,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            source_account="123456789012",
            source_region="us-east-1",
        )

        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.USERS],
            encryption_enabled=False,
            compression_enabled=False,
        )

        # This should fail gracefully
        result = await failing_manager.create_backup(options)

        # Verify failure is handled properly
        assert result.success is False
        assert len(result.errors) > 0
        assert result.backup_id is None
        assert "Collection failed" in str(result.errors)


if __name__ == "__main__":
    pytest.main([__file__])
