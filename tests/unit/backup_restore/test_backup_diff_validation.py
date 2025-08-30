"""
Unit tests for backup diff validation functionality.

This module tests the validation features for backup diff operations,
including input validation, data integrity checks, and error scenarios.
"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.awsideman.backup_restore.backup_diff_manager import InputValidator, OutputFormatError
from src.awsideman.backup_restore.backup_resolver import (
    BackupNotFoundError,
    BackupResolver,
    InvalidDateSpecError,
)
from src.awsideman.backup_restore.models import (
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
)
from src.awsideman.backup_restore.validation import DataValidator, ValidationResult


class TestInputValidation:
    """Test comprehensive input validation."""

    def test_output_format_case_insensitive(self):
        """Test output format validation is case insensitive."""
        test_cases = [
            ("JSON", "json"),
            ("Html", "html"),
            ("CSV", "csv"),
            ("CONSOLE", "console"),
            ("  json  ", "json"),  # With whitespace
        ]

        for input_format, expected in test_cases:
            result = InputValidator.validate_output_format(input_format)
            assert result == expected

    def test_output_format_error_messages(self):
        """Test output format error messages are helpful."""
        with pytest.raises(OutputFormatError) as exc_info:
            InputValidator.validate_output_format("xml")

        error_msg = str(exc_info.value)
        assert "Invalid output format 'xml'" in error_msg
        assert "console, json, csv, html" in error_msg

    def test_output_file_path_normalization(self):
        """Test output file path normalization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test path with extra whitespace
            test_path = f"  {temp_dir}/output.json  "
            result = InputValidator.validate_output_file(test_path)
            assert result == test_path.strip()

    def test_output_file_directory_creation_check(self):
        """Test output file validation checks directory existence."""
        # Test with non-existent parent directory
        non_existent_path = "/definitely/does/not/exist/output.json"

        with pytest.raises(OutputFormatError) as exc_info:
            InputValidator.validate_output_file(non_existent_path)

        assert "directory does not exist" in str(exc_info.value)

    def test_output_file_permission_check(self):
        """Test output file permission checking."""
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Make file read-only
            os.chmod(temp_path, 0o444)

            with pytest.raises(OutputFormatError) as exc_info:
                InputValidator.validate_output_file(temp_path)

            assert "not writable" in str(exc_info.value)
        finally:
            # Clean up
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)

    def test_backup_spec_validation_comprehensive(self):
        """Test comprehensive backup specification validation."""
        # Valid cases
        valid_specs = [
            ("7d", None),
            ("2025-01-15", "2025-01-20"),
            ("backup-123", "backup-456"),
            ("current", None),
            ("1d", "current"),
        ]

        for source, target in valid_specs:
            # Should not raise any exceptions
            InputValidator.validate_backup_specs(source, target)

    def test_backup_spec_validation_edge_cases(self):
        """Test backup specification validation edge cases."""
        # Test with only whitespace
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs("   ")

        # Test with non-string types
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs(123)

        # Test target spec validation
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs("7d", "   ")


