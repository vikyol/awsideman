"""
Core diff engine for backup comparison operations.

This module provides the main DiffEngine class that orchestrates all resource
comparators to identify differences between two backup states.
"""

from .comparators import (
    AssignmentComparator,
    GroupComparator,
    PermissionSetComparator,
    UserComparator,
)
from .diff_models import DiffResult, DiffSummary, ResourceDiff
from .models import BackupData


class DiffEngine:
    """
    Core engine for computing differences between backup data.

    This class orchestrates all resource comparators to provide a comprehensive
    diff between two backup states, handling missing or empty resource collections
    gracefully.
    """

    def __init__(self) -> None:
        """Initialize the diff engine with all resource comparators."""
        self.comparators = {
            "users": UserComparator(),
            "groups": GroupComparator(),
            "permission_sets": PermissionSetComparator(),
            "assignments": AssignmentComparator(),
        }

    def compute_diff(self, source_backup: BackupData, target_backup: BackupData) -> DiffResult:
        """
        Compute comprehensive differences between two backups.

        Args:
            source_backup: The source backup data (baseline)
            target_backup: The target backup data (comparison point)

        Returns:
            DiffResult containing all detected changes between the backups

        Raises:
            ValueError: If backup data is invalid or missing required fields
        """
        if not source_backup or not target_backup:
            raise ValueError("Both source and target backup data are required")

        if not source_backup.metadata or not target_backup.metadata:
            raise ValueError("Backup metadata is required for both backups")

        # Compare each resource type using appropriate comparators
        user_diff = self._compare_users(source_backup, target_backup)
        group_diff = self._compare_groups(source_backup, target_backup)
        permission_set_diff = self._compare_permission_sets(source_backup, target_backup)
        assignment_diff = self._compare_assignments(source_backup, target_backup)

        # Generate summary
        summary = self._generate_summary(
            user_diff, group_diff, permission_set_diff, assignment_diff
        )

        return DiffResult(
            source_backup_id=source_backup.metadata.backup_id,
            target_backup_id=target_backup.metadata.backup_id,
            source_timestamp=source_backup.metadata.timestamp,
            target_timestamp=target_backup.metadata.timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

    def _compare_users(self, source_backup: BackupData, target_backup: BackupData) -> ResourceDiff:
        """
        Compare user resources between backups.

        Args:
            source_backup: Source backup data
            target_backup: Target backup data

        Returns:
            ResourceDiff for users
        """
        source_users = source_backup.users if source_backup.users else []
        target_users = target_backup.users if target_backup.users else []

        return self.comparators["users"].compare(source_users, target_users)

    def _compare_groups(self, source_backup: BackupData, target_backup: BackupData) -> ResourceDiff:
        """
        Compare group resources between backups.

        Args:
            source_backup: Source backup data
            target_backup: Target backup data

        Returns:
            ResourceDiff for groups
        """
        source_groups = source_backup.groups if source_backup.groups else []
        target_groups = target_backup.groups if target_backup.groups else []

        return self.comparators["groups"].compare(source_groups, target_groups)

    def _compare_permission_sets(
        self, source_backup: BackupData, target_backup: BackupData
    ) -> ResourceDiff:
        """
        Compare permission set resources between backups.

        Args:
            source_backup: Source backup data
            target_backup: Target backup data

        Returns:
            ResourceDiff for permission sets
        """
        source_permission_sets = (
            source_backup.permission_sets if source_backup.permission_sets else []
        )
        target_permission_sets = (
            target_backup.permission_sets if target_backup.permission_sets else []
        )

        return self.comparators["permission_sets"].compare(
            source_permission_sets, target_permission_sets
        )

    def _compare_assignments(
        self, source_backup: BackupData, target_backup: BackupData
    ) -> ResourceDiff:
        """
        Compare assignment resources between backups.

        Args:
            source_backup: Source backup data
            target_backup: Target backup data

        Returns:
            ResourceDiff for assignments
        """
        source_assignments = source_backup.assignments if source_backup.assignments else []
        target_assignments = target_backup.assignments if target_backup.assignments else []

        return self.comparators["assignments"].compare(source_assignments, target_assignments)

    def _generate_summary(
        self,
        user_diff: ResourceDiff,
        group_diff: ResourceDiff,
        permission_set_diff: ResourceDiff,
        assignment_diff: ResourceDiff,
    ) -> DiffSummary:
        """
        Generate a summary of all changes across resource types.

        Args:
            user_diff: User resource differences
            group_diff: Group resource differences
            permission_set_diff: Permission set resource differences
            assignment_diff: Assignment resource differences

        Returns:
            DiffSummary with aggregated statistics
        """
        total_changes = (
            user_diff.total_changes
            + group_diff.total_changes
            + permission_set_diff.total_changes
            + assignment_diff.total_changes
        )

        changes_by_type = {
            "users": user_diff.total_changes,
            "groups": group_diff.total_changes,
            "permission_sets": permission_set_diff.total_changes,
            "assignments": assignment_diff.total_changes,
        }

        changes_by_action = {
            "created": (
                len(user_diff.created)
                + len(group_diff.created)
                + len(permission_set_diff.created)
                + len(assignment_diff.created)
            ),
            "deleted": (
                len(user_diff.deleted)
                + len(group_diff.deleted)
                + len(permission_set_diff.deleted)
                + len(assignment_diff.deleted)
            ),
            "modified": (
                len(user_diff.modified)
                + len(group_diff.modified)
                + len(permission_set_diff.modified)
                + len(assignment_diff.modified)
            ),
        }

        return DiffSummary(
            total_changes=total_changes,
            changes_by_type=changes_by_type,
            changes_by_action=changes_by_action,
        )
