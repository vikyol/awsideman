"""
Unit tests for the TemplateExecutor class.

Tests template execution functionality including applying assignments,
generating previews, and integrating with AWS services.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.awsideman.permission_cloning.models import EntityReference, EntityType
from src.awsideman.templates.executor import (
    AssignmentResult,
    ExecutionResult,
    PreviewResult,
    TemplateExecutor,
)
from src.awsideman.templates.models import (
    Template,
    TemplateAssignment,
    TemplateMetadata,
    TemplateTarget,
)


class TestTemplateExecutor:
    """Test cases for TemplateExecutor class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        manager = MagicMock()
        manager.get_identity_center_client.return_value = MagicMock()
        manager.get_identity_store_client.return_value = MagicMock()
        manager.get_organizations_client.return_value = MagicMock()
        return manager

    @pytest.fixture
    def executor(self, mock_client_manager):
        """Create a TemplateExecutor instance with mocked dependencies."""
        return TemplateExecutor(
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
        client.list_account_assignments.return_value = {"AccountAssignments": []}
        client.create_account_assignment.return_value = {}
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
        client.describe_account.return_value = {
            "Account": {"Id": "123456789012", "Name": "Test Account 1"}
        }
        client.list_tags_for_resource.return_value = {"Tags": []}
        return client

    def test_init(self, mock_client_manager):
        """Test executor initialization."""
        executor = TemplateExecutor(
            client_manager=mock_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890abcdef",
        )

        assert executor.client_manager == mock_client_manager
        assert executor.instance_arn == "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        assert executor.identity_store_id == "d-1234567890abcdef"

    def test_entity_resolver_property(self, executor):
        """Test entity resolver property creation."""
        with patch(
            "src.awsideman.permission_cloning.entity_resolver.EntityResolver"
        ) as mock_entity_resolver_class:
            mock_resolver = MagicMock()
            mock_entity_resolver_class.return_value = mock_resolver

            result = executor.entity_resolver

            assert result == mock_resolver
            mock_entity_resolver_class.assert_called_once()

    def test_identity_center_client_property(self, executor):
        """Test Identity Center client property."""
        mock_client = MagicMock()
        executor.client_manager.get_identity_center_client.return_value = mock_client

        result = executor.identity_center_client

        assert result == mock_client
        executor.client_manager.get_identity_center_client.assert_called_once()

    def test_organizations_client_property(self, executor):
        """Test Organizations client property."""
        mock_client = MagicMock()
        executor.client_manager.get_organizations_client.return_value = mock_client

        result = executor.organizations_client

        assert result == mock_client
        executor.client_manager.get_organizations_client.assert_called_once()

    def test_apply_template_success(self, executor, sample_template):
        """Test successful template application."""
        with patch.object(
            executor, "_resolve_template_accounts", return_value=["123456789012", "234567890123"]
        ):
            with patch.object(executor, "_create_assignments") as mock_create:
                mock_create.return_value = [
                    AssignmentResult(
                        entity_name="john.doe",
                        entity_type="user",
                        permission_set_name="DeveloperAccess",
                        account_id="123456789012",
                        account_name="Test Account 1",
                        status="created",
                    )
                ]

                result = executor.apply_template(sample_template, dry_run=False)

                assert isinstance(result, ExecutionResult)
                assert result.success is True
                assert len(result.assignments_created) == 1
                assert result.operation_id is not None
                assert result.execution_time > 0

    def test_apply_template_dry_run(self, executor, sample_template):
        """Test template application in dry-run mode."""
        with patch.object(executor, "_resolve_template_accounts", return_value=["123456789012"]):
            with patch.object(executor, "_create_assignments") as mock_create:
                mock_create.return_value = [
                    AssignmentResult(
                        entity_name="john.doe",
                        entity_type="user",
                        permission_set_name="DeveloperAccess",
                        account_id="123456789012",
                        account_name="Test Account 1",
                        status="created",
                    )
                ]

                result = executor.apply_template(sample_template, dry_run=True)

                assert result.success is True
                assert len(result.assignments_created) == 1

    def test_apply_template_with_failures(self, executor, sample_template):
        """Test template application with some failures."""
        with patch.object(executor, "_resolve_template_accounts", return_value=["123456789012"]):
            with patch.object(executor, "_create_assignments") as mock_create:
                mock_create.return_value = [
                    AssignmentResult(
                        entity_name="john.doe",
                        entity_type="user",
                        permission_set_name="DeveloperAccess",
                        account_id="123456789012",
                        account_name="Test Account 1",
                        status="created",
                    ),
                    AssignmentResult(
                        entity_name="jane.smith",
                        entity_type="user",
                        permission_set_name="AdminAccess",
                        account_id="123456789012",
                        account_name="Test Account 1",
                        status="failed",
                        error_message="Permission denied",
                    ),
                ]

                result = executor.apply_template(sample_template, dry_run=False)

                assert result.success is False
                assert len(result.assignments_created) == 1
                assert len(result.assignments_failed) == 1

    def test_apply_template_exception(self, executor, sample_template):
        """Test template application with exception."""
        with patch.object(
            executor, "_resolve_template_accounts", side_effect=Exception("AWS API error")
        ):
            result = executor.apply_template(sample_template, dry_run=False)

            assert result.success is False
            assert result.error_message == "AWS API error"
            assert result.operation_id is not None

    def test_preview_template(self, executor, sample_template):
        """Test template preview generation."""
        with patch.object(
            executor, "_resolve_template_accounts", return_value=["123456789012", "234567890123"]
        ):
            with patch.object(executor, "_get_entity_details") as mock_entity_details:
                with patch.object(executor, "_get_permission_set_details") as mock_ps_details:
                    with patch.object(executor, "_get_account_details") as mock_account_details:
                        mock_entity_details.return_value = [
                            {"reference": "user:john.doe", "exists": True}
                        ]
                        mock_ps_details.return_value = [{"name": "DeveloperAccess", "exists": True}]
                        mock_account_details.return_value = [
                            {"id": "123456789012", "name": "Test Account"}
                        ]

                        result = executor.preview_template(sample_template)

                        assert isinstance(result, PreviewResult)
                        assert result.template == sample_template
                        assert len(result.resolved_accounts) == 2
                        assert (
                            result.total_assignments == 8
                        )  # 2 entities * 2 permission sets * 2 accounts

    def test_resolve_template_accounts(self, executor, sample_template):
        """Test account resolution from template."""
        with patch.object(executor, "_resolve_accounts_by_tags") as mock_resolve_tags:
            mock_resolve_tags.return_value = ["345678901234"]

            result = executor._resolve_template_accounts(sample_template)

            # Should include both account IDs from the template
            assert "123456789012" in result
            assert "234567890123" in result

    def test_resolve_template_accounts_with_tags(self, executor):
        """Test account resolution with tag-based targets."""
        metadata = TemplateMetadata(name="tag-template")
        targets = TemplateTarget(account_tags={"Environment": "production"})
        assignment = TemplateAssignment(
            entities=["user:admin"], permission_sets=["AdminAccess"], targets=targets
        )
        template = Template(metadata=metadata, assignments=[assignment])

        with patch.object(
            executor, "_resolve_accounts_by_tags", return_value=["123456789012", "234567890123"]
        ):
            result = executor._resolve_template_accounts(template)

            assert "123456789012" in result
            assert "234567890123" in result

    def test_create_assignments(self, executor, sample_template):
        """Test assignment creation from template."""
        accounts = ["123456789012"]

        with patch.object(executor, "_create_single_assignment") as mock_create_single:
            mock_create_single.return_value = AssignmentResult(
                entity_name="john.doe",
                entity_type="user",
                permission_set_name="DeveloperAccess",
                account_id="123456789012",
                account_name="Test Account",
                status="created",
            )

            result = executor._create_assignments(
                sample_template.assignments[0], accounts, dry_run=False, operation_id="test-op"
            )

            # 2 entities * 2 permission sets * 1 account = 4 assignments
            assert len(result) == 4
            mock_create_single.assert_called()

    def test_create_single_assignment_success(self, executor):
        """Test successful single assignment creation."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(executor, "_get_account_name", return_value="Test Account"):
                with patch.object(executor, "_assignment_exists", return_value=False):
                    with patch.object(executor, "_create_assignment_via_api"):
                        result = executor._create_single_assignment(
                            "user:john.doe",
                            "DeveloperAccess",
                            "123456789012",
                            dry_run=False,
                            operation_id="test-op",
                        )

                        assert result.status == "created"
                        assert result.entity_name == "john.doe"
                        assert result.account_id == "123456789012"

    def test_create_single_assignment_dry_run(self, executor):
        """Test single assignment creation in dry-run mode."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(executor, "_get_account_name", return_value="Test Account"):
                result = executor._create_single_assignment(
                    "user:john.doe",
                    "DeveloperAccess",
                    "123456789012",
                    dry_run=True,
                    operation_id="test-op",
                )

                assert result.status == "created"
                assert result.entity_name == "john.doe"

    def test_create_single_assignment_already_exists(self, executor):
        """Test single assignment creation when assignment already exists."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(executor, "_get_account_name", return_value="Test Account"):
                with patch.object(executor, "_assignment_exists", return_value=True):
                    result = executor._create_single_assignment(
                        "user:john.doe",
                        "DeveloperAccess",
                        "123456789012",
                        dry_run=False,
                        operation_id="test-op",
                    )

                    assert result.status == "skipped"
                    assert "already exists" in result.error_message

    def test_create_single_assignment_error(self, executor):
        """Test single assignment creation with error."""
        with patch.object(
            executor, "_parse_entity_reference", side_effect=ValueError("Invalid entity")
        ):
            result = executor._create_single_assignment(
                "invalid:entity",
                "DeveloperAccess",
                "123456789012",
                dry_run=False,
                operation_id="test-op",
            )

            assert result.status == "failed"
            assert "Invalid entity" in result.error_message

    def test_parse_entity_reference_valid(self, executor):
        """Test valid entity reference parsing."""
        result = executor._parse_entity_reference("user:john.doe")
        assert result == ("user", "john.doe")

    def test_parse_entity_reference_invalid_format(self, executor):
        """Test invalid entity reference format."""
        with pytest.raises(ValueError, match="Entity reference must be in format 'type:name'"):
            executor._parse_entity_reference("invalid-format")

    def test_parse_entity_reference_invalid_type(self, executor):
        """Test invalid entity type."""
        with pytest.raises(ValueError, match="Entity type must be 'user' or 'group'"):
            executor._parse_entity_reference("role:admin")

    def test_parse_entity_reference_empty_name(self, executor):
        """Test entity reference with empty name."""
        with pytest.raises(ValueError, match="Entity name cannot be empty"):
            executor._parse_entity_reference("user:")

    def test_get_account_name_success(self, executor):
        """Test successful account name retrieval."""
        mock_client = MagicMock()
        mock_client.describe_account.return_value = {"Account": {"Name": "Test Account"}}
        executor._organizations_client = mock_client

        result = executor._get_account_name("123456789012")
        assert result == "Test Account"

    def test_get_account_name_error(self, executor):
        """Test account name retrieval with error."""
        mock_client = MagicMock()
        mock_client.describe_account.side_effect = Exception("API error")
        executor._organizations_client = mock_client

        result = executor._get_account_name("123456789012")
        assert result == "123456789012"  # Should return account ID on error

    def test_assignment_exists_true(self, executor):
        """Test checking if assignment exists."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(
                executor, "_get_permission_set_arn", return_value="arn:permission-set"
            ):
                # Mock the entity resolver property by setting the private attribute
                mock_resolver = MagicMock()
                mock_resolver.resolve_entity_by_name.return_value = EntityReference(
                    entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
                )
                executor._entity_resolver = mock_resolver

                mock_client = MagicMock()
                mock_client.list_account_assignments.return_value = {
                    "AccountAssignments": [{"PrincipalId": "user-123"}]
                }
                executor._identity_center_client = mock_client

                result = executor._assignment_exists(
                    "user:john.doe", "DeveloperAccess", "123456789012"
                )
                assert result is True

    def test_assignment_exists_false(self, executor):
        """Test checking if assignment doesn't exist."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(
                executor, "_get_permission_set_arn", return_value="arn:permission-set"
            ):
                # Mock the entity resolver property by setting the private attribute
                mock_resolver = MagicMock()
                mock_resolver.resolve_entity_by_name.return_value = EntityReference(
                    entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
                )
                executor._entity_resolver = mock_resolver

                mock_client = MagicMock()
                mock_client.list_account_assignments.return_value = {"AccountAssignments": []}
                executor._identity_center_client = mock_client

                result = executor._assignment_exists(
                    "user:john.doe", "DeveloperAccess", "123456789012"
                )
                assert result is False

    def test_get_permission_set_arn_success(self, executor):
        """Test successful permission set ARN retrieval."""
        mock_client = MagicMock()
        mock_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:permission-set"]
        }
        mock_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "DeveloperAccess"}
        }
        executor._identity_center_client = mock_client

        result = executor._get_permission_set_arn("DeveloperAccess")
        assert result == "arn:permission-set"

    def test_get_permission_set_arn_not_found(self, executor):
        """Test permission set ARN retrieval when not found."""
        mock_client = MagicMock()
        mock_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:permission-set"]
        }
        mock_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "DifferentName"}
        }
        executor._identity_center_client = mock_client

        result = executor._get_permission_set_arn("DeveloperAccess")
        assert result is None

    def test_create_assignment_via_api_success(self, executor):
        """Test successful assignment creation via API."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            with patch.object(
                executor, "_get_permission_set_arn", return_value="arn:permission-set"
            ):
                # Mock the entity resolver property by setting the private attribute
                mock_resolver = MagicMock()
                mock_resolver.resolve_entity_by_name.return_value = EntityReference(
                    entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
                )
                executor._entity_resolver = mock_resolver

                mock_client = MagicMock()
                executor._identity_center_client = mock_client

                executor._create_assignment_via_api(
                    "user:john.doe", "DeveloperAccess", "123456789012"
                )

                mock_client.create_account_assignment.assert_called_once()

    def test_resolve_accounts_by_tags(self, executor):
        """Test account resolution by tags."""
        mock_client = MagicMock()
        mock_client.list_accounts.return_value = {
            "Accounts": [
                {"Id": "123456789012", "Status": "ACTIVE"},
                {"Id": "234567890123", "Status": "ACTIVE"},
            ]
        }
        mock_client.list_tags_for_resource.return_value = {
            "Tags": [{"Key": "Environment", "Value": "production"}]
        }
        executor._organizations_client = mock_client

        result = executor._resolve_accounts_by_tags({"Environment": "production"})

        assert len(result) == 2
        assert "123456789012" in result
        assert "234567890123" in result

    def test_get_entity_details(self, executor, sample_template):
        """Test entity details retrieval."""
        with patch.object(executor, "_parse_entity_reference", return_value=("user", "john.doe")):
            # Mock the entity resolver property by setting the private attribute
            mock_resolver = MagicMock()
            mock_resolver.resolve_entity_by_name.return_value = EntityReference(
                entity_type=EntityType.USER, entity_id="user-123", entity_name="john.doe"
            )
            executor._entity_resolver = mock_resolver

            result = executor._get_entity_details(sample_template)

            assert len(result) == 2  # 2 entities in the template
            assert result[0]["reference"] == "user:john.doe"
            assert result[0]["exists"] is True

    def test_get_permission_set_details(self, executor, sample_template):
        """Test permission set details retrieval."""
        with patch.object(executor, "_get_permission_set_arn", return_value="arn:permission-set"):
            result = executor._get_permission_set_details(sample_template)

            assert len(result) == 2  # 2 permission sets in the template
            assert result[0]["name"] == "DeveloperAccess"
            assert result[0]["exists"] is True

    def test_get_account_details(self, executor):
        """Test account details retrieval."""
        with patch.object(executor, "_get_account_name", return_value="Test Account"):
            result = executor._get_account_details(["123456789012"])

            assert len(result) == 1
            assert result[0]["id"] == "123456789012"
            assert result[0]["name"] == "Test Account"
            assert result[0]["status"] == "ACTIVE"


