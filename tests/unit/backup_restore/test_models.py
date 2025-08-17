"""
Unit tests for backup-restore data models.

Tests the core data models, validation, and serialization functionality.
"""

from datetime import datetime

import pytest

from src.awsideman.backup_restore.models import (
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
    UserData,
)
from src.awsideman.backup_restore.serialization import DataSerializer, SerializationFormat
from src.awsideman.backup_restore.validation import DataValidator


class TestBackupMetadata:
    """Test BackupMetadata model."""

    def test_backup_metadata_creation(self):
        """Test creating BackupMetadata with valid data."""
        retention_policy = RetentionPolicy(keep_daily=7, keep_weekly=4)
        encryption_info = EncryptionMetadata(algorithm="AES-256", encrypted=True)

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        assert metadata.backup_id == "test-backup-123"
        assert metadata.backup_type == BackupType.FULL
        assert metadata.source_account == "123456789012"
        assert metadata.retention_policy.keep_daily == 7
        assert metadata.encryption_info.encrypted is True

    def test_backup_metadata_validation_errors(self):
        """Test BackupMetadata validation with invalid data."""
        retention_policy = RetentionPolicy()
        encryption_info = EncryptionMetadata()

        # Test empty backup_id
        with pytest.raises(ValueError, match="backup_id cannot be empty"):
            BackupMetadata(
                backup_id="",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=retention_policy,
                encryption_info=encryption_info,
            )

        # Test empty instance_arn
        with pytest.raises(ValueError, match="instance_arn cannot be empty"):
            BackupMetadata(
                backup_id="test-backup-123",
                timestamp=datetime.now(),
                instance_arn="",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=retention_policy,
                encryption_info=encryption_info,
            )

    def test_backup_metadata_serialization(self):
        """Test BackupMetadata serialization and deserialization."""
        retention_policy = RetentionPolicy(keep_daily=7, keep_weekly=4)
        encryption_info = EncryptionMetadata(algorithm="AES-256", encrypted=True)

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        # Test to_dict
        data_dict = metadata.to_dict()
        assert data_dict["backup_id"] == "test-backup-123"
        assert data_dict["backup_type"] == "full"
        assert data_dict["source_account"] == "123456789012"

        # Test from_dict
        restored_metadata = BackupMetadata.from_dict(data_dict)
        assert restored_metadata.backup_id == metadata.backup_id
        assert restored_metadata.backup_type == metadata.backup_type
        assert restored_metadata.source_account == metadata.source_account


class TestUserData:
    """Test UserData model."""

    def test_user_data_creation(self):
        """Test creating UserData with valid data."""
        user = UserData(
            user_id="12345678-1234-1234-1234-123456789012",
            user_name="testuser",
            display_name="Test User",
            email="test@example.com",
            given_name="Test",
            family_name="User",
            active=True,
        )

        assert user.user_id == "12345678-1234-1234-1234-123456789012"
        assert user.user_name == "testuser"
        assert user.email == "test@example.com"
        assert user.active is True

    def test_user_data_serialization(self):
        """Test UserData serialization and deserialization."""
        user = UserData(
            user_id="12345678-1234-1234-1234-123456789012",
            user_name="testuser",
            display_name="Test User",
            email="test@example.com",
        )

        # Test to_dict
        data_dict = user.to_dict()
        assert data_dict["user_id"] == "12345678-1234-1234-1234-123456789012"
        assert data_dict["user_name"] == "testuser"
        assert data_dict["email"] == "test@example.com"

        # Test from_dict
        restored_user = UserData.from_dict(data_dict)
        assert restored_user.user_id == user.user_id
        assert restored_user.user_name == user.user_name
        assert restored_user.email == user.email


class TestBackupData:
    """Test BackupData model."""

    def test_backup_data_creation(self):
        """Test creating BackupData with valid data."""
        retention_policy = RetentionPolicy(keep_daily=7)
        encryption_info = EncryptionMetadata(encrypted=True)

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        users = [
            UserData(
                user_id="12345678-1234-1234-1234-123456789012",
                user_name="testuser1",
                email="test1@example.com",
            ),
            UserData(
                user_id="87654321-4321-4321-4321-210987654321",
                user_name="testuser2",
                email="test2@example.com",
            ),
        ]

        backup_data = BackupData(metadata=metadata, users=users)

        assert len(backup_data.users) == 2
        assert backup_data.metadata.resource_counts["users"] == 2
        assert "users" in backup_data.checksums

    def test_backup_data_integrity_verification(self):
        """Test BackupData integrity verification."""
        retention_policy = RetentionPolicy()
        encryption_info = EncryptionMetadata()

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        users = [UserData(user_id="12345678-1234-1234-1234-123456789012", user_name="testuser1")]

        backup_data = BackupData(metadata=metadata, users=users)

        # Initial integrity should be valid
        assert backup_data.verify_integrity() is True

        # Modify data and verify integrity fails
        backup_data.users.append(
            UserData(user_id="87654321-4321-4321-4321-210987654321", user_name="testuser2")
        )

        assert backup_data.verify_integrity() is False


