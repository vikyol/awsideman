"""
Unit tests for backup manager implementation.

This module tests the BackupManager class functionality including backup creation,
validation, error handling, and progress tracking.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.awsideman.backup_restore.manager import BackupManager
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupType,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    ResourceType,
    RetentionPolicy,
    UserData,
    ValidationResult,
)
from src.awsideman.backup_restore.validation import BackupValidator


# Fixtures available to all test classes
@pytest.fixture
def mock_collector():
    """Create mock collector."""
    collector = AsyncMock()
    collector.validate_connection.return_value = ValidationResult(
        is_valid=True, errors=[], warnings=[], details={}
    )
    return collector


@pytest.fixture
def mock_storage_engine():
    """Create mock storage engine."""
    storage = AsyncMock()
    storage.store_backup.return_value = "backup-123"
    storage.verify_integrity.return_value = ValidationResult(
        is_valid=True, errors=[], warnings=[], details={}
    )
    return storage


@pytest.fixture
def mock_validator():
    """Create mock validator."""
    validator = Mock(spec=BackupValidator)
    validator.validate_backup_data = AsyncMock(
        return_value=ValidationResult(is_valid=True, errors=[], warnings=[], details={})
    )
    return validator


@pytest.fixture
def mock_progress_reporter():
    """Create mock progress reporter."""
    reporter = AsyncMock()
    return reporter


@pytest.fixture
def backup_manager(mock_collector, mock_storage_engine, mock_validator, mock_progress_reporter):
    """Create BackupManager instance with mocked dependencies."""
    return BackupManager(
        collector=mock_collector,
        storage_engine=mock_storage_engine,
        validator=mock_validator,
        progress_reporter=mock_progress_reporter,
        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        source_account="123456789012",
        source_region="us-east-1",
    )


@pytest.fixture
def sample_backup_options():
    """Create sample backup options."""
    return BackupOptions(
        backup_type=BackupType.FULL,
        resource_types=[ResourceType.ALL],
        include_inactive_users=False,
        encryption_enabled=True,
        compression_enabled=True,
        parallel_collection=True,
    )


@pytest.fixture
def sample_backup_data():
    """Create sample backup data."""
    metadata = BackupMetadata(
        backup_id="test-backup-123",
        timestamp=datetime.now(),
        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        backup_type=BackupType.FULL,
        version="1.0.0",
        source_account="123456789012",
        source_region="us-east-1",
        retention_policy=RetentionPolicy(),
        encryption_info=EncryptionMetadata(),
    )

    users = [
        UserData(
            user_id="user-123",
            user_name="testuser",
            display_name="Test User",
            email="test@example.com",
        )
    ]

    groups = [GroupData(group_id="group-123", display_name="Test Group", members=["user-123"])]

    permission_sets = [
        PermissionSetData(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            name="TestPermissionSet",
        )
    ]

    assignments = [
        AssignmentData(
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_type="USER",
            principal_id="user-123",
        )
    ]

    return BackupData(
        metadata=metadata,
        users=users,
        groups=groups,
        permission_sets=permission_sets,
        assignments=assignments,
        relationships=RelationshipMap(),
    )


class TestBackupManager:
    """Test cases for BackupManager class."""

    pass


class TestCreateBackup:
    """Test cases for create_backup method."""

    @pytest.mark.asyncio
    async def test_create_full_backup_success(
        self, backup_manager, sample_backup_options, sample_backup_data
    ):
        """Test successful full backup creation."""
        # Setup mocks
        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups
        backup_manager.collector.collect_permission_sets.return_value = (
            sample_backup_data.permission_sets
        )
        backup_manager.collector.collect_assignments.return_value = sample_backup_data.assignments

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is True
        assert result.backup_id == "backup-123"
        assert result.metadata is not None
        assert len(result.errors) == 0

        # Verify collector was called
        backup_manager.collector.validate_connection.assert_called_once()
        backup_manager.collector.collect_users.assert_called_once()
        backup_manager.collector.collect_groups.assert_called_once()
        backup_manager.collector.collect_permission_sets.assert_called_once()
        backup_manager.collector.collect_assignments.assert_called_once()

        # Verify storage was called
        backup_manager.storage_engine.store_backup.assert_called_once()
        backup_manager.storage_engine.verify_integrity.assert_called_once_with("backup-123")

    @pytest.mark.asyncio
    async def test_create_incremental_backup_success(self, backup_manager, sample_backup_data):
        """Test successful incremental backup creation."""
        # Setup
        since_time = datetime.now() - timedelta(hours=1)
        options = BackupOptions(
            backup_type=BackupType.INCREMENTAL, resource_types=[ResourceType.ALL], since=since_time
        )

        backup_manager.collector.collect_incremental.return_value = sample_backup_data

        # Execute
        result = await backup_manager.create_backup(options)

        # Verify
        assert result.success is True
        assert result.backup_id == "backup-123"

        # Verify incremental collection was called
        backup_manager.collector.collect_incremental.assert_called_once_with(since_time, options)

    @pytest.mark.asyncio
    async def test_create_backup_connection_validation_failure(
        self, backup_manager, sample_backup_options
    ):
        """Test backup creation with connection validation failure."""
        # Setup
        backup_manager.collector.validate_connection.return_value = ValidationResult(
            is_valid=False, errors=["Connection failed"], warnings=[], details={}
        )

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is False
        assert "Connection validation failed" in result.message
        assert "Connection failed" in result.errors

        # Verify no further operations were performed
        backup_manager.collector.collect_users.assert_not_called()
        backup_manager.storage_engine.store_backup.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_backup_data_validation_failure(
        self, backup_manager, sample_backup_options, sample_backup_data
    ):
        """Test backup creation with data validation failure."""
        # Setup
        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups
        backup_manager.collector.collect_permission_sets.return_value = (
            sample_backup_data.permission_sets
        )
        backup_manager.collector.collect_assignments.return_value = sample_backup_data.assignments

        backup_manager.validator.validate_backup_data.return_value = ValidationResult(
            is_valid=False, errors=["Critical validation error"], warnings=[], details={}
        )

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is False
        assert "Critical validation errors found" in result.message
        assert "Critical validation error" in result.errors

        # Verify storage was not called
        backup_manager.storage_engine.store_backup.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_backup_storage_failure(
        self, backup_manager, sample_backup_options, sample_backup_data
    ):
        """Test backup creation with storage failure."""
        # Setup
        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups
        backup_manager.collector.collect_permission_sets.return_value = (
            sample_backup_data.permission_sets
        )
        backup_manager.collector.collect_assignments.return_value = sample_backup_data.assignments

        backup_manager.storage_engine.store_backup.return_value = None  # Simulate failure

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is False
        assert "Failed to store backup data" in result.message
        assert "Storage operation failed" in result.errors

    @pytest.mark.asyncio
    async def test_create_backup_integrity_verification_failure(
        self, backup_manager, sample_backup_options, sample_backup_data
    ):
        """Test backup creation with integrity verification failure."""
        # Setup
        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups
        backup_manager.collector.collect_permission_sets.return_value = (
            sample_backup_data.permission_sets
        )
        backup_manager.collector.collect_assignments.return_value = sample_backup_data.assignments

        backup_manager.storage_engine.verify_integrity.return_value = ValidationResult(
            is_valid=False, errors=["Integrity check failed"], warnings=[], details={}
        )

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is False
        assert "Backup integrity verification failed" in result.message
        assert "Integrity check failed" in result.errors

        # Verify cleanup was attempted
        backup_manager.storage_engine.delete_backup.assert_called_once_with("backup-123")

    @pytest.mark.asyncio
    async def test_create_backup_with_progress_reporting(
        self, backup_manager, sample_backup_options, sample_backup_data
    ):
        """Test backup creation with progress reporting."""
        # Setup
        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups
        backup_manager.collector.collect_permission_sets.return_value = (
            sample_backup_data.permission_sets
        )
        backup_manager.collector.collect_assignments.return_value = sample_backup_data.assignments

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is True

        # Verify progress reporting was used
        backup_manager.progress_reporter.start_operation.assert_called_once()
        assert backup_manager.progress_reporter.update_progress.call_count > 0
        backup_manager.progress_reporter.complete_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backup_selective_resources(self, backup_manager, sample_backup_data):
        """Test backup creation with selective resource types."""
        # Setup
        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.USERS, ResourceType.GROUPS],
            include_inactive_users=False,
        )

        backup_manager.collector.collect_users.return_value = sample_backup_data.users
        backup_manager.collector.collect_groups.return_value = sample_backup_data.groups

        # Execute
        result = await backup_manager.create_backup(options)

        # Verify
        assert result.success is True

        # Verify only selected resources were collected
        backup_manager.collector.collect_users.assert_called_once()
        backup_manager.collector.collect_groups.assert_called_once()
        backup_manager.collector.collect_permission_sets.assert_not_called()
        backup_manager.collector.collect_assignments.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_backup_exception_handling(self, backup_manager, sample_backup_options):
        """Test backup creation with unexpected exception."""
        # Setup
        backup_manager.collector.collect_users.side_effect = Exception("Unexpected error")

        # Execute
        result = await backup_manager.create_backup(sample_backup_options)

        # Verify
        assert result.success is False
        assert "Backup operation failed: Unexpected error" in result.message
        assert "Unexpected error" in result.errors
        assert result.duration is not None


class TestListBackups:
    """Test cases for list_backups method."""

    @pytest.mark.asyncio
    async def test_list_backups_success(self, backup_manager):
        """Test successful backup listing."""
        # Setup
        sample_metadata = [
            BackupMetadata(
                backup_id="backup-1",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )
        ]

        backup_manager.storage_engine.list_backups.return_value = sample_metadata

        # Execute
        result = await backup_manager.list_backups()

        # Verify
        assert len(result) == 1
        assert result[0].backup_id == "backup-1"
        backup_manager.storage_engine.list_backups.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_list_backups_with_filters(self, backup_manager):
        """Test backup listing with filters."""
        # Setup
        filters = {"backup_type": "full", "source_account": "123456789012"}
        backup_manager.storage_engine.list_backups.return_value = []

        # Execute
        result = await backup_manager.list_backups(filters)

        # Verify
        assert len(result) == 0
        backup_manager.storage_engine.list_backups.assert_called_once_with(filters)

    @pytest.mark.asyncio
    async def test_list_backups_exception_handling(self, backup_manager):
        """Test backup listing with exception."""
        # Setup
        backup_manager.storage_engine.list_backups.side_effect = Exception("Storage error")

        # Execute
        result = await backup_manager.list_backups()

        # Verify
        assert len(result) == 0  # Should return empty list on error


class TestValidateBackup:
    """Test cases for validate_backup method."""

    @pytest.mark.asyncio
    async def test_validate_backup_success(self, backup_manager, sample_backup_data):
        """Test successful backup validation."""
        # Setup
        backup_manager.storage_engine.verify_integrity.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], details={}
        )
        backup_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Execute
        result = await backup_manager.validate_backup("backup-123")

        # Verify
        assert result.is_valid is True
        assert len(result.errors) == 0

        backup_manager.storage_engine.verify_integrity.assert_called_once_with("backup-123")
        backup_manager.storage_engine.retrieve_backup.assert_called_once_with("backup-123")
        backup_manager.validator.validate_backup_data.assert_called_once_with(sample_backup_data)

    @pytest.mark.asyncio
    async def test_validate_backup_storage_integrity_failure(self, backup_manager):
        """Test backup validation with storage integrity failure."""
        # Setup
        backup_manager.storage_engine.verify_integrity.return_value = ValidationResult(
            is_valid=False, errors=["Storage integrity failed"], warnings=[], details={}
        )

        # Execute
        result = await backup_manager.validate_backup("backup-123")

        # Verify
        assert result.is_valid is False
        assert "Storage integrity failed" in result.errors

        # Should not proceed to data validation
        backup_manager.storage_engine.retrieve_backup.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_backup_not_found(self, backup_manager):
        """Test backup validation when backup is not found."""
        # Setup
        backup_manager.storage_engine.verify_integrity.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], details={}
        )
        backup_manager.storage_engine.retrieve_backup.return_value = None

        # Execute
        result = await backup_manager.validate_backup("backup-123")

        # Verify
        assert result.is_valid is False
        assert any("not found" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_backup_data_validation_failure(
        self, backup_manager, sample_backup_data
    ):
        """Test backup validation with data validation failure."""
        # Setup
        backup_manager.storage_engine.verify_integrity.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[], details={}
        )
        backup_manager.storage_engine.retrieve_backup.return_value = sample_backup_data
        backup_manager.validator.validate_backup_data.return_value = ValidationResult(
            is_valid=False, errors=["Data validation failed"], warnings=[], details={}
        )

        # Execute
        result = await backup_manager.validate_backup("backup-123")

        # Verify
        assert result.is_valid is False
        assert "Data validation failed" in result.errors

    @pytest.mark.asyncio
    async def test_validate_backup_exception_handling(self, backup_manager):
        """Test backup validation with exception."""
        # Setup
        backup_manager.storage_engine.verify_integrity.side_effect = Exception("Validation error")

        # Execute
        result = await backup_manager.validate_backup("backup-123")

        # Verify
        assert result.is_valid is False
        assert any("Validation failed" in error for error in result.errors)


class TestDeleteBackup:
    """Test cases for delete_backup method."""

    @pytest.mark.asyncio
    async def test_delete_backup_success(self, backup_manager):
        """Test successful backup deletion."""
        # Setup
        backup_manager.storage_engine.delete_backup.return_value = True

        # Execute
        result = await backup_manager.delete_backup("backup-123")

        # Verify
        assert result is True
        backup_manager.storage_engine.delete_backup.assert_called_once_with("backup-123")

    @pytest.mark.asyncio
    async def test_delete_backup_failure(self, backup_manager):
        """Test backup deletion failure."""
        # Setup
        backup_manager.storage_engine.delete_backup.return_value = False

        # Execute
        result = await backup_manager.delete_backup("backup-123")

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_backup_exception_handling(self, backup_manager):
        """Test backup deletion with exception."""
        # Setup
        backup_manager.storage_engine.delete_backup.side_effect = Exception("Delete error")

        # Execute
        result = await backup_manager.delete_backup("backup-123")

        # Verify
        assert result is False


class TestGetBackupMetadata:
    """Test cases for get_backup_metadata method."""

    @pytest.mark.asyncio
    async def test_get_backup_metadata_success(self, backup_manager, sample_backup_data):
        """Test successful metadata retrieval."""
        # Setup
        backup_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Execute
        result = await backup_manager.get_backup_metadata("backup-123")

        # Verify
        assert result is not None
        assert result.backup_id == sample_backup_data.metadata.backup_id
        backup_manager.storage_engine.retrieve_backup.assert_called_once_with("backup-123")

    @pytest.mark.asyncio
    async def test_get_backup_metadata_not_found(self, backup_manager):
        """Test metadata retrieval when backup not found."""
        # Setup
        backup_manager.storage_engine.retrieve_backup.return_value = None

        # Execute
        result = await backup_manager.get_backup_metadata("backup-123")

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_get_backup_metadata_exception_handling(self, backup_manager):
        """Test metadata retrieval with exception."""
        # Setup
        backup_manager.storage_engine.retrieve_backup.side_effect = Exception("Retrieval error")

        # Execute
        result = await backup_manager.get_backup_metadata("backup-123")

        # Verify
        assert result is None


class TestOperationManagement:
    """Test cases for operation management methods."""

    @pytest.mark.asyncio
    async def test_get_operation_status(self, backup_manager):
        """Test getting operation status."""
        # Setup - simulate active operation
        operation_id = "op-123"
        backup_manager._active_operations[operation_id] = {
            "type": "backup",
            "start_time": datetime.now(),
            "status": "running",
        }

        # Execute
        result = await backup_manager.get_operation_status(operation_id)

        # Verify
        assert result is not None
        assert result["type"] == "backup"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_operation_status_not_found(self, backup_manager):
        """Test getting status for non-existent operation."""
        # Execute
        result = await backup_manager.get_operation_status("non-existent")

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_operation_success(self, backup_manager):
        """Test successful operation cancellation."""
        # Setup
        operation_id = "op-123"
        backup_manager._active_operations[operation_id] = {
            "type": "backup",
            "start_time": datetime.now(),
            "status": "running",
        }

        # Execute
        result = await backup_manager.cancel_operation(operation_id)

        # Verify
        assert result is True
        assert operation_id not in backup_manager._active_operations
        backup_manager.progress_reporter.complete_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_operation_not_found(self, backup_manager):
        """Test cancelling non-existent operation."""
        # Execute
        result = await backup_manager.cancel_operation("non-existent")

        # Verify
        assert result is False


class TestPrivateMethods:
    """Test cases for private helper methods."""

    def test_calculate_backup_steps(self, backup_manager):
        """Test backup steps calculation."""
        # Test with ALL resources
        options = BackupOptions(resource_types=[ResourceType.ALL])
        steps = backup_manager._calculate_backup_steps(options)
        assert steps == 10  # 6 base steps + 4 resource types

        # Test with specific resources
        options = BackupOptions(resource_types=[ResourceType.USERS, ResourceType.GROUPS])
        steps = backup_manager._calculate_backup_steps(options)
        assert steps == 8  # 6 base steps + 2 resource types

    def test_create_backup_metadata(self, backup_manager, sample_backup_data):
        """Test backup metadata creation."""
        options = BackupOptions(backup_type=BackupType.FULL, encryption_enabled=True)

        metadata = backup_manager._create_backup_metadata(
            "test-backup", options, sample_backup_data
        )

        assert metadata.backup_id == "test-backup"
        assert metadata.backup_type == BackupType.FULL
        assert metadata.instance_arn == backup_manager.instance_arn
        assert metadata.source_account == backup_manager.source_account
        assert metadata.source_region == backup_manager.source_region
        assert metadata.encryption_info.encrypted is True
        assert metadata.resource_counts["users"] == len(sample_backup_data.users)

    def test_build_relationships(self, backup_manager, sample_backup_data):
        """Test relationship building."""
        relationships = backup_manager._build_relationships(
            sample_backup_data.users,
            sample_backup_data.groups,
            sample_backup_data.permission_sets,
            sample_backup_data.assignments,
        )

        # Verify user-group relationships
        assert "user-123" in relationships.user_groups
        assert "group-123" in relationships.user_groups["user-123"]

        # Verify group-member relationships
        assert "group-123" in relationships.group_members
        assert "user-123" in relationships.group_members["group-123"]

        # Verify permission set assignments
        ps_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        assert ps_arn in relationships.permission_set_assignments
        assert len(relationships.permission_set_assignments[ps_arn]) == 1


if __name__ == "__main__":
    pytest.main([__file__])
