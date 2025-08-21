"""
Unit tests for permission cloning data models.

Tests all data models, enums, and validation methods.
"""

from src.awsideman.permission_cloning.models import (
    CloneResult,
    CopyFilters,
    CopyResult,
    CustomerManagedPolicy,
    EntityReference,
    EntityType,
    PermissionAssignment,
    PermissionSetConfig,
    ValidationResult,
    ValidationResultType,
)


class TestEntityType:
    """Test EntityType enum."""

    def test_entity_type_values(self):
        """Test that EntityType has correct values."""
        assert EntityType.USER.value == "USER"
        assert EntityType.GROUP.value == "GROUP"

    def test_entity_type_membership(self):
        """Test EntityType membership."""
        assert EntityType.USER in EntityType
        assert EntityType.GROUP in EntityType


class TestValidationResultType:
    """Test ValidationResultType enum."""

    def test_validation_result_type_values(self):
        """Test that ValidationResultType has correct values."""
        assert ValidationResultType.SUCCESS.value == "SUCCESS"
        assert ValidationResultType.ERROR.value == "ERROR"
        assert ValidationResultType.WARNING.value == "WARNING"


class TestCustomerManagedPolicy:
    """Test CustomerManagedPolicy data model."""

    def test_valid_customer_managed_policy(self):
        """Test valid customer managed policy."""
        policy = CustomerManagedPolicy(name="TestPolicy", path="/test/")
        result = policy.validate()
        assert result.is_valid
        assert not result.has_errors

    def test_empty_policy_name(self):
        """Test validation with empty policy name."""
        policy = CustomerManagedPolicy(name="", path="/test/")
        result = policy.validate()
        assert result.has_errors
        assert "Policy name cannot be empty" in result.messages

    def test_invalid_policy_name_characters(self):
        """Test validation with invalid characters in policy name."""
        policy = CustomerManagedPolicy(name="Test Policy!", path="/test/")
        result = policy.validate()
        assert result.has_errors
        assert "Policy name contains invalid characters" in result.messages

    def test_empty_policy_path(self):
        """Test validation with empty policy path."""
        policy = CustomerManagedPolicy(name="TestPolicy", path="")
        result = policy.validate()
        assert result.has_errors
        assert "Policy path cannot be empty" in result.messages

    def test_invalid_policy_path_format(self):
        """Test validation with invalid policy path format."""
        policy = CustomerManagedPolicy(name="TestPolicy", path="test/")
        result = policy.validate()
        assert result.has_errors
        assert "Policy path must start with '/'" in result.messages

        policy = CustomerManagedPolicy(name="TestPolicy", path="/test")
        result = policy.validate()
        assert result.has_errors
        assert "Policy path must end with '/'" in result.messages


class TestEntityReference:
    """Test EntityReference data model."""

    def test_valid_user_entity(self):
        """Test valid user entity reference."""
        entity = EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="test.user@example.com",
        )
        result = entity.validate()
        assert result.is_valid

    def test_valid_group_entity(self):
        """Test valid group entity reference."""
        entity = EntityReference(
            entity_type=EntityType.GROUP,
            entity_id="87654321-4321-4321-4321-210987654321",
            entity_name="TestGroup",
        )
        result = entity.validate()
        assert result.is_valid

    def test_invalid_entity_id_format(self):
        """Test validation with invalid entity ID format."""
        entity = EntityReference(
            entity_type=EntityType.USER, entity_id="invalid-id", entity_name="test.user@example.com"
        )
        result = entity.validate()
        assert result.has_errors
        assert "Entity ID must be a valid UUID format" in result.messages

    def test_empty_entity_name(self):
        """Test validation with empty entity name."""
        entity = EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="",
        )
        result = entity.validate()
        assert result.has_errors
        assert "Entity name cannot be empty" in result.messages


