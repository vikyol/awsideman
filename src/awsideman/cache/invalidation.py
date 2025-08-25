"""Cache invalidation engine for the unified cache system.

This module provides intelligent cache invalidation based on operation types
and resource relationships. It ensures that when resources are modified,
all related cached data is properly invalidated to maintain consistency.
"""

import logging
from typing import Dict, List, Optional

from .interfaces import ICacheManager
from .key_builder import CacheKeyBuilder

logger = logging.getLogger(__name__)


class CacheInvalidationEngine:
    """
    Engine for intelligent cache invalidation based on operation types and resource relationships.

    This engine understands the relationships between different AWS Identity Center resources
    and ensures that when one resource is modified, all related cached data is invalidated
    to maintain consistency across the system.
    """

    def __init__(self, cache_manager: ICacheManager):
        """
        Initialize the cache invalidation engine.

        Args:
            cache_manager: Cache manager instance to perform invalidations on
        """
        self.cache_manager = cache_manager
        self.invalidation_rules = self._load_invalidation_rules()

        logger.debug("CacheInvalidationEngine initialized")

    def invalidate_for_operation(
        self,
        operation_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        additional_context: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Invalidate cache based on operation type and resource.

        Args:
            operation_type: Type of operation (create, update, delete, etc.)
            resource_type: Type of resource (user, group, permission_set, assignment)
            resource_id: Specific resource identifier (optional)
            additional_context: Additional context for complex invalidations

        Returns:
            Total number of invalidated cache entries
        """
        logger.debug(
            f"Invalidating cache for operation: {operation_type} on {resource_type}"
            f"{f' (ID: {resource_id})' if resource_id else ''}"
        )

        patterns = self._get_invalidation_patterns(
            operation_type, resource_type, resource_id, additional_context or {}
        )

        total_invalidated = 0
        for pattern in patterns:
            invalidated_count = self.cache_manager.invalidate(pattern)
            total_invalidated += invalidated_count

            if invalidated_count > 0:
                logger.debug(f"Invalidated {invalidated_count} entries with pattern: {pattern}")

        logger.debug(f"Total invalidated entries: {total_invalidated}")
        return total_invalidated

    def invalidate_user_operations(self, operation_type: str, user_id: Optional[str] = None) -> int:
        """
        Invalidate cache for user-related operations.

        Args:
            operation_type: Type of operation (create, update, delete)
            user_id: User identifier

        Returns:
            Number of invalidated cache entries
        """
        return self.invalidate_for_operation(operation_type, "user", user_id)

    def invalidate_group_operations(
        self,
        operation_type: str,
        group_id: Optional[str] = None,
        affected_user_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Invalidate cache for group-related operations.

        Args:
            operation_type: Type of operation (create, update, delete, add_member, remove_member)
            group_id: Group identifier
            affected_user_ids: List of user IDs affected by membership changes

        Returns:
            Number of invalidated cache entries
        """
        additional_context = {}
        if affected_user_ids:
            additional_context["affected_user_ids"] = ",".join(affected_user_ids)

        return self.invalidate_for_operation(operation_type, "group", group_id, additional_context)

    def invalidate_permission_set_operations(
        self,
        operation_type: str,
        permission_set_arn: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> int:
        """
        Invalidate cache for permission set operations.

        Args:
            operation_type: Type of operation (create, update, delete)
            permission_set_arn: Permission set ARN
            account_id: Account ID for account-specific operations

        Returns:
            Number of invalidated cache entries
        """
        additional_context = {}
        if account_id:
            additional_context["account_id"] = account_id

        # Extract permission set name from ARN for consistent invalidation
        permission_set_id = None
        if permission_set_arn:
            permission_set_id = CacheKeyBuilder._extract_permission_set_name(permission_set_arn)

        return self.invalidate_for_operation(
            operation_type, "permission_set", permission_set_id, additional_context
        )

    def invalidate_assignment_operations(
        self,
        operation_type: str,
        account_id: Optional[str] = None,
        permission_set_arn: Optional[str] = None,
        principal_id: Optional[str] = None,
        principal_type: Optional[str] = None,
    ) -> int:
        """
        Invalidate cache for assignment operations.

        Args:
            operation_type: Type of operation (create, delete)
            account_id: AWS account ID
            permission_set_arn: Permission set ARN
            principal_id: Principal ID (user or group)
            principal_type: Principal type (USER or GROUP)

        Returns:
            Number of invalidated cache entries
        """
        additional_context = {
            "account_id": account_id or "",
            "permission_set_arn": permission_set_arn or "",
            "principal_id": principal_id or "",
            "principal_type": principal_type or "",
        }

        return self.invalidate_for_operation(operation_type, "assignment", None, additional_context)

    def _get_invalidation_patterns(
        self,
        operation_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        additional_context: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Generate invalidation patterns based on operation and resource type.

        Args:
            operation_type: Type of operation
            resource_type: Type of resource
            resource_id: Specific resource identifier
            additional_context: Additional context for complex invalidations

        Returns:
            List of cache key patterns to invalidate
        """
        patterns = []
        context = additional_context or {}

        # Get base patterns for the resource type and operation
        base_patterns = self.invalidation_rules.get(resource_type, {}).get(operation_type, [])

        for pattern_template in base_patterns:
            # Replace placeholders in pattern templates
            pattern = pattern_template.format(
                resource_type=resource_type, resource_id=resource_id or "*", **context
            )
            patterns.append(pattern)

        # Add cross-resource invalidation patterns
        cross_patterns = self._get_cross_resource_patterns(
            operation_type, resource_type, resource_id, context
        )
        patterns.extend(cross_patterns)

        # Remove duplicates while preserving order
        seen = set()
        unique_patterns = []
        for pattern in patterns:
            if pattern not in seen:
                seen.add(pattern)
                unique_patterns.append(pattern)

        return unique_patterns

    def _get_cross_resource_patterns(
        self,
        operation_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Generate cross-resource invalidation patterns.

        When one resource is modified, related resources may need cache invalidation.
        For example, when a group is updated, user membership lists may be affected.

        Args:
            operation_type: Type of operation
            resource_type: Type of resource
            resource_id: Specific resource identifier
            context: Additional context

        Returns:
            List of cross-resource invalidation patterns
        """
        patterns = []
        context = context or {}

        if resource_type == "user":
            # When user is modified, invalidate group membership caches
            if operation_type in ["update", "delete"]:
                patterns.extend(
                    [
                        "group:members:*",  # All group membership lists
                        "assignment:*",  # All assignment caches (user might be assigned)
                    ]
                )

        elif resource_type == "group":
            # When group is modified, invalidate related caches
            if operation_type in ["update", "delete"]:
                patterns.extend(
                    [
                        "assignment:*",  # All assignment caches (group might be assigned)
                    ]
                )

            # Handle membership changes
            if operation_type in ["add_member", "remove_member"]:
                patterns.extend(
                    [
                        f"group:members:{resource_id}",  # Specific group membership
                        "group:members:*",  # All group memberships (for consistency)
                    ]
                )

                # If we know which users were affected, invalidate their related caches
                if "affected_user_ids" in context:
                    user_ids = context["affected_user_ids"].split(",")
                    for user_id in user_ids:
                        patterns.append(f"user:*:{user_id}")

        elif resource_type == "permission_set":
            # When permission set is modified, invalidate assignment caches
            if operation_type in ["update", "delete"]:
                patterns.extend(
                    [
                        "assignment:*",  # All assignment caches
                    ]
                )

                # If we have account context, be more specific
                if "account_id" in context and context["account_id"]:
                    patterns.append(f"assignment:*:acc-{context['account_id']}*")

        elif resource_type == "assignment":
            # When assignments are modified, invalidate related resource caches
            if operation_type in ["create", "delete"]:
                # Invalidate assignment list caches
                patterns.extend(
                    [
                        "assignment:list:*",
                        "assignment:account_assignments:*",
                    ]
                )

                # Invalidate specific account assignment caches
                if "account_id" in context and context["account_id"]:
                    patterns.append(f"assignment:*:acc-{context['account_id']}*")

                # Invalidate principal-specific caches
                if "principal_id" in context and context["principal_id"]:
                    principal_type = context.get("principal_type", "").lower()
                    if principal_type == "user":
                        patterns.append(f"user:*:{context['principal_id']}")
                    elif principal_type == "group":
                        patterns.append(f"group:*:{context['principal_id']}")

        return patterns

    def _load_invalidation_rules(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Load invalidation rules for each resource type and operation.

        Returns:
            Dictionary mapping resource types and operations to invalidation patterns
        """
        return {
            "user": {
                "create": [
                    "user:list:*",  # Invalidate all user lists
                ],
                "update": [
                    "user:list:*",  # Invalidate all user lists
                    "user:describe:{resource_id}",  # Invalidate specific user
                    "user:*:{resource_id}",  # Invalidate all operations for this user
                ],
                "delete": [
                    "user:list:*",  # Invalidate all user lists
                    "user:*:{resource_id}",  # Invalidate all operations for this user
                ],
            },
            "group": {
                "create": [
                    "group:list:*",  # Invalidate all group lists
                ],
                "update": [
                    "group:list:*",  # Invalidate all group lists
                    "group:describe:{resource_id}",  # Invalidate specific group
                    "group:*:{resource_id}",  # Invalidate all operations for this group
                ],
                "delete": [
                    "group:list:*",  # Invalidate all group lists
                    "group:*:{resource_id}",  # Invalidate all operations for this group
                ],
                "add_member": [
                    "group:members:{resource_id}",  # Invalidate group membership
                    "group:describe:{resource_id}",  # Group details might include member count
                ],
                "remove_member": [
                    "group:members:{resource_id}",  # Invalidate group membership
                    "group:describe:{resource_id}",  # Group details might include member count
                ],
            },
            "permission_set": {
                "create": [
                    "permission_set:list:*",  # Invalidate all permission set lists
                ],
                "update": [
                    "permission_set:list:*",  # Invalidate all permission set lists
                    "permission_set:describe:{resource_id}",  # Invalidate specific permission set
                    "permission_set:*:{resource_id}",  # Invalidate all operations for this permission set
                ],
                "delete": [
                    "permission_set:list:*",  # Invalidate all permission set lists
                    "permission_set:*:{resource_id}",  # Invalidate all operations for this permission set
                ],
                "update_policies": [
                    "permission_set:policies:{resource_id}",  # Invalidate permission set policies
                    "permission_set:describe:{resource_id}",  # Permission set details might include policy info
                ],
            },
            "assignment": {
                "create": [
                    "assignment:list:*",  # Invalidate all assignment lists
                    "assignment:account_assignments:*",  # Invalidate account assignment lists
                ],
                "delete": [
                    "assignment:list:*",  # Invalidate all assignment lists
                    "assignment:account_assignments:*",  # Invalidate account assignment lists
                ],
            },
            "account": {
                "update": [
                    "account:list:*",  # Invalidate all account lists
                    "account:*:{resource_id}",  # Invalidate all operations for this account
                ],
            },
        }

    def get_invalidation_stats(self) -> Dict[str, int]:
        """
        Get statistics about cache invalidations.

        Returns:
            Dictionary with invalidation statistics
        """
        cache_stats = self.cache_manager.get_stats()
        return {
            "total_invalidations": cache_stats.get("invalidations", 0),
            "cache_clears": cache_stats.get("clears", 0),
        }

    def validate_patterns(self) -> List[str]:
        """
        Validate all invalidation patterns for correctness.

        Returns:
            List of validation errors (empty if all patterns are valid)
        """
        errors = []

        for resource_type, operations in self.invalidation_rules.items():
            for operation_type, patterns in operations.items():
                for pattern in patterns:
                    try:
                        # Try to format the pattern with sample data
                        test_pattern = pattern.format(
                            resource_type=resource_type, resource_id="test-id"
                        )

                        # Basic validation - pattern should contain valid characters
                        if not test_pattern or ":" not in test_pattern:
                            errors.append(
                                f"Invalid pattern '{pattern}' for {resource_type}.{operation_type}"
                            )
                    except (KeyError, ValueError) as e:
                        errors.append(
                            f"Pattern formatting error '{pattern}' for {resource_type}.{operation_type}: {e}"
                        )

        return errors


# Convenience functions for common invalidation operations
def invalidate_user_cache(
    cache_manager: ICacheManager, operation: str, user_id: Optional[str] = None
) -> int:
    """Convenience function to invalidate user-related cache entries."""
    engine = CacheInvalidationEngine(cache_manager)
    return engine.invalidate_user_operations(operation, user_id)


def invalidate_group_cache(
    cache_manager: ICacheManager,
    operation: str,
    group_id: Optional[str] = None,
    affected_users: Optional[List[str]] = None,
) -> int:
    """Convenience function to invalidate group-related cache entries."""
    engine = CacheInvalidationEngine(cache_manager)
    return engine.invalidate_group_operations(operation, group_id, affected_users)


def invalidate_permission_set_cache(
    cache_manager: ICacheManager,
    operation: str,
    permission_set_arn: Optional[str] = None,
    account_id: Optional[str] = None,
) -> int:
    """Convenience function to invalidate permission set-related cache entries."""
    engine = CacheInvalidationEngine(cache_manager)
    return engine.invalidate_permission_set_operations(operation, permission_set_arn, account_id)


def invalidate_assignment_cache(
    cache_manager: ICacheManager,
    operation: str,
    account_id: Optional[str] = None,
    permission_set_arn: Optional[str] = None,
    principal_id: Optional[str] = None,
    principal_type: Optional[str] = None,
) -> int:
    """Convenience function to invalidate assignment-related cache entries."""
    engine = CacheInvalidationEngine(cache_manager)
    return engine.invalidate_assignment_operations(
        operation, account_id, permission_set_arn, principal_id, principal_type
    )
