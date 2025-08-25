"""Unit tests for cache key generation system."""

import pytest

from src.awsideman.cache.key_builder import (
    CacheKeyBuilder,
    CacheKeyValidationError,
    assignment_list_key,
    group_describe_key,
    group_list_key,
    group_members_key,
    permission_set_list_key,
    user_describe_key,
    user_list_key,
)


class TestCacheKeyBuilder:
    """Test cases for CacheKeyBuilder class."""

    def test_build_basic_key(self):
        """Test basic key building with required components."""
        key = CacheKeyBuilder.build_key("user", "list")
        assert key == "user:list"

        key = CacheKeyBuilder.build_key("user", "describe", "user-123")
        assert key == "user:describe:user-123"

        key = CacheKeyBuilder.build_key("group", "members", "group-456", "active")
        assert key == "group:members:group-456:active"

    def test_build_key_with_parameters(self):
        """Test key building with additional parameters."""
        key = CacheKeyBuilder.build_key("user", "list", MaxResults=50, Filter="active")

        # Should include parameter hash
        assert key.startswith("user:list:")
        assert len(key.split(":")) == 3

        # Same parameters should generate same key
        key2 = CacheKeyBuilder.build_key("user", "list", MaxResults=50, Filter="active")
        assert key == key2

        # Different parameters should generate different key
        key3 = CacheKeyBuilder.build_key("user", "list", MaxResults=100, Filter="active")
        assert key != key3

    def test_build_user_key(self):
        """Test user-specific key building."""
        # List users
        key = CacheKeyBuilder.build_user_key("list")
        assert key == "user:list"

        # Describe specific user
        key = CacheKeyBuilder.build_user_key("describe", "user-123")
        assert key == "user:describe:user-123"

        # With parameters
        key = CacheKeyBuilder.build_user_key("list", MaxResults=50)
        assert key.startswith("user:list:")

    def test_build_group_key(self):
        """Test group-specific key building."""
        # List groups
        key = CacheKeyBuilder.build_group_key("list")
        assert key == "group:list"

        # Describe specific group
        key = CacheKeyBuilder.build_group_key("describe", "group-456")
        assert key == "group:describe:group-456"

        # Group members
        key = CacheKeyBuilder.build_group_key("members", "group-456")
        assert key == "group:members:group-456"

        # With sub-operation
        key = CacheKeyBuilder.build_group_key("members", "group-456", "active")
        assert key == "group:members:group-456:active"

    def test_build_permission_set_key(self):
        """Test permission set key building."""
        # List permission sets
        key = CacheKeyBuilder.build_permission_set_key("list")
        assert key == "permission_set:list"

        # With ARN
        arn = "arn:aws:sso:::permissionSet/ssoins-123/ps-456"
        key = CacheKeyBuilder.build_permission_set_key("describe", arn)
        assert key == "permission_set:describe:ps-456"

        # With account ID
        key = CacheKeyBuilder.build_permission_set_key("describe", arn, "account-789")
        assert key == "permission_set:describe:ps-456:account-789"

    def test_build_assignment_key(self):
        """Test assignment key building."""
        # Basic assignment key
        key = CacheKeyBuilder.build_assignment_key("list")
        assert key == "assignment:list"

        # With account ID
        key = CacheKeyBuilder.build_assignment_key("list", account_id="123456789012")
        assert key == "assignment:list:acc-123456789012"

        # With multiple identifiers
        arn = "arn:aws:sso:::permissionSet/ssoins-123/ps-456"
        key = CacheKeyBuilder.build_assignment_key(
            "list", account_id="123456789012", permission_set_arn=arn, principal_id="user-789"
        )
        assert key == "assignment:list:acc-123456789012_ps-ps-456_prin-user-789"

    def test_build_account_key(self):
        """Test account key building."""
        # List accounts
        key = CacheKeyBuilder.build_account_key("list")
        assert key == "account:list"

        # Specific account
        key = CacheKeyBuilder.build_account_key("describe", "123456789012")
        assert key == "account:describe:123456789012"

    def test_build_invalidation_pattern(self):
        """Test invalidation pattern building."""
        # All keys
        pattern = CacheKeyBuilder.build_invalidation_pattern()
        assert pattern == "*:*:*"

        # Specific resource type
        pattern = CacheKeyBuilder.build_invalidation_pattern("user")
        assert pattern == "user:*:*"

        # Specific operation
        pattern = CacheKeyBuilder.build_invalidation_pattern("user", "list")
        assert pattern == "user:list:*"

        # Specific identifier
        pattern = CacheKeyBuilder.build_invalidation_pattern("user", "describe", "user-123")
        assert pattern == "user:describe:user-123"

    def test_parse_key(self):
        """Test key parsing functionality."""
        # Basic key
        key = "user:list"
        parsed = CacheKeyBuilder.parse_key(key)
        assert parsed["resource_type"] == "user"
        assert parsed["operation"] == "list"
        assert parsed["identifier"] is None

        # Full key
        key = "group:members:group-456:active:abc123def456"
        parsed = CacheKeyBuilder.parse_key(key)
        assert parsed["resource_type"] == "group"
        assert parsed["operation"] == "members"
        assert parsed["identifier"] == "group-456"
        assert parsed["sub_identifier"] == "active"
        assert parsed["parameters_hash"] == "abc123def456"

    def test_validate_resource_type(self):
        """Test resource type validation."""
        # Valid resource types should not raise
        for resource_type in CacheKeyBuilder.VALID_RESOURCE_TYPES:
            CacheKeyBuilder._validate_resource_type(resource_type)

        # Invalid resource type should raise
        with pytest.raises(CacheKeyValidationError, match="Invalid resource type"):
            CacheKeyBuilder._validate_resource_type("invalid_type")

        # Empty resource type should raise
        with pytest.raises(CacheKeyValidationError, match="Resource type cannot be empty"):
            CacheKeyBuilder._validate_resource_type("")

    def test_validate_operation(self):
        """Test operation validation."""
        # Valid operations should not raise
        for operation in CacheKeyBuilder.VALID_OPERATIONS:
            CacheKeyBuilder._validate_operation(operation)

        # Invalid operation should raise
        with pytest.raises(CacheKeyValidationError, match="Invalid operation"):
            CacheKeyBuilder._validate_operation("invalid_operation")

        # Empty operation should raise
        with pytest.raises(CacheKeyValidationError, match="Operation cannot be empty"):
            CacheKeyBuilder._validate_operation("")

    def test_validate_key_length(self):
        """Test key length validation."""
        # Normal length key should not raise
        normal_key = "user:list:user-123"
        CacheKeyBuilder._validate_key_length(normal_key)

        # Very long key should raise
        long_key = "x" * (CacheKeyBuilder.MAX_KEY_LENGTH + 1)
        with pytest.raises(CacheKeyValidationError, match="Cache key too long"):
            CacheKeyBuilder._validate_key_length(long_key)

    def test_sanitize_component(self):
        """Test component sanitization."""
        # Normal component should remain unchanged
        assert CacheKeyBuilder._sanitize_component("user-123") == "user-123"
        assert CacheKeyBuilder._sanitize_component("group_456") == "group_456"

        # Special characters should be replaced with underscores
        assert CacheKeyBuilder._sanitize_component("user@domain.com") == "user_domain_com"
        assert CacheKeyBuilder._sanitize_component("group/name") == "group_name"

        # Very long component should be truncated and hashed
        long_component = "x" * 100
        sanitized = CacheKeyBuilder._sanitize_component(long_component)
        assert len(sanitized) <= CacheKeyBuilder.MAX_KEY_LENGTH // 4
        assert "_" in sanitized  # Should contain hash suffix

    def test_hash_parameters(self):
        """Test parameter hashing."""
        params1 = {"MaxResults": 50, "Filter": "active"}
        params2 = {"Filter": "active", "MaxResults": 50}  # Different order
        params3 = {"MaxResults": 100, "Filter": "active"}  # Different values

        hash1 = CacheKeyBuilder._hash_parameters(params1)
        hash2 = CacheKeyBuilder._hash_parameters(params2)
        hash3 = CacheKeyBuilder._hash_parameters(params3)

        # Same parameters in different order should produce same hash
        assert hash1 == hash2

        # Different parameters should produce different hash
        assert hash1 != hash3

        # Hash should be reasonable length
        assert len(hash1) == 12

    def test_extract_permission_set_name(self):
        """Test permission set name extraction from ARN."""
        # Full ARN
        arn = "arn:aws:sso:::permissionSet/ssoins-123456789/ps-abcdef123456"
        name = CacheKeyBuilder._extract_permission_set_name(arn)
        assert name == "ps-abcdef123456"

        # Simple name (no ARN format)
        name = CacheKeyBuilder._extract_permission_set_name("simple-name")
        assert name == "simple-name"

        # Edge case with multiple slashes
        arn = "arn:aws:sso:::permissionSet/ssoins-123/sub/ps-456"
        name = CacheKeyBuilder._extract_permission_set_name(arn)
        assert name == "ps-456"

    def test_key_consistency(self):
        """Test that same inputs always produce same keys."""
        # Multiple calls with same parameters should produce same key
        key1 = CacheKeyBuilder.build_user_key("list", MaxResults=50)
        key2 = CacheKeyBuilder.build_user_key("list", MaxResults=50)
        assert key1 == key2

        # Different parameter order should produce same key
        key1 = CacheKeyBuilder.build_key("user", "list", a=1, b=2)
        key2 = CacheKeyBuilder.build_key("user", "list", b=2, a=1)
        assert key1 == key2

    def test_key_uniqueness(self):
        """Test that different inputs produce different keys."""
        keys = set()

        # Different resource types
        keys.add(CacheKeyBuilder.build_key("user", "list"))
        keys.add(CacheKeyBuilder.build_key("group", "list"))

        # Different operations
        keys.add(CacheKeyBuilder.build_key("user", "describe"))

        # Different identifiers
        keys.add(CacheKeyBuilder.build_key("user", "describe", "user-1"))
        keys.add(CacheKeyBuilder.build_key("user", "describe", "user-2"))

        # Different parameters
        keys.add(CacheKeyBuilder.build_key("user", "list", MaxResults=50))
        keys.add(CacheKeyBuilder.build_key("user", "list", MaxResults=100))

        # All keys should be unique
        assert len(keys) == 7


