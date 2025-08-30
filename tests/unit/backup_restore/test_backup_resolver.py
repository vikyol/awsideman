"""
Unit tests for BackupResolver class.

Tests date parsing, backup resolution, and edge case handling.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.awsideman.backup_restore.backup_resolver import BackupResolver, InvalidDateSpecError
from src.awsideman.backup_restore.models import (
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
)


@pytest.fixture
def mock_metadata_index():
    """Create a mock metadata index."""
    return Mock()


@pytest.fixture
def backup_resolver(mock_metadata_index):
    """Create a BackupResolver instance with mocked dependencies."""
    return BackupResolver(mock_metadata_index)


@pytest.fixture
def sample_backups():
    """Create sample backup metadata for testing."""
    base_time = datetime(2025, 1, 15, 12, 0, 0)
    backups = []

    for i in range(5):
        backup_time = base_time - timedelta(days=i)
        backup = BackupMetadata(
            backup_id=f"backup-{i}",
            timestamp=backup_time,
            instance_arn=f"arn:aws:sso:::instance/ins-{i}",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )
        backups.append(backup)

    return backups


class TestBackupResolver:
    """Test cases for BackupResolver class."""


class TestDateSpecValidation:
    """Test date specification validation."""

    def test_validate_relative_dates(self, backup_resolver):
        """Test validation of relative date formats."""
        valid_specs = ["1d", "7d", "30d", "365d"]
        for spec in valid_specs:
            assert backup_resolver.validate_date_spec(spec) is True

    def test_validate_absolute_dates(self, backup_resolver):
        """Test validation of absolute date formats."""
        valid_specs = [
            "2025-01-15",
            "20250115",
            "2025-01-15T10:30:00",
            "2025-01-15T10:30:00.123456",
            "2025-01-15T10:30:00+00:00",
            "2025-01-15T10:30:00Z",
        ]
        for spec in valid_specs:
            assert backup_resolver.validate_date_spec(spec) is True

    def test_validate_special_values(self, backup_resolver):
        """Test validation of special values."""
        assert backup_resolver.validate_date_spec("current") is True
        assert backup_resolver.validate_date_spec("CURRENT") is True

    def test_validate_invalid_specs(self, backup_resolver):
        """Test validation of invalid date specifications."""
        invalid_specs = [
            "",
            "   ",
            "invalid",
            "7days",
            "d7",
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
            "25-01-15",  # Invalid year format
            "-7d",  # Negative days not in correct format
        ]
        for spec in invalid_specs:
            assert backup_resolver.validate_date_spec(spec) is False


class TestRelativeDateParsing:
    """Test relative date parsing functionality."""

    @patch("src.awsideman.backup_restore.backup_resolver.datetime")
    def test_parse_relative_date_basic(self, mock_datetime, backup_resolver):
        """Test basic relative date parsing."""
        # Mock current time
        current_time = datetime(2025, 1, 15, 12, 0, 0)
        mock_datetime.now.return_value = current_time

        # Test 7 days ago
        result = backup_resolver._parse_relative_date("7d")
        expected = current_time - timedelta(days=7)
        assert result == expected

    @patch("src.awsideman.backup_restore.backup_resolver.datetime")
    def test_parse_relative_date_edge_cases(self, mock_datetime, backup_resolver):
        """Test edge cases for relative date parsing."""
        current_time = datetime(2025, 1, 15, 12, 0, 0)
        mock_datetime.now.return_value = current_time

        # Test 0 days (today)
        result = backup_resolver._parse_relative_date("0d")
        assert result == current_time

        # Test large number of days
        result = backup_resolver._parse_relative_date("365d")
        expected = current_time - timedelta(days=365)
        assert result == expected

    def test_parse_relative_date_invalid(self, backup_resolver):
        """Test invalid relative date formats."""
        invalid_specs = ["d", "7", "7days", "-7d", "7.5d"]
        for spec in invalid_specs:
            with pytest.raises(ValueError):
                backup_resolver._parse_relative_date(spec)


class TestAbsoluteDateParsing:
    """Test absolute date parsing functionality."""

    def test_parse_absolute_date_basic_formats(self, backup_resolver):
        """Test basic absolute date formats."""
        test_cases = [
            ("2025-01-15", datetime(2025, 1, 15, 0, 0, 0)),
            ("20250115", datetime(2025, 1, 15, 0, 0, 0)),
            ("2025-01-15T10:30:00", datetime(2025, 1, 15, 10, 30, 0)),
        ]

        for spec, expected in test_cases:
            result = backup_resolver._parse_absolute_date(spec)
            assert result == expected

    def test_parse_absolute_date_with_microseconds(self, backup_resolver):
        """Test absolute date parsing with microseconds."""
        spec = "2025-01-15T10:30:00.123456"
        result = backup_resolver._parse_absolute_date(spec)
        expected = datetime(2025, 1, 15, 10, 30, 0, 123456)
        assert result == expected

    def test_parse_absolute_date_with_timezone(self, backup_resolver):
        """Test absolute date parsing with timezone information."""
        # Test UTC timezone
        spec = "2025-01-15T10:30:00+00:00"
        result = backup_resolver._parse_absolute_date(spec)
        # Should parse successfully (exact comparison depends on timezone handling)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_absolute_date_invalid(self, backup_resolver):
        """Test invalid absolute date formats."""
        invalid_specs = [
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
            "25-01-15",  # Invalid year
            "2025/01/15",  # Wrong separator
            "invalid-date",
        ]

        for spec in invalid_specs:
            with pytest.raises(ValueError):
                backup_resolver._parse_absolute_date(spec)


class TestBackupResolution:
    """Test backup resolution functionality."""

    def test_resolve_current_state(self, backup_resolver):
        """Test resolving 'current' state specification."""
        result = backup_resolver.resolve_backup_from_spec("current")
        assert result is None  # None indicates current state should be collected

    def test_resolve_relative_date(self, backup_resolver, sample_backups):
        """Test resolving relative date specifications."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        with patch("src.awsideman.backup_restore.backup_resolver.datetime") as mock_datetime:
            # Mock current time to be the same as the first backup
            mock_datetime.now.return_value = sample_backups[0].timestamp

            # Request backup from 2 days ago
            result = backup_resolver.resolve_backup_from_spec("2d")

            # Should return the backup closest to 2 days ago
            assert result is not None
            assert result.backup_id in [b.backup_id for b in sample_backups]

    def test_resolve_absolute_date(self, backup_resolver, sample_backups):
        """Test resolving absolute date specifications."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Request backup for a specific date
        target_date = sample_backups[1].timestamp.strftime("%Y-%m-%d")
        result = backup_resolver.resolve_backup_from_spec(target_date)

        # Should return the closest backup
        assert result is not None
        assert result.backup_id in [b.backup_id for b in sample_backups]

    def test_resolve_empty_spec(self, backup_resolver):
        """Test resolving empty date specifications."""
        with pytest.raises(InvalidDateSpecError):
            backup_resolver.resolve_backup_from_spec("")

        with pytest.raises(InvalidDateSpecError):
            backup_resolver.resolve_backup_from_spec("   ")

    def test_resolve_invalid_spec(self, backup_resolver):
        """Test resolving invalid date specifications."""
        with pytest.raises(InvalidDateSpecError):
            backup_resolver.resolve_backup_from_spec("invalid-spec")


class TestClosestBackupFinding:
    """Test finding closest backup functionality."""

    def test_find_closest_backup_exact_match(self, backup_resolver, sample_backups):
        """Test finding backup with exact timestamp match."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Request exact timestamp of second backup
        target_date = sample_backups[1].timestamp
        result = backup_resolver.find_closest_backup(target_date)

        assert result is not None
        assert result.backup_id == sample_backups[1].backup_id

    def test_find_closest_backup_approximate_match(self, backup_resolver, sample_backups):
        """Test finding backup with approximate timestamp match."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Request timestamp between two backups
        target_date = sample_backups[1].timestamp + timedelta(hours=12)
        result = backup_resolver.find_closest_backup(target_date)

        assert result is not None
        # Should return one of the adjacent backups
        assert result.backup_id in [sample_backups[0].backup_id, sample_backups[1].backup_id]

    def test_find_closest_backup_no_backups(self, backup_resolver):
        """Test finding closest backup when no backups exist."""
        backup_resolver.metadata_index.list_backups.return_value = []

        target_date = datetime.now()
        result = backup_resolver.find_closest_backup(target_date)

        assert result is None

    def test_find_closest_backup_single_backup(self, backup_resolver, sample_backups):
        """Test finding closest backup when only one backup exists."""
        single_backup = [sample_backups[0]]
        backup_resolver.metadata_index.list_backups.return_value = single_backup

        target_date = datetime.now()
        result = backup_resolver.find_closest_backup(target_date)

        assert result is not None
        assert result.backup_id == sample_backups[0].backup_id


class TestDateRangeOperations:
    """Test date range operations."""

    def test_find_backup_by_date_range(self, backup_resolver, sample_backups):
        """Test finding backups within a date range."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Define a range that includes some backups
        start_date = sample_backups[3].timestamp
        end_date = sample_backups[1].timestamp

        result = backup_resolver.find_backup_by_date_range(start_date, end_date)

        # Should return backups within the range
        assert len(result) >= 2
        for backup in result:
            assert start_date <= backup.timestamp <= end_date

    def test_find_backup_by_date_range_no_matches(self, backup_resolver, sample_backups):
        """Test finding backups in a range with no matches."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Define a range with no backups
        start_date = datetime(2020, 1, 1)
        end_date = datetime(2020, 1, 2)

        result = backup_resolver.find_backup_by_date_range(start_date, end_date)

        assert len(result) == 0

    def test_get_available_date_range(self, backup_resolver, sample_backups):
        """Test getting available date range."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        result = backup_resolver.get_available_date_range()

        assert result is not None
        earliest, latest = result
        assert earliest == min(b.timestamp for b in sample_backups)
        assert latest == max(b.timestamp for b in sample_backups)

    def test_get_available_date_range_no_backups(self, backup_resolver):
        """Test getting available date range when no backups exist."""
        backup_resolver.metadata_index.list_backups.return_value = []

        result = backup_resolver.get_available_date_range()

        assert result is None


