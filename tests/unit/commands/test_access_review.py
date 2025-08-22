"""Tests for access review commands."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from src.awsideman.commands.access_review import app


@pytest.fixture
def runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration."""
    with patch("src.awsideman.commands.access_review.config") as mock:
        mock.get.side_effect = lambda key, default=None: {
            "default_profile": "test-profile",
            "profiles": {
                "test-profile": {
                    "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                    "identity_store_id": "d-123456789",
                    "region": "us-east-1",
                }
            },
        }.get(key, default)
        yield mock


@pytest.fixture
def mock_client_manager():
    """Mock AWS client manager."""
    with patch("src.awsideman.commands.access_review.AWSClientManager") as mock:
        client_manager = Mock()
        sso_admin_client = Mock()
        identitystore_client = Mock()

        client_manager.get_identity_center_client.return_value = sso_admin_client
        client_manager.get_identity_store_client.return_value = identitystore_client

        mock.return_value = client_manager
        yield {
            "manager": client_manager,
            "sso_admin": sso_admin_client,
            "identitystore": identitystore_client,
        }


def test_export_account_success(runner, mock_config, mock_client_manager):
    """Test successful account export."""

    # Mock the permission sets paginator
    def mock_paginate(*args, **kwargs):
        # Return actual dictionaries, not Mock objects
        return [{"PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-123"]}]

    ps_paginator = Mock()
    ps_paginator.paginate = mock_paginate
    mock_client_manager["sso_admin"].get_paginator.return_value = ps_paginator

    # Mock the list_account_assignments response
    mock_client_manager["sso_admin"].list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "AccountId": "123456789012",
                "PrincipalId": "user-123",
                "PrincipalType": "USER",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            }
        ]
    }

    # Mock permission set description
    mock_client_manager["sso_admin"].describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test permission set"}
    }

    # Mock user description
    mock_client_manager["identitystore"].describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Emails": [{"Value": "test@example.com"}],
    }

    result = runner.invoke(app, ["account", "123456789012"])

    assert result.exit_code == 0
    assert "Exporting permissions for account: 123456789012" in result.stdout
    assert "Found 1 permission assignments" in result.stdout


def test_export_account_invalid_profile(runner):
    """Test export account with invalid profile."""
    with patch("src.awsideman.commands.access_review.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            "default_profile": None,
            "profiles": {},
        }.get(key, default)

        result = runner.invoke(app, ["account", "123456789012"])

        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout


def test_export_principal_success(runner, mock_config, mock_client_manager):
    """Test successful principal export."""
    # Mock user lookup
    mock_client_manager["identitystore"].list_users.return_value = {
        "Users": [{"UserId": "user-123"}]
    }

    # Mock organizations client for account listing
    org_client = Mock()
    org_paginator = Mock()
    org_paginator.paginate.return_value = iter(
        [{"Accounts": [{"Id": "123456789012", "Name": "TestAccount"}]}]
    )
    org_client.get_paginator.return_value = org_paginator
    mock_client_manager["manager"].get_organizations_client.return_value = org_client

    # Mock assignment listing paginator
    assignment_paginator = Mock()
    assignment_paginator.paginate.return_value = iter(
        [
            {
                "AccountAssignments": [
                    {
                        "AccountId": "123456789012",
                        "PrincipalId": "user-123",
                        "PrincipalType": "USER",
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    }
                ]
            }
        ]
    )
    mock_client_manager["sso_admin"].get_paginator.return_value = assignment_paginator

    # Mock permission set description
    mock_client_manager["sso_admin"].describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test permission set"}
    }

    # Mock user lookup for principal resolution
    mock_client_manager["identitystore"].list_users.return_value = {
        "Users": [{"UserId": "user-123", "UserName": "testuser"}]
    }

    # Mock user description
    mock_client_manager["identitystore"].describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Emails": [{"Value": "test@example.com"}],
    }

    result = runner.invoke(app, ["principal", "testuser"])

    assert result.exit_code == 0
    assert "Exporting permissions for principal: testuser" in result.stdout


def test_export_principal_not_found(runner, mock_config, mock_client_manager):
    """Test export principal when principal is not found."""
    # Mock empty user lookup
    mock_client_manager["identitystore"].list_users.return_value = {"Users": []}
    mock_client_manager["identitystore"].list_groups.return_value = {"Groups": []}

    result = runner.invoke(app, ["principal", "nonexistent"])

    assert result.exit_code == 1
    assert "Principal 'nonexistent' not found" in result.stdout


