"""Unit tests for cache key consistency fixes."""

from unittest.mock import Mock

from src.awsideman.cache.aws_client import CachedIdentityCenterClient, CachedIdentityStoreClient
from src.awsideman.cache.manager import CacheManager


class TestCacheKeyConsistency:
    """Test cache key consistency for AWS operations."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset cache manager singleton for clean tests
        CacheManager.reset_instance()
        self.cache_manager = CacheManager()

        # Clear any existing cache data and reset circuit breaker
        self.cache_manager.clear()
        if hasattr(self.cache_manager, "_circuit_breaker"):
            self.cache_manager._circuit_breaker.reset()

        # Mock AWS clients
        self.mock_identity_center_client = Mock()
        self.mock_identity_store_client = Mock()

        # Create cached clients
        self.cached_identity_center = CachedIdentityCenterClient(
            self.mock_identity_center_client, cache_manager=self.cache_manager
        )
        self.cached_identity_store = CachedIdentityStoreClient(
            self.mock_identity_store_client, cache_manager=self.cache_manager
        )

    def test_list_permission_sets_consistent_cache_keys(self):
        """Test that list_permission_sets generates consistent cache keys."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"

        # Mock the AWS API response
        mock_response = {
            "PermissionSets": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111",
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222",
            ]
        }
        self.mock_identity_center_client.list_permission_sets.return_value = mock_response

        # Test different ways of calling the same operation
        test_cases = [
            # Case 1: Using keyword argument
            {"kwargs": {"InstanceArn": instance_arn}},
            # Case 2: Using keyword argument with MaxResults (should generate same key)
            {"kwargs": {"InstanceArn": instance_arn, "MaxResults": 50}},
            # Case 3: Using keyword argument with different MaxResults (should generate same key)
            {"kwargs": {"InstanceArn": instance_arn, "MaxResults": 100}},
            # Case 4: Using positional argument
            {"args": (instance_arn,)},
            # Case 5: Using positional argument with MaxResults
            {"args": (instance_arn,), "kwargs": {"MaxResults": 50}},
        ]

        # Generate cache keys for all test cases
        cache_keys = []
        for i, case in enumerate(test_cases):
            args = case.get("args", ())
            kwargs = case.get("kwargs", {})

            # Generate cache key using the internal method
            cache_key = self.cached_identity_center._generate_cache_key(
                "list_permission_sets", args, kwargs
            )
            cache_keys.append(cache_key)
            print(f"Case {i+1}: args={args}, kwargs={kwargs} -> key={cache_key}")

        # All cache keys should be identical for the same logical operation
        assert len(set(cache_keys)) == 1, f"Cache keys should be identical, got: {cache_keys}"

        # Verify the cache key format
        _expected_key_pattern = (
            f"permission_set:list:{instance_arn.replace(':', '_').replace('/', '_')}"
        )
        assert cache_keys[0].startswith(
            "permission_set:list:"
        ), f"Cache key should start with 'permission_set:list:', got: {cache_keys[0]}"

    def test_list_permission_sets_different_instances_different_keys(self):
        """Test that different SSO instances generate different cache keys."""
        instance_arn_1 = "arn:aws:sso:::instance/ssoins-1111111111111111"
        instance_arn_2 = "arn:aws:sso:::instance/ssoins-2222222222222222"

        # Generate cache keys for different instances
        key_1 = self.cached_identity_center._generate_cache_key(
            "list_permission_sets", (), {"InstanceArn": instance_arn_1}
        )
        key_2 = self.cached_identity_center._generate_cache_key(
            "list_permission_sets", (), {"InstanceArn": instance_arn_2}
        )

        # Keys should be different for different instances
        assert (
            key_1 != key_2
        ), f"Different instances should generate different keys: {key_1} vs {key_2}"

    def test_list_permission_sets_pagination_handling(self):
        """Test that pagination parameters are handled correctly."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"

        # Initial request (no NextToken) - should generate same key regardless of MaxResults
        key_initial_1 = self.cached_identity_center._generate_cache_key(
            "list_permission_sets", (), {"InstanceArn": instance_arn}
        )
        key_initial_2 = self.cached_identity_center._generate_cache_key(
            "list_permission_sets", (), {"InstanceArn": instance_arn, "MaxResults": 50}
        )
        key_initial_3 = self.cached_identity_center._generate_cache_key(
            "list_permission_sets", (), {"InstanceArn": instance_arn, "MaxResults": 100}
        )

        # All initial requests should have the same cache key
        assert (
            key_initial_1 == key_initial_2 == key_initial_3
        ), f"Initial requests should have same key: {key_initial_1}, {key_initial_2}, {key_initial_3}"

        # Paginated request (with NextToken) - should generate different key
        key_paginated = self.cached_identity_center._generate_cache_key(
            "list_permission_sets",
            (),
            {"InstanceArn": instance_arn, "NextToken": "some-token", "MaxResults": 50},
        )

        # Paginated request should have different key
        assert (
            key_initial_1 != key_paginated
        ), f"Paginated request should have different key: {key_initial_1} vs {key_paginated}"

    def test_list_users_consistent_cache_keys(self):
        """Test that list_users generates consistent cache keys."""
        identity_store_id = "d-1234567890"

        # Test different ways of calling the same operation
        test_cases = [
            # Case 1: Basic call
            {"kwargs": {"IdentityStoreId": identity_store_id}},
            # Case 2: With MaxResults (should generate same key)
            {"kwargs": {"IdentityStoreId": identity_store_id, "MaxResults": 50}},
            # Case 3: With different MaxResults (should generate same key)
            {"kwargs": {"IdentityStoreId": identity_store_id, "MaxResults": 100}},
        ]

        # Generate cache keys for all test cases
        cache_keys = []
        for i, case in enumerate(test_cases):
            args = case.get("args", ())
            kwargs = case.get("kwargs", {})

            # Generate cache key using the internal method
            cache_key = self.cached_identity_store._generate_cache_key("list_users", args, kwargs)
            cache_keys.append(cache_key)
            print(f"Case {i+1}: args={args}, kwargs={kwargs} -> key={cache_key}")

        # All cache keys should be identical for the same logical operation
        assert len(set(cache_keys)) == 1, f"Cache keys should be identical, got: {cache_keys}"

    def test_cache_hit_rate_improvement(self):
        """Test that cache hit rate improves with consistent keys."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"

        # Mock the AWS API response
        mock_response = {
            "PermissionSets": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111"
            ]
        }
        self.mock_identity_center_client.list_permission_sets.return_value = mock_response

        # First call - should hit the API and cache the result
        result_1 = self.cached_identity_center.list_permission_sets(InstanceArn=instance_arn)
        assert result_1 == mock_response
        assert self.mock_identity_center_client.list_permission_sets.call_count == 1

        # Second call with same parameters - should hit cache
        result_2 = self.cached_identity_center.list_permission_sets(InstanceArn=instance_arn)
        assert result_2 == mock_response
        assert (
            self.mock_identity_center_client.list_permission_sets.call_count == 1
        )  # No additional API call

        # Third call with MaxResults - should still hit cache (same logical operation)
        result_3 = self.cached_identity_center.list_permission_sets(
            InstanceArn=instance_arn, MaxResults=50
        )
        assert result_3 == mock_response
        assert (
            self.mock_identity_center_client.list_permission_sets.call_count == 1
        )  # No additional API call

        # Fourth call with different MaxResults - should still hit cache
        result_4 = self.cached_identity_center.list_permission_sets(
            InstanceArn=instance_arn, MaxResults=100
        )
        assert result_4 == mock_response
        assert (
            self.mock_identity_center_client.list_permission_sets.call_count == 1
        )  # No additional API call

    def test_cache_statistics_show_hits(self):
        """Test that cache statistics show improved hit rates."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"

        # Mock the AWS API response
        mock_response = {"PermissionSets": []}
        self.mock_identity_center_client.list_permission_sets.return_value = mock_response

        # First call - should call the API
        result_1 = self.cached_identity_center.list_permission_sets(InstanceArn=instance_arn)
        assert result_1 == mock_response
        api_calls_after_first = self.mock_identity_center_client.list_permission_sets.call_count

        # Second call with MaxResults - should hit cache due to consistent key
        result_2 = self.cached_identity_center.list_permission_sets(
            InstanceArn=instance_arn, MaxResults=50
        )
        assert result_2 == mock_response
        api_calls_after_second = self.mock_identity_center_client.list_permission_sets.call_count

        # The second call should not have made an additional API call (cache hit)
        assert (
            api_calls_after_second == api_calls_after_first
        ), f"Second call should hit cache, but API was called {api_calls_after_second} times"

    def test_describe_permission_set_consistent_keys(self):
        """Test that describe_permission_set generates consistent cache keys."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111"
        )

        # Test different ways of calling the same operation
        key_1 = self.cached_identity_center._generate_cache_key(
            "describe_permission_set", (instance_arn, permission_set_arn), {}
        )
        key_2 = self.cached_identity_center._generate_cache_key(
            "describe_permission_set",
            (),
            {"InstanceArn": instance_arn, "PermissionSetArn": permission_set_arn},
        )

        # Both should generate the same cache key
        assert key_1 == key_2, f"Different call styles should generate same key: {key_1} vs {key_2}"
