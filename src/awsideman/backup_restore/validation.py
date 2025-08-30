"""
Validation utilities for backup and restore data models.

This module provides comprehensive validation functions for all data models
used in the backup-restore system, ensuring data integrity and consistency.
"""

import re
from datetime import datetime
from typing import List

from .models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupType,
    ConflictStrategy,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    ResourceType,
    RestoreOptions,
    RetentionPolicy,
    ScheduleConfig,
    UserData,
    ValidationResult,
)


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


class DataValidator:
    """Comprehensive validator for backup-restore data models."""

    # AWS ARN patterns
    INSTANCE_ARN_PATTERN = re.compile(r"^arn:aws:sso:::instance/ssoins-[a-f0-9]{16}$")
    PERMISSION_SET_ARN_PATTERN = re.compile(
        r"^arn:aws:sso:::permissionSet/ssoins-[a-f0-9]{16}/ps-[a-f0-9]{16}$"
    )
    ACCOUNT_ID_PATTERN = re.compile(r"^\d{12}$")

    # Identity patterns
    USER_ID_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    GROUP_ID_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")

    # Email pattern
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    # Cron expression pattern (basic validation)
    CRON_PATTERN = re.compile(
        r"^(\*|[0-5]?\d|\*\/\d+)\s+(\*|[01]?\d|2[0-3]|\*\/\d+)\s+(\*|[0-2]?\d|3[01]|\*\/\d+)\s+(\*|[0]?\d|1[0-2]|\*\/\d+)\s+(\*|[0-6]|\*\/\d+)$"
    )

    @classmethod
    def validate_backup_metadata(cls, metadata: BackupMetadata) -> ValidationResult:
        """
        Validate backup metadata structure and content.

        Args:
            metadata: BackupMetadata object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate required fields
        if not metadata.backup_id:
            errors.append("backup_id is required and cannot be empty")
        elif len(metadata.backup_id) < 8:
            errors.append("backup_id must be at least 8 characters long")

        if not metadata.instance_arn:
            errors.append("instance_arn is required and cannot be empty")
        elif not cls.INSTANCE_ARN_PATTERN.match(metadata.instance_arn):
            errors.append(f"instance_arn has invalid format: {metadata.instance_arn}")

        if not metadata.source_account:
            errors.append("source_account is required and cannot be empty")
        elif not cls.ACCOUNT_ID_PATTERN.match(metadata.source_account):
            errors.append(
                f"source_account must be a 12-digit AWS account ID: {metadata.source_account}"
            )

        if not metadata.source_region:
            errors.append("source_region is required and cannot be empty")
        elif len(metadata.source_region) < 3:
            errors.append("source_region appears to be invalid")

        if not metadata.version:
            errors.append("version is required and cannot be empty")

        # Validate timestamp
        if metadata.timestamp > datetime.now():
            warnings.append("backup timestamp is in the future")

        # Validate backup type
        if metadata.backup_type not in BackupType:
            errors.append(f"invalid backup_type: {metadata.backup_type}")

        # Validate retention policy
        retention_result = cls.validate_retention_policy(metadata.retention_policy)
        errors.extend(retention_result.errors)
        warnings.extend(retention_result.warnings)

        # Validate encryption metadata
        encryption_result = cls.validate_encryption_metadata(metadata.encryption_info)
        errors.extend(encryption_result.errors)
        warnings.extend(encryption_result.warnings)

        # Validate resource counts
        if metadata.resource_counts:
            for resource_type, count in metadata.resource_counts.items():
                if count < 0:
                    errors.append(f"resource count for {resource_type} cannot be negative: {count}")

        # Validate size
        if metadata.size_bytes < 0:
            errors.append(f"size_bytes cannot be negative: {metadata.size_bytes}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "backup_id",
                    "instance_arn",
                    "source_account",
                    "source_region",
                    "version",
                    "timestamp",
                    "backup_type",
                    "retention_policy",
                    "encryption_info",
                ]
            },
        )

    @classmethod
    def validate_backup_options(cls, options: BackupOptions) -> ValidationResult:
        """
        Validate backup options structure and content.

        Args:
            options: BackupOptions object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate backup type
        if options.backup_type not in BackupType:
            errors.append(f"invalid backup_type: {options.backup_type}")

        # Validate resource types
        if not options.resource_types:
            errors.append("resource_types cannot be empty")
        else:
            for resource_type in options.resource_types:
                if resource_type not in ResourceType:
                    errors.append(f"invalid resource_type: {resource_type}")

        # Validate incremental backup requirements
        if options.backup_type == BackupType.INCREMENTAL and not options.since:
            errors.append("incremental backup requires 'since' timestamp")

        if options.since and options.since > datetime.now():
            warnings.append("'since' timestamp is in the future")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={"validated_fields": ["backup_type", "resource_types", "since"]},
        )

    @classmethod
    def validate_restore_options(cls, options: RestoreOptions) -> ValidationResult:
        """
        Validate restore options structure and content.

        Args:
            options: RestoreOptions object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Validate target resources
        if not options.target_resources:
            errors.append("target_resources cannot be empty")
        else:
            for resource_type in options.target_resources:
                if resource_type not in ResourceType:
                    errors.append(f"invalid target resource_type: {resource_type}")

        # Validate conflict strategy
        if options.conflict_strategy not in ConflictStrategy:
            errors.append(f"invalid conflict_strategy: {options.conflict_strategy}")

        # Validate target account
        if options.target_account and not cls.ACCOUNT_ID_PATTERN.match(options.target_account):
            errors.append(
                f"target_account must be a 12-digit AWS account ID: {options.target_account}"
            )

        # Validate target region
        if options.target_region and len(options.target_region) < 3:
            errors.append("target_region appears to be invalid")

        # Validate resource mappings
        if options.resource_mappings:
            for old_id, new_id in options.resource_mappings.items():
                if not old_id or not new_id:
                    errors.append("resource mapping keys and values cannot be empty")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "target_resources",
                    "conflict_strategy",
                    "target_account",
                    "target_region",
                    "resource_mappings",
                ]
            },
        )

    @classmethod
    def validate_user_data(cls, user: UserData) -> ValidationResult:
        """
        Validate user data structure and content.

        Args:
            user: UserData object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate required fields
        if not user.user_id:
            errors.append("user_id is required and cannot be empty")
        elif not cls.USER_ID_PATTERN.match(user.user_id):
            errors.append(f"user_id has invalid UUID format: {user.user_id}")

        if not user.user_name:
            errors.append("user_name is required and cannot be empty")
        elif len(user.user_name) > 128:
            warnings.append("user_name is longer than recommended 128 characters")

        # Validate email format
        if user.email and not cls.EMAIL_PATTERN.match(user.email):
            errors.append(f"email has invalid format: {user.email}")

        # Validate name fields
        if user.display_name and len(user.display_name) > 256:
            warnings.append("display_name is longer than recommended 256 characters")

        if user.given_name and len(user.given_name) > 128:
            warnings.append("given_name is longer than recommended 128 characters")

        if user.family_name and len(user.family_name) > 128:
            warnings.append("family_name is longer than recommended 128 characters")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "user_id",
                    "user_name",
                    "email",
                    "display_name",
                    "given_name",
                    "family_name",
                ]
            },
        )

    @classmethod
    def validate_group_data(cls, group: GroupData) -> ValidationResult:
        """
        Validate group data structure and content.

        Args:
            group: GroupData object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate required fields
        if not group.group_id:
            errors.append("group_id is required and cannot be empty")
        elif not cls.GROUP_ID_PATTERN.match(group.group_id):
            errors.append(f"group_id has invalid UUID format: {group.group_id}")

        if not group.display_name:
            errors.append("display_name is required and cannot be empty")
        elif len(group.display_name) > 256:
            warnings.append("display_name is longer than recommended 256 characters")

        # Validate description
        if group.description and len(group.description) > 1024:
            warnings.append("description is longer than recommended 1024 characters")

        # Validate members
        if group.members:
            for member_id in group.members:
                if not cls.USER_ID_PATTERN.match(member_id):
                    errors.append(f"invalid member user_id format: {member_id}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={"validated_fields": ["group_id", "display_name", "description", "members"]},
        )

    @classmethod
    def validate_permission_set_data(cls, permission_set: PermissionSetData) -> ValidationResult:
        """
        Validate permission set data structure and content.

        Args:
            permission_set: PermissionSetData object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate required fields
        if not permission_set.permission_set_arn:
            errors.append("permission_set_arn is required and cannot be empty")
        elif not cls.PERMISSION_SET_ARN_PATTERN.match(permission_set.permission_set_arn):
            errors.append(
                f"permission_set_arn has invalid format: {permission_set.permission_set_arn}"
            )

        if not permission_set.name:
            errors.append("name is required and cannot be empty")
        elif len(permission_set.name) > 32:
            warnings.append("name is longer than recommended 32 characters")

        # Validate description
        if permission_set.description and len(permission_set.description) > 700:
            warnings.append("description is longer than recommended 700 characters")

        # Validate session duration format (ISO 8601 duration)
        if permission_set.session_duration:
            try:
                # Basic validation for ISO 8601 duration format
                if not permission_set.session_duration.startswith("PT"):
                    errors.append(
                        f"session_duration must be in ISO 8601 format: {permission_set.session_duration}"
                    )
            except Exception:
                errors.append(f"invalid session_duration format: {permission_set.session_duration}")

        # Validate inline policy (should be valid JSON)
        if permission_set.inline_policy:
            try:
                import json

                json.loads(permission_set.inline_policy)
            except json.JSONDecodeError as e:
                errors.append(f"inline_policy is not valid JSON: {e}")

        # Validate managed policies (should be ARNs)
        if permission_set.managed_policies:
            for policy_arn in permission_set.managed_policies:
                if not policy_arn.startswith("arn:aws:iam::"):
                    errors.append(f"invalid managed policy ARN format: {policy_arn}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "permission_set_arn",
                    "name",
                    "description",
                    "session_duration",
                    "inline_policy",
                    "managed_policies",
                ]
            },
        )

    @classmethod
    def validate_assignment_data(cls, assignment: AssignmentData) -> ValidationResult:
        """
        Validate assignment data structure and content.

        Args:
            assignment: AssignmentData object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Validate required fields
        if not assignment.account_id:
            errors.append("account_id is required and cannot be empty")
        elif not cls.ACCOUNT_ID_PATTERN.match(assignment.account_id):
            errors.append(f"account_id must be a 12-digit AWS account ID: {assignment.account_id}")

        if not assignment.permission_set_arn:
            errors.append("permission_set_arn is required and cannot be empty")
        elif not cls.PERMISSION_SET_ARN_PATTERN.match(assignment.permission_set_arn):
            errors.append(f"permission_set_arn has invalid format: {assignment.permission_set_arn}")

        if not assignment.principal_type:
            errors.append("principal_type is required and cannot be empty")
        elif assignment.principal_type not in ["USER", "GROUP"]:
            errors.append(f"principal_type must be 'USER' or 'GROUP': {assignment.principal_type}")

        if not assignment.principal_id:
            errors.append("principal_id is required and cannot be empty")
        elif assignment.principal_type == "USER" and not cls.USER_ID_PATTERN.match(
            assignment.principal_id
        ):
            errors.append(
                f"principal_id has invalid UUID format for USER: {assignment.principal_id}"
            )
        elif assignment.principal_type == "GROUP" and not cls.GROUP_ID_PATTERN.match(
            assignment.principal_id
        ):
            errors.append(
                f"principal_id has invalid UUID format for GROUP: {assignment.principal_id}"
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "account_id",
                    "permission_set_arn",
                    "principal_type",
                    "principal_id",
                ]
            },
        )

    @classmethod
    def validate_backup_data(cls, backup_data: BackupData) -> ValidationResult:
        """
        Validate complete backup data structure and integrity.

        Args:
            backup_data: BackupData object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        validated_items = {"users": 0, "groups": 0, "permission_sets": 0, "assignments": 0}

        # Validate metadata
        metadata_result = cls.validate_backup_metadata(backup_data.metadata)
        errors.extend(metadata_result.errors)
        warnings.extend(metadata_result.warnings)

        # Validate users
        user_ids = set()
        for user in backup_data.users:
            user_result = cls.validate_user_data(user)
            errors.extend([f"User {user.user_id}: {error}" for error in user_result.errors])
            warnings.extend([f"User {user.user_id}: {warning}" for warning in user_result.warnings])

            if user.user_id in user_ids:
                errors.append(f"Duplicate user_id found: {user.user_id}")
            user_ids.add(user.user_id)
            validated_items["users"] += 1

        # Validate groups
        group_ids = set()
        for group in backup_data.groups:
            group_result = cls.validate_group_data(group)
            errors.extend([f"Group {group.group_id}: {error}" for error in group_result.errors])
            warnings.extend(
                [f"Group {group.group_id}: {warning}" for warning in group_result.warnings]
            )

            if group.group_id in group_ids:
                errors.append(f"Duplicate group_id found: {group.group_id}")
            group_ids.add(group.group_id)

            # Validate group members exist
            for member_id in group.members:
                if member_id not in user_ids:
                    warnings.append(
                        f"Group {group.group_id} references non-existent user: {member_id}"
                    )

            validated_items["groups"] += 1

        # Validate permission sets
        permission_set_arns = set()
        for permission_set in backup_data.permission_sets:
            ps_result = cls.validate_permission_set_data(permission_set)
            errors.extend(
                [f"Permission Set {permission_set.name}: {error}" for error in ps_result.errors]
            )
            warnings.extend(
                [
                    f"Permission Set {permission_set.name}: {warning}"
                    for warning in ps_result.warnings
                ]
            )

            if permission_set.permission_set_arn in permission_set_arns:
                errors.append(
                    f"Duplicate permission_set_arn found: {permission_set.permission_set_arn}"
                )
            permission_set_arns.add(permission_set.permission_set_arn)
            validated_items["permission_sets"] += 1

        # Validate assignments
        assignment_keys = set()
        for assignment in backup_data.assignments:
            assignment_result = cls.validate_assignment_data(assignment)
            errors.extend(
                [
                    f"Assignment {assignment.account_id}/{assignment.permission_set_arn}: {error}"
                    for error in assignment_result.errors
                ]
            )
            warnings.extend(
                [
                    f"Assignment {assignment.account_id}/{assignment.permission_set_arn}: {warning}"
                    for warning in assignment_result.warnings
                ]
            )

            # Check for duplicate assignments
            assignment_key = (
                assignment.account_id,
                assignment.permission_set_arn,
                assignment.principal_type,
                assignment.principal_id,
            )
            if assignment_key in assignment_keys:
                errors.append(f"Duplicate assignment found: {assignment_key}")
            assignment_keys.add(assignment_key)

            # Validate references
            if assignment.permission_set_arn not in permission_set_arns:
                warnings.append(
                    f"Assignment references non-existent permission set: {assignment.permission_set_arn}"
                )

            if assignment.principal_type == "USER" and assignment.principal_id not in user_ids:
                warnings.append(
                    f"Assignment references non-existent user: {assignment.principal_id}"
                )
            elif assignment.principal_type == "GROUP" and assignment.principal_id not in group_ids:
                warnings.append(
                    f"Assignment references non-existent group: {assignment.principal_id}"
                )

            validated_items["assignments"] += 1

        # Verify integrity checksums
        if not backup_data.verify_integrity():
            errors.append("Backup data integrity verification failed - checksums do not match")

        # Validate resource counts match actual data
        expected_counts = backup_data.metadata.resource_counts
        for resource_type, expected_count in expected_counts.items():
            actual_count = validated_items.get(resource_type, 0)
            if expected_count != actual_count:
                errors.append(
                    f"Resource count mismatch for {resource_type}: expected {expected_count}, found {actual_count}"
                )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_items": validated_items,
                "total_errors": len(errors),
                "total_warnings": len(warnings),
            },
        )

    @classmethod
    def validate_retention_policy(cls, policy: RetentionPolicy) -> ValidationResult:
        """
        Validate retention policy configuration.

        Args:
            policy: RetentionPolicy object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate retention periods are non-negative
        if policy.keep_daily < 0:
            errors.append(f"keep_daily cannot be negative: {policy.keep_daily}")
        elif policy.keep_daily == 0:
            warnings.append("keep_daily is 0 - no daily backups will be retained")

        if policy.keep_weekly < 0:
            errors.append(f"keep_weekly cannot be negative: {policy.keep_weekly}")

        if policy.keep_monthly < 0:
            errors.append(f"keep_monthly cannot be negative: {policy.keep_monthly}")

        if policy.keep_yearly < 0:
            errors.append(f"keep_yearly cannot be negative: {policy.keep_yearly}")

        # Warn about very short retention periods
        if policy.keep_daily < 3:
            warnings.append(
                "keep_daily is less than 3 - consider keeping more daily backups for recovery"
            )

        # Warn about very long retention periods
        if policy.keep_yearly > 10:
            warnings.append("keep_yearly is greater than 10 - consider storage costs")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "keep_daily",
                    "keep_weekly",
                    "keep_monthly",
                    "keep_yearly",
                    "auto_cleanup",
                ]
            },
        )

    @classmethod
    def validate_encryption_metadata(cls, metadata: EncryptionMetadata) -> ValidationResult:
        """
        Validate encryption metadata configuration.

        Args:
            metadata: EncryptionMetadata object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate algorithm
        supported_algorithms = ["AES-256", "AES-128", "ChaCha20-Poly1305"]
        if metadata.algorithm not in supported_algorithms:
            errors.append(f"unsupported encryption algorithm: {metadata.algorithm}")

        # Validate key_id format (basic validation)
        if metadata.key_id and len(metadata.key_id) < 8:
            errors.append("key_id appears to be too short")

        # Validate IV format (basic validation)
        if metadata.iv and len(metadata.iv) < 16:
            errors.append("initialization vector appears to be too short")

        # Warn about unencrypted data
        if not metadata.encrypted:
            warnings.append(
                "backup data is not encrypted - consider enabling encryption for security"
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={"validated_fields": ["algorithm", "key_id", "iv", "encrypted"]},
        )

    @classmethod
    def validate_schedule_config(cls, config: ScheduleConfig) -> ValidationResult:
        """
        Validate schedule configuration.

        Args:
            config: ScheduleConfig object to validate

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # Validate name
        if not config.name:
            errors.append("schedule name is required and cannot be empty")
        elif len(config.name) > 128:
            warnings.append("schedule name is longer than recommended 128 characters")

        # Validate backup type
        if config.backup_type not in BackupType:
            errors.append(f"invalid backup_type: {config.backup_type}")

        # Validate interval (cron expression or predefined)
        predefined_intervals = ["daily", "weekly", "monthly"]
        if config.interval not in predefined_intervals:
            # Try to validate as cron expression
            if not cls.CRON_PATTERN.match(config.interval):
                errors.append(
                    f"invalid interval format - must be cron expression or one of {predefined_intervals}: {config.interval}"
                )

        # Validate retention policy
        retention_result = cls.validate_retention_policy(config.retention_policy)
        errors.extend(retention_result.errors)
        warnings.extend(retention_result.warnings)

        # Validate notification settings
        if config.notification_settings.enabled:
            if (
                not config.notification_settings.email_addresses
                and not config.notification_settings.webhook_urls
            ):
                warnings.append(
                    "notifications are enabled but no email addresses or webhook URLs are configured"
                )

            for email in config.notification_settings.email_addresses:
                if not cls.EMAIL_PATTERN.match(email):
                    errors.append(f"invalid email address format: {email}")

        # Validate backup options if provided
        if config.backup_options:
            options_result = cls.validate_backup_options(config.backup_options)
            errors.extend(options_result.errors)
            warnings.extend(options_result.warnings)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "validated_fields": [
                    "name",
                    "backup_type",
                    "interval",
                    "retention_policy",
                    "notification_settings",
                    "backup_options",
                ]
            },
        )


class BackupValidator:
    """
    Specialized validator for backup operations and data integrity.

    This class provides high-level validation methods specifically designed
    for backup operations, building on the DataValidator foundation.
    """

    def __init__(self):
        """Initialize backup validator."""
        self.data_validator = DataValidator()

    async def validate_backup_data(self, backup_data: BackupData) -> ValidationResult:
        """
        Validate complete backup data for integrity and consistency.

        Args:
            backup_data: BackupData object to validate

        Returns:
            ValidationResult with comprehensive validation status
        """
        return self.data_validator.validate_backup_data(backup_data)

    async def validate_backup_options(self, options: BackupOptions) -> ValidationResult:
        """
        Validate backup options before starting backup operation.

        Args:
            options: BackupOptions object to validate

        Returns:
            ValidationResult with validation status
        """
        return self.data_validator.validate_backup_options(options)

    async def validate_backup_metadata(self, metadata: BackupMetadata) -> ValidationResult:
        """
        Validate backup metadata structure and content.

        Args:
            metadata: BackupMetadata object to validate

        Returns:
            ValidationResult with validation status
        """
        return self.data_validator.validate_backup_metadata(metadata)

    async def validate_backup_consistency(self, backup_data: BackupData) -> ValidationResult:
        """
        Perform advanced consistency checks on backup data.

        This method performs cross-reference validation and business logic checks
        beyond basic data structure validation.

        Args:
            backup_data: BackupData object to validate

        Returns:
            ValidationResult with consistency validation status
        """
        errors = []
        warnings = []
        details = {}

        try:
            # Check referential integrity
            user_ids = {user.user_id for user in backup_data.users}
            group_ids = {group.group_id for group in backup_data.groups}
            permission_set_arns = {ps.permission_set_arn for ps in backup_data.permission_sets}

            # Validate group memberships
            orphaned_memberships = 0
            for group in backup_data.groups:
                for member_id in group.members:
                    if member_id not in user_ids:
                        orphaned_memberships += 1

            if orphaned_memberships > 0:
                warnings.append(
                    f"Found {orphaned_memberships} group memberships referencing non-existent users"
                )

            # Validate assignments
            orphaned_assignments = 0
            invalid_principals = 0

            for assignment in backup_data.assignments:
                # Check permission set exists
                if assignment.permission_set_arn not in permission_set_arns:
                    orphaned_assignments += 1

                # Check principal exists
                if assignment.principal_type == "USER" and assignment.principal_id not in user_ids:
                    invalid_principals += 1
                elif (
                    assignment.principal_type == "GROUP"
                    and assignment.principal_id not in group_ids
                ):
                    invalid_principals += 1

            if orphaned_assignments > 0:
                warnings.append(
                    f"Found {orphaned_assignments} assignments referencing non-existent permission sets"
                )

            if invalid_principals > 0:
                warnings.append(
                    f"Found {invalid_principals} assignments referencing non-existent principals"
                )

            # Check for circular group memberships (if groups can be members of other groups)
            # This is a placeholder for more complex validation logic

            # Validate backup completeness
            total_resources = (
                len(backup_data.users)
                + len(backup_data.groups)
                + len(backup_data.permission_sets)
                + len(backup_data.assignments)
            )
            if total_resources == 0:
                warnings.append(
                    "Backup contains no resources - this may indicate a collection issue"
                )

            # Check metadata consistency
            metadata_counts = backup_data.metadata.resource_counts
            actual_counts = {
                "users": len(backup_data.users),
                "groups": len(backup_data.groups),
                "permission_sets": len(backup_data.permission_sets),
                "assignments": len(backup_data.assignments),
            }

            for resource_type, expected_count in metadata_counts.items():
                actual_count = actual_counts.get(resource_type, 0)
                if expected_count != actual_count:
                    errors.append(
                        f"Metadata count mismatch for {resource_type}: expected {expected_count}, actual {actual_count}"
                    )

            details.update(
                {
                    "total_resources": total_resources,
                    "orphaned_memberships": orphaned_memberships,
                    "orphaned_assignments": orphaned_assignments,
                    "invalid_principals": invalid_principals,
                    "resource_counts": actual_counts,
                }
            )

        except Exception as e:
            errors.append(f"Consistency validation failed: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    async def validate_incremental_backup(
        self, backup_data: BackupData, base_backup_data: BackupData
    ) -> ValidationResult:
        """
        Validate incremental backup against its base backup.

        Args:
            backup_data: Incremental backup data to validate
            base_backup_data: Base backup data for comparison

        Returns:
            ValidationResult with incremental validation status
        """
        errors = []
        warnings = []
        details = {}

        try:
            # Validate that this is indeed an incremental backup
            if backup_data.metadata.backup_type != BackupType.INCREMENTAL:
                errors.append("Backup is not marked as incremental type")

            # Check timestamp ordering
            if backup_data.metadata.timestamp <= base_backup_data.metadata.timestamp:
                errors.append("Incremental backup timestamp is not after base backup timestamp")

            # Validate instance consistency
            if backup_data.metadata.instance_arn != base_backup_data.metadata.instance_arn:
                errors.append("Incremental backup instance ARN does not match base backup")

            # Check for resource changes (this is a simplified check)
            base_user_ids = {user.user_id for user in base_backup_data.users}
            incremental_user_ids = {user.user_id for user in backup_data.users}

            new_users = incremental_user_ids - base_user_ids
            if len(new_users) > 0:
                details["new_users"] = len(new_users)

            # Similar checks for other resource types
            base_group_ids = {group.group_id for group in base_backup_data.groups}
            incremental_group_ids = {group.group_id for group in backup_data.groups}
            new_groups = incremental_group_ids - base_group_ids
            if len(new_groups) > 0:
                details["new_groups"] = len(new_groups)

            # Check if incremental backup is empty (no changes)
            total_incremental_resources = (
                len(backup_data.users)
                + len(backup_data.groups)
                + len(backup_data.permission_sets)
                + len(backup_data.assignments)
            )
            if total_incremental_resources == 0:
                warnings.append(
                    "Incremental backup contains no resources - no changes detected since base backup"
                )

            details["total_incremental_resources"] = total_incremental_resources

        except Exception as e:
            errors.append(f"Incremental validation failed: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )
