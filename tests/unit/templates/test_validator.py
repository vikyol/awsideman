"""
Unit tests for the TemplateValidator class.

Tests template validation functionality including structure validation,
entity resolution, permission set validation, and account validation.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.awsideman.permission_cloning.models import EntityReference, EntityType
from src.awsideman.templates.models import (
    Template,
    TemplateAssignment,
    TemplateMetadata,
    TemplateTarget,
)
from src.awsideman.templates.validator import TemplateValidator, ValidationResult


class TestValidationResult:
    """Test cases for ValidationResult class."""

    def test_init_success(self):
        """Test successful validation result initialization."""
        result = ValidationResult(
            is_valid=True, errors=[], warnings=[], resolved_entities={}, resolved_accounts=[]
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_init_failure(self):
        """Test failed validation result initialization."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
            resolved_entities={},
            resolved_accounts=[],
        )

        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_post_init_sets_is_valid(self):
        """Test that post_init sets is_valid based on errors."""
        result = ValidationResult(
            is_valid=None,  # Not set initially
            errors=["Error 1"],  # Has errors
            warnings=[],
            resolved_entities={},
            resolved_accounts=[],
        )

        # The post_init method should set is_valid to False when there are errors
        assert result.is_valid is False

    def test_add_error(self):
        """Test adding error messages."""
        result = ValidationResult(
            is_valid=True, errors=[], warnings=[], resolved_entities={}, resolved_accounts=[]
        )

        result.add_error("New error")

        assert len(result.errors) == 1
        assert "New error" in result.errors
        assert result.is_valid is False

    def test_add_warning(self):
        """Test adding warning messages."""
        result = ValidationResult(
            is_valid=True, errors=[], warnings=[], resolved_entities={}, resolved_accounts=[]
        )

        result.add_warning("New warning")

        assert len(result.warnings) == 1
        assert "New warning" in result.warnings
        assert result.is_valid is True  # Warnings don't affect validity

    def test_merge(self):
        """Test merging validation results."""
        result1 = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Warning 1"],
            resolved_entities={"user:john": MagicMock()},
            resolved_accounts=["123456789012"],
        )

        result2 = ValidationResult(
            is_valid=False,
            errors=["Error 1"],
            warnings=["Warning 2"],
            resolved_entities={"group:devs": MagicMock()},
            resolved_accounts=["234567890123"],
        )

        result1.merge(result2)

        assert len(result1.errors) == 1
        assert len(result1.warnings) == 2
        assert len(result1.resolved_entities) == 2
        assert len(result1.resolved_accounts) == 2
        assert result1.is_valid is False


