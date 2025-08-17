"""
Integration tests for backup-restore core functionality.

Tests the integration between models, validation, and serialization.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupType,
    ConflictStrategy,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    ResourceType,
    RestoreOptions,
    RetentionPolicy,
    UserData,
)
from src.awsideman.backup_restore.serialization import (
    CompressionType,
    DataSerializer,
    SerializationFormat,
    load_backup_from_file,
    save_backup_to_file,
)
from src.awsideman.backup_restore.validation import DataValidator


class TestBackupRestoreIntegration:
    """Test integration between all backup-restore components."""

    def test_complete_backup_workflow(self):
        """Test a complete backup creation, validation, and serialization workflow."""
        # Create sample data
        retention_policy = RetentionPolicy(keep_daily=7, keep_weekly=4, keep_monthly=12)
        encryption_info = EncryptionMetadata(
            algorithm="AES-256", encrypted=True, key_id="test-key-123"
        )

        metadata = BackupMetadata(
            backup_id="integration-test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        # Create users
        users = [
            UserData(
                user_id="12345678-1234-1234-1234-123456789012",
                user_name="alice.smith",
                display_name="Alice Smith",
                email="alice.smith@example.com",
                given_name="Alice",
                family_name="Smith",
                active=True,
            ),
            UserData(
                user_id="87654321-4321-4321-4321-210987654321",
                user_name="bob.jones",
                display_name="Bob Jones",
                email="bob.jones@example.com",
                given_name="Bob",
                family_name="Jones",
                active=True,
            ),
        ]

        # Create groups
        groups = [
            GroupData(
                group_id="11111111-1111-1111-1111-111111111111",
                display_name="Administrators",
                description="System administrators group",
                members=["12345678-1234-1234-1234-123456789012"],
            ),
            GroupData(
                group_id="22222222-2222-2222-2222-222222222222",
                display_name="Developers",
                description="Software developers group",
                members=["87654321-4321-4321-4321-210987654321"],
            ),
        ]

        # Create permission sets
        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111",
                name="AdminAccess",
                description="Full administrative access",
                session_duration="PT8H",
                managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222",
                name="DeveloperAccess",
                description="Developer access with limited permissions",
                session_duration="PT4H",
                managed_policies=["arn:aws:iam::aws:policy/PowerUserAccess"],
            ),
        ]

        # Create assignments
        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111",
                principal_type="GROUP",
                principal_id="11111111-1111-1111-1111-111111111111",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222",
                principal_type="GROUP",
                principal_id="22222222-2222-2222-2222-222222222222",
            ),
            AssignmentData(
                account_id="987654321098",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111",
                principal_type="USER",
                principal_id="12345678-1234-1234-1234-123456789012",
            ),
        ]

        # Create relationships
        relationships = RelationshipMap(
            user_groups={
                "12345678-1234-1234-1234-123456789012": ["11111111-1111-1111-1111-111111111111"],
                "87654321-4321-4321-4321-210987654321": ["22222222-2222-2222-2222-222222222222"],
            },
            group_members={
                "11111111-1111-1111-1111-111111111111": ["12345678-1234-1234-1234-123456789012"],
                "22222222-2222-2222-2222-222222222222": ["87654321-4321-4321-4321-210987654321"],
            },
            permission_set_assignments={
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111": [
                    "123456789012-GROUP-11111111-1111-1111-1111-111111111111",
                    "987654321098-USER-12345678-1234-1234-1234-123456789012",
                ],
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222": [
                    "123456789012-GROUP-22222222-2222-2222-2222-222222222222"
                ],
            },
        )

        # Create complete backup data
        backup_data = BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

        # Validate the backup data
        validation_result = DataValidator.validate_backup_data(backup_data)
        assert validation_result.is_valid, f"Validation failed: {validation_result.errors}"

        # Verify resource counts are correct
        assert backup_data.metadata.resource_counts["users"] == 2
        assert backup_data.metadata.resource_counts["groups"] == 2
        assert backup_data.metadata.resource_counts["permission_sets"] == 2
        assert backup_data.metadata.resource_counts["assignments"] == 3

        # Verify integrity
        assert backup_data.verify_integrity() is True

        # Test serialization with different formats and compression
        serializer = DataSerializer()

        # Test JSON with GZIP
        json_gzip_data = serializer.serialize(
            backup_data, SerializationFormat.JSON, CompressionType.GZIP
        )
        restored_backup_json = serializer.deserialize(
            json_gzip_data, BackupData, SerializationFormat.JSON, CompressionType.GZIP
        )

        assert restored_backup_json.metadata.backup_id == backup_data.metadata.backup_id
        assert len(restored_backup_json.users) == len(backup_data.users)
        assert len(restored_backup_json.groups) == len(backup_data.groups)
        assert len(restored_backup_json.permission_sets) == len(backup_data.permission_sets)
        assert len(restored_backup_json.assignments) == len(backup_data.assignments)

        # Test file operations
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_file = Path(temp_dir) / "test_backup.json.gz"

            # Save to file
            save_backup_to_file(
                backup_data, backup_file, SerializationFormat.JSON, CompressionType.GZIP
            )
            assert backup_file.exists()
            assert backup_file.stat().st_size > 0

            # Load from file
            loaded_backup = load_backup_from_file(
                backup_file, SerializationFormat.JSON, CompressionType.GZIP
            )
            assert loaded_backup.metadata.backup_id == backup_data.metadata.backup_id
            assert len(loaded_backup.users) == len(backup_data.users)

            # Verify loaded data integrity
            assert loaded_backup.verify_integrity() is True

    def test_backup_options_validation_integration(self):
        """Test integration between BackupOptions and validation."""
        # Test valid backup options
        valid_options = BackupOptions(
            backup_type=BackupType.INCREMENTAL,
            resource_types=[ResourceType.USERS, ResourceType.GROUPS],
            include_inactive_users=False,
            since=datetime.now(),
            encryption_enabled=True,
            compression_enabled=True,
            parallel_collection=True,
        )

        validation_result = DataValidator.validate_backup_options(valid_options)
        assert validation_result.is_valid is True

        # Test serialization of options
        serializer = DataSerializer()
        serialized_options = serializer.serialize(valid_options)
        restored_options = serializer.deserialize(serialized_options, BackupOptions)

        assert restored_options.backup_type == valid_options.backup_type
        assert restored_options.resource_types == valid_options.resource_types
        assert restored_options.encryption_enabled == valid_options.encryption_enabled

    def test_restore_options_validation_integration(self):
        """Test integration between RestoreOptions and validation."""
        # Test valid restore options
        valid_options = RestoreOptions(
            target_resources=[ResourceType.USERS, ResourceType.PERMISSION_SETS],
            conflict_strategy=ConflictStrategy.MERGE,
            dry_run=True,
            target_account="987654321098",
            target_region="us-west-2",
            resource_mappings={"old-user-id": "new-user-id", "old-group-id": "new-group-id"},
            skip_validation=False,
        )

        validation_result = DataValidator.validate_restore_options(valid_options)
        assert validation_result.is_valid is True

        # Test serialization of options
        serializer = DataSerializer()
        serialized_options = serializer.serialize(valid_options)
        restored_options = serializer.deserialize(serialized_options, RestoreOptions)

        assert restored_options.target_resources == valid_options.target_resources
        assert restored_options.conflict_strategy == valid_options.conflict_strategy
        assert restored_options.target_account == valid_options.target_account
        assert restored_options.resource_mappings == valid_options.resource_mappings

    def test_error_handling_integration(self):
        """Test error handling across all components."""
        # Test invalid backup metadata
        invalid_metadata = BackupMetadata(
            backup_id="short",  # Too short
            timestamp=datetime.now(),
            instance_arn="invalid-arn",  # Invalid format
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="invalid-account",  # Invalid format
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        validation_result = DataValidator.validate_backup_metadata(invalid_metadata)
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0

        # Test that serialization still works even with invalid data
        serializer = DataSerializer()
        serialized_data = serializer.serialize(invalid_metadata)
        restored_metadata = serializer.deserialize(serialized_data, BackupMetadata)

        # Data should be restored correctly even if it's invalid
        assert restored_metadata.backup_id == invalid_metadata.backup_id
        assert restored_metadata.instance_arn == invalid_metadata.instance_arn

        # But validation should still fail
        validation_result_restored = DataValidator.validate_backup_metadata(restored_metadata)
        assert validation_result_restored.is_valid is False


if __name__ == "__main__":
    pytest.main([__file__])
