"""
Unit tests for backup diff error handling and validation.

This module tests the comprehensive error handling and validation features
implemented for the backup diff functionality.
"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.awsideman.backup_restore.backup_diff_manager import (
    BackupDiffError,
    BackupDiffManager,
    ComparisonError,
    DataCorruptionError,
    InputValidator,
    OutputFormatError,
    ProgressTracker,
)
from src.awsideman.backup_restore.backup_resolver import (
    BackupNotFoundError,
    BackupResolver,
    InvalidDateSpecError,
)
from src.awsideman.backup_restore.diff_models import DiffResult, DiffSummary, ResourceDiff
from src.awsideman.backup_restore.models import (
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
)
from src.awsideman.backup_restore.validation import ValidationResult


class TestInputValidator:
    """Test input validation functionality."""

    def test_validate_output_format_valid_formats(self):
        """Test validation of valid output formats."""
        valid_formats = ["console", "json", "csv", "html"]

        for format_str in valid_formats:
            # Test lowercase
            result = InputValidator.validate_output_format(format_str)
            assert result == format_str

            # Test uppercase
            result = InputValidator.validate_output_format(format_str.upper())
            assert result == format_str

            # Test mixed case
            result = InputValidator.validate_output_format(format_str.capitalize())
            assert result == format_str

    def test_validate_output_format_invalid_formats(self):
        """Test validation of invalid output formats."""
        invalid_formats = ["xml", "yaml", "txt", "pdf"]

        for format_str in invalid_formats:
            with pytest.raises(OutputFormatError) as exc_info:
                InputValidator.validate_output_format(format_str)
            assert "Invalid output format" in str(exc_info.value)

        # Test empty string separately (different error message)
        with pytest.raises(OutputFormatError) as exc_info:
            InputValidator.validate_output_format("")
        assert "must be a non-empty string" in str(exc_info.value)

    def test_validate_output_format_none_and_non_string(self):
        """Test validation with None and non-string inputs."""
        invalid_inputs = [None, 123, [], {}, True]

        for invalid_input in invalid_inputs:
            with pytest.raises(OutputFormatError) as exc_info:
                InputValidator.validate_output_format(invalid_input)
            assert "must be a non-empty string" in str(exc_info.value)

    def test_validate_output_file_valid_paths(self):
        """Test validation of valid output file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test valid file path in existing directory
            valid_path = os.path.join(temp_dir, "output.json")
            result = InputValidator.validate_output_file(valid_path)
            assert result == valid_path

            # Test None (should be allowed)
            result = InputValidator.validate_output_file(None)
            assert result is None

    def test_validate_output_file_invalid_paths(self):
        """Test validation of invalid output file paths."""
        # Test empty string
        with pytest.raises(OutputFormatError):
            InputValidator.validate_output_file("")

        # Test non-string
        with pytest.raises(OutputFormatError):
            InputValidator.validate_output_file(123)

        # Test non-existent directory
        with pytest.raises(OutputFormatError):
            InputValidator.validate_output_file("/non/existent/directory/file.json")

    def test_validate_backup_specs_valid(self):
        """Test validation of valid backup specifications."""
        # Should not raise any exceptions
        InputValidator.validate_backup_specs("7d")
        InputValidator.validate_backup_specs("2025-01-15")
        InputValidator.validate_backup_specs("backup-123", "backup-456")
        InputValidator.validate_backup_specs("current", None)

    def test_validate_backup_specs_invalid(self):
        """Test validation of invalid backup specifications."""
        # Test empty source spec
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs("")

        # Test None source spec
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs(None)

        # Test empty target spec
        with pytest.raises(InvalidDateSpecError):
            InputValidator.validate_backup_specs("7d", "")


class TestProgressTracker:
    """Test progress tracking functionality."""

    def test_progress_tracker_initialization(self):
        """Test progress tracker initialization."""
        tracker = ProgressTracker(total_steps=5)
        assert tracker.total_steps == 5
        assert tracker.current_step == 0
        assert len(tracker.step_descriptions) == 5

    def test_progress_tracker_callbacks(self):
        """Test progress tracker callback functionality."""
        tracker = ProgressTracker(total_steps=3)
        callback_calls = []

        def test_callback(current, total, description):
            callback_calls.append((current, total, description))

        tracker.add_callback(test_callback)

        # Test updates
        tracker.update("Step 1")
        tracker.update("Step 2")
        tracker.complete()

        assert len(callback_calls) == 3
        assert callback_calls[0] == (0, 3, "Step 1")
        assert callback_calls[1] == (1, 3, "Step 2")
        assert callback_calls[2] == (3, 3, "Complete")

    def test_progress_tracker_callback_errors(self):
        """Test progress tracker handles callback errors gracefully."""
        tracker = ProgressTracker(total_steps=2)

        def failing_callback(current, total, description):
            raise Exception("Callback error")

        tracker.add_callback(failing_callback)

        # Should not raise exception
        tracker.update("Test step")
        tracker.complete()