class TestExecutionResult:
    """Test cases for ExecutionResult class."""

    def test_init_success(self):
        """Test successful execution result initialization."""
        result = ExecutionResult(
            success=True,
            assignments_created=[MagicMock()],
            assignments_skipped=[],
            assignments_failed=[],
            operation_id="test-op",
            execution_time=1.5,
        )

        assert result.success is True
        assert len(result.assignments_created) == 1
        assert result.operation_id == "test-op"
        assert result.execution_time == 1.5

    def test_init_failure(self):
        """Test failed execution result initialization."""
        result = ExecutionResult(
            success=False,
            assignments_created=[],
            assignments_skipped=[],
            assignments_failed=[MagicMock()],
            operation_id="test-op",
            execution_time=1.5,
        )

        assert result.success is False
        assert len(result.assignments_failed) == 1

    def test_post_init_sets_success(self):
        """Test that post_init sets success based on failures."""
        result = ExecutionResult(
            success=None,  # Not set initially
            assignments_created=[],
            assignments_skipped=[],
            assignments_failed=[MagicMock()],  # Has failures
            operation_id="test-op",
            execution_time=1.5,
        )

        # The post_init method should set success to False when there are failures
        assert result.success is False

    def test_get_summary(self):
        """Test execution result summary."""
        result = ExecutionResult(
            success=True,
            assignments_created=[MagicMock(), MagicMock()],  # 2 created
            assignments_skipped=[MagicMock()],  # 1 skipped
            assignments_failed=[],  # 0 failed
            operation_id="test-op",
            execution_time=2.0,
        )

        summary = result.get_summary()

        assert summary["total_assignments"] == 3
        assert summary["created"] == 2
        assert summary["skipped"] == 1
        assert summary["failed"] == 0
        assert summary["success_rate"] == 2 / 3
        assert summary["execution_time"] == 2.0
        assert summary["operation_id"] == "test-op"


