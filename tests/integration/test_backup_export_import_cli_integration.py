"""Integration tests for backup export/import CLI commands.

This module tests the backup export and import CLI commands including
export, import, and validate-import operations.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from awsideman.commands.backup.export_import_commands import app


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_profile_data():
    """Mock profile data for testing."""
    return {
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "account_id": "123456789012",
        "region": "us-east-1",
    }


@pytest.fixture
def temp_export_file(tmp_path):
    """Create a temporary export file for testing."""
    export_file = tmp_path / "test_export.json"
    return str(export_file)


@pytest.fixture
def temp_import_file(tmp_path):
    """Create a temporary import file for testing."""
    import_data = {
        "metadata": {
            "backup_id": "backup-123",
            "timestamp": "2024-01-17T14:30:22",
            "instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "backup_type": "full",
            "version": "1.0.0",
            "source_account": "123456789012",
            "source_region": "us-east-1",
        },
        "users": [],
        "groups": [],
        "permission_sets": [],
        "assignments": [],
        "relationships": {},
        "checksums": {},
    }

    import_file = tmp_path / "test_import.json"
    import_file.write_text(json.dumps(import_data, indent=2))
    return str(import_file)


class TestExportCommand:
    """Test the export command."""

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_export_backup_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_export_file,
    ):
        """Test successful backup export."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "output_path": temp_export_file,
            "file_size": 1024,
            "message": "Export completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app, ["export", "backup-123", "--format", "json", "--output", temp_export_file]
        )

        # Verify result
        assert result.exit_code == 0
        assert "Export completed successfully" in result.stdout
        assert temp_export_file in result.stdout
        assert "1.0 KB" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_export_backup_with_compression(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_export_file,
    ):
        """Test backup export with compression."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "output_path": temp_export_file,
            "file_size": 512,
            "message": "Export completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app,
            [
                "export",
                "backup-123",
                "--format",
                "json",
                "--output",
                temp_export_file,
                "--compress",
                "gzip",
            ],
        )

        # Verify result
        assert result.exit_code == 0
        assert "Export completed successfully" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_export_backup_with_encryption(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_export_file,
    ):
        """Test backup export with encryption."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "output_path": temp_export_file,
            "file_size": 1024,
            "message": "Export completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app,
            ["export", "backup-123", "--format", "json", "--output", temp_export_file, "--encrypt"],
        )

        # Verify result
        assert result.exit_code == 0
        assert "Export completed successfully" in result.stdout
        assert "Encryption: Enabled" in result.stdout
        mock_asyncio_run.assert_called_once()

    def test_export_backup_invalid_format(self, cli_runner, temp_export_file):
        """Test export with invalid format."""
        result = cli_runner.invoke(
            app, ["export", "backup-123", "--format", "invalid", "--output", temp_export_file]
        )

        assert result.exit_code == 1
        assert "Invalid export format" in result.stdout

    def test_export_backup_invalid_compression(self, cli_runner, temp_export_file):
        """Test export with invalid compression type."""
        result = cli_runner.invoke(
            app,
            [
                "export",
                "backup-123",
                "--format",
                "json",
                "--output",
                temp_export_file,
                "--compress",
                "invalid",
            ],
        )

        assert result.exit_code == 1
        assert "Invalid compression type" in result.stdout

    def test_export_backup_empty_id(self, cli_runner, temp_export_file):
        """Test export with empty backup ID."""
        result = cli_runner.invoke(
            app, ["export", "", "--format", "json", "--output", temp_export_file]
        )

        assert result.exit_code == 1
        assert "Backup ID cannot be empty" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.Path.exists")
    def test_export_backup_file_exists_no_overwrite(
        self, mock_exists, cli_runner, temp_export_file
    ):
        """Test export when output file exists and no overwrite flag."""
        mock_exists.return_value = True

        result = cli_runner.invoke(
            app, ["export", "backup-123", "--format", "json", "--output", temp_export_file]
        )

        assert result.exit_code == 1
        assert "Output file already exists" in result.stdout
        assert "Use --overwrite" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_export_backup_failure(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_export_file,
    ):
        """Test export failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Export failed",
            "errors": ["Backup not found"],
        }

        # Run command
        result = cli_runner.invoke(
            app, ["export", "backup-123", "--format", "json", "--output", temp_export_file]
        )

        # Verify result
        assert result.exit_code == 1
        assert "Export failed" in result.stdout
        assert "Backup not found" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_export_backup_json_output(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_export_file,
    ):
        """Test export with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "output_path": temp_export_file,
            "file_size": 1024,
            "message": "Export completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app,
            [
                "export",
                "backup-123",
                "--format",
                "json",
                "--output",
                temp_export_file,
                "--output-format",
                "json",
            ],
        )

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert output_data["output_path"] == temp_export_file


