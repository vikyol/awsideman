"""Integration tests for multi-account end-to-end workflows.

This module contains integration tests that test the complete multi-account
workflows from command invocation to final results, including:
- Complete multi-account assignment workflow
- Complete multi-account revocation workflow
- Dry-run validation across multiple accounts
- Mixed success/failure scenarios

These tests verify the integration between CLI commands, account filtering,
batch processing, progress tracking, and result reporting.
"""
from datetime import datetime
from typing import List
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.commands.assignment import (
    _execute_multi_account_assignment,
    _execute_multi_account_revocation,
    assign_permission_set,
)
from src.awsideman.utils.models import AccountInfo


class TestMultiAccountIntegrationFixtures:
    """Test fixtures and mock data for multi-account integration tests."""

    @staticmethod
    def get_sample_accounts() -> List[AccountInfo]:
        """Get sample account data for testing."""
        return [
            AccountInfo(
                account_id="111111111111",
                account_name="dev-account-1",
                email="dev1@company.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Backend"},
                ou_path=["Root", "Development"],
            ),
            AccountInfo(
                account_id="222222222222",
                account_name="dev-account-2",
                email="dev2@company.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Frontend"},
                ou_path=["Root", "Development"],
            ),
            AccountInfo(
                account_id="333333333333",
                account_name="prod-account-1",
                email="prod1@company.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Backend"},
                ou_path=["Root", "Production"],
            ),
            AccountInfo(
                account_id="444444444444",
                account_name="staging-account",
                email="staging@company.com",
                status="ACTIVE",
                tags={"Environment": "Staging", "Team": "QA"},
                ou_path=["Root", "Staging"],
            ),
        ]

    @staticmethod
    def get_mock_aws_responses():
        """Get mock AWS API responses for testing."""
        return {
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
                    {
                        "Id": "444444444444",
                        "Name": "staging-account",
                        "Email": "staging@company.com",
                        "Status": "ACTIVE",
                    },
                ]
            },
            "account_tags": {
                "111111111111": [
                    {"Key": "Environment", "Value": "Development"},
                    {"Key": "Team", "Value": "Backend"},
                ],
                "222222222222": [
                    {"Key": "Environment", "Value": "Development"},
                    {"Key": "Team", "Value": "Frontend"},
                ],
                "333333333333": [
                    {"Key": "Environment", "Value": "Production"},
                    {"Key": "Team", "Value": "Backend"},
                ],
                "444444444444": [
                    {"Key": "Environment", "Value": "Staging"},
                    {"Key": "Team", "Value": "QA"},
                ],
            },
            "permission_sets": {
                "PermissionSets": [
                    "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess"
                ]
            },
            "permission_set_details": {
                "PermissionSet": {
                    "Name": "ReadOnlyAccess",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "Description": "Read-only access permission set",
                    "SessionDuration": "PT8H",
                }
            },
            "users": {
                "Users": [
                    {
                        "UserId": "user-1234567890abcdef",
                        "UserName": "john.doe@company.com",
                        "DisplayName": "John Doe",
                        "Name": {"GivenName": "John", "FamilyName": "Doe"},
                    }
                ]
            },
            "groups": {
                "Groups": [
                    {
                        "GroupId": "group-1234567890abcdef",
                        "DisplayName": "DevTeam",
                        "Description": "Development team group",
                    }
                ]
            },
            "successful_assignment": {
                "AccountAssignmentCreationStatus": {
                    "Status": "SUCCEEDED",
                    "RequestId": "req-1234567890abcdef",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "TargetId": "111111111111",
                    "TargetType": "AWS_ACCOUNT",
                }
            },
            "successful_revocation": {
                "AccountAssignmentDeletionStatus": {
                    "Status": "SUCCEEDED",
                    "RequestId": "req-1234567890abcdef",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "TargetId": "111111111111",
                    "TargetType": "AWS_ACCOUNT",
                }
            },
            "existing_assignments": {
                "AccountAssignments": [
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        "PrincipalId": "user-1234567890abcdef",
                        "PrincipalType": "USER",
                        "AccountId": "111111111111",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                ]
            },
            "empty_assignments": {"AccountAssignments": []},
        }


