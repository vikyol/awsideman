"""
Unit tests for backup diff comparators.

This module tests the resource comparison logic for detecting changes between
backup states for users, groups, permission sets, and assignments.
"""

from src.awsideman.backup_restore.comparators import (
    AssignmentComparator,
    GroupComparator,
    PermissionSetComparator,
    ResourceComparator,
    UserComparator,
)
from src.awsideman.backup_restore.diff_models import ChangeType, ResourceDiff
from src.awsideman.backup_restore.models import (
    AssignmentData,
    GroupData,
    PermissionSetData,
    UserData,
)


class TestResourceComparator:
    """Test the abstract ResourceComparator base class."""

    def test_create_resource_maps(self):
        """Test creating resource maps from lists."""

        # Create a concrete implementation for testing
        class TestComparator(ResourceComparator):
            def compare(self, source_resources, target_resources):
                return ResourceDiff(resource_type="test")

        comparator = TestComparator()

        # Test with UserData objects
        users = [
            UserData(user_id="user1", user_name="testuser1"),
            UserData(user_id="user2", user_name="testuser2"),
        ]

        user_map = comparator._create_resource_maps(users, "user_id")

        assert len(user_map) == 2
        assert "user1" in user_map
        assert "user2" in user_map
        assert user_map["user1"].user_name == "testuser1"
        assert user_map["user2"].user_name == "testuser2"

    def test_detect_attribute_changes_no_changes(self):
        """Test attribute change detection when there are no changes."""

        class TestComparator(ResourceComparator):
            def compare(self, source_resources, target_resources):
                return ResourceDiff(resource_type="test")

        comparator = TestComparator()

        user1 = UserData(user_id="user1", user_name="testuser", email="test@example.com")
        user2 = UserData(user_id="user1", user_name="testuser", email="test@example.com")

        changes = comparator._detect_attribute_changes(user1, user2)
        assert len(changes) == 0

    def test_detect_attribute_changes_with_changes(self):
        """Test attribute change detection when there are changes."""

        class TestComparator(ResourceComparator):
            def compare(self, source_resources, target_resources):
                return ResourceDiff(resource_type="test")

        comparator = TestComparator()

        user1 = UserData(
            user_id="user1", user_name="testuser", email="old@example.com", active=True
        )
        user2 = UserData(
            user_id="user1", user_name="testuser", email="new@example.com", active=False
        )

        changes = comparator._detect_attribute_changes(user1, user2)

        assert len(changes) == 2

        # Find email change
        email_change = next((c for c in changes if c.attribute_name == "email"), None)
        assert email_change is not None
        assert email_change.before_value == "old@example.com"
        assert email_change.after_value == "new@example.com"

        # Find active change
        active_change = next((c for c in changes if c.attribute_name == "active"), None)
        assert active_change is not None
        assert active_change.before_value is True
        assert active_change.after_value is False

    def test_detect_attribute_changes_with_lists(self):
        """Test attribute change detection with list attributes."""

        class TestComparator(ResourceComparator):
            def compare(self, source_resources, target_resources):
                return ResourceDiff(resource_type="test")

        comparator = TestComparator()

        group1 = GroupData(group_id="group1", display_name="testgroup", members=["user1", "user2"])
        group2 = GroupData(group_id="group1", display_name="testgroup", members=["user1", "user3"])

        changes = comparator._detect_attribute_changes(group1, group2)

        assert len(changes) == 1
        assert changes[0].attribute_name == "members"
        assert changes[0].before_value == ["user1", "user2"]
        assert changes[0].after_value == ["user1", "user3"]


