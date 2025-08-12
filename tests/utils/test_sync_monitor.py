"""Tests for the SyncMonitor component."""
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    StatusLevel,
    SyncMonitorStatus,
    SyncProviderType,
    SyncStatus,
)
from src.awsideman.utils.sync_monitor import SyncMonitor


class TestSyncMonitor:
    """Test cases for SyncMonitor component."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client."""
        client = Mock()
        client.client = Mock()
        return client

    @pytest.fixture
    def sync_monitor(self, mock_idc_client):
        """Create a SyncMonitor instance with mock client."""
        config = StatusCheckConfig(timeout_seconds=10, retry_attempts=1)
        return SyncMonitor(mock_idc_client, config)

    @pytest.fixture
    def sample_instances(self):
        """Sample Identity Center instances."""
        return {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "IdentityStoreId": "d-1234567890",
                }
            ]
        }

    @pytest.fixture
    def sample_external_groups(self):
        """Sample external groups data."""
        return {
            "Groups": [
                {
                    "GroupId": "group-1",
                    "DisplayName": "DOMAIN\\Engineering",
                    "ExternalIds": [
                        {
                            "Issuer": "ActiveDirectory",
                            "Id": "CN=Engineering,OU=Groups,DC=company,DC=com",
                        }
                    ],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                    },
                },
                {
                    "GroupId": "group-2",
                    "DisplayName": "azure-developers@company.com",
                    "ExternalIds": [{"Issuer": "AzureAD", "Id": "azure-id-123"}],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                    },
                },
            ]
        }

    @pytest.fixture
    def sample_external_users(self):
        """Sample external users data."""
        return {
            "Users": [
                {
                    "UserId": "user-1",
                    "UserName": "DOMAIN\\john.doe",
                    "ExternalIds": [
                        {
                            "Issuer": "ActiveDirectory",
                            "Id": "CN=John Doe,OU=Users,DC=company,DC=com",
                        }
                    ],
                    "Meta": {
                        "ResourceType": "User",
                        "LastModified": (datetime.utcnow() - timedelta(hours=3)).isoformat() + "Z",
                    },
                    "Emails": [{"Value": "john.doe@company.com", "Primary": True}],
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_check_status_no_providers(self, sync_monitor, mock_idc_client, sample_instances):
        """Test sync status check when no external providers are configured."""
        # Mock API responses for no external providers
        mock_idc_client.client.list_instances.return_value = sample_instances
        mock_idc_client.client.list_groups.return_value = {"Groups": []}
        mock_idc_client.client.list_users.return_value = {"Users": []}

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.providers_configured == 0
        assert result.providers_healthy == 0
        assert result.providers_with_errors == 0
        assert "No external identity providers configured" in result.message
        assert len(result.sync_providers) == 0

    @pytest.mark.asyncio
    async def test_check_status_with_external_groups(
        self, sync_monitor, mock_idc_client, sample_instances, sample_external_groups
    ):
        """Test sync status check with external groups detected."""
        # Mock API responses
        mock_idc_client.client.list_instances.return_value = sample_instances
        mock_idc_client.client.list_groups.return_value = sample_external_groups
        mock_idc_client.client.list_users.return_value = {"Users": []}

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.providers_configured == 1
        assert result.providers_healthy == 1
        assert result.providers_with_errors == 0
        assert len(result.sync_providers) == 1

        # Check provider details
        provider = result.sync_providers[0]
        assert provider.provider_type == SyncProviderType.ACTIVE_DIRECTORY
        assert provider.last_sync_time is not None
        assert provider.sync_status == "Active"

    @pytest.mark.asyncio
    async def test_check_status_with_external_users(
        self, sync_monitor, mock_idc_client, sample_instances, sample_external_users
    ):
        """Test sync status check with external users detected."""
        # Mock API responses
        mock_idc_client.client.list_instances.return_value = sample_instances
        mock_idc_client.client.list_groups.return_value = {"Groups": []}
        mock_idc_client.client.list_users.return_value = sample_external_users

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.providers_configured == 1
        assert result.providers_healthy == 1
        assert len(result.sync_providers) == 1

        # Check provider details
        provider = result.sync_providers[0]
        assert provider.provider_type == SyncProviderType.ACTIVE_DIRECTORY
        assert provider.last_sync_time is not None

    @pytest.mark.asyncio
    async def test_check_status_overdue_sync(
        self, sync_monitor, mock_idc_client, sample_instances, sample_external_groups
    ):
        """Test sync status check with overdue synchronization."""
        # Modify sample data to have old timestamps
        old_groups = sample_external_groups.copy()
        for group in old_groups["Groups"]:
            group["Meta"]["LastModified"] = (
                datetime.utcnow() - timedelta(hours=30)
            ).isoformat() + "Z"

        # Mock API responses
        mock_idc_client.client.list_instances.return_value = sample_instances
        mock_idc_client.client.list_groups.return_value = old_groups
        mock_idc_client.client.list_users.return_value = {"Users": []}

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.WARNING
        assert result.providers_configured == 1
        assert result.providers_healthy == 0  # Overdue sync means not healthy
        assert len(result.sync_providers) == 1

        # Check provider details
        provider = result.sync_providers[0]
        assert provider.sync_status == "Overdue"
        assert provider.error_message is not None
        assert "threshold" in provider.error_message

    @pytest.mark.asyncio
    async def test_check_status_api_error(self, sync_monitor, mock_idc_client, sample_instances):
        """Test sync status check with API errors."""
        # Mock API responses with errors
        mock_idc_client.client.list_instances.return_value = sample_instances
        mock_idc_client.client.list_groups.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListGroups"
        )
        mock_idc_client.client.list_users.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListUsers"
        )

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY  # No providers detected due to errors
        assert result.providers_configured == 0
        assert "No external identity providers configured" in result.message

    @pytest.mark.asyncio
    async def test_check_status_no_instances(self, sync_monitor, mock_idc_client):
        """Test sync status check when no Identity Center instances exist."""
        # Mock API response with no instances
        mock_idc_client.client.list_instances.return_value = {"Instances": []}

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.providers_configured == 0
        assert "No external identity providers configured" in result.message

    @pytest.mark.asyncio
    async def test_check_status_unexpected_error(self, sync_monitor, mock_idc_client):
        """Test sync status check with unexpected errors."""
        # Mock API to raise unexpected error
        mock_idc_client.client.list_instances.side_effect = Exception("Unexpected error")

        result = await sync_monitor.check_status()

        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.CRITICAL
        assert "Sync status check failed" in result.message
        assert len(result.errors) > 0
        assert "Unexpected error" in result.errors[0]

    def test_is_external_group_active_directory(self, sync_monitor):
        """Test detection of Active Directory groups."""
        ad_group = {
            "DisplayName": "DOMAIN\\Engineering",
            "ExternalIds": [
                {"Issuer": "ActiveDirectory", "Id": "CN=Engineering,OU=Groups,DC=company,DC=com"}
            ],
        }

        assert sync_monitor._is_external_group(ad_group) is True

    def test_is_external_group_azure_ad(self, sync_monitor):
        """Test detection of Azure AD groups."""
        azure_group = {
            "DisplayName": "azure-developers@company.com",
            "ExternalIds": [{"Issuer": "AzureAD", "Id": "azure-id-123"}],
        }

        assert sync_monitor._is_external_group(azure_group) is True

    def test_is_external_group_ldap_format(self, sync_monitor):
        """Test detection of LDAP format groups."""
        ldap_group = {"DisplayName": "cn=developers,ou=groups,dc=company,dc=com", "ExternalIds": []}

        assert sync_monitor._is_external_group(ldap_group) is True

    def test_is_external_group_internal(self, sync_monitor):
        """Test detection of internal (non-external) groups."""
        internal_group = {"DisplayName": "Internal-Developers", "ExternalIds": []}

        assert sync_monitor._is_external_group(internal_group) is False

    def test_is_external_user_active_directory(self, sync_monitor):
        """Test detection of Active Directory users."""
        ad_user = {
            "UserName": "DOMAIN\\john.doe",
            "ExternalIds": [
                {"Issuer": "ActiveDirectory", "Id": "CN=John Doe,OU=Users,DC=company,DC=com"}
            ],
        }

        assert sync_monitor._is_external_user(ad_user) is True

    def test_is_external_user_email_format(self, sync_monitor):
        """Test detection of email format users."""
        email_user = {"UserName": "john.doe@company.com", "ExternalIds": []}

        assert sync_monitor._is_external_user(email_user) is True

    def test_is_external_user_with_attributes(self, sync_monitor):
        """Test detection of users with external attributes."""
        attr_user = {
            "UserName": "jdoe",
            "ExternalIds": [],
            "Attributes": {"employeeId": "12345", "department": "Engineering"},
        }

        assert sync_monitor._is_external_user(attr_user) is True

    def test_is_external_user_internal(self, sync_monitor):
        """Test detection of internal (non-external) users."""
        internal_user = {"UserName": "internal-user", "ExternalIds": [], "Attributes": {}}

        assert sync_monitor._is_external_user(internal_user) is False

    def test_infer_provider_type_from_groups_active_directory(self, sync_monitor):
        """Test provider type inference from Active Directory groups."""
        ad_groups = [
            {"DisplayName": "DOMAIN\\Engineering"},
            {"DisplayName": "cn=developers,ou=groups,dc=company,dc=com"},
        ]

        provider_type = sync_monitor._infer_provider_type_from_groups(ad_groups)
        assert provider_type == SyncProviderType.ACTIVE_DIRECTORY

    def test_infer_provider_type_from_groups_azure_ad(self, sync_monitor):
        """Test provider type inference from Azure AD groups."""
        azure_groups = [
            {"DisplayName": "azure-developers@company.com"},
            {"DisplayName": "aad-admins"},
        ]

        provider_type = sync_monitor._infer_provider_type_from_groups(azure_groups)
        assert provider_type == SyncProviderType.AZURE_AD

    def test_infer_provider_type_from_groups_default(self, sync_monitor):
        """Test provider type inference defaults to EXTERNAL_SAML."""
        generic_groups = [{"DisplayName": "external-group-1"}, {"DisplayName": "external-group-2"}]

        provider_type = sync_monitor._infer_provider_type_from_groups(generic_groups)
        assert provider_type == SyncProviderType.EXTERNAL_SAML

    def test_infer_provider_type_from_users_active_directory(self, sync_monitor):
        """Test provider type inference from Active Directory users."""
        ad_users = [{"UserName": "DOMAIN\\john.doe"}, {"UserName": "DOMAIN\\jane.smith"}]

        provider_type = sync_monitor._infer_provider_type_from_users(ad_users)
        assert provider_type == SyncProviderType.ACTIVE_DIRECTORY

    def test_infer_provider_type_from_users_azure_ad(self, sync_monitor):
        """Test provider type inference from Azure AD users."""
        azure_users = [
            {"UserName": "john.doe@company.com", "Emails": [{"Value": "john.doe@outlook.com"}]}
        ]

        provider_type = sync_monitor._infer_provider_type_from_users(azure_users)
        assert provider_type == SyncProviderType.AZURE_AD

    def test_determine_sync_status_no_providers(self, sync_monitor):
        """Test sync status determination with no providers."""
        result = sync_monitor._determine_sync_status([])

        assert result["status"] == StatusLevel.HEALTHY
        assert "No external identity providers configured" in result["message"]
        assert result["errors"] == []

    def test_determine_sync_status_all_healthy(self, sync_monitor):
        """Test sync status determination with all healthy providers."""
        healthy_provider = SyncStatus(
            provider_name="Test Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow() - timedelta(hours=1),
            sync_status="Active",
        )

        result = sync_monitor._determine_sync_status([healthy_provider])

        assert result["status"] == StatusLevel.HEALTHY
        assert "synchronized successfully" in result["message"]
        assert result["errors"] == []

    def test_determine_sync_status_with_errors(self, sync_monitor):
        """Test sync status determination with provider errors."""
        error_provider = SyncStatus(
            provider_name="Error Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow() - timedelta(hours=1),
            sync_status="Error",
            error_message="Connection failed",
        )

        result = sync_monitor._determine_sync_status([error_provider])

        assert result["status"] == StatusLevel.WARNING
        assert "have errors" in result["message"]
        assert len(result["errors"]) > 0

    def test_determine_sync_status_high_error_rate(self, sync_monitor):
        """Test sync status determination with high error rate."""
        providers = []
        # Create 3 error providers and 1 healthy (75% error rate)
        for i in range(3):
            providers.append(
                SyncStatus(
                    provider_name=f"Error Provider {i}",
                    provider_type=SyncProviderType.ACTIVE_DIRECTORY,
                    last_sync_time=datetime.utcnow() - timedelta(hours=1),
                    sync_status="Error",
                    error_message="Connection failed",
                )
            )

        providers.append(
            SyncStatus(
                provider_name="Healthy Provider",
                provider_type=SyncProviderType.ACTIVE_DIRECTORY,
                last_sync_time=datetime.utcnow() - timedelta(hours=1),
                sync_status="Active",
            )
        )

        result = sync_monitor._determine_sync_status(providers)

        assert result["status"] == StatusLevel.CRITICAL
        assert "High sync error rate" in result["message"]
        assert "75.0%" in result["message"]

    def test_determine_sync_status_overdue_sync(self, sync_monitor):
        """Test sync status determination with overdue sync."""
        # Create provider with old sync time
        overdue_provider = SyncStatus(
            provider_name="Overdue Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow() - timedelta(hours=30),  # Older than 24h threshold
            sync_status="Active",
        )

        result = sync_monitor._determine_sync_status([overdue_provider])

        assert result["status"] == StatusLevel.WARNING
        assert "Overdue synchronization detected" in result["message"]

    def test_get_provider_type_breakdown(self, sync_monitor):
        """Test provider type breakdown calculation."""
        providers = [
            SyncStatus(
                provider_name="AD Provider",
                provider_type=SyncProviderType.ACTIVE_DIRECTORY,
                last_sync_time=datetime.utcnow(),
                sync_status="Active",
            ),
            SyncStatus(
                provider_name="Azure Provider",
                provider_type=SyncProviderType.AZURE_AD,
                last_sync_time=datetime.utcnow(),
                sync_status="Active",
            ),
            SyncStatus(
                provider_name="SAML Provider",
                provider_type=SyncProviderType.EXTERNAL_SAML,
                last_sync_time=datetime.utcnow(),
                sync_status="Active",
            ),
        ]

        breakdown = sync_monitor._get_provider_type_breakdown(providers)

        assert breakdown[SyncProviderType.ACTIVE_DIRECTORY.value] == 1
        assert breakdown[SyncProviderType.AZURE_AD.value] == 1
        assert breakdown[SyncProviderType.EXTERNAL_SAML.value] == 1

    def test_update_sync_cache(self, sync_monitor):
        """Test sync cache update functionality."""
        providers = [
            SyncStatus(
                provider_name="Test Provider",
                provider_type=SyncProviderType.ACTIVE_DIRECTORY,
                last_sync_time=datetime.utcnow(),
                sync_status="Active",
            )
        ]

        sync_monitor._update_sync_cache(providers)

        assert len(sync_monitor._sync_cache) == 1
        assert "Test Provider" in sync_monitor._sync_cache

    def test_update_sync_cache_cleanup_old_entries(self, sync_monitor):
        """Test sync cache cleanup of old entries."""
        # Add old entry to cache
        old_provider = SyncStatus(
            provider_name="Old Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow() - timedelta(days=10),  # Older than 7 days
            sync_status="Active",
        )
        sync_monitor._sync_cache["Old Provider"] = old_provider

        # Add new entry
        new_providers = [
            SyncStatus(
                provider_name="New Provider",
                provider_type=SyncProviderType.ACTIVE_DIRECTORY,
                last_sync_time=datetime.utcnow(),
                sync_status="Active",
            )
        ]

        sync_monitor._update_sync_cache(new_providers)

        # Old entry should be removed, new entry should be present
        assert "Old Provider" not in sync_monitor._sync_cache
        assert "New Provider" in sync_monitor._sync_cache

    def test_get_sync_health_summary_no_providers(self, sync_monitor):
        """Test sync health summary with no providers."""
        sync_status = SyncMonitorStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.HEALTHY,
            message="No providers",
            sync_providers=[],
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary = sync_monitor.get_sync_health_summary(sync_status)
        assert "No external identity providers configured" in summary

    def test_get_sync_health_summary_with_providers(self, sync_monitor):
        """Test sync health summary with providers."""
        provider = SyncStatus(
            provider_name="Test Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow(),
            sync_status="Active",
        )

        sync_status = SyncMonitorStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.HEALTHY,
            message="All healthy",
            sync_providers=[provider],
            providers_configured=1,
            providers_healthy=1,
            providers_with_errors=0,
        )

        summary = sync_monitor.get_sync_health_summary(sync_status)
        assert "Status: Healthy" in summary
        assert "Providers: 1" in summary
        assert "Healthy: 1" in summary
        assert "Health: 100.0%" in summary

    def test_get_remediation_suggestions_no_providers(self, sync_monitor):
        """Test remediation suggestions with no providers."""
        sync_status = SyncMonitorStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.HEALTHY,
            message="No providers",
            sync_providers=[],
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        suggestions = sync_monitor.get_remediation_suggestions(sync_status)
        assert len(suggestions) == 1
        assert "configuring external identity providers" in suggestions[0]

    def test_get_remediation_suggestions_with_errors(self, sync_monitor):
        """Test remediation suggestions with provider errors."""
        error_provider = SyncStatus(
            provider_name="Error Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow(),
            sync_status="Error",
            error_message="Permission denied",
        )

        sync_status = SyncMonitorStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.WARNING,
            message="Errors detected",
            sync_providers=[error_provider],
            providers_configured=1,
            providers_healthy=0,
            providers_with_errors=1,
        )

        suggestions = sync_monitor.get_remediation_suggestions(sync_status)
        assert len(suggestions) > 0
        assert any("connectivity and credentials" in s for s in suggestions)
        assert any("permissions for Error Provider" in s for s in suggestions)

    def test_get_remediation_suggestions_overdue_sync(self, sync_monitor):
        """Test remediation suggestions with overdue sync."""
        overdue_provider = SyncStatus(
            provider_name="Overdue Provider",
            provider_type=SyncProviderType.ACTIVE_DIRECTORY,
            last_sync_time=datetime.utcnow() - timedelta(hours=50),  # Very old
            sync_status="Active",
        )

        sync_status = SyncMonitorStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.WARNING,
            message="Overdue sync",
            sync_providers=[overdue_provider],
            providers_configured=1,
            providers_healthy=0,
            providers_with_errors=0,
        )

        suggestions = sync_monitor.get_remediation_suggestions(sync_status)
        assert len(suggestions) > 0
        assert any("scheduled synchronization" in s for s in suggestions)
        assert any("manual sync trigger" in s for s in suggestions)


