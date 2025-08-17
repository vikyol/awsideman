"""
Unit tests for export/import manager functionality.

This module tests the export and import capabilities including format conversion,
validation, streaming operations, and audit logging.
"""

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from src.awsideman.backup_restore.export_import import (
    AuditLogger,
    ExportImportError,
    ExportImportManager,
    FormatConverter,
    StreamingProcessor,
)
from src.awsideman.backup_restore.interfaces import StorageEngineInterface
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    ExportFormat,
    GroupData,
    ImportSource,
    PermissionSetData,
    RelationshipMap,
    RetentionPolicy,
    UserData,
)


class TestFormatConverter:
    """Test cases for format conversion functionality."""

    @pytest.fixture
    def sample_backup_data(self):
        """Create sample backup data for testing."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
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
                given_name="Test",
                family_name="User",
                active=True,
                external_ids={"external": "ext-123"},
            )
        ]

        groups = [
            GroupData(
                group_id="group-123",
                display_name="Test Group",
                description="A test group",
                members=["user-123"],
            )
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                name="TestPermissionSet",
                description="Test permission set",
                session_duration="PT1H",
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            )
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
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
    def format_converter(self):
        """Create format converter instance."""
        return FormatConverter()

    @pytest.mark.asyncio
    async def test_convert_to_json(self, format_converter, sample_backup_data):
        """Test conversion to JSON format."""
        json_result = await format_converter.convert_to_json(sample_backup_data)

        assert isinstance(json_result, str)

        # Verify it's valid JSON
        parsed_data = json.loads(json_result)
        assert "metadata" in parsed_data
        assert "users" in parsed_data
        assert "groups" in parsed_data
        assert "permission_sets" in parsed_data
        assert "assignments" in parsed_data

        # Verify content
        assert parsed_data["metadata"]["backup_id"] == "test-backup-123"
        assert len(parsed_data["users"]) == 1
        assert parsed_data["users"][0]["user_name"] == "testuser"

    @pytest.mark.asyncio
    async def test_convert_to_json_pretty_print(self, format_converter, sample_backup_data):
        """Test JSON conversion with pretty printing."""
        json_result = await format_converter.convert_to_json(sample_backup_data, pretty_print=True)

        # Pretty printed JSON should contain indentation
        assert "  " in json_result or "\t" in json_result

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not available")
    @pytest.mark.asyncio
    async def test_convert_to_yaml(self, format_converter, sample_backup_data):
        """Test conversion to YAML format."""
        yaml_result = await format_converter.convert_to_yaml(sample_backup_data)

        assert isinstance(yaml_result, str)

        # Verify it's valid YAML
        parsed_data = yaml.safe_load(yaml_result)
        assert "metadata" in parsed_data
        assert "users" in parsed_data
        assert parsed_data["metadata"]["backup_id"] == "test-backup-123"

    @pytest.mark.asyncio
    async def test_convert_to_yaml_without_pyyaml(self, format_converter, sample_backup_data):
        """Test YAML conversion when PyYAML is not available."""
        with patch("src.awsideman.backup_restore.export_import.YAML_AVAILABLE", False):
            with pytest.raises(ExportImportError, match="YAML export requires PyYAML"):
                await format_converter.convert_to_yaml(sample_backup_data)

    @pytest.mark.asyncio
    async def test_convert_to_csv(self, format_converter, sample_backup_data):
        """Test conversion to CSV format."""
        csv_result = await format_converter.convert_to_csv(sample_backup_data)

        assert isinstance(csv_result, dict)
        assert "users" in csv_result
        assert "groups" in csv_result
        assert "permission_sets" in csv_result
        assert "assignments" in csv_result
        assert "metadata" in csv_result

        # Verify CSV content
        users_csv = csv_result["users"]
        assert "user_id,user_name" in users_csv
        assert "user-123,testuser" in users_csv

    @pytest.mark.asyncio
    async def test_convert_from_json(self, format_converter, sample_backup_data):
        """Test conversion from JSON format."""
        # First convert to JSON
        json_data = await format_converter.convert_to_json(sample_backup_data)

        # Then convert back
        restored_data = await format_converter.convert_from_json(json_data)

        assert isinstance(restored_data, BackupData)
        assert restored_data.metadata.backup_id == "test-backup-123"
        assert len(restored_data.users) == 1
        assert restored_data.users[0].user_name == "testuser"

    @pytest.mark.asyncio
    async def test_convert_from_invalid_json(self, format_converter):
        """Test conversion from invalid JSON."""
        invalid_json = "{ invalid json }"

        with pytest.raises(ExportImportError, match="Invalid JSON format"):
            await format_converter.convert_from_json(invalid_json)

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not available")
    @pytest.mark.asyncio
    async def test_convert_from_yaml(self, format_converter, sample_backup_data):
        """Test conversion from YAML format."""
        # First convert to YAML
        yaml_data = await format_converter.convert_to_yaml(sample_backup_data)

        # Then convert back
        restored_data = await format_converter.convert_from_yaml(yaml_data)

        assert isinstance(restored_data, BackupData)
        assert restored_data.metadata.backup_id == "test-backup-123"

    @pytest.mark.asyncio
    async def test_convert_from_csv(self, format_converter, sample_backup_data):
        """Test conversion from CSV format."""
        # First convert to CSV
        csv_data = await format_converter.convert_to_csv(sample_backup_data)

        # Then convert back
        restored_data = await format_converter.convert_from_csv(csv_data)

        assert isinstance(restored_data, BackupData)
        assert restored_data.metadata.backup_id == "test-backup-123"
        assert len(restored_data.users) == 1
        assert restored_data.users[0].user_name == "testuser"

    @pytest.mark.asyncio
    async def test_convert_from_csv_missing_metadata(self, format_converter):
        """Test CSV conversion with missing metadata."""
        csv_data = {"users": "user_id,user_name\nuser-123,testuser"}

        with pytest.raises(ExportImportError, match="Metadata CSV file is required"):
            await format_converter.convert_from_csv(csv_data)


class TestStreamingProcessor:
    """Test cases for streaming operations."""

    @pytest.fixture
    def streaming_processor(self):
        """Create streaming processor instance."""
        return StreamingProcessor(chunk_size=100)

    @pytest.fixture
    def sample_backup_data(self):
        """Create sample backup data for testing."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        return BackupData(
            metadata=metadata,
            users=[UserData(user_id=f"user-{i}", user_name=f"user{i}") for i in range(5)],
            groups=[],
            permission_sets=[],
            assignments=[],
        )

    @pytest.mark.asyncio
    async def test_stream_json_export(self, streaming_processor, sample_backup_data):
        """Test streaming JSON export."""
        from io import StringIO

        output_stream = StringIO()
        format_config = ExportFormat(format_type="JSON")

        await streaming_processor.stream_export(sample_backup_data, format_config, output_stream)

        result = output_stream.getvalue()
        assert result.startswith("{")
        assert result.endswith("}\n")
        assert '"metadata"' in result
        assert '"users"' in result

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not available")
    @pytest.mark.asyncio
    async def test_stream_yaml_export(self, streaming_processor, sample_backup_data):
        """Test streaming YAML export."""
        from io import StringIO

        output_stream = StringIO()
        format_config = ExportFormat(format_type="YAML")

        await streaming_processor.stream_export(sample_backup_data, format_config, output_stream)

        result = output_stream.getvalue()
        assert "metadata:" in result
        assert "users:" in result

    @pytest.mark.asyncio
    async def test_stream_csv_export(self, streaming_processor, sample_backup_data):
        """Test streaming CSV export."""
        from io import StringIO

        output_stream = StringIO()
        format_config = ExportFormat(format_type="CSV")

        await streaming_processor.stream_export(sample_backup_data, format_config, output_stream)

        result = output_stream.getvalue()
        assert "# USERS" in result
        assert "# METADATA" in result
        assert "user_id,user_name" in result

    @pytest.mark.asyncio
    async def test_stream_unsupported_format(self, streaming_processor, sample_backup_data):
        """Test streaming with unsupported format."""
        from io import StringIO

        output_stream = StringIO()
        format_config = ExportFormat(format_type="UNSUPPORTED")

        with pytest.raises(ExportImportError, match="Streaming not supported"):
            await streaming_processor.stream_export(
                sample_backup_data, format_config, output_stream
            )