class TestBackupResolverErrorHandling:
    """Test backup resolver error handling."""

    def test_invalid_date_spec_error_with_suggestions(self):
        """Test InvalidDateSpecError with suggestions."""
        suggestions = ["Use format YYYY-MM-DD", "Try relative dates like '7d'"]
        error = InvalidDateSpecError("Invalid format", suggestions=suggestions)

        assert str(error) == "Invalid format"
        assert error.suggestions == suggestions

    def test_backup_not_found_error_with_available_backups(self):
        """Test BackupNotFoundError with available backups."""
        mock_backup = Mock()
        mock_backup.backup_id = "backup-123"
        mock_backup.timestamp = datetime.now()

        available_backups = [mock_backup]
        error = BackupNotFoundError("Not found", available_backups=available_backups)

        assert str(error) == "Not found"
        assert error.available_backups == available_backups

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_resolve_backup_from_spec_invalid_format(self, mock_metadata_index):
        """Test backup resolution with invalid format."""
        resolver = BackupResolver(mock_metadata_index)

        with pytest.raises(InvalidDateSpecError) as exc_info:
            resolver.resolve_backup_from_spec("invalid-format")

        error = exc_info.value
        assert "Invalid date specification format" in str(error)
        assert hasattr(error, "suggestions")
        assert len(error.suggestions) > 0

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_resolve_backup_from_spec_empty_input(self, mock_metadata_index):
        """Test backup resolution with empty input."""
        resolver = BackupResolver(mock_metadata_index)

        with pytest.raises(InvalidDateSpecError) as exc_info:
            resolver.resolve_backup_from_spec("")

        error = exc_info.value
        assert "cannot be empty" in str(error)
        assert hasattr(error, "suggestions")


