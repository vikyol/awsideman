"""
Unit tests for cross-account functionality in the restore manager.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.awsideman.aws_clients import AWSClientManager
from src.awsideman.backup_restore.interfaces import StorageEngineInterface
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    ConflictStrategy,
    CrossAccountConfig,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    ResourceMapping,
    ResourceType,
    RestoreOptions,
    RestoreResult,
    RetentionPolicy,
    UserData,
    ValidationResult,
)
from src.awsideman.backup_restore.restore_manager import CrossAccountRestoreManager


class TestCrossAccountRestoreManager:
    """Test cases for CrossAccountRestoreManager."""

    @pytest.fixture
    def client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)
        manager.region = "us-east-1"
        return manager

    @pytest.fixture
    def storage_engine(self):
        """Create a mock storage engine."""
        return Mock(spec=StorageEngineInterface)

    @pytest.fixture
    def restore_manager(self, client_manager, storage_engine):
        """Create a CrossAccountRestoreManager instance."""
        return CrossAccountRestoreManager(client_manager, storage_engine)

    @pytest.fixture
    def sample_backup_data(self):
        """Create sample backup data for testing."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ins-123",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="111111111111",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        users = [
            UserData(
                user_id="user-123",
                user_name="testuser1",
                display_name="Test User 1",
                email="testuser1@example.com",
            )
        ]

        groups = [
            GroupData(
                group_id="group-123",
                display_name="Test Group 1",
                description="Test group",
                members=["user-123"],
            )
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPermissionSet",
                description="Test permission set",
            )
        ]

        assignments = [
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
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

    @pytest.fixture
    def cross_account_config(self):
        """Create a test cross-account configuration."""
        return CrossAccountConfig(
            target_account_id="222222222222",
            role_arn="arn:aws:iam::222222222222:role/RestoreRole",
            external_id="test-external-id",
        )

    @pytest.fixture
    def resource_mappings(self):
        """Create test resource mappings."""
        return [
            ResourceMapping(
                source_account_id="111111111111",
                target_account_id="222222222222",
                source_region="us-east-1",
                target_region="us-west-2",
                permission_set_name_mappings={"TestPermissionSet": "MappedPermissionSet"},
            )
        ]

    @pytest.mark.asyncio
    async def test_restore_backup_success_local_account(self, restore_manager, sample_backup_data):
        """Test successful backup restore to local account."""
        backup_id = "test-backup-123"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock restore processor
        mock_restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 1, "groups": 1, "permission_sets": 1, "assignments": 1},
        )

        with patch(
            "src.awsideman.backup_restore.restore_manager.RestoreProcessor"
        ) as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_restore = AsyncMock(return_value=mock_restore_result)
            mock_processor_class.return_value = mock_processor

            # Create restore options (no cross-account config)
            options = RestoreOptions(
                target_resources=[ResourceType.ALL],
                conflict_strategy=ConflictStrategy.OVERWRITE,
                dry_run=False,
            )

            # Test restore
            result = await restore_manager.restore_backup(backup_id, options)

            assert result.success
            assert result.message == "Restore completed successfully"
            assert result.changes_applied["users"] == 1

    @pytest.mark.asyncio
    async def test_restore_backup_cross_account(
        self, restore_manager, sample_backup_data, cross_account_config
    ):
        """Test successful cross-account backup restore."""
        backup_id = "test-backup-123"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock cross-account validation
        mock_validation_result = ValidationResult(is_valid=True, errors=[], warnings=[])
        restore_manager.permission_validator.validate_restore_permissions = AsyncMock(
            return_value=mock_validation_result
        )

        # Mock cross-account client manager
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)
        restore_manager.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_cross_account_client_manager
        )

        # Mock restore processor
        mock_restore_result = RestoreResult(
            success=True,
            message="Cross-account restore completed successfully",
            changes_applied={"users": 1, "groups": 1, "permission_sets": 1, "assignments": 1},
        )

        with patch(
            "src.awsideman.backup_restore.restore_manager.RestoreProcessor"
        ) as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_restore = AsyncMock(return_value=mock_restore_result)
            mock_processor_class.return_value = mock_processor

            # Create restore options with cross-account config
            options = RestoreOptions(
                target_resources=[ResourceType.ALL],
                conflict_strategy=ConflictStrategy.OVERWRITE,
                cross_account_config=cross_account_config,
                target_instance_arn="arn:aws:sso:::instance/ins-456",
            )

            # Test restore
            result = await restore_manager.restore_backup(backup_id, options)

            assert result.success
            assert "Cross-account restore completed successfully" in result.message

    @pytest.mark.asyncio
    async def test_restore_backup_with_resource_mappings(
        self, restore_manager, sample_backup_data, cross_account_config, resource_mappings
    ):
        """Test backup restore with resource mappings."""
        backup_id = "test-backup-123"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock cross-account validation
        mock_validation_result = ValidationResult(is_valid=True, errors=[], warnings=[])
        restore_manager.permission_validator.validate_restore_permissions = AsyncMock(
            return_value=mock_validation_result
        )

        # Mock cross-account client manager
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)
        restore_manager.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_cross_account_client_manager
        )

        # Mock restore processor
        mock_restore_result = RestoreResult(
            success=True,
            message="Restore with mappings completed successfully",
            changes_applied={"users": 1, "groups": 1, "permission_sets": 1, "assignments": 1},
        )

        with patch(
            "src.awsideman.backup_restore.restore_manager.RestoreProcessor"
        ) as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_restore = AsyncMock(return_value=mock_restore_result)
            mock_processor_class.return_value = mock_processor

            # Create restore options with resource mappings
            options = RestoreOptions(
                target_resources=[ResourceType.ALL],
                conflict_strategy=ConflictStrategy.OVERWRITE,
                cross_account_config=cross_account_config,
                resource_mapping_configs=resource_mappings,
                target_instance_arn="arn:aws:sso:::instance/ins-456",
            )

            # Test restore
            result = await restore_manager.restore_backup(backup_id, options)

            assert result.success

    @pytest.mark.asyncio
    async def test_restore_backup_validation_failure(
        self, restore_manager, sample_backup_data, cross_account_config
    ):
        """Test backup restore with validation failure."""
        backup_id = "test-backup-123"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock cross-account validation failure
        mock_validation_result = ValidationResult(
            is_valid=False, errors=["Access denied to target instance"], warnings=[]
        )
        restore_manager.permission_validator.validate_restore_permissions = AsyncMock(
            return_value=mock_validation_result
        )

        # Create restore options with cross-account config
        options = RestoreOptions(
            target_resources=[ResourceType.ALL],
            cross_account_config=cross_account_config,
            target_instance_arn="arn:aws:sso:::instance/ins-456",
        )

        # Test restore
        result = await restore_manager.restore_backup(backup_id, options)

        assert not result.success
        # Just verify it failed with some error message
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self, restore_manager):
        """Test backup restore with backup not found."""
        backup_id = "nonexistent-backup"

        # Mock storage engine to return None (backup not found)
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=None)

        options = RestoreOptions()

        # Test restore
        result = await restore_manager.restore_backup(backup_id, options)

        assert not result.success
        assert f"Backup {backup_id} not found" in result.message
        assert f"Backup {backup_id} not found" in result.errors

    @pytest.mark.asyncio
    async def test_preview_restore_success(
        self, restore_manager, sample_backup_data, resource_mappings
    ):
        """Test successful restore preview."""
        backup_id = "test-backup-123"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Create restore options with resource mappings
        options = RestoreOptions(
            target_resources=[ResourceType.ALL],
            resource_mapping_configs=resource_mappings,
            cross_account_config=CrossAccountConfig(
                target_account_id="222222222222",
                role_arn="arn:aws:iam::222222222222:role/RestoreRole",
            ),
        )

        # Test preview
        preview = await restore_manager.preview_restore(backup_id, options)

        assert preview.changes_summary["users"] == 1
        assert preview.changes_summary["groups"] == 1
        assert preview.changes_summary["permission_sets"] == 1
        assert preview.changes_summary["assignments"] == 1

        # Should have warnings about cross-account and resource mapping
        assert len(preview.warnings) >= 2
        assert any("Cross-account restore" in warning for warning in preview.warnings)
        assert any("Resource mapping" in warning for warning in preview.warnings)

    @pytest.mark.asyncio
    async def test_preview_restore_backup_not_found(self, restore_manager):
        """Test restore preview with backup not found."""
        backup_id = "nonexistent-backup"

        # Mock storage engine to return None
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=None)

        options = RestoreOptions()

        # Test preview
        preview = await restore_manager.preview_restore(backup_id, options)

        assert preview.changes_summary == {}
        assert len(preview.warnings) > 0
        assert f"Backup {backup_id} not found" in preview.warnings[0]

    @pytest.mark.asyncio
    async def test_validate_compatibility_success(self, restore_manager, sample_backup_data):
        """Test successful compatibility validation."""
        backup_id = "test-backup-123"
        target_instance_arn = "arn:aws:sso:us-west-2:222222222222:instance/ins-456"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock backup data integrity check
        sample_backup_data.verify_integrity = Mock(return_value=True)

        # Test compatibility validation
        result = await restore_manager.validate_compatibility(backup_id, target_instance_arn)

        assert result.is_valid
        assert result.details["target_account"] == "222222222222"
        assert result.details["target_region"] == "us-west-2"
        assert result.details["source_account"] == "111111111111"
        assert result.details["source_region"] == "us-east-1"
        assert result.details["cross_account"] is True
        assert result.details["cross_region"] is True

        # Should have warnings about cross-account and cross-region
        assert len(result.warnings) >= 2

    @pytest.mark.asyncio
    async def test_validate_compatibility_integrity_failure(
        self, restore_manager, sample_backup_data
    ):
        """Test compatibility validation with integrity failure."""
        backup_id = "test-backup-123"
        target_instance_arn = "arn:aws:sso:::instance/ins-456"

        # Mock storage engine to return backup data
        restore_manager.storage_engine.retrieve_backup = AsyncMock(return_value=sample_backup_data)

        # Mock backup data integrity check failure
        sample_backup_data.verify_integrity = Mock(return_value=False)

        # Test compatibility validation
        result = await restore_manager.validate_compatibility(backup_id, target_instance_arn)

        assert not result.is_valid
        assert "Backup data integrity check failed" in result.errors

    @pytest.mark.asyncio
    async def test_apply_resource_mappings(
        self, restore_manager, sample_backup_data, resource_mappings
    ):
        """Test applying resource mappings to backup data."""
        # Test resource mapping application
        mapped_data = await restore_manager._apply_resource_mappings(
            sample_backup_data, resource_mappings
        )

        # Verify mappings were applied
        assert mapped_data.metadata.source_account == "222222222222"  # Mapped account
        assert mapped_data.metadata.source_region == "us-west-2"  # Mapped region

        # Verify permission set name mapping
        assert mapped_data.permission_sets[0].name == "MappedPermissionSet"

        # Verify assignment account mapping
        assert mapped_data.assignments[0].account_id == "222222222222"

    @pytest.mark.asyncio
    async def test_get_target_client_manager_local(self, restore_manager):
        """Test getting target client manager for local account."""
        options = RestoreOptions()  # No cross-account config

        client_manager = await restore_manager._get_target_client_manager(options)

        # Should return the local client manager
        assert client_manager == restore_manager.client_manager

    @pytest.mark.asyncio
    async def test_get_target_client_manager_cross_account(
        self, restore_manager, cross_account_config
    ):
        """Test getting target client manager for cross-account."""
        # Mock cross-account client manager
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)
        restore_manager.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_cross_account_client_manager
        )

        options = RestoreOptions(cross_account_config=cross_account_config)

        client_manager = await restore_manager._get_target_client_manager(options)

        # Should return the cross-account client manager
        assert client_manager == mock_cross_account_client_manager

        # Verify the cross-account manager was called with correct config
        restore_manager.cross_account_manager.get_cross_account_client_manager.assert_called_once_with(
            cross_account_config
        )


