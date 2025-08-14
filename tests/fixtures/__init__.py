"""Test fixtures package for awsideman.

This package provides organized test fixtures and data for different functional areas:

- common: Shared fixtures and configuration
- aws_clients: AWS client mocks and fixtures
- bulk_operations: Bulk operation test data and fixtures
- rollback_operations: Rollback operation test data and fixtures
- permission_sets: Permission set test data and fixtures
- users_groups: User and group test data and fixtures
- organizations: AWS Organizations test data and fixtures

Usage:
    from tests.fixtures.common import mock_validation_functions
    from tests.fixtures.aws_clients import mock_aws_client_manager
    from tests.fixtures.bulk_operations import sample_bulk_assignments
    from tests.fixtures.rollback_operations import sample_operation_record
    from tests.fixtures.permission_sets import sample_permission_set_data
    from tests.fixtures.users_groups import sample_user_data
    from tests.fixtures.organizations import sample_account_data
"""

from .aws_clients import (
    aws_client_factory,
    mock_aws_client_manager,
    mock_aws_error,
    mock_iam_client,
    mock_identity_store_client,
    mock_organizations_client,
    mock_sso_admin_client,
)
from .bulk_operations import (
    bulk_operation_factory,
    sample_bulk_assignments,
    sample_bulk_results,
    sample_csv_data,
    sample_json_data,
    sample_multi_account_data,
    sample_resolved_assignments,
)

# Import all fixtures to make them available when importing the package
from .common import (
    PermissionSetMockFactory,
    mock_aws_infrastructure,
    mock_validation_functions,
    sample_create_response,
    sample_managed_policies,
    sample_permission_set_data,
)
from .organizations import (
    organizations_factory,
    sample_account_data,
    sample_account_tags,
    sample_accounts_list,
    sample_organization_hierarchy,
    sample_organizational_unit_data,
    sample_organizational_units_list,
    sample_root_data,
)
from .permission_sets import permission_set_factory
from .permission_sets import sample_create_response as sample_create_response_ps
from .permission_sets import sample_managed_policies as sample_managed_policies_ps
from .permission_sets import sample_permission_set_assignments
from .permission_sets import sample_permission_set_data as sample_permission_set_data_ps
from .permission_sets import sample_permission_sets_list
from .rollback_operations import (
    rollback_operation_factory,
    sample_operation_record,
    sample_operation_results,
    sample_rollback_actions,
    sample_rollback_operation_data,
    sample_rollback_plan,
    sample_rollback_validation,
)
from .users_groups import (
    sample_group_data,
    sample_group_members,
    sample_groups_list,
    sample_user_assignments,
    sample_user_data,
    sample_users_list,
    users_groups_factory,
)

__all__ = [
    # Common fixtures
    "mock_validation_functions",
    "mock_aws_infrastructure",
    "sample_permission_set_data",
    "sample_create_response",
    "sample_managed_policies",
    "PermissionSetMockFactory",
    # AWS client fixtures
    "mock_aws_client_manager",
    "mock_sso_admin_client",
    "mock_identity_store_client",
    "mock_organizations_client",
    "mock_iam_client",
    "aws_client_factory",
    "mock_aws_error",
    # Bulk operation fixtures
    "sample_bulk_assignments",
    "sample_csv_data",
    "sample_json_data",
    "sample_resolved_assignments",
    "sample_bulk_results",
    "sample_multi_account_data",
    "bulk_operation_factory",
    # Rollback operation fixtures
    "sample_operation_record",
    "sample_rollback_plan",
    "sample_rollback_validation",
    "sample_rollback_actions",
    "sample_operation_results",
    "sample_rollback_operation_data",
    "rollback_operation_factory",
    # Permission set fixtures
    "sample_permission_set_data_ps",
    "sample_create_response_ps",
    "sample_managed_policies_ps",
    "sample_permission_sets_list",
    "sample_permission_set_assignments",
    "permission_set_factory",
    # User and group fixtures
    "sample_user_data",
    "sample_group_data",
    "sample_users_list",
    "sample_groups_list",
    "sample_group_members",
    "sample_user_assignments",
    "users_groups_factory",
    # Organization fixtures
    "sample_account_data",
    "sample_organizational_unit_data",
    "sample_root_data",
    "sample_accounts_list",
    "sample_organizational_units_list",
    "sample_organization_hierarchy",
    "sample_account_tags",
    "organizations_factory",
]