class TestTemplateValidator:
    """Test cases for TemplateValidator class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        from src.awsideman.aws_clients.manager import AWSClientManager

        manager = MagicMock(spec=AWSClientManager)
        manager.get_identity_center_client.return_value = MagicMock()
        manager.get_identity_store_client.return_value = MagicMock()
        manager.get_organizations_client.return_value = MagicMock()
        return manager

    @pytest.fixture
    def validator(self, mock_client_manager):
        """Create a TemplateValidator instance with mocked dependencies."""
        return TemplateValidator(
            client_manager=mock_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890abcdef",
        )

    @pytest.fixture
    def sample_template(self):
        """Create a sample template for testing."""
        metadata = TemplateMetadata(
            name="test-template", description="Test template", version="1.0", author="Test Author"
        )
        targets = TemplateTarget(account_ids=["123456789012", "234567890123"])
        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )
        return Template(metadata=metadata, assignments=[assignment])

    @pytest.fixture
    def mock_entity_resolver(self):
        """Create a mock entity resolver."""
        resolver = MagicMock()
        resolver.resolve_entity_by_name.return_value = EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
        )
        return resolver

    @pytest.fixture
    def mock_identity_center_client(self):
        """Create a mock Identity Center client."""
        client = MagicMock()
        client.list_permission_sets.return_value = {
            "PermissionSetArns": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            ]
        }
        client.describe_permission_set.return_value = {"PermissionSet": {"Name": "DeveloperAccess"}}
        return client

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock Organizations client."""
        client = MagicMock()
        client.list_accounts.return_value = {
            "Accounts": [
                {"Id": "123456789012", "Name": "Test Account 1", "Status": "ACTIVE"},
                {"Id": "234567890123", "Name": "Test Account 2", "Status": "ACTIVE"},
            ]
        }
        client.list_tags_for_resource.return_value = {"Tags": []}
        return client

    def test_init(self, mock_client_manager):
        """Test validator initialization."""
        validator = TemplateValidator(
            client_manager=mock_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890abcdef",
        )

        assert validator.client_manager == mock_client_manager
        assert validator.instance_arn == "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        assert validator.identity_store_id == "d-1234567890abcdef"

    def test_entity_resolver_property(self, validator):
        """Test entity resolver property creation."""
        with patch(
            "src.awsideman.permission_cloning.entity_resolver.EntityResolver"
        ) as mock_entity_resolver_class:
            mock_resolver = MagicMock()
            mock_entity_resolver_class.return_value = mock_resolver

            result = validator.entity_resolver

            assert result == mock_resolver
            mock_entity_resolver_class.assert_called_once()

    def test_identity_center_client_property(self, validator):
        """Test Identity Center client property."""
        mock_client = MagicMock()
        validator.client_manager.get_identity_center_client.return_value = mock_client

        result = validator.identity_center_client

        assert result == mock_client
        validator.client_manager.get_identity_center_client.assert_called_once()

    def test_organizations_client_property(self, validator):
        """Test Organizations client property."""
        mock_client = MagicMock()
        validator.client_manager.get_organizations_client.return_value = mock_client

        result = validator.organizations_client

        assert result == mock_client
        validator.client_manager.get_organizations_client.assert_called_once()

    def test_validate_template_success(self, validator, sample_template):
        """Test successful template validation."""
        with patch.object(validator, "validate_structure", return_value=[]):
            with patch.object(validator, "validate_entities", return_value=[]):
                with patch.object(validator, "validate_permission_sets", return_value=[]):
                    with patch.object(validator, "validate_accounts", return_value=[]):
                        result = validator.validate_template(sample_template)

                        assert isinstance(result, ValidationResult)
                        assert result.is_valid is True
                        assert len(result.errors) == 0

    def test_validate_template_structure_errors(self, validator, sample_template):
        """Test template validation with structure errors."""
        with patch.object(validator, "validate_structure", return_value=["Structure error"]):
            with patch.object(validator, "validate_entities", return_value=[]):
                with patch.object(validator, "validate_permission_sets", return_value=[]):
                    with patch.object(validator, "validate_accounts", return_value=[]):
                        result = validator.validate_template(sample_template)

                        assert result.is_valid is False
                        assert len(result.errors) == 1
                        assert "Structure error" in result.errors

    def test_validate_template_entity_errors(self, validator, sample_template):
        """Test template validation with entity errors."""
        with patch.object(validator, "validate_structure", return_value=[]):
            with patch.object(validator, "validate_entities", return_value=["Entity not found"]):
                with patch.object(validator, "validate_permission_sets", return_value=[]):
                    with patch.object(validator, "validate_accounts", return_value=[]):
                        result = validator.validate_template(sample_template)

                        assert result.is_valid is False
                        assert len(result.errors) == 1
                        assert "Entity not found" in result.errors

    def test_validate_structure_valid(self, validator, sample_template):
        """Test structure validation with valid template."""
        result = validator.validate_structure(sample_template)

        assert len(result) == 0

    def test_validate_structure_missing_name(self, validator):
        """Test structure validation with missing template name."""
        metadata = TemplateMetadata(name="")  # Empty name
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        result = validator.validate_structure(template)

        assert len(result) == 1
        assert "Template name is required" in result[0]

    def test_validate_structure_no_assignments(self, validator):
        """Test structure validation with no assignments."""
        metadata = TemplateMetadata(name="test-template")
        # Create a template with a minimal assignment to avoid the post_init error
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        # Now remove the assignment to test the validation
        template.assignments = []

        result = validator.validate_structure(template)

        assert len(result) == 1
        assert "At least one assignment must be specified" in result[0]

    def test_validate_entities_success(self, validator, sample_template):
        """Test successful entity validation."""
        with patch.object(validator, "_parse_entity_reference", return_value=("user", "john.doe")):
            # Mock the entity resolver property by setting the private attribute
            mock_resolver = MagicMock()
            mock_resolver.resolve_entity_by_name.return_value = EntityReference(
                entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
            )
            validator._entity_resolver = mock_resolver

            result = validator.validate_entities(sample_template)

            assert len(result) == 0

    def test_validate_entities_not_found(self, validator, sample_template):
        """Test entity validation with entity not found."""
        with patch.object(validator, "_parse_entity_reference", return_value=("user", "john.doe")):
            # Mock the entity resolver property by setting the private attribute
            mock_resolver = MagicMock()
            mock_resolver.resolve_entity_by_name.return_value = None
            validator._entity_resolver = mock_resolver

            result = validator.validate_entities(sample_template)

            assert len(result) == 2  # 2 entities in template
            assert "Entity not found: user:john.doe" in result[0]
            assert "Entity not found: group:developers" in result[1]

    def test_validate_entities_invalid_reference(self, validator, sample_template):
        """Test entity validation with invalid entity reference."""
        with patch.object(
            validator, "_parse_entity_reference", side_effect=ValueError("Invalid format")
        ):
            result = validator.validate_entities(sample_template)

            assert len(result) == 2
            assert "Invalid entity reference 'user:john.doe': Invalid format" in result[0]

    def test_validate_permission_sets_success(self, validator, sample_template):
        """Test successful permission set validation."""
        mock_client = MagicMock()
        mock_client.list_permission_sets.return_value = {
            "PermissionSetArns": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-234567890123456789",
            ]
        }
        # Mock the describe_permission_set to return different names for each call
        mock_client.describe_permission_set.side_effect = [
            {"PermissionSet": {"Name": "DeveloperAccess"}},
            {"PermissionSet": {"Name": "ReadOnlyAccess"}},
        ]
        validator._identity_center_client = mock_client

        result = validator.validate_permission_sets(sample_template)

        assert len(result) == 0

    def test_validate_permission_sets_not_found(self, validator, sample_template):
        """Test permission set validation with permission set not found."""
        mock_client = MagicMock()
        mock_client.list_permission_sets.return_value = {
            "PermissionSetArns": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            ]
        }
        mock_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "DifferentName"}
        }
        validator._identity_center_client = mock_client

        result = validator.validate_permission_sets(sample_template)

        assert len(result) == 2  # Both permission sets not found
        assert "Permission set not found: DeveloperAccess" in result[0]
        assert "Permission set not found: ReadOnlyAccess" in result[1]

    def test_validate_permission_sets_api_error(self, validator, sample_template):
        """Test permission set validation with API error."""
        mock_client = MagicMock()
        mock_client.list_permission_sets.side_effect = Exception("API error")
        validator._identity_center_client = mock_client

        result = validator.validate_permission_sets(sample_template)

        assert len(result) == 1
        assert "Failed to validate permission sets: API error" in result[0]

    def test_validate_accounts_success(self, validator, sample_template):
        """Test successful account validation."""
        result = validator.validate_accounts(sample_template)

        assert len(result) == 0

    def test_validate_accounts_invalid_format(self, validator):
        """Test account validation with invalid account ID format."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["invalid-id", "123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        result = validator.validate_accounts(template)

        assert len(result) == 1
        assert "Invalid account ID format: invalid-id" in result[0]

    def test_validate_accounts_invalid_tags(self, validator):
        """Test account validation with invalid tags."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_tags={"": "value", "key": ""})  # Invalid tags
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        result = validator.validate_accounts(template)

        assert len(result) == 2
        assert "Invalid tag: =value" in result[0]
        assert "Invalid tag: key=" in result[1]

    def test_validate_accounts_invalid_exclude(self, validator):
        """Test account validation with invalid exclude account IDs."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"], exclude_accounts=["invalid-exclude"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        result = validator.validate_accounts(template)

        assert len(result) == 1
        assert "Invalid exclude account ID format: invalid-exclude" in result[0]

    def test_parse_entity_reference_valid(self, validator):
        """Test valid entity reference parsing."""
        result = validator._parse_entity_reference("user:john.doe")
        assert result == ("user", "john.doe")

    def test_parse_entity_reference_invalid_format(self, validator):
        """Test invalid entity reference format."""
        with pytest.raises(ValueError, match="Entity reference must be in format 'type:name'"):
            validator._parse_entity_reference("invalid-format")

    def test_parse_entity_reference_invalid_type(self, validator):
        """Test invalid entity type."""
        with pytest.raises(ValueError, match="Entity type must be 'user' or 'group'"):
            validator._parse_entity_reference("role:admin")

    def test_parse_entity_reference_empty_name(self, validator):
        """Test entity reference with empty name."""
        with pytest.raises(ValueError, match="Entity name cannot be empty"):
            validator._parse_entity_reference("user:")

    def test_is_valid_account_id_valid(self, validator):
        """Test valid account ID validation."""
        assert validator._is_valid_account_id("123456789012") is True
        assert validator._is_valid_account_id("000000000000") is True

    def test_is_valid_account_id_invalid(self, validator):
        """Test invalid account ID validation."""
        assert validator._is_valid_account_id("12345678901") is False  # Too short
        assert validator._is_valid_account_id("1234567890123") is False  # Too long
        assert validator._is_valid_account_id("12345678901a") is False  # Non-numeric
        assert validator._is_valid_account_id("") is False  # Empty

    def test_get_resolved_entities(self, validator):
        """Test getting resolved entities."""
        # Set up some resolved entities
        validator._resolved_entities = {
            "user:john.doe": EntityReference(EntityType.USER, "user-123", "john.doe"),
            "group:developers": EntityReference(EntityType.GROUP, "group-456", "developers"),
        }

        result = validator.get_resolved_entities()

        assert len(result) == 2
        assert "user:john.doe" in result
        assert "group:developers" in result

    def test_get_resolved_accounts_success(self, validator, sample_template):
        """Test successful account resolution."""
        with patch.object(validator, "_resolve_accounts_by_tags", return_value=["345678901234"]):
            result = validator.get_resolved_accounts(sample_template)

            # Should include both account IDs from the template
            assert "123456789012" in result
            assert "234567890123" in result

    def test_get_resolved_accounts_with_tags(self, validator):
        """Test account resolution with tag-based targets."""
        metadata = TemplateMetadata(name="tag-template")
        targets = TemplateTarget(account_tags={"Environment": "production"})
        assignment = TemplateAssignment(
            entities=["user:admin"], permission_sets=["AdminAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        with patch.object(
            validator, "_resolve_accounts_by_tags", return_value=["123456789012", "234567890123"]
        ):
            result = validator.get_resolved_accounts(template)

            assert "123456789012" in result
            assert "234567890123" in result

    def test_get_resolved_accounts_with_exclusions(self, validator):
        """Test account resolution with exclusions."""
        metadata = TemplateMetadata(name="exclude-template")
        targets = TemplateTarget(
            account_ids=["123456789012", "234567890123", "345678901234"],
            exclude_accounts=["234567890123"],
        )
        assignment = TemplateAssignment(
            entities=["user:admin"], permission_sets=["AdminAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        result = validator.get_resolved_accounts(template)

        assert "123456789012" in result
        assert "234567890123" not in result  # Should be excluded
        assert "345678901234" in result

    def test_resolve_accounts_by_tags_success(self, validator):
        """Test successful account resolution by tags."""
        mock_client = MagicMock()
        mock_client.list_accounts.return_value = {
            "Accounts": [
                {"Id": "123456789012", "Status": "ACTIVE"},
                {"Id": "234567890123", "Status": "ACTIVE"},
                {"Id": "345678901234", "Status": "SUSPENDED"},  # Should be filtered out
            ]
        }
        mock_client.list_tags_for_resource.return_value = {
            "Tags": [{"Key": "Environment", "Value": "production"}]
        }
        validator._organizations_client = mock_client

        result = validator._resolve_accounts_by_tags({"Environment": "production"})

        assert len(result) == 2
        assert "123456789012" in result
        assert "234567890123" in result
        assert "345678901234" not in result  # Suspended account should be filtered

    def test_resolve_accounts_by_tags_no_match(self, validator):
        """Test account resolution by tags with no matches."""
        mock_client = MagicMock()
        mock_client.list_accounts.return_value = {
            "Accounts": [{"Id": "123456789012", "Status": "ACTIVE"}]
        }
        mock_client.list_tags_for_resource.return_value = {
            "Tags": [{"Key": "Environment", "Value": "development"}]  # Different value
        }
        validator._organizations_client = mock_client

        result = validator._resolve_accounts_by_tags({"Environment": "production"})

        assert len(result) == 0

    def test_resolve_accounts_by_tags_api_error(self, validator):
        """Test account resolution by tags with API error."""
        mock_client = MagicMock()
        mock_client.list_accounts.side_effect = Exception("API error")
        validator._organizations_client = mock_client

        result = validator._resolve_accounts_by_tags({"Environment": "production"})

        assert len(result) == 0

    def test_resolve_accounts_by_tags_tag_error(self, validator):
        """Test account resolution by tags with tag retrieval error."""
        mock_client = MagicMock()
        mock_client.list_accounts.return_value = {
            "Accounts": [{"Id": "123456789012", "Status": "ACTIVE"}]
        }
        mock_client.list_tags_for_resource.side_effect = Exception("Tag API error")
        validator._organizations_client = mock_client

        result = validator._resolve_accounts_by_tags({"Environment": "production"})

        assert len(result) == 0
