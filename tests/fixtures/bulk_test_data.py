"""Test fixtures for bulk operations testing.

This module provides test data fixtures for bulk operations tests,
including CSV and JSON input files with various scenarios.
"""
import csv
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List


class BulkTestDataFixtures:
    """Test data fixtures for bulk operations."""

    @staticmethod
    def create_csv_file(assignments: List[Dict[str, Any]], suffix: str = ".csv") -> Path:
        """Create a temporary CSV file with assignment data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            if assignments:
                # Get all unique keys from assignments
                fieldnames = set()
                for assignment in assignments:
                    fieldnames.update(assignment.keys())
                fieldnames = sorted(list(fieldnames))

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(assignments)

            return Path(f.name)

    @staticmethod
    def create_json_file(assignments: List[Dict[str, Any]], suffix: str = ".json") -> Path:
        """Create a temporary JSON file with assignment data."""
        data = {"assignments": assignments}

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            json.dump(data, f, indent=2)
            return Path(f.name)

    @staticmethod
    def get_valid_user_assignments() -> List[Dict[str, Any]]:
        """Get valid user assignment test data."""
        return [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
            },
            {
                "principal_name": "jane.smith",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Development",
                "principal_type": "USER",
            },
        ]

    @staticmethod
    def get_valid_group_assignments() -> List[Dict[str, Any]]:
        """Get valid group assignment test data."""
        return [
            {
                "principal_name": "Developers",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Development",
                "principal_type": "GROUP",
            },
            {
                "principal_name": "Administrators",
                "permission_set_name": "AdministratorAccess",
                "account_name": "Production",
                "principal_type": "GROUP",
            },
        ]

    @staticmethod
    def get_mixed_assignments() -> List[Dict[str, Any]]:
        """Get mixed user and group assignment test data."""
        return [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
            },
            {
                "principal_name": "Developers",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Development",
                "principal_type": "GROUP",
            },
            {
                "principal_name": "jane.smith",
                "permission_set_name": "DataAnalystAccess",
                "account_name": "Analytics",
                "principal_type": "USER",
            },
        ]

    @staticmethod
    def get_assignments_with_validation_errors() -> List[Dict[str, Any]]:
        """Get assignment data that will cause validation errors."""
        return [
            {
                "principal_name": "",  # Empty principal name
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
            },
            {
                "principal_name": "john.doe",
                "permission_set_name": "",  # Empty permission set name
                "account_name": "Production",
                "principal_type": "USER",
            },
            {
                "principal_name": "jane.smith",
                "permission_set_name": "PowerUserAccess",
                "account_name": "",  # Empty account name
                "principal_type": "USER",
            },
        ]

    @staticmethod
    def get_assignments_with_missing_columns() -> List[Dict[str, Any]]:
        """Get assignment data with missing required columns."""
        return [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                # Missing account_name
                "principal_type": "USER",
            },
            {
                "principal_name": "jane.smith",
                # Missing permission_set_name
                "account_name": "Production",
                "principal_type": "USER",
            },
        ]

    @staticmethod
    def get_large_assignment_dataset(size: int = 100) -> List[Dict[str, Any]]:
        """Generate a large dataset for performance testing."""
        assignments = []

        for i in range(size):
            assignments.append(
                {
                    "principal_name": f"user{i:04d}",
                    "permission_set_name": f"PermissionSet{i % 10}",
                    "account_name": f"Account{i % 5}",
                    "principal_type": "USER",
                }
            )

        return assignments

    @staticmethod
    def get_assignments_with_special_characters() -> List[Dict[str, Any]]:
        """Get assignment data with special characters for edge case testing."""
        return [
            {
                "principal_name": "user.with-special_chars@domain.com",
                "permission_set_name": "Permission-Set_With.Special@Chars",
                "account_name": "Account With Spaces",
                "principal_type": "USER",
            },
            {
                "principal_name": "group/with/slashes",
                "permission_set_name": "Permission:Set:With:Colons",
                "account_name": "Account-With-Dashes",
                "principal_type": "GROUP",
            },
        ]

    @staticmethod
    def get_assignments_with_optional_fields() -> List[Dict[str, Any]]:
        """Get assignment data with optional fields populated."""
        return [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_type": "USER",
                "principal_id": "user-123456789012",
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "account_id": "123456789012",
            },
            {
                "principal_name": "Developers",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Development",
                "principal_type": "GROUP",
                "principal_id": "group-123456789012",
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-789",
                "account_id": "123456789013",
            },
        ]

    @staticmethod
    def create_malformed_csv_file() -> Path:
        """Create a malformed CSV file for error testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            # Write malformed CSV content
            f.write("principal_name,permission_set_name,account_name\n")
            f.write("john.doe,ReadOnlyAccess\n")  # Missing column
            f.write('jane.smith,"PowerUserAccess,Production\n')  # Unclosed quote
            return Path(f.name)

    @staticmethod
    def create_malformed_json_file() -> Path:
        """Create a malformed JSON file for error testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write malformed JSON content
            f.write("{\n")
            f.write('  "assignments": [\n')
            f.write("    {\n")
            f.write('      "principal_name": "john.doe",\n')
            f.write('      "permission_set_name": "ReadOnlyAccess"\n')
            f.write('      "account_name": "Production"\n')  # Missing comma
            f.write("    }\n")
            f.write("  ]\n")
            # Missing closing brace
            return Path(f.name)

    @staticmethod
    def create_empty_csv_file() -> Path:
        """Create an empty CSV file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            # Write only headers
            f.write("principal_name,permission_set_name,account_name,principal_type\n")
            return Path(f.name)

    @staticmethod
    def create_empty_json_file() -> Path:
        """Create an empty JSON file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"assignments": []}, f)
            return Path(f.name)


class MockAWSResponses:
    """Mock AWS API responses for testing."""

    @staticmethod
    def get_successful_user_resolution():
        """Get mock response for successful user resolution."""
        return {
            "Users": [
                {
                    "UserId": "user-123456789012",
                    "UserName": "john.doe",
                    "DisplayName": "John Doe",
                    "Name": {"GivenName": "John", "FamilyName": "Doe"},
                    "Emails": [{"Value": "john.doe@example.com", "Type": "work", "Primary": True}],
                }
            ]
        }

    @staticmethod
    def get_successful_group_resolution():
        """Get mock response for successful group resolution."""
        return {
            "Groups": [
                {
                    "GroupId": "group-123456789012",
                    "DisplayName": "Developers",
                    "Description": "Development team group",
                }
            ]
        }

    @staticmethod
    def get_successful_permission_set_resolution():
        """Get mock response for successful permission set resolution."""
        return {
            "PermissionSets": [
                {
                    "Name": "ReadOnlyAccess",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                    "Description": "Read-only access permission set",
                    "CreatedDate": "2023-01-01T00:00:00Z",
                    "SessionDuration": "PT8H",
                }
            ]
        }

    @staticmethod
    def get_successful_account_resolution():
        """Get mock response for successful account resolution."""
        return {
            "Accounts": [
                {
                    "Id": "123456789012",
                    "Arn": "arn:aws:organizations::123456789012:account/o-example123456/123456789012",
                    "Email": "production@example.com",
                    "Name": "Production",
                    "Status": "ACTIVE",
                    "JoinedMethod": "INVITED",
                    "JoinedTimestamp": "2023-01-01T00:00:00Z",
                }
            ]
        }

    @staticmethod
    def get_successful_assignment_creation():
        """Get mock response for successful assignment creation."""
        return {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-123456789012",
                "FailureReason": None,
                "TargetId": "123456789012",
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "PrincipalType": "USER",
                "PrincipalId": "user-123456789012",
                "CreatedDate": "2023-01-01T00:00:00Z",
            }
        }

    @staticmethod
    def get_successful_assignment_deletion():
        """Get mock response for successful assignment deletion."""
        return {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-123456789012",
                "FailureReason": None,
                "TargetId": "123456789012",
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "PrincipalType": "USER",
                "PrincipalId": "user-123456789012",
                "CreatedDate": "2023-01-01T00:00:00Z",
            }
        }

    @staticmethod
    def get_existing_assignments():
        """Get mock response for existing assignments."""
        return {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                    "PrincipalId": "user-123456789012",
                    "PrincipalType": "USER",
                }
            ]
        }

    @staticmethod
    def get_empty_assignments():
        """Get mock response for no existing assignments."""
        return {"AccountAssignments": []}
