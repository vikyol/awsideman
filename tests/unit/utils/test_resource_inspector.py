"""Tests for ResourceInspector component."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.resource_inspector import ResourceInspector
from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    ResourceInspectionStatus,
    ResourceStatus,
    ResourceType,
    StatusLevel,
)


class TestResourceInspector:
    """Test cases for ResourceInspector component."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client."""
        client = Mock()
        client.get_raw_identity_store_client = Mock()
        client.get_raw_identity_center_client = Mock()
        return client

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return StatusCheckConfig(timeout_seconds=10, retry_attempts=1, enable_parallel_checks=False)

    @pytest.fixture
    def inspector(self, mock_idc_client, config):
        """Create a ResourceInspector instance."""
        return ResourceInspector(mock_idc_client, config)

    @pytest.fixture
    def sample_user_data(self):
        """Sample user data from AWS API."""
        return {
            "UserId": "12345678-1234-1234-1234-123456789012",
            "UserName": "testuser",
            "DisplayName": "Test User",
            "Emails": [{"Value": "testuser@example.com", "Primary": True}],
            "Name": {"GivenName": "Test", "FamilyName": "User"},
            "Status": "ENABLED",
            "Timezone": "UTC",
            "Locale": "en-US",
            "Meta": {"LastModified": "2024-01-01T12:00:00Z"},
        }

    @pytest.fixture
    def sample_group_data(self):
        """Sample group data from AWS API."""
        return {
            "GroupId": "87654321-4321-4321-4321-210987654321",
            "DisplayName": "Test Group",
            "Description": "A test group for testing",
            "Meta": {"LastModified": "2024-01-01T12:00:00Z"},
        }

    @pytest.fixture
    def sample_permission_set_data(self):
        """Sample permission set data from AWS API."""
        return {
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-abcdef1234567890",
            "Name": "TestPermissionSet",
            "Description": "A test permission set",
            "SessionDuration": "PT8H",
            "RelayState": "https://example.com",
            "CreatedDate": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

    @pytest.mark.asyncio
    async def test_check_status_basic(self, inspector):
        """Test basic status check functionality."""
        result = await inspector.check_status()

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert "ready for specific resource inspections" in result.message
        assert result.inspection_type is None

    @pytest.mark.asyncio
    async def test_inspect_user_found_by_id(self, inspector, mock_idc_client, sample_user_data):
        """Test inspecting a user found by user ID."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user lookup
        mock_identity_store.describe_user.return_value = sample_user_data

        user_id = "12345678-1234-1234-1234-123456789012"
        result = await inspector.inspect_user(user_id)

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_type == ResourceType.USER
        assert result.target_resource.resource_name == "Test User"
        assert result.inspection_type == ResourceType.USER

        # Verify the API call
        mock_identity_store.describe_user.assert_called_once_with(
            IdentityStoreId="d-1234567890", UserId=user_id
        )

    @pytest.mark.asyncio
    async def test_inspect_user_found_by_username(
        self, inspector, mock_idc_client, sample_user_data
    ):
        """Test inspecting a user found by username."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock username search
        mock_identity_store.list_users.return_value = {
            "Users": [{"UserId": sample_user_data["UserId"]}]
        }
        mock_identity_store.describe_user.return_value = sample_user_data

        result = await inspector.inspect_user("testuser")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_name == "Test User"

        # Verify the API calls
        mock_identity_store.list_users.assert_called_once()
        mock_identity_store.describe_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_inspect_user_found_by_email(self, inspector, mock_idc_client, sample_user_data):
        """Test inspecting a user found by email."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock username search (returns empty)
        mock_identity_store.list_users.side_effect = [
            {"Users": []},  # Username search returns empty
            {"Users": [sample_user_data]},  # List all users returns the user
        ]
        mock_identity_store.describe_user.return_value = sample_user_data

        result = await inspector.inspect_user("testuser@example.com")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_name == "Test User"

    @pytest.mark.asyncio
    async def test_inspect_user_not_found_with_suggestions(self, inspector, mock_idc_client):
        """Test inspecting a user that doesn't exist with suggestions."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user not found
        mock_identity_store.list_users.return_value = {"Users": []}

        # Mock suggestions (similar users)
        similar_users = [
            {
                "UserId": "user1",
                "UserName": "testuser1",
                "DisplayName": "Test User 1",
                "Emails": [{"Value": "testuser1@example.com", "Primary": True}],
            },
            {
                "UserId": "user2",
                "UserName": "testuser2",
                "DisplayName": "Test User 2",
                "Emails": [{"Value": "testuser2@example.com", "Primary": True}],
            },
        ]

        # Mock the _get_all_users method
        with patch.object(inspector, "_get_all_users", return_value=similar_users):
            result = await inspector.inspect_user("testuse")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.WARNING
        assert not result.resource_found()
        assert result.has_suggestions()
        assert len(result.similar_resources) > 0
        assert "testuser1" in result.similar_resources[0]

    @pytest.mark.asyncio
    async def test_inspect_user_error(self, inspector, mock_idc_client):
        """Test inspecting a user with API error."""
        # Mock the identity store client to raise an error
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListInstances"
        )

        result = await inspector.inspect_user("testuser")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.CRITICAL
        assert not result.resource_found()
        assert len(result.errors) > 0
        assert "Access denied" in result.errors[0]

    @pytest.mark.asyncio
    async def test_inspect_group_found_by_id(self, inspector, mock_idc_client, sample_group_data):
        """Test inspecting a group found by group ID."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock group lookup
        mock_identity_store.describe_group.return_value = sample_group_data

        group_id = "87654321-4321-4321-4321-210987654321"
        result = await inspector.inspect_group(group_id)

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_type == ResourceType.GROUP
        assert result.target_resource.resource_name == "Test Group"
        assert result.inspection_type == ResourceType.GROUP

        # Verify the API call
        mock_identity_store.describe_group.assert_called_once_with(
            IdentityStoreId="d-1234567890", GroupId=group_id
        )

    @pytest.mark.asyncio
    async def test_inspect_group_found_by_name(self, inspector, mock_idc_client, sample_group_data):
        """Test inspecting a group found by display name."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock group search
        mock_identity_store.list_groups.return_value = {
            "Groups": [{"GroupId": sample_group_data["GroupId"]}]
        }
        mock_identity_store.describe_group.return_value = sample_group_data

        result = await inspector.inspect_group("Test Group")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_name == "Test Group"

        # Verify the API calls
        mock_identity_store.list_groups.assert_called_once()
        mock_identity_store.describe_group.assert_called_once()

    @pytest.mark.asyncio
    async def test_inspect_group_not_found_with_suggestions(self, inspector, mock_idc_client):
        """Test inspecting a group that doesn't exist with suggestions."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock group not found
        mock_identity_store.list_groups.return_value = {"Groups": []}

        # Mock suggestions (similar groups)
        similar_groups = [
            {"GroupId": "group1", "DisplayName": "Test Group 1", "Description": "First test group"},
            {
                "GroupId": "group2",
                "DisplayName": "Test Group 2",
                "Description": "Second test group",
            },
        ]

        # Mock the _get_all_groups method
        with patch.object(inspector, "_get_all_groups", return_value=similar_groups):
            result = await inspector.inspect_group("Test Grou")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.WARNING
        assert not result.resource_found()
        assert result.has_suggestions()
        assert len(result.similar_resources) > 0
        assert "Test Group" in result.similar_resources[0]

    @pytest.mark.asyncio
    async def test_inspect_permission_set_found_by_arn(
        self, inspector, mock_idc_client, sample_permission_set_data
    ):
        """Test inspecting a permission set found by ARN."""
        # Mock the SSO admin client
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ins-1234567890abcdef"}]
        }

        # Mock permission set lookup
        mock_sso_admin.describe_permission_set.return_value = {
            "PermissionSet": sample_permission_set_data
        }

        ps_arn = "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-abcdef1234567890"
        result = await inspector.inspect_permission_set(ps_arn)

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_type == ResourceType.PERMISSION_SET
        assert result.target_resource.resource_name == "TestPermissionSet"
        assert result.inspection_type == ResourceType.PERMISSION_SET

        # Verify the API call
        mock_sso_admin.describe_permission_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_inspect_permission_set_found_by_name(
        self, inspector, mock_idc_client, sample_permission_set_data
    ):
        """Test inspecting a permission set found by name."""
        # Mock the SSO admin client
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ins-1234567890abcdef"}]
        }

        # Mock permission set search
        mock_sso_admin.list_permission_sets.return_value = {
            "PermissionSets": [sample_permission_set_data["PermissionSetArn"]]
        }
        mock_sso_admin.describe_permission_set.return_value = {
            "PermissionSet": sample_permission_set_data
        }

        # Mock the _get_all_permission_sets method
        with patch.object(
            inspector, "_get_all_permission_sets", return_value=[sample_permission_set_data]
        ):
            result = await inspector.inspect_permission_set("TestPermissionSet")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_name == "TestPermissionSet"

    @pytest.mark.asyncio
    async def test_inspect_permission_set_not_found_with_suggestions(
        self, inspector, mock_idc_client
    ):
        """Test inspecting a permission set that doesn't exist with suggestions."""
        # Mock the SSO admin client
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ins-1234567890abcdef"}]
        }

        # Mock suggestions (similar permission sets)
        similar_permission_sets = [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-1",
                "Name": "TestPermissionSet1",
                "Description": "First test permission set",
            },
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-2",
                "Name": "TestPermissionSet2",
                "Description": "Second test permission set",
            },
        ]

        # Mock the _get_all_permission_sets method
        with patch.object(
            inspector, "_get_all_permission_sets", return_value=similar_permission_sets
        ):
            result = await inspector.inspect_permission_set("TestPermission")

        assert isinstance(result, ResourceInspectionStatus)
        assert result.status == StatusLevel.WARNING
        assert not result.resource_found()
        assert result.has_suggestions()
        assert len(result.similar_resources) > 0
        assert "TestPermissionSet" in result.similar_resources[0]

    @pytest.mark.asyncio
    async def test_create_user_status(self, inspector, sample_user_data):
        """Test creating user status from user data."""
        resource_status = await inspector._create_user_status(sample_user_data)

        assert isinstance(resource_status, ResourceStatus)
        assert resource_status.resource_type == ResourceType.USER
        assert resource_status.resource_name == "Test User"
        assert resource_status.exists
        assert resource_status.status == StatusLevel.HEALTHY
        assert resource_status.configuration["username"] == "testuser"
        assert resource_status.configuration["display_name"] == "Test User"
        assert resource_status.health_details["active"]
        assert resource_status.health_details["has_display_name"]
        assert resource_status.last_updated is not None

    @pytest.mark.asyncio
    async def test_create_group_status(self, inspector, sample_group_data):
        """Test creating group status from group data."""
        resource_status = await inspector._create_group_status(sample_group_data)

        assert isinstance(resource_status, ResourceStatus)
        assert resource_status.resource_type == ResourceType.GROUP
        assert resource_status.resource_name == "Test Group"
        assert resource_status.exists
        assert resource_status.status == StatusLevel.HEALTHY
        assert resource_status.configuration["display_name"] == "Test Group"
        assert resource_status.configuration["description"] == "A test group for testing"
        assert resource_status.health_details["has_display_name"]
        assert resource_status.health_details["has_description"]
        assert resource_status.last_updated is not None

    @pytest.mark.asyncio
    async def test_create_permission_set_status(self, inspector, sample_permission_set_data):
        """Test creating permission set status from permission set data."""
        resource_status = await inspector._create_permission_set_status(sample_permission_set_data)

        assert isinstance(resource_status, ResourceStatus)
        assert resource_status.resource_type == ResourceType.PERMISSION_SET
        assert resource_status.resource_name == "TestPermissionSet"
        assert resource_status.exists
        assert resource_status.status == StatusLevel.HEALTHY
        assert resource_status.configuration["name"] == "TestPermissionSet"
        assert resource_status.configuration["description"] == "A test permission set"
        assert resource_status.configuration["session_duration"] == "PT8H"
        assert resource_status.health_details["has_name"]
        assert resource_status.health_details["has_description"]
        assert resource_status.last_updated is not None

    @pytest.mark.asyncio
    async def test_get_user_suggestions(self, inspector):
        """Test getting user suggestions."""
        # Mock users for suggestions
        users = [
            {
                "UserId": "user1",
                "UserName": "testuser1",
                "DisplayName": "Test User 1",
                "Emails": [{"Value": "testuser1@example.com", "Primary": True}],
                "Name": {"GivenName": "Test", "FamilyName": "User1"},
            },
            {
                "UserId": "user2",
                "UserName": "testuser2",
                "DisplayName": "Test User 2",
                "Emails": [{"Value": "testuser2@example.com", "Primary": True}],
                "Name": {"GivenName": "Test", "FamilyName": "User2"},
            },
            {
                "UserId": "user3",
                "UserName": "completelyunrelated",
                "DisplayName": "Completely Unrelated User",
                "Emails": [{"Value": "unrelated@example.com", "Primary": True}],
                "Name": {"GivenName": "Unrelated", "FamilyName": "Person"},
            },
        ]

        with patch.object(inspector, "_get_all_users", return_value=users):
            suggestions = await inspector._get_user_suggestions("testuse", max_suggestions=3)

        assert len(suggestions) > 0
        # Should suggest users with similar names
        assert any("testuser1" in suggestion for suggestion in suggestions)
        assert any("testuser2" in suggestion for suggestion in suggestions)
        # Should not suggest very different users
        assert not any("completelyunrelated" in suggestion for suggestion in suggestions)

    @pytest.mark.asyncio
    async def test_get_group_suggestions(self, inspector):
        """Test getting group suggestions."""
        # Mock groups for suggestions
        groups = [
            {"GroupId": "group1", "DisplayName": "Test Group 1", "Description": "First test group"},
            {
                "GroupId": "group2",
                "DisplayName": "Test Group 2",
                "Description": "Second test group",
            },
            {
                "GroupId": "group3",
                "DisplayName": "Completely Unrelated Group",
                "Description": "A completely unrelated group",
            },
        ]

        with patch.object(inspector, "_get_all_groups", return_value=groups):
            suggestions = await inspector._get_group_suggestions("Test Grou", max_suggestions=3)

        assert len(suggestions) > 0
        # Should suggest groups with similar names
        assert any("Test Group" in suggestion for suggestion in suggestions)
        # Should not suggest very different groups
        assert not any("Completely Unrelated" in suggestion for suggestion in suggestions)

    @pytest.mark.asyncio
    async def test_get_permission_set_suggestions(self, inspector):
        """Test getting permission set suggestions."""
        # Mock permission sets for suggestions
        permission_sets = [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-1",
                "Name": "TestPermissionSet1",
                "Description": "First test permission set",
            },
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-2",
                "Name": "TestPermissionSet2",
                "Description": "Second test permission set",
            },
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-1234567890abcdef/ps-3",
                "Name": "DatabaseAdminRole",
                "Description": "Database administration role",
            },
        ]

        with patch.object(inspector, "_get_all_permission_sets", return_value=permission_sets):
            suggestions = await inspector._get_permission_set_suggestions(
                "TestPermission", max_suggestions=3
            )

        assert len(suggestions) > 0
        # Should suggest permission sets with similar names
        assert any("TestPermissionSet" in suggestion for suggestion in suggestions)
        # Should not suggest very different permission sets
        assert not any("DatabaseAdminRole" in suggestion for suggestion in suggestions)

    @pytest.mark.asyncio
    async def test_cache_functionality(self, inspector, mock_idc_client):
        """Test resource caching functionality."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user listing
        mock_identity_store.list_users.return_value = {
            "Users": [{"UserId": "user1", "UserName": "testuser1"}]
        }

        # First call should hit the API
        users1 = await inspector._get_all_users()
        assert len(users1) == 1
        assert mock_identity_store.list_users.call_count == 1

        # Second call should use cache
        users2 = await inspector._get_all_users()
        assert len(users2) == 1
        assert mock_identity_store.list_users.call_count == 1  # No additional calls

        # Clear cache and call again should hit API
        inspector.clear_cache()
        users3 = await inspector._get_all_users()
        assert len(users3) == 1
        assert mock_identity_store.list_users.call_count == 2  # One additional call

    @pytest.mark.asyncio
    async def test_cache_expiry(self, inspector, mock_idc_client):
        """Test cache expiry functionality."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client for getting identity store ID
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user listing
        mock_identity_store.list_users.return_value = {
            "Users": [{"UserId": "user1", "UserName": "testuser1"}]
        }

        # Set cache TTL to 0 minutes for immediate expiry
        inspector._cache_ttl_minutes = 0

        # First call should hit the API
        users1 = await inspector._get_all_users()
        assert len(users1) == 1
        assert mock_identity_store.list_users.call_count == 1

        # Second call should hit API again due to expired cache
        users2 = await inspector._get_all_users()
        assert len(users2) == 1
        assert mock_identity_store.list_users.call_count == 2  # Additional call due to expiry

    def test_clear_cache(self, inspector):
        """Test cache clearing functionality."""
        # Set some cache data
        inspector._user_cache = [{"UserId": "user1"}]
        inspector._group_cache = [{"GroupId": "group1"}]
        inspector._permission_set_cache = [{"PermissionSetArn": "ps1"}]
        inspector._cache_timestamp = datetime.now(timezone.utc)

        # Clear cache
        inspector.clear_cache()

        # Verify cache is cleared
        assert inspector._user_cache is None
        assert inspector._group_cache is None
        assert inspector._permission_set_cache is None
        assert inspector._cache_timestamp is None