class TestPermissionAssignment:
    """Test PermissionAssignment data model."""

    def test_valid_permission_assignment(self):
        """Test valid permission assignment."""
        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890123456/ps-abcdef1234567890",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
        )
        result = assignment.validate()
        assert result.is_valid

    def test_valid_assignment_without_account_name(self):
        """Test valid permission assignment without account name."""
        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890123456/ps-abcdef1234567890",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
        )
        result = assignment.validate()
        assert result.is_valid

    def test_invalid_permission_set_arn(self):
        """Test validation with invalid permission set ARN."""
        assignment = PermissionAssignment(
            permission_set_arn="invalid-arn",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
        )
        result = assignment.validate()
        assert result.has_errors
        assert "Permission set ARN format is invalid" in result.messages

    def test_empty_permission_set_name(self):
        """Test validation with empty permission set name."""
        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890123456/ps-abcdef1234567890",
            permission_set_name="",
            account_id="123456789012",
        )
        result = assignment.validate()
        assert result.has_errors
        assert "Permission set name cannot be empty" in result.messages

    def test_invalid_account_id(self):
        """Test validation with invalid account ID."""
        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890123456/ps-abcdef1234567890",
            permission_set_name="TestPermissionSet",
            account_id="invalid-account",
        )
        result = assignment.validate()
        assert result.has_errors
        assert "Account ID must be a 12-digit number" in result.messages


