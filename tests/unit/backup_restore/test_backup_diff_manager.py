"""
Unit tests for BackupDiffManager.

This module tests the BackupDiffManager class functionality including backup
resolution, loading, comparison, and output generation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.awsideman.backup_restore.backup_diff_manager import (
    BackupDiffManager,
    ComparisonError,
    OutputFormatError,
)
from src.awsideman.backup_restore.backup_resolver import BackupNotFoundError, InvalidDateSpecError
from src.awsideman.backup_restore.diff_models import DiffResult, DiffSummary, ResourceDiff
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    GroupData,
    PermissionSetData,
    UserData,
)


@pytest.fixture
def mock_storage_engine():
    """Mock storage engine for testing."""
    storage_engine = AsyncMock()
    return storage_engine


@pytest.fixture
def mock_metadata_index():
    """Mock metadata index for testing."""
    metadata_index = MagicMock()
    return metadata_index


@pytest.fixture
def mock_collector():
    """Mock collector for testing."""
    collector = AsyncMock()
    return collector


@pytest.fixture
def sample_backup_metadata():
    """Sample backup metadata for testing."""
    from src.awsideman.backup_restore.models import EncryptionMetadata, RetentionPolicy

    return BackupMetadata(
        backup_id="test-backup-123",
        timestamp=datetime(2025, 1, 15, 10, 30, 0),
        instance_arn="arn:aws:sso:::instance/test-instance",
        backup_type=BackupType.FULL,
        version="1.0.0",
        source_account="123456789012",
        source_region="us-east-1",
        retention_policy=RetentionPolicy(),
        encryption_info=EncryptionMetadata(encrypted=False),
    )


@pytest.fixture
def sample_backup_data(sample_backup_metadata):
    """Sample backup data for testing."""
    return BackupData(
        metadata=sample_backup_metadata,
        users=[
            UserData(
                user_id="user-1",
                user_name="testuser1",
                email="test1@example.com",
                display_name="Test User 1",
            )
        ],
        groups=[
            GroupData(
                group_id="group-1",
                display_name="Test Group 1",
                description="Test group",
            )
        ],
        permission_sets=[
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/test-ps-1",
                name="TestPermissionSet",
                description="Test permission set",
            )
        ],
        assignments=[
            AssignmentData(
                principal_id="user-1",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/test-ps-1",
                account_id="123456789012",
            )
        ],
    )


@pytest.fixture
def sample_diff_result():
    """Sample diff result for testing."""
    return DiffResult(
        source_backup_id="backup-1",
        target_backup_id="backup-2",
        source_timestamp=datetime(2025, 1, 14, 10, 0, 0),
        target_timestamp=datetime(2025, 1, 15, 10, 0, 0),
        user_diff=ResourceDiff(resource_type="users"),
        group_diff=ResourceDiff(resource_type="groups"),
        permission_set_diff=ResourceDiff(resource_type="permission_sets"),
        assignment_diff=ResourceDiff(resource_type="assignments"),
        summary=DiffSummary(
            total_changes=0,
            changes_by_type={},
            changes_by_action={},
        ),
    )


@pytest.fixture
def backup_diff_manager(mock_storage_engine, mock_metadata_index, mock_collector):
    """BackupDiffManager instance for testing."""
    return BackupDiffManager(
        storage_engine=mock_storage_engine,
        metadata_index=mock_metadata_index,
        collector=mock_collector,
        enable_validation=False,  # Disable validation for existing tests
    )


class TestBackupDiffManager:
    """Test cases for BackupDiffManager."""

    def test_init(self, mock_storage_engine, mock_metadata_index, mock_collector):
        """Test BackupDiffManager initialization."""
        manager = BackupDiffManager(
            storage_engine=mock_storage_engine,
            metadata_index=mock_metadata_index,
            collector=mock_collector,
        )

        assert manager.storage_engine == mock_storage_engine
        assert manager.metadata_index == mock_metadata_index
        assert manager.collector == mock_collector
        assert manager.backup_resolver is not None
        assert manager.diff_engine is not None
        assert manager.output_formatter is not None

    def test_init_without_collector(self, mock_storage_engine, mock_metadata_index):
        """Test BackupDiffManager initialization without collector."""
        manager = BackupDiffManager(
            storage_engine=mock_storage_engine,
            metadata_index=mock_metadata_index,
        )

        assert manager.collector is None

    @pytest.mark.asyncio
    async def test_compare_backups_success(
        self,
        backup_diff_manager,
        sample_backup_data,
        sample_diff_result,
    ):
        """Test successful backup comparison."""
        # Mock backup resolution and loading
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            return_value=sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Mock diff computation
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=sample_diff_result)

        result = await backup_diff_manager.compare_backups("7d", "current")

        assert result == sample_diff_result
        backup_diff_manager.storage_engine.retrieve_backup.assert_called()

    @pytest.mark.asyncio
    async def test_compare_backups_with_backup_ids(
        self,
        backup_diff_manager,
        sample_backup_data,
        sample_diff_result,
    ):
        """Test backup comparison using backup IDs."""
        # Mock metadata index to return backup metadata for IDs
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = (
            sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Mock diff computation
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=sample_diff_result)

        result = await backup_diff_manager.compare_backups("backup-1", "backup-2")

        assert result == sample_diff_result
        assert backup_diff_manager.metadata_index.get_backup_metadata.call_count == 2

    @pytest.mark.asyncio
    async def test_compare_backups_invalid_date_spec(self, backup_diff_manager):
        """Test backup comparison with invalid date specification."""
        # Mock both source and target to avoid current state collection
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            side_effect=InvalidDateSpecError("Invalid date format")
        )
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = None

        with pytest.raises(InvalidDateSpecError):
            await backup_diff_manager.compare_backups("invalid-date", "another-invalid-date")

    @pytest.mark.asyncio
    async def test_compare_backups_backup_not_found(self, backup_diff_manager):
        """Test backup comparison when backup is not found."""
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = None
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(return_value=None)

        with pytest.raises(BackupNotFoundError):
            await backup_diff_manager.compare_backups("nonexistent-backup")

    @pytest.mark.asyncio
    async def test_compare_backups_storage_failure(self, backup_diff_manager, sample_backup_data):
        """Test backup comparison when storage loading fails."""
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = (
            sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup.return_value = None

        with pytest.raises(ComparisonError):
            await backup_diff_manager.compare_backups("backup-1")

    @pytest.mark.asyncio
    async def test_compare_backups_with_output_file(
        self,
        backup_diff_manager,
        sample_backup_data,
        sample_diff_result,
    ):
        """Test backup comparison with output file."""
        # Mock backup resolution and loading
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            return_value=sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Mock diff computation
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=sample_diff_result)

        # Mock output formatter
        backup_diff_manager.output_formatter.format_json = MagicMock(
            return_value='{"test": "output"}'
        )

        with patch("tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "temp_file.tmp"
            mock_temp_file.return_value.__enter__.return_value.write = MagicMock()

            with patch("os.path.dirname") as mock_dirname:
                mock_dirname.return_value = "/tmp"
                with patch("os.path.abspath") as mock_abspath:
                    mock_abspath.return_value = "/tmp/output.json"
                    with patch("os.rename") as mock_rename:
                        mock_rename.return_value = None

                        result = await backup_diff_manager.compare_backups(
                            "7d", "current", output_format="json", output_file="output.json"
                        )

                        assert result == sample_diff_result
                        # Verify temp file was created and written to
                        mock_temp_file.assert_called_once()
                        mock_temp_file.return_value.__enter__.return_value.write.assert_called_once_with(
                            '{"test": "output"}'
                        )
                        mock_rename.assert_called_once_with("temp_file.tmp", "output.json")

    @pytest.mark.asyncio
    async def test_collect_current_state_success(self, backup_diff_manager, mock_collector):
        """Test successful current state collection."""
        # Mock collector responses
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-1",
                user_name="currentuser",
                email="current@example.com",
                display_name="Current User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        backup_data = await backup_diff_manager._collect_current_state()

        assert backup_data.metadata.backup_id == "current"
        assert len(backup_data.users) == 1
        assert backup_data.users[0].user_name == "currentuser"

    @pytest.mark.asyncio
    async def test_collect_current_state_no_collector(self, backup_diff_manager):
        """Test current state collection without collector."""
        backup_diff_manager.collector = None

        with pytest.raises(ComparisonError, match="no collector provided"):
            await backup_diff_manager._collect_current_state()

    @pytest.mark.asyncio
    async def test_collect_current_state_failure(self, backup_diff_manager, mock_collector):
        """Test current state collection failure."""
        mock_collector.collect_users.side_effect = Exception("Collection failed")

        with pytest.raises(ComparisonError):
            await backup_diff_manager._collect_current_state()

    @pytest.mark.asyncio
    async def test_collect_current_state_partial_failure(self, backup_diff_manager, mock_collector):
        """Test current state collection with partial failures."""
        # Mock successful collection for some resources, failure for others
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-1",
                user_name="testuser",
                email="test@example.com",
                display_name="Test User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.side_effect = Exception("Permission sets failed")
        mock_collector.collect_assignments.return_value = []

        # Partial failures should not raise an exception, just log warnings
        result = await backup_diff_manager._collect_current_state()

        # Should still return backup data with available resources
        assert result is not None
        assert len(result.users) == 1
        assert len(result.groups) == 0
        assert len(result.permission_sets) == 0
        assert len(result.assignments) == 0

    @pytest.mark.asyncio
    async def test_collect_current_state_empty_resources(self, backup_diff_manager, mock_collector):
        """Test current state collection with empty resource collections."""
        # Mock empty collections for all resource types
        mock_collector.collect_users.return_value = []
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        backup_data = await backup_diff_manager._collect_current_state()

        assert backup_data.metadata.backup_id == "current"
        assert len(backup_data.users) == 0
        assert len(backup_data.groups) == 0
        assert len(backup_data.permission_sets) == 0
        assert len(backup_data.assignments) == 0

    @pytest.mark.asyncio
    async def test_collect_current_state_comprehensive(self, backup_diff_manager, mock_collector):
        """Test current state collection with comprehensive data."""
        # Mock comprehensive data collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-1",
                user_name="user1",
                email="user1@example.com",
                display_name="User One",
                active=True,
            ),
            UserData(
                user_id="user-2",
                user_name="user2",
                email="user2@example.com",
                display_name="User Two",
                active=False,
            ),
        ]
        mock_collector.collect_groups.return_value = [
            GroupData(
                group_id="group-1",
                display_name="Test Group",
                description="A test group",
                members=["user-1"],
            )
        ]
        mock_collector.collect_permission_sets.return_value = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPermissionSet",
                description="Test permission set",
            )
        ]
        mock_collector.collect_assignments.return_value = [
            AssignmentData(
                principal_id="user-1",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                account_id="123456789012",
            )
        ]

        backup_data = await backup_diff_manager._collect_current_state()

        assert backup_data.metadata.backup_id == "current"
        assert len(backup_data.users) == 2
        assert len(backup_data.groups) == 1
        assert len(backup_data.permission_sets) == 1
        assert len(backup_data.assignments) == 1
        assert backup_data.users[0].user_name == "user1"
        assert backup_data.groups[0].display_name == "Test Group"

    @pytest.mark.asyncio
    async def test_compare_backups_current_vs_backup(
        self, backup_diff_manager, mock_collector, sample_backup_data
    ):
        """Test comparing current state against a backup."""
        # Mock current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-current",
                user_name="current_user",
                email="current@example.com",
                display_name="Current User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        # Mock backup resolution and loading
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            return_value=sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup = AsyncMock(
            return_value=sample_backup_data
        )

        # Mock diff engine
        mock_diff_result = DiffResult(
            source_backup_id=sample_backup_data.metadata.backup_id,
            target_backup_id="current",
            source_timestamp=sample_backup_data.metadata.timestamp,
            target_timestamp=datetime.now(),
            user_diff=ResourceDiff(resource_type="users"),
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=1, changes_by_type={}, changes_by_action={}),
        )
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=mock_diff_result)

        result = await backup_diff_manager.compare_backups("7d", "current")

        assert result is not None
        assert result.target_backup_id == "current"
        backup_diff_manager.diff_engine.compute_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_backups_current_as_source(
        self, backup_diff_manager, mock_collector, sample_backup_data
    ):
        """Test using current state as source in comparison."""
        # Mock current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-current",
                user_name="current_user",
                email="current@example.com",
                display_name="Current User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        # Mock backup resolution and loading
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            return_value=sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup = AsyncMock(
            return_value=sample_backup_data
        )

        # Mock diff engine
        mock_diff_result = DiffResult(
            source_backup_id="current",
            target_backup_id=sample_backup_data.metadata.backup_id,
            source_timestamp=datetime.now(),
            target_timestamp=sample_backup_data.metadata.timestamp,
            user_diff=ResourceDiff(resource_type="users"),
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=1, changes_by_type={}, changes_by_action={}),
        )
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=mock_diff_result)

        result = await backup_diff_manager.compare_backups("current", "7d")

        assert result is not None
        assert result.source_backup_id == "current"
        backup_diff_manager.diff_engine.compute_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_backups_current_vs_current(self, backup_diff_manager, mock_collector):
        """Test comparing current state against itself (edge case)."""
        # Mock current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-current",
                user_name="current_user",
                email="current@example.com",
                display_name="Current User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        # Mock diff engine to return no changes
        mock_diff_result = DiffResult(
            source_backup_id="current",
            target_backup_id="current",
            source_timestamp=datetime.now(),
            target_timestamp=datetime.now(),
            user_diff=ResourceDiff(resource_type="users"),
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=0, changes_by_type={}, changes_by_action={}),
        )
        backup_diff_manager.diff_engine.compute_diff = MagicMock(return_value=mock_diff_result)

        result = await backup_diff_manager.compare_backups("current", "current")

        assert result is not None
        assert result.source_backup_id == "current"
        assert result.target_backup_id == "current"
        assert not result.has_changes
        backup_diff_manager.diff_engine.compute_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_output_json(self, backup_diff_manager, sample_diff_result):
        """Test saving output in JSON format."""
        backup_diff_manager.output_formatter.format_json = MagicMock(
            return_value='{"test": "json"}'
        )

        with patch("tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "temp_file.tmp"
            mock_temp_file.return_value.__enter__.return_value.write = MagicMock()

            with patch("os.path.dirname") as mock_dirname:
                mock_dirname.return_value = "/tmp"
                with patch("os.path.abspath") as mock_abspath:
                    mock_abspath.return_value = "/tmp/output.json"
                    with patch("os.rename") as mock_rename:
                        mock_rename.return_value = None

                        await backup_diff_manager._save_output(
                            sample_diff_result, "json", "output.json"
                        )

                        # Verify temp file was created and written to
                        mock_temp_file.assert_called_once()
                        mock_temp_file.return_value.__enter__.return_value.write.assert_called_once_with(
                            '{"test": "json"}'
                        )
                        mock_rename.assert_called_once_with("temp_file.tmp", "output.json")

    @pytest.mark.asyncio
    async def test_save_output_csv(self, backup_diff_manager, sample_diff_result):
        """Test saving output in CSV format."""
        backup_diff_manager.output_formatter.format_csv = MagicMock(
            return_value="test,csv\ndata,here"
        )

        with patch("tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "temp_file.tmp"
            mock_temp_file.return_value.__enter__.return_value.write = MagicMock()

            with patch("os.path.dirname") as mock_dirname:
                mock_dirname.return_value = "/tmp"
                with patch("os.path.abspath") as mock_abspath:
                    mock_abspath.return_value = "/tmp/output.csv"
                    with patch("os.rename") as mock_rename:
                        mock_rename.return_value = None

                        await backup_diff_manager._save_output(
                            sample_diff_result, "csv", "output.csv"
                        )

                        # Verify temp file was created and written to
                        mock_temp_file.assert_called_once()
                        mock_temp_file.return_value.__enter__.return_value.write.assert_called_once_with(
                            "test,csv\ndata,here"
                        )
                        mock_rename.assert_called_once_with("temp_file.tmp", "output.csv")

    @pytest.mark.asyncio
    async def test_save_output_html(self, backup_diff_manager, sample_diff_result):
        """Test saving output in HTML format."""
        backup_diff_manager.output_formatter.format_html = MagicMock(
            return_value="<html><body>Test HTML</body></html>"
        )

        with patch("tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "temp_file.tmp"
            mock_temp_file.return_value.__enter__.return_value.write = MagicMock()

            with patch("os.path.dirname") as mock_dirname:
                mock_dirname.return_value = "/tmp"
                with patch("os.path.abspath") as mock_abspath:
                    mock_abspath.return_value = "/tmp/output.html"
                    with patch("os.rename") as mock_rename:
                        mock_rename.return_value = None

                        await backup_diff_manager._save_output(
                            sample_diff_result, "html", "output.html"
                        )

                        # Verify temp file was created and written to
                        mock_temp_file.assert_called_once()
                        mock_temp_file.return_value.__enter__.return_value.write.assert_called_once_with(
                            "<html><body>Test HTML</body></html>"
                        )
                        mock_rename.assert_called_once_with("temp_file.tmp", "output.html")

    @pytest.mark.asyncio
    async def test_save_output_console(self, backup_diff_manager, sample_diff_result):
        """Test saving output in console format."""
        backup_diff_manager.output_formatter.format_console = MagicMock(
            return_value="Console output text"
        )

        with patch("tempfile.NamedTemporaryFile") as mock_temp_file:
            mock_temp_file.return_value.__enter__.return_value.name = "temp_file.tmp"
            mock_temp_file.return_value.__enter__.return_value.write = MagicMock()

            with patch("os.path.dirname") as mock_dirname:
                mock_dirname.return_value = "/tmp"
                with patch("os.path.abspath") as mock_abspath:
                    mock_abspath.return_value = "/tmp/output.txt"
                    with patch("os.rename") as mock_rename:
                        mock_rename.return_value = None

                        await backup_diff_manager._save_output(
                            sample_diff_result, "console", "output.txt"
                        )

                        # Verify temp file was created and written to
                        mock_temp_file.assert_called_once()
                        mock_temp_file.return_value.__enter__.return_value.write.assert_called_once_with(
                            "Console output text"
                        )
                        mock_rename.assert_called_once_with("temp_file.tmp", "output.txt")

    @pytest.mark.asyncio
    async def test_save_output_unsupported_format(self, backup_diff_manager, sample_diff_result):
        """Test saving output with unsupported format."""
        with pytest.raises(OutputFormatError, match="Unsupported output format"):
            await backup_diff_manager._save_output(sample_diff_result, "unsupported", "output.txt")

    @pytest.mark.asyncio
    async def test_save_output_file_error(self, backup_diff_manager, sample_diff_result):
        """Test saving output when file writing fails."""
        backup_diff_manager.output_formatter.format_json = MagicMock(
            return_value='{"test": "json"}'
        )

        with patch("tempfile.NamedTemporaryFile", side_effect=OSError("Permission denied")):
            with pytest.raises(OutputFormatError, match="Failed to write to output.json"):
                await backup_diff_manager._save_output(sample_diff_result, "json", "output.json")

    def test_get_available_backups(self, backup_diff_manager, sample_backup_metadata):
        """Test getting available backups."""
        backup_diff_manager.metadata_index.list_backups.return_value = [sample_backup_metadata]

        backups = backup_diff_manager.get_available_backups()

        assert len(backups) == 1
        assert backups[0] == sample_backup_metadata

    def test_get_available_backups_error(self, backup_diff_manager):
        """Test getting available backups when listing fails."""
        backup_diff_manager.metadata_index.list_backups.side_effect = Exception("Index error")

        backups = backup_diff_manager.get_available_backups()

        assert backups == []

    @pytest.mark.asyncio
    async def test_validate_backup_compatibility_success(
        self, backup_diff_manager, sample_backup_metadata
    ):
        """Test successful backup compatibility validation."""
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = sample_backup_metadata

        result = await backup_diff_manager.validate_backup_compatibility("backup-1", "backup-2")

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_backup_compatibility_missing_metadata(self, backup_diff_manager):
        """Test backup compatibility validation with missing metadata."""
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = None

        result = await backup_diff_manager.validate_backup_compatibility("backup-1", "backup-2")

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_backup_compatibility_different_instances(
        self, backup_diff_manager, sample_backup_metadata
    ):
        """Test backup compatibility validation with different instances."""
        metadata1 = sample_backup_metadata
        from src.awsideman.backup_restore.models import EncryptionMetadata, RetentionPolicy

        metadata2 = BackupMetadata(
            backup_id="backup-2",
            timestamp=datetime(2025, 1, 16, 10, 30, 0),
            instance_arn="arn:aws:sso:::instance/different-instance",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=False),
        )

        backup_diff_manager.metadata_index.get_backup_metadata.side_effect = [
            metadata1,
            metadata2,
        ]

        result = await backup_diff_manager.validate_backup_compatibility("backup-1", "backup-2")

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_backup_compatibility_error(self, backup_diff_manager):
        """Test backup compatibility validation with error."""
        backup_diff_manager.metadata_index.get_backup_metadata.side_effect = Exception(
            "Metadata error"
        )

        result = await backup_diff_manager.validate_backup_compatibility("backup-1", "backup-2")

        assert result is False


class TestBackupDiffManagerEdgeCases:
    """Test edge cases and error scenarios for BackupDiffManager."""

    @pytest.mark.asyncio
    async def test_resolve_and_load_backup_current_spec(self, backup_diff_manager, mock_collector):
        """Test resolving 'current' backup specification."""
        # Mock collector responses
        mock_collector.collect_users.return_value = []
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        backup_data = await backup_diff_manager._resolve_and_load_backup("current")

        assert backup_data.metadata.backup_id == "current"

    @pytest.mark.asyncio
    async def test_resolve_and_load_backup_exception_handling(
        self, backup_diff_manager, sample_backup_metadata
    ):
        """Test exception handling in backup resolution and loading."""
        backup_diff_manager.metadata_index.get_backup_metadata.return_value = sample_backup_metadata
        backup_diff_manager.storage_engine.retrieve_backup.side_effect = Exception("Storage error")

        with pytest.raises(ComparisonError):
            await backup_diff_manager._resolve_and_load_backup("backup-1")

    @pytest.mark.asyncio
    async def test_compare_backups_diff_engine_failure(
        self, backup_diff_manager, sample_backup_data
    ):
        """Test backup comparison when diff engine fails."""
        # Mock successful backup loading
        backup_diff_manager.backup_resolver.resolve_backup_from_spec = MagicMock(
            return_value=sample_backup_data.metadata
        )
        backup_diff_manager.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Mock diff engine failure
        backup_diff_manager.diff_engine.compute_diff = MagicMock(
            side_effect=Exception("Diff computation failed")
        )

        with pytest.raises(ComparisonError):
            await backup_diff_manager.compare_backups("7d", "current")