class TestBackupDiffManagerErrorHandling:
    """Test backup diff manager error handling."""

    def create_mock_backup_data(self, backup_id: str = "test-backup") -> BackupData:
        """Create mock backup data for testing."""
        metadata = BackupMetadata(
            backup_id=backup_id,
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890123456",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
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

    def create_mock_diff_result(self) -> DiffResult:
        """Create mock diff result for testing."""
        return DiffResult(
            source_backup_id="source",
            target_backup_id="target",
            source_timestamp=datetime.now() - timedelta(days=1),
            target_timestamp=datetime.now(),
            user_diff=ResourceDiff(resource_type="users"),
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=0),
        )

    @pytest.fixture
    def mock_diff_manager(self):
        """Create a mock backup diff manager for testing."""
        mock_storage = Mock()
        mock_metadata_index = Mock()
        mock_collector = Mock()

        manager = BackupDiffManager(
            storage_engine=mock_storage,
            metadata_index=mock_metadata_index,
            collector=mock_collector,
        )

        return manager

    @pytest.mark.asyncio
    async def test_compare_backups_invalid_output_format(self, mock_diff_manager):
        """Test compare_backups with invalid output format."""
        with pytest.raises(OutputFormatError):
            await mock_diff_manager.compare_backups(
                source_spec="7d", output_format="invalid-format"
            )

    @pytest.mark.asyncio
    async def test_compare_backups_invalid_output_file(self, mock_diff_manager):
        """Test compare_backups with invalid output file."""
        with pytest.raises(OutputFormatError):
            await mock_diff_manager.compare_backups(
                source_spec="7d", output_file="/non/existent/directory/output.json"
            )

    @pytest.mark.asyncio
    async def test_compare_backups_empty_source_spec(self, mock_diff_manager):
        """Test compare_backups with empty source specification."""
        with pytest.raises(InvalidDateSpecError):
            await mock_diff_manager.compare_backups(source_spec="")

    @pytest.mark.asyncio
    async def test_load_backup_with_retry_success_after_retry(self, mock_diff_manager):
        """Test backup loading succeeds after retry."""
        mock_backup_data = self.create_mock_backup_data()

        # Mock storage engine to fail first, then succeed
        mock_diff_manager.storage_engine.retrieve_backup = AsyncMock(
            side_effect=[Exception("Temporary failure"), mock_backup_data]
        )

        result = await mock_diff_manager._load_backup_with_retry("test-backup", max_retries=2)
        assert result == mock_backup_data
        assert mock_diff_manager.storage_engine.retrieve_backup.call_count == 2

    @pytest.mark.asyncio
    async def test_load_backup_with_retry_corruption_error(self, mock_diff_manager):
        """Test backup loading with corruption error (no retry)."""
        mock_diff_manager.storage_engine.retrieve_backup = AsyncMock(
            side_effect=Exception("Data is corrupt")
        )

        with pytest.raises(DataCorruptionError):
            await mock_diff_manager._load_backup_with_retry("test-backup")

        # Should only be called once (no retry for corruption)
        assert mock_diff_manager.storage_engine.retrieve_backup.call_count == 1

    @pytest.mark.asyncio
    async def test_load_backup_with_retry_max_retries_exceeded(self, mock_diff_manager):
        """Test backup loading fails after max retries."""
        mock_diff_manager.storage_engine.retrieve_backup = AsyncMock(
            side_effect=Exception("Persistent failure")
        )

        with pytest.raises(ComparisonError) as exc_info:
            await mock_diff_manager._load_backup_with_retry("test-backup", max_retries=2)

        assert "after 3 attempts" in str(exc_info.value)
        assert mock_diff_manager.storage_engine.retrieve_backup.call_count == 3

    @pytest.mark.asyncio
    async def test_validate_backup_data_invalid(self, mock_diff_manager):
        """Test backup data validation with invalid data."""
        mock_backup_data = self.create_mock_backup_data()

        # Mock validator to return invalid result
        with patch(
            "src.awsideman.backup_restore.backup_diff_manager.DataValidator"
        ) as mock_validator_class:
            mock_validator = mock_validator_class.return_value
            mock_validator.validate_backup_data.return_value = ValidationResult(
                is_valid=False,
                errors=["Invalid backup data", "Missing required fields"],
                warnings=[],
                details={},
            )

            with pytest.raises(DataCorruptionError) as exc_info:
                await mock_diff_manager._validate_backup_data(mock_backup_data, "test")

            assert "backup data is invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_backup_data_with_warnings(self, mock_diff_manager):
        """Test backup data validation with warnings."""
        mock_backup_data = self.create_mock_backup_data()

        with patch(
            "src.awsideman.backup_restore.backup_diff_manager.DataValidator"
        ) as mock_validator_class:
            mock_validator = mock_validator_class.return_value
            mock_validator.validate_backup_data.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=["Warning 1", "Warning 2"], details={}
            )

            # Should not raise exception but log warnings
            await mock_diff_manager._validate_backup_data(mock_backup_data, "test")

    @pytest.mark.asyncio
    async def test_save_output_permission_error(self, mock_diff_manager):
        """Test output saving with permission error."""
        diff_result = self.create_mock_diff_result()

        # Create a directory that we can make read-only
        with tempfile.TemporaryDirectory() as temp_dir:
            # Make directory read-only
            os.chmod(temp_dir, 0o444)
            temp_path = os.path.join(temp_dir, "output.json")

            try:
                # Mock the output formatter to return some content
                mock_diff_manager.output_formatter.format_json = Mock(
                    return_value='{"test": "data"}'
                )

                with pytest.raises(OutputFormatError) as exc_info:
                    await mock_diff_manager._save_output(diff_result, "json", temp_path)

                assert "Permission denied" in str(exc_info.value) or "Failed to write" in str(
                    exc_info.value
                )
            finally:
                # Restore permissions for cleanup
                os.chmod(temp_dir, 0o755)

    @pytest.mark.asyncio
    async def test_save_output_invalid_format(self, mock_diff_manager):
        """Test output saving with invalid format."""
        diff_result = self.create_mock_diff_result()

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            with pytest.raises(OutputFormatError) as exc_info:
                await mock_diff_manager._save_output(diff_result, "invalid", temp_path)

            assert "Unsupported output format" in str(exc_info.value)
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_collect_current_state_no_collector(self, mock_diff_manager):
        """Test current state collection without collector."""
        mock_diff_manager.collector = None

        with pytest.raises(ComparisonError) as exc_info:
            await mock_diff_manager._collect_current_state()

        assert "no collector provided" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_collect_current_state_partial_failure(self, mock_diff_manager):
        """Test current state collection with partial failures."""
        # Mock collector methods to simulate partial failures
        # At least one collection should succeed to avoid total failure
        mock_diff_manager.collector.collect_users = AsyncMock(
            return_value=[Mock()]
        )  # Return at least one user
        mock_diff_manager.collector.collect_groups = AsyncMock(
            side_effect=Exception("Groups failed")
        )
        mock_diff_manager.collector.collect_permission_sets = AsyncMock(return_value=[])
        mock_diff_manager.collector.collect_assignments = AsyncMock(
            side_effect=Exception("Assignments failed")
        )

        # Should succeed with partial data
        result = await mock_diff_manager._collect_current_state()
        assert isinstance(result, BackupData)
        assert len(result.users) == 1  # One user collected
        assert len(result.groups) == 0  # Failed collection
        assert len(result.permission_sets) == 0
        assert len(result.assignments) == 0  # Failed collection

    @pytest.mark.asyncio
    async def test_collect_current_state_total_failure(self, mock_diff_manager):
        """Test current state collection with total failure."""
        # Mock all collector methods to fail
        mock_diff_manager.collector.collect_users = AsyncMock(side_effect=Exception("Users failed"))
        mock_diff_manager.collector.collect_groups = AsyncMock(
            side_effect=Exception("Groups failed")
        )
        mock_diff_manager.collector.collect_permission_sets = AsyncMock(
            side_effect=Exception("Permission sets failed")
        )
        mock_diff_manager.collector.collect_assignments = AsyncMock(
            side_effect=Exception("Assignments failed")
        )

        with pytest.raises(ComparisonError) as exc_info:
            await mock_diff_manager._collect_current_state()

        assert "Failed to collect any current state data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_compare_backups_with_progress_callback(self, mock_diff_manager):
        """Test compare_backups with progress callback."""
        # Mock all dependencies
        mock_backup_data = self.create_mock_backup_data()
        mock_diff_result = self.create_mock_diff_result()

        mock_diff_manager.backup_resolver.resolve_backup_from_spec = Mock(return_value=None)
        mock_diff_manager._collect_current_state = AsyncMock(return_value=mock_backup_data)
        mock_diff_manager._validate_backup_data = AsyncMock()
        mock_diff_manager.diff_engine.compute_diff = Mock(return_value=mock_diff_result)

        # Track progress callback calls
        progress_calls = []

        def progress_callback(current, total, description):
            progress_calls.append((current, total, description))

        result = await mock_diff_manager.compare_backups(
            source_spec="current", target_spec="current", progress_callback=progress_callback
        )

        assert result == mock_diff_result
        assert len(progress_calls) > 0  # Should have received progress updates


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_progress_tracker_zero_steps(self):
        """Test progress tracker with zero steps."""
        tracker = ProgressTracker(total_steps=0)
        tracker.update("Test")
        tracker.complete()  # Should not raise exception

    def test_input_validator_whitespace_handling(self):
        """Test input validator handles whitespace correctly."""
        # Output format with whitespace
        result = InputValidator.validate_output_format("  json  ")
        assert result == "json"

        # Backup specs with whitespace
        InputValidator.validate_backup_specs("  7d  ", "  current  ")  # Should not raise

    @patch("src.awsideman.backup_restore.backup_resolver.LocalMetadataIndex")
    def test_backup_resolver_edge_cases(self, mock_metadata_index):
        """Test backup resolver edge cases."""
        resolver = BackupResolver(mock_metadata_index)

        # Test with very large relative date
        with pytest.raises(InvalidDateSpecError):
            resolver.resolve_backup_from_spec("999999d")

        # Test with negative relative date
        with pytest.raises(InvalidDateSpecError):
            resolver.resolve_backup_from_spec("-7d")

    def test_error_classes_inheritance(self):
        """Test error class inheritance structure."""
        # Test inheritance chain
        assert issubclass(ComparisonError, BackupDiffError)
        assert issubclass(DataCorruptionError, BackupDiffError)
        assert issubclass(OutputFormatError, BackupDiffError)
        assert issubclass(BackupDiffError, Exception)

        # Test error instantiation
        error = DataCorruptionError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, BackupDiffError)
        assert isinstance(error, Exception)


if __name__ == "__main__":
    pytest.main([__file__])