class TestMultiAccountAssignWorkflow:
    """Integration tests for complete multi-account assignment workflow."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create comprehensive mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client
        organizations_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()

        organizations_client.list_accounts.return_value = responses["organizations_accounts"]

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = responses[
            "organizations_accounts"
        ]

        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": responses["account_tags"].get(ResourceId, [])}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["empty_assignments"]
        sso_admin_client.create_account_assignment.return_value = responses["successful_assignment"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        identity_store_client.list_groups.return_value = responses["groups"]
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("typer.confirm")
    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_complete_multi_assign_workflow_wildcard_filter(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager,
    ):
        """Test complete multi-account assignment workflow with wildcard filter."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # Auto-confirm the operation

        # Execute multi-account assignment command
        assign_permission_set(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=False,
            batch_size=10,
            profile=None,
        )

        # Verify Organizations API was called to list accounts
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called_once()

        # Verify account tags were retrieved for filtering
        assert organizations_client.list_tags_for_resource.call_count >= 4

        # Verify permission set resolution
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_permission_sets.assert_called_once()
        sso_admin_client.describe_permission_set.assert_called()

        # Verify user resolution
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called_once()

        # Verify assignments were created for all accounts
        assert sso_admin_client.create_account_assignment.call_count == 4

        # Verify each account had assignment created
        expected_account_ids = ["111111111111", "222222222222", "333333333333", "444444444444"]
        actual_calls = sso_admin_client.create_account_assignment.call_args_list

        for i, call_args in enumerate(actual_calls):
            assert call_args[1]["TargetId"] in expected_account_ids
            assert (
                call_args[1]["PermissionSetArn"]
                == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess"
            )
            assert call_args[1]["PrincipalId"] == "user-1234567890abcdef"
            assert call_args[1]["PrincipalType"] == "USER"

    @patch("typer.confirm")
    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_complete_multi_assign_workflow_tag_filter(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager,
    ):
        """Test complete multi-assign workflow with tag-based filter."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # Auto-confirm the operation

        # Execute multi-account assignment command with tag filter
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="tag:Environment=Development",
            principal_type="USER",
            dry_run=False,
            batch_size=10,
            profile=None,
        )

        # Verify Organizations API was called
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called_once()
        organizations_client.list_tags_for_resource.assert_called()

        # Verify assignments were created only for development accounts
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        assert sso_admin_client.create_account_assignment.call_count == 2  # Only dev accounts

        # Verify correct accounts were targeted
        actual_calls = sso_admin_client.create_account_assignment.call_args_list
        targeted_accounts = [call_args[1]["TargetId"] for call_args in actual_calls]

        # Should only include development accounts
        assert "111111111111" in targeted_accounts  # dev-account-1
        assert "222222222222" in targeted_accounts  # dev-account-2
        assert "333333333333" not in targeted_accounts  # prod-account-1
        assert "444444444444" not in targeted_accounts  # staging-account

    @patch("typer.confirm")
    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_complete_multi_assign_workflow_group_principal(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager,
    ):
        """Test complete multi-assign workflow with GROUP principal type."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # Auto-confirm the operation

        # Execute multi-account assignment command with group principal
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="DevTeam",
            account_filter="*",
            principal_type="GROUP",
            dry_run=False,
            batch_size=10,
            profile=None,
        )

        # Verify group resolution instead of user resolution
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_groups.assert_called_once()
        identity_store_client.list_users.assert_not_called()

        # Verify assignments were created with GROUP principal type
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        actual_calls = sso_admin_client.create_account_assignment.call_args_list

        for call_args in actual_calls:
            assert call_args[1]["PrincipalType"] == "GROUP"
            assert call_args[1]["PrincipalId"] == "group-1234567890abcdef"


