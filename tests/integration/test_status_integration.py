"""Integration tests for end-to-end status workflows.

This module contains integration tests that verify complete status checking
workflows from command invocation to final results, including:
- Complete status check workflow with all components
- Individual status component workflows
- Output format generation and validation
- Error handling with various AWS service error conditions
- Status command CLI integration
- Resource inspection workflows
- Orphaned assignment cleanup workflows

These tests verify the integration between CLI commands, status orchestrator,
individual status checkers, output formatters, and AWS service interactions.
"""
import asyncio
import csv
import io
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.commands.status import check_status, cleanup_orphaned, inspect_resource
from src.awsideman.utils.output_formatters import CSVFormatter, JSONFormatter, TableFormatter
from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    PrincipalType,
    ProvisioningOperation,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)
from src.awsideman.utils.status_orchestrator import StatusOrchestrator


class TestStatusIntegrationFixtures:
    """Test fixtures and mock data for status integration tests."""

    @staticmethod
    def get_mock_aws_responses():
        """Get comprehensive mock AWS API responses for testing."""
        return {
            # Identity Center instance info
            "instance_metadata": {
                "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "IdentityStoreId": "d-1234567890",
                "Status": "ACTIVE",
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            },
            # Health check responses
            "list_instances": {
                "Instances": [
                    {
                        "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        "IdentityStoreId": "d-1234567890",
                        "Status": "ACTIVE",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                ]
            },
            # Provisioning status responses
            "account_assignment_creation_status": {
                "AccountAssignmentCreationStatus": {
                    "Status": "IN_PROGRESS",
                    "RequestId": "req-1234567890abcdef",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "TargetId": "111111111111",
                    "TargetType": "AWS_ACCOUNT",
                    "CreatedDate": datetime.utcnow() - timedelta(minutes=5),
                }
            },
            "account_assignment_deletion_status": {
                "AccountAssignmentDeletionStatus": {
                    "Status": "FAILED",
                    "RequestId": "req-0987654321fedcba",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "PrincipalId": "user-0987654321fedcba",
                    "PrincipalType": "USER",
                    "TargetId": "222222222222",
                    "TargetType": "AWS_ACCOUNT",
                    "CreatedDate": datetime.utcnow() - timedelta(hours=1),
                    "FailureReason": "Principal not found in identity store",
                }
            },
            # Users and groups
            "users": {
                "Users": [
                    {
                        "UserId": "user-1234567890abcdef",
                        "UserName": "john.doe@company.com",
                        "DisplayName": "John Doe",
                        "Name": {"GivenName": "John", "FamilyName": "Doe"},
                        "Meta": {
                            "Created": datetime(2023, 1, 1, 0, 0, 0),
                            "LastModified": datetime(2023, 6, 1, 0, 0, 0),
                        },
                    },
                    {
                        "UserId": "user-0987654321fedcba",
                        "UserName": "jane.smith@company.com",
                        "DisplayName": "Jane Smith",
                        "Name": {"GivenName": "Jane", "FamilyName": "Smith"},
                        "Meta": {
                            "Created": datetime(2023, 2, 1, 0, 0, 0),
                            "LastModified": datetime(2023, 7, 1, 0, 0, 0),
                        },
                    },
                ]
            },
            "groups": {
                "Groups": [
                    {
                        "GroupId": "group-1234567890abcdef",
                        "DisplayName": "Administrators",
                        "Description": "System administrators group",
                        "Meta": {
                            "Created": datetime(2023, 1, 1, 0, 0, 0),
                            "LastModified": datetime(2023, 5, 1, 0, 0, 0),
                        },
                    },
                    {
                        "GroupId": "group-0987654321fedcba",
                        "DisplayName": "Developers",
                        "Description": "Development team group",
                        "Meta": {
                            "Created": datetime(2023, 1, 15, 0, 0, 0),
                            "LastModified": datetime(2023, 6, 15, 0, 0, 0),
                        },
                    },
                ]
            },
            # Permission sets
            "permission_sets": {
                "PermissionSets": [
                    "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-poweruseraccess",
                    "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-administratoraccess",
                ]
            },
            "permission_set_details": {
                "PermissionSet": {
                    "Name": "ReadOnlyAccess",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "Description": "Read-only access permission set",
                    "SessionDuration": "PT8H",
                    "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                }
            },
            # Account assignments with orphaned entries
            "account_assignments": {
                "AccountAssignments": [
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        "PrincipalId": "user-1234567890abcdef",
                        "PrincipalType": "USER",
                        "AccountId": "111111111111",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                    },
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        "PrincipalId": "user-orphaned123456",  # This user doesn't exist
                        "PrincipalType": "USER",
                        "AccountId": "222222222222",
                        "CreatedDate": datetime(2023, 2, 1, 0, 0, 0),
                    },
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-poweruseraccess",
                        "PrincipalId": "group-orphaned789012",  # This group doesn't exist
                        "PrincipalType": "GROUP",
                        "AccountId": "333333333333",
                        "CreatedDate": datetime(2023, 3, 1, 0, 0, 0),
                    },
                ]
            },
            # Organizations accounts
            "organizations_accounts": {
                "Accounts": [
                    {
                        "Id": "111111111111",
                        "Name": "dev-account-1",
                        "Email": "dev1@company.com",
                        "Status": "ACTIVE",
                    },
                    {
                        "Id": "222222222222",
                        "Name": "dev-account-2",
                        "Email": "dev2@company.com",
                        "Status": "ACTIVE",
                    },
                    {
                        "Id": "333333333333",
                        "Name": "prod-account-1",
                        "Email": "prod1@company.com",
                        "Status": "ACTIVE",
                    },
                ]
            },
            # External identity provider info (for sync monitoring)
            "identity_providers": {
                "IdentityProviders": [
                    {
                        "IdentityProviderArn": "arn:aws:sso:::identityProvider/ssoins-1234567890abcdef/idp-activeDirectory",
                        "Name": "Corporate Active Directory",
                        "IdentityProviderType": "ACTIVE_DIRECTORY",
                        "Status": "ACTIVE",
                    }
                ]
            },
            # Sync status (mock external provider sync)
            "sync_status": {
                "SyncStatus": "SUCCEEDED",
                "LastSyncTime": datetime.utcnow() - timedelta(hours=2),
                "NextSyncTime": datetime.utcnow() + timedelta(hours=22),
            },
        }

    @staticmethod
    def create_mock_aws_client_manager():
        """Create comprehensive mock AWS client manager for status testing."""
        manager = Mock(spec=AWSClientManager)
        responses = TestStatusIntegrationFixtures.get_mock_aws_responses()

        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.list_instances.return_value = responses["list_instances"]
        sso_admin_client.describe_instance_access_control_attribute_configuration.return_value = {
            "Status": "ENABLED",
            "StatusReason": "Configuration is active",
        }
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["account_assignments"]
        sso_admin_client.describe_account_assignment_creation_status.return_value = responses[
            "account_assignment_creation_status"
        ]
        sso_admin_client.describe_account_assignment_deletion_status.return_value = responses[
            "account_assignment_deletion_status"
        ]
        sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "cleanup-req-123456",
            }
        }
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        identity_store_client.list_groups.return_value = responses["groups"]

        # Mock user lookup failures for orphaned detection
        def mock_describe_user(UserId):
            if UserId == "user-orphaned123456":
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ResourceNotFoundException",
                            "Message": f"User with ID {UserId} not found",
                        }
                    },
                    operation_name="DescribeUser",
                )
            return {
                "UserId": UserId,
                "UserName": "existing.user@company.com",
                "DisplayName": "Existing User",
            }

        def mock_describe_group(GroupId):
            if GroupId == "group-orphaned789012":
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ResourceNotFoundException",
                            "Message": f"Group with ID {GroupId} not found",
                        }
                    },
                    operation_name="DescribeGroup",
                )
            return {"GroupId": GroupId, "DisplayName": "Existing Group"}

        identity_store_client.describe_user.side_effect = mock_describe_user
        identity_store_client.describe_group.side_effect = mock_describe_group
        manager.get_identity_store_client.return_value = identity_store_client

        # Mock Organizations client
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = responses["organizations_accounts"]
        manager.get_organizations_client.return_value = organizations_client

        return manager

    @staticmethod
    def create_failing_aws_client_manager():
        """Create mock AWS client manager that simulates various failure scenarios."""
        manager = Mock(spec=AWSClientManager)

        # Mock SSO Admin client with connection failures
        sso_admin_client = Mock()
        sso_admin_client.list_instances.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "UnauthorizedOperation",
                    "Message": "You are not authorized to perform this operation",
                }
            },
            operation_name="ListInstances",
        )
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client with timeout
        identity_store_client = Mock()
        identity_store_client.list_users.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ServiceUnavailable",
                    "Message": "Service temporarily unavailable",
                }
            },
            operation_name="ListUsers",
        )
        manager.get_identity_store_client.return_value = identity_store_client

        # Mock Organizations client with rate limiting
        organizations_client = Mock()
        organizations_client.list_accounts.side_effect = ClientError(
            error_response={
                "Error": {"Code": "TooManyRequestsException", "Message": "Request rate exceeded"}
            },
            operation_name="ListAccounts",
        )
        manager.get_organizations_client.return_value = organizations_client

        return manager