class TestDataValidator:
    """Test DataValidator functionality."""

    def test_validate_backup_metadata_valid(self):
        """Test validation of valid BackupMetadata."""
        retention_policy = RetentionPolicy(keep_daily=7)
        encryption_info = EncryptionMetadata(encrypted=True)

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        result = DataValidator.validate_backup_metadata(metadata)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_backup_metadata_invalid(self):
        """Test validation of invalid BackupMetadata."""
        retention_policy = RetentionPolicy()
        encryption_info = EncryptionMetadata()

        metadata = BackupMetadata(
            backup_id="short",  # Too short
            timestamp=datetime.now(),
            instance_arn="invalid-arn",  # Invalid format
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="invalid",  # Invalid account ID
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        result = DataValidator.validate_backup_metadata(metadata)
        assert result.is_valid is False
        assert len(result.errors) > 0

        # Check specific error messages
        error_messages = " ".join(result.errors)
        assert "backup_id must be at least 8 characters" in error_messages
        assert "instance_arn has invalid format" in error_messages
        assert "source_account must be a 12-digit AWS account ID" in error_messages

    def test_validate_user_data_valid(self):
        """Test validation of valid UserData."""
        user = UserData(
            user_id="12345678-1234-1234-1234-123456789012",
            user_name="testuser",
            email="test@example.com",
        )

        result = DataValidator.validate_user_data(user)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_user_data_invalid(self):
        """Test validation of invalid UserData."""
        user = UserData(
            user_id="invalid-uuid",  # Invalid UUID format
            user_name="",  # Empty username
            email="invalid-email",  # Invalid email format
        )

        result = DataValidator.validate_user_data(user)
        assert result.is_valid is False
        assert len(result.errors) > 0

        # Check specific error messages
        error_messages = " ".join(result.errors)
        assert "user_id has invalid UUID format" in error_messages
        assert "user_name is required and cannot be empty" in error_messages
        assert "email has invalid format" in error_messages


class TestDataSerializer:
    """Test DataSerializer functionality."""

    def test_serialize_deserialize_user_data(self):
        """Test serialization and deserialization of UserData."""
        user = UserData(
            user_id="12345678-1234-1234-1234-123456789012",
            user_name="testuser",
            email="test@example.com",
            display_name="Test User",
        )

        serializer = DataSerializer()

        # Serialize
        serialized_data = serializer.serialize(user, SerializationFormat.JSON)
        assert isinstance(serialized_data, bytes)

        # Deserialize
        deserialized_user = serializer.deserialize(serialized_data, UserData)
        assert isinstance(deserialized_user, UserData)
        assert deserialized_user.user_id == user.user_id
        assert deserialized_user.user_name == user.user_name
        assert deserialized_user.email == user.email
        assert deserialized_user.display_name == user.display_name

    def test_serialize_deserialize_backup_data(self):
        """Test serialization and deserialization of BackupData."""
        retention_policy = RetentionPolicy(keep_daily=7)
        encryption_info = EncryptionMetadata(encrypted=True)

        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=retention_policy,
            encryption_info=encryption_info,
        )

        users = [UserData(user_id="12345678-1234-1234-1234-123456789012", user_name="testuser1")]

        backup_data = BackupData(metadata=metadata, users=users)

        serializer = DataSerializer()

        # Serialize
        serialized_data = serializer.serialize(backup_data, SerializationFormat.JSON)
        assert isinstance(serialized_data, bytes)

        # Deserialize
        deserialized_backup = serializer.deserialize(serialized_data, BackupData)
        assert isinstance(deserialized_backup, BackupData)
        assert deserialized_backup.metadata.backup_id == backup_data.metadata.backup_id
        assert len(deserialized_backup.users) == len(backup_data.users)
        assert deserialized_backup.users[0].user_id == backup_data.users[0].user_id


if __name__ == "__main__":
    pytest.main([__file__])
