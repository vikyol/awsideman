"""AWS Organizations test fixtures and data for awsideman tests."""

from datetime import datetime

import pytest


@pytest.fixture
def sample_account_data():
    """Sample AWS account data for testing."""
    return {
        "Id": "123456789012",
        "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/123456789012",
        "Email": "prod@company.com",
        "Name": "Production",
        "Status": "ACTIVE",
        "JoinedDate": datetime(2023, 1, 1, 0, 0, 0),
        "JoinedMethod": "INVITED",
    }


@pytest.fixture
def sample_organizational_unit_data():
    """Sample organizational unit data for testing."""
    return {
        "Id": "ou-1234567890",
        "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1234567890",
        "Name": "Production",
        "Description": "Production environment accounts",
    }


@pytest.fixture
def sample_root_data():
    """Sample root organizational unit data for testing."""
    return {
        "Id": "r-1234",
        "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234",
        "Name": "Root",
        "PolicyTypes": [{"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}],
    }


@pytest.fixture
def sample_accounts_list():
    """Sample list of AWS accounts for testing."""
    return [
        {
            "Id": "123456789012",
            "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/123456789012",
            "Email": "prod@company.com",
            "Name": "Production",
            "Status": "ACTIVE",
            "JoinedDate": datetime(2023, 1, 1, 0, 0, 0),
            "JoinedMethod": "INVITED",
        },
        {
            "Id": "098765432109",
            "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/098765432109",
            "Email": "dev@company.com",
            "Name": "Development",
            "Status": "ACTIVE",
            "JoinedDate": datetime(2023, 1, 2, 0, 0, 0),
            "JoinedMethod": "INVITED",
        },
        {
            "Id": "112233445566",
            "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/112233445566",
            "Email": "staging@company.com",
            "Name": "Staging",
            "Status": "ACTIVE",
            "JoinedDate": datetime(2023, 1, 3, 0, 0, 0),
            "JoinedMethod": "INVITED",
        },
    ]


@pytest.fixture
def sample_organizational_units_list():
    """Sample list of organizational units for testing."""
    return [
        {
            "Id": "ou-1234567890",
            "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1234567890",
            "Name": "Production",
            "Description": "Production environment accounts",
        },
        {
            "Id": "ou-0987654321",
            "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-0987654321",
            "Name": "Development",
            "Description": "Development environment accounts",
        },
        {
            "Id": "ou-1122334455",
            "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1122334455",
            "Name": "Staging",
            "Description": "Staging environment accounts",
        },
    ]


@pytest.fixture
def sample_organization_hierarchy():
    """Sample organization hierarchy for testing."""
    return {
        "root": {
            "id": "r-1234",
            "name": "Root",
            "children": [
                {
                    "id": "ou-1234567890",
                    "name": "Production",
                    "type": "ORGANIZATIONAL_UNIT",
                    "children": [
                        {
                            "id": "123456789012",
                            "name": "Production",
                            "type": "ACCOUNT",
                            "email": "prod@company.com",
                        }
                    ],
                },
                {
                    "id": "ou-0987654321",
                    "name": "Development",
                    "type": "ORGANIZATIONAL_UNIT",
                    "children": [
                        {
                            "id": "098765432109",
                            "name": "Development",
                            "type": "ACCOUNT",
                            "email": "dev@company.com",
                        }
                    ],
                },
            ],
        }
    }


@pytest.fixture
def sample_account_tags():
    """Sample account tags for testing."""
    return [
        {"Key": "Environment", "Value": "Production"},
        {"Key": "Team", "Value": "Operations"},
        {"Key": "CostCenter", "Value": "CC-001"},
    ]


@pytest.fixture
def organizations_factory():
    """Factory for creating AWS Organizations test data."""

    class OrganizationsFactory:
        @staticmethod
        def create_account(
            account_id="123456789012", name="TestAccount", email="test@company.com", status="ACTIVE"
        ):
            """Create an AWS account for testing."""
            return {
                "Id": account_id,
                "Arn": f"arn:aws:organizations::123456789012:account/o-1234567890/{account_id}",
                "Email": email,
                "Name": name,
                "Status": status,
                "JoinedDate": datetime(2023, 1, 1, 0, 0, 0),
                "JoinedMethod": "INVITED",
            }

        @staticmethod
        def create_organizational_unit(
            ou_id="ou-123", name="TestOU", description="Test organizational unit"
        ):
            """Create an organizational unit for testing."""
            return {
                "Id": ou_id,
                "Arn": f"arn:aws:organizations::123456789012:ou/o-1234567890/{ou_id}",
                "Name": name,
                "Description": description,
            }

        @staticmethod
        def create_root(root_id="r-1234", name="Root"):
            """Create a root organizational unit for testing."""
            return {
                "Id": root_id,
                "Arn": f"arn:aws:organizations::123456789012:root/o-1234567890/{root_id}",
                "Name": name,
                "PolicyTypes": [{"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}],
            }

        @staticmethod
        def create_account_tag(key="Environment", value="Test"):
            """Create an account tag for testing."""
            return {"Key": key, "Value": value}

        @staticmethod
        def create_accounts_batch(count=5, base_name="TestAccount"):
            """Create multiple AWS accounts for testing."""
            accounts = []
            for i in range(count):
                name = f"{base_name}{i}"
                account_id = f"12345678901{i}"
                accounts.append(
                    {
                        "Id": account_id,
                        "Arn": f"arn:aws:organizations::123456789012:account/o-1234567890/{account_id}",
                        "Email": f"{name.lower()}@company.com",
                        "Name": name,
                        "Status": "ACTIVE",
                        "JoinedDate": datetime(2023, 1, 1, 0, 0, 0),
                        "JoinedMethod": "INVITED",
                    }
                )
            return accounts

        @staticmethod
        def create_organizational_units_batch(count=5, base_name="TestOU"):
            """Create multiple organizational units for testing."""
            ous = []
            for i in range(count):
                name = f"{base_name}{i}"
                ou_id = f"ou-{i}"
                ous.append(
                    {
                        "Id": ou_id,
                        "Arn": f"arn:aws:organizations::123456789012:ou/o-1234567890/{ou_id}",
                        "Name": name,
                        "Description": f"Test organizational unit {i}",
                    }
                )
            return ous

        @staticmethod
        def create_hierarchy_structure(depth=3, accounts_per_ou=2):
            """Create a hierarchical organization structure for testing."""

            def create_level(level, parent_id, max_depth):
                if level >= max_depth:
                    return []

                ous = []
                for i in range(2):  # 2 OUs per level
                    ou_id = f"ou-{parent_id}-{i}"
                    ou = {
                        "id": ou_id,
                        "name": f"Level{level}OU{i}",
                        "type": "ORGANIZATIONAL_UNIT",
                        "children": [],
                    }

                    # Add accounts to this OU
                    for j in range(accounts_per_ou):
                        account_id = f"12345678901{j}"
                        account = {
                            "id": account_id,
                            "name": f"Account{j}",
                            "type": "ACCOUNT",
                            "email": f"account{j}@company.com",
                        }
                        ou["children"].append(account)

                    # Add child OUs
                    if level < max_depth - 1:
                        ou["children"].extend(create_level(level + 1, ou_id, max_depth))

                    ous.append(ou)

                return ous

            root = {"id": "r-1234", "name": "Root", "children": create_level(0, "root", depth)}

            return {"root": root}

    return OrganizationsFactory()
