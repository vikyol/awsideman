"""
Role-Based Access Control (RBAC) for backup-restore operations.

This module provides comprehensive access control mechanisms for backup and restore
operations, including role definitions, permission checking, and access enforcement.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .audit import AuditEventType, get_audit_logger


class Permission(Enum):
    """Available permissions for backup-restore operations."""

    # Backup permissions
    CREATE_BACKUP = "backup:create"
    LIST_BACKUPS = "backup:list"
    VIEW_BACKUP = "backup:view"
    DELETE_BACKUP = "backup:delete"
    VALIDATE_BACKUP = "backup:validate"

    # Restore permissions
    RESTORE_BACKUP = "restore:execute"
    PREVIEW_RESTORE = "restore:preview"
    VALIDATE_RESTORE = "restore:validate"

    # Export/Import permissions
    EXPORT_BACKUP = "export:execute"
    IMPORT_BACKUP = "import:execute"

    # Schedule permissions
    CREATE_SCHEDULE = "schedule:create"
    UPDATE_SCHEDULE = "schedule:update"
    DELETE_SCHEDULE = "schedule:delete"
    VIEW_SCHEDULE = "schedule:view"
    EXECUTE_SCHEDULE = "schedule:execute"

    # Security permissions
    VIEW_AUDIT_LOGS = "audit:view"
    MANAGE_ENCRYPTION = "encryption:manage"
    SECURE_DELETE = "security:delete"

    # Administrative permissions
    MANAGE_ROLES = "admin:roles"
    MANAGE_USERS = "admin:users"
    SYSTEM_CONFIG = "admin:config"


class Role(Enum):
    """Predefined roles with specific permission sets."""

    # Basic user role - can create and restore their own backups
    BACKUP_USER = "backup_user"

    # Operator role - can manage backups and schedules
    BACKUP_OPERATOR = "backup_operator"

    # Administrator role - full access to all operations
    BACKUP_ADMIN = "backup_admin"

    # Read-only role - can view backups and audit logs
    BACKUP_VIEWER = "backup_viewer"

    # Security role - can manage encryption and view security events
    SECURITY_OFFICER = "security_officer"


@dataclass
class User:
    """Represents a user in the RBAC system."""

    user_id: str
    username: str
    roles: Set[Role]
    additional_permissions: Set[Permission]
    active: bool = True

    def get_all_permissions(self) -> Set[Permission]:
        """Get all permissions for this user (from roles and additional)."""
        permissions = set(self.additional_permissions)

        for role in self.roles:
            permissions.update(get_role_permissions(role))

        return permissions

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in self.get_all_permissions()

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "roles": [role.value for role in self.roles],
            "additional_permissions": [perm.value for perm in self.additional_permissions],
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """Create user from dictionary."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            roles={Role(role) for role in data["roles"]},
            additional_permissions={Permission(perm) for perm in data["additional_permissions"]},
            active=data.get("active", True),
        )


def get_role_permissions(role: Role) -> Set[Permission]:
    """Get the permissions associated with a role."""
    role_permissions = {
        Role.BACKUP_USER: {
            Permission.CREATE_BACKUP,
            Permission.LIST_BACKUPS,
            Permission.VIEW_BACKUP,
            Permission.RESTORE_BACKUP,
            Permission.PREVIEW_RESTORE,
            Permission.VALIDATE_BACKUP,
            Permission.VALIDATE_RESTORE,
            Permission.EXPORT_BACKUP,
        },
        Role.BACKUP_OPERATOR: {
            Permission.CREATE_BACKUP,
            Permission.LIST_BACKUPS,
            Permission.VIEW_BACKUP,
            Permission.DELETE_BACKUP,
            Permission.VALIDATE_BACKUP,
            Permission.RESTORE_BACKUP,
            Permission.PREVIEW_RESTORE,
            Permission.VALIDATE_RESTORE,
            Permission.EXPORT_BACKUP,
            Permission.IMPORT_BACKUP,
            Permission.CREATE_SCHEDULE,
            Permission.UPDATE_SCHEDULE,
            Permission.DELETE_SCHEDULE,
            Permission.VIEW_SCHEDULE,
            Permission.EXECUTE_SCHEDULE,
        },
        Role.BACKUP_ADMIN: set(Permission),  # All permissions
        Role.BACKUP_VIEWER: {
            Permission.LIST_BACKUPS,
            Permission.VIEW_BACKUP,
            Permission.PREVIEW_RESTORE,
            Permission.VALIDATE_BACKUP,
            Permission.VIEW_SCHEDULE,
            Permission.VIEW_AUDIT_LOGS,
        },
        Role.SECURITY_OFFICER: {
            Permission.VIEW_AUDIT_LOGS,
            Permission.MANAGE_ENCRYPTION,
            Permission.SECURE_DELETE,
            Permission.LIST_BACKUPS,
            Permission.VIEW_BACKUP,
            Permission.VALIDATE_BACKUP,
        },
    }

    return role_permissions.get(role, set())


class AccessControlInterface(ABC):
    """Interface for access control implementations."""

    @abstractmethod
    def authenticate_user(self, credentials: Dict[str, Any]) -> Optional[User]:
        """Authenticate a user and return user object if successful."""
        pass

    @abstractmethod
    def authorize_operation(
        self, user: User, permission: Permission, resource_id: Optional[str] = None
    ) -> bool:
        """Check if user is authorized to perform an operation."""
        pass

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        pass

    @abstractmethod
    def create_user(self, user: User) -> bool:
        """Create a new user."""
        pass

    @abstractmethod
    def update_user(self, user: User) -> bool:
        """Update an existing user."""
        pass

    @abstractmethod
    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        pass

    @abstractmethod
    def list_users(self) -> List[User]:
        """List all users."""
        pass


class FileBasedAccessControl(AccessControlInterface):
    """
    File-based access control implementation.

    Stores user and role information in JSON files for simple deployments.
    In production, this would typically be replaced with integration to
    enterprise identity systems like LDAP, Active Directory, or OAuth.
    """

    def __init__(self, users_file: Optional[Path] = None):
        """
        Initialize file-based access control.

        Args:
            users_file: Path to users configuration file
        """
        self.users_file = users_file or Path("users.json")
        self.users: Dict[str, User] = {}
        self.audit_logger = get_audit_logger()

        # Load users from file
        self._load_users()

    def _load_users(self) -> None:
        """Load users from configuration file."""
        if not self.users_file.exists():
            # Create default admin user if no users file exists
            admin_user = User(
                user_id="admin",
                username="admin",
                roles={Role.BACKUP_ADMIN},
                additional_permissions=set(),
            )
            self.users = {"admin": admin_user}
            self._save_users()
            return

        try:
            with open(self.users_file, "r") as f:
                users_data = json.load(f)

            self.users = {}
            for user_id, user_data in users_data.items():
                self.users[user_id] = User.from_dict(user_data)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Log error and use empty users dict
            self.audit_logger.log_security_event(
                AuditEventType.SECURITY_VIOLATION,
                "Failed to load users configuration",
                error_message=str(e),
            )
            self.users = {}

    def _save_users(self) -> None:
        """Save users to configuration file."""
        try:
            users_data = {user_id: user.to_dict() for user_id, user in self.users.items()}

            with open(self.users_file, "w") as f:
                json.dump(users_data, f, indent=2)

        except IOError as e:
            self.audit_logger.log_security_event(
                AuditEventType.SECURITY_VIOLATION,
                "Failed to save users configuration",
                error_message=str(e),
            )

    def authenticate_user(self, credentials: Dict[str, Any]) -> Optional[User]:
        """
        Authenticate a user with provided credentials.

        Args:
            credentials: Dictionary containing authentication credentials

        Returns:
            User object if authentication successful, None otherwise
        """
        user_id = credentials.get("user_id")
        # In a real implementation, this would verify passwords, tokens, etc.
        # For this implementation, we'll just check if user exists and is active

        if not user_id:
            return None

        user = self.users.get(user_id)
        if user and user.active:
            self.audit_logger.log_security_event(
                AuditEventType.ACCESS_GRANTED,
                "User authentication successful",
                user_id=user_id,
                success=True,
            )
            return user

        self.audit_logger.log_security_event(
            AuditEventType.ACCESS_DENIED,
            "User authentication failed",
            user_id=user_id,
            success=False,
            error_message="Invalid credentials or inactive user",
        )
        return None

    def authorize_operation(
        self, user: User, permission: Permission, resource_id: Optional[str] = None
    ) -> bool:
        """
        Check if user is authorized to perform an operation.

        Args:
            user: User requesting authorization
            permission: Permission being requested
            resource_id: Optional resource ID for resource-specific authorization

        Returns:
            True if authorized, False otherwise
        """
        if not user.active:
            self.audit_logger.log_access_attempt(
                resource_id or "system",
                user.user_id,
                granted=False,
                reason="User account is inactive",
            )
            return False

        has_permission = user.has_permission(permission)

        # Log the access attempt
        self.audit_logger.log_access_attempt(
            resource_id or permission.value,
            user.user_id,
            granted=has_permission,
            reason=None if has_permission else f"Missing permission: {permission.value}",
        )

        return has_permission

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self.users.get(user_id)

    def create_user(self, user: User) -> bool:
        """Create a new user."""
        if user.user_id in self.users:
            return False

        self.users[user.user_id] = user
        self._save_users()

        self.audit_logger.log_security_event(
            AuditEventType.ACCESS_GRANTED,
            "User created",
            user_id=user.user_id,
            success=True,
            details={"roles": [role.value for role in user.roles]},
        )

        return True

    def update_user(self, user: User) -> bool:
        """Update an existing user."""
        if user.user_id not in self.users:
            return False

        old_user = self.users[user.user_id]
        self.users[user.user_id] = user
        self._save_users()

        self.audit_logger.log_security_event(
            AuditEventType.ACCESS_GRANTED,
            "User updated",
            user_id=user.user_id,
            success=True,
            details={
                "old_roles": [role.value for role in old_user.roles],
                "new_roles": [role.value for role in user.roles],
            },
        )

        return True

    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        if user_id not in self.users:
            return False

        del self.users[user_id]
        self._save_users()

        self.audit_logger.log_security_event(
            AuditEventType.ACCESS_GRANTED, "User deleted", user_id=user_id, success=True
        )

        return True

    def list_users(self) -> List[User]:
        """List all users."""
        return list(self.users.values())