class TestAuditLogger:
    """Test cases for audit logging functionality."""

    @pytest.fixture
    def audit_logger(self):
        """Create audit logger instance."""
        return AuditLogger()

    @pytest.mark.asyncio
    async def test_log_export_start(self, audit_logger):
        """Test logging export start."""
        operation_id = str(uuid.uuid4())
        backup_id = "test-backup-123"
        format_config = ExportFormat(format_type="JSON")
        target_path = "/tmp/test.json"

        # Should not raise any exceptions
        await audit_logger.log_export_start(operation_id, backup_id, format_config, target_path)

    @pytest.mark.asyncio
    async def test_log_export_complete(self, audit_logger):
        """Test logging export completion."""
        operation_id = str(uuid.uuid4())

        # Test successful completion
        await audit_logger.log_export_complete(operation_id, True, 1024)

        # Test failed completion
        await audit_logger.log_export_complete(operation_id, False, error="Test error")

    @pytest.mark.asyncio
    async def test_log_import_start(self, audit_logger):
        """Test logging import start."""
        operation_id = str(uuid.uuid4())
        source = ImportSource(source_type="filesystem", location="/tmp/test.json")
        format_config = ExportFormat(format_type="JSON")

        # Should not raise any exceptions
        await audit_logger.log_import_start(operation_id, source, format_config)

    @pytest.mark.asyncio
    async def test_log_import_complete(self, audit_logger):
        """Test logging import completion."""
        operation_id = str(uuid.uuid4())

        # Test successful completion
        await audit_logger.log_import_complete(operation_id, True, backup_id="imported-backup-123")

        # Test failed completion
        await audit_logger.log_import_complete(operation_id, False, error="Test error")


class TestExportImportManager:
    """Test cases for the main export/import manager."""

    @pytest.fixture
    def mock_storage_engine(self):
        """Create mock storage engine."""
        storage_engine = AsyncMock(spec=StorageEngineInterface)
        return storage_engine

    @pytest.fixture
    def export_import_manager(self, mock_storage_engine):
        """Create export/import manager instance."""
        return ExportImportManager(mock_storage_engine)

    @pytest.fixture
    def sample_backup_data(self):
        """Create sample backup data for testing."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
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

        return BackupData(
            metadata=metadata, users=users, groups=[], permission_sets=[], assignments=[]
        )

    @pytest.mark.asyncio
    async def test_export_backup_json(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test exporting backup to JSON format."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "backup.json"
            format_config = ExportFormat(format_type="JSON")

            result = await export_import_manager.export_backup(
                backup_id, format_config, str(target_path)
            )

            assert result is True
            assert target_path.exists()

            # Verify content
            with open(target_path, "r") as f:
                content = json.load(f)
            assert content["metadata"]["backup_id"] == backup_id

    @pytest.mark.asyncio
    async def test_export_backup_not_found(self, export_import_manager, mock_storage_engine):
        """Test exporting non-existent backup."""
        backup_id = "non-existent-backup"
        mock_storage_engine.retrieve_backup.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "backup.json"
            format_config = ExportFormat(format_type="JSON")

            result = await export_import_manager.export_backup(
                backup_id, format_config, str(target_path)
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_export_backup_with_compression(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test exporting backup with compression."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "backup.json"
            format_config = ExportFormat(format_type="JSON", compression="gzip")

            result = await export_import_manager.export_backup(
                backup_id, format_config, str(target_path)
            )

            assert result is True
            assert target_path.exists()

            # File should be compressed (binary content)
            with open(target_path, "rb") as f:
                content = f.read()
            # Gzip files start with specific magic bytes
            assert content[:2] == b"\x1f\x8b"

    @pytest.mark.asyncio
    async def test_export_backup_csv(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test exporting backup to CSV format."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "backup_csv"
            format_config = ExportFormat(format_type="CSV")

            result = await export_import_manager.export_backup(
                backup_id, format_config, str(target_path)
            )

            assert result is True

            # CSV export creates a directory with multiple files
            csv_dir = target_path.with_suffix("")
            assert csv_dir.exists()
            assert (csv_dir / "users.csv").exists()
            assert (csv_dir / "metadata.csv").exists()

    @pytest.mark.asyncio
    async def test_import_backup_json(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test importing backup from JSON format."""
        mock_storage_engine.store_backup.return_value = "imported-backup-123"

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test JSON file
            json_file = Path(temp_dir) / "backup.json"
            with open(json_file, "w") as f:
                json.dump(sample_backup_data.to_dict(), f)

            source = ImportSource(source_type="filesystem", location=str(json_file))
            format_config = ExportFormat(format_type="JSON")

            result = await export_import_manager.import_backup(source, format_config)

            assert result == "imported-backup-123"
            mock_storage_engine.store_backup.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_backup_file_not_found(self, export_import_manager, mock_storage_engine):
        """Test importing from non-existent file."""
        source = ImportSource(source_type="filesystem", location="/non/existent/file.json")
        format_config = ExportFormat(format_type="JSON")

        with pytest.raises(ExportImportError, match="Source file not found"):
            await export_import_manager.import_backup(source, format_config)

    @pytest.mark.asyncio
    async def test_validate_import_format_valid(self, export_import_manager, sample_backup_data):
        """Test validating valid import format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test JSON file
            json_file = Path(temp_dir) / "backup.json"
            with open(json_file, "w") as f:
                json.dump(sample_backup_data.to_dict(), f)

            source = ImportSource(source_type="filesystem", location=str(json_file))
            format_config = ExportFormat(format_type="JSON")

            result = await export_import_manager.validate_import_format(source, format_config)

            assert result.is_valid is True
            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_import_format_invalid(self, export_import_manager):
        """Test validating invalid import format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create invalid JSON file
            json_file = Path(temp_dir) / "backup.json"
            with open(json_file, "w") as f:
                f.write("{ invalid json }")

            source = ImportSource(source_type="filesystem", location=str(json_file))
            format_config = ExportFormat(format_type="JSON")

            result = await export_import_manager.validate_import_format(source, format_config)

            assert result.is_valid is False
            assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_convert_format(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test format conversion."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data

        from_format = ExportFormat(format_type="JSON")
        to_format = ExportFormat(format_type="YAML")

        with patch.object(export_import_manager, "export_backup", return_value=True) as mock_export:
            result = await export_import_manager.convert_format(backup_id, from_format, to_format)

            assert result.startswith("/tmp/converted_")
            mock_export.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_format_backup_not_found(
        self, export_import_manager, mock_storage_engine
    ):
        """Test format conversion with non-existent backup."""
        backup_id = "non-existent-backup"
        mock_storage_engine.retrieve_backup.return_value = None

        from_format = ExportFormat(format_type="JSON")
        to_format = ExportFormat(format_type="YAML")

        with pytest.raises(ExportImportError, match="Backup not found"):
            await export_import_manager.convert_format(backup_id, from_format, to_format)

    @pytest.mark.asyncio
    async def test_unsupported_source_type(self, export_import_manager):
        """Test import with unsupported source type."""
        source = ImportSource(source_type="unsupported", location="test")
        format_config = ExportFormat(format_type="JSON")

        with pytest.raises(ExportImportError, match="Unsupported source type"):
            await export_import_manager.import_backup(source, format_config)

    @pytest.mark.asyncio
    async def test_s3_import_not_implemented(self, export_import_manager):
        """Test that S3 import raises not implemented error."""
        source = ImportSource(source_type="s3", location="s3://bucket/key")
        format_config = ExportFormat(format_type="JSON")

        with pytest.raises(ExportImportError, match="S3 import not yet implemented"):
            await export_import_manager.import_backup(source, format_config)

    @pytest.mark.asyncio
    async def test_url_import_not_implemented(self, export_import_manager):
        """Test that URL import raises not implemented error."""
        source = ImportSource(source_type="url", location="https://example.com/backup.json")
        format_config = ExportFormat(format_type="JSON")

        with pytest.raises(ExportImportError, match="URL import not yet implemented"):
            await export_import_manager.import_backup(source, format_config)


class TestValidation:
    """Test cases for backup data validation."""

    @pytest.fixture
    def export_import_manager(self):
        """Create export/import manager instance."""
        mock_storage_engine = AsyncMock(spec=StorageEngineInterface)
        return ExportImportManager(mock_storage_engine)

    @pytest.mark.asyncio
    async def test_validate_backup_data_valid(self, export_import_manager):
        """Test validation of valid backup data."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[UserData(user_id="user-123", user_name="testuser")],
            groups=[],
            permission_sets=[],
            assignments=[],
        )

        result = await export_import_manager._validate_backup_data(backup_data)

        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_backup_data_missing_metadata(self, export_import_manager):
        """Test validation with missing metadata."""
        # Create a backup data object with minimal metadata first
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        backup_data = BackupData(
            metadata=metadata, users=[], groups=[], permission_sets=[], assignments=[]
        )

        # Now set metadata to None to test validation
        backup_data.metadata = None

        result = await export_import_manager._validate_backup_data(backup_data)

        assert result.is_valid is False
        assert "Missing backup metadata" in result.errors

    @pytest.mark.asyncio
    async def test_validate_backup_data_invalid_user(self, export_import_manager):
        """Test validation with invalid user data."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[UserData(user_id="", user_name="")],  # Invalid user
            groups=[],
            permission_sets=[],
            assignments=[],
        )

        result = await export_import_manager._validate_backup_data(backup_data)

        assert result.is_valid is False
        assert any("Invalid user data" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_backup_data_empty_backup(self, export_import_manager):
        """Test validation with empty backup."""
        metadata = BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        backup_data = BackupData(
            metadata=metadata, users=[], groups=[], permission_sets=[], assignments=[]
        )

        result = await export_import_manager._validate_backup_data(backup_data)

        assert result.is_valid is True  # Empty backup is valid
        assert "Backup contains no resources" in result.warnings


if __name__ == "__main__":
    pytest.main([__file__])
