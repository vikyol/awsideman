"""Cached AWS client wrapper for transparent caching of AWS API calls."""

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from ..cache.manager import CacheManager
from ..utils.models import CacheConfig
from .manager import (
    AWSClientManager,
    IdentityCenterClientWrapper,
    IdentityStoreClientWrapper,
    OrganizationsClientWrapper,
)

logger = logging.getLogger(__name__)


class CachedAwsClient:
    """
    Wrapper around AWSClientManager that provides transparent caching of AWS API calls.

    This class intercepts AWS API calls and checks the cache before making actual
    API requests. Successful responses are cached for future use based on TTL settings.
    """

    def __init__(
        self, client_manager: AWSClientManager, cache_manager: Optional[CacheManager] = None
    ):
        """
        Initialize the cached AWS client.

        Args:
            client_manager: AWSClientManager instance for AWS API calls
            cache_manager: Optional CacheManager instance. If None, creates a new one.
        """
        self.client_manager = client_manager
        self.cache_manager = cache_manager or CacheManager()

        # Track which operations are cacheable (read-only operations)
        self._cacheable_operations = {
            # Organizations operations
            "list_roots",
            "list_organizational_units_for_parent",
            "list_accounts_for_parent",
            # "list_accounts",  # Temporarily disable caching for debugging
            "describe_account",
            "list_tags_for_resource",
            "list_policies_for_target",
            "list_parents",
            # Identity Center operations
            "list_instances",
            "list_permission_sets",
            "describe_permission_set",
            "list_accounts_for_provisioned_permission_set",
            "list_permission_sets_provisioned_to_account",
            "describe_instance",
            # Permission Set operations (enhanced)
            "list_managed_policies_in_permission_set",
            "get_inline_policy_for_permission_set",
            "list_customer_managed_policy_references_in_permission_set",
            # Assignment operations (enhanced)
            "list_account_assignments",
            "list_permission_sets_provisioned_to_account",
            "list_accounts_for_provisioned_permission_set",
            # Identity Store operations
            "list_users",
            "list_groups",
            "describe_user",
            "describe_group",
            "list_group_memberships",
        }

    def get_organizations_client(self) -> "CachedOrganizationsClient":
        """
        Get a cached Organizations client.

        Returns:
            CachedOrganizationsClient instance
        """
        return CachedOrganizationsClient(self.client_manager, self.cache_manager)

    def get_identity_center_client(self) -> "CachedIdentityCenterClient":
        """
        Get a cached Identity Center client.

        Returns:
            CachedIdentityCenterClient instance
        """
        return CachedIdentityCenterClient(self.client_manager, self.cache_manager)

    def get_identity_store_client(self) -> "CachedIdentityStoreClient":
        """
        Get a cached Identity Store client.

        Returns:
            CachedIdentityStoreClient instance
        """
        return CachedIdentityStoreClient(self.client_manager, self.cache_manager)

    def _generate_cache_key(self, operation: str, params: Dict[str, Any]) -> str:
        """
        Generate a deterministic cache key based on operation and parameters.

        Args:
            operation: AWS operation name
            params: Operation parameters

        Returns:
            Cache key string
        """
        # Create a deterministic representation of the parameters
        # Sort keys to ensure consistent ordering
        sorted_params = json.dumps(params, sort_keys=True, default=str)

        # Include profile and region in the key to avoid conflicts
        profile = getattr(self.client_manager, "profile", "default") or "default"
        region = getattr(self.client_manager, "region", "us-east-1") or "us-east-1"

        # Create the key components
        key_data = f"{operation}:{sorted_params}:{profile}:{region}"

        # Generate a hash for the key to keep it manageable
        key_hash = hashlib.sha256(key_data.encode("utf-8")).hexdigest()

        # Return a readable key with hash
        return f"{operation}_{key_hash[:16]}"

    def _is_cacheable_operation(self, operation: str) -> bool:
        """
        Check if an operation is cacheable (read-only).

        Args:
            operation: AWS operation name

        Returns:
            True if operation is cacheable, False otherwise
        """
        return operation in self._cacheable_operations

    def _execute_with_cache(
        self, operation: str, params: Dict[str, Any], api_call: Callable[[], Any]
    ) -> Any:
        """
        Execute an AWS API call with caching support.

        Args:
            operation: AWS operation name
            params: Operation parameters
            api_call: Function that makes the actual API call

        Returns:
            API response (from cache or fresh API call)
        """
        # Check if operation is cacheable
        if not self._is_cacheable_operation(operation):
            logger.debug(f"Operation {operation} is not cacheable, calling API directly")
            return api_call()

        # Generate cache key - if this fails, fall back to API call
        try:
            cache_key = self._generate_cache_key(operation, params)
            logger.debug(f"Generated cache key: {cache_key} for operation {operation}")
        except Exception as e:
            logger.warning(f"Failed to generate cache key for operation {operation}: {e}")
            logger.debug(f"Falling back to API call for operation {operation}")
            return api_call()

        # Try to get from cache - if cache fails, fall back to API call
        try:
            logger.debug(f"Checking cache for key: {cache_key}")
            cached_result = self.cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for operation {operation}")
                return cached_result
            else:
                logger.debug(f"Cache miss for operation {operation}")
        except Exception as e:
            logger.warning(f"Cache retrieval failed for operation {operation}: {e}")
            logger.debug(f"Falling back to API call for operation {operation}")
            # Continue to API call - don't return here

        # Cache miss or cache failure - call the API
        logger.debug(f"Cache miss for operation {operation}, calling API")
        try:
            result = api_call()

            # Try to cache the successful result - if caching fails, log but don't fail the operation
            try:
                logger.debug(f"Storing result in cache with key: {cache_key}")
                self.cache_manager.set(cache_key, result)
                logger.debug(f"Successfully cached result for operation {operation}")
            except Exception as cache_error:
                logger.warning(f"Failed to cache result for operation {operation}: {cache_error}")
                # Continue - the API call was successful even if caching failed

            return result

        except Exception as e:
            logger.debug(f"API call failed for operation {operation}: {e}")
            # Don't cache errors, just re-raise
            raise


