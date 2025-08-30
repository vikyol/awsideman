"""
Unit tests for the Identity Center data collector.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients import AWSClientManager
from src.awsideman.backup_restore.collector import IdentityCenterCollector
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupOptions,
    BackupType,
    GroupData,
    PermissionSetData,
    ResourceType,
    UserData,
)


class TestIdentityCenterCollector:
    """Test cases for IdentityCenterCollector."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)
        manager.region = "us-east-1"
        manager.session = Mock()
        manager.session.get_credentials.return_value = Mock(access_key="test-key")
        return manager

    @pytest.fixture
    def mock_identity_center_client(self):
        """Create a mock Identity Center client."""
        client = Mock()
        client.describe_instance_access_control_attribute_configuration.return_value = {
            "InstanceAccessControlAttributeConfiguration": {
                "AccessControlAttributes": [{"Key": "test-store-id"}]
            }
        }
        client.list_instances.return_value = {
            "Instances": [
                {
                    "InstanceArn": "arn:aws:sso:::instance/test-instance",
                    "IdentityStoreId": "test-store-id",
                }
            ]
        }
        return client

    @pytest.fixture
    def mock_identity_store_client(self):
        """Create a mock Identity Store client."""
        client = Mock()
        client.get_paginator.return_value = Mock()
        return client

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock Organizations client."""
        client = Mock()
        client.list_roots.return_value = [{"Id": "r-test", "Name": "Root"}]
        return client

    @pytest.fixture
    def collector(
        self,
        mock_client_manager,
        mock_identity_center_client,
        mock_identity_store_client,
        mock_organizations_client,
    ):
        """Create a collector instance with mocked clients."""
        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Mock the client properties
        collector._identity_center_client = mock_identity_center_client
        collector._identity_store_client = mock_identity_store_client
        collector._organizations_client = mock_organizations_client
        collector._identity_store_id = "test-store-id"

        return collector

    @pytest.fixture
    def backup_options(self):
        """Create default backup options."""
        return BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            include_inactive_users=False,
            parallel_collection=True,
        )

    @pytest.mark.asyncio
    async def test_get_identity_store_id_success(self, collector, mock_identity_center_client):
        """Test successful retrieval of Identity Store ID."""
        collector._identity_store_id = None  # Reset cached value

        identity_store_id = await collector.get_identity_store_id()

        assert identity_store_id == "test-store-id"
        assert collector._identity_store_id == "test-store-id"

    @pytest.mark.asyncio
    async def test_get_identity_store_id_fallback(self, collector, mock_identity_center_client):
        """Test fallback method for getting Identity Store ID."""
        collector._identity_store_id = None

        identity_store_id = await collector.get_identity_store_id()

        assert identity_store_id == "test-store-id"
        mock_identity_center_client.list_instances.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_identity_store_id_failure(self, collector, mock_identity_center_client):
        """Test failure to get Identity Store ID."""
        collector._identity_store_id = None

        # Make the method fail
        mock_identity_center_client.list_instances.return_value = {"Instances": []}

        with pytest.raises(ValueError, match="Could not determine Identity Store ID"):
            await collector.get_identity_store_id()

    @pytest.mark.asyncio
    async def test_validate_connection_success(self, collector):
        """Test successful connection validation."""
        result = await collector.validate_connection()

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.details["identity_center_connection"] == "OK"
        assert result.details["identity_store_connection"] == "OK"
        assert result.details["organizations_connection"] == "OK"

    @pytest.mark.asyncio
    async def test_validate_connection_identity_center_failure(
        self, collector, mock_identity_center_client
    ):
        """Test connection validation with Identity Center failure."""
        mock_identity_center_client.list_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListInstances"
        )

        result = await collector.validate_connection()

        assert not result.is_valid
        assert len(result.errors) > 0
        assert "Identity Center connection failed" in result.errors[0]
        assert result.details["identity_center_connection"] == "FAILED"

    @pytest.mark.asyncio
    async def test_validate_connection_organizations_warning(
        self, collector, mock_organizations_client
    ):
        """Test connection validation with Organizations warning."""
        mock_organizations_client.list_roots.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListRoots"
        )

        result = await collector.validate_connection()

        assert result.is_valid  # Organizations is optional
        assert len(result.warnings) > 0
        assert "Organizations connection failed (optional)" in result.warnings[0]
        assert result.details["organizations_connection"] == "FAILED"

    @pytest.mark.asyncio
    async def test_collect_users_success(
        self, collector, mock_identity_store_client, backup_options
    ):
        """Test successful user collection."""
        # Mock paginator
        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "Users": [
                    {
                        "UserId": "user-1",
                        "UserName": "john.doe",
                        "DisplayName": "John Doe",
                        "Active": True,
                        "Emails": [{"Value": "john.doe@example.com"}],
                        "Name": {"GivenName": "John", "FamilyName": "Doe"},
                        "ExternalIds": [{"Issuer": "external", "Id": "ext-123"}],
                    },
                    {
                        "UserId": "user-2",
                        "UserName": "jane.smith",
                        "DisplayName": "Jane Smith",
                        "Active": False,
                        "Emails": [{"Value": "jane.smith@example.com"}],
                        "Name": {"GivenName": "Jane", "FamilyName": "Smith"},
                    },
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_store_client.get_paginator.return_value = mock_paginator

        users = await collector.collect_users(backup_options)

        assert len(users) == 1  # Only active user since include_inactive_users=False
        assert users[0].user_id == "user-1"
        assert users[0].user_name == "john.doe"
        assert users[0].display_name == "John Doe"
        assert users[0].email == "john.doe@example.com"
        assert users[0].given_name == "John"
        assert users[0].family_name == "Doe"
        assert users[0].active is True
        assert users[0].external_ids == {"external": "ext-123"}

    @pytest.mark.asyncio
    async def test_collect_users_include_inactive(self, collector, mock_identity_store_client):
        """Test user collection including inactive users."""
        backup_options = BackupOptions(include_inactive_users=True)

        # Mock paginator
        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "Users": [
                    {
                        "UserId": "user-1",
                        "UserName": "john.doe",
                        "Active": True,
                        "Emails": [],
                        "Name": {},
                    },
                    {
                        "UserId": "user-2",
                        "UserName": "jane.smith",
                        "Active": False,
                        "Emails": [],
                        "Name": {},
                    },
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_store_client.get_paginator.return_value = mock_paginator

        users = await collector.collect_users(backup_options)

        assert len(users) == 2  # Both active and inactive users
        assert users[0].active is True
        assert users[1].active is False

    @pytest.mark.asyncio
    async def test_collect_users_client_error(
        self, collector, mock_identity_store_client, backup_options
    ):
        """Test user collection with client error."""
        mock_identity_store_client.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListUsers"
        )

        with pytest.raises(ClientError):
            await collector.collect_users(backup_options)

    @pytest.mark.asyncio
    async def test_collect_groups_success(
        self, collector, mock_identity_store_client, backup_options
    ):
        """Test successful group collection."""
        # Mock paginator for groups
        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "Groups": [
                    {
                        "GroupId": "group-1",
                        "DisplayName": "Administrators",
                        "Description": "Admin group",
                    },
                    {"GroupId": "group-2", "DisplayName": "Users", "Description": "Regular users"},
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator

        # Mock paginator for group memberships
        mock_membership_paginator = Mock()
        mock_membership_iterator = [
            {
                "GroupMemberships": [
                    {"MemberId": {"UserId": "user-1"}},
                    {"MemberId": {"UserId": "user-2"}},
                ]
            }
        ]

        def get_paginator_side_effect(operation_name):
            if operation_name == "list_groups":
                return mock_paginator
            elif operation_name == "list_group_memberships":
                mock_membership_paginator.paginate.return_value = mock_membership_iterator
                return mock_membership_paginator

        mock_identity_store_client.get_paginator.side_effect = get_paginator_side_effect

        groups = await collector.collect_groups(backup_options)

        assert len(groups) == 2
        assert groups[0].group_id == "group-1"
        assert groups[0].display_name == "Administrators"
        assert groups[0].description == "Admin group"
        assert groups[0].members == ["user-1", "user-2"]

    @pytest.mark.asyncio
    async def test_collect_groups_membership_error(
        self, collector, mock_identity_store_client, backup_options
    ):
        """Test group collection with membership retrieval error."""
        # Mock paginator for groups
        mock_paginator = Mock()
        mock_page_iterator = [{"Groups": [{"GroupId": "group-1", "DisplayName": "Administrators"}]}]

        mock_paginator.paginate.return_value = mock_page_iterator

        # Mock paginator for group memberships that fails
        mock_membership_paginator = Mock()
        mock_membership_paginator.paginate.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListGroupMemberships"
        )

        def get_paginator_side_effect(operation_name):
            if operation_name == "list_groups":
                return mock_paginator
            elif operation_name == "list_group_memberships":
                return mock_membership_paginator

        mock_identity_store_client.get_paginator.side_effect = get_paginator_side_effect

        groups = await collector.collect_groups(backup_options)

        assert len(groups) == 1
        assert groups[0].group_id == "group-1"
        assert groups[0].members == []  # Empty due to error

    @pytest.mark.asyncio
    async def test_collect_permission_sets_parallel(
        self, collector, mock_identity_center_client, backup_options
    ):
        """Test parallel permission set collection."""
        # Mock paginator for permission sets
        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "PermissionSets": [
                    "arn:aws:sso:::permissionSet/test-instance/ps-1",
                    "arn:aws:sso:::permissionSet/test-instance/ps-2",
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_center_client.get_paginator.return_value = mock_paginator

        # Mock permission set details
        def describe_permission_set_side_effect(**kwargs):
            ps_arn = kwargs["PermissionSetArn"]
            if "ps-1" in ps_arn:
                return {
                    "PermissionSet": {
                        "Name": "AdminAccess",
                        "Description": "Admin access",
                        "SessionDuration": "PT8H",
                    }
                }
            elif "ps-2" in ps_arn:
                return {
                    "PermissionSet": {"Name": "ReadOnlyAccess", "Description": "Read-only access"}
                }

        mock_identity_center_client.describe_permission_set.side_effect = (
            describe_permission_set_side_effect
        )

        # Mock other permission set methods
        mock_identity_center_client.get_inline_policy_for_permission_set.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetInlinePolicyForPermissionSet",
        )

        mock_managed_paginator = Mock()
        mock_managed_paginator.paginate.return_value = [{"AttachedManagedPolicies": []}]

        mock_customer_paginator = Mock()
        mock_customer_paginator.paginate.return_value = [{"CustomerManagedPolicyReferences": []}]

        def get_paginator_side_effect(operation_name):
            if operation_name == "list_permission_sets":
                return mock_paginator
            elif operation_name == "list_managed_policies_in_permission_set":
                return mock_managed_paginator
            elif operation_name == "list_customer_managed_policy_references_in_permission_set":
                return mock_customer_paginator

        mock_identity_center_client.get_paginator.side_effect = get_paginator_side_effect

        mock_identity_center_client.get_permissions_boundary_for_permission_set.side_effect = (
            ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
                "GetPermissionsBoundaryForPermissionSet",
            )
        )

        permission_sets = await collector.collect_permission_sets(backup_options)

        assert len(permission_sets) == 2
        assert permission_sets[0].name in ["AdminAccess", "ReadOnlyAccess"]
        assert permission_sets[1].name in ["AdminAccess", "ReadOnlyAccess"]

    @pytest.mark.asyncio
    async def test_collect_permission_sets_sequential(self, collector, mock_identity_center_client):
        """Test sequential permission set collection."""
        backup_options = BackupOptions(parallel_collection=False)

        # Mock paginator for permission sets
        mock_paginator = Mock()
        mock_page_iterator = [
            {"PermissionSets": ["arn:aws:sso:::permissionSet/test-instance/ps-1"]}
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_center_client.get_paginator.return_value = mock_paginator

        # Mock permission set details
        mock_identity_center_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "AdminAccess", "Description": "Admin access"}
        }

        # Mock other methods
        mock_identity_center_client.get_inline_policy_for_permission_set.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetInlinePolicyForPermissionSet",
        )

        mock_managed_paginator = Mock()
        mock_managed_paginator.paginate.return_value = [{"AttachedManagedPolicies": []}]

        mock_customer_paginator = Mock()
        mock_customer_paginator.paginate.return_value = [{"CustomerManagedPolicyReferences": []}]

        def get_paginator_side_effect(operation_name):
            if operation_name == "list_permission_sets":
                return mock_paginator
            elif operation_name == "list_managed_policies_in_permission_set":
                return mock_managed_paginator
            elif operation_name == "list_customer_managed_policy_references_in_permission_set":
                return mock_customer_paginator

        mock_identity_center_client.get_paginator.side_effect = get_paginator_side_effect

        mock_identity_center_client.get_permissions_boundary_for_permission_set.side_effect = (
            ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
                "GetPermissionsBoundaryForPermissionSet",
            )
        )

        permission_sets = await collector.collect_permission_sets(backup_options)

        assert len(permission_sets) == 1
        assert permission_sets[0].name == "AdminAccess"

    @pytest.mark.asyncio
    async def test_collect_assignments_success(
        self, collector, mock_identity_center_client, mock_organizations_client, backup_options
    ):
        """Test successful assignment collection."""
        # Mock organization accounts
        with patch.object(collector, "_get_organization_accounts") as mock_get_accounts:
            mock_get_accounts.return_value = ["123456789012", "123456789013"]

            with patch.object(collector, "_get_permission_set_arns") as mock_get_ps_arns:
                mock_get_ps_arns.return_value = ["arn:aws:sso:::permissionSet/test-instance/ps-1"]

                # Mock the accounts where permission set is provisioned
                mock_identity_center_client.list_accounts_for_provisioned_permission_set.return_value = {
                    "AccountIds": ["123456789012", "123456789013"]
                }

                # Mock assignment collection
                mock_paginator = Mock()
                mock_page_iterator = [
                    {
                        "AccountAssignments": [
                            {"PrincipalType": "USER", "PrincipalId": "user-1"},
                            {"PrincipalType": "GROUP", "PrincipalId": "group-1"},
                        ]
                    }
                ]

                mock_paginator.paginate.return_value = mock_page_iterator
                mock_identity_center_client.get_paginator.return_value = mock_paginator

                assignments = await collector.collect_assignments(backup_options)

                # Should have assignments for 2 accounts * 1 permission set * 2 principals = 4 assignments
                assert len(assignments) == 4
                assert all(isinstance(a, AssignmentData) for a in assignments)
                assert assignments[0].account_id in ["123456789012", "123456789013"]
                assert (
                    assignments[0].permission_set_arn
                    == "arn:aws:sso:::permissionSet/test-instance/ps-1"
                )

    @pytest.mark.asyncio
    async def test_collect_assignments_no_assignments(
        self, collector, mock_identity_center_client, backup_options
    ):
        """Test assignment collection when no assignments exist."""
        with patch.object(collector, "_get_organization_accounts") as mock_get_accounts:
            mock_get_accounts.return_value = ["123456789012"]

            with patch.object(collector, "_get_permission_set_arns") as mock_get_ps_arns:
                mock_get_ps_arns.return_value = ["arn:aws:sso:::permissionSet/test-instance/ps-1"]

                # Mock the accounts where permission set is provisioned
                mock_identity_center_client.list_accounts_for_provisioned_permission_set.return_value = {
                    "AccountIds": ["123456789012"]
                }

                # Mock no assignments
                mock_paginator = Mock()
                mock_page_iterator = [{"AccountAssignments": []}]

                mock_paginator.paginate.return_value = mock_page_iterator
                mock_identity_center_client.get_paginator.return_value = mock_paginator

                assignments = await collector.collect_assignments(backup_options)

                assert len(assignments) == 0

    @pytest.mark.asyncio
    async def test_collect_incremental_parallel(self, collector, backup_options):
        """Test incremental collection with parallel processing."""
        since = datetime.now() - timedelta(days=1)

        with patch.object(collector, "collect_users") as mock_collect_users:
            mock_collect_users.return_value = [
                UserData(user_id="user-1", user_name="john.doe", active=True)
            ]

            with patch.object(collector, "collect_groups") as mock_collect_groups:
                mock_collect_groups.return_value = [
                    GroupData(group_id="group-1", display_name="Admins", members=["user-1"])
                ]

                with patch.object(collector, "collect_permission_sets") as mock_collect_ps:
                    mock_collect_ps.return_value = [
                        PermissionSetData(
                            permission_set_arn="arn:aws:sso:::permissionSet/test-instance/ps-1",
                            name="AdminAccess",
                        )
                    ]

                    with patch.object(collector, "collect_assignments") as mock_collect_assignments:
                        mock_collect_assignments.return_value = [
                            AssignmentData(
                                account_id="123456789012",
                                permission_set_arn="arn:aws:sso:::permissionSet/test-instance/ps-1",
                                principal_type="USER",
                                principal_id="user-1",
                            )
                        ]

                        backup_data = await collector.collect_incremental(since, backup_options)

                        assert len(backup_data.users) == 1
                        assert len(backup_data.groups) == 1
                        assert len(backup_data.permission_sets) == 1
                        assert len(backup_data.assignments) == 1
                        assert backup_data.metadata.backup_type == BackupType.INCREMENTAL

                        # Verify relationships were built
                        assert "user-1" in backup_data.relationships.user_groups
                        assert backup_data.relationships.user_groups["user-1"] == ["group-1"]

    @pytest.mark.asyncio
    async def test_collect_incremental_sequential(self, collector):
        """Test incremental collection with sequential processing."""
        since = datetime.now() - timedelta(days=1)
        backup_options = BackupOptions(
            backup_type=BackupType.INCREMENTAL,
            parallel_collection=False,
            resource_types=[ResourceType.USERS],
        )

        with patch.object(collector, "collect_users") as mock_collect_users:
            mock_collect_users.return_value = [
                UserData(user_id="user-1", user_name="john.doe", active=True)
            ]

            backup_data = await collector.collect_incremental(since, backup_options)

            assert len(backup_data.users) == 1
            assert len(backup_data.groups) == 0  # Not requested
            assert len(backup_data.permission_sets) == 0  # Not requested
            assert len(backup_data.assignments) == 0  # Not requested

    def test_get_collection_stats(self, collector):
        """Test getting collection statistics."""
        # Set some test stats
        collector._collection_stats["users"]["count"] = 100
        collector._collection_stats["users"]["duration"] = 5.5

        stats = collector.get_collection_stats()

        assert stats["users"]["count"] == 100
        assert stats["users"]["duration"] == 5.5

        # Verify it's a copy
        stats["users"]["count"] = 200
        assert collector._collection_stats["users"]["count"] == 100

    @pytest.mark.asyncio
    async def test_get_organization_accounts_success(self, collector, mock_organizations_client):
        """Test successful organization account retrieval."""
        # Mock organization hierarchy
        mock_org_node = Mock()
        mock_org_node.is_account.return_value = True
        mock_org_node.id = "123456789012"
        mock_org_node.children = []

        mock_root = Mock()
        mock_root.is_account.return_value = False
        mock_root.children = [mock_org_node]

        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy:
            mock_build_hierarchy.return_value = [mock_root]

            accounts = await collector._get_organization_accounts()

            assert accounts == ["123456789012"]

    @pytest.mark.asyncio
    async def test_get_organization_accounts_fallback(self, collector, mock_organizations_client):
        """Test organization account retrieval with fallback method."""
        # Mock hierarchy building failure
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy:
            mock_build_hierarchy.side_effect = Exception("Hierarchy build failed")

            # Mock fallback paginator
            mock_paginator = Mock()
            mock_page_iterator = [{"Accounts": [{"Id": "123456789012"}, {"Id": "123456789013"}]}]

            mock_paginator.paginate.return_value = mock_page_iterator
            mock_organizations_client.get_paginator.return_value = mock_paginator

            accounts = await collector._get_organization_accounts()

            assert accounts == ["123456789012", "123456789013"]

    @pytest.mark.asyncio
    async def test_get_permission_set_arns_success(self, collector, mock_identity_center_client):
        """Test successful permission set ARN retrieval."""
        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "PermissionSets": [
                    "arn:aws:sso:::permissionSet/test-instance/ps-1",
                    "arn:aws:sso:::permissionSet/test-instance/ps-2",
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_center_client.get_paginator.return_value = mock_paginator

        ps_arns = await collector._get_permission_set_arns()

        assert len(ps_arns) == 2
        assert "arn:aws:sso:::permissionSet/test-instance/ps-1" in ps_arns
        assert "arn:aws:sso:::permissionSet/test-instance/ps-2" in ps_arns

    def test_get_permission_set_details_success(self, collector, mock_identity_center_client):
        """Test successful permission set details retrieval."""
        ps_arn = "arn:aws:sso:::permissionSet/test-instance/ps-1"

        # Mock describe permission set
        mock_identity_center_client.describe_permission_set.return_value = {
            "PermissionSet": {
                "Name": "AdminAccess",
                "Description": "Admin access",
                "SessionDuration": "PT8H",
                "RelayState": "https://console.aws.amazon.com",
            }
        }

        # Mock inline policy
        mock_identity_center_client.get_inline_policy_for_permission_set.return_value = {
            "InlinePolicy": '{"Version": "2012-10-17", "Statement": []}'
        }

        # Mock managed policies
        mock_managed_paginator = Mock()
        mock_managed_paginator.paginate.return_value = [
            {"AttachedManagedPolicies": [{"Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}]}
        ]

        # Mock customer managed policies
        mock_customer_paginator = Mock()
        mock_customer_paginator.paginate.return_value = [
            {"CustomerManagedPolicyReferences": [{"Name": "CustomPolicy", "Path": "/"}]}
        ]

        def get_paginator_side_effect(operation_name):
            if operation_name == "list_managed_policies_in_permission_set":
                return mock_managed_paginator
            elif operation_name == "list_customer_managed_policy_references_in_permission_set":
                return mock_customer_paginator

        mock_identity_center_client.get_paginator.side_effect = get_paginator_side_effect

        # Mock permissions boundary
        mock_identity_center_client.get_permissions_boundary_for_permission_set.return_value = {
            "PermissionsBoundary": {"ManagedPolicyArn": "arn:aws:iam::aws:policy/PowerUserAccess"}
        }

        ps_data = collector._get_permission_set_details(ps_arn)

        assert ps_data is not None
        assert ps_data.permission_set_arn == ps_arn
        assert ps_data.name == "AdminAccess"
        assert ps_data.description == "Admin access"
        assert ps_data.session_duration == "PT8H"
        assert ps_data.relay_state == "https://console.aws.amazon.com"
        assert ps_data.inline_policy == '{"Version": "2012-10-17", "Statement": []}'
        assert ps_data.managed_policies == ["arn:aws:iam::aws:policy/AdministratorAccess"]
        assert ps_data.customer_managed_policies == [{"Name": "CustomPolicy", "Path": "/"}]
        assert ps_data.permissions_boundary == {
            "ManagedPolicyArn": "arn:aws:iam::aws:policy/PowerUserAccess"
        }

    def test_get_permission_set_details_failure(self, collector, mock_identity_center_client):
        """Test permission set details retrieval failure."""
        ps_arn = "arn:aws:sso:::permissionSet/test-instance/ps-1"

        mock_identity_center_client.describe_permission_set.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "DescribePermissionSet",
        )

        ps_data = collector._get_permission_set_details(ps_arn)

        assert ps_data is None

    def test_get_assignments_for_account_and_ps_success(
        self, collector, mock_identity_center_client
    ):
        """Test successful assignment retrieval for account and permission set."""
        account_id = "123456789012"
        ps_arn = "arn:aws:sso:::permissionSet/test-instance/ps-1"

        mock_paginator = Mock()
        mock_page_iterator = [
            {
                "AccountAssignments": [
                    {"PrincipalType": "USER", "PrincipalId": "user-1"},
                    {"PrincipalType": "GROUP", "PrincipalId": "group-1"},
                ]
            }
        ]

        mock_paginator.paginate.return_value = mock_page_iterator
        mock_identity_center_client.get_paginator.return_value = mock_paginator

        assignments = collector._get_assignments_for_account_and_ps(account_id, ps_arn)

        assert len(assignments) == 2
        assert assignments[0].account_id == account_id
        assert assignments[0].permission_set_arn == ps_arn
        assert assignments[0].principal_type == "USER"
        assert assignments[0].principal_id == "user-1"
        assert assignments[1].principal_type == "GROUP"
        assert assignments[1].principal_id == "group-1"

    def test_get_assignments_for_account_and_ps_no_assignments(
        self, collector, mock_identity_center_client
    ):
        """Test assignment retrieval when no assignments exist."""
        account_id = "123456789012"
        ps_arn = "arn:aws:sso:::permissionSet/test-instance/ps-1"

        mock_identity_center_client.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "ListAccountAssignments",
        )

        assignments = collector._get_assignments_for_account_and_ps(account_id, ps_arn)

        assert len(assignments) == 0

    def test_build_relationships(self, collector):
        """Test relationship building between resources."""
        users = [
            UserData(user_id="user-1", user_name="john.doe", active=True),
            UserData(user_id="user-2", user_name="jane.smith", active=True),
        ]

        groups = [
            GroupData(group_id="group-1", display_name="Admins", members=["user-1"]),
            GroupData(group_id="group-2", display_name="Users", members=["user-1", "user-2"]),
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/test-instance/ps-1",
                name="AdminAccess",
            )
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/test-instance/ps-1",
                principal_type="USER",
                principal_id="user-1",
            ),
            AssignmentData(
                account_id="123456789013",
                permission_set_arn="arn:aws:sso:::permissionSet/test-instance/ps-1",
                principal_type="GROUP",
                principal_id="group-1",
            ),
        ]

        relationships = collector._build_relationships(users, groups, permission_sets, assignments)

        # Check user-group relationships
        assert "user-1" in relationships.user_groups
        assert "group-1" in relationships.user_groups["user-1"]
        assert "group-2" in relationships.user_groups["user-1"]

        assert "user-2" in relationships.user_groups
        assert relationships.user_groups["user-2"] == ["group-2"]

        # Check group-member relationships
        assert relationships.group_members["group-1"] == ["user-1"]
        assert relationships.group_members["group-2"] == ["user-1", "user-2"]

        # Check permission set assignment relationships
        ps_arn = "arn:aws:sso:::permissionSet/test-instance/ps-1"
        assert ps_arn in relationships.permission_set_assignments
        expected_assignments = ["123456789012:USER:user-1", "123456789013:GROUP:group-1"]
        assert relationships.permission_set_assignments[ps_arn] == expected_assignments
