"""
Unit tests for Role-Based Access Control (RBAC) functionality.

Tests the RBAC system including user management, role definitions,
permission checking, and access control enforcement.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.awsideman.backup_restore.rbac import (
    AccessControlManager,
    FileBasedAccessControl,
    Permission,
    Role,
    User,
    configure_access_control,
    get_access_control_manager,
    get_role_permissions,
)


class TestPermissionAndRole:
    """Test Permission and Role enums."""

    def test_permission_enum_values(self):
        """Test that permission enum has expected values."""
        assert Permission.CREATE_BACKUP.value == "backup:create"
        assert Permission.RESTORE_BACKUP.value == "restore:execute"
        assert Permission.VIEW_AUDIT_LOGS.value == "audit:view"
        assert Permission.MANAGE_ROLES.value == "admin:roles"

    def test_role_enum_values(self):
        """Test that role enum has expected values."""
        assert Role.BACKUP_USER.value == "backup_user"
        assert Role.BACKUP_OPERATOR.value == "backup_operator"
        assert Role.BACKUP_ADMIN.value == "backup_admin"
        assert Role.BACKUP_VIEWER.value == "backup_viewer"
        assert Role.SECURITY_OFFICER.value == "security_officer"

    def test_get_role_permissions(self):
        """Test getting permissions for different roles."""
        # Test backup user permissions
        user_perms = get_role_permissions(Role.BACKUP_USER)
        assert Permission.CREATE_BACKUP in user_perms
        assert Permission.RESTORE_BACKUP in user_perms
        assert Permission.DELETE_BACKUP not in user_perms
        assert Permission.MANAGE_ROLES not in user_perms

        # Test backup admin permissions (should have all)
        admin_perms = get_role_permissions(Role.BACKUP_ADMIN)
        assert len(admin_perms) == len(Permission)
        assert Permission.MANAGE_ROLES in admin_perms

        # Test backup viewer permissions
        viewer_perms = get_role_permissions(Role.BACKUP_VIEWER)
        assert Permission.VIEW_BACKUP in viewer_perms
        assert Permission.CREATE_BACKUP not in viewer_perms
        assert Permission.DELETE_BACKUP not in viewer_perms

        # Test security officer permissions
        security_perms = get_role_permissions(Role.SECURITY_OFFICER)
        assert Permission.VIEW_AUDIT_LOGS in security_perms
        assert Permission.MANAGE_ENCRYPTION in security_perms
        assert Permission.CREATE_BACKUP not in security_perms


class TestUser:
    """Test User data model."""

    def test_user_creation(self):
        """Test creating a user."""
        user = User(
            user_id="test-user",
            username="testuser",
            roles={Role.BACKUP_USER},
            additional_permissions={Permission.VIEW_AUDIT_LOGS},
        )

        assert user.user_id == "test-user"
        assert user.username == "testuser"
        assert Role.BACKUP_USER in user.roles
        assert Permission.VIEW_AUDIT_LOGS in user.additional_permissions
        assert user.active is True

    def test_user_get_all_permissions(self):
        """Test getting all permissions for a user."""
        user = User(
            user_id="test-user",
            username="testuser",
            roles={Role.BACKUP_USER, Role.BACKUP_VIEWER},
            additional_permissions={Permission.MANAGE_ENCRYPTION},
        )

        all_perms = user.get_all_permissions()

        # Should include permissions from both roles
        assert Permission.CREATE_BACKUP in all_perms  # From BACKUP_USER
        assert Permission.VIEW_BACKUP in all_perms  # From BACKUP_VIEWER

        # Should include additional permissions
        assert Permission.MANAGE_ENCRYPTION in all_perms

        # Should not include permissions not granted
        assert Permission.MANAGE_ROLES not in all_perms

    def test_user_has_permission(self):
        """Test checking if user has specific permission."""
        user = User(
            user_id="test-user",
            username="testuser",
            roles={Role.BACKUP_USER},
            additional_permissions={Permission.VIEW_AUDIT_LOGS},
        )

        # Should have permissions from role
        assert user.has_permission(Permission.CREATE_BACKUP) is True
        assert user.has_permission(Permission.RESTORE_BACKUP) is True

        # Should have additional permissions
        assert user.has_permission(Permission.VIEW_AUDIT_LOGS) is True

        # Should not have permissions not granted
        assert user.has_permission(Permission.MANAGE_ROLES) is False
        assert user.has_permission(Permission.DELETE_BACKUP) is False

    def test_user_serialization(self):
        """Test user serialization to/from dictionary."""
        user = User(
            user_id="test-user",
            username="testuser",
            roles={Role.BACKUP_USER, Role.BACKUP_VIEWER},
            additional_permissions={Permission.VIEW_AUDIT_LOGS},
            active=False,
        )

        # Convert to dict
        user_dict = user.to_dict()

        assert user_dict["user_id"] == "test-user"
        assert user_dict["username"] == "testuser"
        assert "backup_user" in user_dict["roles"]
        assert "backup_viewer" in user_dict["roles"]
        assert "audit:view" in user_dict["additional_permissions"]
        assert user_dict["active"] is False

        # Convert back to user
        restored_user = User.from_dict(user_dict)

        assert restored_user.user_id == user.user_id
        assert restored_user.username == user.username
        assert restored_user.roles == user.roles
        assert restored_user.additional_permissions == user.additional_permissions
        assert restored_user.active == user.active


class TestFileBasedAccessControl:
    """Test FileBasedAccessControl implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.users_file = Path(self.temp_dir) / "test_users.json"

    def test_initialization_creates_default_admin(self):
        """Test that initialization creates default admin user when no users file exists."""
        access_control = FileBasedAccessControl(self.users_file)

        # Should have created default admin user
        admin_user = access_control.get_user("admin")
        assert admin_user is not None
        assert admin_user.username == "admin"
        assert Role.BACKUP_ADMIN in admin_user.roles

        # Should have created users file
        assert self.users_file.exists()

    def test_load_users_from_file(self):
        """Test loading users from configuration file."""
        # Create users file
        users_data = {
            "user1": {
                "user_id": "user1",
                "username": "testuser1",
                "roles": ["backup_user"],
                "additional_permissions": ["audit:view"],
                "active": True,
            },
            "user2": {
                "user_id": "user2",
                "username": "testuser2",
                "roles": ["backup_operator"],
                "additional_permissions": [],
                "active": False,
            },
        }

        with open(self.users_file, "w") as f:
            json.dump(users_data, f)

        access_control = FileBasedAccessControl(self.users_file)

        # Verify users were loaded
        user1 = access_control.get_user("user1")
        assert user1 is not None
        assert user1.username == "testuser1"
        assert Role.BACKUP_USER in user1.roles
        assert Permission.VIEW_AUDIT_LOGS in user1.additional_permissions
        assert user1.active is True

        user2 = access_control.get_user("user2")
        assert user2 is not None
        assert user2.username == "testuser2"
        assert Role.BACKUP_OPERATOR in user2.roles
        assert user2.active is False

    def test_authenticate_user_success(self):
        """Test successful user authentication."""
        access_control = FileBasedAccessControl(self.users_file)

        # Create a test user
        test_user = User(
            user_id="testuser",
            username="testuser",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )
        access_control.create_user(test_user)

        # Authenticate user
        authenticated_user = access_control.authenticate_user({"user_id": "testuser"})

        assert authenticated_user is not None
        assert authenticated_user.user_id == "testuser"
        assert authenticated_user.active is True

    def test_authenticate_user_failure(self):
        """Test failed user authentication."""
        access_control = FileBasedAccessControl(self.users_file)

        # Try to authenticate non-existent user
        authenticated_user = access_control.authenticate_user({"user_id": "nonexistent"})
        assert authenticated_user is None

        # Try to authenticate inactive user
        inactive_user = User(
            user_id="inactive",
            username="inactive",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
            active=False,
        )
        access_control.create_user(inactive_user)

        authenticated_user = access_control.authenticate_user({"user_id": "inactive"})
        assert authenticated_user is None

    def test_authorize_operation_success(self):
        """Test successful operation authorization."""
        access_control = FileBasedAccessControl(self.users_file)

        user = User(
            user_id="testuser",
            username="testuser",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )

        # Should authorize operations user has permission for
        assert access_control.authorize_operation(user, Permission.CREATE_BACKUP) is True
        assert access_control.authorize_operation(user, Permission.RESTORE_BACKUP) is True

    def test_authorize_operation_failure(self):
        """Test failed operation authorization."""
        access_control = FileBasedAccessControl(self.users_file)

        user = User(
            user_id="testuser",
            username="testuser",
            roles={Role.BACKUP_VIEWER},  # Read-only role
            additional_permissions=set(),
        )

        # Should not authorize operations user doesn't have permission for
        assert access_control.authorize_operation(user, Permission.CREATE_BACKUP) is False
        assert access_control.authorize_operation(user, Permission.DELETE_BACKUP) is False

        # Should not authorize operations for inactive user
        user.active = False
        assert access_control.authorize_operation(user, Permission.VIEW_BACKUP) is False

    def test_create_user(self):
        """Test creating a new user."""
        access_control = FileBasedAccessControl(self.users_file)

        user = User(
            user_id="newuser",
            username="newuser",
            roles={Role.BACKUP_OPERATOR},
            additional_permissions={Permission.VIEW_AUDIT_LOGS},
        )

        # Create user
        result = access_control.create_user(user)
        assert result is True

        # Verify user was created
        created_user = access_control.get_user("newuser")
        assert created_user is not None
        assert created_user.username == "newuser"
        assert Role.BACKUP_OPERATOR in created_user.roles

        # Try to create user with same ID (should fail)
        duplicate_user = User(
            user_id="newuser",
            username="duplicate",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )
        result = access_control.create_user(duplicate_user)
        assert result is False

    def test_update_user(self):
        """Test updating an existing user."""
        access_control = FileBasedAccessControl(self.users_file)

        # Create initial user
        user = User(
            user_id="updateuser",
            username="updateuser",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )
        access_control.create_user(user)

        # Update user
        user.roles = {Role.BACKUP_OPERATOR}
        user.additional_permissions = {Permission.VIEW_AUDIT_LOGS}

        result = access_control.update_user(user)
        assert result is True

        # Verify user was updated
        updated_user = access_control.get_user("updateuser")
        assert Role.BACKUP_OPERATOR in updated_user.roles
        assert Permission.VIEW_AUDIT_LOGS in updated_user.additional_permissions

        # Try to update non-existent user (should fail)
        nonexistent_user = User(
            user_id="nonexistent",
            username="nonexistent",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )
        result = access_control.update_user(nonexistent_user)
        assert result is False

    def test_delete_user(self):
        """Test deleting a user."""
        access_control = FileBasedAccessControl(self.users_file)

        # Create user
        user = User(
            user_id="deleteuser",
            username="deleteuser",
            roles={Role.BACKUP_USER},
            additional_permissions=set(),
        )
        access_control.create_user(user)

        # Verify user exists
        assert access_control.get_user("deleteuser") is not None

        # Delete user
        result = access_control.delete_user("deleteuser")
        assert result is True

        # Verify user was deleted
        assert access_control.get_user("deleteuser") is None

        # Try to delete non-existent user (should fail)
        result = access_control.delete_user("nonexistent")
        assert result is False

    def test_list_users(self):
        """Test listing all users."""
        access_control = FileBasedAccessControl(self.users_file)

        # Should have default admin user
        users = access_control.list_users()
        assert len(users) == 1
        assert users[0].user_id == "admin"

        # Add more users
        user1 = User("user1", "user1", {Role.BACKUP_USER}, set())
        user2 = User("user2", "user2", {Role.BACKUP_OPERATOR}, set())

        access_control.create_user(user1)
        access_control.create_user(user2)

        # Should list all users
        users = access_control.list_users()
        assert len(users) == 3
        user_ids = {user.user_id for user in users}
        assert user_ids == {"admin", "user1", "user2"}


