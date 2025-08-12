"""Tests for the Summary Statistics collector component."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.status_infrastructure import StatusCheckConfig, StatusCheckError
from src.awsideman.utils.status_models import StatusLevel, SummaryStatistics
from src.awsideman.utils.summary_statistics import SummaryStatisticsCollector


class TestSummaryStatisticsCollector:
    """Test cases for SummaryStatisticsCollector."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client."""
        client = Mock()
        client.get_identity_store_client = Mock()
        client.get_client = Mock()
        return client

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return StatusCheckConfig(enable_parallel_checks=True, timeout_seconds=30, retry_attempts=2)

    @pytest.fixture
    def collector(self, mock_idc_client, config):
        """Create a SummaryStatisticsCollector instance."""
        return SummaryStatisticsCollector(mock_idc_client, config)

    @pytest.fixture
    def sample_users(self):
        """Sample user data for testing."""
        return [
            {
                "UserId": "user-1",
                "UserName": "john.doe",
                "Meta": {"Created": "2023-01-15T10:30:00.000Z"},
            },
            {
                "UserId": "user-2",
                "UserName": "jane.smith",
                "Meta": {"Created": "2023-02-20T14:45:00.000Z"},
            },
        ]

    @pytest.fixture
    def sample_groups(self):
        """Sample group data for testing."""
        return [
            {
                "GroupId": "group-1",
                "DisplayName": "Administrators",
                "Meta": {"Created": "2023-01-10T09:00:00.000Z"},
            },
            {
                "GroupId": "group-2",
                "DisplayName": "Developers",
                "Meta": {"Created": "2023-01-25T11:15:00.000Z"},
            },
        ]

    @pytest.fixture
    def sample_permission_sets(self):
        """Sample permission set data for testing."""
        return [
            "arn:aws:sso:::permissionSet/ins-123/ps-456",
            "arn:aws:sso:::permissionSet/ins-123/ps-789",
        ]

    @pytest.fixture
    def sample_accounts(self):
        """Sample account data for testing."""
        return [
            {"Id": "123456789012", "Name": "Production"},
            {"Id": "123456789013", "Name": "Development"},
        ]

    @pytest.fixture
    def sample_assignments(self):
        """Sample assignment data for testing."""
        return [
            {
                "AccountId": "123456789012",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "PrincipalId": "user-1",
                "PrincipalType": "USER",
            },
            {
                "AccountId": "123456789012",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "PrincipalId": "group-1",
                "PrincipalType": "GROUP",
            },
        ]

    @pytest.mark.asyncio
    async def test_check_status_success(
        self,
        collector,
        mock_idc_client,
        sample_users,
        sample_groups,
        sample_permission_sets,
        sample_accounts,
        sample_assignments,
    ):
        """Test successful status check with complete statistics collection."""
        # Mock SSO Admin client
        mock_sso_admin = Mock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ins-123", "IdentityStoreId": "store-123"}
            ]
        }

        # Mock permission set details
        mock_sso_admin.describe_permission_set.side_effect = [
            {
                "PermissionSet": {
                    "PermissionSetArn": sample_permission_sets[0],
                    "CreatedDate": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                }
            },
            {
                "PermissionSet": {
                    "PermissionSetArn": sample_permission_sets[1],
                    "CreatedDate": datetime(2023, 1, 5, 14, 30, 0, tzinfo=timezone.utc),
                }
            },
        ]

        # Mock paginators
        mock_user_paginator = Mock()
        mock_user_paginator.paginate.return_value = [{"Users": sample_users}]

        mock_group_paginator = Mock()
        mock_group_paginator.paginate.return_value = [{"Groups": sample_groups}]

        mock_ps_paginator = Mock()
        mock_ps_paginator.paginate.return_value = [{"PermissionSets": sample_permission_sets}]

        mock_assignment_paginator = Mock()
        mock_assignment_paginator.paginate.return_value = [
            {"AccountAssignments": sample_assignments}
        ]

        # Mock Identity Store client
        mock_identity_store = Mock()
        mock_identity_store.get_paginator.side_effect = lambda op: {
            "list_users": mock_user_paginator,
            "list_groups": mock_group_paginator,
        }[op]

        # Mock Organizations client
        mock_organizations = Mock()
        mock_org_paginator = Mock()
        mock_org_paginator.paginate.return_value = [{"Accounts": sample_accounts}]
        mock_organizations.get_paginator.return_value = mock_org_paginator

        # Configure SSO Admin paginators
        mock_sso_admin.get_paginator.side_effect = lambda op: {
            "list_permission_sets": mock_ps_paginator,
            "list_account_assignments": mock_assignment_paginator,
        }[op]

        # Configure client mocks
        mock_idc_client.get_identity_store_client.return_value = mock_identity_store
        mock_idc_client.get_client.side_effect = lambda service: {
            "sso-admin": mock_sso_admin,
            "organizations": mock_organizations,
        }[service]

        # Execute the check
        result = await collector.check_status()

        # Verify result
        assert result.status == StatusLevel.HEALTHY
        assert "Summary statistics collected successfully" in result.message
        assert "summary_statistics" in result.details

        # Verify statistics
        stats = result.details["summary_statistics"]
        assert isinstance(stats, SummaryStatistics)
        assert stats.total_users == 2
        assert stats.total_groups == 2
        assert stats.total_permission_sets == 2
        assert stats.total_assignments == 8  # 2 assignments × 2 permission sets × 2 accounts
        assert stats.active_accounts == 2

        # Verify creation dates were collected
        assert len(stats.user_creation_dates) == 2
        assert len(stats.group_creation_dates) == 2
        assert len(stats.permission_set_creation_dates) == 2

    @pytest.mark.asyncio
    async def test_check_status_with_aws_error(self, collector, mock_idc_client):
        """Test status check handling AWS API errors."""
        # Mock SSO Admin client to raise an error
        mock_sso_admin = Mock()
        mock_sso_admin.list_instances.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListInstances",
        )

        mock_idc_client.get_client.return_value = mock_sso_admin

        # Execute the check
        result = await collector.check_status()

        # Verify error result
        assert result.status == StatusLevel.CRITICAL
        assert "Failed to collect summary statistics" in result.message
        assert len(result.errors) > 0
        assert "error_type" in result.details

    @pytest.mark.asyncio
    async def test_collect_user_statistics(self, collector, mock_idc_client, sample_users):
        """Test user statistics collection."""
        # Mock Identity Store client
        mock_identity_store = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"Users": sample_users}]
        mock_identity_store.get_paginator.return_value = mock_paginator

        mock_idc_client.get_identity_store_client.return_value = mock_identity_store

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute user statistics collection
        await collector._collect_user_statistics(stats, "store-123")

        # Verify results
        assert stats.total_users == 2
        assert len(stats.user_creation_dates) == 2
        assert "user-1" in stats.user_creation_dates
        assert "user-2" in stats.user_creation_dates

        # Verify dates were parsed correctly
        user1_date = stats.user_creation_dates["user-1"]
        assert isinstance(user1_date, datetime)
        assert user1_date.year == 2023
        assert user1_date.month == 1
        assert user1_date.day == 15

    @pytest.mark.asyncio
    async def test_collect_group_statistics(self, collector, mock_idc_client, sample_groups):
        """Test group statistics collection."""
        # Mock Identity Store client
        mock_identity_store = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"Groups": sample_groups}]
        mock_identity_store.get_paginator.return_value = mock_paginator

        mock_idc_client.get_identity_store_client.return_value = mock_identity_store

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute group statistics collection
        await collector._collect_group_statistics(stats, "store-123")

        # Verify results
        assert stats.total_groups == 2
        assert len(stats.group_creation_dates) == 2
        assert "group-1" in stats.group_creation_dates
        assert "group-2" in stats.group_creation_dates

    @pytest.mark.asyncio
    async def test_collect_permission_set_statistics(
        self, collector, mock_idc_client, sample_permission_sets
    ):
        """Test permission set statistics collection."""
        # Mock SSO Admin client
        mock_sso_admin = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"PermissionSets": sample_permission_sets}]
        mock_sso_admin.get_paginator.return_value = mock_paginator

        # Mock permission set details
        mock_sso_admin.describe_permission_set.side_effect = [
            {
                "PermissionSet": {
                    "PermissionSetArn": sample_permission_sets[0],
                    "CreatedDate": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                }
            },
            {
                "PermissionSet": {
                    "PermissionSetArn": sample_permission_sets[1],
                    "CreatedDate": datetime(2023, 1, 5, 14, 30, 0, tzinfo=timezone.utc),
                }
            },
        ]

        mock_idc_client.get_client.return_value = mock_sso_admin

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute permission set statistics collection
        await collector._collect_permission_set_statistics(stats, "arn:aws:sso:::instance/ins-123")

        # Verify results
        assert stats.total_permission_sets == 2
        assert len(stats.permission_set_creation_dates) == 2
        assert sample_permission_sets[0] in stats.permission_set_creation_dates
        assert sample_permission_sets[1] in stats.permission_set_creation_dates

    @pytest.mark.asyncio
    async def test_collect_assignment_statistics(
        self,
        collector,
        mock_idc_client,
        sample_permission_sets,
        sample_accounts,
        sample_assignments,
    ):
        """Test assignment statistics collection."""
        # Mock SSO Admin client
        mock_sso_admin = Mock()

        # Mock permission set paginator
        mock_ps_paginator = Mock()
        mock_ps_paginator.paginate.return_value = [{"PermissionSets": sample_permission_sets}]

        # Mock assignment paginator
        mock_assignment_paginator = Mock()
        mock_assignment_paginator.paginate.return_value = [
            {"AccountAssignments": sample_assignments}
        ]

        mock_sso_admin.get_paginator.side_effect = lambda op: {
            "list_permission_sets": mock_ps_paginator,
            "list_account_assignments": mock_assignment_paginator,
        }[op]

        # Mock Organizations client
        mock_organizations = Mock()
        mock_org_paginator = Mock()
        mock_org_paginator.paginate.return_value = [{"Accounts": sample_accounts}]
        mock_organizations.get_paginator.return_value = mock_org_paginator

        mock_idc_client.get_client.side_effect = lambda service: {
            "sso-admin": mock_sso_admin,
            "organizations": mock_organizations,
        }[service]

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute assignment statistics collection
        await collector._collect_assignment_statistics(stats, "arn:aws:sso:::instance/ins-123")

        # Verify results
        # 2 assignments × 2 permission sets × 2 accounts = 8 total assignments
        assert stats.total_assignments == 8
        assert stats.active_accounts == 2  # Both accounts have assignments

    @pytest.mark.asyncio
    async def test_collect_statistics_parallel(self, collector, mock_idc_client):
        """Test parallel statistics collection."""
        collector.config.enable_parallel_checks = True

        # Mock all collection methods
        collector._collect_user_statistics = AsyncMock()
        collector._collect_group_statistics = AsyncMock()
        collector._collect_permission_set_statistics = AsyncMock()
        collector._collect_assignment_statistics = AsyncMock()

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute parallel collection
        await collector._collect_statistics_parallel(stats, "instance-arn", "store-id")

        # Verify all methods were called
        collector._collect_user_statistics.assert_called_once_with(stats, "store-id")
        collector._collect_group_statistics.assert_called_once_with(stats, "store-id")
        collector._collect_permission_set_statistics.assert_called_once_with(stats, "instance-arn")
        collector._collect_assignment_statistics.assert_called_once_with(stats, "instance-arn")

    @pytest.mark.asyncio
    async def test_collect_statistics_sequential(self, collector, mock_idc_client):
        """Test sequential statistics collection."""
        # Mock all collection methods
        collector._collect_user_statistics = AsyncMock()
        collector._collect_group_statistics = AsyncMock()
        collector._collect_permission_set_statistics = AsyncMock()
        collector._collect_assignment_statistics = AsyncMock()

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute sequential collection
        await collector._collect_statistics_sequential(stats, "instance-arn", "store-id")

        # Verify all methods were called in order
        collector._collect_user_statistics.assert_called_once_with(stats, "store-id")
        collector._collect_group_statistics.assert_called_once_with(stats, "store-id")
        collector._collect_permission_set_statistics.assert_called_once_with(stats, "instance-arn")
        collector._collect_assignment_statistics.assert_called_once_with(stats, "instance-arn")

    @pytest.mark.asyncio
    async def test_get_instance_info(self, collector, mock_idc_client):
        """Test getting Identity Center instance information."""
        # Mock SSO Admin client
        mock_sso_admin = Mock()
        mock_sso_admin.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ins-123", "IdentityStoreId": "store-123"}
            ]
        }

        mock_idc_client.get_client.return_value = mock_sso_admin

        # Execute method
        instance_arn, identity_store_id = await collector._get_instance_info()

        # Verify results
        assert instance_arn == "arn:aws:sso:::instance/ins-123"
        assert identity_store_id == "store-123"

    @pytest.mark.asyncio
    async def test_get_instance_info_no_instances(self, collector, mock_idc_client):
        """Test handling case where no Identity Center instances are found."""
        # Mock SSO Admin client with no instances
        mock_sso_admin = Mock()
        mock_sso_admin.list_instances.return_value = {"Instances": []}

        mock_idc_client.get_client.return_value = mock_sso_admin

        # Execute method and expect error
        with pytest.raises(StatusCheckError, match="No Identity Center instances found"):
            await collector._get_instance_info()

    @pytest.mark.asyncio
    async def test_get_all_accounts(self, collector, sample_accounts):
        """Test getting all organization accounts."""
        # Mock Organizations client
        mock_organizations = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"Accounts": sample_accounts}]
        mock_organizations.get_paginator.return_value = mock_paginator

        # Execute method
        accounts = await collector._get_all_accounts(mock_organizations)

        # Verify results
        assert len(accounts) == 2
        assert accounts[0]["Id"] == "123456789012"
        assert accounts[1]["Id"] == "123456789013"

    @pytest.mark.asyncio
    async def test_get_all_accounts_with_error(self, collector):
        """Test handling errors when getting organization accounts."""
        # Mock Organizations client that raises an error
        mock_organizations = Mock()
        mock_organizations.get_paginator.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListAccounts",
        )

        # Execute method
        accounts = await collector._get_all_accounts(mock_organizations)

        # Should return empty list on error
        assert accounts == []

    @pytest.mark.asyncio
    async def test_get_all_permission_sets(self, collector, sample_permission_sets):
        """Test getting all permission sets."""
        # Mock SSO Admin client
        mock_sso_admin = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"PermissionSets": sample_permission_sets}]
        mock_sso_admin.get_paginator.return_value = mock_paginator

        # Execute method
        permission_sets = await collector._get_all_permission_sets(mock_sso_admin, "instance-arn")

        # Verify results
        assert len(permission_sets) == 2
        assert permission_sets == sample_permission_sets

    @pytest.mark.asyncio
    async def test_user_statistics_with_invalid_date_format(self, collector, mock_idc_client):
        """Test user statistics collection with invalid date formats."""
        # Sample users with various date formats
        users_with_bad_dates = [
            {
                "UserId": "user-1",
                "UserName": "john.doe",
                "Meta": {"Created": "invalid-date-format"},
            },
            {
                "UserId": "user-2",
                "UserName": "jane.smith",
                "Meta": {"Created": "2023-01-15T10:30:00.000Z"},
            },
        ]

        # Mock Identity Store client
        mock_identity_store = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"Users": users_with_bad_dates}]
        mock_identity_store.get_paginator.return_value = mock_paginator

        mock_idc_client.get_identity_store_client.return_value = mock_identity_store

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute user statistics collection
        await collector._collect_user_statistics(stats, "store-123")

        # Verify results - should still count users but only valid dates
        assert stats.total_users == 2
        assert len(stats.user_creation_dates) == 1  # Only valid date should be included
        assert "user-2" in stats.user_creation_dates
        assert "user-1" not in stats.user_creation_dates

    @pytest.mark.asyncio
    async def test_permission_set_statistics_with_describe_errors(self, collector, mock_idc_client):
        """Test permission set statistics collection with describe errors."""
        sample_permission_sets = [
            "arn:aws:sso:::permissionSet/ins-123/ps-456",
            "arn:aws:sso:::permissionSet/ins-123/ps-789",
        ]

        # Mock SSO Admin client
        mock_sso_admin = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{"PermissionSets": sample_permission_sets}]
        mock_sso_admin.get_paginator.return_value = mock_paginator

        # Mock describe_permission_set to fail for first PS, succeed for second
        mock_sso_admin.describe_permission_set.side_effect = [
            ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                operation_name="DescribePermissionSet",
            ),
            {
                "PermissionSet": {
                    "PermissionSetArn": sample_permission_sets[1],
                    "CreatedDate": datetime(2023, 1, 5, 14, 30, 0, tzinfo=timezone.utc),
                }
            },
        ]

        mock_idc_client.get_client.return_value = mock_sso_admin

        # Create statistics object
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Execute permission set statistics collection
        await collector._collect_permission_set_statistics(stats, "arn:aws:sso:::instance/ins-123")

        # Verify results - should count all permission sets but only get dates for successful ones
        assert stats.total_permission_sets == 2
        assert len(stats.permission_set_creation_dates) == 1  # Only one successful describe
        assert sample_permission_sets[1] in stats.permission_set_creation_dates
        assert sample_permission_sets[0] not in stats.permission_set_creation_dates

    def test_component_metadata(self, collector):
        """Test component metadata methods."""
        assert collector.get_component_name() == "SummaryStatisticsCollector"
        assert collector.get_component_version() == "1.0.0"

        supported_checks = collector.get_supported_checks()
        assert "summary_statistics" in supported_checks
        assert "statistics" in supported_checks
        assert "summary" in supported_checks

    @pytest.mark.asyncio
    async def test_summary_statistics_model_methods(self):
        """Test SummaryStatistics model helper methods."""
        # Create sample statistics
        stats = SummaryStatistics(
            total_users=10,
            total_groups=5,
            total_permission_sets=8,
            total_assignments=50,
            active_accounts=3,
            last_updated=datetime.utcnow(),
            user_creation_dates={"user-1": datetime(2023, 1, 1), "user-2": datetime(2023, 6, 15)},
        )

        # Test helper methods
        assert stats.get_total_principals() == 15  # 10 users + 5 groups
        assert abs(stats.get_assignments_per_account() - 16.67) < 0.01  # 50 / 3
        assert abs(stats.get_assignments_per_permission_set() - 6.25) < 0.01  # 50 / 8

        # Test date methods
        newest_date = stats.get_newest_user_date()
        oldest_date = stats.get_oldest_user_date()

        assert newest_date == datetime(2023, 6, 15)
        assert oldest_date == datetime(2023, 1, 1)

    @pytest.mark.asyncio
    async def test_empty_statistics_model_methods(self):
        """Test SummaryStatistics model methods with empty data."""
        # Create empty statistics
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=datetime.utcnow(),
        )

        # Test helper methods with zero values
        assert stats.get_total_principals() == 0
        assert stats.get_assignments_per_account() == 0.0
        assert stats.get_assignments_per_permission_set() == 0.0
        assert stats.get_newest_user_date() is None
        assert stats.get_oldest_user_date() is None
