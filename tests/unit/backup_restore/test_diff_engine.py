"""
Unit tests for the DiffEngine class.

Tests the core diff engine functionality including orchestration of resource
comparators, handling of missing/empty collections, and summary generation.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.awsideman.backup_restore.diff_engine import DiffEngine
from src.awsideman.backup_restore.diff_models import (
    ChangeType,
    DiffResult,
    ResourceChange,
    ResourceDiff,
)
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


class TestDiffEngine:
    """Test cases for the DiffEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.diff_engine = DiffEngine()

        # Create test metadata
        self.source_metadata = BackupMetadata(
            backup_id="source-backup-123",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        self.target_metadata = BackupMetadata(
            backup_id="target-backup-456",
            timestamp=datetime(2025, 1, 2, 12, 0, 0),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

    def test_init(self):
        """Test DiffEngine initialization."""
        engine = DiffEngine()

        assert "users" in engine.comparators
        assert "groups" in engine.comparators
        assert "permission_sets" in engine.comparators
        assert "assignments" in engine.comparators
        assert len(engine.comparators) == 4

    def test_compute_diff_with_empty_backups(self):
        """Test computing diff with empty backup data."""
        source_backup = BackupData(metadata=self.source_metadata)
        target_backup = BackupData(metadata=self.target_metadata)

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        assert isinstance(result, DiffResult)
        assert result.source_backup_id == "source-backup-123"
        assert result.target_backup_id == "target-backup-456"
        assert result.source_timestamp == datetime(2025, 1, 1, 12, 0, 0)
        assert result.target_timestamp == datetime(2025, 1, 2, 12, 0, 0)

        # All diffs should be empty
        assert result.user_diff.total_changes == 0
        assert result.group_diff.total_changes == 0
        assert result.permission_set_diff.total_changes == 0
        assert result.assignment_diff.total_changes == 0

        # Summary should reflect no changes
        assert result.summary.total_changes == 0
        assert not result.has_changes

    def test_compute_diff_with_none_backup_data(self):
        """Test computing diff with None backup data raises ValueError."""
        source_backup = BackupData(metadata=self.source_metadata)

        with pytest.raises(ValueError, match="Both source and target backup data are required"):
            self.diff_engine.compute_diff(source_backup, None)

        with pytest.raises(ValueError, match="Both source and target backup data are required"):
            self.diff_engine.compute_diff(None, source_backup)

    def test_compute_diff_with_missing_metadata(self):
        """Test computing diff with missing metadata raises ValueError."""
        source_backup = BackupData(metadata=self.source_metadata)

        # Create a mock backup with None metadata (bypassing __post_init__)
        target_backup = Mock()
        target_backup.metadata = None

        with pytest.raises(ValueError, match="Backup metadata is required for both backups"):
            self.diff_engine.compute_diff(source_backup, target_backup)

    def test_compute_diff_with_user_changes(self):
        """Test computing diff with user changes."""
        # Create source backup with one user
        source_users = [
            UserData(
                user_id="user-123",
                user_name="john.doe",
                display_name="John Doe",
                email="john.doe@example.com",
            )
        ]
        source_backup = BackupData(metadata=self.source_metadata, users=source_users)

        # Create target backup with modified user and new user
        target_users = [
            UserData(
                user_id="user-123",
                user_name="john.doe",
                display_name="John Smith",  # Changed display name
                email="john.doe@example.com",
            ),
            UserData(
                user_id="user-456",
                user_name="jane.doe",
                display_name="Jane Doe",
                email="jane.doe@example.com",
            ),
        ]
        target_backup = BackupData(metadata=self.target_metadata, users=target_users)

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Should have user changes
        assert result.user_diff.total_changes == 2  # 1 modified, 1 created
        assert len(result.user_diff.created) == 1
        assert len(result.user_diff.modified) == 1
        assert len(result.user_diff.deleted) == 0

        # Summary should reflect changes
        assert result.summary.total_changes == 2
        assert result.summary.changes_by_type["users"] == 2
        assert result.summary.changes_by_action["created"] == 1
        assert result.summary.changes_by_action["modified"] == 1
        assert result.has_changes

    def test_compute_diff_with_group_changes(self):
        """Test computing diff with group changes."""
        # Create source backup with one group
        source_groups = [
            GroupData(
                group_id="group-123",
                display_name="Developers",
                description="Development team",
                members=["user-123"],
            )
        ]
        source_backup = BackupData(metadata=self.source_metadata, groups=source_groups)

        # Create target backup with no groups (deleted)
        target_backup = BackupData(metadata=self.target_metadata, groups=[])

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Should have group deletion
        assert result.group_diff.total_changes == 1
        assert len(result.group_diff.deleted) == 1
        assert len(result.group_diff.created) == 0
        assert len(result.group_diff.modified) == 0

        # Summary should reflect changes
        assert result.summary.total_changes == 1
        assert result.summary.changes_by_type["groups"] == 1
        assert result.summary.changes_by_action["deleted"] == 1

    def test_compute_diff_with_permission_set_changes(self):
        """Test computing diff with permission set changes."""
        # Create source backup with one permission set
        source_permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                name="ReadOnlyAccess",
                description="Read-only access",
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            )
        ]
        source_backup = BackupData(
            metadata=self.source_metadata, permission_sets=source_permission_sets
        )

        # Create target backup with modified permission set
        target_permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                name="ReadOnlyAccess",
                description="Updated read-only access",  # Changed description
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            )
        ]
        target_backup = BackupData(
            metadata=self.target_metadata, permission_sets=target_permission_sets
        )

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Should have permission set modification
        assert result.permission_set_diff.total_changes == 1
        assert len(result.permission_set_diff.modified) == 1
        assert len(result.permission_set_diff.created) == 0
        assert len(result.permission_set_diff.deleted) == 0

    def test_compute_diff_with_assignment_changes(self):
        """Test computing diff with assignment changes."""
        # Create source backup with one assignment
        source_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                principal_type="USER",
                principal_id="user-123",
            )
        ]
        source_backup = BackupData(metadata=self.source_metadata, assignments=source_assignments)

        # Create target backup with additional assignment
        target_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                principal_type="USER",
                principal_id="user-123",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                principal_type="GROUP",
                principal_id="group-123",
            ),
        ]
        target_backup = BackupData(metadata=self.target_metadata, assignments=target_assignments)

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Should have assignment creation
        assert result.assignment_diff.total_changes == 1
        assert len(result.assignment_diff.created) == 1
        assert len(result.assignment_diff.modified) == 0
        assert len(result.assignment_diff.deleted) == 0

    def test_compute_diff_with_mixed_changes(self):
        """Test computing diff with changes across all resource types."""
        # Create source backup with various resources
        source_backup = BackupData(
            metadata=self.source_metadata,
            users=[UserData(user_id="user-123", user_name="john.doe", display_name="John Doe")],
            groups=[GroupData(group_id="group-123", display_name="Developers")],
            permission_sets=[
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    name="ReadOnlyAccess",
                )
            ],
            assignments=[
                AssignmentData(
                    account_id="123456789012",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    principal_type="USER",
                    principal_id="user-123",
                )
            ],
        )

        # Create target backup with changes in all resource types
        target_backup = BackupData(
            metadata=self.target_metadata,
            users=[
                UserData(
                    user_id="user-123", user_name="john.doe", display_name="John Smith"
                ),  # Modified
                UserData(
                    user_id="user-456", user_name="jane.doe", display_name="Jane Doe"
                ),  # Created
            ],
            groups=[],  # Deleted group
            permission_sets=[
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    name="ReadOnlyAccess",
                ),
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                    name="PowerUserAccess",
                ),  # Created
            ],
            assignments=[
                AssignmentData(
                    account_id="123456789012",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                    principal_type="USER",
                    principal_id="user-456",
                )  # Different assignment (original deleted, new created)
            ],
        )

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Verify changes across all resource types
        assert result.user_diff.total_changes == 2  # 1 modified, 1 created
        assert result.group_diff.total_changes == 1  # 1 deleted
        assert result.permission_set_diff.total_changes == 1  # 1 created
        assert result.assignment_diff.total_changes == 2  # 1 deleted, 1 created

        # Verify summary
        assert result.summary.total_changes == 6
        assert result.summary.changes_by_type["users"] == 2
        assert result.summary.changes_by_type["groups"] == 1
        assert result.summary.changes_by_type["permission_sets"] == 1
        assert result.summary.changes_by_type["assignments"] == 2

        assert result.summary.changes_by_action["created"] == 3
        assert result.summary.changes_by_action["deleted"] == 2
        assert result.summary.changes_by_action["modified"] == 1

        assert result.has_changes

    def test_compute_diff_handles_none_resource_lists(self):
        """Test that diff engine handles None resource lists gracefully."""
        # Create mock backups with None resource lists (bypassing BackupData validation)
        source_backup = Mock()
        source_backup.metadata = self.source_metadata
        source_backup.users = None
        source_backup.groups = None
        source_backup.permission_sets = None
        source_backup.assignments = None

        target_backup = Mock()
        target_backup.metadata = self.target_metadata
        target_backup.users = [UserData(user_id="user-123", user_name="john.doe")]
        target_backup.groups = None
        target_backup.permission_sets = None
        target_backup.assignments = None

        result = self.diff_engine.compute_diff(source_backup, target_backup)

        # Should handle None lists as empty lists
        assert result.user_diff.total_changes == 1  # 1 created user
        assert result.group_diff.total_changes == 0
        assert result.permission_set_diff.total_changes == 0
        assert result.assignment_diff.total_changes == 0

        assert result.summary.total_changes == 1

    @patch("src.awsideman.backup_restore.diff_engine.UserComparator")
    @patch("src.awsideman.backup_restore.diff_engine.GroupComparator")
    @patch("src.awsideman.backup_restore.diff_engine.PermissionSetComparator")
    @patch("src.awsideman.backup_restore.diff_engine.AssignmentComparator")
    def test_compute_diff_uses_all_comparators(
        self, mock_assignment_comp, mock_ps_comp, mock_group_comp, mock_user_comp
    ):
        """Test that compute_diff uses all comparators."""
        # Set up mock comparators
        mock_user_comp.return_value.compare.return_value = ResourceDiff("users")
        mock_group_comp.return_value.compare.return_value = ResourceDiff("groups")
        mock_ps_comp.return_value.compare.return_value = ResourceDiff("permission_sets")
        mock_assignment_comp.return_value.compare.return_value = ResourceDiff("assignments")

        # Create test backups
        source_backup = BackupData(metadata=self.source_metadata)
        target_backup = BackupData(metadata=self.target_metadata)

        # Create new engine to use mocked comparators
        engine = DiffEngine()
        result = engine.compute_diff(source_backup, target_backup)

        # Verify all comparators were called
        mock_user_comp.return_value.compare.assert_called_once()
        mock_group_comp.return_value.compare.assert_called_once()
        mock_ps_comp.return_value.compare.assert_called_once()
        mock_assignment_comp.return_value.compare.assert_called_once()

        assert isinstance(result, DiffResult)

    def test_generate_summary_with_no_changes(self):
        """Test summary generation with no changes."""
        user_diff = ResourceDiff("users")
        group_diff = ResourceDiff("groups")
        permission_set_diff = ResourceDiff("permission_sets")
        assignment_diff = ResourceDiff("assignments")

        summary = self.diff_engine._generate_summary(
            user_diff, group_diff, permission_set_diff, assignment_diff
        )

        assert summary.total_changes == 0
        assert all(count == 0 for count in summary.changes_by_type.values())
        assert all(count == 0 for count in summary.changes_by_action.values())

    def test_generate_summary_with_changes(self):
        """Test summary generation with various changes."""
        # Create diffs with changes
        user_diff = ResourceDiff("users")
        user_diff.created = [
            ResourceChange(ChangeType.CREATED, "users", "user-1"),
            ResourceChange(ChangeType.CREATED, "users", "user-2"),
        ]
        user_diff.modified = [ResourceChange(ChangeType.MODIFIED, "users", "user-3")]

        group_diff = ResourceDiff("groups")
        group_diff.deleted = [ResourceChange(ChangeType.DELETED, "groups", "group-1")]

        permission_set_diff = ResourceDiff("permission_sets")
        assignment_diff = ResourceDiff("assignments")

        summary = self.diff_engine._generate_summary(
            user_diff, group_diff, permission_set_diff, assignment_diff
        )

        assert summary.total_changes == 4
        assert summary.changes_by_type["users"] == 3
        assert summary.changes_by_type["groups"] == 1
        assert summary.changes_by_type["permission_sets"] == 0
        assert summary.changes_by_type["assignments"] == 0

        assert summary.changes_by_action["created"] == 2
        assert summary.changes_by_action["modified"] == 1
        assert summary.changes_by_action["deleted"] == 1
