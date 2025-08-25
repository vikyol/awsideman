"""Cache key generation system for the unified cache manager.

This module provides a hierarchical cache key generation system that follows
the pattern: {resource_type}:{operation}:{identifier}:{sub_identifier}

The key builder ensures consistent key generation across all AWS operations
and supports targeted cache invalidation through pattern matching.
"""

import hashlib
import re
from typing import Any, Dict, Optional


class CacheKeyValidationError(Exception):
    """Raised when cache key validation fails."""

    pass


class CacheKeyBuilder:
    """
    Utility class for generating hierarchical cache keys.

    Provides methods for different resource types and operations while
    ensuring consistent key format and validation.
    """

    # Maximum key length to prevent filesystem and storage issues
    MAX_KEY_LENGTH = 250

    # Valid resource types
    VALID_RESOURCE_TYPES = {
        "user",
        "group",
        "permission_set",
        "assignment",
        "account",
        "instance",
        "application",
        "trusted_token_issuer",
    }

    # Valid operations
    VALID_OPERATIONS = {
        "list",
        "describe",
        "get",
        "create",
        "update",
        "delete",
        "members",
        "assignments",
        "permissions",
        "policies",
        "provisioning_status",
        "account_assignments",
    }

    # Key component separator
    SEPARATOR = ":"

    # Pattern for validating key components (alphanumeric, hyphens, underscores)
    COMPONENT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    @classmethod
    def build_key(
        cls,
        resource_type: str,
        operation: str,
        identifier: Optional[str] = None,
        sub_identifier: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Build a hierarchical cache key.

        Args:
            resource_type: Type of AWS resource (user, group, permission_set, etc.)
            operation: Operation being performed (list, describe, get, etc.)
            identifier: Primary identifier (user ID, group ID, etc.)
            sub_identifier: Secondary identifier for nested operations
            **kwargs: Additional parameters to include in key generation

        Returns:
            Formatted cache key string

        Raises:
            CacheKeyValidationError: If key components are invalid
        """
        # Validate required components
        cls._validate_resource_type(resource_type)
        cls._validate_operation(operation)

        # Build key components
        components = [resource_type, operation]

        if identifier:
            components.append(cls._sanitize_component(identifier))

        if sub_identifier:
            components.append(cls._sanitize_component(sub_identifier))

        # Add additional parameters if provided
        if kwargs:
            param_hash = cls._hash_parameters(kwargs)
            components.append(param_hash)

        # Join components and validate final key
        key = cls.SEPARATOR.join(components)
        cls._validate_key_length(key)

        return key

    @classmethod
    def build_user_key(cls, operation: str, user_id: Optional[str] = None, **kwargs: Any) -> str:
        """
        Build cache key for user operations.

        Args:
            operation: User operation (list, describe, create, update, delete)
            user_id: User identifier (optional for list operations)
            **kwargs: Additional parameters

        Returns:
            User cache key
        """
        return cls.build_key("user", operation, user_id, **kwargs)

    @classmethod
    def build_group_key(
        cls,
        operation: str,
        group_id: Optional[str] = None,
        sub_operation: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Build cache key for group operations.

        Args:
            operation: Group operation (list, describe, members, etc.)
            group_id: Group identifier (optional for list operations)
            sub_operation: Sub-operation for nested operations
            **kwargs: Additional parameters

        Returns:
            Group cache key
        """
        return cls.build_key("group", operation, group_id, sub_operation, **kwargs)

    @classmethod
    def build_permission_set_key(
        cls,
        operation: str,
        permission_set_arn: Optional[str] = None,
        account_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Build cache key for permission set operations.

        Args:
            operation: Permission set operation
            permission_set_arn: Permission set ARN
            account_id: Account ID for account-specific operations
            **kwargs: Additional parameters

        Returns:
            Permission set cache key
        """
        # Extract permission set name from ARN for cleaner keys
        identifier = None
        if permission_set_arn:
            identifier = cls._extract_permission_set_name(permission_set_arn)

        return cls.build_key("permission_set", operation, identifier, account_id, **kwargs)

    @classmethod
    def build_assignment_key(
        cls,
        operation: str,
        account_id: Optional[str] = None,
        permission_set_arn: Optional[str] = None,
        principal_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Build cache key for assignment operations.

        Args:
            operation: Assignment operation
            account_id: AWS account ID
            permission_set_arn: Permission set ARN
            principal_id: Principal ID (user or group)
            **kwargs: Additional parameters

        Returns:
            Assignment cache key
        """
        # Create composite identifier for assignments
        identifiers = []
        if account_id:
            identifiers.append(f"acc-{account_id}")
        if permission_set_arn:
            ps_name = cls._extract_permission_set_name(permission_set_arn)
            identifiers.append(f"ps-{ps_name}")
        if principal_id:
            identifiers.append(f"prin-{principal_id}")

        identifier = "_".join(identifiers) if identifiers else None

        return cls.build_key("assignment", operation, identifier, **kwargs)

    @classmethod
    def build_account_key(
        cls, operation: str, account_id: Optional[str] = None, **kwargs: Any
    ) -> str:
        """
        Build cache key for account operations.

        Args:
            operation: Account operation
            account_id: AWS account ID
            **kwargs: Additional parameters

        Returns:
            Account cache key
        """
        return cls.build_key("account", operation, account_id, **kwargs)

    @classmethod
    def build_invalidation_pattern(
        cls,
        resource_type: Optional[str] = None,
        operation: Optional[str] = None,
        identifier: Optional[str] = None,
    ) -> str:
        """
        Build pattern for cache invalidation.

        Args:
            resource_type: Resource type to invalidate (optional, * for all)
            operation: Operation to invalidate (optional, * for all)
            identifier: Identifier to invalidate (optional, * for all)

        Returns:
            Invalidation pattern with wildcards
        """
        components = []

        components.append(resource_type or "*")
        components.append(operation or "*")

        if identifier:
            components.append(cls._sanitize_component(identifier))
        else:
            components.append("*")

        return cls.SEPARATOR.join(components)

    @classmethod
    def parse_key(cls, key: str) -> Dict[str, Optional[str]]:
        """
        Parse a cache key into its components.

        Args:
            key: Cache key to parse

        Returns:
            Dictionary with key components
        """
        components = key.split(cls.SEPARATOR)

        result = {
            "resource_type": components[0] if len(components) > 0 else None,
            "operation": components[1] if len(components) > 1 else None,
            "identifier": components[2] if len(components) > 2 else None,
            "sub_identifier": components[3] if len(components) > 3 else None,
            "parameters_hash": components[4] if len(components) > 4 else None,
        }

        return result

    @classmethod
    def _validate_resource_type(cls, resource_type: str) -> None:
        """Validate resource type."""
        if not resource_type:
            raise CacheKeyValidationError("Resource type cannot be empty")

        if resource_type not in cls.VALID_RESOURCE_TYPES:
            raise CacheKeyValidationError(
                f"Invalid resource type '{resource_type}'. "
                f"Valid types: {', '.join(sorted(cls.VALID_RESOURCE_TYPES))}"
            )

    @classmethod
    def _validate_operation(cls, operation: str) -> None:
        """Validate operation."""
        if not operation:
            raise CacheKeyValidationError("Operation cannot be empty")

        if operation not in cls.VALID_OPERATIONS:
            raise CacheKeyValidationError(
                f"Invalid operation '{operation}'. "
                f"Valid operations: {', '.join(sorted(cls.VALID_OPERATIONS))}"
            )

    @classmethod
    def _validate_key_length(cls, key: str) -> None:
        """Validate key length."""
        if len(key) > cls.MAX_KEY_LENGTH:
            raise CacheKeyValidationError(
                f"Cache key too long ({len(key)} chars). " f"Maximum length: {cls.MAX_KEY_LENGTH}"
            )

    @classmethod
    def _sanitize_component(cls, component: str) -> str:
        """
        Sanitize key component to ensure it's safe for use.

        Args:
            component: Component to sanitize

        Returns:
            Sanitized component
        """
        if not component:
            return component

        # Replace problematic characters with safe alternatives
        # This is better than URL encoding for cache keys
        sanitized = component.replace(":", "_").replace("/", "_").replace("\\", "_")

        # Remove any other potentially problematic characters
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", sanitized)

        # Replace multiple underscores with single underscore
        sanitized = re.sub(r"_+", "_", sanitized)

        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")

        # Truncate if too long (leave room for other components)
        max_component_length = cls.MAX_KEY_LENGTH // 4
        if len(sanitized) > max_component_length:
            # Hash long components to maintain uniqueness
            hash_suffix = hashlib.sha256(component.encode()).hexdigest()[:8]
            sanitized = sanitized[: max_component_length - 9] + "_" + hash_suffix

        return sanitized

    @classmethod
    def _hash_parameters(cls, params: Dict[str, Any]) -> str:
        """
        Create hash of parameters for key generation.

        Args:
            params: Parameters to hash

        Returns:
            Short hash string
        """
        # Sort parameters for consistent hashing
        sorted_items = sorted(params.items())
        param_string = str(sorted_items)

        # Create short hash
        return hashlib.sha256(param_string.encode()).hexdigest()[:12]

    @classmethod
    def _extract_permission_set_name(cls, permission_set_arn: str) -> str:
        """
        Extract permission set name from ARN.

        Args:
            permission_set_arn: Permission set ARN

        Returns:
            Permission set name
        """
        # ARN format: arn:aws:sso:::permissionSet/ssoins-xxx/ps-xxx
        if "/" in permission_set_arn:
            return permission_set_arn.split("/")[-1]
        return permission_set_arn


# Convenience functions for common operations
def user_list_key(**kwargs: Any) -> str:
    """Generate key for user list operations."""
    return CacheKeyBuilder.build_user_key("list", **kwargs)


def user_describe_key(user_id: str, **kwargs: Any) -> str:
    """Generate key for user describe operations."""
    return CacheKeyBuilder.build_user_key("describe", user_id, **kwargs)


def group_list_key(**kwargs: Any) -> str:
    """Generate key for group list operations."""
    return CacheKeyBuilder.build_group_key("list", **kwargs)


def group_describe_key(group_id: str, **kwargs: Any) -> str:
    """Generate key for group describe operations."""
    return CacheKeyBuilder.build_group_key("describe", group_id, **kwargs)


def group_members_key(group_id: str, **kwargs: Any) -> str:
    """Generate key for group members operations."""
    return CacheKeyBuilder.build_group_key("members", group_id, **kwargs)


def permission_set_list_key(**kwargs: Any) -> str:
    """Generate key for permission set list operations."""
    return CacheKeyBuilder.build_permission_set_key("list", **kwargs)


def assignment_list_key(account_id: str, **kwargs: Any) -> str:
    """Generate key for assignment list operations."""
    return CacheKeyBuilder.build_assignment_key("list", account_id, **kwargs)