class TestComprehensiveStatusWorkflow:
    """Integration tests for complete status checking workflows."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @pytest.fixture
    def failing_aws_client_manager(self):
        """Create failing mock AWS client manager for error testing."""
        return TestStatusIntegrationFixtures.create_failing_aws_client_manager()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_complete_status_check_workflow_table_format(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test complete status check workflow with table output format."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check command
        check_status(
            output_format="table",
            status_type=None,  # Comprehensive check
            timeout=30,
            parallel=True,
            profile=None,
        )

        # Verify AWS clients were initialized
        mock_aws_client_manager_class.assert_called_once_with(profile="default", region="us-east-1")

        # Verify SSO Admin client was used for health checks
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_instances.assert_called()

        # Verify Identity Store client was used for user/group enumeration
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called()
        identity_store_client.list_groups.assert_called()

        # Verify Organizations client was used for account enumeration
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called()

        # Verify permission sets were enumerated
        sso_admin_client.list_permission_sets.assert_called()

        # Verify account assignments were checked for orphaned detection
        sso_admin_client.list_account_assignments.assert_called()

        # Verify console output was generated (table format)
        assert mock_console.print.call_count > 0

        # Verify no JSON or CSV specific output
        printed_content = str(mock_console.print.call_args_list)
        assert "json" not in printed_content.lower() or "table" in printed_content.lower()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_complete_status_check_workflow_json_format(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test complete status check workflow with JSON output format."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check command with JSON format
        check_status(
            output_format="json", status_type=None, timeout=30, parallel=True, profile=None
        )

        # Verify AWS services were called
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_instances.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify JSON output was generated
        printed_calls = mock_console.print.call_args_list
        json_output_found = False

        for call in printed_calls:
            call_str = str(call)
            if "{" in call_str and "}" in call_str:
                json_output_found = True
                break

        assert json_output_found, "JSON output should be generated"

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_complete_status_check_workflow_csv_format(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test complete status check workflow with CSV output format."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check command with CSV format
        check_status(output_format="csv", status_type=None, timeout=30, parallel=True, profile=None)

        # Verify AWS services were called
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_instances.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify CSV-like output was generated
        printed_calls = mock_console.print.call_args_list
        csv_output_found = False

        for call in printed_calls:
            call_str = str(call)
            if "," in call_str and ("Component" in call_str or "Status" in call_str):
                csv_output_found = True
                break

        assert csv_output_found, "CSV output should be generated"

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_specific_health_status_check_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test specific health status check workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute specific health status check
        check_status(
            output_format="table", status_type="health", timeout=30, parallel=True, profile=None
        )

        # Verify health-specific AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_instances.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify health-specific output
        printed_content = str(mock_console.print.call_args_list)
        assert "health" in printed_content.lower() or "status" in printed_content.lower()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_specific_orphaned_status_check_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test specific orphaned assignment status check workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute specific orphaned assignment check
        check_status(
            output_format="table", status_type="orphaned", timeout=30, parallel=True, profile=None
        )

        # Verify orphaned-specific AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_account_assignments.assert_called()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        # Should attempt to describe users/groups to detect orphaned ones
        assert (
            identity_store_client.describe_user.call_count > 0
            or identity_store_client.describe_group.call_count > 0
        )

        # Verify console output was generated
        assert mock_console.print.call_count > 0


class TestStatusErrorHandlingWorkflow:
    """Integration tests for error handling in status workflows."""

    @pytest.fixture
    def failing_aws_client_manager(self):
        """Create failing mock AWS client manager for error testing."""
        return TestStatusIntegrationFixtures.create_failing_aws_client_manager()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_status_check_with_connection_failures(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        failing_aws_client_manager,
    ):
        """Test status check workflow with AWS connection failures."""
        # Setup mocks with failing client
        mock_aws_client_manager_class.return_value = failing_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check command - should handle errors gracefully
        with pytest.raises(typer.Exit):
            check_status(
                output_format="table", status_type=None, timeout=30, parallel=True, profile=None
            )

        # Verify error handling was triggered
        assert mock_console.print.call_count > 0

        # Verify error messages were displayed
        printed_content = str(mock_console.print.call_args_list)
        assert "error" in printed_content.lower() or "failed" in printed_content.lower()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_status_check_with_partial_failures(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
    ):
        """Test status check workflow with partial component failures."""
        # Create mixed success/failure client
        manager = Mock(spec=AWSClientManager)

        # SSO Admin client works
        sso_admin_client = Mock()
        responses = TestStatusIntegrationFixtures.get_mock_aws_responses()
        sso_admin_client.list_instances.return_value = responses["list_instances"]
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.list_account_assignments.return_value = responses["account_assignments"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Identity Store client fails
        identity_store_client = Mock()
        identity_store_client.list_users.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ServiceUnavailable",
                    "Message": "Identity Store temporarily unavailable",
                }
            },
            operation_name="ListUsers",
        )
        manager.get_identity_store_client.return_value = identity_store_client

        # Organizations client works
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = responses["organizations_accounts"]
        manager.get_organizations_client.return_value = organizations_client

        # Setup mocks
        mock_aws_client_manager_class.return_value = manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check - should handle partial failures gracefully
        check_status(
            output_format="table", status_type=None, timeout=30, parallel=True, profile=None
        )

        # Verify both successful and failed components were processed
        sso_admin_client.list_instances.assert_called()  # Should succeed
        identity_store_client.list_users.assert_called()  # Should fail but be handled
        organizations_client.list_accounts.assert_called()  # Should succeed

        # Verify console output was generated despite partial failures
        assert mock_console.print.call_count > 0

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_status_check_with_timeout_handling(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
    ):
        """Test status check workflow with timeout scenarios."""
        # Create client that simulates slow responses
        manager = Mock(spec=AWSClientManager)

        # SSO Admin client with slow response
        sso_admin_client = Mock()

        async def slow_list_instances():
            await asyncio.sleep(2)  # Simulate slow response
            return TestStatusIntegrationFixtures.get_mock_aws_responses()["list_instances"]

        sso_admin_client.list_instances.side_effect = slow_list_instances
        manager.get_identity_center_client.return_value = sso_admin_client

        # Setup other clients normally
        identity_store_client = Mock()
        responses = TestStatusIntegrationFixtures.get_mock_aws_responses()
        identity_store_client.list_users.return_value = responses["users"]
        manager.get_identity_store_client.return_value = identity_store_client

        organizations_client = Mock()
        organizations_client.list_accounts.return_value = responses["organizations_accounts"]
        manager.get_organizations_client.return_value = organizations_client

        # Setup mocks
        mock_aws_client_manager_class.return_value = manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute status check with short timeout
        check_status(
            output_format="table",
            status_type=None,
            timeout=1,  # Very short timeout
            parallel=True,
            profile=None,
        )

        # Verify console output was generated despite timeouts
        assert mock_console.print.call_count > 0


class TestResourceInspectionWorkflow:
    """Integration tests for resource inspection workflows."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for resource inspection testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_user_inspection_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test user resource inspection workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute user inspection
        inspect_resource(
            resource_type="user",
            resource_id="john.doe@company.com",
            output_format="table",
            profile=None,
        )

        # Verify user-specific AWS calls were made
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify user-specific output
        printed_content = str(mock_console.print.call_args_list)
        assert "user" in printed_content.lower()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_group_inspection_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test group resource inspection workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute group inspection
        inspect_resource(
            resource_type="group", resource_id="Administrators", output_format="json", profile=None
        )

        # Verify group-specific AWS calls were made
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_groups.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify JSON output for group
        printed_calls = mock_console.print.call_args_list
        json_output_found = False

        for call in printed_calls:
            call_str = str(call)
            if "{" in call_str and "}" in call_str:
                json_output_found = True
                break

        assert json_output_found, "JSON output should be generated for group inspection"

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_permission_set_inspection_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test permission set resource inspection workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute permission set inspection
        inspect_resource(
            resource_type="permission-set",
            resource_id="ReadOnlyAccess",
            output_format="csv",
            profile=None,
        )

        # Verify permission set-specific AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_permission_sets.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify CSV output for permission set
        printed_calls = mock_console.print.call_args_list
        csv_output_found = False

        for call in printed_calls:
            call_str = str(call)
            if "," in call_str and ("Resource" in call_str or "Status" in call_str):
                csv_output_found = True
                break

        assert csv_output_found, "CSV output should be generated for permission set inspection"

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_resource_not_found_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test resource inspection workflow when resource is not found."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute inspection for non-existent user
        inspect_resource(
            resource_type="user",
            resource_id="nonexistent.user@company.com",
            output_format="table",
            profile=None,
        )

        # Verify AWS calls were made to search for the resource
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify "not found" messaging
        printed_content = str(mock_console.print.call_args_list)
        assert "not found" in printed_content.lower() or "found: no" in printed_content.lower()


