"""
Integration tests for export/import functionality.

This module tests the complete export/import workflow including
format conversion, file operations, and data integrity validation.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from src.awsideman.backup_restore.export_import import ExportImportManager
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


class TestExportImportIntegration:
    """Integration tests for complete export/import workflows."""

    @pytest.fixture
    def sample_backup_data(self):
        """Create comprehensive sample backup data."""
        metadata = BackupMetadata(
            backup_id="integration-test-backup",
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
                user_id="user-1",
                user_name="alice",
                display_name="Alice Smith",
                email="alice@example.com",
                given_name="Alice",
                family_name="Smith",
                active=True,
                external_ids={"external": "ext-alice"},
            ),
            UserData(
                user_id="user-2",
                user_name="bob",
                display_name="Bob Johnson",
                email="bob@example.com",
                given_name="Bob",
                family_name="Johnson",
                active=True,
                external_ids={},
            ),
        ]

        groups = [
            GroupData(
                group_id="group-1",
                display_name="Developers",
                description="Development team",
                members=["user-1", "user-2"],
            ),
            GroupData(
                group_id="group-2",
                display_name="Admins",
                description="Administrative team",
                members=["user-1"],
            ),
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-dev",
                name="DeveloperAccess",
                description="Developer permissions",
                session_duration="PT8H",
                managed_policies=["arn:aws:iam::aws:policy/PowerUserAccess"],
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                name="AdminAccess",
                description="Administrator permissions",
                session_duration="PT4H",
                managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            ),
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-dev",
                principal_type="GROUP",
                principal_id="group-1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                principal_type="GROUP",
                principal_id="group-2",
            ),
        ]

        relationships = RelationshipMap(
            user_groups={"user-1": ["group-1", "group-2"], "user-2": ["group-1"]},
            group_members={"group-1": ["user-1", "user-2"], "group-2": ["user-1"]},
            permission_set_assignments={
                "arn:aws:sso:::permissionSet/ssoins-123/ps-dev": ["assignment-1"],
                "arn:aws:sso:::permissionSet/ssoins-123/ps-admin": ["assignment-2"],
            },
        )

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

    @pytest.fixture
    def mock_storage_engine(self):
        """Create mock storage engine."""
        storage_engine = AsyncMock(spec=StorageEngineInterface)
        return storage_engine

    @pytest.fixture
    def export_import_manager(self, mock_storage_engine):
        """Create export/import manager instance."""
        return ExportImportManager(mock_storage_engine)

    @pytest.mark.asyncio
    async def test_json_export_import_roundtrip(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test complete JSON export/import roundtrip."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data
        mock_storage_engine.store_backup.return_value = "imported-backup-456"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "backup.json"

            # Export backup to JSON
            format_config = ExportFormat(format_type="JSON")
            export_success = await export_import_manager.export_backup(
                backup_id, format_config, str(export_path)
            )

            assert export_success is True
            assert export_path.exists()

            # Verify exported JSON content
            with open(export_path, "r") as f:
                exported_data = json.load(f)

            assert exported_data["metadata"]["backup_id"] == "integration-test-backup"
            assert len(exported_data["users"]) == 2
            assert len(exported_data["groups"]) == 2
            assert len(exported_data["permission_sets"]) == 2
            assert len(exported_data["assignments"]) == 2

            # Import backup from JSON
            source = ImportSource(source_type="filesystem", location=str(export_path))
            imported_backup_id = await export_import_manager.import_backup(source, format_config)

            assert imported_backup_id == "imported-backup-456"

            # Verify storage engine was called correctly
            mock_storage_engine.retrieve_backup.assert_called_once_with(backup_id)
            mock_storage_engine.store_backup.assert_called_once()

            # Verify imported data structure
            stored_backup_data = mock_storage_engine.store_backup.call_args[0][0]
            assert isinstance(stored_backup_data, BackupData)
            assert len(stored_backup_data.users) == 2
            assert stored_backup_data.users[0].user_name == "alice"
            assert stored_backup_data.users[1].user_name == "bob"

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not available")
    @pytest.mark.asyncio
    async def test_yaml_export_import_roundtrip(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test complete YAML export/import roundtrip."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data
        mock_storage_engine.store_backup.return_value = "imported-backup-456"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "backup.yaml"

            # Export backup to YAML
            format_config = ExportFormat(format_type="YAML")
            export_success = await export_import_manager.export_backup(
                backup_id, format_config, str(export_path)
            )

            assert export_success is True
            assert export_path.exists()

            # Verify exported YAML content
            with open(export_path, "r") as f:
                exported_data = yaml.safe_load(f)

            assert exported_data["metadata"]["backup_id"] == "integration-test-backup"
            assert len(exported_data["users"]) == 2

            # Import backup from YAML
            source = ImportSource(source_type="filesystem", location=str(export_path))
            imported_backup_id = await export_import_manager.import_backup(source, format_config)

            assert imported_backup_id == "imported-backup-456"

            # Verify imported data
            stored_backup_data = mock_storage_engine.store_backup.call_args[0][0]
            assert len(stored_backup_data.users) == 2
            assert stored_backup_data.groups[0].display_name == "Developers"

    @pytest.mark.asyncio
    async def test_csv_export_import_roundtrip(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test complete CSV export/import roundtrip."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data
        mock_storage_engine.store_backup.return_value = "imported-backup-456"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "backup_csv"

            # Export backup to CSV
            format_config = ExportFormat(format_type="CSV")
            export_success = await export_import_manager.export_backup(
                backup_id, format_config, str(export_path)
            )

            assert export_success is True

            # Verify CSV directory and files were created
            csv_dir = export_path.with_suffix("")
            assert csv_dir.exists()
            assert (csv_dir / "users.csv").exists()
            assert (csv_dir / "groups.csv").exists()
            assert (csv_dir / "permission_sets.csv").exists()
            assert (csv_dir / "assignments.csv").exists()
            assert (csv_dir / "metadata.csv").exists()

            # Verify CSV content
            with open(csv_dir / "users.csv", "r") as f:
                users_csv = f.read()
            assert "alice" in users_csv
            assert "bob" in users_csv

            # Import backup from CSV directory
            source = ImportSource(source_type="filesystem", location=str(csv_dir))
            imported_backup_id = await export_import_manager.import_backup(source, format_config)

            assert imported_backup_id == "imported-backup-456"

            # Verify imported data
            stored_backup_data = mock_storage_engine.store_backup.call_args[0][0]
            assert len(stored_backup_data.users) == 2
            assert stored_backup_data.users[0].user_name == "alice"
            assert len(stored_backup_data.permission_sets) == 2

    @pytest.mark.asyncio
    async def test_compressed_export_import(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test export/import with compression."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data
        mock_storage_engine.store_backup.return_value = "imported-backup-456"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "backup.json.gz"

            # Export backup with compression
            format_config = ExportFormat(format_type="JSON", compression="gzip")
            export_success = await export_import_manager.export_backup(
                backup_id, format_config, str(export_path)
            )

            assert export_success is True
            assert export_path.exists()

            # Verify file is compressed (binary content)
            with open(export_path, "rb") as f:
                content = f.read()
            assert content[:2] == b"\x1f\x8b"  # Gzip magic bytes

            # Import compressed backup
            source = ImportSource(source_type="filesystem", location=str(export_path))
            imported_backup_id = await export_import_manager.import_backup(source, format_config)

            assert imported_backup_id == "imported-backup-456"

            # Verify data integrity after compression/decompression
            stored_backup_data = mock_storage_engine.store_backup.call_args[0][0]
            assert len(stored_backup_data.users) == 2
            assert stored_backup_data.metadata.backup_id.startswith("imported_")

    @pytest.mark.asyncio
    async def test_format_conversion_workflow(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test format conversion between different formats."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data

        # Test JSON to YAML conversion
        from_format = ExportFormat(format_type="JSON")
        to_format = ExportFormat(format_type="YAML")

        # Mock the export_backup method to simulate successful conversion
        original_export = export_import_manager.export_backup

        async def mock_export(backup_id, format_config, target_path):
            # Create a test file to simulate successful export
            Path(target_path).touch()
            return True

        export_import_manager.export_backup = mock_export

        try:
            converted_path = await export_import_manager.convert_format(
                backup_id, from_format, to_format
            )

            assert converted_path.startswith("/tmp/converted_")
            assert Path(converted_path).exists()

        finally:
            # Restore original method
            export_import_manager.export_backup = original_export

    @pytest.mark.asyncio
    async def test_validation_workflow(self, export_import_manager, sample_backup_data):
        """Test import validation workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create valid JSON file
            json_file = Path(temp_dir) / "valid_backup.json"
            with open(json_file, "w") as f:
                json.dump(sample_backup_data.to_dict(), f)

            # Test validation of valid file
            source = ImportSource(source_type="filesystem", location=str(json_file))
            format_config = ExportFormat(format_type="JSON")

            validation_result = await export_import_manager.validate_import_format(
                source, format_config
            )

            assert validation_result.is_valid is True
            assert len(validation_result.errors) == 0
            assert validation_result.details["total_users"] == 2
            assert validation_result.details["total_groups"] == 2

            # Create invalid JSON file
            invalid_json_file = Path(temp_dir) / "invalid_backup.json"
            with open(invalid_json_file, "w") as f:
                f.write("{ invalid json }")

            # Test validation of invalid file
            invalid_source = ImportSource(source_type="filesystem", location=str(invalid_json_file))

            invalid_validation_result = await export_import_manager.validate_import_format(
                invalid_source, format_config
            )

            assert invalid_validation_result.is_valid is False
            assert len(invalid_validation_result.errors) > 0

    @pytest.mark.asyncio
    async def test_data_integrity_preservation(
        self, export_import_manager, mock_storage_engine, sample_backup_data
    ):
        """Test that data integrity is preserved through export/import cycle."""
        backup_id = "test-backup-123"
        mock_storage_engine.retrieve_backup.return_value = sample_backup_data
        mock_storage_engine.store_backup.return_value = "imported-backup-456"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "backup.json"

            # Export and import
            format_config = ExportFormat(format_type="JSON")

            await export_import_manager.export_backup(backup_id, format_config, str(export_path))

            source = ImportSource(source_type="filesystem", location=str(export_path))
            await export_import_manager.import_backup(source, format_config)

            # Get the imported data
            imported_data = mock_storage_engine.store_backup.call_args[0][0]

            # Verify all data is preserved (excluding backup_id which gets regenerated)
            assert len(imported_data.users) == len(sample_backup_data.users)
            assert len(imported_data.groups) == len(sample_backup_data.groups)
            assert len(imported_data.permission_sets) == len(sample_backup_data.permission_sets)
            assert len(imported_data.assignments) == len(sample_backup_data.assignments)

            # Verify specific data integrity
            assert imported_data.users[0].user_name == sample_backup_data.users[0].user_name
            assert imported_data.users[0].email == sample_backup_data.users[0].email
            assert imported_data.groups[0].display_name == sample_backup_data.groups[0].display_name
            assert (
                imported_data.permission_sets[0].name == sample_backup_data.permission_sets[0].name
            )
            assert (
                imported_data.assignments[0].account_id
                == sample_backup_data.assignments[0].account_id
            )

            # Verify relationships are preserved
            assert (
                imported_data.relationships.user_groups
                == sample_backup_data.relationships.user_groups
            )
            assert (
                imported_data.relationships.group_members
                == sample_backup_data.relationships.group_members
            )


if __name__ == "__main__":
    pytest.main([__file__])
