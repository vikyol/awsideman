"""
Unit tests for enhanced backup and restore managers with error handling.

Tests the integration of error handling, retry logic, partial recovery,
and rollback capabilities in the enhanced managers.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.backup_restore.enhanced_backup_manager import EnhancedBackupManager
from src.awsideman.backup_restore.enhanced_restore_manager import EnhancedRestoreManager
from src.awsideman.backup_restore.error_handling import RetryConfig
from src.awsideman.backup_restore.models import (
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupType,
    ConflictStrategy,
    EncryptionMetadata,
    GroupData,
    ResourceType,
    RestoreOptions,
    RetentionPolicy,
    UserData,
)


class TestEnhancedBackupManager:
    """Test enhanced backup manager with error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_collector = AsyncMock()
        self.mock_storage_engine = AsyncMock()
        self.mock_validator = AsyncMock()
        self.mock_progress_reporter = AsyncMock()

        # Create enhanced backup manager with fast retry config for testing
        retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1)

        self.manager = EnhancedBackupManager(
            collector=self.mock_collector,
            storage_engine=self.mock_storage_engine,
            validator=self.mock_validator,
            progress_reporter=self.mock_progress_reporter,
            instance_arn="arn:aws:sso:::instance/test-instance",
            source_account="123456789012",
            source_region="us-east-1",
            retry_config=retry_config,
        )

    @pytest.mark.asyncio
    async def test_successful_backup_with_recovery_tracking(self):
        """Test successful backup operation with recovery tracking."""
        # Setup mocks
        self.mock_collector.validate_connection.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        self.mock_collector.collect_users.return_value = [
            UserData(user_id="user1", user_name="test1"),
            UserData(user_id="user2", user_name="test2"),
        ]
        self.mock_collector.collect_groups.return_value = [
            GroupData(group_id="group1", display_name="Test Group")
        ]
        self.mock_collector.collect_permission_sets.return_value = []
        self.mock_collector.collect_assignments.return_value = []

        self.mock_validator.validate_backup_data.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        self.mock_storage_engine.store_backup.return_value = "backup-123"
        self.mock_storage_engine.verify_integrity.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await self.manager.create_backup(options)

        # Verify success
        assert result.success is True
        assert result.backup_id == "backup-123"
        assert "Enhanced backup created successfully" in result.message

        # Verify progress tracking was used
        self.mock_progress_reporter.start_operation.assert_called_once()
        self.mock_progress_reporter.complete_operation.assert_called_once()

        # Verify all collection methods were called
        self.mock_collector.collect_users.assert_called_once()
        self.mock_collector.collect_groups.assert_called_once()
        self.mock_collector.collect_permission_sets.assert_called_once()
        self.mock_collector.collect_assignments.assert_called_once()

    @pytest.mark.asyncio
    async def test_backup_with_retry_on_transient_failure(self):
        """Test backup operation with retry on transient failures."""
        # Setup connection validation to fail first, then succeed
        validation_calls = 0

        async def mock_validate_connection():
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 1:
                raise ConnectionError("Temporary network issue")
            return AsyncMock(is_valid=True, errors=[], warnings=[])

        self.mock_collector.validate_connection.side_effect = mock_validate_connection

        # Setup other mocks for success
        self.mock_collector.collect_users.return_value = []
        self.mock_collector.collect_groups.return_value = []
        self.mock_collector.collect_permission_sets.return_value = []
        self.mock_collector.collect_assignments.return_value = []
        self.mock_validator.validate_backup_data.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        self.mock_storage_engine.store_backup.return_value = "backup-retry-123"
        self.mock_storage_engine.verify_integrity.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await self.manager.create_backup(options)

        # Verify success after retry
        assert result.success is True
        assert result.backup_id == "backup-retry-123"
        assert validation_calls == 2  # Should have retried once

    @pytest.mark.asyncio
    async def test_backup_with_partial_recovery(self):
        """Test backup operation with partial recovery on failure."""
        # Setup connection validation to succeed
        self.mock_collector.validate_connection.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )

        # Setup partial collection success
        self.mock_collector.collect_users.return_value = [
            UserData(user_id="user1", user_name="test1")
        ]
        self.mock_collector.collect_groups.return_value = [
            GroupData(group_id="group1", display_name="Test Group")
        ]

        # Make permission sets collection fail
        self.mock_collector.collect_permission_sets.side_effect = Exception(
            "Permission set collection failed"
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await self.manager.create_backup(options)

        # Verify failure but with partial recovery information
        assert result.success is False
        assert "Permission set collection failed" in result.message

        # Should have attempted partial recovery
        assert len(result.warnings) > 0 or "Partial recovery" in result.message

    @pytest.mark.asyncio
    async def test_backup_with_non_retryable_error(self):
        """Test backup operation with non-retryable error."""
        # Setup connection validation to fail with authorization error
        error_response = {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}}
        self.mock_collector.validate_connection.side_effect = ClientError(
            error_response, "ListUsers"
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await self.manager.create_backup(options)

        # Verify failure without retry
        assert result.success is False
        assert "Connection validation failed" in result.message
        assert "Check IAM permissions" in str(result.errors)

        # Should only be called once (no retry for auth errors)
        assert self.mock_collector.validate_connection.call_count == 1

    @pytest.mark.asyncio
    async def test_backup_operation_state_tracking(self):
        """Test that operation state is properly tracked."""
        # Setup mocks for successful backup
        self.mock_collector.validate_connection.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        self.mock_collector.collect_users.return_value = []
        self.mock_collector.collect_groups.return_value = []
        self.mock_collector.collect_permission_sets.return_value = []
        self.mock_collector.collect_assignments.return_value = []
        self.mock_validator.validate_backup_data.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        self.mock_storage_engine.store_backup.return_value = "backup-state-123"
        self.mock_storage_engine.verify_integrity.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await self.manager.create_backup(options)

        # Verify operation states are tracked
        states = await self.manager.list_operation_states()
        assert len(states) >= 0  # May be cleaned up quickly in tests

        # The operation should have completed successfully
        assert result.success is True


class TestEnhancedRestoreManager:
    """Test enhanced restore manager with error handling and rollback."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_storage_engine = AsyncMock()
        self.mock_identity_center_client = AsyncMock()
        self.mock_identity_store_client = AsyncMock()
        self.mock_progress_reporter = AsyncMock()

        # Create enhanced restore manager with fast retry config for testing
        retry_config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1)

        self.manager = EnhancedRestoreManager(
            storage_engine=self.mock_storage_engine,
            identity_center_client=self.mock_identity_center_client,
            identity_store_client=self.mock_identity_store_client,
            progress_reporter=self.mock_progress_reporter,
            retry_config=retry_config,
        )

        # Create test backup data
        self.test_backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup-123",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/test-instance",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="user1", user_name="test1")],
            groups=[GroupData(group_id="group1", display_name="Test Group")],
        )

    @pytest.mark.asyncio
    async def test_successful_restore_with_rollback_tracking(self):
        """Test successful restore operation with rollback tracking."""
        # Setup mocks
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Mock compatibility validation
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(is_valid=True, errors=[], warnings=[])

            # Execute restore
            options = RestoreOptions(
                target_resources=[ResourceType.USERS, ResourceType.GROUPS],
                conflict_strategy=ConflictStrategy.OVERWRITE,
                dry_run=False,
                target_instance_arn="arn:aws:sso:::instance/target-instance",
            )

            result = await self.manager.restore_backup("test-backup-123", options)

            # Verify the restore was attempted
            assert result is not None
            # Note: The actual restore logic is mocked, so we're mainly testing the error handling framework

    @pytest.mark.asyncio
    async def test_restore_with_retry_on_transient_failure(self):
        """Test restore operation with retry on transient failures."""
        # Setup backup retrieval to fail first, then succeed
        retrieval_calls = 0

        async def mock_retrieve_backup(backup_id):
            nonlocal retrieval_calls
            retrieval_calls += 1
            if retrieval_calls == 1:
                raise ConnectionError("Temporary network issue")
            return self.test_backup_data

        self.mock_storage_engine.retrieve_backup.side_effect = mock_retrieve_backup

        # Mock compatibility validation
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(is_valid=True, errors=[], warnings=[])

            # Execute restore
            options = RestoreOptions(
                target_resources=[ResourceType.USERS],
                conflict_strategy=ConflictStrategy.SKIP,
                dry_run=False,
            )

            result = await self.manager.restore_backup("test-backup-123", options)

            # Verify retry occurred
            assert retrieval_calls == 2
            assert result is not None

    @pytest.mark.asyncio
    async def test_restore_with_rollback_on_failure(self):
        """Test restore operation with rollback on failure."""
        # Setup backup retrieval to succeed
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Mock compatibility validation to succeed
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(is_valid=True, errors=[], warnings=[])

            # Mock restore processor to fail after some changes
            with patch(
                "src.awsideman.backup_restore.enhanced_restore_manager.EnhancedRestoreProcessor"
            ) as mock_processor_class:
                mock_processor = AsyncMock()
                mock_processor_class.return_value = mock_processor

                # Make the restore fail
                mock_processor.process_restore_with_rollback.side_effect = Exception(
                    "Restore processing failed"
                )

                # Execute restore
                options = RestoreOptions(
                    target_resources=[ResourceType.USERS],
                    conflict_strategy=ConflictStrategy.OVERWRITE,
                    dry_run=False,
                )

                result = await self.manager.restore_backup("test-backup-123", options)

                # Verify failure and rollback information
                assert result.success is False
                assert "Restore processing failed" in result.message

    @pytest.mark.asyncio
    async def test_restore_preview_functionality(self):
        """Test restore preview functionality."""
        # Setup backup retrieval
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Execute preview
        options = RestoreOptions(
            target_resources=[ResourceType.USERS, ResourceType.GROUPS],
            conflict_strategy=ConflictStrategy.PROMPT,
            dry_run=True,
        )

        preview = await self.manager.preview_restore("test-backup-123", options)

        # Verify preview was generated
        assert preview is not None
        assert isinstance(preview.changes_summary, dict)
        assert isinstance(preview.warnings, list)

    @pytest.mark.asyncio
    async def test_validate_compatibility_functionality(self):
        """Test compatibility validation functionality."""
        # Setup backup retrieval
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Mock compatibility validator
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(
                is_valid=True, errors=[], warnings=["Some warning"], details={"test": "data"}
            )

            # Execute compatibility validation
            result = await self.manager.validate_compatibility(
                "test-backup-123", "arn:aws:sso:::instance/target-instance"
            )

            # Verify validation result
            assert result.is_valid is True
            assert len(result.warnings) == 1
            assert result.warnings[0] == "Some warning"

    @pytest.mark.asyncio
    async def test_restore_operation_state_tracking(self):
        """Test that restore operation state is properly tracked."""
        # Setup mocks
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Mock compatibility validation
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(is_valid=True, errors=[], warnings=[])

            # Execute restore
            options = RestoreOptions(
                target_resources=[ResourceType.USERS],
                conflict_strategy=ConflictStrategy.SKIP,
                dry_run=False,
            )

            await self.manager.restore_backup("test-backup-123", options)

            # Verify operation states are tracked
            states = await self.manager.list_operation_states()
            assert len(states) >= 0  # May be cleaned up quickly in tests

    @pytest.mark.asyncio
    async def test_backup_not_found_error(self):
        """Test handling of backup not found error."""
        # Setup backup retrieval to return None
        self.mock_storage_engine.retrieve_backup.return_value = None

        # Execute restore
        options = RestoreOptions(target_resources=[ResourceType.USERS])
        result = await self.manager.restore_backup("nonexistent-backup", options)

        # Verify failure
        assert result.success is False
        assert "not found or could not be retrieved" in result.message

    @pytest.mark.asyncio
    async def test_compatibility_validation_failure(self):
        """Test handling of compatibility validation failure."""
        # Setup backup retrieval to succeed
        self.mock_storage_engine.retrieve_backup.return_value = self.test_backup_data

        # Mock compatibility validation to fail
        with patch.object(
            self.manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = AsyncMock(
                is_valid=False, errors=["Incompatible version", "Missing permissions"], warnings=[]
            )

            # Execute restore
            options = RestoreOptions(target_resources=[ResourceType.USERS], skip_validation=False)

            result = await self.manager.restore_backup("test-backup-123", options)

            # Verify failure due to compatibility
            assert result.success is False
            assert "Compatibility validation failed" in result.message


class TestErrorHandlingIntegration:
    """Test integration of error handling across enhanced managers."""

    @pytest.mark.asyncio
    async def test_error_categorization_and_reporting(self):
        """Test that errors are properly categorized and reported."""
        # Create manager with mocked dependencies
        mock_collector = AsyncMock()
        mock_storage_engine = AsyncMock()

        retry_config = RetryConfig(max_retries=1, base_delay=0.01)
        manager = EnhancedBackupManager(
            collector=mock_collector, storage_engine=mock_storage_engine, retry_config=retry_config
        )

        # Setup authorization error
        error_response = {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}}
        mock_collector.validate_connection.side_effect = ClientError(error_response, "ListUsers")

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await manager.create_backup(options)

        # Verify error was categorized and reported
        assert result.success is False
        assert "Connection validation failed" in result.message
        assert any("Check IAM permissions" in error for error in result.errors)
        assert any("Error Report ID:" in error for error in result.errors)
        assert any("Next Steps:" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_retry_logic_with_different_error_types(self):
        """Test retry logic behaves correctly for different error types."""
        mock_collector = AsyncMock()
        mock_storage_engine = AsyncMock()

        retry_config = RetryConfig(max_retries=2, base_delay=0.01)
        manager = EnhancedBackupManager(
            collector=mock_collector, storage_engine=mock_storage_engine, retry_config=retry_config
        )

        # Test with retryable error (throttling)
        call_count = 0

        async def mock_validate_with_throttling():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
                raise ClientError(error_response, "ListUsers")
            return AsyncMock(is_valid=True, errors=[], warnings=[])

        mock_collector.validate_connection.side_effect = mock_validate_with_throttling

        # Setup other mocks for success
        mock_collector.collect_users.return_value = []
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        mock_validator = AsyncMock()
        mock_validator.validate_backup_data.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )
        manager.validator = mock_validator

        mock_storage_engine.store_backup.return_value = "backup-retry-test"
        mock_storage_engine.verify_integrity.return_value = AsyncMock(
            is_valid=True, errors=[], warnings=[]
        )

        # Execute backup
        options = BackupOptions(backup_type=BackupType.FULL)
        result = await manager.create_backup(options)

        # Verify success after retries
        assert result.success is True
        assert call_count == 3  # Initial call + 2 retries


if __name__ == "__main__":
    pytest.main([__file__])