class TestSyncMonitorIntegration:
    """Integration tests for SyncMonitor component."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client for integration tests."""
        client = Mock()
        client.client = Mock()
        return client

    @pytest.fixture
    def sync_monitor(self, mock_idc_client):
        """Create a SyncMonitor instance for integration tests."""
        config = StatusCheckConfig(
            timeout_seconds=30, retry_attempts=2, enable_parallel_checks=True
        )
        return SyncMonitor(mock_idc_client, config)

    @pytest.mark.asyncio
    async def test_full_sync_check_workflow(self, sync_monitor, mock_idc_client):
        """Test complete sync check workflow with realistic data."""
        # Setup realistic mock responses
        instances = {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "IdentityStoreId": "d-1234567890",
                }
            ]
        }

        external_groups = {
            "Groups": [
                {
                    "GroupId": "group-1",
                    "DisplayName": "COMPANY\\Engineering-Team",
                    "ExternalIds": [
                        {
                            "Issuer": "ActiveDirectory",
                            "Id": "CN=Engineering,OU=Groups,DC=company,DC=com",
                        }
                    ],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                    },
                },
                {
                    "GroupId": "group-2",
                    "DisplayName": "COMPANY\\DevOps-Team",
                    "ExternalIds": [
                        {"Issuer": "ActiveDirectory", "Id": "CN=DevOps,OU=Groups,DC=company,DC=com"}
                    ],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                    },
                },
            ]
        }

        external_users = {
            "Users": [
                {
                    "UserId": "user-1",
                    "UserName": "COMPANY\\john.doe",
                    "ExternalIds": [
                        {
                            "Issuer": "ActiveDirectory",
                            "Id": "CN=John Doe,OU=Users,DC=company,DC=com",
                        }
                    ],
                    "Meta": {
                        "ResourceType": "User",
                        "LastModified": (
                            datetime.utcnow() - timedelta(hours=1, minutes=30)
                        ).isoformat()
                        + "Z",
                    },
                }
            ]
        }

        # Configure mock responses
        mock_idc_client.client.list_instances.return_value = instances
        mock_idc_client.client.list_groups.return_value = external_groups
        mock_idc_client.client.list_users.return_value = external_users

        # Execute sync check
        result = await sync_monitor.check_status()

        # Verify comprehensive results
        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.providers_configured == 1
        assert result.providers_healthy == 1
        assert result.providers_with_errors == 0
        assert len(result.sync_providers) == 1

        # Verify provider details
        provider = result.sync_providers[0]
        assert provider.provider_type == SyncProviderType.ACTIVE_DIRECTORY
        assert provider.last_sync_time is not None
        assert provider.sync_status == "Active"
        assert provider.error_message is None

        # Verify detailed information
        assert "check_duration_ms" in result.details
        assert "provider_types" in result.details
        assert result.details["provider_types"][SyncProviderType.ACTIVE_DIRECTORY.value] == 1

        # Verify health percentage
        assert result.get_health_percentage() == 100.0

    @pytest.mark.asyncio
    async def test_mixed_provider_scenario(self, sync_monitor, mock_idc_client):
        """Test scenario with mixed provider types and statuses."""
        # Setup mixed scenario with multiple instances
        instances = {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1111111111111111",
                    "IdentityStoreId": "d-1111111111",
                },
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-2222222222222222",
                    "IdentityStoreId": "d-2222222222",
                },
            ]
        }

        # First instance: Active Directory with recent sync
        ad_groups = {
            "Groups": [
                {
                    "GroupId": "group-ad-1",
                    "DisplayName": "DOMAIN\\Administrators",
                    "ExternalIds": [
                        {
                            "Issuer": "ActiveDirectory",
                            "Id": "CN=Administrators,OU=Groups,DC=domain,DC=com",
                        }
                    ],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                    },
                }
            ]
        }

        # Second instance: Azure AD with overdue sync
        azure_groups = {
            "Groups": [
                {
                    "GroupId": "group-azure-1",
                    "DisplayName": "azure-developers@company.com",
                    "ExternalIds": [{"Issuer": "AzureAD", "Id": "azure-group-123"}],
                    "Meta": {
                        "ResourceType": "Group",
                        "LastModified": (datetime.utcnow() - timedelta(hours=30)).isoformat()
                        + "Z",  # Overdue
                    },
                }
            ]
        }

        # Configure mock to return different responses based on identity store ID
        def mock_list_groups(IdentityStoreId=None):
            # The code converts instance ARN to identity store ID by replacing 'sso' with 'identitystore'
            if (
                IdentityStoreId
                == "arn:aws:identitystore:::instance/identitystoreins-1111111111111111"
            ):
                return ad_groups
            elif (
                IdentityStoreId
                == "arn:aws:identitystore:::instance/identitystoreins-2222222222222222"
            ):
                return azure_groups
            else:
                return {"Groups": []}

        mock_idc_client.client.list_instances.return_value = instances
        mock_idc_client.client.list_groups.side_effect = mock_list_groups
        mock_idc_client.client.list_users.return_value = {"Users": []}

        # Execute sync check
        result = await sync_monitor.check_status()

        # Verify mixed results
        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.WARNING  # Due to overdue sync
        assert result.providers_configured == 2
        assert result.providers_healthy == 1  # Only AD provider is healthy
        assert result.providers_with_errors == 1  # Azure AD provider has overdue sync
        assert len(result.sync_providers) == 2

        # Verify provider breakdown
        provider_types = result.details["provider_types"]
        assert provider_types[SyncProviderType.ACTIVE_DIRECTORY.value] == 1
        assert provider_types[SyncProviderType.AZURE_AD.value] == 1

        # Verify overdue detection
        overdue_providers = result.get_overdue_providers()
        assert len(overdue_providers) == 1
        assert overdue_providers[0].provider_type == SyncProviderType.AZURE_AD

        # Verify health percentage
        assert result.get_health_percentage() == 50.0  # 1 out of 2 healthy

    @pytest.mark.asyncio
    async def test_error_recovery_and_partial_results(self, sync_monitor, mock_idc_client):
        """Test error recovery and partial results handling."""
        instances = {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "IdentityStoreId": "d-1234567890",
                }
            ]
        }

        # Configure mock to succeed for instances but fail for groups/users
        mock_idc_client.client.list_instances.return_value = instances
        mock_idc_client.client.list_groups.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "ListGroups"
        )
        mock_idc_client.client.list_users.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "ListUsers"
        )

        # Execute sync check
        result = await sync_monitor.check_status()

        # Should handle errors gracefully and return meaningful results
        assert isinstance(result, SyncMonitorStatus)
        assert result.status == StatusLevel.HEALTHY  # No providers detected due to API errors
        assert result.providers_configured == 0
        assert "No external identity providers configured" in result.message

        # Should not have critical errors since this is expected behavior
        assert result.status != StatusLevel.CRITICAL