class TestUserComparator:
    """Test the UserComparator class."""

    def test_compare_no_changes(self):
        """Test user comparison with no changes."""
        comparator = UserComparator()

        users = [
            UserData(user_id="user1", user_name="testuser1", email="test1@example.com"),
            UserData(user_id="user2", user_name="testuser2", email="test2@example.com"),
        ]

        result = comparator.compare(users, users)

        assert result.resource_type == "users"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0
        assert result.total_changes == 0

    def test_compare_created_users(self):
        """Test user comparison with created users."""
        comparator = UserComparator()

        source_users = [
            UserData(user_id="user1", user_name="testuser1", email="test1@example.com"),
        ]

        target_users = [
            UserData(user_id="user1", user_name="testuser1", email="test1@example.com"),
            UserData(user_id="user2", user_name="testuser2", email="test2@example.com"),
        ]

        result = comparator.compare(source_users, target_users)

        assert result.resource_type == "users"
        assert len(result.created) == 1
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        created_user = result.created[0]
        assert created_user.change_type == ChangeType.CREATED
        assert created_user.resource_id == "user2"
        assert created_user.resource_name == "testuser2"
        assert created_user.before_value is None
        assert created_user.after_value is not None

    def test_compare_deleted_users(self):
        """Test user comparison with deleted users."""
        comparator = UserComparator()

        source_users = [
            UserData(user_id="user1", user_name="testuser1", email="test1@example.com"),
            UserData(user_id="user2", user_name="testuser2", email="test2@example.com"),
        ]

        target_users = [
            UserData(user_id="user1", user_name="testuser1", email="test1@example.com"),
        ]

        result = comparator.compare(source_users, target_users)

        assert result.resource_type == "users"
        assert len(result.created) == 0
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        deleted_user = result.deleted[0]
        assert deleted_user.change_type == ChangeType.DELETED
        assert deleted_user.resource_id == "user2"
        assert deleted_user.resource_name == "testuser2"
        assert deleted_user.before_value is not None
        assert deleted_user.after_value is None

    def test_compare_modified_users(self):
        """Test user comparison with modified users."""
        comparator = UserComparator()

        source_users = [
            UserData(user_id="user1", user_name="testuser1", email="old@example.com", active=True),
        ]

        target_users = [
            UserData(user_id="user1", user_name="testuser1", email="new@example.com", active=False),
        ]

        result = comparator.compare(source_users, target_users)

        assert result.resource_type == "users"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 1

        modified_user = result.modified[0]
        assert modified_user.change_type == ChangeType.MODIFIED
        assert modified_user.resource_id == "user1"
        assert modified_user.resource_name == "testuser1"
        assert modified_user.before_value is not None
        assert modified_user.after_value is not None
        assert len(modified_user.attribute_changes) == 2


class TestGroupComparator:
    """Test the GroupComparator class."""

    def test_compare_no_changes(self):
        """Test group comparison with no changes."""
        comparator = GroupComparator()

        groups = [
            GroupData(group_id="group1", display_name="testgroup1", members=["user1"]),
            GroupData(group_id="group2", display_name="testgroup2", members=["user2"]),
        ]

        result = comparator.compare(groups, groups)

        assert result.resource_type == "groups"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0
        assert result.total_changes == 0

    def test_compare_created_groups(self):
        """Test group comparison with created groups."""
        comparator = GroupComparator()

        source_groups = [
            GroupData(group_id="group1", display_name="testgroup1", members=["user1"]),
        ]

        target_groups = [
            GroupData(group_id="group1", display_name="testgroup1", members=["user1"]),
            GroupData(group_id="group2", display_name="testgroup2", members=["user2"]),
        ]

        result = comparator.compare(source_groups, target_groups)

        assert result.resource_type == "groups"
        assert len(result.created) == 1
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        created_group = result.created[0]
        assert created_group.change_type == ChangeType.CREATED
        assert created_group.resource_id == "group2"
        assert created_group.resource_name == "testgroup2"

    def test_compare_modified_groups_membership(self):
        """Test group comparison with modified group membership."""
        comparator = GroupComparator()

        source_groups = [
            GroupData(group_id="group1", display_name="testgroup1", members=["user1", "user2"]),
        ]

        target_groups = [
            GroupData(group_id="group1", display_name="testgroup1", members=["user1", "user3"]),
        ]

        result = comparator.compare(source_groups, target_groups)

        assert result.resource_type == "groups"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 1

        modified_group = result.modified[0]
        assert modified_group.change_type == ChangeType.MODIFIED
        assert modified_group.resource_id == "group1"
        assert len(modified_group.attribute_changes) == 1
        assert modified_group.attribute_changes[0].attribute_name == "members"


