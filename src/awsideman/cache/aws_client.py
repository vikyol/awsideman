"""Cached AWS client wrapper for the unified cache system.

This module provides a base class for wrapping boto3 clients with automatic
caching for read operations and cache invalidation for write operations.
"""

import logging
from datetime import timedelta
from typing import Any, Callable, Dict, Optional

from .interfaces import ICacheManager
from .key_builder import CacheKeyBuilder
from .manager import CacheManager

logger = logging.getLogger(__name__)


class CachedAWSClient:
    """
    Base class that wraps boto3 clients with automatic caching.

    This class provides transparent caching for read operations (list_*, describe_*, get_*)
    and automatic cache invalidation for write operations (create_*, update_*, delete_*).

    Features:
    - Automatic detection of read vs write operations
    - Intelligent cache key generation using CacheKeyBuilder
    - Automatic cache invalidation for write operations
    - Graceful degradation when cache operations fail
    - Support for custom TTL per operation type
    """

    # Default TTL values for different operation types
    DEFAULT_TTL_CONFIG = {
        "list": timedelta(minutes=15),
        "describe": timedelta(minutes=10),
        "get": timedelta(minutes=10),
        "default": timedelta(minutes=5),
    }

    # Operations that should be cached (read operations)
    READ_OPERATIONS = {
        "list_users",
        "list_groups",
        "list_permission_sets",
        "list_instances",
        "list_accounts",
        "list_roots",
        "list_organizational_units_for_parent",
        "list_accounts_for_parent",
        "list_permission_sets_provisioned_to_account",
        "list_accounts_for_provisioned_permission_set",
        "list_group_memberships",
        "list_account_assignments",
        "list_tags_for_resource",
        "list_policies_for_target",
        "list_parents",
        "describe_user",
        "describe_group",
        "describe_permission_set",
        "describe_instance",
        "describe_account",
        "get_inline_policy_for_permission_set",
        "get_permissions_boundary_for_permission_set",
        "list_managed_policies_in_permission_set",
        "list_customer_managed_policy_references_in_permission_set",
    }

    # Operations that should trigger cache invalidation (write operations)
    WRITE_OPERATIONS = {
        "create_user",
        "create_group",
        "create_permission_set",
        "create_account_assignment",
        "update_user",
        "update_group",
        "update_permission_set",
        "update_instance",
        "delete_user",
        "delete_group",
        "delete_permission_set",
        "delete_account_assignment",
        "create_group_membership",
        "delete_group_membership",
        "provision_permission_set",
        "put_inline_policy_in_permission_set",
        "delete_inline_policy_from_permission_set",
        "attach_managed_policy_to_permission_set",
        "detach_managed_policy_from_permission_set",
        "put_permissions_boundary_to_permission_set",
        "delete_permissions_boundary_from_permission_set",
        "attach_customer_managed_policy_reference_to_permission_set",
        "detach_customer_managed_policy_reference_from_permission_set",
    }

    def __init__(
        self,
        aws_client: Any,
        resource_type: str,
        cache_manager: Optional[ICacheManager] = None,
        ttl_config: Optional[Dict[str, timedelta]] = None,
    ):
        """
        Initialize the cached AWS client wrapper.

        Args:
            aws_client: The boto3 client to wrap
            resource_type: Type of AWS resource (user, group, permission_set, etc.)
            cache_manager: Cache manager instance (defaults to CacheManager singleton)
            ttl_config: Custom TTL configuration for different operation types
        """
        self.aws_client = aws_client
        self.resource_type = resource_type
        self.cache_manager = cache_manager or CacheManager()
        self.ttl_config = {**self.DEFAULT_TTL_CONFIG, **(ttl_config or {})}

        logger.debug(f"Initialized CachedAWSClient for resource type: {resource_type}")

    def __getattr__(self, name: str) -> Callable:
        """
        Intercept method calls and provide caching for read operations.

        Args:
            name: Method name being called

        Returns:
            Wrapped method with caching support
        """
        # Get the original method from the AWS client
        original_method = getattr(self.aws_client, name)

        # If it's not callable, return as-is (properties, etc.)
        if not callable(original_method):
            return original_method

        # Special handling for get_paginator - always pass through without caching
        if name == "get_paginator":
            return original_method

        # Determine if this is a read or write operation
        is_read_operation = self._is_read_operation(name)
        is_write_operation = self._is_write_operation(name)

        if is_read_operation:
            return self._create_cached_method(name, original_method)
        elif is_write_operation:
            return self._create_invalidating_method(name, original_method)
        else:
            # For operations we don't recognize, just pass through
            logger.debug(f"Unknown operation type for {name}, passing through without caching")
            return original_method

    def _is_read_operation(self, operation_name: str) -> bool:
        """
        Check if an operation is a read operation that should be cached.

        Args:
            operation_name: Name of the operation

        Returns:
            True if operation should be cached
        """
        # Check explicit list first
        if operation_name in self.READ_OPERATIONS:
            return True

        # Check common patterns
        read_prefixes = ("list_", "describe_", "get_")
        return any(operation_name.startswith(prefix) for prefix in read_prefixes)

    def _is_write_operation(self, operation_name: str) -> bool:
        """
        Check if an operation is a write operation that should invalidate cache.

        Args:
            operation_name: Name of the operation

        Returns:
            True if operation should invalidate cache
        """
        # Check explicit list first
        if operation_name in self.WRITE_OPERATIONS:
            return True

        # Check common patterns
        write_prefixes = (
            "create_",
            "update_",
            "delete_",
            "put_",
            "attach_",
            "detach_",
            "provision_",
        )
        return any(operation_name.startswith(prefix) for prefix in write_prefixes)

    def _create_cached_method(self, operation_name: str, original_method: Callable) -> Callable:
        """
        Create a cached version of a read method.

        Args:
            operation_name: Name of the operation
            original_method: Original method to wrap

        Returns:
            Cached method wrapper
        """

        def cached_method(*args, **kwargs):
            # Generate cache key
            try:
                cache_key = self._generate_cache_key(operation_name, args, kwargs)
            except Exception as e:
                logger.warning(f"Failed to generate cache key for {operation_name}: {e}")
                return original_method(*args, **kwargs)

            # Try to get from cache
            try:
                cached_result = self.cache_manager.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {operation_name}")
                    return cached_result
            except Exception as e:
                logger.warning(f"Cache retrieval failed for {operation_name}: {e}")
                # Continue to API call

            # Cache miss - call the API
            logger.debug(f"Cache miss for {operation_name}, calling AWS API")
            try:
                result = original_method(*args, **kwargs)

                # Cache the result
                try:
                    ttl = self._get_ttl_for_operation(operation_name)
                    self.cache_manager.set(cache_key, result, ttl)
                    logger.debug(f"Cached result for {operation_name}")
                except Exception as cache_error:
                    logger.warning(f"Failed to cache result for {operation_name}: {cache_error}")

                return result

            except Exception as e:
                logger.debug(f"AWS API call failed for {operation_name}: {e}")
                raise

        return cached_method

    def _create_invalidating_method(
        self, operation_name: str, original_method: Callable
    ) -> Callable:
        """
        Create a version of a write method that invalidates cache.

        Args:
            operation_name: Name of the operation
            original_method: Original method to wrap

        Returns:
            Method wrapper with cache invalidation
        """

        def invalidating_method(*args, **kwargs):
            # Call the original method first
            try:
                result = original_method(*args, **kwargs)

                # Invalidate relevant cache entries
                try:
                    invalidated_count = self._invalidate_for_operation(operation_name, args, kwargs)
                    if invalidated_count > 0:
                        logger.debug(
                            f"Invalidated {invalidated_count} cache entries for {operation_name}"
                        )
                except Exception as e:
                    logger.warning(f"Cache invalidation failed for {operation_name}: {e}")

                return result

            except Exception as e:
                logger.debug(f"AWS API call failed for {operation_name}: {e}")
                raise

        return invalidating_method

    def _generate_cache_key(self, operation_name: str, args: tuple, kwargs: dict) -> str:
        """
        Generate a cache key for the operation and parameters.

        Args:
            operation_name: Name of the AWS operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Cache key string
        """
        # Map operation to cache key builder operation
        if operation_name.startswith("list_"):
            cache_operation = "list"
        elif operation_name.startswith("describe_"):
            cache_operation = "describe"
        elif operation_name.startswith("get_"):
            cache_operation = "get"
        else:
            cache_operation = operation_name

        # Extract identifiers based on resource type and operation
        identifier = None
        sub_identifier = None
        additional_params = {}

        # Handle common parameter patterns
        if self.resource_type == "user":
            if "UserId" in kwargs:
                identifier = kwargs["UserId"]
            elif len(args) >= 2 and operation_name in ["describe_user"]:
                identifier = args[1]  # Usually identity_store_id, user_id
        elif self.resource_type == "group":
            if "GroupId" in kwargs:
                identifier = kwargs["GroupId"]
            elif len(args) >= 2 and operation_name in ["describe_group", "list_group_memberships"]:
                identifier = args[1]  # Usually identity_store_id, group_id
        elif self.resource_type == "permission_set":
            if "PermissionSetArn" in kwargs:
                identifier = kwargs["PermissionSetArn"]
            elif len(args) >= 2 and operation_name in ["describe_permission_set"]:
                identifier = args[1]  # Usually instance_arn, permission_set_arn
        elif self.resource_type == "assignment":
            if "AccountId" in kwargs:
                identifier = kwargs["AccountId"]
            if "PermissionSetArn" in kwargs:
                sub_identifier = kwargs["PermissionSetArn"]

        # Add remaining parameters to additional params, but handle pagination carefully
        for key, value in kwargs.items():
            if key not in ["UserId", "GroupId", "PermissionSetArn", "AccountId", "InstanceArn"]:
                # For list operations, only include pagination if it's a specific page request
                if key in ["MaxResults", "NextToken"]:
                    if operation_name.startswith("list_") and key == "NextToken" and value:
                        # This is a request for a specific page
                        additional_params[key.lower()] = value
                    elif (
                        operation_name.startswith("list_")
                        and key == "MaxResults"
                        and "NextToken" in kwargs
                        and kwargs["NextToken"]
                    ):
                        # Include MaxResults only if NextToken is also present
                        additional_params[key.lower()] = value
                    # Skip MaxResults for initial requests to allow consistent caching
                else:
                    additional_params[key] = value

        # For list operations without specific identifiers, use "all" as identifier
        if cache_operation == "list" and identifier is None:
            identifier = "all"

        # Use CacheKeyBuilder to generate the key
        return CacheKeyBuilder.build_key(
            resource_type=self.resource_type,
            operation=cache_operation,
            identifier=identifier,
            sub_identifier=sub_identifier,
            **additional_params,
        )

    def _get_ttl_for_operation(self, operation_name: str) -> timedelta:
        """
        Get TTL for a specific operation.

        Args:
            operation_name: Name of the operation

        Returns:
            TTL for the operation
        """
        if operation_name.startswith("list_"):
            return self.ttl_config.get("list", self.ttl_config["default"])
        elif operation_name.startswith("describe_"):
            return self.ttl_config.get("describe", self.ttl_config["default"])
        elif operation_name.startswith("get_"):
            return self.ttl_config.get("get", self.ttl_config["default"])
        else:
            return self.ttl_config["default"]

    def _invalidate_for_operation(self, operation_name: str, args: tuple, kwargs: dict) -> int:
        """
        Invalidate cache entries for a write operation.

        Args:
            operation_name: Name of the write operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Number of invalidated cache entries
        """
        # Determine operation type for invalidation
        if operation_name.startswith("create_"):
            operation_type = "create"
        elif operation_name.startswith("update_"):
            operation_type = "update"
        elif operation_name.startswith("delete_"):
            operation_type = "delete"
        else:
            operation_type = "modify"

        # Extract resource identifier for targeted invalidation
        resource_id = None
        additional_context = {}

        if self.resource_type == "user":
            if "UserId" in kwargs:
                resource_id = kwargs["UserId"]
        elif self.resource_type == "group":
            if "GroupId" in kwargs:
                resource_id = kwargs["GroupId"]
        elif self.resource_type == "permission_set":
            if "PermissionSetArn" in kwargs:
                resource_id = kwargs["PermissionSetArn"]
        elif self.resource_type == "assignment":
            if "AccountId" in kwargs:
                additional_context["account_id"] = kwargs["AccountId"]
            if "PermissionSetArn" in kwargs:
                additional_context["permission_set_arn"] = kwargs["PermissionSetArn"]
            if "PrincipalId" in kwargs:
                additional_context["principal_id"] = kwargs["PrincipalId"]

        # Use the cache manager's invalidation method
        return self.cache_manager.invalidate_for_operation(
            operation_type=operation_type,
            resource_type=self.resource_type,
            resource_id=resource_id,
            additional_context=additional_context,
        )