class TestCrossAccountRestoreIntegration:
    """Integration tests for cross-account restore functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_cross_account_restore(self):
        """Test complete end-to-end cross-account restore workflow."""
        # Create mock components
        client_manager = Mock(spec=AWSClientManager)
        storage_engine = Mock(spec=StorageEngineInterface)

        restore_manager = CrossAccountRestoreManager(client_manager, storage_engine)

        # Create test backup data
        metadata = BackupMetadata(
            backup_id="integration-test-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ins-source",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="111111111111",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[UserData(user_id="user-1", user_name="testuser")],
            groups=[GroupData(group_id="group-1", display_name="testgroup")],
            permission_sets=[
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:us-east-1:111111111111:permissionSet/ins-source/ps-1",
                    name="TestPS",
                )
            ],
            assignments=[
                AssignmentData(
                    account_id="111111111111",
                    permission_set_arn="arn:aws:sso:us-east-1:111111111111:permissionSet/ins-source/ps-1",
                    principal_type="USER",
                    principal_id="user-1",
                )
            ],
            relationships=RelationshipMap(),
        )

        # Mock storage engine
        storage_engine.retrieve_backup = AsyncMock(return_value=backup_data)

        # Mock cross-account validation
        restore_manager.permission_validator.validate_restore_permissions = AsyncMock(
            return_value=ValidationResult(is_valid=True, errors=[], warnings=[])
        )

        # Mock cross-account client manager
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)
        restore_manager.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_cross_account_client_manager
        )

        # Mock restore processor
        mock_restore_result = RestoreResult(
            success=True,
            message="Integration test restore completed",
            changes_applied={"users": 1, "groups": 1, "permission_sets": 1, "assignments": 1},
        )

        with patch(
            "src.awsideman.backup_restore.restore_manager.RestoreProcessor"
        ) as mock_processor_class:
            mock_processor = Mock()
            mock_processor.process_restore = AsyncMock(return_value=mock_restore_result)
            mock_processor_class.return_value = mock_processor

            # Create comprehensive restore options
            cross_account_config = CrossAccountConfig(
                target_account_id="222222222222",
                role_arn="arn:aws:iam::222222222222:role/RestoreRole",
            )

            resource_mappings = [
                ResourceMapping(
                    source_account_id="111111111111",
                    target_account_id="222222222222",
                    source_region="us-east-1",
                    target_region="us-west-2",
                )
            ]

            options = RestoreOptions(
                target_resources=[ResourceType.ALL],
                conflict_strategy=ConflictStrategy.OVERWRITE,
                cross_account_config=cross_account_config,
                resource_mapping_configs=resource_mappings,
                target_instance_arn="arn:aws:sso:::instance/ins-target",
            )

            # Test the complete workflow

            # 1. Validate compatibility
            compatibility_result = await restore_manager.validate_compatibility(
                "integration-test-backup", "arn:aws:sso:us-west-2:222222222222:instance/ins-target"
            )
            assert compatibility_result.is_valid

            # 2. Preview restore
            preview = await restore_manager.preview_restore("integration-test-backup", options)
            assert preview.changes_summary["users"] == 1
            assert len(preview.warnings) > 0  # Should have cross-account warnings

            # 3. Perform restore
            result = await restore_manager.restore_backup("integration-test-backup", options)
            assert result.success
            assert result.changes_applied["users"] == 1

            # Verify cross-account client manager was used
            restore_manager.cross_account_manager.get_cross_account_client_manager.assert_called_with(
                cross_account_config
            )


if __name__ == "__main__":
    pytest.main([__file__])
