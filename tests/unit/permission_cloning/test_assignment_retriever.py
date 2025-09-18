"""
Unit tests for the AssignmentRetriever class.

Tests assignment retrieval functionality including:
- User assignment retrieval
- Group assignment retrieval
- Caching behavior
- Error handling
- Performance optimizations
"""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.permission_cloning.assignment_retriever import AssignmentRetriever
from src.awsideman.permission_cloning.models import (
    EntityReference,
    EntityType,
    PermissionAssignment,
)


class TestAssignmentRetriever:
    """Test cases for AssignmentRetriever class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        return Mock(spec=AWSClientManager)

    @pytest.fixture
    def mock_sso_admin_client(self):
        """Create a mock SSO Admin client."""
        return Mock()

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock Organizations client."""
        return Mock()

    @pytest.fixture
    def mock_entity_resolver(self):
        """Create a mock EntityResolver."""
        return Mock()

    @pytest.fixture
    def assignment_retriever(
        self, mock_client_manager, mock_sso_admin_client, mock_organizations_client
    ):
        """Create an AssignmentRetriever instance with mocked dependencies."""
        mock_client_manager.get_identity_center_client.return_value = mock_sso_admin_client
        mock_client_manager.get_organizations_client.return_value = mock_organizations_client

        # Mock the EntityResolver constructor
        with patch(
            "src.awsideman.permission_cloning.assignment_retriever.EntityResolver"
        ) as mock_resolver_class:
            mock_resolver_class.return_value = Mock()
            retriever = AssignmentRetriever(
                mock_client_manager, "arn:aws:sso:::instance/ssoins-123", "d-1234567890"
            )
            retriever.entity_resolver = mock_resolver_class.return_value
            return retriever

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

    @pytest.fixture
    def sample_permission_sets(self):
        """Sample permission sets for testing."""
        return [
            "arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
            "arn:aws:sso:::permissionSet/ssoins-123/ps-developer",
        ]

    @pytest.fixture
    def sample_accounts(self):
        """Sample accounts for testing."""
        return [
            {"Id": "123456789012", "Name": "Production"},
            {"Id": "098765432109", "Name": "Development"},
            {"Id": "555555555555", "Name": "Staging"},
        ]

    @pytest.fixture
    def sample_assignments(self):
        """Sample PermissionAssignment objects for testing."""
        from src.awsideman.permission_cloning.models import PermissionAssignment

        return [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="123456789012",
                account_name="Production",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
                permission_set_name="ReadOnlyAccess",
                account_id="098765432109",
                account_name="Development",
            ),
        ]

    def test_init(self, mock_client_manager):
        """Test AssignmentRetriever initialization."""
        instance_arn = "arn:aws:sso:::instance/ssoins-123"
        identity_store_id = "d-1234567890"

        with patch("src.awsideman.permission_cloning.assignment_retriever.EntityResolver"):
            retriever = AssignmentRetriever(mock_client_manager, instance_arn, identity_store_id)

            assert retriever.client_manager == mock_client_manager
            assert retriever.instance_arn == instance_arn
            assert retriever.identity_store_id == identity_store_id
            assert retriever._sso_admin_client is None
            assert retriever._organizations_client is None
            assert retriever._user_assignments_cache == {}
            assert retriever._group_assignments_cache == {}

    def test_sso_admin_client_property(self, assignment_retriever, mock_sso_admin_client):
        """Test that the sso_admin_client property creates and caches the client."""
        # First access should create the client
        client = assignment_retriever.sso_admin_client
        assert client == mock_sso_admin_client
        assert assignment_retriever._sso_admin_client == mock_sso_admin_client

        # Second access should return the cached client
        client2 = assignment_retriever.sso_admin_client
        assert client2 == mock_sso_admin_client
        assert assignment_retriever.client_manager.get_identity_center_client.call_count == 1

    def test_organizations_client_property(self, assignment_retriever, mock_organizations_client):
        """Test that the organizations_client property creates and caches the client."""
        # First access should create the client
        client = assignment_retriever.organizations_client
        assert client == mock_organizations_client
        assert assignment_retriever._organizations_client == mock_organizations_client

        # Second access should return the cached client
        client2 = assignment_retriever.organizations_client
        assert client2 == mock_organizations_client
        assert assignment_retriever.client_manager.get_organizations_client.call_count == 1

    def test_get_user_assignments_success(
        self,
        assignment_retriever,
        valid_user_entity,
        mock_sso_admin_client,
        mock_organizations_client,
        sample_permission_sets,
        sample_accounts,
        sample_assignments,
    ):
        """Test successful user assignment retrieval."""
        # Mock entity validation
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        # Mock the _fetch_entity_assignments method to return controlled data
        assignment_retriever._fetch_entity_assignments = Mock(return_value=sample_assignments)

        # Mock permission set and account name resolution
        assignment_retriever._permission_set_cache[
            "arn:aws:sso:::permissionSet/ssoins-123/ps-admin"
        ] = {"name": "AdministratorAccess", "description": "Full access"}
        assignment_retriever._permission_set_cache[
            "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly"
        ] = {"name": "ReadOnlyAccess", "description": "Read-only access"}
        assignment_retriever._account_cache["123456789012"] = "Production"
        assignment_retriever._account_cache["098765432109"] = "Development"

        # Get user assignments
        assignments = assignment_retriever.get_user_assignments(valid_user_entity)

        assert len(assignments) == 2
        assert all(isinstance(assignment, PermissionAssignment) for assignment in assignments)

        # Check first assignment
        assert (
            assignments[0].permission_set_arn == "arn:aws:sso:::permissionSet/ssoins-123/ps-admin"
        )
        assert assignments[0].permission_set_name == "AdministratorAccess"
        assert assignments[0].account_id == "123456789012"
        assert assignments[0].account_name == "Production"

        # Check second assignment
        assert (
            assignments[1].permission_set_arn
            == "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly"
        )
        assert assignments[1].permission_set_name == "ReadOnlyAccess"
        assert assignments[1].account_id == "098765432109"
        assert assignments[1].account_name == "Development"

    def test_get_user_assignments_validation_error(self, assignment_retriever, valid_user_entity):
        """Test user assignment retrieval with validation error."""
        # Mock validation failure
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(
            has_errors=True, messages=["User not found"]
        )

        assignments = assignment_retriever.get_user_assignments(valid_user_entity)

        assert assignments == []

    def test_get_user_assignments_from_cache(self, assignment_retriever, valid_user_entity):
        """Test that user assignments are retrieved from cache when available."""
        # Mock entity validation
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        # Populate cache
        cached_assignments = [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="123456789012",
                account_name="Production",
            )
        ]
        cache_key = f"user:{valid_user_entity.entity_id}"
        assignment_retriever._user_assignments_cache[cache_key] = cached_assignments

        # Get assignments - should use cache
        assignments = assignment_retriever.get_user_assignments(valid_user_entity)

        assert assignments == cached_assignments
        # Should not call any AWS APIs since we used cache
        assert assignment_retriever.client_manager.get_identity_center_client.call_count == 0

    def test_get_group_assignments_success(
        self,
        assignment_retriever,
        valid_group_entity,
        mock_sso_admin_client,
        mock_organizations_client,
        sample_permission_sets,
        sample_accounts,
    ):
        """Test successful group assignment retrieval."""
        # Mock entity validation
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        # Mock the _fetch_entity_assignments method to return controlled data
        from src.awsideman.permission_cloning.models import PermissionAssignment

        mock_group_assignments = [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-developer",
                permission_set_name="DeveloperAccess",
                account_id="555555555555",
                account_name="Staging",
            )
        ]
        assignment_retriever._fetch_entity_assignments = Mock(return_value=mock_group_assignments)

        # Mock permission set and account name resolution
        assignment_retriever._permission_set_cache[
            "arn:aws:sso:::permissionSet/ssoins-123/ps-developer"
        ] = {"name": "DeveloperAccess", "description": "Developer access"}
        assignment_retriever._account_cache["555555555555"] = "Staging"

        # Get group assignments
        assignments = assignment_retriever.get_group_assignments(valid_group_entity)

        assert len(assignments) == 1
        assert isinstance(assignments[0], PermissionAssignment)
        assert (
            assignments[0].permission_set_arn
            == "arn:aws:sso:::permissionSet/ssoins-123/ps-developer"
        )
        assert assignments[0].permission_set_name == "DeveloperAccess"
        assert assignments[0].account_id == "555555555555"
        assert assignments[0].account_name == "Staging"

    def test_get_entity_assignments_user(self, assignment_retriever, valid_user_entity):
        """Test get_entity_assignments for user entity."""
        # Mock user assignments
        mock_assignments = [Mock()]
        assignment_retriever.get_user_assignments = Mock(return_value=mock_assignments)

        assignments = assignment_retriever.get_entity_assignments(valid_user_entity)

        assert assignments == mock_assignments
        assignment_retriever.get_user_assignments.assert_called_once_with(valid_user_entity)

    def test_get_entity_assignments_group(self, assignment_retriever, valid_group_entity):
        """Test get_entity_assignments for group entity."""
        # Mock group assignments
        mock_assignments = [Mock()]
        assignment_retriever.get_group_assignments = Mock(return_value=mock_assignments)

        assignments = assignment_retriever.get_entity_assignments(valid_group_entity)

        assert assignments == mock_assignments
        assignment_retriever.get_group_assignments.assert_called_once_with(valid_group_entity)

    def test_get_entity_assignments_invalid_type(self, assignment_retriever):
        """Test get_entity_assignments with invalid entity type."""
        invalid_entity = EntityReference(
            entity_type="INVALID", entity_id="invalid-id", entity_name="invalid"  # Invalid type
        )

        assignments = assignment_retriever.get_entity_assignments(invalid_entity)

        assert assignments == []

    def test_get_assignments_for_multiple_entities(
        self, assignment_retriever, valid_user_entity, valid_group_entity
    ):
        """Test getting assignments for multiple entities."""
        # Mock assignments for both entities
        user_assignments = [Mock()]
        group_assignments = [Mock()]

        assignment_retriever.get_user_assignments = Mock(return_value=user_assignments)
        assignment_retriever.get_group_assignments = Mock(return_value=group_assignments)

        # Mock entity validation
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        results = assignment_retriever.get_assignments_for_multiple_entities(
            [valid_user_entity, valid_group_entity]
        )

        assert len(results) == 2
        assert results[valid_user_entity.entity_id] == user_assignments
        assert results[valid_group_entity.entity_id] == group_assignments

    def test_get_assignments_for_multiple_entities_with_error(
        self, assignment_retriever, valid_user_entity, valid_group_entity
    ):
        """Test getting assignments for multiple entities when one fails."""
        # Mock user assignments success, group assignments failure
        user_assignments = [Mock()]
        assignment_retriever.get_user_assignments = Mock(return_value=user_assignments)
        assignment_retriever.get_group_assignments = Mock(side_effect=Exception("API Error"))

        # Mock entity validation
        assignment_retriever.entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        results = assignment_retriever.get_assignments_for_multiple_entities(
            [valid_user_entity, valid_group_entity]
        )

        assert len(results) == 2
        assert results[valid_user_entity.entity_id] == user_assignments
        assert results[valid_group_entity.entity_id] == []  # Empty list for failed entity

    def test_warm_cache_for_entities(
        self, assignment_retriever, valid_user_entity, valid_group_entity
    ):
        """Test warming cache for entities."""
        # Mock get_entity_assignments
        assignment_retriever.get_entity_assignments = Mock()

        # Warm cache
        assignment_retriever.warm_cache_for_entities([valid_user_entity, valid_group_entity])

        # Verify both entities were processed
        assert assignment_retriever.get_entity_assignments.call_count == 2
        assignment_retriever.get_entity_assignments.assert_any_call(valid_user_entity)
        assignment_retriever.get_entity_assignments.assert_any_call(valid_group_entity)

    def test_warm_cache_for_entities_with_failure(
        self, assignment_retriever, valid_user_entity, valid_group_entity
    ):
        """Test warming cache when some entities fail."""
        # Mock get_entity_assignments to fail for group
        assignment_retriever.get_entity_assignments = Mock(
            side_effect=[[Mock()], Exception("API Error")]  # User succeeds  # Group fails
        )

        # Warm cache - should not fail even with errors
        assignment_retriever.warm_cache_for_entities([valid_user_entity, valid_group_entity])

        # Verify both entities were attempted
        assert assignment_retriever.get_entity_assignments.call_count == 2

    def test_clear_cache(self, assignment_retriever):
        """Test that clear_cache removes all cached data."""
        # Populate caches
        assignment_retriever._user_assignments_cache["user1"] = [Mock()]
        assignment_retriever._group_assignments_cache["group1"] = [Mock()]
        assignment_retriever._permission_set_cache["ps1"] = {"name": "test"}
        assignment_retriever._account_cache["acc1"] = "test"

        # Clear cache
        assignment_retriever.clear_cache()

        # Verify all caches are empty
        assert assignment_retriever._user_assignments_cache == {}
        assert assignment_retriever._group_assignments_cache == {}
        assert assignment_retriever._permission_set_cache == {}
        assert assignment_retriever._account_cache == {}

    def test_get_cache_stats(self, assignment_retriever):
        """Test getting cache statistics."""
        # Populate caches
        assignment_retriever._user_assignments_cache["user1"] = [Mock()]
        assignment_retriever._group_assignments_cache["group1"] = [Mock()]
        assignment_retriever._permission_set_cache["ps1"] = {"name": "test"}
        assignment_retriever._account_cache["acc1"] = "test"

        stats = assignment_retriever.get_cache_stats()

        assert stats["user_assignments_cache_size"] == 1
        assert stats["group_assignments_cache_size"] == 1
        assert stats["permission_set_cache_size"] == 1
        assert stats["account_cache_size"] == 1

    def test_fetch_entity_assignments_success(
        self, assignment_retriever, mock_sso_admin_client, sample_permission_sets, sample_accounts
    ):
        """Test successful fetching of entity assignments."""
        # Mock permission sets and accounts
        assignment_retriever._assignment_cache["permission_sets"] = sample_permission_sets
        assignment_retriever._assignment_cache["accounts"] = sample_accounts

        # Mock SSO Admin client responses to return only one assignment for the specific entity
        def mock_list_account_assignments(**kwargs):
            if (
                kwargs.get("AccountId") == "123456789012"
                and kwargs.get("PermissionSetArn")
                == "arn:aws:sso:::permissionSet/ssoins-123/ps-admin"
            ):
                return {
                    "AccountAssignments": [
                        {
                            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                            "AccountId": "123456789012",
                            "PrincipalId": "test-user-id",
                            "PrincipalType": "USER",
                        }
                    ]
                }
            return {"AccountAssignments": []}

        mock_sso_admin_client.list_account_assignments.side_effect = mock_list_account_assignments

        assignments = assignment_retriever._fetch_entity_assignments("test-user-id", "USER")

        assert len(assignments) == 1
        assert (
            assignments[0].permission_set_arn == "arn:aws:sso:::permissionSet/ssoins-123/ps-admin"
        )
        assert assignments[0].account_id == "123456789012"
        assert isinstance(assignments[0], PermissionAssignment)

    def test_fetch_entity_assignments_with_api_error(
        self, assignment_retriever, mock_sso_admin_client, sample_permission_sets, sample_accounts
    ):
        """Test fetching entity assignments when API calls fail."""
        # Mock permission sets and accounts
        assignment_retriever._assignment_cache["permission_sets"] = sample_permission_sets
        assignment_retriever._assignment_cache["accounts"] = sample_accounts

        # Mock SSO Admin client to fail for some calls
        def mock_list_account_assignments(**kwargs):
            if kwargs.get("AccountId") == "123456789012":
                raise ClientError(
                    {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                    "ListAccountAssignments",
                )
            return {"AccountAssignments": []}

        mock_sso_admin_client.list_account_assignments.side_effect = mock_list_account_assignments

        # Should not fail, just skip the problematic account
        assignments = assignment_retriever._fetch_entity_assignments("test-user-id", "USER")

        assert len(assignments) == 0  # No assignments due to API errors

    def test_get_all_permission_sets_from_cache(self, assignment_retriever):
        """Test getting permission sets from cache."""
        # Populate cache
        cached_permission_sets = ["ps1", "ps2", "ps3"]
        assignment_retriever._assignment_cache["permission_sets"] = cached_permission_sets

        permission_sets = assignment_retriever._get_all_permission_sets()

        assert permission_sets == cached_permission_sets
        # Should not call AWS API since we used cache
        assert assignment_retriever.client_manager.get_identity_center_client.call_count == 0

    def test_get_all_permission_sets_from_api(self, assignment_retriever, mock_sso_admin_client):
        """Test getting permission sets from AWS API."""
        # Mock paginator response
        mock_paginator = Mock()
        mock_sso_admin_client.get_paginator.return_value = mock_paginator

        mock_paginator.paginate.return_value = [
            {"PermissionSets": ["ps1", "ps2"]},
            {"PermissionSets": ["ps3"]},
        ]

        permission_sets = assignment_retriever._get_all_permission_sets()

        assert permission_sets == ["ps1", "ps2", "ps3"]
        # Verify cache was populated
        assert assignment_retriever._assignment_cache["permission_sets"] == ["ps1", "ps2", "ps3"]

    def test_get_all_accounts_from_cache(self, assignment_retriever):
        """Test getting accounts from cache."""
        # Populate cache
        cached_accounts = [{"Id": "acc1", "Name": "Account1"}]
        assignment_retriever._assignment_cache["accounts"] = cached_accounts

        accounts = assignment_retriever._get_all_accounts()

        assert accounts == cached_accounts
        # Should not call AWS API since we used cache
        assert assignment_retriever.client_manager.get_organizations_client.call_count == 0

    def test_get_all_accounts_from_api(self, assignment_retriever, mock_organizations_client):
        """Test getting accounts from AWS Organizations API."""
        # Mock paginator response
        mock_paginator = Mock()
        mock_organizations_client.get_paginator.return_value = mock_paginator

        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "acc1", "Name": "Account1"}]},
            {"Accounts": [{"Id": "acc2", "Name": "Account2"}]},
        ]

        accounts = assignment_retriever._get_all_accounts()

        assert len(accounts) == 2
        assert accounts[0]["Id"] == "acc1"
        assert accounts[1]["Id"] == "acc2"
        # Verify cache was populated
        assert len(assignment_retriever._assignment_cache["accounts"]) == 2

    def test_enrich_assignments_success(self, assignment_retriever):
        """Test successful enrichment of assignments."""
        # Mock permission set and account name resolution
        assignment_retriever._permission_set_cache["ps-arn"] = {
            "name": "TestPS",
            "description": "Test",
        }
        assignment_retriever._account_cache["acc-id"] = "TestAccount"

        raw_assignments = [
            {
                "PermissionSetArn": "ps-arn",
                "AccountId": "acc-id",
                "PrincipalId": "user-id",
                "PrincipalType": "USER",
            }
        ]

        enriched_assignments = assignment_retriever._enrich_assignments(raw_assignments)

        assert len(enriched_assignments) == 1
        assert isinstance(enriched_assignments[0], PermissionAssignment)
        assert enriched_assignments[0].permission_set_arn == "ps-arn"
        assert enriched_assignments[0].permission_set_name == "TestPS"
        assert enriched_assignments[0].account_id == "acc-id"
        assert enriched_assignments[0].account_name == "TestAccount"

    def test_enrich_assignments_with_error(self, assignment_retriever):
        """Test enrichment of assignments when some fail."""
        # Mock permission set name resolution to fail
        assignment_retriever._get_permission_set_name = Mock(side_effect=Exception("API Error"))

        raw_assignments = [
            {
                "PermissionSetArn": "ps-arn",
                "AccountId": "acc-id",
                "PrincipalId": "user-id",
                "PrincipalType": "USER",
            }
        ]

        # Should continue processing and return empty list for failed assignment
        enriched_assignments = assignment_retriever._enrich_assignments(raw_assignments)

        assert len(enriched_assignments) == 0

    def test_get_permission_set_name_from_cache(self, assignment_retriever):
        """Test getting permission set name from cache."""
        # Populate cache
        assignment_retriever._permission_set_cache["ps-arn"] = {
            "name": "TestPS",
            "description": "Test",
        }

        name = assignment_retriever._get_permission_set_name("ps-arn")

        assert name == "TestPS"
        # Should not call AWS API since we used cache
        assert assignment_retriever.client_manager.get_identity_center_client.call_count == 0

    def test_get_permission_set_name_from_api(self, assignment_retriever, mock_sso_admin_client):
        """Test getting permission set name from AWS API."""
        # Mock API response
        mock_sso_admin_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPS", "Description": "Test Description"}
        }

        name = assignment_retriever._get_permission_set_name("ps-arn")

        assert name == "TestPS"
        # Verify cache was populated
        assert assignment_retriever._permission_set_cache["ps-arn"]["name"] == "TestPS"
        assert (
            assignment_retriever._permission_set_cache["ps-arn"]["description"]
            == "Test Description"
        )

    def test_get_account_name_from_cache(self, assignment_retriever):
        """Test getting account name from cache."""
        # Populate cache
        assignment_retriever._account_cache["acc-id"] = "TestAccount"

        name = assignment_retriever._get_account_name("acc-id")

        assert name == "TestAccount"
        # Should not call AWS API since we used cache
        assert assignment_retriever.client_manager.get_organizations_client.call_count == 0

    def test_get_account_name_from_organizations_cache(self, assignment_retriever):
        """Test getting account name from organizations cache."""
        # Populate organizations cache
        assignment_retriever._assignment_cache["accounts"] = [
            {"Id": "acc-id", "Name": "TestAccount"}
        ]

        name = assignment_retriever._get_account_name("acc-id")

        assert name == "TestAccount"
        # Verify account cache was populated
        assert assignment_retriever._account_cache["acc-id"] == "TestAccount"

    def test_get_account_name_from_api(self, assignment_retriever, mock_organizations_client):
        """Test getting account name from AWS Organizations API."""
        # Mock API response
        mock_organizations_client.describe_account.return_value = {
            "Account": {"Id": "acc-id", "Name": "TestAccount"}
        }

        name = assignment_retriever._get_account_name("acc-id")

        assert name == "TestAccount"
        # Verify cache was populated
        assert assignment_retriever._account_cache["acc-id"] == "TestAccount"
