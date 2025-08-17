"""
Filter engine for permission assignment filtering in AWS Identity Center.

This module provides functionality to filter permission assignments based on various criteria
including permission set names, account IDs, and combinable include/exclude logic.
"""

import logging
from typing import List

from .models import CopyFilters, PermissionAssignment, ValidationResult, ValidationResultType

logger = logging.getLogger(__name__)


class FilterEngine:
    """
    Provides flexible filtering capabilities for permission assignments.

    This class supports:
    - Permission set name inclusion/exclusion
    - AWS account ID inclusion/exclusion
    - Combinable filters with AND logic
    - Validation of filter criteria
    """

    def __init__(self):
        """Initialize the FilterEngine."""
        pass

    def apply_filters(
        self, assignments: List[PermissionAssignment], filters: CopyFilters
    ) -> List[PermissionAssignment]:
        """
        Apply filters to a list of permission assignments.

        Args:
            assignments: List of permission assignments to filter
            filters: Filter criteria to apply

        Returns:
            Filtered list of permission assignments
        """
        if not filters or not self._has_active_filters(filters):
            logger.debug("No active filters, returning all assignments")
            return assignments

        # Validate filters before applying
        validation = self.validate_filters(filters)
        if validation.has_errors:
            logger.error(f"Invalid filters: {validation.messages}")
            return []

        logger.info(f"Applying filters to {len(assignments)} assignments")

        filtered_assignments = []
        for assignment in assignments:
            if self._assignment_matches_filters(assignment, filters):
                filtered_assignments.append(assignment)

        logger.info(f"Filtered to {len(filtered_assignments)} assignments")
        return filtered_assignments

    def validate_filters(self, filters: CopyFilters) -> ValidationResult:
        """
        Validate filter criteria for consistency and correctness.

        Args:
            filters: Filter criteria to validate

        Returns:
            ValidationResult indicating success or failure with details
        """
        errors = []
        warnings = []

        if not filters:
            warnings.append("No filters specified")
            return ValidationResult(ValidationResultType.WARNING, warnings)

        # Check for overlapping account filters
        if filters.include_accounts and filters.exclude_accounts:
            overlap = set(filters.include_accounts) & set(filters.exclude_accounts)
            if overlap:
                errors.append(f"Accounts cannot be both included and excluded: {list(overlap)}")

        # Validate permission set name filters (exclude only)
        if filters.exclude_permission_sets:
            for name in filters.exclude_permission_sets:
                if not name or not name.strip():
                    errors.append("Exclude permission set names cannot be empty")

        # Validate account ID filters
        if filters.include_accounts:
            for account_id in filters.include_accounts:
                if not self._is_valid_account_id(account_id):
                    errors.append(f"Invalid account ID in include filter: {account_id}")

        if filters.exclude_accounts:
            for account_id in filters.exclude_accounts:
                if not self._is_valid_account_id(account_id):
                    errors.append(f"Invalid account ID in exclude filter: {account_id}")

        # Check if any filters are specified
        if not self._has_active_filters(filters):
            warnings.append("No active filters specified - all assignments will be processed")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        elif warnings:
            return ValidationResult(ValidationResultType.WARNING, warnings)

        return ValidationResult(ValidationResultType.SUCCESS, [])

    def get_filter_summary(self, filters: CopyFilters) -> str:
        """
        Get a human-readable summary of the active filters.

        Args:
            filters: Filter criteria to summarize

        Returns:
            String summary of active filters
        """
        if not filters or not self._has_active_filters(filters):
            return "No filters applied"

        summary_parts = []

        if filters.exclude_permission_sets:
            summary_parts.append(
                f"Exclude permission sets: {', '.join(filters.exclude_permission_sets)}"
            )

        if filters.include_accounts:
            summary_parts.append(f"Include accounts: {', '.join(filters.include_accounts)}")

        if filters.exclude_accounts:
            summary_parts.append(f"Exclude accounts: {', '.join(filters.exclude_accounts)}")

        return "; ".join(summary_parts)

    def get_filter_stats(self, original_count: int, filtered_count: int) -> dict:
        """
        Get statistics about the filtering operation.

        Args:
            original_count: Number of assignments before filtering
            filtered_count: Number of assignments after filtering

        Returns:
            Dictionary with filtering statistics
        """
        excluded_count = original_count - filtered_count
        exclusion_rate = (excluded_count / original_count * 100) if original_count > 0 else 0

        return {
            "original_count": original_count,
            "filtered_count": filtered_count,
            "excluded_count": excluded_count,
            "exclusion_rate_percent": round(exclusion_rate, 2),
        }

    def _assignment_matches_filters(
        self, assignment: PermissionAssignment, filters: CopyFilters
    ) -> bool:
        """
        Check if an assignment matches the filter criteria.

        Args:
            assignment: Permission assignment to check
            filters: Filter criteria to apply

        Returns:
            True if assignment matches filters, False otherwise
        """
        # Check permission set name filters
        if not self._permission_set_matches_filters(assignment.permission_set_name, filters):
            return False

        # Check account ID filters
        if not self._account_matches_filters(assignment.account_id, filters):
            return False

        return True

    def _permission_set_matches_filters(
        self, permission_set_name: str, filters: CopyFilters
    ) -> bool:
        """
        Check if a permission set name matches the permission set filters.

        Args:
            permission_set_name: Name of the permission set to check
            filters: Filter criteria to apply

        Returns:
            True if permission set matches filters, False otherwise
        """
        # If exclude filter is specified, permission set must not be in the list
        if filters.exclude_permission_sets:
            if permission_set_name in filters.exclude_permission_sets:
                return False

        return True

    def _account_matches_filters(self, account_id: str, filters: CopyFilters) -> bool:
        """
        Check if an account ID matches the account filters.

        Args:
            account_id: Account ID to check
            filters: Filter criteria to apply

        Returns:
            True if account matches filters, False otherwise
        """
        # If include filter is specified, account must be in the list
        if filters.include_accounts:
            if account_id not in filters.include_accounts:
                return False

        # If exclude filter is specified, account must not be in the list
        if filters.exclude_accounts:
            if account_id in filters.exclude_accounts:
                return False

        return True

    def _has_active_filters(self, filters: CopyFilters) -> bool:
        """
        Check if any filters are actively specified.

        Args:
            filters: Filter criteria to check

        Returns:
            True if any filters are specified, False otherwise
        """
        if not filters:
            return False

        return any(
            [filters.exclude_permission_sets, filters.include_accounts, filters.exclude_accounts]
        )

    def _is_valid_account_id(self, account_id: str) -> bool:
        """
        Validate that an account ID is in the correct format.

        Args:
            account_id: Account ID to validate

        Returns:
            True if account ID is valid, False otherwise
        """
        if not account_id or not account_id.strip():
            return False

        # AWS account IDs are 12-digit numbers
        return account_id.isdigit() and len(account_id) == 12
