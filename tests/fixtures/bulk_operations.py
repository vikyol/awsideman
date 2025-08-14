"""Bulk operations test fixtures and data for awsideman tests."""

from datetime import datetime

import pytest


@pytest.fixture
def sample_bulk_assignments():
    """Sample bulk assignment data for testing."""
    return [
        {
            "principal_name": "john.doe",
            "permission_set_name": "ReadOnlyAccess",
            "account_name": "Production",
            "principal_type": "USER",
        },
        {
            "principal_name": "jane.smith",
            "permission_set_name": "AdministratorAccess",
            "account_name": "Development",
            "principal_type": "USER",
        },
        {
            "principal_name": "developers",
            "permission_set_name": "PowerUserAccess",
            "account_name": "Staging",
            "principal_type": "GROUP",
        },
    ]


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for bulk operations testing."""
    return """principal_name,permission_set_name,account_name,principal_type
john.doe,ReadOnlyAccess,Production,USER
jane.smith,AdministratorAccess,Development,USER
developers,PowerUserAccess,Staging,GROUP"""


@pytest.fixture
def sample_json_data():
    """Sample JSON data for bulk operations testing."""
    return {
        "assignments": [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
            },
            {
                "principal_name": "jane.smith",
                "permission_set_name": "AdministratorAccess",
                "account_name": "Development",
                "principal_type": "USER",
            },
            {
                "principal_name": "developers",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Staging",
                "principal_type": "GROUP",
            },
        ]
    }


@pytest.fixture
def sample_resolved_assignments():
    """Sample resolved assignments with AWS resource identifiers."""
    return [
        {
            "principal_name": "john.doe",
            "principal_id": "1234567890abcdef",
            "permission_set_name": "ReadOnlyAccess",
            "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            "account_name": "Production",
            "account_id": "123456789012",
            "principal_type": "USER",
            "resolution_success": True,
        },
        {
            "principal_name": "jane.smith",
            "principal_id": "0987654321fedcba",
            "permission_set_name": "AdministratorAccess",
            "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-123/ps-789",
            "account_name": "Development",
            "account_id": "098765432109",
            "principal_type": "USER",
            "resolution_success": True,
        },
        {
            "principal_name": "developers",
            "principal_id": "abcdef1234567890",
            "permission_set_name": "PowerUserAccess",
            "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-123/ps-012",
            "account_name": "Staging",
            "account_id": "112233445566",
            "principal_type": "GROUP",
            "resolution_success": True,
        },
    ]


@pytest.fixture
def sample_bulk_results():
    """Sample bulk operation results for testing."""
    return {
        "total_processed": 3,
        "successful": [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
                "status": "success",
                "processing_time": 0.5,
                "timestamp": datetime.now().timestamp(),
            }
        ],
        "failed": [
            {
                "principal_name": "jane.smith",
                "permission_set_name": "AdministratorAccess",
                "account_name": "Development",
                "principal_type": "USER",
                "status": "failed",
                "error_message": "Access denied",
                "processing_time": 0.2,
                "timestamp": datetime.now().timestamp(),
            }
        ],
        "skipped": [
            {
                "principal_name": "developers",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Staging",
                "principal_type": "GROUP",
                "status": "skipped",
                "error_message": "Already assigned",
                "processing_time": 0.1,
                "timestamp": datetime.now().timestamp(),
            }
        ],
        "operation_type": "assign",
        "duration": 0.8,
        "batch_size": 10,
        "continue_on_error": True,
    }


@pytest.fixture
def sample_multi_account_data():
    """Sample multi-account data for testing."""
    return {
        "accounts": [
            {
                "id": "123456789012",
                "name": "Production",
                "email": "prod@company.com",
                "status": "ACTIVE",
            },
            {
                "id": "098765432109",
                "name": "Development",
                "email": "dev@company.com",
                "status": "ACTIVE",
            },
            {
                "id": "112233445566",
                "name": "Staging",
                "email": "staging@company.com",
                "status": "ACTIVE",
            },
        ],
        "permission_set": {
            "name": "ReadOnlyAccess",
            "arn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
        },
        "principal": {"name": "developers", "id": "abcdef1234567890", "type": "GROUP"},
    }


@pytest.fixture
def bulk_operation_factory():
    """Factory for creating bulk operation test data."""

    class BulkOperationFactory:
        @staticmethod
        def create_assignment(
            principal_name="test.user",
            permission_set_name="TestAccess",
            account_name="TestAccount",
            principal_type="USER",
        ):
            """Create a single assignment for testing."""
            return {
                "principal_name": principal_name,
                "permission_set_name": permission_set_name,
                "account_name": account_name,
                "principal_type": principal_type,
            }

        @staticmethod
        def create_bulk_assignments(count=5):
            """Create multiple assignments for testing."""
            assignments = []
            for i in range(count):
                assignment = {
                    "principal_name": f"user{i}",
                    "permission_set_name": f"PermissionSet{i}",
                    "account_name": f"Account{i}",
                    "principal_type": "USER" if i % 2 == 0 else "GROUP",
                }
                assignments.append(assignment)
            return assignments

        @staticmethod
        def create_csv_data(assignments):
            """Create CSV data from assignments."""
            if not assignments:
                return ""

            headers = ["principal_name", "permission_set_name", "account_name", "principal_type"]
            csv_lines = [",".join(headers)]

            for assignment in assignments:
                line = ",".join(
                    [
                        assignment["principal_name"],
                        assignment["permission_set_name"],
                        assignment["account_name"],
                        assignment["principal_type"],
                    ]
                )
                csv_lines.append(line)

            return "\n".join(csv_lines)

        @staticmethod
        def create_json_data(assignments):
            """Create JSON data from assignments."""
            return {"assignments": assignments}

    return BulkOperationFactory()