class TestMultiAccountRevokeWorkflow:
    """Integration tests for complete multi-revoke workflow."""

    @pytest.fixture
    def mock_aws_client_manager_with_existing_assignments(self):
        """Create mock AWS client manager with existing assignments."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client
        organizations_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()

        organizations_client.list_accounts.return_value = responses["organizations_accounts"]

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = responses[
            "organizations_accounts"
        ]

        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": responses["account_tags"].get(ResourceId, [])}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client with existing assignments
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["existing_assignments"]
        sso_admin_client.delete_account_assignment.return_value = responses["successful_revocation"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        identity_store_client.list_groups.return_value = responses["groups"]
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_complete_multi_revoke_workflow_wildcard_filter(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager_with_existing_assignments,
    ):
        """Test complete multi-revoke workflow with wildcard filter."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = (
            mock_aws_client_manager_with_existing_assignments
        )
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account revocation command
        _execute_multi_account_revocation(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=False,
            batch_size=10,
            force=True,  # Skip confirmation
            profile=None,
        )

        # Verify Organizations API was called to list accounts
        organizations_client = (
            mock_aws_client_manager_with_existing_assignments.get_organizations_client.return_value
        )
        organizations_client.list_accounts.assert_called_once()

        # Verify permission set and user resolution
        sso_admin_client = (
            mock_aws_client_manager_with_existing_assignments.get_identity_center_client.return_value
        )
        sso_admin_client.list_permission_sets.assert_called_once()

        identity_store_client = (
            mock_aws_client_manager_with_existing_assignments.get_identity_store_client.return_value
        )
        identity_store_client.list_users.assert_called_once()

        # Verify existing assignments were checked for each account
        assert sso_admin_client.list_account_assignments.call_count >= 4

        # Verify revocations were attempted for accounts with existing assignments
        assert sso_admin_client.delete_account_assignment.call_count >= 1

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_complete_multi_revoke_workflow_tag_filter(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager_with_existing_assignments,
    ):
        """Test complete multi-revoke workflow with tag-based filter."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = (
            mock_aws_client_manager_with_existing_assignments
        )
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account revocation command with tag filter
        _execute_multi_account_revocation(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="tag:Environment=Production",
            principal_type="USER",
            dry_run=False,
            batch_size=10,
            force=True,
            profile=None,
        )

        # Verify Organizations API was called
        organizations_client = (
            mock_aws_client_manager_with_existing_assignments.get_organizations_client.return_value
        )
        organizations_client.list_accounts.assert_called_once()
        organizations_client.list_tags_for_resource.assert_called()

        # Verify only production accounts were processed
        sso_admin_client = (
            mock_aws_client_manager_with_existing_assignments.get_identity_center_client.return_value
        )

        # Should check assignments only for production account
        list_assignment_calls = sso_admin_client.list_account_assignments.call_args_list
        production_account_processed = any(
            "333333333333" in str(call) for call in list_assignment_calls
        )
        assert production_account_processed


class TestMultiAccountDryRunWorkflow:
    """Integration tests for dry-run validation across multiple accounts."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for dry-run testing."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client
        organizations_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()

        organizations_client.list_accounts.return_value = responses["organizations_accounts"]

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = responses[
            "organizations_accounts"
        ]

        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": responses["account_tags"].get(ResourceId, [])}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["empty_assignments"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_assign_dry_run_validation(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test multi-assign dry-run validation across multiple accounts."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account assignment command with dry-run
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=True,
            batch_size=10,
            profile=None,
        )

        # Verify account discovery and filtering occurred
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called_once()

        # Verify name resolution occurred
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_permission_sets.assert_called_once()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called_once()

        # Verify NO actual assignments were created in dry-run mode
        sso_admin_client.create_account_assignment.assert_not_called()

        # Verify existing assignments were checked for preview
        assert sso_admin_client.list_account_assignments.call_count >= 4

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_revoke_dry_run_validation(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test multi-revoke dry-run validation across multiple accounts."""
        # Setup mocks with existing assignments
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Mock existing assignments for dry-run preview
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_account_assignments.return_value = responses["existing_assignments"]

        # Execute multi-account revocation command with dry-run
        _execute_multi_account_revocation(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=True,
            batch_size=10,
            force=True,
            profile=None,
        )

        # Verify account discovery occurred
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called_once()

        # Verify name resolution occurred
        sso_admin_client.list_permission_sets.assert_called_once()

        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.assert_called_once()

        # Verify existing assignments were checked for preview
        assert sso_admin_client.list_account_assignments.call_count >= 4

        # Verify NO actual revocations were performed in dry-run mode
        sso_admin_client.delete_account_assignment.assert_not_called()

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_dry_run_with_tag_filter_validation(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager,
    ):
        """Test dry-run validation with tag-based account filtering."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account assignment command with tag filter and dry-run
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="tag:Environment=Development",
            principal_type="USER",
            dry_run=True,
            batch_size=10,
            profile=None,
        )

        # Verify account discovery and tag filtering occurred
        organizations_client = mock_aws_client_manager.get_organizations_client.return_value
        organizations_client.list_accounts.assert_called_once()
        organizations_client.list_tags_for_resource.assert_called()

        # Verify name resolution occurred
        sso_admin_client = mock_aws_client_manager.get_identity_center_client.return_value
        sso_admin_client.list_permission_sets.assert_called_once()

        # Verify NO assignments were created
        sso_admin_client.create_account_assignment.assert_not_called()

        # Verify existing assignments were checked only for filtered accounts
        # Should be called for development accounts only (2 accounts)
        assert sso_admin_client.list_account_assignments.call_count >= 2