class TestResourceInspectorIntegration:
    """Integration tests for ResourceInspector component."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client for integration tests."""
        client = Mock()
        client.get_raw_identity_store_client = Mock()
        client.get_raw_identity_center_client = Mock()
        return client

    @pytest.fixture
    def inspector(self, mock_idc_client):
        """Create a ResourceInspector instance for integration tests."""
        return ResourceInspector(mock_idc_client)

    @pytest.mark.asyncio
    async def test_full_user_inspection_workflow(self, inspector, mock_idc_client):
        """Test complete user inspection workflow."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user data
        user_data = {
            "UserId": "12345678-1234-1234-1234-123456789012",
            "UserName": "testuser",
            "DisplayName": "Test User",
            "Emails": [{"Value": "testuser@example.com", "Primary": True}],
            "Name": {"GivenName": "Test", "FamilyName": "User"},
            "Status": "ENABLED",
            "Meta": {"LastModified": "2024-01-01T12:00:00Z"},
        }

        # Mock successful user lookup
        mock_identity_store.describe_user.return_value = user_data

        # Test inspection
        result = await inspector.inspect_user("12345678-1234-1234-1234-123456789012")

        # Verify results
        assert result.status == StatusLevel.HEALTHY
        assert result.resource_found()
        assert result.target_resource.resource_type == ResourceType.USER
        assert result.target_resource.resource_name == "Test User"
        assert result.target_resource.configuration["username"] == "testuser"
        assert result.target_resource.health_details["active"]

    @pytest.mark.asyncio
    async def test_resource_not_found_with_suggestions_workflow(self, inspector, mock_idc_client):
        """Test complete workflow when resource is not found but suggestions are available."""
        # Mock the identity store client
        mock_identity_store = Mock()
        mock_idc_client.get_raw_identity_store_client.return_value = mock_identity_store

        # Mock the SSO admin client
        mock_sso_admin = Mock()
        mock_idc_client.get_raw_identity_center_client.return_value = mock_sso_admin
        mock_sso_admin.list_instances.return_value = {
            "Instances": [{"IdentityStoreId": "d-1234567890"}]
        }

        # Mock user not found
        mock_identity_store.list_users.return_value = {"Users": []}

        # Mock similar users for suggestions
        similar_users = [
            {
                "UserId": "user1",
                "UserName": "testuser1",
                "DisplayName": "Test User 1",
                "Emails": [{"Value": "testuser1@example.com", "Primary": True}],
            }
        ]

        # Mock the _get_all_users method
        with patch.object(inspector, "_get_all_users", return_value=similar_users):
            result = await inspector.inspect_user("testuse")

        # Verify results
        assert result.status == StatusLevel.WARNING
        assert not result.resource_found()
        assert result.has_suggestions()
        assert len(result.similar_resources) > 0
        assert "testuser1" in result.similar_resources[0]
        assert result.inspection_type == ResourceType.USER
