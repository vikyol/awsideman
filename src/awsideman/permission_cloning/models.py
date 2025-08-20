"""
Data models for permission cloning operations.

This module defines all the core data structures used for copying permission assignments
and cloning permission sets in AWS Identity Center.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(Enum):
    """Enumeration of entity types in AWS Identity Center."""

    USER = "USER"
    GROUP = "GROUP"


class ValidationResultType(Enum):
    """Enumeration of validation result types."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass
class CustomerManagedPolicy:
    """Represents a customer managed policy reference."""

    name: str
    path: str

    def validate(self) -> "ValidationResult":
        """Validate the customer managed policy reference."""
        errors = []

        if not self.name or not self.name.strip():
            errors.append("Policy name cannot be empty")
        elif not re.match(r"^[\w+=,.@-]+$", self.name):
            errors.append("Policy name contains invalid characters")

        if not self.path or not self.path.strip():
            errors.append("Policy path cannot be empty")
        elif not self.path.startswith("/"):
            errors.append("Policy path must start with '/'")
        elif not self.path.endswith("/"):
            errors.append("Policy path must end with '/'")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class EntityReference:
    """Reference to a user or group entity in AWS Identity Center."""

    entity_type: EntityType
    entity_id: str
    entity_name: str

    def validate(self) -> "ValidationResult":
        """Validate the entity reference."""
        errors = []

        if not isinstance(self.entity_type, EntityType):
            errors.append("Entity type must be a valid EntityType enum value")

        if not self.entity_id or not self.entity_id.strip():
            errors.append("Entity ID cannot be empty")
        elif not re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", self.entity_id
        ):
            errors.append("Entity ID must be a valid UUID format")

        if not self.entity_name or not self.entity_name.strip():
            errors.append("Entity name cannot be empty")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class PermissionAssignment:
    """Represents a permission set assignment to an account."""

    permission_set_arn: str
    permission_set_name: str
    account_id: str
    account_name: Optional[str] = None

    def validate(self) -> "ValidationResult":
        """Validate the permission assignment."""
        errors = []

        if not self.permission_set_arn or not self.permission_set_arn.strip():
            errors.append("Permission set ARN cannot be empty")
        elif not re.match(
            r"^arn:aws:sso:::permissionSet/[a-zA-Z0-9-]+/ps-[a-zA-Z0-9]+$", self.permission_set_arn
        ):
            errors.append("Permission set ARN format is invalid")

        if not self.permission_set_name or not self.permission_set_name.strip():
            errors.append("Permission set name cannot be empty")

        if not self.account_id or not self.account_id.strip():
            errors.append("Account ID cannot be empty")
        elif not re.match(r"^\d{12}$", self.account_id):
            errors.append("Account ID must be a 12-digit number")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class PermissionSetConfig:
    """Complete configuration of a permission set."""

    name: str
    description: str
    session_duration: str
    relay_state_url: Optional[str] = None
    aws_managed_policies: Optional[List[str]] = None
    customer_managed_policies: Optional[List[CustomerManagedPolicy]] = None
    inline_policy: Optional[str] = None

    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.aws_managed_policies is None:
            self.aws_managed_policies = []
        if self.customer_managed_policies is None:
            self.customer_managed_policies = []

    def validate(self) -> "ValidationResult":
        """Validate the permission set configuration."""
        errors = []
        warnings = []

        # Validate required fields
        if not self.name or not self.name.strip():
            errors.append("Permission set name cannot be empty")
        elif len(self.name) > 32:
            errors.append("Permission set name cannot exceed 32 characters")
        elif not re.match(r"^[\w+=,.@-]+$", self.name):
            errors.append("Permission set name contains invalid characters")

        if not self.description or not self.description.strip():
            errors.append("Permission set description cannot be empty")
        elif len(self.description) > 700:
            errors.append("Permission set description cannot exceed 700 characters")

        # Validate session duration format (ISO 8601 duration)
        if not self.session_duration or not self.session_duration.strip():
            errors.append("Session duration cannot be empty")
        elif not re.match(r"^PT([0-9]+H)?([0-9]+M)?$", self.session_duration):
            errors.append("Session duration must be in ISO 8601 format (e.g., PT1H, PT2H30M)")

        # Validate relay state URL if provided
        if self.relay_state_url:
            if len(self.relay_state_url) > 240:
                errors.append("Relay state URL cannot exceed 240 characters")
            elif not re.match(r"^https?://", self.relay_state_url):
                warnings.append("Relay state URL should start with http:// or https://")

        # Validate AWS managed policies
        for policy_arn in self.aws_managed_policies:
            if not re.match(r"^arn:aws:iam::aws:policy/", policy_arn):
                errors.append(f"Invalid AWS managed policy ARN: {policy_arn}")

        # Validate customer managed policies
        for policy in self.customer_managed_policies:
            policy_validation = policy.validate()
            if policy_validation.result_type == ValidationResultType.ERROR:
                errors.extend(policy_validation.messages)

        # Validate inline policy if provided
        if self.inline_policy:
            if len(self.inline_policy) > 32768:  # 32KB limit
                errors.append("Inline policy cannot exceed 32KB")

        # Check if at least one policy is defined
        if (
            not self.aws_managed_policies
            and not self.customer_managed_policies
            and not self.inline_policy
        ):
            warnings.append("Permission set has no policies defined")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        elif warnings:
            return ValidationResult(ValidationResultType.WARNING, warnings)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class CopyFilters:
    """Filters for controlling which assignments are copied."""

    exclude_permission_sets: Optional[List[str]] = None
    include_accounts: Optional[List[str]] = None
    exclude_accounts: Optional[List[str]] = None

    def validate(self) -> "ValidationResult":
        """Validate the copy filters."""
        errors = []
        warnings = []

        # Validate permission set filters - only exclude filters are supported

        # Validate account ID filters
        if self.include_accounts:
            for account_id in self.include_accounts:
                if not re.match(r"^\d{12}$", account_id):
                    errors.append(f"Invalid account ID in include filter: {account_id}")

        if self.exclude_accounts:
            for account_id in self.exclude_accounts:
                if not re.match(r"^\d{12}$", account_id):
                    errors.append(f"Invalid account ID in exclude filter: {account_id}")

        if self.include_accounts and self.exclude_accounts:
            overlap = set(self.include_accounts) & set(self.exclude_accounts)
            if overlap:
                errors.append(f"Accounts cannot be both included and excluded: {list(overlap)}")

        # Check for empty filters
        if (
            not self.exclude_permission_sets
            and not self.include_accounts
            and not self.exclude_accounts
        ):
            warnings.append("No filters specified - all assignments will be processed")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        elif warnings:
            return ValidationResult(ValidationResultType.WARNING, warnings)
        return ValidationResult(ValidationResultType.SUCCESS, [])

    def to_dict(self) -> Dict[str, Any]:
        """Convert filters to dictionary representation."""
        return {
            "exclude_permission_sets": self.exclude_permission_sets,
            "include_accounts": self.include_accounts,
            "exclude_accounts": self.exclude_accounts,
        }