class TestSuggestions:
    """Test backup suggestion functionality."""

    def test_suggest_closest_dates(self, backup_resolver, sample_backups):
        """Test suggesting closest backup dates."""
        backup_resolver.metadata_index.list_backups.return_value = sample_backups

        # Request suggestions for a date between backups
        target_date = sample_backups[1].timestamp + timedelta(hours=12)
        result = backup_resolver.suggest_closest_dates(target_date, count=3)

        assert len(result) <= 3
        assert len(result) <= len(sample_backups)

        # Results should be sorted by proximity
        if len(result) > 1:
            distances = [abs((backup.timestamp - target_date).total_seconds()) for backup in result]
            assert distances == sorted(distances)

    def test_suggest_closest_dates_no_backups(self, backup_resolver):
        """Test suggesting dates when no backups exist."""
        backup_resolver.metadata_index.list_backups.return_value = []

        target_date = datetime.now()
        result = backup_resolver.suggest_closest_dates(target_date)

        assert len(result) == 0


class TestBackupById:
    """Test backup retrieval by ID."""

    def test_get_backup_by_id_success(self, backup_resolver, sample_backups):
        """Test successful backup retrieval by ID."""
        target_backup = sample_backups[0]
        backup_resolver.metadata_index.get_backup_metadata.return_value = target_backup

        result = backup_resolver.get_backup_by_id(target_backup.backup_id)

        assert result is not None
        assert result.backup_id == target_backup.backup_id

    def test_get_backup_by_id_not_found(self, backup_resolver):
        """Test backup retrieval when backup doesn't exist."""
        backup_resolver.metadata_index.get_backup_metadata.return_value = None

        result = backup_resolver.get_backup_by_id("nonexistent-backup")

        assert result is None


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_metadata_index_exception(self, backup_resolver):
        """Test handling of metadata index exceptions."""
        backup_resolver.metadata_index.list_backups.side_effect = Exception("Database error")

        target_date = datetime.now()
        result = backup_resolver.find_closest_backup(target_date)

        # Should handle exception gracefully
        assert result is None

    def test_invalid_date_spec_error_message(self, backup_resolver):
        """Test that InvalidDateSpecError provides helpful error messages."""
        with pytest.raises(InvalidDateSpecError) as exc_info:
            backup_resolver.resolve_backup_from_spec("invalid-format")

        error_message = str(exc_info.value)
        assert "invalid-format" in error_message
        assert "Supported formats" in error_message


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_leap_year_handling(self, backup_resolver):
        """Test handling of leap year dates."""
        # Test leap year date
        leap_year_date = "2024-02-29"
        assert backup_resolver.validate_date_spec(leap_year_date) is True

        result = backup_resolver._parse_absolute_date(leap_year_date)
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 29

    def test_month_boundary_relative_dates(self, backup_resolver):
        """Test relative dates that cross month boundaries."""
        with patch("src.awsideman.backup_restore.backup_resolver.datetime") as mock_datetime:
            # Set current time to beginning of month
            current_time = datetime(2025, 2, 1, 12, 0, 0)
            mock_datetime.now.return_value = current_time

            # Request 5 days ago (should go to previous month)
            result = backup_resolver._parse_relative_date("5d")
            expected = datetime(2025, 1, 27, 12, 0, 0)
            assert result == expected

    def test_year_boundary_relative_dates(self, backup_resolver):
        """Test relative dates that cross year boundaries."""
        with patch("src.awsideman.backup_restore.backup_resolver.datetime") as mock_datetime:
            # Set current time to beginning of year
            current_time = datetime(2025, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = current_time

            # Request 5 days ago (should go to previous year)
            result = backup_resolver._parse_relative_date("5d")
            expected = datetime(2024, 12, 27, 12, 0, 0)
            assert result == expected

    def test_case_insensitive_parsing(self, backup_resolver):
        """Test that parsing is case insensitive."""
        test_cases = ["current", "CURRENT", "Current", "CuRrEnT"]

        for spec in test_cases:
            result = backup_resolver.resolve_backup_from_spec(spec)
            assert result is None  # All should resolve to current state

    def test_whitespace_handling(self, backup_resolver):
        """Test handling of whitespace in specifications."""
        test_cases = [
            "  current  ",
            "\tcurrent\t",
            "\ncurrent\n",
            "  7d  ",
            "  2025-01-15  ",
        ]

        for spec in test_cases:
            # Should not raise exceptions
            assert backup_resolver.validate_date_spec(spec) is True

    def test_current_state_variations(self, backup_resolver):
        """Test various forms of current state specification."""
        current_variations = [
            "current",
            "CURRENT",
            "Current",
            "CuRrEnT",
            "  current  ",
            "\tcurrent\n",
        ]

        for spec in current_variations:
            result = backup_resolver.resolve_backup_from_spec(spec)
            assert result is None, f"Failed for spec: '{spec}'"

    def test_current_state_validation(self, backup_resolver):
        """Test validation of current state specifications."""
        current_variations = [
            "current",
            "CURRENT",
            "Current",
            "  current  ",
        ]

        for spec in current_variations:
            assert (
                backup_resolver.validate_date_spec(spec) is True
            ), f"Failed validation for: '{spec}'"

    def test_current_state_mixed_with_other_specs(self, backup_resolver):
        """Test that current state doesn't interfere with other specifications."""
        # Test that "current" doesn't match partial strings
        non_current_specs = [
            "currently",
            "current_backup",
            "not_current",
            "7dcurrent",
            "current7d",
        ]

        for spec in non_current_specs:
            with pytest.raises(InvalidDateSpecError):
                backup_resolver.resolve_backup_from_spec(spec)