class TestConvenienceFunctions:
    """Test convenience functions for common operations."""

    def test_user_list_key(self):
        """Test user list convenience function."""
        key = user_list_key()
        assert key == "user:list"

        key = user_list_key(MaxResults=50)
        assert key.startswith("user:list:")

    def test_user_describe_key(self):
        """Test user describe convenience function."""
        key = user_describe_key("user-123")
        assert key == "user:describe:user-123"

        key = user_describe_key("user-123", IncludeGroups=True)
        assert key.startswith("user:describe:user-123:")

    def test_group_list_key(self):
        """Test group list convenience function."""
        key = group_list_key()
        assert key == "group:list"

    def test_group_describe_key(self):
        """Test group describe convenience function."""
        key = group_describe_key("group-456")
        assert key == "group:describe:group-456"

    def test_group_members_key(self):
        """Test group members convenience function."""
        key = group_members_key("group-456")
        assert key == "group:members:group-456"

    def test_permission_set_list_key(self):
        """Test permission set list convenience function."""
        key = permission_set_list_key()
        assert key == "permission_set:list"

    def test_assignment_list_key(self):
        """Test assignment list convenience function."""
        key = assignment_list_key("123456789012")
        assert key == "assignment:list:acc-123456789012"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_identifier(self):
        """Test handling of empty identifiers."""
        # Empty identifier should be skipped
        key = CacheKeyBuilder.build_key("user", "list", "")
        assert key == "user:list"

        # None identifier should be skipped
        key = CacheKeyBuilder.build_key("user", "list", None)
        assert key == "user:list"

    def test_special_characters_in_identifiers(self):
        """Test handling of special characters in identifiers."""
        # Special characters should be replaced with underscores
        key = CacheKeyBuilder.build_user_key("describe", "user@domain.com")
        assert "user_domain_com" in key

        # Spaces should be replaced with underscores
        key = CacheKeyBuilder.build_group_key("describe", "group with spaces")
        assert "group_with_spaces" in key

    def test_very_long_identifiers(self):
        """Test handling of very long identifiers."""
        long_id = "x" * 200
        key = CacheKeyBuilder.build_user_key("describe", long_id)

        # Key should not exceed maximum length
        assert len(key) <= CacheKeyBuilder.MAX_KEY_LENGTH

        # Should still be unique
        long_id2 = "y" * 200
        key2 = CacheKeyBuilder.build_user_key("describe", long_id2)
        assert key != key2

    def test_unicode_identifiers(self):
        """Test handling of Unicode characters in identifiers."""
        unicode_id = "user-测试-123"
        key = CacheKeyBuilder.build_user_key("describe", unicode_id)

        # Should not raise exception
        assert key is not None
        assert len(key) > 0

    def test_none_parameters(self):
        """Test handling of None parameters."""
        key = CacheKeyBuilder.build_key("user", "list", param1=None, param2="value")

        # Should handle None values gracefully
        assert key is not None

        # Same key should be generated consistently
        key2 = CacheKeyBuilder.build_key("user", "list", param1=None, param2="value")
        assert key == key2

    def test_complex_parameter_types(self):
        """Test handling of complex parameter types."""
        # List parameters
        key1 = CacheKeyBuilder.build_key("user", "list", filters=["active", "inactive"])

        # Dict parameters
        key2 = CacheKeyBuilder.build_key("user", "list", config={"max": 50, "sort": "name"})

        # Should handle complex types without error
        assert key1 is not None
        assert key2 is not None
        assert key1 != key2

    def test_parameter_order_independence(self):
        """Test that parameter order doesn't affect key generation."""
        key1 = CacheKeyBuilder.build_key(
            "user", "list", param_a="value_a", param_b="value_b", param_c="value_c"
        )

        key2 = CacheKeyBuilder.build_key(
            "user", "list", param_c="value_c", param_a="value_a", param_b="value_b"
        )

        assert key1 == key2


class TestValidationErrors:
    """Test validation error conditions."""

    def test_invalid_resource_types(self):
        """Test various invalid resource types."""
        invalid_types = ["", "invalid", "USER", "user_type", "user-type-long"]

        for invalid_type in invalid_types:
            with pytest.raises(CacheKeyValidationError):
                CacheKeyBuilder.build_key(invalid_type, "list")

    def test_invalid_operations(self):
        """Test various invalid operations."""
        invalid_operations = ["", "invalid", "LIST", "list_all", "list-operation"]

        for invalid_op in invalid_operations:
            with pytest.raises(CacheKeyValidationError):
                CacheKeyBuilder.build_key("user", invalid_op)

    def test_key_too_long(self):
        """Test key length validation with various scenarios."""
        # Very long identifier
        long_id = "x" * 300

        # Should handle gracefully by truncating/hashing
        key = CacheKeyBuilder.build_key("user", "describe", long_id)
        assert len(key) <= CacheKeyBuilder.MAX_KEY_LENGTH

        # Multiple long components
        key = CacheKeyBuilder.build_key("user", "describe", "x" * 100, "y" * 100, param1="z" * 100)
        assert len(key) <= CacheKeyBuilder.MAX_KEY_LENGTH