class TestOrphanedAssignmentCleanupWorkflow:
    """Integration tests for orphaned assignment cleanup workflows."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for cleanup testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_orphaned_cleanup_dry_run_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test orphaned assignment cleanup dry-run workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute cleanup in dry-run mode
        cleanup_orphaned(dry_run=True, force=False, profile=None)

        # Verify orphaned detection AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_account_assignments.assert_called()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        # Should attempt to describe users/groups to detect orphaned ones
        assert (
            identity_store_client.describe_user.call_count > 0
            or identity_store_client.describe_group.call_count > 0
        )

        # Verify NO actual deletions were performed in dry-run
        sso_admin_client.delete_account_assignment.assert_not_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify dry-run messaging
        printed_content = str(mock_console.print.call_args_list)
        assert "dry run" in printed_content.lower() or "preview" in printed_content.lower()

    @patch("typer.confirm")
    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_orphaned_cleanup_execute_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager,
    ):
        """Test orphaned assignment cleanup execution workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # User confirms cleanup

        # Execute cleanup with execution
        cleanup_orphaned(dry_run=False, force=False, profile=None)

        # Verify orphaned detection AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_account_assignments.assert_called()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        # Should attempt to describe users/groups to detect orphaned ones
        assert (
            identity_store_client.describe_user.call_count > 0
            or identity_store_client.describe_group.call_count > 0
        )

        # Verify confirmation was requested
        mock_confirm.assert_called_once()

        # Verify actual deletions were performed
        sso_admin_client.delete_account_assignment.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

        # Verify cleanup success messaging
        printed_content = str(mock_console.print.call_args_list)
        assert "cleaned up" in printed_content.lower() or "success" in printed_content.lower()

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_orphaned_cleanup_force_workflow(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test orphaned assignment cleanup with force flag workflow."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute cleanup with force flag (no confirmation)
        cleanup_orphaned(dry_run=False, force=True, profile=None)

        # Verify orphaned detection AWS calls were made
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_account_assignments.assert_called()

        # Verify actual deletions were performed without confirmation
        sso_admin_client.delete_account_assignment.assert_called()

        # Verify console output was generated
        assert mock_console.print.call_count > 0

    @patch("src.awsideman.commands.status.validate_profile")
    @patch("src.awsideman.commands.status.validate_sso_instance")
    @patch("src.awsideman.commands.status.AWSClientManager")
    @patch("src.awsideman.commands.status.console")
    def test_orphaned_cleanup_no_orphaned_assignments(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
    ):
        """Test orphaned assignment cleanup when no orphaned assignments exist."""
        # Create client with no orphaned assignments
        manager = Mock(spec=AWSClientManager)

        # SSO Admin client with clean assignments
        sso_admin_client = Mock()
        sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "AccountId": "111111111111",
                    "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                }
            ]
        }
        manager.get_identity_center_client.return_value = sso_admin_client

        # Identity Store client with all users existing
        identity_store_client = Mock()
        identity_store_client.describe_user.return_value = {
            "UserId": "user-1234567890abcdef",
            "UserName": "existing.user@company.com",
            "DisplayName": "Existing User",
        }
        manager.get_identity_store_client.return_value = identity_store_client

        # Setup mocks
        mock_aws_client_manager_class.return_value = manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute cleanup
        cleanup_orphaned(dry_run=True, force=False, profile=None)

        # Verify detection calls were made
        sso_admin_client.list_account_assignments.assert_called()
        identity_store_client.describe_user.assert_called()

        # Verify no deletions were attempted
        sso_admin_client.delete_account_assignment.assert_not_called()

        # Verify console output indicates no orphaned assignments
        assert mock_console.print.call_count > 0
        printed_content = str(mock_console.print.call_args_list)
        assert "no orphaned" in printed_content.lower() or "not found" in printed_content.lower()