class TestPermissionSetConfig:
    """Test PermissionSetConfig data model."""

    def test_valid_permission_set_config(self):
        """Test valid permission set configuration."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="Test permission set description",
            session_duration="PT1H",
            relay_state_url="https://example.com/relay",
            aws_managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            customer_managed_policies=[CustomerManagedPolicy(name="TestPolicy", path="/test/")],
            inline_policy='{"Version": "2012-10-17", "Statement": []}',
        )
        result = config.validate()
        assert result.is_valid

    def test_minimal_valid_config(self):
        """Test minimal valid permission set configuration."""
        config = PermissionSetConfig(
            name="TestPermissionSet", description="Test description", session_duration="PT1H"
        )
        result = config.validate()
        # Should have warning about no policies
        assert result.has_warnings
        assert "Permission set has no policies defined" in result.messages

    def test_empty_name(self):
        """Test validation with empty name."""
        config = PermissionSetConfig(
            name="", description="Test description", session_duration="PT1H"
        )
        result = config.validate()
        assert result.has_errors
        assert "Permission set name cannot be empty" in result.messages

    def test_name_too_long(self):
        """Test validation with name too long."""
        config = PermissionSetConfig(
            name="a" * 33,  # 33 characters, exceeds 32 limit
            description="Test description",
            session_duration="PT1H",
        )
        result = config.validate()
        assert result.has_errors
        assert "Permission set name cannot exceed 32 characters" in result.messages

    def test_invalid_name_characters(self):
        """Test validation with invalid characters in name."""
        config = PermissionSetConfig(
            name="Test Permission Set!", description="Test description", session_duration="PT1H"
        )
        result = config.validate()
        assert result.has_errors
        assert "Permission set name contains invalid characters" in result.messages

    def test_empty_description(self):
        """Test validation with empty description."""
        config = PermissionSetConfig(
            name="TestPermissionSet", description="", session_duration="PT1H"
        )
        result = config.validate()
        assert result.has_errors
        assert "Permission set description cannot be empty" in result.messages

    def test_description_too_long(self):
        """Test validation with description too long."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="a" * 701,  # 701 characters, exceeds 700 limit
            session_duration="PT1H",
        )
        result = config.validate()
        assert result.has_errors
        assert "Permission set description cannot exceed 700 characters" in result.messages

    def test_invalid_session_duration(self):
        """Test validation with invalid session duration."""
        config = PermissionSetConfig(
            name="TestPermissionSet", description="Test description", session_duration="1 hour"
        )
        result = config.validate()
        assert result.has_errors
        assert (
            "Session duration must be in ISO 8601 format (e.g., PT1H, PT2H30M)" in result.messages
        )

    def test_valid_session_duration_formats(self):
        """Test validation with various valid session duration formats."""
        valid_durations = ["PT1H", "PT2H", "PT30M", "PT1H30M", "PT12H"]

        for duration in valid_durations:
            config = PermissionSetConfig(
                name="TestPermissionSet", description="Test description", session_duration=duration
            )
            result = config.validate()
            assert not result.has_errors, f"Duration {duration} should be valid"

    def test_invalid_relay_state_url(self):
        """Test validation with invalid relay state URL."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            relay_state_url="a" * 241,  # 241 characters, exceeds 240 limit
        )
        result = config.validate()
        assert result.has_errors
        assert "Relay state URL cannot exceed 240 characters" in result.messages

    def test_relay_state_url_warning(self):
        """Test validation warning for relay state URL without protocol."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            relay_state_url="example.com/relay",
        )
        result = config.validate()
        assert result.has_warnings
        assert "Relay state URL should start with http:// or https://" in result.messages

    def test_invalid_aws_managed_policy(self):
        """Test validation with invalid AWS managed policy ARN."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            aws_managed_policies=["invalid-policy-arn"],
        )
        result = config.validate()
        assert result.has_errors
        assert "Invalid AWS managed policy ARN: invalid-policy-arn" in result.messages

    def test_inline_policy_too_large(self):
        """Test validation with inline policy too large."""
        config = PermissionSetConfig(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            inline_policy="a" * 32769,  # 32769 characters, exceeds 32KB limit
        )
        result = config.validate()
        assert result.has_errors
        assert "Inline policy cannot exceed 32KB" in result.messages


class TestCopyFilters:
    """Test CopyFilters data model."""

    def test_valid_filters(self):
        """Test valid copy filters."""
        filters = CopyFilters(
            exclude_permission_sets=["PermissionSet3"],
            include_accounts=["123456789012", "123456789013"],
            exclude_accounts=["123456789014"],
        )
        result = filters.validate()
        assert result.is_valid

    def test_empty_filters_warning(self):
        """Test validation warning with empty filters."""
        filters = CopyFilters()
        result = filters.validate()
        assert result.has_warnings
        assert "No filters specified - all assignments will be processed" in result.messages

    def test_overlapping_permission_sets(self):
        """Test validation error with overlapping permission sets."""
        # Since CopyFilters no longer supports include_permission_sets,
        # we test overlapping accounts instead
        filters = CopyFilters(
            include_accounts=["123456789012", "123456789013"],
            exclude_accounts=["123456789013", "123456789014"],
        )
        result = filters.validate()
        assert result.has_errors
        assert "Accounts cannot be both included and excluded" in result.messages[0]
        assert "123456789013" in result.messages[0]

    def test_overlapping_accounts(self):
        """Test validation error with overlapping accounts."""
        filters = CopyFilters(
            include_accounts=["123456789012", "123456789013"],
            exclude_accounts=["123456789013", "123456789014"],
        )
        result = filters.validate()
        assert result.has_errors
        assert "Accounts cannot be both included and excluded" in result.messages[0]
        assert "123456789013" in result.messages[0]

    def test_invalid_account_id_in_include(self):
        """Test validation error with invalid account ID in include filter."""
        filters = CopyFilters(include_accounts=["invalid-account"])
        result = filters.validate()
        assert result.has_errors
        assert "Invalid account ID in include filter: invalid-account" in result.messages

    def test_invalid_account_id_in_exclude(self):
        """Test validation error with invalid account ID in exclude filter."""
        filters = CopyFilters(exclude_accounts=["invalid-account"])
        result = filters.validate()
        assert result.has_errors
        assert "Invalid account ID in exclude filter: invalid-account" in result.messages


class TestCopyResult:
    """Test CopyResult data model."""

    def test_valid_copy_result(self):
        """Test valid copy result."""
        source = EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="source.user@example.com",
        )
        target = EntityReference(
            entity_type=EntityType.USER,
            entity_id="87654321-4321-4321-4321-210987654321",
            entity_name="target.user@example.com",
        )
        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890123456/ps-abcdef1234567890",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
        )

        result = CopyResult(
            source=source,
            target=target,
            assignments_copied=[assignment],
            assignments_skipped=[],
            rollback_id="rollback-123",
            success=True,
        )
        validation = result.validate()
        assert validation.is_valid

    def test_failed_result_without_error_message(self):
        """Test validation error for failed result without error message."""
        source = EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="source.user@example.com",
        )
        target = EntityReference(
            entity_type=EntityType.USER,
            entity_id="87654321-4321-4321-4321-210987654321",
            entity_name="target.user@example.com",
        )

        result = CopyResult(
            source=source,
            target=target,
            assignments_copied=[],
            assignments_skipped=[],
            success=False,
        )
        validation = result.validate()
        assert validation.has_errors
        assert "Failed operations must include an error message" in validation.messages

    def test_successful_result_with_error_message(self):
        """Test validation error for successful result with error message."""
        source = EntityReference(
            entity_type=EntityType.USER,
            entity_id="12345678-1234-1234-1234-123456789012",
            entity_name="source.user@example.com",
        )
        target = EntityReference(
            entity_type=EntityType.USER,
            entity_id="87654321-4321-4321-4321-210987654321",
            entity_name="target.user@example.com",
        )

        result = CopyResult(
            source=source,
            target=target,
            assignments_copied=[],
            assignments_skipped=[],
            success=True,
            error_message="This shouldn't be here",
        )
        validation = result.validate()
        assert validation.has_errors
        assert "Successful operations should not have error messages" in validation.messages


class TestCloneResult:
    """Test CloneResult data model."""

    def test_valid_clone_result(self):
        """Test valid clone result."""
        config = PermissionSetConfig(
            name="ClonedPermissionSet", description="Cloned permission set", session_duration="PT1H"
        )

        result = CloneResult(
            source_name="SourcePermissionSet",
            target_name="ClonedPermissionSet",
            cloned_config=config,
            rollback_id="rollback-456",
            success=True,
        )
        validation = result.validate()
        # Should have warning about no policies in config
        assert not validation.has_errors

    def test_empty_source_name(self):
        """Test validation error with empty source name."""
        result = CloneResult(source_name="", target_name="ClonedPermissionSet", success=True)
        validation = result.validate()
        assert validation.has_errors
        assert "Source permission set name cannot be empty" in validation.messages

    def test_empty_target_name(self):
        """Test validation error with empty target name."""
        result = CloneResult(source_name="SourcePermissionSet", target_name="", success=True)
        validation = result.validate()
        assert validation.has_errors
        assert "Target permission set name cannot be empty" in validation.messages

    def test_successful_result_without_config(self):
        """Test validation error for successful result without cloned config."""
        result = CloneResult(
            source_name="SourcePermissionSet", target_name="ClonedPermissionSet", success=True
        )
        validation = result.validate()
        assert validation.has_errors
        assert (
            "Successful clone operations must include cloned configuration" in validation.messages
        )


class TestValidationResult:
    """Test ValidationResult data model."""

    def test_success_validation_result(self):
        """Test success validation result properties."""
        result = ValidationResult(ValidationResultType.SUCCESS, [])
        assert result.is_valid
        assert not result.has_errors
        assert not result.has_warnings

    def test_error_validation_result(self):
        """Test error validation result properties."""
        result = ValidationResult(ValidationResultType.ERROR, ["Error message"])
        assert not result.is_valid
        assert result.has_errors
        assert not result.has_warnings

    def test_warning_validation_result(self):
        """Test warning validation result properties."""
        result = ValidationResult(ValidationResultType.WARNING, ["Warning message"])
        assert not result.is_valid  # Warnings are not considered valid
        assert not result.has_errors
        assert result.has_warnings