@dataclass
class CopyResult:
    """Result of a permission assignment copy operation."""

    source: EntityReference
    target: EntityReference
    assignments_copied: List[PermissionAssignment]
    assignments_skipped: List[PermissionAssignment]
    rollback_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.assignments_copied is None:
            self.assignments_copied = []
        if self.assignments_skipped is None:
            self.assignments_skipped = []

    def validate(self) -> "ValidationResult":
        """Validate the copy result."""
        errors = []

        # Validate source and target entities
        source_validation = self.source.validate()
        if source_validation.result_type == ValidationResultType.ERROR:
            errors.extend([f"Source entity: {msg}" for msg in source_validation.messages])

        target_validation = self.target.validate()
        if target_validation.result_type == ValidationResultType.ERROR:
            errors.extend([f"Target entity: {msg}" for msg in target_validation.messages])

        # Validate assignments
        for assignment in self.assignments_copied:
            assignment_validation = assignment.validate()
            if assignment_validation.result_type == ValidationResultType.ERROR:
                errors.extend(
                    [f"Copied assignment: {msg}" for msg in assignment_validation.messages]
                )

        for assignment in self.assignments_skipped:
            assignment_validation = assignment.validate()
            if assignment_validation.result_type == ValidationResultType.ERROR:
                errors.extend(
                    [f"Skipped assignment: {msg}" for msg in assignment_validation.messages]
                )

        # Validate consistency
        if not self.success and not self.error_message:
            errors.append("Failed operations must include an error message")

        if self.success and self.error_message:
            errors.append("Successful operations should not have error messages")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class CloneResult:
    """Result of a permission set clone operation."""

    source_name: str
    target_name: str
    cloned_config: Optional[PermissionSetConfig] = None
    rollback_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    source_arn: Optional[str] = None
    target_arn: Optional[str] = None

    def validate(self) -> "ValidationResult":
        """Validate the clone result."""
        errors = []

        # Validate source and target names
        if not self.source_name or not self.source_name.strip():
            errors.append("Source permission set name cannot be empty")

        if not self.target_name or not self.target_name.strip():
            errors.append("Target permission set name cannot be empty")

        # Validate cloned configuration if present
        if self.cloned_config:
            config_validation = self.cloned_config.validate()
            if config_validation.result_type == ValidationResultType.ERROR:
                errors.extend([f"Cloned config: {msg}" for msg in config_validation.messages])

        # Validate consistency
        if not self.success and not self.error_message:
            errors.append("Failed operations must include an error message")

        if self.success and self.error_message:
            errors.append("Successful operations should not have error messages")

        if self.success and not self.cloned_config:
            errors.append("Successful clone operations must include cloned configuration")

        if errors:
            return ValidationResult(ValidationResultType.ERROR, errors)
        return ValidationResult(ValidationResultType.SUCCESS, [])


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    result_type: ValidationResultType
    messages: List[str]

    def __post_init__(self):
        """Initialize default values for optional fields."""
        if self.messages is None:
            self.messages = []

    @property
    def is_valid(self) -> bool:
        """Check if the validation result indicates success."""
        return self.result_type == ValidationResultType.SUCCESS

    @property
    def has_errors(self) -> bool:
        """Check if the validation result has errors."""
        return self.result_type == ValidationResultType.ERROR

    @property
    def has_warnings(self) -> bool:
        """Check if the validation result has warnings."""
        return self.result_type == ValidationResultType.WARNING