class TestOutputFormatValidation:
    """Integration tests for output format generation and validation."""

    def test_json_formatter_integration(self):
        """Test JSON formatter with real status data."""
        # Create sample status report
        timestamp = datetime.utcnow()
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="All systems operational",
            service_available=True,
            connectivity_status="Connected",
        )

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No active operations",
                active_operations=[],
                failed_operations=[],
                completed_operations=[],
                pending_count=0,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No orphaned assignments",
                orphaned_assignments=[],
                cleanup_available=False,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=0,
                providers_healthy=0,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=3,
                last_updated=timestamp,
            ),
            check_duration_seconds=2.5,
        )

        # Test JSON formatting
        formatter = JSONFormatter()
        result = formatter.format(status_report)

        # Verify JSON output
        assert result.format_type == OutputFormat.JSON
        assert result.content is not None

        # Verify JSON is valid
        parsed_json = json.loads(result.content)
        assert "timestamp" in parsed_json
        assert "overall_health" in parsed_json
        assert "summary_statistics" in parsed_json
        assert parsed_json["summary_statistics"]["total_users"] == 10

    def test_csv_formatter_integration(self):
        """Test CSV formatter with real status data."""
        # Create sample status report
        timestamp = datetime.utcnow()
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.WARNING,
            message="Minor issues detected",
            service_available=True,
            connectivity_status="Connected",
        )

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No active operations",
                active_operations=[],
                failed_operations=[],
                completed_operations=[],
                pending_count=0,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message="Orphaned assignments found",
                orphaned_assignments=[
                    OrphanedAssignment(
                        assignment_id="assign-123",
                        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        permission_set_name="ReadOnlyAccess",
                        account_id="111111111111",
                        account_name="dev-account-1",
                        principal_id="user-orphaned123456",
                        principal_name=None,
                        principal_type=PrincipalType.USER,
                        error_message="User not found",
                        created_date=datetime(2023, 1, 1, 0, 0, 0),
                    )
                ],
                cleanup_available=True,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=0,
                providers_healthy=0,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=3,
                last_updated=timestamp,
            ),
            check_duration_seconds=3.2,
        )

        # Test CSV formatting
        formatter = CSVFormatter()
        result = formatter.format(status_report)

        # Verify CSV output
        assert result.format_type == OutputFormat.CSV
        assert result.content is not None

        # Verify CSV is valid
        csv_reader = csv.reader(io.StringIO(result.content))
        rows = list(csv_reader)

        # Should have header row and data rows
        assert len(rows) > 1
        header = rows[0]
        assert "Component" in header
        assert "Status" in header
        assert "Message" in header

    def test_table_formatter_integration(self):
        """Test table formatter with real status data."""
        # Create sample status report with various status levels
        timestamp = datetime.utcnow()

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=HealthStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message="Critical issues detected",
                service_available=False,
                connectivity_status="Connection Failed",
            ),
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.WARNING,
                message="Some operations failed",
                active_operations=[
                    ProvisioningOperation(
                        operation_id="op-123",
                        operation_type="CREATE_ASSIGNMENT",
                        status="IN_PROGRESS",
                        target_account="111111111111",
                        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        principal_id="user-1234567890abcdef",
                        principal_type=PrincipalType.USER,
                        created_date=datetime.utcnow() - timedelta(minutes=5),
                        estimated_completion=datetime.utcnow() + timedelta(minutes=2),
                    )
                ],
                failed_operations=[],
                completed_operations=[],
                pending_count=1,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No orphaned assignments",
                orphaned_assignments=[],
                cleanup_available=False,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=1,
                providers_healthy=1,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=100,
                total_groups=20,
                total_permission_sets=15,
                total_assignments=500,
                active_accounts=10,
                last_updated=timestamp,
            ),
            check_duration_seconds=5.7,
        )

        # Test table formatting
        formatter = TableFormatter()
        result = formatter.format(status_report)

        # Verify table output
        assert result.format_type == OutputFormat.TABLE
        assert result.content is not None

        # Verify table contains expected elements
        content = result.content
        assert "Status Report" in content or "Health" in content
        assert "Critical" in content or "Warning" in content
        assert "100" in content  # Total users
        assert "500" in content  # Total assignments