class TestAssignmentResult:
    """Test cases for AssignmentResult class."""

    def test_init(self):
        """Test assignment result initialization."""
        result = AssignmentResult(
            entity_name="john.doe",
            entity_type="user",
            permission_set_name="DeveloperAccess",
            account_id="123456789012",
            account_name="Test Account",
            status="created",
            operation_id="test-op",
        )

        assert result.entity_name == "john.doe"
        assert result.entity_type == "user"
        assert result.permission_set_name == "DeveloperAccess"
        assert result.account_id == "123456789012"
        assert result.account_name == "Test Account"
        assert result.status == "created"
        assert result.operation_id == "test-op"
        assert result.error_message is None


class TestPreviewResult:
    """Test cases for PreviewResult class."""

    def test_init(self):
        """Test preview result initialization."""
        # Create a proper mock template with metadata
        template = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.name = "test-template"
        template.metadata = mock_metadata

        result = PreviewResult(
            template=template,
            resolved_accounts=["123456789012"],
            total_assignments=4,
            entity_details=[{"name": "john.doe"}],
            permission_set_details=[{"name": "DeveloperAccess"}],
            account_details=[{"id": "123456789012"}],
        )

        assert result.template == template
        assert result.resolved_accounts == ["123456789012"]
        assert result.total_assignments == 4
        assert len(result.entity_details) == 1
        assert len(result.permission_set_details) == 1
        assert len(result.account_details) == 1

    def test_get_summary(self):
        """Test preview result summary."""
        # Create a proper mock template with metadata
        template = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.name = "test-template"
        template.metadata = mock_metadata

        result = PreviewResult(
            template=template,
            resolved_accounts=["123456789012", "234567890123"],
            total_assignments=8,
            entity_details=[{"name": "john.doe"}, {"name": "jane.smith"}],
            permission_set_details=[{"name": "DeveloperAccess"}, {"name": "ReadOnlyAccess"}],
            account_details=[{"id": "123456789012"}, {"id": "234567890123"}],
        )

        summary = result.get_summary()

        assert summary["template_name"] == "test-template"
        assert summary["total_assignments"] == 8
        assert summary["resolved_accounts"] == 2
        assert summary["entities"] == 2
        assert summary["permission_sets"] == 2