class CachedIdentityCenterClient(CachedAWSClient):
    """Cached wrapper for AWS Identity Center (SSO Admin) client."""

    def __init__(
        self,
        identity_center_client: Any,
        cache_manager: Optional[ICacheManager] = None,
        ttl_config: Optional[Dict[str, timedelta]] = None,
    ):
        """
        Initialize cached Identity Center client.

        Args:
            identity_center_client: boto3 SSO Admin client
            cache_manager: Cache manager instance
            ttl_config: Custom TTL configuration
        """
        super().__init__(
            aws_client=identity_center_client,
            resource_type="permission_set",
            cache_manager=cache_manager,
            ttl_config=ttl_config,
        )

        # Explicitly override key methods to ensure they go through caching
        self._override_methods()

    def _override_methods(self):
        """Override key methods to ensure they go through caching."""
        # Override list_permission_sets to ensure it's cached
        if hasattr(self.aws_client, "list_permission_sets"):
            original_method = self.aws_client.list_permission_sets
            self.list_permission_sets = self._create_cached_method(
                "list_permission_sets", original_method
            )

        # Override describe_permission_set to ensure it's cached
        if hasattr(self.aws_client, "describe_permission_set"):
            original_method = self.aws_client.describe_permission_set
            self.describe_permission_set = self._create_cached_method(
                "describe_permission_set", original_method
            )

    def _generate_cache_key(self, operation_name: str, args: tuple, kwargs: dict) -> str:
        """
        Generate a cache key for Identity Center operations.

        Args:
            operation_name: Name of the AWS operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Cache key string
        """
        # Map operation to cache key builder operation
        if operation_name.startswith("list_"):
            cache_operation = "list"
        elif operation_name.startswith("describe_"):
            cache_operation = "describe"
        elif operation_name.startswith("get_"):
            cache_operation = "get"
        else:
            cache_operation = operation_name

        # Extract identifiers based on operation
        identifier = None
        sub_identifier = None
        additional_params = {}

        # Handle permission set operations
        if "permission_set" in operation_name.lower():
            resource_type = "permission_set"
            if "PermissionSetArn" in kwargs:
                identifier = kwargs["PermissionSetArn"]
            elif len(args) >= 2 and operation_name in ["describe_permission_set"]:
                # describe_permission_set(instance_arn, permission_set_arn)
                identifier = args[1]
            elif operation_name == "list_permission_sets":
                # For list_permission_sets, use InstanceArn as the identifier
                # to ensure different SSO instances have different cache keys
                # but the same instance always generates the same key
                if "InstanceArn" in kwargs:
                    identifier = kwargs["InstanceArn"]
                elif len(args) >= 1:
                    # list_permission_sets(instance_arn)
                    identifier = args[0]
                else:
                    identifier = "all"
        # Handle assignment operations
        elif "assignment" in operation_name.lower():
            resource_type = "assignment"
            if "AccountId" in kwargs:
                identifier = kwargs["AccountId"]
            if "PermissionSetArn" in kwargs:
                sub_identifier = kwargs["PermissionSetArn"]
        # Handle instance operations
        elif "instance" in operation_name.lower():
            resource_type = "instance"
            if "InstanceArn" in kwargs:
                identifier = kwargs["InstanceArn"]
            elif len(args) >= 1 and operation_name in ["describe_instance"]:
                identifier = args[0]
            elif operation_name == "list_instances":
                identifier = "all"
        else:
            # Default to permission_set
            resource_type = "permission_set"
            identifier = "all"

        # Handle pagination parameters carefully
        # For list operations, we should cache the complete result, not paginated chunks
        # Only include pagination in cache key if it's a specific page request
        if operation_name.startswith("list_") and "NextToken" in kwargs and kwargs["NextToken"]:
            # This is a request for a specific page, include pagination in key
            additional_params["next_token"] = kwargs["NextToken"]
            if "MaxResults" in kwargs:
                additional_params["max_results"] = kwargs["MaxResults"]
        # For initial requests (no NextToken), don't include pagination in cache key
        # This allows caching of complete results regardless of MaxResults setting

        # Use CacheKeyBuilder to generate the key
        return CacheKeyBuilder.build_key(
            resource_type=resource_type,
            operation=cache_operation,
            identifier=identifier,
            sub_identifier=sub_identifier,
            **additional_params,
        )

    def _invalidate_for_operation(self, operation_name: str, args: tuple, kwargs: dict) -> int:
        """
        Invalidate cache entries for Identity Center write operations.

        Args:
            operation_name: Name of the write operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Number of invalidated cache entries
        """
        # Determine operation type for invalidation
        if operation_name.startswith("create_"):
            operation_type = "create"
        elif operation_name.startswith("update_"):
            operation_type = "update"
        elif operation_name.startswith("delete_"):
            operation_type = "delete"
        elif operation_name.startswith("provision_"):
            operation_type = "provision"
        else:
            operation_type = "modify"

        # Determine resource type and ID
        resource_type = "permission_set"  # Default
        resource_id = None
        additional_context = {}

        if "permission_set" in operation_name.lower():
            resource_type = "permission_set"
            if "PermissionSetArn" in kwargs:
                resource_id = kwargs["PermissionSetArn"]
        elif "assignment" in operation_name.lower():
            resource_type = "assignment"
            if "AccountId" in kwargs:
                additional_context["account_id"] = kwargs["AccountId"]
            if "PermissionSetArn" in kwargs:
                additional_context["permission_set_arn"] = kwargs["PermissionSetArn"]
            if "PrincipalId" in kwargs:
                additional_context["principal_id"] = kwargs["PrincipalId"]
        elif "instance" in operation_name.lower():
            resource_type = "instance"
            if "InstanceArn" in kwargs:
                resource_id = kwargs["InstanceArn"]

        # Use the cache manager's invalidation method
        return self.cache_manager.invalidate_for_operation(
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            additional_context=additional_context,
        )