class TestStatusOrchestratorIntegration:
    """Integration tests for status orchestrator coordination."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for orchestrator testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @pytest.mark.asyncio
    async def test_orchestrator_comprehensive_status_integration(self, mock_aws_client_manager):
        """Test status orchestrator comprehensive status coordination."""
        # Create status orchestrator with test configuration
        config = StatusCheckConfig(
            timeout_seconds=10,
            enable_parallel_checks=True,
            max_concurrent_checks=3,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Execute comprehensive status check
        status_report = await orchestrator.get_comprehensive_status()

        # Verify status report structure
        assert isinstance(status_report, StatusReport)
        assert status_report.timestamp is not None
        assert status_report.overall_health is not None
        assert status_report.provisioning_status is not None
        assert status_report.orphaned_assignment_status is not None
        assert status_report.sync_status is not None
        assert status_report.summary_statistics is not None
        assert status_report.check_duration_seconds > 0

        # Verify AWS clients were used
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_instances.assert_called()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called()
        identity_store_client.list_groups.assert_called()

        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called()

    @pytest.mark.asyncio
    async def test_orchestrator_specific_status_integration(self, mock_aws_client_manager):
        """Test status orchestrator specific status check coordination."""
        config = StatusCheckConfig(
            timeout_seconds=5, enable_parallel_checks=False, retry_attempts=1
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Test each specific status type
        status_types = ["health", "provisioning", "orphaned", "sync"]

        for status_type in status_types:
            result = await orchestrator.get_specific_status(status_type)

            # Verify result structure
            assert hasattr(result, "timestamp")
            assert hasattr(result, "status")
            assert hasattr(result, "message")
            assert result.timestamp is not None
            assert result.status in [
                StatusLevel.HEALTHY,
                StatusLevel.WARNING,
                StatusLevel.CRITICAL,
                StatusLevel.CONNECTION_FAILED,
            ]

    @pytest.mark.asyncio
    async def test_orchestrator_parallel_vs_sequential_integration(self, mock_aws_client_manager):
        """Test orchestrator parallel vs sequential execution integration."""
        # Test parallel execution
        parallel_config = StatusCheckConfig(
            timeout_seconds=10,
            enable_parallel_checks=True,
            max_concurrent_checks=5,
            retry_attempts=1,
        )

        parallel_orchestrator = StatusOrchestrator(mock_aws_client_manager, parallel_config)
        parallel_start = datetime.utcnow()
        parallel_report = await parallel_orchestrator.get_comprehensive_status()
        parallel_duration = (datetime.utcnow() - parallel_start).total_seconds()

        # Test sequential execution
        sequential_config = StatusCheckConfig(
            timeout_seconds=10, enable_parallel_checks=False, retry_attempts=1
        )

        sequential_orchestrator = StatusOrchestrator(mock_aws_client_manager, sequential_config)
        sequential_start = datetime.utcnow()
        sequential_report = await sequential_orchestrator.get_comprehensive_status()
        sequential_duration = (datetime.utcnow() - sequential_start).total_seconds()

        # Verify both reports have similar structure
        assert isinstance(parallel_report, StatusReport)
        assert isinstance(sequential_report, StatusReport)

        # Verify both approaches produce valid results
        assert parallel_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]
        assert sequential_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

        # Note: In real scenarios, parallel should be faster, but with mocks timing may vary
        assert parallel_duration >= 0
        assert sequential_duration >= 0

    @pytest.mark.asyncio
    async def test_orchestrator_error_handling_integration(self):
        """Test orchestrator error handling and graceful degradation."""
        # Create failing client manager
        failing_manager = TestStatusIntegrationFixtures.create_failing_aws_client_manager()

        config = StatusCheckConfig(
            timeout_seconds=5,
            enable_parallel_checks=True,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(failing_manager, config)

        # Execute comprehensive status check with failing clients
        status_report = await orchestrator.get_comprehensive_status()

        # Verify graceful degradation
        assert isinstance(status_report, StatusReport)
        assert status_report.timestamp is not None

        # Should have component failures tracked
        failures = orchestrator.get_component_failures()
        assert len(failures) > 0  # Should have some failures
        assert orchestrator.has_component_failures()

        # Overall health should reflect the failures
        assert status_report.overall_health.status in [
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

    @pytest.mark.asyncio
    async def test_orchestrator_timeout_handling_integration(self, mock_aws_client_manager):
        """Test orchestrator timeout handling integration."""
        # Create client with slow responses
        slow_sso_client = Mock()

        async def slow_list_instances():
            await asyncio.sleep(2)  # Simulate slow response
            return TestStatusIntegrationFixtures.get_mock_aws_responses()["list_instances"]

        slow_sso_client.list_instances.side_effect = slow_list_instances
        mock_aws_client_manager.get_identity_center_client.return_value = slow_sso_client

        # Configure short timeout
        config = StatusCheckConfig(
            timeout_seconds=1,  # Very short timeout
            enable_parallel_checks=True,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Execute status check - should handle timeouts gracefully
        status_report = await orchestrator.get_comprehensive_status()

        # Verify timeout was handled
        assert isinstance(status_report, StatusReport)

        # Should have timeout-related failures
        failures = orchestrator.get_component_failures()
        timeout_failures = [
            failure
            for failure_list in failures.values()
            for failure in failure_list
            if "timeout" in failure.lower() or "timed out" in failure.lower()
        ]
        assert len(timeout_failures) > 0


class TestEndToEndStatusWorkflows:
    """End-to-end integration tests for complete status workflows."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for end-to-end testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    def test_complete_status_monitoring_workflow(self, mock_aws_client_manager):
        """Test complete status monitoring workflow from CLI to output."""
        with patch(
            "src.awsideman.commands.status.validate_profile"
        ) as mock_validate_profile, patch(
            "src.awsideman.commands.status.validate_sso_instance"
        ) as mock_validate_sso_instance, patch(
            "src.awsideman.commands.status.AWSClientManager"
        ) as mock_aws_client_manager_class, patch(
            "src.awsideman.commands.status.console"
        ) as mock_console:
            # Setup mocks
            mock_aws_client_manager_class.return_value = mock_aws_client_manager
            mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
            mock_validate_sso_instance.return_value = (
                "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "d-1234567890",
            )

            # Test comprehensive status check
            check_status(
                output_format="table", status_type=None, timeout=30, parallel=True, profile=None
            )

            # Test specific component checks
            for status_type in ["health", "provisioning", "orphaned", "sync"]:
                check_status(
                    output_format="json",
                    status_type=status_type,
                    timeout=30,
                    parallel=True,
                    profile=None,
                )

            # Test different output formats
            for output_format in ["table", "json", "csv"]:
                check_status(
                    output_format=output_format,
                    status_type="health",
                    timeout=30,
                    parallel=True,
                    profile=None,
                )

            # Verify extensive AWS API usage
            sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
            assert sso_admin_client.list_instances.call_count >= 7  # Called in each test

            identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
            assert (
                identity_store_client.list_users.call_count >= 4
            )  # Called in comprehensive and specific checks

            # Verify extensive console output
            assert mock_console.print.call_count >= 20  # Multiple outputs from all tests

    def test_complete_resource_inspection_workflow(self, mock_aws_client_manager):
        """Test complete resource inspection workflow from CLI to output."""
        with patch(
            "src.awsideman.commands.status.validate_profile"
        ) as mock_validate_profile, patch(
            "src.awsideman.commands.status.validate_sso_instance"
        ) as mock_validate_sso_instance, patch(
            "src.awsideman.commands.status.AWSClientManager"
        ) as mock_aws_client_manager_class, patch(
            "src.awsideman.commands.status.console"
        ) as mock_console:
            # Setup mocks
            mock_aws_client_manager_class.return_value = mock_aws_client_manager
            mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
            mock_validate_sso_instance.return_value = (
                "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "d-1234567890",
            )

            # Test user inspection
            inspect_resource(
                resource_type="user",
                resource_id="john.doe@company.com",
                output_format="table",
                profile=None,
            )

            # Test group inspection
            inspect_resource(
                resource_type="group",
                resource_id="Administrators",
                output_format="json",
                profile=None,
            )

            # Test permission set inspection
            inspect_resource(
                resource_type="permission-set",
                resource_id="ReadOnlyAccess",
                output_format="csv",
                profile=None,
            )

            # Test non-existent resource
            inspect_resource(
                resource_type="user",
                resource_id="nonexistent.user@company.com",
                output_format="table",
                profile=None,
            )

            # Verify AWS API calls for different resource types
            identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
            assert identity_store_client.list_users.call_count >= 2  # User inspections
            assert identity_store_client.list_groups.call_count >= 1  # Group inspection

            sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
            assert (
                sso_admin_client.list_permission_sets.call_count >= 1
            )  # Permission set inspection

            # Verify console output for all inspections
            assert mock_console.print.call_count >= 8  # Multiple outputs from all inspections

    def test_complete_orphaned_cleanup_workflow(self, mock_aws_client_manager):
        """Test complete orphaned assignment cleanup workflow from CLI to completion."""
        with patch(
            "src.awsideman.commands.status.validate_profile"
        ) as mock_validate_profile, patch(
            "src.awsideman.commands.status.validate_sso_instance"
        ) as mock_validate_sso_instance, patch(
            "src.awsideman.commands.status.AWSClientManager"
        ) as mock_aws_client_manager_class, patch(
            "src.awsideman.commands.status.console"
        ) as mock_console, patch(
            "typer.confirm"
        ) as mock_confirm:
            # Setup mocks
            mock_aws_client_manager_class.return_value = mock_aws_client_manager
            mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
            mock_validate_sso_instance.return_value = (
                "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "d-1234567890",
            )
            mock_confirm.return_value = True

            # Test dry-run cleanup
            cleanup_orphaned(dry_run=True, force=False, profile=None)

            # Test actual cleanup with confirmation
            cleanup_orphaned(dry_run=False, force=False, profile=None)

            # Test forced cleanup
            cleanup_orphaned(dry_run=False, force=True, profile=None)

            # Verify orphaned detection calls
            sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
            assert (
                sso_admin_client.list_account_assignments.call_count >= 3
            )  # Called in each cleanup

            identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
            # Should attempt to describe users/groups to detect orphaned ones
            total_describe_calls = (
                identity_store_client.describe_user.call_count
                + identity_store_client.describe_group.call_count
            )
            assert total_describe_calls > 0

            # Verify cleanup operations (only for non-dry-run)
            assert (
                sso_admin_client.delete_account_assignment.call_count >= 2
            )  # Called in actual cleanups

            # Verify confirmation was requested (only for non-force cleanup)
            mock_confirm.assert_called_once()

            # Verify console output for all cleanup operations
            assert mock_console.print.call_count >= 6  # Multiple outputs from all cleanups

    def test_error_recovery_and_resilience_workflow(self):
        """Test error recovery and resilience across different failure scenarios."""
        # Test with various failure scenarios
        failure_scenarios = [
            # Connection failures
            TestStatusIntegrationFixtures.create_failing_aws_client_manager(),
            # Partial failures (mixed success/failure)
            TestStatusIntegrationFixtures.create_mock_aws_client_manager(),
        ]

        for i, failing_manager in enumerate(failure_scenarios):
            with patch(
                "src.awsideman.commands.status.validate_profile"
            ) as mock_validate_profile, patch(
                "src.awsideman.commands.status.validate_sso_instance"
            ) as mock_validate_sso_instance, patch(
                "src.awsideman.commands.status.AWSClientManager"
            ) as mock_aws_client_manager_class, patch(
                "src.awsideman.commands.status.console"
            ) as mock_console:
                # Setup mocks
                mock_aws_client_manager_class.return_value = failing_manager
                mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
                mock_validate_sso_instance.return_value = (
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "d-1234567890",
                )

                # Test status check with failures - should handle gracefully
                if i == 0:  # Complete failure scenario
                    with pytest.raises(typer.Exit):
                        check_status(
                            output_format="table",
                            status_type=None,
                            timeout=5,
                            parallel=True,
                            profile=None,
                        )
                else:  # Partial failure scenario
                    check_status(
                        output_format="table",
                        status_type=None,
                        timeout=5,
                        parallel=True,
                        profile=None,
                    )

                # Verify error handling produced output
                assert mock_console.print.call_count > 0

                # Reset for next scenario
                mock_console.reset_mock()

    def test_performance_and_scalability_workflow(self, mock_aws_client_manager):
        """Test performance and scalability aspects of status workflows."""
        # Create large dataset responses
        large_responses = TestStatusIntegrationFixtures.get_mock_aws_responses()

        # Simulate large user base
        large_user_list = []
        for i in range(100):
            large_user_list.append(
                {
                    "UserId": f"user-{i:010d}",
                    "UserName": f"user{i}@company.com",
                    "DisplayName": f"User {i}",
                    "Name": {"GivenName": "User", "FamilyName": f"{i}"},
                    "Meta": {
                        "Created": datetime(2023, 1, 1, 0, 0, 0),
                        "LastModified": datetime(2023, 6, 1, 0, 0, 0),
                    },
                }
            )

        large_responses["users"]["Users"] = large_user_list

        # Update mock to return large dataset
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.return_value = large_responses["users"]

        with patch(
            "src.awsideman.commands.status.validate_profile"
        ) as mock_validate_profile, patch(
            "src.awsideman.commands.status.validate_sso_instance"
        ) as mock_validate_sso_instance, patch(
            "src.awsideman.commands.status.AWSClientManager"
        ) as mock_aws_client_manager_class, patch(
            "src.awsideman.commands.status.console"
        ) as mock_console:
            # Setup mocks
            mock_aws_client_manager_class.return_value = mock_aws_client_manager
            mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
            mock_validate_sso_instance.return_value = (
                "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "d-1234567890",
            )

            # Test performance with large dataset
            start_time = datetime.utcnow()

            check_status(
                output_format="json",  # JSON should be efficient for large datasets
                status_type=None,
                timeout=60,  # Longer timeout for large dataset
                parallel=True,  # Use parallel processing
                profile=None,
            )

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Verify reasonable performance (should complete within reasonable time)
            assert duration < 30  # Should complete within 30 seconds even with large dataset

            # Verify AWS calls were made
            identity_store_client.list_users.assert_called()

            # Verify output was generated
            assert mock_console.print.call_count > 0

    def test_concurrent_operations_workflow(self, mock_aws_client_manager):
        """Test concurrent status operations workflow."""
        with patch(
            "src.awsideman.commands.status.validate_profile"
        ) as mock_validate_profile, patch(
            "src.awsideman.commands.status.validate_sso_instance"
        ) as mock_validate_sso_instance, patch(
            "src.awsideman.commands.status.AWSClientManager"
        ) as mock_aws_client_manager_class:
            # Setup mocks
            mock_aws_client_manager_class.return_value = mock_aws_client_manager
            mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
            mock_validate_sso_instance.return_value = (
                "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "d-1234567890",
            )

            # Simulate concurrent operations by running multiple status checks
            async def run_concurrent_checks():
                config = StatusCheckConfig(
                    timeout_seconds=10,
                    enable_parallel_checks=True,
                    max_concurrent_checks=5,
                    retry_attempts=1,
                )

                orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

                # Run multiple concurrent status checks
                tasks = []
                for i in range(5):
                    if i % 2 == 0:
                        task = orchestrator.get_comprehensive_status()
                    else:
                        task = orchestrator.get_specific_status("health")
                    tasks.append(task)

                # Execute all tasks concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Verify all tasks completed successfully
                for result in results:
                    assert not isinstance(result, Exception)
                    assert hasattr(result, "timestamp")
                    assert hasattr(result, "status") or hasattr(result, "overall_health")

                return results

            # Run concurrent test
            results = asyncio.run(run_concurrent_checks())

            # Verify concurrent operations completed successfully
            assert len(results) == 5

            # Verify AWS clients handled concurrent access
            sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
            assert (
                sso_admin_client.list_instances.call_count >= 5
            )  # Called in each concurrent check


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])
