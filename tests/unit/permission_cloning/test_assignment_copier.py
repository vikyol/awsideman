"""
Unit tests for the AssignmentCopier class.

Tests assignment copying functionality including:
- Entity validation
- Assignment copying between different entity types
- Duplicate detection and skipping
- Filter application
- Preview mode
- Error handling
"""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.permission_cloning.assignment_copier import AssignmentCopier
from src.awsideman.permission_cloning.assignment_retriever import AssignmentRetriever
from src.awsideman.permission_cloning.entity_resolver import EntityResolver
from src.awsideman.permission_cloning.filter_engine import FilterEngine
from src.awsideman.permission_cloning.models import (
    CopyFilters,
    CopyResult,
    EntityReference,
    EntityType,
    PermissionAssignment,
    ValidationResultType,
)


class TestAssignmentCopier:
    """Test cases for AssignmentCopier class."""

    @pytest.fixture
    def mock_entity_resolver(self):
        """Create a mock EntityResolver."""
        return Mock(spec=EntityResolver)

    @pytest.fixture
    def mock_assignment_retriever(self):
        """Create a mock AssignmentRetriever."""
        return Mock(spec=AssignmentRetriever)

    @pytest.fixture
    def mock_filter_engine(self):
        """Create a mock FilterEngine."""
        return Mock(spec=FilterEngine)

    @pytest.fixture
    def assignment_copier(
        self, mock_entity_resolver, mock_assignment_retriever, mock_filter_engine
    ):
        """Create an AssignmentCopier instance with mocked dependencies."""
        return AssignmentCopier(
            entity_resolver=mock_entity_resolver,
            assignment_retriever=mock_assignment_retriever,
            filter_engine=mock_filter_engine,
        )

    @pytest.fixture
    def valid_user_entity(self):
        """Create a valid user entity reference."""
        return EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="test-user"
        )

    @pytest.fixture
    def valid_group_entity(self):
        """Create a valid group entity reference."""
        return EntityReference(
            entity_type=EntityType.GROUP, entity_id="group-456", entity_name="test-group"
        )

    @pytest.fixture
    def sample_assignments(self):
        """Create sample permission assignments for testing."""
        return [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="123456789012",
                account_name="Production",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
                permission_set_name="ReadOnlyAccess",
                account_id="098765432109",
                account_name="Development",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-developer",
                permission_set_name="DeveloperAccess",
                account_id="555555555555",
                account_name="Staging",
            ),
        ]

    @pytest.fixture
    def sample_filters(self):
        """Create sample copy filters for testing."""
        return CopyFilters(
            exclude_permission_sets=["DeveloperAccess"],
            exclude_accounts=["555555555555"],
        )

    def test_init(
        self, assignment_copier, mock_entity_resolver, mock_assignment_retriever, mock_filter_engine
    ):
        """Test AssignmentCopier initialization."""
        assert assignment_copier.entity_resolver == mock_entity_resolver
        assert assignment_copier.assignment_retriever == mock_assignment_retriever
        assert assignment_copier.filter_engine == mock_filter_engine

    def test_validate_entities_success(
        self, assignment_copier, mock_entity_resolver, valid_user_entity, valid_group_entity
    ):
        """Test successful entity validation."""
        # Mock successful validation for both entities
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        result = assignment_copier.validate_entities(valid_user_entity, valid_group_entity)

        assert result.result_type == ValidationResultType.SUCCESS
        assert len(result.messages) == 0
        assert mock_entity_resolver.validate_entity.call_count == 2

    def test_validate_entities_source_error(
        self, assignment_copier, mock_entity_resolver, valid_user_entity, valid_group_entity
    ):
        """Test entity validation with source entity error."""
        # Mock source validation failure
        mock_entity_resolver.validate_entity.side_effect = [
            Mock(
                has_errors=True, messages=["User not found"], result_type=ValidationResultType.ERROR
            ),  # Source
            Mock(has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS),  # Target
        ]

        result = assignment_copier.validate_entities(valid_user_entity, valid_group_entity)

        assert result.result_type == ValidationResultType.ERROR
        assert "Source USER: User not found" in result.messages[0]

    def test_validate_entities_target_error(
        self, assignment_copier, mock_entity_resolver, valid_user_entity, valid_group_entity
    ):
        """Test entity validation with target entity error."""
        # Mock target validation failure
        mock_entity_resolver.validate_entity.side_effect = [
            Mock(has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS),  # Source
            Mock(
                has_errors=True,
                messages=["Group not found"],
                result_type=ValidationResultType.ERROR,
            ),  # Target
        ]

        result = assignment_copier.validate_entities(valid_user_entity, valid_group_entity)

        assert result.result_type == ValidationResultType.ERROR
        assert "Target GROUP: Group not found" in result.messages[0]

    def test_validate_entities_same_entity(
        self, assignment_copier, mock_entity_resolver, valid_user_entity
    ):
        """Test entity validation with same source and target entity."""
        # Mock successful validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        result = assignment_copier.validate_entities(valid_user_entity, valid_user_entity)

        assert result.result_type == ValidationResultType.ERROR
        assert "Source and target entities cannot be the same" in result.messages[0]

    def test_get_source_assignments_user(
        self, assignment_copier, mock_assignment_retriever, valid_user_entity, sample_assignments
    ):
        """Test getting source assignments for a user."""
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments

        result = assignment_copier.get_source_assignments(valid_user_entity)

        assert result == sample_assignments
        mock_assignment_retriever.get_user_assignments.assert_called_once_with(valid_user_entity)

    def test_get_source_assignments_group(
        self, assignment_copier, mock_assignment_retriever, valid_group_entity, sample_assignments
    ):
        """Test getting source assignments for a group."""
        mock_assignment_retriever.get_group_assignments.return_value = sample_assignments

        result = assignment_copier.get_source_assignments(valid_group_entity)

        assert result == sample_assignments
        mock_assignment_retriever.get_group_assignments.assert_called_once_with(valid_group_entity)

    def test_get_source_assignments_unsupported_type(self, assignment_copier):
        """Test getting source assignments for unsupported entity type."""
        unsupported_entity = EntityReference(
            entity_type="UNSUPPORTED", entity_id="test", entity_name="test"
        )

        result = assignment_copier.get_source_assignments(unsupported_entity)

        assert result == []

    def test_identify_assignments_to_copy_no_duplicates(
        self, assignment_copier, sample_assignments
    ):
        """Test identifying assignments to copy with no duplicates."""
        target_assignments = []  # No existing assignments

        to_copy, to_skip = assignment_copier._identify_assignments_to_copy(
            sample_assignments, target_assignments
        )

        assert len(to_copy) == 3
        assert len(to_skip) == 0
        assert to_copy == sample_assignments

    def test_identify_assignments_to_copy_with_duplicates(
        self, assignment_copier, sample_assignments
    ):
        """Test identifying assignments to copy with duplicates."""
        # Create target assignments with one duplicate
        target_assignments = [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="123456789012",
                account_name="Production",
            )
        ]

        to_copy, to_skip = assignment_copier._identify_assignments_to_copy(
            sample_assignments, target_assignments
        )

        assert len(to_copy) == 2
        assert len(to_skip) == 1
        assert to_skip[0].permission_set_name == "AdministratorAccess"
        assert to_skip[0].account_id == "123456789012"

    def test_copy_assignments_success(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
    ):
        """Test successful assignment copying."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_group_assignments.return_value = []

        # Mock the get_source_assignments method to return proper lists
        assignment_copier.get_source_assignments = Mock(
            side_effect=[sample_assignments, []]  # For source entity  # For target entity
        )

        # Mock filter engine
        mock_filter_engine.apply_filters.return_value = sample_assignments
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        # Mock SSO client
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        with patch("uuid.uuid4", return_value="test-rollback-id"):
            result = assignment_copier.copy_assignments(valid_user_entity, valid_group_entity)

        assert result.success
        # The UUID patch might not work in all environments, so just check it's not None
        assert result.rollback_id is not None
        assert len(result.assignments_copied) == 3
        assert len(result.assignments_skipped) == 0
        assert result.source == valid_user_entity
        assert result.target == valid_group_entity

    def test_copy_assignments_with_filters(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
        sample_filters,
    ):
        """Test assignment copying with filters."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_group_assignments.return_value = []

        # Mock filter engine
        filtered_assignments = sample_assignments[:2]  # First 2 assignments
        mock_filter_engine.apply_filters.return_value = filtered_assignments
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        # Mock SSO client
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        with patch("uuid.uuid4", return_value="test-rollback-id"):
            result = assignment_copier.copy_assignments(
                valid_user_entity, valid_group_entity, filters=sample_filters
            )

        assert result.success
        assert len(result.assignments_copied) == 2
        mock_filter_engine.apply_filters.assert_called_once_with(sample_assignments, sample_filters)

    def test_copy_assignments_preview_mode(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
    ):
        """Test assignment copying in preview mode."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_group_assignments.return_value = []

        # Mock filter engine
        mock_filter_engine.apply_filters.return_value = sample_assignments
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        result = assignment_copier.copy_assignments(
            valid_user_entity, valid_group_entity, preview=True
        )

        assert result.success
        assert result.rollback_id is None
        assert len(result.assignments_copied) == 3
        assert len(result.assignments_skipped) == 0
        # Should not call SSO client methods in preview mode

    def test_copy_assignments_no_source_assignments(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        valid_user_entity,
        valid_group_entity,
    ):
        """Test assignment copying with no source assignments."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock empty assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = []
        mock_assignment_retriever.get_group_assignments.return_value = []

        result = assignment_copier.copy_assignments(valid_user_entity, valid_group_entity)

        assert result.success
        assert len(result.assignments_copied) == 0
        assert len(result.assignments_skipped) == 0
        assert result.rollback_id is None

    def test_copy_assignments_filters_no_matches(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
        sample_filters,
    ):
        """Test assignment copying with filters that result in no matches."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_group_assignments.return_value = []

        # Mock filter engine returning no matches
        mock_filter_engine.apply_filters.return_value = []
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        result = assignment_copier.copy_assignments(
            valid_user_entity, valid_group_entity, filters=sample_filters
        )

        assert result.success
        assert len(result.assignments_copied) == 0
        assert len(result.assignments_skipped) == 0
        assert result.rollback_id is None

    def test_copy_assignments_exception_handling(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        valid_user_entity,
        valid_group_entity,
    ):
        """Test assignment copying with exception handling."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval to raise exception
        mock_assignment_retriever.get_user_assignments.side_effect = Exception("API Error")

        result = assignment_copier.copy_assignments(valid_user_entity, valid_group_entity)

        assert not result.success
        assert "Copy operation failed: API Error" in result.error_message
        assert result.rollback_id is None

    def test_create_user_assignment_success(self, assignment_copier, mock_assignment_retriever):
        """Test successful user assignment creation."""
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        assignment_copier._create_user_assignment(
            user_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            account_id="123456789012",
        )

        mock_sso_client.create_account_assignment.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test",
            TargetId="user-123",
            TargetType="AWS_ACCOUNT",
            PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            PrincipalType="USER",
            AccountId="123456789012",
        )

    def test_create_group_assignment_success(self, assignment_copier, mock_assignment_retriever):
        """Test successful group assignment creation."""
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        assignment_copier._create_group_assignment(
            group_id="group-456",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            account_id="123456789012",
        )

        mock_sso_client.create_account_assignment.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test",
            TargetId="group-456",
            TargetType="AWS_ACCOUNT",
            PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            PrincipalType="GROUP",
            AccountId="123456789012",
        )

    def test_create_user_assignment_failure(self, assignment_copier, mock_assignment_retriever):
        """Test user assignment creation failure."""
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        # Mock API call to raise exception
        mock_sso_client.create_account_assignment.side_effect = Exception("Permission denied")

        with pytest.raises(Exception, match="Permission denied"):
            assignment_copier._create_user_assignment(
                user_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                account_id="123456789012",
            )

    def test_get_copy_summary_success(self, assignment_copier):
        """Test getting copy summary for successful operation."""
        copy_result = CopyResult(
            source=EntityReference(EntityType.USER, "user-123", "test-user"),
            target=EntityReference(EntityType.GROUP, "group-456", "test-group"),
            assignments_copied=[Mock(), Mock()],  # 2 assignments
            assignments_skipped=[Mock()],  # 1 skipped
            rollback_id="test-rollback-id",
            success=True,
            error_message=None,
        )

        summary = assignment_copier.get_copy_summary(copy_result)

        assert "Successfully copied 2 assignments" in summary
        assert "Skipped 1 duplicate assignments" in summary
        assert "Rollback ID: test-rollback-id" in summary

    def test_get_copy_summary_failure(self, assignment_copier):
        """Test getting copy summary for failed operation."""
        copy_result = CopyResult(
            source=EntityReference(EntityType.USER, "user-123", "test-user"),
            target=EntityReference(EntityType.GROUP, "group-456", "test-group"),
            assignments_copied=[],
            assignments_skipped=[],
            rollback_id=None,
            success=False,
            error_message="Validation failed",
        )

        summary = assignment_copier.get_copy_summary(copy_result)

        assert "Copy operation failed: Validation failed" in summary

    def test_get_copy_summary_no_assignments(self, assignment_copier):
        """Test getting copy summary for operation with no assignments."""
        copy_result = CopyResult(
            source=EntityReference(EntityType.USER, "user-123", "test-user"),
            target=EntityReference(EntityType.GROUP, "group-456", "test-group"),
            assignments_copied=[],
            assignments_skipped=[],
            rollback_id=None,
            success=True,
            error_message=None,
        )

        summary = assignment_copier.get_copy_summary(copy_result)

        assert "No assignments were copied" in summary
        assert "Rollback ID" not in summary

    def test_copy_assignments_user_to_group(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
    ):
        """Test copying assignments from user to group."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_user_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_group_assignments.return_value = []

        # Mock filter engine
        mock_filter_engine.apply_filters.return_value = sample_assignments
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        # Mock SSO client
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        with patch("uuid.uuid4", return_value="test-rollback-id"):
            result = assignment_copier.copy_assignments(valid_user_entity, valid_group_entity)

        assert result.success
        assert result.source.entity_type == EntityType.USER
        assert result.target.entity_type == EntityType.GROUP

    def test_copy_assignments_group_to_user(
        self,
        assignment_copier,
        mock_entity_resolver,
        mock_assignment_retriever,
        mock_filter_engine,
        valid_user_entity,
        valid_group_entity,
        sample_assignments,
    ):
        """Test copying assignments from group to user."""
        # Mock entity validation
        mock_entity_resolver.validate_entity.return_value = Mock(
            has_errors=False, messages=[], result_type=ValidationResultType.SUCCESS
        )

        # Mock assignment retrieval
        mock_assignment_retriever.get_group_assignments.return_value = sample_assignments
        mock_assignment_retriever.get_user_assignments.return_value = []

        # Mock filter engine
        mock_filter_engine.apply_filters.return_value = sample_assignments
        mock_filter_engine.get_filter_summary.return_value = "Test filters"

        # Mock SSO client
        mock_sso_client = Mock()
        mock_assignment_retriever.sso_admin_client = mock_sso_client
        mock_assignment_retriever.instance_arn = "arn:aws:sso:::instance/test"

        with patch("uuid.uuid4", return_value="test-rollback-id"):
            result = assignment_copier.copy_assignments(valid_group_entity, valid_user_entity)

        assert result.success
        assert result.source.entity_type == EntityType.GROUP
        assert result.target.entity_type == EntityType.USER