class TestAccessControlManager:
    """Test AccessControlManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.users_file = Path(self.temp_dir) / "test_users.json"
        self.access_control = FileBasedAccessControl(self.users_file)
        self.manager = AccessControlManager(self.access_control)

    def test_authenticate(self):
        """Test user authentication through manager."""
        # Create test user
        user = User("testuser", "testuser", {Role.BACKUP_USER}, set())
        self.access_control.create_user(user)

        # Authenticate
        authenticated_user = self.manager.authenticate({"user_id": "testuser"})
        assert authenticated_user is not None
        assert authenticated_user.user_id == "testuser"

    def test_check_permission(self):
        """Test permission checking through manager."""
        user = User("testuser", "testuser", {Role.BACKUP_USER}, set())

        assert self.manager.check_permission(user, Permission.CREATE_BACKUP) is True
        assert self.manager.check_permission(user, Permission.MANAGE_ROLES) is False

    def test_require_permission_success(self):
        """Test requiring permission when user has it."""
        user = User("testuser", "testuser", {Role.BACKUP_USER}, set())

        # Should not raise exception
        self.manager.require_permission(user, Permission.CREATE_BACKUP)

    def test_require_permission_failure(self):
        """Test requiring permission when user doesn't have it."""
        user = User("testuser", "testuser", {Role.BACKUP_VIEWER}, set())

        # Should raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            self.manager.require_permission(user, Permission.CREATE_BACKUP)

        assert "lacks permission backup:create" in str(exc_info.value)

    def test_create_user(self):
        """Test creating user through manager."""
        user = self.manager.create_user(
            user_id="newuser",
            username="New User",
            roles=[Role.BACKUP_OPERATOR],
            additional_permissions=[Permission.VIEW_AUDIT_LOGS],
        )

        assert user.user_id == "newuser"
        assert user.username == "New User"
        assert Role.BACKUP_OPERATOR in user.roles
        assert Permission.VIEW_AUDIT_LOGS in user.additional_permissions

        # Verify user was created in access control
        created_user = self.access_control.get_user("newuser")
        assert created_user is not None

    def test_create_user_duplicate(self):
        """Test creating user with duplicate ID."""
        # Create first user
        self.manager.create_user("duplicate", "User 1", [Role.BACKUP_USER])

        # Try to create user with same ID
        with pytest.raises(ValueError) as exc_info:
            self.manager.create_user("duplicate", "User 2", [Role.BACKUP_OPERATOR])

        assert "already exists" in str(exc_info.value)

    def test_update_user_roles(self):
        """Test updating user roles through manager."""
        # Create user
        self.manager.create_user("testuser", "Test User", [Role.BACKUP_USER])

        # Update roles
        result = self.manager.update_user_roles(
            "testuser", [Role.BACKUP_OPERATOR, Role.BACKUP_VIEWER]
        )
        assert result is True

        # Verify roles were updated
        updated_user = self.manager.get_user("testuser")
        assert Role.BACKUP_OPERATOR in updated_user.roles
        assert Role.BACKUP_VIEWER in updated_user.roles
        assert Role.BACKUP_USER not in updated_user.roles

    def test_deactivate_user(self):
        """Test deactivating user through manager."""
        # Create user
        user = self.manager.create_user("testuser", "Test User", [Role.BACKUP_USER])
        assert user.active is True

        # Deactivate user
        result = self.manager.deactivate_user("testuser")
        assert result is True

        # Verify user was deactivated
        deactivated_user = self.manager.get_user("testuser")
        assert deactivated_user.active is False

    def test_list_users(self):
        """Test listing users through manager."""
        # Create some users
        self.manager.create_user("user1", "User 1", [Role.BACKUP_USER])
        self.manager.create_user("user2", "User 2", [Role.BACKUP_OPERATOR])

        users = self.manager.list_users()
        # Should include default admin + 2 created users
        assert len(users) >= 3

        user_ids = {user.user_id for user in users}
        assert "admin" in user_ids
        assert "user1" in user_ids
        assert "user2" in user_ids


