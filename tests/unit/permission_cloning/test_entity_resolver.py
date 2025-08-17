"""
Unit tests for the EntityResolver class.

Tests entity validation and resolution functionality including:
- Entity existence validation
- Name to ID resolution and vice versa
- Caching behavior
- Error handling
"""

from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.permission_cloning.entity_resolver import EntityResolver
from src.awsideman.permission_cloning.models import (
    EntityReference,
    EntityType,
    ValidationResultType,
)


class TestEntityResolver:
    """Test cases for EntityResolver class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        return Mock(spec=AWSClientManager)

    @pytest.fixture
    def mock_identity_store_client(self):
        """Create a mock Identity Store client."""
        return Mock()

    @pytest.fixture
    def entity_resolver(self, mock_client_manager, mock_identity_store_client):
        """Create an EntityResolver instance with mocked dependencies."""
        mock_client_manager.get_identity_store_client.return_value = mock_identity_store_client
        return EntityResolver(mock_client_manager, "d-1234567890")

    @pytest.fixture
    def valid_user_entity(self):
        """Create a valid user entity reference."""
        return EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="testuser",
        )

    @pytest.fixture
    def valid_group_entity(self):
        """Create a valid group entity reference."""
        return EntityReference(
            entity_type=EntityType.GROUP,
            entity_id="87654321-4321-4321-4321-210987654321",
            entity_name="testgroup",
        )

    def test_init(self, mock_client_manager):
        """Test EntityResolver initialization."""
        identity_store_id = "d-1234567890"
        resolver = EntityResolver(mock_client_manager, identity_store_id)

        assert resolver.client_manager == mock_client_manager
        assert resolver.identity_store_id == identity_store_id
        assert resolver._identity_store_client is None
        assert resolver._user_cache == {}
        assert resolver._group_cache == {}
        assert resolver._user_name_to_id_cache == {}
        assert resolver._group_name_to_id_cache == {}

    def test_identity_store_client_property(self, entity_resolver, mock_identity_store_client):
        """Test that the identity_store_client property creates and caches the client."""
        # First access should create the client
        client = entity_resolver.identity_store_client
        assert client == mock_identity_store_client
        assert entity_resolver._identity_store_client == mock_identity_store_client

        # Second access should return the cached client
        client2 = entity_resolver.identity_store_client
        assert client2 == mock_identity_store_client
        assert entity_resolver.client_manager.get_identity_store_client.call_count == 1

    def test_validate_entity_success(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test successful entity validation."""
        # Mock successful user lookup
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }

        result = entity_resolver.validate_entity(valid_user_entity)

        assert result.is_valid
        assert result.result_type == ValidationResultType.SUCCESS
        assert result.messages == []

    def test_validate_entity_structure_error(self, entity_resolver):
        """Test entity validation with invalid structure."""
        invalid_entity = EntityReference(
            entity_type=EntityType.USER,
            entity_id="invalid-id",  # Invalid UUID format
            entity_name="testuser",
        )

        result = entity_resolver.validate_entity(invalid_entity)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Entity ID must be a valid UUID format" in result.messages[0]

    def test_validate_entity_not_found(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test entity validation when entity doesn't exist."""
        # Mock user not found
        mock_identity_store_client.describe_user.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}},
            "DescribeUser",
        )

        result = entity_resolver.validate_entity(valid_user_entity)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "USER with ID 12345678-1234-1234-1234-123456789012 not found" in result.messages[0]

    def test_validate_entity_name_mismatch_warning(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test entity validation with name mismatch warning."""
        # First, populate cache with different name
        entity_resolver._user_cache[valid_user_entity.entity_id] = {
            "UserId": valid_user_entity.entity_id,
            "UserName": "differentname",
            "DisplayName": "Different User",
        }

        # Mock successful user lookup
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": "differentname",
            "DisplayName": "Different User",
        }

        result = entity_resolver.validate_entity(valid_user_entity)

        assert result.has_warnings
        assert result.result_type == ValidationResultType.WARNING
        assert "Entity name mismatch" in result.messages[0]

    def test_resolve_entity_by_id_user_success(self, entity_resolver, mock_identity_store_client):
        """Test successful user resolution by ID."""
        user_id = "12345678-1234-1234-1234-123456789012"
        mock_identity_store_client.describe_user.return_value = {
            "UserId": user_id,
            "UserName": "testuser",
            "DisplayName": "Test User",
        }

        result = entity_resolver.resolve_entity_by_id(EntityType.USER, user_id)

        assert result is not None
        assert result.entity_type == EntityType.USER
        assert result.entity_id == user_id
        assert result.entity_name == "testuser"

    def test_resolve_entity_by_id_group_success(self, entity_resolver, mock_identity_store_client):
        """Test successful group resolution by ID."""
        group_id = "87654321-4321-4321-4321-210987654321"
        mock_identity_store_client.describe_group.return_value = {
            "GroupId": group_id,
            "DisplayName": "testgroup",
            "Description": "Test Group",
        }

        result = entity_resolver.resolve_entity_by_id(EntityType.GROUP, group_id)

        assert result is not None
        assert result.entity_type == EntityType.GROUP
        assert result.entity_id == group_id
        assert result.entity_name == "testgroup"

    def test_resolve_entity_by_id_not_found(self, entity_resolver, mock_identity_store_client):
        """Test entity resolution by ID when entity doesn't exist."""
        user_id = "12345678-1234-1234-1234-123456789012"
        mock_identity_store_client.describe_user.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}},
            "DescribeUser",
        )

        result = entity_resolver.resolve_entity_by_id(EntityType.USER, user_id)

        assert result is None

    def test_resolve_entity_by_name_user_success(self, entity_resolver, mock_identity_store_client):
        """Test successful user resolution by name."""
        user_name = "testuser"
        user_id = "12345678-1234-1234-1234-123456789012"

        mock_identity_store_client.list_users.return_value = {
            "Users": [{"UserId": user_id, "UserName": user_name, "DisplayName": "Test User"}]
        }

        result = entity_resolver.resolve_entity_by_name(EntityType.USER, user_name)

        assert result is not None
        assert result.entity_type == EntityType.USER
        assert result.entity_id == user_id
        assert result.entity_name == user_name

    def test_resolve_entity_by_name_group_success(
        self, entity_resolver, mock_identity_store_client
    ):
        """Test successful group resolution by name."""
        group_name = "testgroup"
        group_id = "87654321-4321-4321-4321-210987654321"

        mock_identity_store_client.list_groups.return_value = {
            "Groups": [
                {"GroupId": group_id, "DisplayName": group_name, "Description": "Test Group"}
            ]
        }

        result = entity_resolver.resolve_entity_by_name(EntityType.GROUP, group_name)

        assert result is not None
        assert result.entity_type == EntityType.GROUP
        assert result.entity_id == group_id
        assert result.entity_name == group_name

    def test_resolve_entity_by_name_not_found(self, entity_resolver, mock_identity_store_client):
        """Test entity resolution by name when entity doesn't exist."""
        user_name = "nonexistentuser"
        mock_identity_store_client.list_users.return_value = {"Users": []}

        result = entity_resolver.resolve_entity_by_name(EntityType.USER, user_name)

        assert result is None

    def test_validate_entities_all_valid(
        self, entity_resolver, valid_user_entity, valid_group_entity, mock_identity_store_client
    ):
        """Test validation of multiple entities when all are valid."""
        # Mock successful lookups
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }
        mock_identity_store_client.describe_group.return_value = {
            "GroupId": valid_group_entity.entity_id,
            "DisplayName": valid_group_entity.entity_name,
            "Description": "Test Group",
        }

        result = entity_resolver.validate_entities([valid_user_entity, valid_group_entity])

        assert result.is_valid
        assert result.result_type == ValidationResultType.SUCCESS
        assert result.messages == []

    def test_validate_entities_some_invalid(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test validation of multiple entities when some are invalid."""
        invalid_entity = EntityReference(
            entity_type=EntityType.USER, entity_id="invalid-id", entity_name="invaliduser"
        )

        # Mock successful lookup for valid entity
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }

        result = entity_resolver.validate_entities([valid_user_entity, invalid_entity])

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Entity 2:" in result.messages[0]

    def test_check_entities_exist(
        self, entity_resolver, valid_user_entity, valid_group_entity, mock_identity_store_client
    ):
        """Test checking which entities exist."""
        # Mock successful user lookup, failed group lookup
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }
        mock_identity_store_client.describe_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Group not found"}},
            "DescribeGroup",
        )

        existing, errors = entity_resolver.check_entities_exist(
            [valid_user_entity, valid_group_entity]
        )

        assert len(existing) == 1
        assert existing[0] == valid_user_entity
        assert len(errors) == 1
        assert "GROUP with ID 87654321-4321-4321-4321-210987654321 not found" in errors[0]

    def test_user_caching(self, entity_resolver, mock_identity_store_client):
        """Test that user information is properly cached."""
        user_id = "12345678-1234-1234-1234-123456789012"
        user_name = "testuser"

        mock_identity_store_client.describe_user.return_value = {
            "UserId": user_id,
            "UserName": user_name,
            "DisplayName": "Test User",
        }

        # First call should hit the API
        result1 = entity_resolver._get_user_by_id(user_id)
        assert result1 is not None
        assert mock_identity_store_client.describe_user.call_count == 1

        # Second call should use cache
        result2 = entity_resolver._get_user_by_id(user_id)
        assert result2 == result1
        assert mock_identity_store_client.describe_user.call_count == 1

        # Check that name-to-id cache is also populated
        assert entity_resolver._user_name_to_id_cache[user_name] == user_id

    def test_group_caching(self, entity_resolver, mock_identity_store_client):
        """Test that group information is properly cached."""
        group_id = "87654321-4321-4321-4321-210987654321"
        group_name = "testgroup"

        mock_identity_store_client.describe_group.return_value = {
            "GroupId": group_id,
            "DisplayName": group_name,
            "Description": "Test Group",
        }

        # First call should hit the API
        result1 = entity_resolver._get_group_by_id(group_id)
        assert result1 is not None
        assert mock_identity_store_client.describe_group.call_count == 1

        # Second call should use cache
        result2 = entity_resolver._get_group_by_id(group_id)
        assert result2 == result1
        assert mock_identity_store_client.describe_group.call_count == 1

        # Check that name-to-id cache is also populated
        assert entity_resolver._group_name_to_id_cache[group_name] == group_id

    def test_get_user_by_name_with_cache(self, entity_resolver, mock_identity_store_client):
        """Test getting user by name uses cache when available."""
        user_id = "12345678-1234-1234-1234-123456789012"
        user_name = "testuser"

        # Populate cache first
        entity_resolver._user_name_to_id_cache[user_name] = user_id
        entity_resolver._user_cache[user_id] = {
            "UserId": user_id,
            "UserName": user_name,
            "DisplayName": "Test User",
        }

        result = entity_resolver._get_user_by_name(user_name)

        assert result is not None
        assert result["UserId"] == user_id
        assert result["UserName"] == user_name
        # Should not call the API since we used cache
        assert mock_identity_store_client.list_users.call_count == 0

    def test_get_group_by_name_with_cache(self, entity_resolver, mock_identity_store_client):
        """Test getting group by name uses cache when available."""
        group_id = "87654321-4321-4321-4321-210987654321"
        group_name = "testgroup"

        # Populate cache first
        entity_resolver._group_name_to_id_cache[group_name] = group_id
        entity_resolver._group_cache[group_id] = {
            "GroupId": group_id,
            "DisplayName": group_name,
            "Description": "Test Group",
        }

        result = entity_resolver._get_group_by_name(group_name)

        assert result is not None
        assert result["GroupId"] == group_id
        assert result["DisplayName"] == group_name
        # Should not call the API since we used cache
        assert mock_identity_store_client.list_groups.call_count == 0

    def test_clear_cache(self, entity_resolver):
        """Test that clear_cache removes all cached data."""
        # Populate caches
        entity_resolver._user_cache["user1"] = {"UserName": "test"}
        entity_resolver._group_cache["group1"] = {"DisplayName": "test"}
        entity_resolver._user_name_to_id_cache["testuser"] = "user1"
        entity_resolver._group_name_to_id_cache["testgroup"] = "group1"

        # Clear cache
        entity_resolver.clear_cache()

        # Verify all caches are empty
        assert entity_resolver._user_cache == {}
        assert entity_resolver._group_cache == {}
        assert entity_resolver._user_name_to_id_cache == {}
        assert entity_resolver._group_name_to_id_cache == {}

    def test_get_cached_entity_name_user(self, entity_resolver):
        """Test getting cached entity name for user."""
        user_id = "12345678-1234-1234-1234-123456789012"
        user_name = "testuser"

        # Populate cache
        entity_resolver._user_cache[user_id] = {
            "UserId": user_id,
            "UserName": user_name,
            "DisplayName": "Test User",
        }

        result = entity_resolver._get_cached_entity_name(EntityType.USER, user_id)
        assert result == user_name

    def test_get_cached_entity_name_group(self, entity_resolver):
        """Test getting cached entity name for group."""
        group_id = "87654321-4321-4321-4321-210987654321"
        group_name = "testgroup"

        # Populate cache
        entity_resolver._group_cache[group_id] = {
            "GroupId": group_id,
            "DisplayName": group_name,
            "Description": "Test Group",
        }

        result = entity_resolver._get_cached_entity_name(EntityType.GROUP, group_id)
        assert result == group_name

    def test_get_cached_entity_name_not_cached(self, entity_resolver):
        """Test getting cached entity name when not cached."""
        user_id = "12345678-1234-1234-1234-123456789012"

        result = entity_resolver._get_cached_entity_name(EntityType.USER, user_id)
        assert result is None

    def test_aws_error_handling(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test handling of various AWS errors."""
        # Test throttling error
        mock_identity_store_client.describe_user.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "DescribeUser"
        )

        result = entity_resolver.validate_entity(valid_user_entity)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "AWS error checking USER" in result.messages[0]

    def test_generic_exception_handling(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test handling of generic exceptions."""
        mock_identity_store_client.describe_user.side_effect = Exception("Unexpected error")

        result = entity_resolver.validate_entity(valid_user_entity)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Error checking USER: Unexpected error" in result.messages[0]

    def test_get_cache_stats(self, entity_resolver):
        """Test getting cache statistics."""
        # Populate caches
        entity_resolver._user_cache["user1"] = {"UserName": "test"}
        entity_resolver._group_cache["group1"] = {"DisplayName": "test"}
        entity_resolver._user_name_to_id_cache["testuser"] = "user1"
        entity_resolver._group_name_to_id_cache["testgroup"] = "group1"

        stats = entity_resolver.get_cache_stats()

        assert stats["user_cache_size"] == 1
        assert stats["group_cache_size"] == 1
        assert stats["user_name_to_id_cache_size"] == 1
        assert stats["group_name_to_id_cache_size"] == 1

    def test_warm_cache_for_entities(
        self, entity_resolver, valid_user_entity, valid_group_entity, mock_identity_store_client
    ):
        """Test warming cache for entities."""
        # Mock successful lookups
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }
        mock_identity_store_client.describe_group.return_value = {
            "GroupId": valid_group_entity.entity_id,
            "DisplayName": valid_group_entity.entity_name,
            "Description": "Test Group",
        }

        # Warm cache
        entity_resolver.warm_cache_for_entities([valid_user_entity, valid_group_entity])

        # Verify caches are populated
        assert valid_user_entity.entity_id in entity_resolver._user_cache
        assert valid_group_entity.entity_id in entity_resolver._group_cache
        assert valid_user_entity.entity_name in entity_resolver._user_name_to_id_cache
        assert valid_group_entity.entity_name in entity_resolver._group_name_to_id_cache

    def test_warm_cache_for_entities_with_failure(
        self, entity_resolver, valid_user_entity, mock_identity_store_client
    ):
        """Test warming cache when some entities fail to load."""
        # Mock successful user lookup, failed group lookup
        mock_identity_store_client.describe_user.return_value = {
            "UserId": valid_user_entity.entity_id,
            "UserName": valid_user_entity.entity_name,
            "DisplayName": "Test User",
        }
        mock_identity_store_client.describe_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Group not found"}},
            "DescribeGroup",
        )

        invalid_group = EntityReference(
            entity_type=EntityType.GROUP, entity_id="invalid-group-id", entity_name="invalidgroup"
        )

        # Warm cache - should not fail even with errors
        entity_resolver.warm_cache_for_entities([valid_user_entity, invalid_group])

        # Verify user cache is populated
        assert valid_user_entity.entity_id in entity_resolver._user_cache
        # Verify group cache is not populated due to error
        assert invalid_group.entity_id not in entity_resolver._group_cache

    def test_search_entities_user_success(self, entity_resolver, mock_identity_store_client):
        """Test successful user search."""
        search_term = "test"
        user_id = "12345678-1234-1234-1234-123456789012"
        user_name = "testuser"

        mock_identity_store_client.list_users.return_value = {
            "Users": [{"UserId": user_id, "UserName": user_name, "DisplayName": "Test User"}]
        }

        results = entity_resolver.search_entities(EntityType.USER, search_term)

        assert len(results) == 1
        assert results[0].entity_type == EntityType.USER
        assert results[0].entity_id == user_id
        assert results[0].entity_name == user_name

    def test_search_entities_group_success(self, entity_resolver, mock_identity_store_client):
        """Test successful group search."""
        search_term = "test"
        group_id = "87654321-4321-4321-4321-210987654321"
        group_name = "testgroup"

        mock_identity_store_client.list_groups.return_value = {
            "Groups": [
                {"GroupId": group_id, "DisplayName": group_name, "Description": "Test Group"}
            ]
        }

        results = entity_resolver.search_entities(EntityType.GROUP, search_term)

        assert len(results) == 1
        assert results[0].entity_type == EntityType.GROUP
        assert results[0].entity_id == group_id
        assert results[0].entity_name == group_name

    def test_search_entities_no_results(self, entity_resolver, mock_identity_store_client):
        """Test search with no results."""
        search_term = "nonexistent"

        mock_identity_store_client.list_users.return_value = {"Users": []}

        results = entity_resolver.search_entities(EntityType.USER, search_term)

        assert len(results) == 0

    def test_search_entities_with_error(self, entity_resolver, mock_identity_store_client):
        """Test search when AWS API returns an error."""
        search_term = "test"

        mock_identity_store_client.list_users.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "ListUsers"
        )

        results = entity_resolver.search_entities(EntityType.USER, search_term)

        assert len(results) == 0