class TestImportCommand:
    """Test the import command."""

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_import_backup_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test successful backup import."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "backup_id": "imported-backup-456",
            "message": "Import completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app, ["import", "--source", temp_import_file, "--format", "json"]
        )

        # Verify result
        assert result.exit_code == 0
        assert "Import completed successfully" in result.stdout
        assert "imported-backup-456" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_import_backup_validate_only(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test import with validation only."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {"is_valid": True, "errors": [], "warnings": [], "details": {}},
        }

        # Run command
        result = cli_runner.invoke(
            app, ["import", "--source", temp_import_file, "--format", "json", "--validate-only"]
        )

        # Verify result
        assert result.exit_code == 0
        assert "Import data validation passed" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_import_backup_validation_failure(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test import with validation failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {
                "is_valid": False,
                "errors": ["Invalid backup format", "Missing required fields"],
                "warnings": [],
                "details": {},
            },
        }

        # Run command
        result = cli_runner.invoke(
            app, ["import", "--source", temp_import_file, "--format", "json", "--validate-only"]
        )

        # Verify result
        assert result.exit_code == 1
        assert "Import data validation failed" in result.stdout
        assert "Invalid backup format" in result.stdout
        assert "Missing required fields" in result.stdout

    def test_import_backup_invalid_format(self, cli_runner, temp_import_file):
        """Test import with invalid format."""
        result = cli_runner.invoke(
            app, ["import", "--source", temp_import_file, "--format", "invalid"]
        )

        assert result.exit_code == 1
        assert "Invalid import format" in result.stdout

    def test_import_backup_invalid_source_type(self, cli_runner, temp_import_file):
        """Test import with invalid source type."""
        result = cli_runner.invoke(
            app,
            [
                "import",
                "--source",
                temp_import_file,
                "--format",
                "json",
                "--source-type",
                "invalid",
            ],
        )

        assert result.exit_code == 1
        assert "Invalid source type" in result.stdout

    def test_import_backup_empty_source(self, cli_runner):
        """Test import with empty source."""
        result = cli_runner.invoke(app, ["import", "--source", "", "--format", "json"])

        assert result.exit_code == 1
        assert "Source cannot be empty" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_import_backup_failure(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test import failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Import failed",
            "errors": ["File not found"],
        }

        # Run command
        result = cli_runner.invoke(
            app, ["import", "--source", temp_import_file, "--format", "json"]
        )

        # Verify result
        assert result.exit_code == 1
        assert "Import failed" in result.stdout
        assert "File not found" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_import_backup_s3_source(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test import from S3 source."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "backup_id": "imported-backup-456",
            "message": "Import completed successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app,
            [
                "import",
                "--source",
                "s3://my-bucket/backup.json",
                "--format",
                "json",
                "--source-type",
                "s3",
            ],
        )

        # Verify result
        assert result.exit_code == 0
        assert "Import completed successfully" in result.stdout
        mock_asyncio_run.assert_called_once()