class TestPermissionSetComparator:
    """Test the PermissionSetComparator class."""

    def test_compare_no_changes(self):
        """Test permission set comparison with no changes."""
        comparator = PermissionSetComparator()

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Test permission set 1",
            ),
        ]

        result = comparator.compare(permission_sets, permission_sets)

        assert result.resource_type == "permission_sets"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0
        assert result.total_changes == 0

    def test_compare_created_permission_sets(self):
        """Test permission set comparison with created permission sets."""
        comparator = PermissionSetComparator()

        source_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Test permission set 1",
            ),
        ]

        target_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Test permission set 1",
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                name="TestPS2",
                description="Test permission set 2",
            ),
        ]

        result = comparator.compare(source_ps, target_ps)

        assert result.resource_type == "permission_sets"
        assert len(result.created) == 1
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        created_ps = result.created[0]
        assert created_ps.change_type == ChangeType.CREATED
        assert created_ps.resource_id == "arn:aws:sso:::permissionSet/ins-123/ps-456"
        assert created_ps.resource_name == "TestPS2"

    def test_compare_deleted_permission_sets(self):
        """Test permission set comparison with deleted permission sets."""
        comparator = PermissionSetComparator()

        source_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Test permission set 1",
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                name="TestPS2",
                description="Test permission set 2",
            ),
        ]

        target_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Test permission set 1",
            ),
        ]

        result = comparator.compare(source_ps, target_ps)

        assert result.resource_type == "permission_sets"
        assert len(result.created) == 0
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        deleted_ps = result.deleted[0]
        assert deleted_ps.change_type == ChangeType.DELETED
        assert deleted_ps.resource_id == "arn:aws:sso:::permissionSet/ins-123/ps-456"
        assert deleted_ps.resource_name == "TestPS2"

    def test_compare_modified_permission_sets(self):
        """Test permission set comparison with modified permission sets."""
        comparator = PermissionSetComparator()

        source_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="Old description",
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            ),
        ]

        target_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS1",
                description="New description",
                managed_policies=["arn:aws:iam::aws:policy/PowerUserAccess"],
            ),
        ]

        result = comparator.compare(source_ps, target_ps)

        assert result.resource_type == "permission_sets"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 1

        modified_ps = result.modified[0]
        assert modified_ps.change_type == ChangeType.MODIFIED
        assert modified_ps.resource_id == "arn:aws:sso:::permissionSet/ins-123/ps-123"
        assert len(modified_ps.attribute_changes) == 2  # description and managed_policies

    def test_compare_complex_policy_modifications(self):
        """Test permission set comparison with complex policy modifications."""
        comparator = PermissionSetComparator()

        source_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="ComplexPS",
                description="Complex permission set",
                session_duration="PT8H",
                inline_policy='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}]}',
                managed_policies=[
                    "arn:aws:iam::aws:policy/ReadOnlyAccess",
                    "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
                ],
                customer_managed_policies=[
                    {"Name": "CustomPolicy1", "Path": "/"},
                    {"Name": "CustomPolicy2", "Path": "/team/"},
                ],
                permissions_boundary={
                    "CustomerManagedPolicyReference": {"Name": "BoundaryPolicy", "Path": "/"}
                },
            ),
        ]

        target_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="ComplexPS",
                description="Complex permission set",
                session_duration="PT12H",  # Changed
                inline_policy='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": "*"}]}',  # Changed
                managed_policies=[
                    "arn:aws:iam::aws:policy/PowerUserAccess",  # Changed
                    "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
                ],
                customer_managed_policies=[
                    {"Name": "CustomPolicy1", "Path": "/"},
                    {"Name": "CustomPolicy3", "Path": "/team/"},  # Changed
                ],
                permissions_boundary={
                    "CustomerManagedPolicyReference": {
                        "Name": "NewBoundaryPolicy",  # Changed
                        "Path": "/",
                    }
                },
            ),
        ]

        result = comparator.compare(source_ps, target_ps)

        assert result.resource_type == "permission_sets"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 1

        modified_ps = result.modified[0]
        assert modified_ps.change_type == ChangeType.MODIFIED
        assert modified_ps.resource_id == "arn:aws:sso:::permissionSet/ins-123/ps-123"

        # Should detect changes in session_duration, inline_policy, managed_policies,
        # customer_managed_policies, and permissions_boundary
        assert len(modified_ps.attribute_changes) == 5

        # Verify specific attribute changes
        attribute_names = {change.attribute_name for change in modified_ps.attribute_changes}
        expected_changes = {
            "session_duration",
            "inline_policy",
            "managed_policies",
            "customer_managed_policies",
            "permissions_boundary",
        }
        assert attribute_names == expected_changes

    def test_compare_policy_list_order_independence(self):
        """Test that managed policy list comparison is order-independent."""
        comparator = PermissionSetComparator()

        source_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS",
                managed_policies=[
                    "arn:aws:iam::aws:policy/ReadOnlyAccess",
                    "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
                ],
            ),
        ]

        target_ps = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                name="TestPS",
                managed_policies=[
                    "arn:aws:iam::aws:policy/IAMReadOnlyAccess",  # Different order
                    "arn:aws:iam::aws:policy/ReadOnlyAccess",
                ],
            ),
        ]

        result = comparator.compare(source_ps, target_ps)

        # Should not detect changes since the policies are the same, just in different order
        assert result.resource_type == "permission_sets"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0