def test_export_permission_set_success(runner, mock_config, mock_client_manager):
    """Test successful permission set export."""
    # Mock permission set lookup
    ps_paginator = Mock()
    ps_paginator.paginate.return_value = [
        {"PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-123"]}
    ]
    mock_client_manager["sso_admin"].get_paginator.return_value = ps_paginator

    # Mock permission set description
    mock_client_manager["sso_admin"].describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test permission set"}
    }

    # Mock organizations client
    org_client = Mock()
    org_paginator = Mock()
    org_paginator.paginate.return_value = iter(
        [{"Accounts": [{"Id": "123456789012", "Name": "TestAccount"}]}]
    )
    org_client.get_paginator.return_value = org_paginator
    mock_client_manager["manager"].get_raw_organizations_client.return_value = org_client

    # Mock assignment listing paginator
    assignment_paginator = Mock()
    assignment_paginator.paginate.return_value = iter(
        [
            {
                "AccountAssignments": [
                    {
                        "AccountId": "123456789012",
                        "PrincipalId": "user-123",
                        "PrincipalType": "USER",
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    }
                ]
            }
        ]
    )
    # Mock both paginators - first for permission sets, then for assignments
    mock_client_manager["sso_admin"].get_paginator.side_effect = [
        ps_paginator,
        assignment_paginator,
    ]

    result = runner.invoke(app, ["permission-set", "TestPermissionSet"])

    assert result.exit_code == 0
    assert "Exporting assignments for permission set: TestPermissionSet" in result.stdout


def test_export_permission_set_not_found(runner, mock_config, mock_client_manager):
    """Test export permission set when permission set is not found."""
    # Mock empty permission set lookup
    ps_paginator = Mock()
    ps_paginator.paginate.return_value = [{"PermissionSets": []}]
    mock_client_manager["sso_admin"].get_paginator.return_value = ps_paginator

    result = runner.invoke(app, ["permission-set", "NonExistent"])

    assert result.exit_code == 1
    assert "Permission set 'NonExistent' not found" in result.stdout


def test_json_output_format(runner, mock_config, mock_client_manager):
    """Test JSON output format."""
    # Mock the permission sets paginator
    ps_paginator = Mock()
    ps_paginator.paginate.return_value = iter(
        [{"PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-123"]}]
    )
    mock_client_manager["sso_admin"].get_paginator.return_value = ps_paginator

    # Mock the list_account_assignments response
    mock_client_manager["sso_admin"].list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "AccountId": "123456789012",
                "PrincipalId": "user-123",
                "PrincipalType": "USER",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            }
        ]
    }

    # Mock permission set description
    mock_client_manager["sso_admin"].describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test permission set"}
    }

    # Mock user description
    mock_client_manager["identitystore"].describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Emails": [{"Value": "test@example.com"}],
    }

    result = runner.invoke(app, ["account", "123456789012", "--format", "json"])

    assert result.exit_code == 0
    assert '"account_id": "123456789012"' in result.stdout
    assert '"total_assignments": 1' in result.stdout


def test_csv_output_format(runner, mock_config, mock_client_manager, tmp_path):
    """Test CSV output format."""
    # Mock the permission sets paginator
    ps_paginator = Mock()
    ps_paginator.paginate.return_value = iter(
        [{"PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-123"]}]
    )
    mock_client_manager["sso_admin"].get_paginator.return_value = ps_paginator

    # Mock the list_account_assignments response
    mock_client_manager["sso_admin"].list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "AccountId": "123456789012",
                "PrincipalId": "user-123",
                "PrincipalType": "USER",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            }
        ]
    }

    # Mock permission set description
    mock_client_manager["sso_admin"].describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test permission set"}
    }

    # Mock user description
    mock_client_manager["identitystore"].describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Emails": [{"Value": "test@example.com"}],
    }

    output_file = tmp_path / "test_output.csv"
    result = runner.invoke(
        app, ["account", "123456789012", "--format", "csv", "--output", str(output_file)]
    )

    assert result.exit_code == 0
    assert "CSV output written to:" in result.stdout
    assert output_file.name in result.stdout  # Just check for the filename, not the full path
    assert output_file.exists()


def test_aws_error_handling(runner, mock_config, mock_client_manager):
    """Test AWS error handling."""
    # Mock a ClientError
    error_response = {
        "Error": {
            "Code": "AccessDenied",
            "Message": "User is not authorized to perform this action",
        }
    }
    client_error = ClientError(error_response, "ListAccountAssignments")

    # Make the paginator raise the error
    mock_client_manager["sso_admin"].get_paginator.side_effect = client_error

    result = runner.invoke(app, ["account", "123456789012"])

    assert result.exit_code == 1
    assert "AWS Error (AccessDenied)" in result.stdout
    assert "User is not authorized to perform this action" in result.stdout