class CachedIdentityStoreClient(CachedAWSClient):
    """Cached wrapper for AWS Identity Store client."""

    def __init__(
        self,
        identity_store_client: Any,
        cache_manager: Optional[ICacheManager] = None,
        ttl_config: Optional[Dict[str, timedelta]] = None,
    ):
        """
        Initialize cached Identity Store client.

        Args:
            identity_store_client: boto3 Identity Store client
            cache_manager: Cache manager instance
            ttl_config: Custom TTL configuration
        """
        super().__init__(
            aws_client=identity_store_client,
            resource_type="user",  # Primary resource type, but handles groups too
            cache_manager=cache_manager,
            ttl_config=ttl_config,
        )

        # Explicitly override key methods to ensure they go through caching
        self._override_methods()

    def _override_methods(self):
        """Override key methods to ensure they go through caching."""
        # Override user operations to ensure they're cached
        if hasattr(self.aws_client, "list_users"):
            original_method = self.aws_client.list_users
            self.list_users = self._create_cached_method("list_users", original_method)

        if hasattr(self.aws_client, "describe_user"):
            original_method = self.aws_client.describe_user
            self.describe_user = self._create_cached_method("describe_user", original_method)

        # Override write operations to ensure they invalidate cache
        if hasattr(self.aws_client, "create_user"):
            original_method = self.aws_client.create_user
            self.create_user = self._create_invalidating_method("create_user", original_method)

        if hasattr(self.aws_client, "update_user"):
            original_method = self.aws_client.update_user
            self.update_user = self._create_invalidating_method("update_user", original_method)

        if hasattr(self.aws_client, "delete_user"):
            original_method = self.aws_client.delete_user
            self.delete_user = self._create_invalidating_method("delete_user", original_method)

        # Override group operations
        if hasattr(self.aws_client, "list_groups"):
            original_method = self.aws_client.list_groups
            self.list_groups = self._create_cached_method("list_groups", original_method)

        if hasattr(self.aws_client, "describe_group"):
            original_method = self.aws_client.describe_group
            self.describe_group = self._create_cached_method("describe_group", original_method)

        if hasattr(self.aws_client, "create_group"):
            original_method = self.aws_client.create_group
            self.create_group = self._create_invalidating_method("create_group", original_method)

        if hasattr(self.aws_client, "update_group"):
            original_method = self.aws_client.update_group
            self.update_group = self._create_invalidating_method("update_group", original_method)

        if hasattr(self.aws_client, "delete_group"):
            original_method = self.aws_client.delete_group
            self.delete_group = self._create_invalidating_method("delete_group", original_method)

    def _generate_cache_key(self, operation_name: str, args: tuple, kwargs: dict) -> str:
        """
        Generate a cache key for Identity Store operations.

        Args:
            operation_name: Name of the AWS operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Cache key string
        """
        # Map operation to cache key builder operation
        if operation_name.startswith("list_"):
            cache_operation = "list"
        elif operation_name.startswith("describe_"):
            cache_operation = "describe"
        elif operation_name.startswith("get_"):
            cache_operation = "get"
        else:
            cache_operation = operation_name

        # Extract identifiers based on operation
        identifier = None
        sub_identifier = None
        additional_params = {}

        # Handle user operations
        if "user" in operation_name.lower():
            resource_type = "user"
            if "UserId" in kwargs:
                identifier = kwargs["UserId"]
            elif len(args) >= 2 and operation_name in ["describe_user"]:
                # describe_user(identity_store_id, user_id)
                identifier = args[1]
            elif operation_name == "list_users":
                identifier = "all"
                # Include filters in additional params
                if "Filters" in kwargs:
                    additional_params["filters"] = str(kwargs["Filters"])
        # Handle group operations
        elif "group" in operation_name.lower():
            resource_type = "group"
            if "GroupId" in kwargs:
                identifier = kwargs["GroupId"]
            elif len(args) >= 2 and operation_name in ["describe_group", "list_group_memberships"]:
                # describe_group(identity_store_id, group_id)
                identifier = args[1]
            elif operation_name == "list_groups":
                identifier = "all"
                # Include filters in additional params
                if "Filters" in kwargs:
                    additional_params["filters"] = str(kwargs["Filters"])
        else:
            # Default to user resource type
            resource_type = "user"
            identifier = "all"

        # Handle pagination parameters carefully
        # For list operations, we should cache the complete result, not paginated chunks
        # Only include pagination in cache key if it's a specific page request
        if operation_name.startswith("list_") and "NextToken" in kwargs and kwargs["NextToken"]:
            # This is a request for a specific page, include pagination in key
            additional_params["next_token"] = kwargs["NextToken"]
            if "MaxResults" in kwargs:
                additional_params["max_results"] = kwargs["MaxResults"]
        # For initial requests (no NextToken), don't include pagination in cache key
        # This allows caching of complete results regardless of MaxResults setting

        # Use CacheKeyBuilder to generate the key
        return CacheKeyBuilder.build_key(
            resource_type=resource_type,
            operation=cache_operation,
            identifier=identifier,
            sub_identifier=sub_identifier,
            **additional_params,
        )

    def _invalidate_for_operation(self, operation_name: str, args: tuple, kwargs: dict) -> int:
        """
        Invalidate cache entries for Identity Store write operations.

        Args:
            operation_name: Name of the write operation
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Number of invalidated cache entries
        """
        # Determine operation type for invalidation
        if operation_name.startswith("create_"):
            operation_type = "create"
        elif operation_name.startswith("update_"):
            operation_type = "update"
        elif operation_name.startswith("delete_"):
            operation_type = "delete"
        else:
            operation_type = "modify"

        # Determine resource type and ID
        resource_type = "user"  # Default
        resource_id = None
        additional_context = {}

        if "user" in operation_name.lower():
            resource_type = "user"
            if "UserId" in kwargs:
                resource_id = kwargs["UserId"]
        elif "group" in operation_name.lower():
            resource_type = "group"
            if "GroupId" in kwargs:
                resource_id = kwargs["GroupId"]
            # For group membership operations, also invalidate user cache
            if "membership" in operation_name.lower():
                additional_context["affects_users"] = True
                if "MemberId" in kwargs:
                    additional_context["member_id"] = kwargs["MemberId"]

        # Use the cache manager's invalidation method
        total_invalidated = self.cache_manager.invalidate_for_operation(
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            additional_context=additional_context,
        )

        # For group membership operations, also invalidate user-related cache
        if additional_context.get("affects_users"):
            user_invalidated = self.cache_manager.invalidate_for_operation(
                operation_type=operation_type,
                resource_type="user",
                resource_id=additional_context.get("member_id"),
                additional_context={"group_membership_changed": True},
            )
            total_invalidated += user_invalidated

        return total_invalidated