class AccessControlManager:
    """
    Manager for access control operations.

    Provides a high-level interface for authentication and authorization
    with support for different access control backends.
    """

    def __init__(self, access_control: Optional[AccessControlInterface] = None):
        """
        Initialize access control manager.

        Args:
            access_control: Access control implementation to use
        """
        self.access_control = access_control or FileBasedAccessControl()
        self.audit_logger = get_audit_logger()

    def authenticate(self, credentials: Dict[str, Any]) -> Optional[User]:
        """Authenticate a user."""
        return self.access_control.authenticate_user(credentials)

    def check_permission(
        self, user: User, permission: Permission, resource_id: Optional[str] = None
    ) -> bool:
        """Check if user has permission for an operation."""
        return self.access_control.authorize_operation(user, permission, resource_id)

    def require_permission(
        self, user: User, permission: Permission, resource_id: Optional[str] = None
    ) -> None:
        """
        Require a permission, raising an exception if not authorized.

        Args:
            user: User requesting permission
            permission: Required permission
            resource_id: Optional resource ID

        Raises:
            PermissionError: If user doesn't have required permission
        """
        if not self.check_permission(user, permission, resource_id):
            raise PermissionError(f"User {user.user_id} lacks permission {permission.value}")

    def create_user(
        self,
        user_id: str,
        username: str,
        roles: List[Role],
        additional_permissions: Optional[List[Permission]] = None,
    ) -> User:
        """
        Create a new user.

        Args:
            user_id: Unique user identifier
            username: Human-readable username
            roles: List of roles to assign
            additional_permissions: Additional permissions beyond roles

        Returns:
            Created user object

        Raises:
            ValueError: If user already exists
        """
        user = User(
            user_id=user_id,
            username=username,
            roles=set(roles),
            additional_permissions=set(additional_permissions or []),
        )

        if not self.access_control.create_user(user):
            raise ValueError(f"User {user_id} already exists")

        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self.access_control.get_user(user_id)

    def update_user_roles(self, user_id: str, roles: List[Role]) -> bool:
        """Update user's roles."""
        user = self.access_control.get_user(user_id)
        if not user:
            return False

        user.roles = set(roles)
        return self.access_control.update_user(user)

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account."""
        user = self.access_control.get_user(user_id)
        if not user:
            return False

        user.active = False
        return self.access_control.update_user(user)

    def list_users(self) -> List[User]:
        """List all users."""
        return self.access_control.list_users()


# Global access control manager instance
_access_control_manager: Optional[AccessControlManager] = None


def get_access_control_manager() -> AccessControlManager:
    """Get the global access control manager instance."""
    global _access_control_manager
    if _access_control_manager is None:
        _access_control_manager = AccessControlManager()
    return _access_control_manager


def configure_access_control(access_control: AccessControlInterface) -> None:
    """Configure the global access control manager."""
    global _access_control_manager
    _access_control_manager = AccessControlManager(access_control)