class TestValidateImportCommand:
    """Test the validate-import command."""

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_validate_import_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test successful import validation."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {
                "is_valid": True,
                "errors": [],
                "warnings": ["Minor formatting issue"],
                "details": {
                    "format_check": {"passed": True, "message": "Valid JSON format"},
                    "schema_check": {"passed": True, "message": "Schema validation passed"},
                    "integrity_check": {"passed": True, "message": "Data integrity verified"},
                },
            },
        }

        # Run command
        result = cli_runner.invoke(
            app, ["validate-import", "--source", temp_import_file, "--format", "json"]
        )

        # Verify result
        assert result.exit_code == 0
        assert "Import format validation passed" in result.stdout
        assert "Validation Details" in result.stdout
        assert "Format Check" in result.stdout
        assert "Schema Check" in result.stdout
        assert "Integrity Check" in result.stdout
        assert "Minor formatting issue" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_validate_import_failure(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test import validation failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {
                "is_valid": False,
                "errors": ["Invalid JSON syntax", "Missing metadata section"],
                "warnings": [],
                "details": {
                    "format_check": {"passed": False, "message": "Invalid JSON syntax"},
                    "schema_check": {"passed": False, "message": "Missing required fields"},
                },
            },
        }

        # Run command
        result = cli_runner.invoke(
            app, ["validate-import", "--source", temp_import_file, "--format", "json"]
        )

        # Verify result
        assert result.exit_code == 1
        assert "Import format validation failed" in result.stdout
        assert "Invalid JSON syntax" in result.stdout
        assert "Missing metadata section" in result.stdout

    @patch("awsideman.commands.backup.export_import_commands.validate_profile")
    @patch("awsideman.commands.backup.export_import_commands.asyncio.run")
    def test_validate_import_json_output(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        temp_import_file,
    ):
        """Test import validation with JSON output."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {"is_valid": True, "errors": [], "warnings": [], "details": {}},
        }

        # Run command
        result = cli_runner.invoke(
            app,
            [
                "validate-import",
                "--source",
                temp_import_file,
                "--format",
                "json",
                "--output-format",
                "json",
            ],
        )

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert output_data["validation"]["is_valid"] is True

    def test_validate_import_invalid_format(self, cli_runner, temp_import_file):
        """Test validate-import with invalid format."""
        result = cli_runner.invoke(
            app, ["validate-import", "--source", temp_import_file, "--format", "invalid"]
        )

        assert result.exit_code == 1
        assert "Invalid import format" in result.stdout

    def test_validate_import_empty_source(self, cli_runner):
        """Test validate-import with empty source."""
        result = cli_runner.invoke(app, ["validate-import", "--source", "", "--format", "json"])

        assert result.exit_code == 1
        assert "Source cannot be empty" in result.stdout


@pytest.mark.asyncio
class TestExportImportAsyncFunctions:
    """Test the async helper functions used by export/import commands."""

    @patch("awsideman.commands.backup.export_import_commands.ExportImportManager")
    @patch("awsideman.commands.backup.export_import_commands.StorageEngine")
    async def test_export_backup_async_success(
        self, mock_storage_engine_class, mock_export_import_manager_class, mock_profile_data
    ):
        """Test successful async backup export."""
        from awsideman.backup_restore.models import ExportFormat
        from awsideman.commands.backup.export_import_commands import _export_backup_async

        # Setup mocks
        mock_export_import_manager = AsyncMock()
        mock_export_import_manager.export_backup.return_value = True
        mock_export_import_manager_class.return_value = mock_export_import_manager

        # Call function
        result = await _export_backup_async(
            backup_id="backup-123",
            format_config=ExportFormat(format_type="json"),
            output_path="/tmp/export.json",
            storage_backend="filesystem",
            storage_path=None,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["output_path"] == "/tmp/export.json"
        mock_export_import_manager.export_backup.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.ExportImportManager")
    @patch("awsideman.commands.backup.export_import_commands.StorageEngine")
    async def test_import_backup_async_success(
        self, mock_storage_engine_class, mock_export_import_manager_class, mock_profile_data
    ):
        """Test successful async backup import."""
        from awsideman.backup_restore.models import ExportFormat, ImportSource
        from awsideman.commands.backup.export_import_commands import _import_backup_async

        # Setup mocks
        mock_export_import_manager = AsyncMock()
        mock_export_import_manager.import_backup.return_value = "imported-backup-456"
        mock_export_import_manager_class.return_value = mock_export_import_manager

        # Call function
        result = await _import_backup_async(
            import_source=ImportSource(source_type="filesystem", location="/tmp/import.json"),
            format_config=ExportFormat(format_type="json"),
            storage_backend="filesystem",
            storage_path=None,
            validate_only=False,
            skip_validation=False,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["backup_id"] == "imported-backup-456"
        mock_export_import_manager.import_backup.assert_called_once()

    @patch("awsideman.commands.backup.export_import_commands.ExportImportManager")
    @patch("awsideman.commands.backup.export_import_commands.StorageEngine")
    async def test_validate_import_format_async_success(
        self, mock_storage_engine_class, mock_export_import_manager_class, mock_profile_data
    ):
        """Test successful async import format validation."""
        from awsideman.backup_restore.models import ExportFormat, ImportSource, ValidationResult
        from awsideman.commands.backup.export_import_commands import _validate_import_format_async

        # Setup mocks
        mock_validation_result = ValidationResult(is_valid=True, errors=[], warnings=[], details={})
        mock_export_import_manager = AsyncMock()
        mock_export_import_manager.validate_import_format.return_value = mock_validation_result
        mock_export_import_manager_class.return_value = mock_export_import_manager

        # Call function
        result = await _validate_import_format_async(
            import_source=ImportSource(source_type="filesystem", location="/tmp/import.json"),
            format_config=ExportFormat(format_type="json"),
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["validation"]["is_valid"] is True
        mock_export_import_manager.validate_import_format.assert_called_once()