class TestGlobalAccessControl:
    """Test global access control functions."""

    def test_get_access_control_manager(self):
        """Test getting global access control manager."""
        manager1 = get_access_control_manager()
        manager2 = get_access_control_manager()

        # Should return the same instance
        assert manager1 is manager2

    def test_configure_access_control(self):
        """Test configuring global access control manager."""
        temp_dir = tempfile.mkdtemp()
        users_file = Path(temp_dir) / "configured_users.json"
        custom_access_control = FileBasedAccessControl(users_file)

        configure_access_control(custom_access_control)

        manager = get_access_control_manager()
        assert manager.access_control is custom_access_control


@pytest.fixture
def sample_user():
    """Fixture providing a sample user."""
    return User(
        user_id="sample-user",
        username="Sample User",
        roles={Role.BACKUP_USER, Role.BACKUP_VIEWER},
        additional_permissions={Permission.VIEW_AUDIT_LOGS},
        active=True,
    )


def test_user_permission_inheritance(sample_user):
    """Test that user inherits permissions from multiple roles correctly."""
    all_perms = sample_user.get_all_permissions()

    # Should have permissions from BACKUP_USER role
    backup_user_perms = get_role_permissions(Role.BACKUP_USER)
    for perm in backup_user_perms:
        assert perm in all_perms

    # Should have permissions from BACKUP_VIEWER role
    backup_viewer_perms = get_role_permissions(Role.BACKUP_VIEWER)
    for perm in backup_viewer_perms:
        assert perm in all_perms

    # Should have additional permissions
    assert Permission.VIEW_AUDIT_LOGS in all_perms


