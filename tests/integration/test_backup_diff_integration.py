"""
Integration tests for backup diff functionality.

This module tests the complete backup diff workflow including storage engine
integration, metadata index operations, and end-to-end diff operations.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.awsideman.backup_restore.backends import FileSystemStorageBackend
from src.awsideman.backup_restore.backup_diff_manager import BackupDiffManager, ComparisonError
from src.awsideman.backup_restore.collector import IdentityCenterCollector
from src.awsideman.backup_restore.local_metadata_index import LocalMetadataIndex
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RetentionPolicy,
    UserData,
)
from src.awsideman.backup_restore.storage import StorageEngine


@pytest.fixture
def temp_storage_dir():
    """Temporary directory for storage testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def temp_metadata_dir():
    """Temporary directory for metadata index testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def filesystem_backend(temp_storage_dir):
    """Filesystem storage backend for testing."""
    return FileSystemStorageBackend(base_path=temp_storage_dir)


@pytest.fixture
def storage_engine(filesystem_backend):
    """Storage engine with filesystem backend."""
    return StorageEngine(backend=filesystem_backend)


@pytest.fixture
def metadata_index(temp_metadata_dir):
    """Local metadata index for testing."""
    return LocalMetadataIndex(index_path=temp_metadata_dir)


@pytest.fixture
def mock_collector():
    """Mock collector for current state testing."""
    collector = AsyncMock(spec=IdentityCenterCollector)
    return collector


@pytest.fixture
def sample_backup_data_1():
    """First sample backup data for comparison."""
    metadata = BackupMetadata(
        backup_id="backup-2025-01-14",
        timestamp=datetime(2025, 1, 14, 10, 0, 0),
        instance_arn="arn:aws:sso:::instance/test-instance",
        backup_type=BackupType.FULL,
        version="1.0.0",
        source_account="123456789012",
        source_region="us-east-1",
        retention_policy=RetentionPolicy(),
        encryption_info=EncryptionMetadata(encrypted=False),
    )

    return BackupData(
        metadata=metadata,
        users=[
            UserData(
                user_id="user-1",
                user_name="alice",
                email="alice@example.com",
                display_name="Alice Smith",
            ),
            UserData(
                user_id="user-2",
                user_name="bob",
                email="bob@example.com",
                display_name="Bob Jones",
            ),
        ],
        groups=[
            GroupData(
                group_id="group-1",
                display_name="Developers",
                description="Development team",
            ),
        ],
        permission_sets=[
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ps-dev",
                name="DeveloperAccess",
                description="Developer permissions",
            ),
        ],
        assignments=[
            AssignmentData(
                principal_id="user-1",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-dev",
                account_id="123456789012",
            ),
        ],
    )


@pytest.fixture
def sample_backup_data_2():
    """Second sample backup data for comparison."""
    metadata = BackupMetadata(
        backup_id="backup-2025-01-15",
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        instance_arn="arn:aws:sso:::instance/test-instance",
        backup_type=BackupType.FULL,
        version="1.0.0",
        source_account="123456789012",
        source_region="us-east-1",
        retention_policy=RetentionPolicy(),
        encryption_info=EncryptionMetadata(encrypted=False),
    )

    return BackupData(
        metadata=metadata,
        users=[
            UserData(
                user_id="user-1",
                user_name="alice",
                email="alice@example.com",
                display_name="Alice Smith",
            ),
            UserData(
                user_id="user-2",
                user_name="bob",
                email="bob@newcompany.com",  # Changed email
                display_name="Bob Jones",
            ),
            UserData(
                user_id="user-3",
                user_name="charlie",
                email="charlie@example.com",
                display_name="Charlie Brown",
            ),
        ],
        groups=[
            GroupData(
                group_id="group-1",
                display_name="Developers",
                description="Development team",
            ),
            GroupData(
                group_id="group-2",
                display_name="Admins",
                description="Administrator group",
            ),
        ],
        permission_sets=[
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ps-dev",
                name="DeveloperAccess",
                description="Developer permissions",
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ps-admin",
                name="AdminAccess",
                description="Administrator permissions",
            ),
        ],
        assignments=[
            AssignmentData(
                principal_id="user-1",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-dev",
                account_id="123456789012",
            ),
            AssignmentData(
                principal_id="user-3",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-admin",
                account_id="123456789012",
            ),
        ],
    )


@pytest.fixture
async def populated_storage(
    storage_engine, metadata_index, sample_backup_data_1, sample_backup_data_2
):
    """Storage engine populated with test backup data."""
    # Store first backup
    backup_id_1 = await storage_engine.store_backup(sample_backup_data_1)
    metadata_index.add_backup_metadata(
        backup_id_1, sample_backup_data_1.metadata, "filesystem", "test-storage"
    )

    # Store second backup
    backup_id_2 = await storage_engine.store_backup(sample_backup_data_2)
    metadata_index.add_backup_metadata(
        backup_id_2, sample_backup_data_2.metadata, "filesystem", "test-storage"
    )

    return storage_engine, metadata_index, [backup_id_1, backup_id_2]


class TestBackupDiffIntegration:
    """Integration tests for backup diff functionality."""

    @pytest.mark.asyncio
    async def test_complete_diff_workflow(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test complete backup diff workflow from storage to output."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Perform comparison
        result = await diff_manager.compare_backups(
            backup_ids[0],  # First backup
            backup_ids[1],  # Second backup
        )

        # Verify diff results
        assert result is not None
        assert result.source_backup_id == backup_ids[0]
        assert result.target_backup_id == backup_ids[1]
        assert result.has_changes

        # Check specific changes
        assert result.user_diff.total_changes > 0  # User email changed + new user
        assert result.group_diff.total_changes > 0  # New group added
        assert result.permission_set_diff.total_changes > 0  # New permission set
        assert result.assignment_diff.total_changes > 0  # New assignment

    @pytest.mark.asyncio
    async def test_diff_with_current_state(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test diff comparison with current state."""
        storage_engine, metadata_index, backup_ids = populated_storage

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

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Perform comparison with current state
        result = await diff_manager.compare_backups(
            backup_ids[0],  # Backup
            "current",  # Current state
        )

        # Verify results
        assert result is not None
        assert result.source_backup_id == backup_ids[0]
        assert result.target_backup_id == "current"
        assert result.has_changes

    @pytest.mark.asyncio
    async def test_diff_current_state_comprehensive(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test comprehensive current state comparison with various resource types."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Mock comprehensive current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-current-1",
                user_name="current_user_1",
                email="current1@example.com",
                display_name="Current User 1",
                active=True,
            ),
            UserData(
                user_id="user-current-2",
                user_name="current_user_2",
                email="current2@example.com",
                display_name="Current User 2",
                active=False,
            ),
        ]
        mock_collector.collect_groups.return_value = [
            GroupData(
                group_id="group-current-1",
                display_name="Current Group",
                description="A current group",
                members=["user-current-1"],
            )
        ]
        mock_collector.collect_permission_sets.return_value = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-current/ps-current",
                name="CurrentPermissionSet",
                description="Current permission set",
            )
        ]
        mock_collector.collect_assignments.return_value = [
            AssignmentData(
                principal_id="user-current-1",
                principal_type="USER",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-current/ps-current",
                target_id="123456789012",
                target_type="AWS_ACCOUNT",
            )
        ]

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Perform comparison with current state
        result = await diff_manager.compare_backups(
            backup_ids[0],  # Backup
            "current",  # Current state
        )

        # Verify results
        assert result is not None
        assert result.source_backup_id == backup_ids[0]
        assert result.target_backup_id == "current"

        # Verify that all resource types were compared
        assert result.user_diff is not None
        assert result.group_diff is not None
        assert result.permission_set_diff is not None
        assert result.assignment_diff is not None

    @pytest.mark.asyncio
    async def test_diff_current_state_as_source(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test using current state as source in comparison."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Mock current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-source",
                user_name="source_user",
                email="source@example.com",
                display_name="Source User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Perform comparison with current state as source
        result = await diff_manager.compare_backups(
            "current",  # Current state as source
            backup_ids[0],  # Backup as target
        )

        # Verify results
        assert result is not None
        assert result.source_backup_id == "current"
        assert result.target_backup_id == backup_ids[0]

    @pytest.mark.asyncio
    async def test_diff_current_state_collection_failure(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test handling of current state collection failures."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Mock collection failure
        mock_collector.collect_users.side_effect = Exception("AWS API Error")

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Attempt comparison with current state should fail
        with pytest.raises(ComparisonError):
            await diff_manager.compare_backups(
                backup_ids[0],  # Backup
                "current",  # Current state
            )

    @pytest.mark.asyncio
    async def test_diff_current_state_no_collector(
        self,
        populated_storage,
    ):
        """Test current state comparison without collector."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Create diff manager without collector
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=None,  # No collector provided
        )

        # Attempt comparison with current state should fail
        with pytest.raises(ComparisonError, match="no collector provided"):
            await diff_manager.compare_backups(
                backup_ids[0],  # Backup
                "current",  # Current state
            )

    @pytest.mark.asyncio
    async def test_diff_current_state_output_formats(
        self,
        populated_storage,
        mock_collector,
        temp_storage_dir,
    ):
        """Test current state comparison with different output formats."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Mock current state collection
        mock_collector.collect_users.return_value = [
            UserData(
                user_id="user-output-test",
                user_name="output_test_user",
                email="output@example.com",
                display_name="Output Test User",
            )
        ]
        mock_collector.collect_groups.return_value = []
        mock_collector.collect_permission_sets.return_value = []
        mock_collector.collect_assignments.return_value = []

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Test JSON output with current state
        json_file = Path(temp_storage_dir) / "current_diff_output.json"
        await diff_manager.compare_backups(
            backup_ids[0],
            "current",
            output_format="json",
            output_file=str(json_file),
        )

        assert json_file.exists()
        with open(json_file, "r") as f:
            json_data = json.load(f)
            assert json_data["target_backup_id"] == "current"

        # Test HTML output with current state
        html_file = Path(temp_storage_dir) / "current_diff_output.html"
        await diff_manager.compare_backups(
            backup_ids[0],
            "current",
            output_format="html",
            output_file=str(html_file),
        )

        assert html_file.exists()
        html_content = html_file.read_text()
        assert "current" in html_content.lower()

    @pytest.mark.asyncio
    async def test_diff_output_formats(
        self,
        populated_storage,
        mock_collector,
        temp_storage_dir,
    ):
        """Test diff output in different formats."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Test JSON output
        json_file = Path(temp_storage_dir) / "diff_output.json"
        await diff_manager.compare_backups(
            backup_ids[0],
            backup_ids[1],
            output_format="json",
            output_file=str(json_file),
        )

        assert json_file.exists()
        with open(json_file, "r") as f:
            json_data = json.load(f)
            assert "source_backup_id" in json_data
            assert "target_backup_id" in json_data

        # Test CSV output
        csv_file = Path(temp_storage_dir) / "diff_output.csv"
        await diff_manager.compare_backups(
            backup_ids[0],
            backup_ids[1],
            output_format="csv",
            output_file=str(csv_file),
        )

        assert csv_file.exists()
        csv_content = csv_file.read_text()
        assert "Resource Type" in csv_content
        assert "Change Type" in csv_content

        # Test HTML output
        html_file = Path(temp_storage_dir) / "diff_output.html"
        await diff_manager.compare_backups(
            backup_ids[0],
            backup_ids[1],
            output_format="html",
            output_file=str(html_file),
        )

        assert html_file.exists()
        html_content = html_file.read_text()
        assert "<html>" in html_content
        assert "<table>" in html_content

    @pytest.mark.asyncio
    async def test_date_specification_resolution(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test backup resolution using date specifications."""
        storage_engine, metadata_index, backup_ids = populated_storage

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Test with relative date (should find closest backup)
        # Note: This test assumes the backup resolver can find backups by date
        # In a real scenario, we'd need backups with appropriate timestamps

        # Get available backups to verify they exist
        available_backups = diff_manager.get_available_backups()
        assert len(available_backups) == 2

        # Test backup compatibility validation
        is_compatible = await diff_manager.validate_backup_compatibility(
            backup_ids[0], backup_ids[1]
        )
        assert is_compatible is True

    @pytest.mark.asyncio
    async def test_error_handling_integration(
        self,
        storage_engine,
        metadata_index,
        mock_collector,
    ):
        """Test error handling in integration scenarios."""
        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Test with non-existent backup
        with pytest.raises(Exception):  # Should raise BackupNotFoundError or ComparisonError
            await diff_manager.compare_backups("nonexistent-backup-1", "nonexistent-backup-2")

    @pytest.mark.asyncio
    async def test_large_backup_comparison(
        self,
        storage_engine,
        metadata_index,
        mock_collector,
    ):
        """Test comparison of larger backup datasets."""
        # Create larger backup datasets
        large_backup_1 = BackupData(
            metadata=BackupMetadata(
                backup_id="large-backup-1",
                timestamp=datetime(2025, 1, 10, 10, 0, 0),
                instance_arn="arn:aws:sso:::instance/test-instance",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            ),
            users=[
                UserData(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    email=f"user{i}@example.com",
                    display_name=f"User {i}",
                )
                for i in range(100)
            ],
            groups=[
                GroupData(
                    group_id=f"group-{i}",
                    display_name=f"Group {i}",
                    description=f"Test group {i}",
                )
                for i in range(50)
            ],
        )

        large_backup_2 = BackupData(
            metadata=BackupMetadata(
                backup_id="large-backup-2",
                timestamp=datetime(2025, 1, 11, 10, 0, 0),
                instance_arn="arn:aws:sso:::instance/test-instance",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            ),
            users=[
                UserData(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    email=f"user{i}@newdomain.com",  # Changed domain
                    display_name=f"User {i}",
                )
                for i in range(100)
            ],
            groups=[
                GroupData(
                    group_id=f"group-{i}",
                    display_name=f"Group {i}",
                    description=f"Test group {i}",
                )
                for i in range(60)  # Added 10 more groups
            ],
        )

        # Store backups
        backup_id_1 = await storage_engine.store_backup(large_backup_1)
        backup_id_2 = await storage_engine.store_backup(large_backup_2)

        metadata_index.add_backup_metadata(
            backup_id_1, large_backup_1.metadata, "filesystem", "test-storage"
        )
        metadata_index.add_backup_metadata(
            backup_id_2, large_backup_2.metadata, "filesystem", "test-storage"
        )

        # Create diff manager and compare
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        result = await diff_manager.compare_backups(backup_id_1, backup_id_2)

        # Verify results
        assert result is not None
        assert result.has_changes
        assert result.user_diff.total_changes == 100  # All users modified (email changed)
        assert result.group_diff.total_changes == 10  # 10 new groups added

    @pytest.mark.asyncio
    async def test_metadata_index_integration(
        self,
        storage_engine,
        metadata_index,
        sample_backup_data_1,
    ):
        """Test metadata index integration with diff operations."""
        # Store backup
        backup_id = await storage_engine.store_backup(sample_backup_data_1)
        metadata_index.add_backup_metadata(
            backup_id, sample_backup_data_1.metadata, "filesystem", "test-storage"
        )

        # Verify metadata index operations
        stored_metadata = metadata_index.get_backup_metadata(backup_id)
        assert stored_metadata is not None
        assert stored_metadata.backup_id == backup_id

        storage_location = metadata_index.get_storage_location(backup_id)
        assert storage_location is not None
        assert storage_location["backend"] == "filesystem"

        # Test listing backups
        all_backups = metadata_index.list_backups()
        assert len(all_backups) == 1
        assert all_backups[0].backup_id == backup_id

        # Test index stats
        stats = metadata_index.get_index_stats()
        assert stats["total_backups"] == 1
        assert "filesystem" in stats["by_backend"]


class TestBackupDiffPerformance:
    """Performance-related integration tests."""

    @pytest.mark.asyncio
    async def test_concurrent_diff_operations(
        self,
        populated_storage,
        mock_collector,
    ):
        """Test multiple concurrent diff operations."""
        import asyncio

        storage_engine, metadata_index, backup_ids = populated_storage

        # Create multiple diff managers
        diff_managers = [
            BackupDiffManager(
                storage_engine=storage_engine,
                metadata_index=metadata_index,
                collector=mock_collector,
                enable_validation=False,
            )
            for _ in range(3)
        ]

        # Run concurrent comparisons
        tasks = [manager.compare_backups(backup_ids[0], backup_ids[1]) for manager in diff_managers]

        results = await asyncio.gather(*tasks)

        # Verify all results are consistent
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert result.has_changes
            assert result.source_backup_id == backup_ids[0]
            assert result.target_backup_id == backup_ids[1]

    @pytest.mark.asyncio
    async def test_memory_usage_large_diffs(
        self,
        storage_engine,
        metadata_index,
        mock_collector,
    ):
        """Test memory usage with large diff operations."""
        # This test would ideally monitor memory usage
        # For now, we'll just ensure large diffs complete successfully

        # Create very large backup (simplified for testing)
        large_users = [
            UserData(
                user_id=f"user-{i}",
                user_name=f"user{i}",
                email=f"user{i}@example.com",
                display_name=f"User {i}",
            )
            for i in range(1000)
        ]

        large_backup = BackupData(
            metadata=BackupMetadata(
                backup_id="memory-test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/test-instance",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            ),
            users=large_users,
        )

        backup_id = await storage_engine.store_backup(large_backup)
        metadata_index.add_backup_metadata(
            backup_id, large_backup.metadata, "filesystem", "test-storage"
        )

        # Create diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=mock_collector,
            enable_validation=False,
        )

        # Compare with itself (should show no changes)
        result = await diff_manager.compare_backups(backup_id, backup_id)

        assert result is not None
        assert not result.has_changes  # No changes when comparing with itself