class TestMultiAccountMixedScenarios:
    """Integration tests for mixed success/failure scenarios."""

    @pytest.fixture
    def mock_aws_client_manager_mixed_results(self):
        """Create mock AWS client manager that simulates mixed success/failure results."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client
        organizations_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()

        organizations_client.list_accounts.return_value = responses["organizations_accounts"]

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = responses[
            "organizations_accounts"
        ]

        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": responses["account_tags"].get(ResourceId, [])}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client with mixed results
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["empty_assignments"]

        # Mock create_account_assignment to fail for specific accounts
        def mock_create_assignment(**kwargs):
            if kwargs["TargetId"] == "333333333333":  # prod-account-1 fails
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "AccessDenied",
                            "Message": "Insufficient permissions for account 333333333333",
                        }
                    },
                    operation_name="CreateAccountAssignment",
                )
            elif kwargs["TargetId"] == "444444444444":  # staging-account fails
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ThrottlingException",
                            "Message": "Rate exceeded for account 444444444444",
                        }
                    },
                    operation_name="CreateAccountAssignment",
                )
            else:
                return responses["successful_assignment"]

        sso_admin_client.create_account_assignment.side_effect = mock_create_assignment
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("typer.confirm")
    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_assign_mixed_success_failure(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager_mixed_results,
    ):
        """Test multi-assign workflow with mixed success/failure scenarios."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager_mixed_results
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # Auto-confirm the operation

        # Execute multi-account assignment command (should handle errors gracefully)
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=False,
            batch_size=10,
            profile=None,
        )

        # Verify all accounts were attempted
        sso_admin_client = (
            mock_aws_client_manager_mixed_results.get_identity_center_client.return_value
        )
        assert sso_admin_client.create_account_assignment.call_count == 4

        # Verify that the command completed despite individual failures
        # (The command should handle errors gracefully and continue processing)
        organizations_client = (
            mock_aws_client_manager_mixed_results.get_organizations_client.return_value
        )
        organizations_client.list_accounts.assert_called_once()

    @pytest.fixture
    def mock_aws_client_manager_name_resolution_failures(self):
        """Create mock AWS client manager that simulates name resolution failures."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client
        organizations_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()

        organizations_client.list_accounts.return_value = responses["organizations_accounts"]

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = responses[
            "organizations_accounts"
        ]

        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": responses["account_tags"].get(ResourceId, [])}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client with permission set resolution failure
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = {
            "PermissionSets": []
        }  # No permission sets found
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client with user resolution failure
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = {"Users": []}  # No users found
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_assign_name_resolution_failures(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager_name_resolution_failures,
    ):
        """Test multi-assign workflow with name resolution failures."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = (
            mock_aws_client_manager_name_resolution_failures
        )
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account assignment command and expect it to handle resolution failures
        with pytest.raises(SystemExit):  # Should exit due to resolution failures
            _execute_multi_account_assignment(
                permission_set_name="NonexistentPermissionSet",
                principal_name="nonexistent.user@company.com",
                account_filter="*",
                principal_type="USER",
                dry_run=False,
                batch_size=10,
                profile=None,
            )

        # Verify name resolution was attempted
        sso_admin_client = (
            mock_aws_client_manager_name_resolution_failures.get_identity_center_client.return_value
        )
        sso_admin_client.list_permission_sets.assert_called_once()

        identity_store_client = (
            mock_aws_client_manager_name_resolution_failures.get_identity_store_client.return_value
        )
        identity_store_client.list_users.assert_called_once()

        # Verify no assignments were attempted due to resolution failures
        sso_admin_client.create_account_assignment.assert_not_called()

    @pytest.fixture
    def mock_aws_client_manager_account_filter_failures(self):
        """Create mock AWS client manager that simulates account filter failures."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client that fails
        organizations_client = Mock()
        organizations_client.list_accounts.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Insufficient permissions to list organization accounts",
                }
            },
            operation_name="ListAccounts",
        )
        manager.get_organizations_client.return_value = organizations_client

        return manager

    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_assign_account_filter_failures(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_aws_client_manager_account_filter_failures,
    ):
        """Test multi-assign workflow with account filter failures."""
        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager_account_filter_failures
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )

        # Execute multi-account assignment command and expect it to handle account filter failures
        with pytest.raises(SystemExit):  # Should exit due to account filter failures
            _execute_multi_account_assignment(
                permission_set_name="ReadOnlyAccess",
                principal_name="john.doe@company.com",
                account_filter="*",
                principal_type="USER",
                dry_run=False,
                batch_size=10,
                profile=None,
            )

        # Verify account listing was attempted
        organizations_client = (
            mock_aws_client_manager_account_filter_failures.get_organizations_client.return_value
        )
        organizations_client.list_accounts.assert_called_once()


class TestMultiAccountPerformanceIntegration:
    """Integration tests for multi-account performance scenarios."""

    @pytest.fixture
    def mock_aws_client_manager_large_scale(self):
        """Create mock AWS client manager for large-scale testing."""
        manager = Mock(spec=AWSClientManager)

        # Mock Organizations client with many accounts
        organizations_client = Mock()

        # Generate 50 mock accounts for performance testing
        large_account_list = {
            "Accounts": [
                {
                    "Id": f"{str(i).zfill(12)}",
                    "Name": f"account-{i}",
                    "Email": f"account{i}@company.com",
                    "Status": "ACTIVE",
                }
                for i in range(1, 51)  # 50 accounts
            ]
        }

        organizations_client.list_accounts.return_value = large_account_list

        # Mock organization hierarchy calls
        organizations_client.list_roots.return_value = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Type": "ROOT",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
            }
        ]

        organizations_client.list_organizational_units_for_parent.return_value = []
        organizations_client.list_accounts_for_parent.return_value = large_account_list

        # Mock tags for all accounts
        def mock_list_tags_for_resource(ResourceId):
            return {"Tags": [{"Key": "Environment", "Value": "Test"}]}

        organizations_client.list_tags_for_resource.side_effect = mock_list_tags_for_resource
        manager.get_organizations_client.return_value = organizations_client

        # Mock SSO Admin client
        sso_admin_client = Mock()
        responses = TestMultiAccountIntegrationFixtures.get_mock_aws_responses()
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.describe_permission_set.return_value = responses["permission_set_details"]
        sso_admin_client.list_account_assignments.return_value = responses["empty_assignments"]
        sso_admin_client.create_account_assignment.return_value = responses["successful_assignment"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        manager.get_identity_store_client.return_value = identity_store_client

        return manager

    @patch("typer.confirm")
    @patch("src.awsideman.commands.assignment.validate_profile")
    @patch("src.awsideman.commands.assignment.validate_sso_instance")
    @patch("src.awsideman.commands.assignment.AWSClientManager")
    @patch("src.awsideman.commands.assignment.console")
    def test_multi_assign_large_scale_performance(
        self,
        mock_console,
        mock_aws_client_manager_class,
        mock_validate_sso_instance,
        mock_validate_profile,
        mock_confirm,
        mock_aws_client_manager_large_scale,
    ):
        """Test multi-assign workflow performance with large number of accounts."""
        import time

        # Setup mocks
        mock_aws_client_manager_class.return_value = mock_aws_client_manager_large_scale
        mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
        mock_validate_sso_instance.return_value = (
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890",
        )
        mock_confirm.return_value = True  # Auto-confirm the operation

        # Measure execution time
        start_time = time.time()

        # Execute multi-account assignment command with large batch size
        _execute_multi_account_assignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            account_filter="*",
            principal_type="USER",
            dry_run=False,
            batch_size=20,  # Large batch size for performance
            profile=None,
        )

        execution_time = time.time() - start_time

        # Verify all 50 accounts were processed
        sso_admin_client = (
            mock_aws_client_manager_large_scale.get_identity_center_client.return_value
        )
        assert sso_admin_client.create_account_assignment.call_count == 50

        # Verify reasonable performance (should complete within reasonable time)
        assert execution_time < 30.0  # Should complete within 30 seconds

        # Verify Organizations API was called efficiently
        organizations_client = (
            mock_aws_client_manager_large_scale.get_organizations_client.return_value
        )
        organizations_client.list_accounts.assert_called_once()  # Should only call once, not per account