def test_role_permission_coverage():
    """Test that all roles have appropriate permission coverage."""
    # Backup user should have basic backup/restore permissions
    user_perms = get_role_permissions(Role.BACKUP_USER)
    assert Permission.CREATE_BACKUP in user_perms
    assert Permission.RESTORE_BACKUP in user_perms
    assert Permission.VIEW_BACKUP in user_perms

    # Backup operator should have management permissions
    operator_perms = get_role_permissions(Role.BACKUP_OPERATOR)
    assert Permission.DELETE_BACKUP in operator_perms
    assert Permission.CREATE_SCHEDULE in operator_perms
    assert Permission.EXECUTE_SCHEDULE in operator_perms

    # Backup viewer should only have read permissions
    viewer_perms = get_role_permissions(Role.BACKUP_VIEWER)
    assert Permission.VIEW_BACKUP in viewer_perms
    assert Permission.LIST_BACKUPS in viewer_perms
    assert Permission.CREATE_BACKUP not in viewer_perms
    assert Permission.DELETE_BACKUP not in viewer_perms

    # Security officer should have security-related permissions
    security_perms = get_role_permissions(Role.SECURITY_OFFICER)
    assert Permission.VIEW_AUDIT_LOGS in security_perms
    assert Permission.MANAGE_ENCRYPTION in security_perms
    assert Permission.SECURE_DELETE in security_perms

    # Backup admin should have all permissions
    admin_perms = get_role_permissions(Role.BACKUP_ADMIN)
    assert len(admin_perms) == len(Permission)


def test_access_control_handles_malformed_users_file():
    """Test that access control handles malformed users file gracefully."""
    temp_dir = tempfile.mkdtemp()
    users_file = Path(temp_dir) / "malformed_users.json"

    # Create malformed users file
    with open(users_file, "w") as f:
        f.write('{"invalid": "json"')  # Malformed JSON

    # Should not raise exception and should create empty users dict
    access_control = FileBasedAccessControl(users_file)
    users = access_control.list_users()
    assert len(users) == 0