class TestAssignmentComparator:
    """Test the AssignmentComparator class."""

    def test_compare_no_changes(self):
        """Test assignment comparison with no changes."""
        comparator = AssignmentComparator()

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
        ]

        result = comparator.compare(assignments, assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0
        assert result.total_changes == 0

    def test_compare_created_assignments(self):
        """Test assignment comparison with created assignments."""
        comparator = AssignmentComparator()

        source_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
        ]

        target_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                principal_type="GROUP",
                principal_id="group1",
            ),
        ]

        result = comparator.compare(source_assignments, target_assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 1
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        created_assignment = result.created[0]
        assert created_assignment.change_type == ChangeType.CREATED
        assert created_assignment.resource_name == "GROUP:group1"

    def test_compare_deleted_assignments(self):
        """Test assignment comparison with deleted assignments."""
        comparator = AssignmentComparator()

        source_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                principal_type="GROUP",
                principal_id="group1",
            ),
        ]

        target_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
        ]

        result = comparator.compare(source_assignments, target_assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 0
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        deleted_assignment = result.deleted[0]
        assert deleted_assignment.change_type == ChangeType.DELETED
        assert deleted_assignment.resource_name == "GROUP:group1"

    def test_compare_complex_assignment_changes(self):
        """Test assignment comparison with complex scenarios involving multiple accounts and principals."""
        comparator = AssignmentComparator()

        source_assignments = [
            # User assignment to account A
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            # Group assignment to account A
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                principal_type="GROUP",
                principal_id="group1",
            ),
            # User assignment to account B
            AssignmentData(
                account_id="222222222222",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
        ]

        target_assignments = [
            # Same user assignment to account A (no change)
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            # Group assignment moved to different permission set (delete + create)
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-789",
                principal_type="GROUP",
                principal_id="group1",
            ),
            # User assignment moved to different account (delete + create)
            AssignmentData(
                account_id="333333333333",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            # New assignment for different user
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user2",
            ),
        ]

        result = comparator.compare(source_assignments, target_assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 3  # New group PS, new account for user1, new user2
        assert (
            len(result.deleted) == 2
        )  # Old group PS, old account for user1 (user1 from account B is removed)
        assert len(result.modified) == 0  # Assignments don't have modifiable attributes

        # Verify created assignments
        created_keys = {change.resource_id for change in result.created}
        expected_created = {
            "111111111111:arn:aws:sso:::permissionSet/ins-123/ps-789:GROUP:group1",
            "333333333333:arn:aws:sso:::permissionSet/ins-123/ps-123:USER:user1",
            "111111111111:arn:aws:sso:::permissionSet/ins-123/ps-123:USER:user2",
        }
        assert created_keys == expected_created

        # Verify deleted assignments
        deleted_keys = {change.resource_id for change in result.deleted}
        expected_deleted = {
            "111111111111:arn:aws:sso:::permissionSet/ins-123/ps-456:GROUP:group1",
            "222222222222:arn:aws:sso:::permissionSet/ins-123/ps-123:USER:user1",
        }
        assert deleted_keys == expected_deleted

    def test_compare_principal_type_changes(self):
        """Test assignment comparison when principal type changes for same principal ID."""
        comparator = AssignmentComparator()

        # This scenario could happen if a user ID is reused as a group ID (unlikely but possible)
        source_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="principal1",
            ),
        ]

        target_assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="GROUP",
                principal_id="principal1",
            ),
        ]

        result = comparator.compare(source_assignments, target_assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 1
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        # Should be treated as delete USER assignment and create GROUP assignment
        created_assignment = result.created[0]
        deleted_assignment = result.deleted[0]

        assert created_assignment.resource_name == "GROUP:principal1"
        assert deleted_assignment.resource_name == "USER:principal1"

    def test_compare_cross_account_assignment_patterns(self):
        """Test assignment comparison with cross-account assignment patterns."""
        comparator = AssignmentComparator()

        source_assignments = [
            # Same permission set assigned to multiple accounts
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            AssignmentData(
                account_id="222222222222",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            AssignmentData(
                account_id="333333333333",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
        ]

        target_assignments = [
            # Admin user removed from account 222222222222, added to account 444444444444
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            AssignmentData(
                account_id="333333333333",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            AssignmentData(
                account_id="444444444444",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
        ]

        result = comparator.compare(source_assignments, target_assignments)

        assert result.resource_type == "assignments"
        assert len(result.created) == 1
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        created_assignment = result.created[0]
        deleted_assignment = result.deleted[0]

        assert "444444444444" in created_assignment.resource_id
        assert "222222222222" in deleted_assignment.resource_id

    def test_create_assignment_maps(self):
        """Test creating assignment maps with composite keys."""
        comparator = AssignmentComparator()

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
                principal_type="GROUP",
                principal_id="group1",
            ),
        ]

        assignment_map = comparator._create_assignment_maps(assignments)

        assert len(assignment_map) == 2

        expected_key1 = "123456789012:arn:aws:sso:::permissionSet/ins-123/ps-123:USER:user1"
        expected_key2 = "123456789012:arn:aws:sso:::permissionSet/ins-123/ps-456:GROUP:group1"

        assert expected_key1 in assignment_map
        assert expected_key2 in assignment_map
        assert assignment_map[expected_key1].principal_id == "user1"
        assert assignment_map[expected_key2].principal_id == "group1"

    def test_create_assignment_maps_with_duplicate_keys(self):
        """Test assignment map creation handles potential duplicate keys gracefully."""
        comparator = AssignmentComparator()

        # This shouldn't happen in real data, but test the behavior
        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                principal_type="USER",
                principal_id="user1",
            ),
        ]

        assignment_map = comparator._create_assignment_maps(assignments)

        # Should only have one entry (last one wins)
        assert len(assignment_map) == 1
        expected_key = "123456789012:arn:aws:sso:::permissionSet/ins-123/ps-123:USER:user1"
        assert expected_key in assignment_map


class TestIntegrationScenarios:
    """Test complex integration scenarios with multiple resource types."""

    def test_mixed_changes_scenario(self):
        """Test a realistic scenario with mixed changes across resource types."""
        user_comparator = UserComparator()
        group_comparator = GroupComparator()

        # Source state
        source_users = [
            UserData(user_id="user1", user_name="alice", email="alice@old.com", active=True),
            UserData(user_id="user2", user_name="bob", email="bob@example.com", active=True),
        ]

        source_groups = [
            GroupData(group_id="group1", display_name="Developers", members=["user1", "user2"]),
        ]

        # Target state
        target_users = [
            UserData(
                user_id="user1", user_name="alice", email="alice@new.com", active=True
            ),  # Modified
            UserData(
                user_id="user3", user_name="charlie", email="charlie@example.com", active=True
            ),  # Created
            # user2 deleted
        ]

        target_groups = [
            GroupData(
                group_id="group1", display_name="Developers", members=["user1", "user3"]
            ),  # Modified
            GroupData(group_id="group2", display_name="Admins", members=["user1"]),  # Created
        ]

        user_diff = user_comparator.compare(source_users, target_users)
        group_diff = group_comparator.compare(source_groups, target_groups)

        # Verify user changes
        assert len(user_diff.created) == 1
        assert len(user_diff.deleted) == 1
        assert len(user_diff.modified) == 1
        assert user_diff.created[0].resource_name == "charlie"
        assert user_diff.deleted[0].resource_name == "bob"
        assert user_diff.modified[0].resource_name == "alice"

        # Verify group changes
        assert len(group_diff.created) == 1
        assert len(group_diff.deleted) == 0
        assert len(group_diff.modified) == 1
        assert group_diff.created[0].resource_name == "Admins"
        assert group_diff.modified[0].resource_name == "Developers"

    def test_comprehensive_permission_and_assignment_scenario(self):
        """Test a comprehensive scenario with permission sets and assignments changes."""
        ps_comparator = PermissionSetComparator()
        assignment_comparator = AssignmentComparator()

        # Source state - Initial setup
        source_permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-dev",
                name="DeveloperAccess",
                description="Developer access permissions",
                session_duration="PT8H",
                managed_policies=["arn:aws:iam::aws:policy/PowerUserAccess"],
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                name="AdminAccess",
                description="Administrator access permissions",
                session_duration="PT4H",
                managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            ),
        ]

        source_assignments = [
            # Developer access for dev team
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-dev",
                principal_type="GROUP",
                principal_id="dev-team",
            ),
            # Admin access for admin user
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            # Admin access in production account
            AssignmentData(
                account_id="222222222222",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
        ]

        # Target state - After organizational changes
        target_permission_sets = [
            # Developer permission set modified (longer session, additional policy)
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-dev",
                name="DeveloperAccess",
                description="Enhanced developer access permissions",  # Changed
                session_duration="PT12H",  # Changed
                managed_policies=[
                    "arn:aws:iam::aws:policy/PowerUserAccess",
                    "arn:aws:iam::aws:policy/IAMReadOnlyAccess",  # Added
                ],
            ),
            # Admin permission set unchanged
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                name="AdminAccess",
                description="Administrator access permissions",
                session_duration="PT4H",
                managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            ),
            # New read-only permission set created
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-readonly",
                name="ReadOnlyAccess",
                description="Read-only access permissions",
                session_duration="PT24H",
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            ),
        ]

        target_assignments = [
            # Developer access moved to individual users instead of group
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-dev",
                principal_type="USER",
                principal_id="dev-user1",
            ),
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-dev",
                principal_type="USER",
                principal_id="dev-user2",
            ),
            # Admin access unchanged in dev account
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-admin",
                principal_type="USER",
                principal_id="admin-user",
            ),
            # Admin access removed from production, replaced with read-only
            AssignmentData(
                account_id="222222222222",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-readonly",
                principal_type="USER",
                principal_id="admin-user",
            ),
            # New read-only access for auditors
            AssignmentData(
                account_id="111111111111",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-readonly",
                principal_type="GROUP",
                principal_id="auditors",
            ),
            AssignmentData(
                account_id="222222222222",
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-readonly",
                principal_type="GROUP",
                principal_id="auditors",
            ),
        ]

        # Compare permission sets
        ps_diff = ps_comparator.compare(source_permission_sets, target_permission_sets)

        # Verify permission set changes
        assert len(ps_diff.created) == 1  # ReadOnlyAccess created
        assert len(ps_diff.deleted) == 0
        assert len(ps_diff.modified) == 1  # DeveloperAccess modified

        created_ps = ps_diff.created[0]
        assert created_ps.resource_name == "ReadOnlyAccess"

        modified_ps = ps_diff.modified[0]
        assert modified_ps.resource_name == "DeveloperAccess"
        assert (
            len(modified_ps.attribute_changes) == 3
        )  # description, session_duration, managed_policies

        # Compare assignments
        assignment_diff = assignment_comparator.compare(source_assignments, target_assignments)

        # Verify assignment changes
        assert (
            len(assignment_diff.created) == 5
        )  # 2 dev users + 1 readonly for admin + 2 auditor groups
        assert len(assignment_diff.deleted) == 2  # dev group + admin in prod
        assert len(assignment_diff.modified) == 0

        # Verify specific assignment changes
        created_assignment_names = {change.resource_name for change in assignment_diff.created}
        expected_created_names = {
            "USER:dev-user1",
            "USER:dev-user2",
            "USER:admin-user",
            "GROUP:auditors",
        }
        # Note: admin-user and auditors appear in multiple assignments, so we check subset
        assert len(created_assignment_names & expected_created_names) >= 3

        deleted_assignment_keys = {change.resource_id for change in assignment_diff.deleted}
        assert any("dev-team" in key for key in deleted_assignment_keys)
        assert any("222222222222" in key and "ps-admin" in key for key in deleted_assignment_keys)

    def test_edge_case_empty_collections(self):
        """Test comparators handle empty collections gracefully."""
        user_comparator = UserComparator()
        group_comparator = GroupComparator()
        ps_comparator = PermissionSetComparator()
        assignment_comparator = AssignmentComparator()

        # Test empty source
        empty_source = []
        target_data = [
            UserData(user_id="user1", user_name="testuser"),
        ]

        result = user_comparator.compare(empty_source, target_data)
        assert len(result.created) == 1
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        # Test empty target
        result = user_comparator.compare(target_data, empty_source)
        assert len(result.created) == 0
        assert len(result.deleted) == 1
        assert len(result.modified) == 0

        # Test both empty
        result = user_comparator.compare(empty_source, empty_source)
        assert len(result.created) == 0
        assert len(result.deleted) == 0
        assert len(result.modified) == 0

        # Test with all comparators
        for comparator in [group_comparator, ps_comparator, assignment_comparator]:
            result = comparator.compare([], [])
            assert result.total_changes == 0