class CachedOrganizationsClient(CachedAWSClient):
    """Cached wrapper for AWS Organizations client."""

    def __init__(
        self,
        organizations_client: Any,
        cache_manager: Optional[ICacheManager] = None,
        ttl_config: Optional[Dict[str, timedelta]] = None,
    ):
        """
        Initialize cached Organizations client.

        Args:
            organizations_client: boto3 Organizations client
            cache_manager: Cache manager instance
            ttl_config: Custom TTL configuration
        """
        super().__init__(
            aws_client=organizations_client,
            resource_type="account",
            cache_manager=cache_manager,
            ttl_config=ttl_config,
        )


def create_cached_client(
    aws_client: Any,
    resource_type: str,
    cache_manager: Optional[ICacheManager] = None,
    ttl_config: Optional[Dict[str, timedelta]] = None,
) -> CachedAWSClient:
    """
    Factory function to create a cached AWS client wrapper.

    Args:
        aws_client: The boto3 client to wrap
        resource_type: Type of AWS resource
        cache_manager: Cache manager instance
        ttl_config: Custom TTL configuration

    Returns:
        CachedAWSClient instance
    """
    return CachedAWSClient(
        aws_client=aws_client,
        resource_type=resource_type,
        cache_manager=cache_manager,
        ttl_config=ttl_config,
    )