class CachedOrganizationsClient:
    """
    Cached wrapper for OrganizationsClient that provides transparent caching.

    This class maintains the same interface as OrganizationsClient but adds
    caching capabilities for all read operations.
    """

    def __init__(self, client_manager: AWSClientManager, cache_manager: CacheManager):
        """
        Initialize the cached Organizations client.

        Args:
            client_manager: AWSClientManager instance
            cache_manager: CacheManager instance for caching
        """
        self.client_manager = client_manager
        self.cache_manager = cache_manager
        self._cached_aws_client = CachedAwsClient(client_manager, cache_manager)
        self._organizations_client = OrganizationsClientWrapper(client_manager)

    @property
    def client(self):
        """Get the underlying Organizations client for compatibility."""
        return self._organizations_client.client

    def list_roots(self) -> List[Dict[str, Any]]:
        """
        List all roots in the organization (cached).

        Returns:
            List of root dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_roots", {}, lambda: self._organizations_client.list_roots()
        )

    def list_organizational_units_for_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List organizational units for a given parent (cached).

        Args:
            parent_id: The unique identifier of the parent root or OU

        Returns:
            List of OU dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_organizational_units_for_parent",
            {"parent_id": parent_id},
            lambda: self._organizations_client.list_organizational_units_for_parent(parent_id),
        )

    def list_accounts_for_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List accounts for a given parent (cached).

        Args:
            parent_id: The unique identifier of the parent root or OU

        Returns:
            List of account dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_accounts_for_parent",
            {"parent_id": parent_id},
            lambda: self._organizations_client.list_accounts_for_parent(parent_id),
        )

    def list_accounts(self) -> Dict[str, Any]:
        """
        List all accounts in the organization (cached).

        Returns:
            Dictionary with 'Accounts' key containing list of account dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_accounts",
            {},
            lambda: self._organizations_client.list_accounts(),
        )

    def describe_account(self, account_id: str) -> Dict[str, Any]:
        """
        Get detailed information about an account (cached).

        Args:
            account_id: The unique identifier of the account

        Returns:
            Account dictionary
        """
        return self._cached_aws_client._execute_with_cache(
            "describe_account",
            {"account_id": account_id},
            lambda: self._organizations_client.describe_account(account_id),
        )

    def list_tags_for_resource(self, resource_id: str) -> Dict[str, Any]:
        """
        List tags for a resource (cached).

        Args:
            resource_id: The unique identifier of the resource

        Returns:
            Dictionary with 'Tags' key containing list of tag dictionaries
        """
        tags = self._cached_aws_client._execute_with_cache(
            "list_tags_for_resource",
            {"resource_id": resource_id},
            lambda: self._organizations_client.list_tags_for_resource(resource_id),
        )
        return {"Tags": tags}

    def list_policies_for_target(self, target_id: str, filter_type: str) -> List[Dict[str, Any]]:
        """
        List policies attached to a target (cached).

        Args:
            target_id: The unique identifier of the target
            filter_type: The type of policy to filter by

        Returns:
            List of policy dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_policies_for_target",
            {"target_id": target_id, "filter_type": filter_type},
            lambda: self._organizations_client.list_policies_for_target(target_id, filter_type),
        )

    def list_parents(self, child_id: str) -> List[Dict[str, Any]]:
        """
        List the parents of a child (cached).

        Args:
            child_id: The unique identifier of the child

        Returns:
            List of parent dictionaries
        """
        return self._cached_aws_client._execute_with_cache(
            "list_parents",
            {"child_id": child_id},
            lambda: self._organizations_client.list_parents(child_id),
        )

    def get_paginator(self, operation_name: str):
        """
        Get a paginator for the specified operation.

        Args:
            operation_name: Name of the operation to get a paginator for

        Returns:
            Paginator object for the specified operation
        """
        # Delegate to the underlying organizations client
        return self._organizations_client.client.get_paginator(operation_name)

    def __getattr__(self, name):
        """
        Intercept method calls and delegate to the underlying organizations client.

        Args:
            name: Method name being called

        Returns:
            Result from the underlying client
        """
        # Delegate to the underlying organizations client for any missing methods
        return getattr(self._organizations_client.client, name)


def create_cached_client_manager(
    profile: Optional[str] = None,
    region: Optional[str] = None,
    cache_config: Optional[CacheConfig] = None,
) -> CachedAwsClient:
    """
    Factory function to create a CachedAwsClient with proper initialization.

    Args:
        profile: AWS profile name to use
        region: AWS region to use
        cache_config: Optional cache configuration

    Returns:
        CachedAwsClient instance ready for use
    """
    # Create the underlying AWS client manager
    client_manager = AWSClientManager(profile=profile, region=region)

    # Create cache manager with optional config
    cache_manager = CacheManager()

    # Create and return the cached client
    return CachedAwsClient(client_manager, cache_manager)


class CachedIdentityCenterClient:
    """
    Cached wrapper for IdentityCenterClientWrapper that provides transparent caching.

    This class maintains the same interface as IdentityCenterClientWrapper but adds
    caching capabilities for all read operations.
    """

    def __init__(self, client_manager: AWSClientManager, cache_manager: CacheManager):
        """
        Initialize the cached Identity Center client.

        Args:
            client_manager: AWSClientManager instance
            cache_manager: CacheManager instance for caching
        """
        self.client_manager = client_manager
        self.cache_manager = cache_manager
        self._cached_aws_client = CachedAwsClient(client_manager, cache_manager)
        self._identity_center_client = IdentityCenterClientWrapper(client_manager)

    @property
    def client(self):
        """Get the underlying Identity Center client for compatibility."""
        return self._identity_center_client.client

    def __getattr__(self, name):
        """
        Intercept method calls and provide caching for cacheable operations.

        Args:
            name: Method name being called

        Returns:
            Cached or fresh result from the API call
        """
        # Get the original method from the underlying client
        original_method = getattr(self._identity_center_client, name)

        # If this is not a cacheable operation, just call it directly
        if not self._cached_aws_client._is_cacheable_operation(name):
            return original_method

        # Return a wrapper function that provides caching
        def cached_method(*args, **kwargs):
            # Convert args and kwargs to a parameters dict for cache key generation
            params = {}
            if args:
                # For positional args, we need to map them to parameter names
                # This is a simplified approach - in practice, you might want to inspect
                # the method signature to get proper parameter names
                if name == "describe_instance" and len(args) >= 1:
                    params["instance_arn"] = args[0]
                elif name == "list_permission_sets" and len(args) >= 1:
                    params["instance_arn"] = args[0]
                elif name == "describe_permission_set" and len(args) >= 2:
                    params["instance_arn"] = args[0]
                    params["permission_set_arn"] = args[1]
                elif name == "list_accounts_for_provisioned_permission_set" and len(args) >= 2:
                    params["instance_arn"] = args[0]
                    params["permission_set_arn"] = args[1]
                elif name == "list_permission_sets_provisioned_to_account" and len(args) >= 2:
                    params["instance_arn"] = args[0]
                    params["account_id"] = args[1]

            # Add kwargs to params
            params.update(kwargs)

            # Execute the API call with caching
            def api_call():
                return original_method(*args, **kwargs)

            result = self._cached_aws_client._execute_with_cache(name, params, api_call)

            return result

        return cached_method


class CachedIdentityStoreClient:
    """
    Cached wrapper for IdentityStoreClientWrapper that provides transparent caching.

    This class maintains the same interface as IdentityStoreClientWrapper but adds
    caching capabilities for all read operations.
    """

    def __init__(self, client_manager: AWSClientManager, cache_manager: CacheManager):
        """
        Initialize the cached Identity Store client.

        Args:
            client_manager: AWSClientManager instance
            cache_manager: CacheManager instance for caching
        """
        self.client_manager = client_manager
        self.cache_manager = cache_manager
        self._cached_aws_client = CachedAwsClient(client_manager, cache_manager)
        self._identity_store_client = IdentityStoreClientWrapper(client_manager)

    @property
    def client(self):
        """Get the underlying Identity Store client for compatibility."""
        return self._identity_store_client.client

    def __getattr__(self, name):
        """
        Intercept method calls and provide caching for cacheable operations.

        Args:
            name: Method name being called

        Returns:
            Cached or fresh result from the API call
        """
        # Get the original method from the underlying client
        original_method = getattr(self._identity_store_client, name)

        # If this is not a cacheable operation, just call it directly
        if not self._cached_aws_client._is_cacheable_operation(name):
            return original_method

        # Return a wrapper function that provides caching
        def cached_method(*args, **kwargs):
            # Convert args and kwargs to a parameters dict for cache key generation
            params = {}
            if args:
                # For positional args, we need to map them to parameter names
                # This is a simplified approach - in practice, you might want to inspect
                # the method signature to get proper parameter names
                if name == "describe_user" and len(args) >= 2:
                    params["identity_store_id"] = args[0]
                    params["user_id"] = args[1]
                elif name == "describe_group" and len(args) >= 2:
                    params["identity_store_id"] = args[0]
                    params["group_id"] = args[1]
                elif name == "list_group_memberships" and len(args) >= 2:
                    params["identity_store_id"] = args[0]
                    params["group_id"] = args[1]
                elif name in ["list_users", "list_groups"] and len(args) >= 1:
                    params["identity_store_id"] = args[0]

            # Add kwargs to params
            params.update(kwargs)

            # Execute the API call with caching
            def api_call():
                return original_method(*args, **kwargs)

            result = self._cached_aws_client._execute_with_cache(name, params, api_call)

            return result

        return cached_method