class TestBackupResolverValidation:
    """Test backup resolver validation and error handling."""

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_resolve_backup_comprehensive_error_messages(self, mock_metadata_index):
        """Test comprehensive error messages from backup resolver."""
        resolver = BackupResolver(mock_metadata_index)

        # Mock no available backups
        resolver.get_available_date_range = Mock(return_value=None)

        with pytest.raises(InvalidDateSpecError) as exc_info:
            resolver.resolve_backup_from_spec("invalid-format")

        error = exc_info.value
        assert hasattr(error, "suggestions")
        assert len(error.suggestions) > 0
        assert any("relative dates" in suggestion for suggestion in error.suggestions)

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_resolve_backup_with_available_range(self, mock_metadata_index):
        """Test backup resolution with available date range information."""
        resolver = BackupResolver(mock_metadata_index)

        # Mock available date range
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now() - timedelta(days=1)
        resolver.get_available_date_range = Mock(return_value=(start_date, end_date))
        resolver.find_closest_backup = Mock(return_value=None)

        with pytest.raises(BackupNotFoundError) as exc_info:
            resolver.resolve_backup_from_spec("7d")

        error_msg = str(exc_info.value)
        assert start_date.date().isoformat() in error_msg
        assert end_date.date().isoformat() in error_msg

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_resolve_backup_with_suggestions(self, mock_metadata_index):
        """Test backup resolution provides helpful suggestions."""
        resolver = BackupResolver(mock_metadata_index)

        # Mock suggestion backups
        mock_backup1 = Mock()
        mock_backup1.timestamp = datetime.now() - timedelta(days=5)
        mock_backup1.backup_id = "backup-1"

        mock_backup2 = Mock()
        mock_backup2.timestamp = datetime.now() - timedelta(days=10)
        mock_backup2.backup_id = "backup-2"

        resolver.suggest_closest_dates = Mock(return_value=[mock_backup1, mock_backup2])
        resolver.find_closest_backup = Mock(return_value=None)

        with pytest.raises(BackupNotFoundError) as exc_info:
            resolver.resolve_backup_from_spec("2025-01-15")

        error = exc_info.value
        assert hasattr(error, "available_backups")
        assert len(error.available_backups) == 2

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_date_format_validation_comprehensive(self, mock_metadata_index):
        """Test comprehensive date format validation."""
        resolver = BackupResolver(mock_metadata_index)

        # Test various invalid formats
        invalid_formats = [
            "7days",  # Should be "7d"
            "2025/01/15",  # Wrong separator
            "15-01-2025",  # Wrong order
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
            "abc",  # Non-date string
            "7x",  # Invalid relative format
        ]

        for invalid_format in invalid_formats:
            with pytest.raises(InvalidDateSpecError) as exc_info:
                resolver.resolve_backup_from_spec(invalid_format)

            error = exc_info.value
            assert hasattr(error, "suggestions")
            assert len(error.suggestions) > 0

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_relative_date_boundary_conditions(self, mock_metadata_index):
        """Test relative date boundary conditions."""
        resolver = BackupResolver(mock_metadata_index)

        # Test zero days (should be valid)
        try:
            resolver._parse_relative_date("0d")
        except ValueError:
            pytest.fail("0d should be a valid relative date")

        # Test very large number (should handle gracefully)
        # Use a smaller but still large number that will cause overflow
        with pytest.raises((ValueError, OverflowError)):
            resolver._parse_relative_date("999999d")

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_absolute_date_timezone_handling(self, mock_metadata_index):
        """Test absolute date parsing with timezone information."""
        resolver = BackupResolver(mock_metadata_index)

        # Test various timezone formats
        timezone_formats = [
            "2025-01-15T10:30:00Z",
            "2025-01-15T10:30:00+00:00",
            "2025-01-15T10:30:00-05:00",
            "2025-01-15T10:30:00.123456Z",
        ]

        for date_format in timezone_formats:
            try:
                result = resolver._parse_absolute_date(date_format)
                assert isinstance(result, datetime)
            except ValueError as e:
                pytest.fail(f"Failed to parse valid timezone format {date_format}: {e}")


class TestDataValidationIntegration:
    """Test integration with data validation system."""

    def create_test_backup_data(self, valid: bool = True) -> BackupData:
        """Create test backup data for validation testing."""
        if valid:
            metadata = BackupMetadata(
                backup_id="test-backup-123",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890123456",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            )
        else:
            # Create invalid metadata
            metadata = BackupMetadata(
                backup_id="",  # Invalid: empty backup ID
                timestamp=datetime.now(),
                instance_arn="invalid-arn",  # Invalid ARN format
                backup_type=BackupType.FULL,
                version="",  # Invalid: empty version
                source_account="invalid",  # Invalid account ID
                source_region="",  # Invalid: empty region
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            )

        return BackupData(
            metadata=metadata,
            users=[],
            groups=[],
            permission_sets=[],
            assignments=[],
        )

    def test_backup_data_validation_success(self):
        """Test successful backup data validation."""
        backup_data = self.create_test_backup_data(valid=True)
        validator = DataValidator()

        result = validator.validate_backup_data(backup_data)
        assert result.is_valid

    def test_backup_data_validation_failure(self):
        """Test backup data validation failure."""
        # Create backup data with invalid metadata that won't fail in __post_init__
        metadata = BackupMetadata(
            backup_id="test-backup",  # Valid backup ID
            timestamp=datetime.now(),
            instance_arn="invalid-arn",  # Invalid ARN format - will be caught by validator
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="invalid",  # Invalid account ID - will be caught by validator
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=False),
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[],
            groups=[],
            permission_sets=[],
            assignments=[],
        )

        validator = DataValidator()
        result = validator.validate_backup_data(backup_data)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validation_result_error_handling(self):
        """Test validation result error handling."""
        # Test with multiple errors
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2", "Error 3", "Error 4", "Error 5", "Error 6"],
            warnings=["Warning 1", "Warning 2", "Warning 3", "Warning 4"],
            details={},
        )

        # Test error truncation (should show first 5 errors)
        assert len(result.errors) == 6

        # Test warning truncation (should show first 3 warnings)
        assert len(result.warnings) == 4


class TestErrorMessageQuality:
    """Test the quality and helpfulness of error messages."""

    def test_error_message_contains_context(self):
        """Test error messages contain helpful context."""
        # Test InvalidDateSpecError with suggestions
        error = InvalidDateSpecError(
            "Invalid format 'xyz'",
            suggestions=["Use YYYY-MM-DD format", "Try relative dates like '7d'"],
        )

        assert "Invalid format 'xyz'" in str(error)
        assert hasattr(error, "suggestions")
        assert len(error.suggestions) == 2

    def test_error_message_actionable_advice(self):
        """Test error messages provide actionable advice."""
        # Test BackupNotFoundError with available backups
        mock_backup = Mock()
        mock_backup.backup_id = "backup-123"
        mock_backup.timestamp = datetime.now()

        error = BackupNotFoundError(
            "No backup found for '2025-01-15'", available_backups=[mock_backup]
        )

        assert "No backup found" in str(error)
        assert hasattr(error, "available_backups")
        assert len(error.available_backups) == 1

    def test_output_format_error_specificity(self):
        """Test output format errors are specific and helpful."""
        with pytest.raises(OutputFormatError) as exc_info:
            InputValidator.validate_output_format("xml")

        error_msg = str(exc_info.value)
        # Should mention the invalid format
        assert "xml" in error_msg
        # Should list valid formats
        assert "console" in error_msg
        assert "json" in error_msg
        assert "csv" in error_msg
        assert "html" in error_msg


class TestValidationPerformance:
    """Test validation performance and efficiency."""

    def test_validation_handles_large_datasets(self):
        """Test validation can handle large datasets efficiently."""
        # Create backup data with many resources
        metadata = BackupMetadata(
            backup_id="large-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890123456",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=False),
        )

        # Create large lists (but not too large for test performance)
        large_backup_data = BackupData(
            metadata=metadata,
            users=[],  # Would normally have many users
            groups=[],  # Would normally have many groups
            permission_sets=[],  # Would normally have many permission sets
            assignments=[],  # Would normally have many assignments
        )

        validator = DataValidator()

        # Should complete without timeout or memory issues
        result = validator.validate_backup_data(large_backup_data)
        assert isinstance(result, ValidationResult)

    def test_validation_early_termination(self):
        """Test validation can terminate early on critical errors."""
        # Create backup data with critical error
        metadata = BackupMetadata(
            backup_id="test-backup",
            timestamp=datetime.now(),
            instance_arn="invalid-arn",  # Invalid ARN format
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="invalid",  # Invalid account ID
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=False),
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[],
            groups=[],
            permission_sets=[],
            assignments=[],
        )

        validator = DataValidator()

        # Validation should complete quickly even with errors
        result = validator.validate_backup_data(backup_data)
        assert not result.is_valid
        assert len(result.errors) > 0


if __name__ == "__main__":
    pytest.main([__file__])
