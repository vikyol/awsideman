"""Tests for data models and hierarchy builder functionality."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import (
    OrganizationsClient,
    _account_matches_ou_filter,
    _account_matches_tag_filter,
    _build_children_recursive,
    _calculate_ou_path,
    _create_org_node_from_data,
    _get_all_accounts_in_organization,
    build_organization_hierarchy,
    get_account_details,
    search_accounts,
)
from src.awsideman.utils.models import (
    AccountDetails,
    HierarchyPath,
    NodeType,
    OrgNode,
    PolicyInfo,
    PolicyType,
)


class TestOrgNode:
    """Test OrgNode data model."""

    def test_org_node_creation_basic(self):
        """Test basic OrgNode creation."""
        node = OrgNode(id="r-1234567890", name="Root", type=NodeType.ROOT, children=[])

        assert node.id == "r-1234567890"
        assert node.name == "Root"
        assert node.type == NodeType.ROOT
        assert node.children == []

    def test_org_node_post_init_none_children(self):
        """Test that __post_init__ handles None children."""
        node = OrgNode(id="r-1234567890", name="Root", type=NodeType.ROOT, children=None)

        assert node.children == []

    def test_add_child(self):
        """Test adding child nodes."""
        parent = OrgNode("r-1234", "Root", NodeType.ROOT, [])
        child = OrgNode("ou-5678", "Engineering", NodeType.OU, [])

        parent.add_child(child)

        assert len(parent.children) == 1
        assert parent.children[0] == child

    def test_is_root(self):
        """Test is_root method."""
        root_node = OrgNode("r-1234", "Root", NodeType.ROOT, [])
        ou_node = OrgNode("ou-5678", "Engineering", NodeType.OU, [])
        account_node = OrgNode("111111111111", "dev-account", NodeType.ACCOUNT, [])

        assert root_node.is_root() is True
        assert ou_node.is_root() is False
        assert account_node.is_root() is False

    def test_is_ou(self):
        """Test is_ou method."""
        root_node = OrgNode("r-1234", "Root", NodeType.ROOT, [])
        ou_node = OrgNode("ou-5678", "Engineering", NodeType.OU, [])
        account_node = OrgNode("111111111111", "dev-account", NodeType.ACCOUNT, [])

        assert root_node.is_ou() is False
        assert ou_node.is_ou() is True
        assert account_node.is_ou() is False

    def test_is_account(self):
        """Test is_account method."""
        root_node = OrgNode("r-1234", "Root", NodeType.ROOT, [])
        ou_node = OrgNode("ou-5678", "Engineering", NodeType.OU, [])
        account_node = OrgNode("111111111111", "dev-account", NodeType.ACCOUNT, [])

        assert root_node.is_account() is False
        assert ou_node.is_account() is False
        assert account_node.is_account() is True


class TestAccountDetails:
    """Test AccountDetails data model."""

    def test_account_details_creation_basic(self):
        """Test basic AccountDetails creation."""
        joined_time = datetime(2021, 1, 1, tzinfo=timezone.utc)
        tags = {"Environment": "Development", "Team": "Engineering"}
        ou_path = ["Root", "Engineering"]

        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=joined_time,
            tags=tags,
            ou_path=ou_path,
        )

        assert account.id == "111111111111"
        assert account.name == "dev-account"
        assert account.email == "dev@example.com"
        assert account.status == "ACTIVE"
        assert account.joined_timestamp == joined_time
        assert account.tags == tags
        assert account.ou_path == ou_path

    def test_account_details_post_init_none_values(self):
        """Test that __post_init__ handles None values."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags=None,
            ou_path=None,
        )

        assert account.tags == {}
        assert account.ou_path == []

    def test_get_tag_existing(self):
        """Test get_tag method with existing tag."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=[],
        )

        assert account.get_tag("Environment") == "Development"
        assert account.get_tag("Team") == "Engineering"

    def test_get_tag_nonexistent(self):
        """Test get_tag method with nonexistent tag."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development"},
            ou_path=[],
        )

        assert account.get_tag("NonExistent") is None
        assert account.get_tag("NonExistent", "default") == "default"

    def test_has_tag_key_only(self):
        """Test has_tag method checking key existence only."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=[],
        )

        assert account.has_tag("Environment") is True
        assert account.has_tag("Team") is True
        assert account.has_tag("NonExistent") is False

    def test_has_tag_key_and_value(self):
        """Test has_tag method checking key and value."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=[],
        )

        assert account.has_tag("Environment", "Development") is True
        assert account.has_tag("Environment", "Production") is False
        assert account.has_tag("Team", "Engineering") is True
        assert account.has_tag("Team", "Marketing") is False
        assert account.has_tag("NonExistent", "Value") is False


class TestPolicyInfo:
    """Test PolicyInfo data model."""

    def test_policy_info_creation_basic(self):
        """Test basic PolicyInfo creation."""
        policy = PolicyInfo(
            id="p-1234567890",
            name="FullAWSAccess",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Allows access to all AWS services",
            aws_managed=True,
            attachment_point="r-1234567890",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )

        assert policy.id == "p-1234567890"
        assert policy.name == "FullAWSAccess"
        assert policy.type == PolicyType.SERVICE_CONTROL_POLICY
        assert policy.description == "Allows access to all AWS services"
        assert policy.aws_managed is True
        assert policy.attachment_point == "r-1234567890"
        assert policy.attachment_point_name == "Root"
        assert policy.effective_status == "ENABLED"

    def test_policy_info_post_init_none_values(self):
        """Test that __post_init__ handles None values."""
        policy = PolicyInfo(
            id="p-1234567890",
            name="FullAWSAccess",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description=None,
            aws_managed=True,
            attachment_point="r-1234567890",
            attachment_point_name=None,
            effective_status="ENABLED",
        )

        assert policy.description == ""
        assert policy.attachment_point_name == "r-1234567890"

    def test_is_scp(self):
        """Test is_scp method."""
        scp = PolicyInfo(
            id="p-scp123",
            name="SCP Policy",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )

        rcp = PolicyInfo(
            id="p-rcp123",
            name="RCP Policy",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="",
            aws_managed=False,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )

        assert scp.is_scp() is True
        assert rcp.is_scp() is False

    def test_is_rcp(self):
        """Test is_rcp method."""
        scp = PolicyInfo(
            id="p-scp123",
            name="SCP Policy",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )

        rcp = PolicyInfo(
            id="p-rcp123",
            name="RCP Policy",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="",
            aws_managed=False,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )

        assert scp.is_rcp() is False
        assert rcp.is_rcp() is True


class TestHierarchyPath:
    """Test HierarchyPath data model."""

    def test_hierarchy_path_creation_basic(self):
        """Test basic HierarchyPath creation."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.ids == ["r-1234", "ou-5678", "111111111111"]
        assert path.names == ["Root", "Engineering", "dev-account"]
        assert path.types == [NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT]

    def test_hierarchy_path_post_init_none_values(self):
        """Test that __post_init__ handles None values."""
        path = HierarchyPath(ids=None, names=None, types=None)

        assert path.ids == []
        assert path.names == []
        assert path.types == []

    def test_hierarchy_path_post_init_unequal_lengths(self):
        """Test that __post_init__ equalizes list lengths."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678"],
            names=["Root"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        # All lists should be padded to length 3
        assert len(path.ids) == 3
        assert len(path.names) == 3
        assert len(path.types) == 3

        assert path.ids == ["r-1234", "ou-5678", ""]
        assert path.names == ["Root", "", ""]
        assert path.types == [NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT]

    def test_depth(self):
        """Test depth method."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.depth() == 3

    def test_get_path_string_default_separator(self):
        """Test get_path_string with default separator."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.get_path_string() == "Root → Engineering → dev-account"

    def test_get_path_string_custom_separator(self):
        """Test get_path_string with custom separator."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.get_path_string(" / ") == "Root / Engineering / dev-account"

    def test_get_id_path_string_default_separator(self):
        """Test get_id_path_string with default separator."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.get_id_path_string() == "r-1234/ou-5678/111111111111"

    def test_get_id_path_string_custom_separator(self):
        """Test get_id_path_string with custom separator."""
        path = HierarchyPath(
            ids=["r-1234", "ou-5678", "111111111111"],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT],
        )

        assert path.get_id_path_string(" -> ") == "r-1234 -> ou-5678 -> 111111111111"


class TestCreateOrgNodeFromData:
    """Test _create_org_node_from_data function."""

    def test_create_root_node(self):
        """Test creating root node from data."""
        data = {"Id": "r-1234567890", "Name": "Root"}

        node = _create_org_node_from_data(data, NodeType.ROOT)

        assert node.id == "r-1234567890"
        assert node.name == "Root"
        assert node.type == NodeType.ROOT
        assert node.children == []

    def test_create_root_node_no_name(self):
        """Test creating root node without name (uses default)."""
        data = {"Id": "r-1234567890"}

        node = _create_org_node_from_data(data, NodeType.ROOT)

        assert node.id == "r-1234567890"
        assert node.name == "Root-r-1234567890"
        assert node.type == NodeType.ROOT

    def test_create_ou_node(self):
        """Test creating OU node from data."""
        data = {"Id": "ou-1234567890-abcdefgh", "Name": "Engineering"}

        node = _create_org_node_from_data(data, NodeType.OU)

        assert node.id == "ou-1234567890-abcdefgh"
        assert node.name == "Engineering"
        assert node.type == NodeType.OU
        assert node.children == []

    def test_create_ou_node_missing_name(self):
        """Test creating OU node without name raises error."""
        data = {"Id": "ou-1234567890-abcdefgh"}

        with pytest.raises(ValueError, match="Missing required 'Name' field in OU data"):
            _create_org_node_from_data(data, NodeType.OU)

    def test_create_account_node(self):
        """Test creating account node from data."""
        data = {"Id": "111111111111", "Name": "dev-account", "Email": "dev@example.com"}

        node = _create_org_node_from_data(data, NodeType.ACCOUNT)

        assert node.id == "111111111111"
        assert node.name == "dev-account"
        assert node.type == NodeType.ACCOUNT
        assert node.children == []

    def test_create_account_node_no_name_uses_email(self):
        """Test creating account node without name uses email as fallback."""
        data = {"Id": "111111111111", "Email": "dev@example.com"}

        node = _create_org_node_from_data(data, NodeType.ACCOUNT)

        assert node.id == "111111111111"
        assert node.name == "dev@example.com"
        assert node.type == NodeType.ACCOUNT

    def test_create_account_node_no_name_no_email(self):
        """Test creating account node without name or email uses default."""
        data = {"Id": "111111111111"}

        node = _create_org_node_from_data(data, NodeType.ACCOUNT)

        assert node.id == "111111111111"
        assert node.name == "Account-111111111111"
        assert node.type == NodeType.ACCOUNT

    def test_create_node_missing_id(self):
        """Test creating node without ID raises error."""
        data = {"Name": "Test Node"}

        with pytest.raises(ValueError, match="Missing required 'Id' field"):
            _create_org_node_from_data(data, NodeType.ROOT)

    def test_create_node_unknown_type(self):
        """Test creating node with unknown type raises error."""
        data = {"Id": "test-id", "Name": "Test Node"}

        with pytest.raises(ValueError, match="Unknown node type"):
            _create_org_node_from_data(data, "UNKNOWN_TYPE")


@pytest.fixture
def mock_organizations_client():
    """Create a mock OrganizationsClient."""
    return MagicMock(spec=OrganizationsClient)


class TestBuildOrganizationHierarchy:
    """Test build_organization_hierarchy function."""

    def test_build_hierarchy_success(self, mock_organizations_client):
        """Test successful hierarchy building."""
        # Mock the API responses
        mock_organizations_client.list_roots.return_value = [{"Id": "r-1234567890", "Name": "Root"}]

        def mock_list_ous(parent_id):
            if parent_id == "r-1234567890":
                return [{"Id": "ou-1234567890-abcdefgh", "Name": "Engineering"}]
            else:
                return []

        def mock_list_accounts(parent_id):
            if parent_id == "r-1234567890":
                return []  # No accounts under root
            elif parent_id == "ou-1234567890-abcdefgh":
                return [{"Id": "111111111111", "Name": "dev-account", "Email": "dev@example.com"}]
            else:
                return []

        mock_organizations_client.list_organizational_units_for_parent.side_effect = mock_list_ous
        mock_organizations_client.list_accounts_for_parent.side_effect = mock_list_accounts

        # Build hierarchy
        hierarchy = build_organization_hierarchy(mock_organizations_client)

        # Verify structure
        assert len(hierarchy) == 1
        root = hierarchy[0]
        assert root.id == "r-1234567890"
        assert root.name == "Root"
        assert root.type == NodeType.ROOT
        assert len(root.children) == 1

        ou = root.children[0]
        assert ou.id == "ou-1234567890-abcdefgh"
        assert ou.name == "Engineering"
        assert ou.type == NodeType.OU
        assert len(ou.children) == 1

        account = ou.children[0]
        assert account.id == "111111111111"
        assert account.name == "dev-account"
        assert account.type == NodeType.ACCOUNT
        assert len(account.children) == 0

    def test_build_hierarchy_no_roots(self, mock_organizations_client):
        """Test hierarchy building with no roots."""
        mock_organizations_client.list_roots.return_value = []

        with pytest.raises(ValueError, match="No organization roots found"):
            build_organization_hierarchy(mock_organizations_client)

    def test_build_hierarchy_client_error(self, mock_organizations_client):
        """Test hierarchy building with client error."""
        mock_organizations_client.list_roots.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}, "ListRoots"
        )

        with pytest.raises(ClientError):
            build_organization_hierarchy(mock_organizations_client)

    @patch("src.awsideman.aws_clients.manager.console")
    def test_build_hierarchy_partial_failure(self, mock_console, mock_organizations_client):
        """Test hierarchy building with partial failures."""
        # Mock successful root listing
        mock_organizations_client.list_roots.return_value = [
            {"Id": "r-1234567890", "Name": "Root"},
            {"Id": "r-0987654321", "Name": "BadRoot"},  # This will fail
        ]

        # Mock OU listing - first succeeds, second fails
        def mock_list_ous(parent_id):
            if parent_id == "r-1234567890":
                return [{"Id": "ou-1234567890-abcdefgh", "Name": "Engineering"}]
            elif parent_id == "r-0987654321":
                raise ClientError(
                    {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
                    "ListOrganizationalUnitsForParent",
                )
            else:
                return []

        def mock_list_accounts(parent_id):
            if parent_id == "r-0987654321":
                raise ClientError(
                    {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
                    "ListAccountsForParent",
                )
            else:
                return []

        mock_organizations_client.list_organizational_units_for_parent.side_effect = mock_list_ous
        mock_organizations_client.list_accounts_for_parent.side_effect = mock_list_accounts

        # Build hierarchy - should succeed with both roots (second one just has no children)
        hierarchy = build_organization_hierarchy(mock_organizations_client)

        # Should have both roots
        assert len(hierarchy) == 2
        root_ids = [root.id for root in hierarchy]
        assert "r-1234567890" in root_ids
        assert "r-0987654321" in root_ids

        # Should have printed warning about the failed children
        mock_console.print.assert_called()

    def test_build_hierarchy_all_roots_fail(self, mock_organizations_client):
        """Test hierarchy building when all roots fail."""
        mock_organizations_client.list_roots.return_value = [{"Id": "r-1234567890", "Name": "Root"}]

        # Mock failure when building children
        mock_organizations_client.list_organizational_units_for_parent.side_effect = Exception(
            "Test error"
        )
        mock_organizations_client.list_accounts_for_parent.side_effect = Exception("Test error")

        # Should still return the root node even if children fail
        hierarchy = build_organization_hierarchy(mock_organizations_client)

        assert len(hierarchy) == 1
        assert hierarchy[0].id == "r-1234567890"
        assert len(hierarchy[0].children) == 0  # No children due to failures


class TestBuildChildrenRecursive:
    """Test _build_children_recursive function."""

    def test_build_children_success(self, mock_organizations_client):
        """Test successful children building."""
        parent = OrgNode("r-1234567890", "Root", NodeType.ROOT, [])

        def mock_list_ous(parent_id):
            if parent_id == "r-1234567890":
                return [{"Id": "ou-1234567890-abcdefgh", "Name": "Engineering"}]
            else:
                return []

        def mock_list_accounts(parent_id):
            if parent_id == "r-1234567890":
                return []  # No accounts under root
            elif parent_id == "ou-1234567890-abcdefgh":
                return [{"Id": "111111111111", "Name": "dev-account", "Email": "dev@example.com"}]
            else:
                return []

        mock_organizations_client.list_organizational_units_for_parent.side_effect = mock_list_ous
        mock_organizations_client.list_accounts_for_parent.side_effect = mock_list_accounts

        # Build children
        _build_children_recursive(mock_organizations_client, parent)

        # Verify structure
        assert len(parent.children) == 1
        ou = parent.children[0]
        assert ou.id == "ou-1234567890-abcdefgh"
        assert ou.name == "Engineering"
        assert len(ou.children) == 1

        account = ou.children[0]
        assert account.id == "111111111111"
        assert account.name == "dev-account"

    @patch("src.awsideman.aws_clients.manager.console")
    def test_build_children_ou_failure(self, mock_console, mock_organizations_client):
        """Test children building with OU processing failure."""
        parent = OrgNode("r-1234567890", "Root", NodeType.ROOT, [])

        # Mock API responses - OU listing succeeds but OU processing fails
        mock_organizations_client.list_organizational_units_for_parent.return_value = [
            {"Id": "ou-bad"},  # Missing name, will cause error
            {"Id": "ou-good", "Name": "Engineering"},
        ]
        mock_organizations_client.list_accounts_for_parent.side_effect = [
            [],  # No accounts under root
            [],  # No accounts under good OU
        ]

        # Build children
        _build_children_recursive(mock_organizations_client, parent)

        # Should have one child (the good OU) and warning printed
        assert len(parent.children) == 1
        assert parent.children[0].id == "ou-good"
        mock_console.print.assert_called()

    @patch("src.awsideman.aws_clients.manager.console")
    def test_build_children_account_failure(self, mock_console, mock_organizations_client):
        """Test children building with account processing failure."""
        parent = OrgNode("r-1234567890", "Root", NodeType.ROOT, [])

        # Mock API responses
        mock_organizations_client.list_organizational_units_for_parent.return_value = []
        mock_organizations_client.list_accounts_for_parent.return_value = [
            {"Id": "111111111111"},  # Missing name and email, will use default
            {"Name": "good-account", "Email": "good@example.com"},  # Missing ID, will cause error
        ]

        # Build children
        _build_children_recursive(mock_organizations_client, parent)

        # Should have one child (the account with ID) and warning printed
        assert len(parent.children) == 1
        assert parent.children[0].id == "111111111111"
        mock_console.print.assert_called()

    @patch("src.awsideman.aws_clients.manager.console")
    def test_build_children_api_failure(self, mock_console, mock_organizations_client):
        """Test children building with API failure."""
        parent = OrgNode("r-1234567890", "Root", NodeType.ROOT, [])

        # Mock API failure
        mock_organizations_client.list_organizational_units_for_parent.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "ListOrganizationalUnitsForParent",
        )

        # Build children - should not raise exception
        _build_children_recursive(mock_organizations_client, parent)

        # Should have no children and warning printed
        assert len(parent.children) == 0
        mock_console.print.assert_called()


class TestGetAccountDetails:
    """Test get_account_details function."""

    def test_get_account_details_success(self, mock_organizations_client):
        """Test successful account details retrieval."""
        joined_time = datetime(2021, 1, 1, tzinfo=timezone.utc)

        # Mock API responses
        mock_organizations_client.describe_account.return_value = {
            "Id": "111111111111",
            "Name": "dev-account",
            "Email": "dev@example.com",
            "Status": "ACTIVE",
            "JoinedTimestamp": joined_time,
        }
        mock_organizations_client.list_tags_for_resource.return_value = [
            {"Key": "Environment", "Value": "Development"},
            {"Key": "Team", "Value": "Engineering"},
        ]

        # Mock OU path calculation
        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_calc_path:
            mock_calc_path.return_value = ["Root", "Engineering"]

            # Get account details
            details = get_account_details(mock_organizations_client, "111111111111")

            # Verify result
            assert details.id == "111111111111"
            assert details.name == "dev-account"
            assert details.email == "dev@example.com"
            assert details.status == "ACTIVE"
            assert details.joined_timestamp == joined_time
            assert details.tags == {"Environment": "Development", "Team": "Engineering"}
            assert details.ou_path == ["Root", "Engineering"]

    def test_get_account_details_no_account(self, mock_organizations_client):
        """Test account details with account not found."""
        mock_organizations_client.describe_account.return_value = {}

        with pytest.raises(ValueError, match="Account 111111111111 not found"):
            get_account_details(mock_organizations_client, "111111111111")

    def test_get_account_details_string_timestamp(self, mock_organizations_client):
        """Test account details with string timestamp."""
        # Mock API responses with string timestamp
        mock_organizations_client.describe_account.return_value = {
            "Id": "111111111111",
            "Name": "dev-account",
            "Email": "dev@example.com",
            "Status": "ACTIVE",
            "JoinedTimestamp": "2021-01-01T00:00:00Z",
        }
        mock_organizations_client.list_tags_for_resource.return_value = []

        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_calc_path:
            mock_calc_path.return_value = []

            details = get_account_details(mock_organizations_client, "111111111111")

            # Should parse string timestamp correctly (with timezone)
            from datetime import timezone

            expected_time = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            assert details.joined_timestamp == expected_time

    def test_get_account_details_no_timestamp(self, mock_organizations_client):
        """Test account details with no timestamp."""
        mock_organizations_client.describe_account.return_value = {
            "Id": "111111111111",
            "Name": "dev-account",
            "Email": "dev@example.com",
            "Status": "ACTIVE",
        }
        mock_organizations_client.list_tags_for_resource.return_value = []

        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_calc_path:
            mock_calc_path.return_value = []

            details = get_account_details(mock_organizations_client, "111111111111")

            # Should use datetime.min for missing timestamp
            assert details.joined_timestamp == datetime.min

    @patch("src.awsideman.aws_clients.manager.console")
    def test_get_account_details_tags_failure(self, mock_console, mock_organizations_client):
        """Test account details with tags retrieval failure."""
        mock_organizations_client.describe_account.return_value = {
            "Id": "111111111111",
            "Name": "dev-account",
            "Email": "dev@example.com",
            "Status": "ACTIVE",
            "JoinedTimestamp": datetime(2021, 1, 1, tzinfo=timezone.utc),
        }
        mock_organizations_client.list_tags_for_resource.side_effect = Exception("Tags error")

        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_calc_path:
            mock_calc_path.return_value = []

            details = get_account_details(mock_organizations_client, "111111111111")

            # Should have empty tags and warning printed
            assert details.tags == {}
            mock_console.print.assert_called()

    def test_get_account_details_client_error(self, mock_organizations_client):
        """Test account details with client error."""
        mock_organizations_client.describe_account.side_effect = ClientError(
            {"Error": {"Code": "AccountNotFoundException", "Message": "Account not found"}},
            "DescribeAccount",
        )

        with pytest.raises(ClientError):
            get_account_details(mock_organizations_client, "111111111111")


class TestCalculateOuPath:
    """Test _calculate_ou_path function."""

    def test_calculate_ou_path_success(self, mock_organizations_client):
        """Test successful OU path calculation."""

        # Mock the hierarchy traversal
        def mock_list_parents(child_id):
            if child_id == "111111111111":  # Account
                return [{"Id": "ou-1234567890-abcdefgh", "Type": "ORGANIZATIONAL_UNIT"}]
            elif child_id == "ou-1234567890-abcdefgh":  # OU
                return [{"Id": "r-1234567890", "Type": "ROOT"}]
            else:
                return []

        mock_organizations_client.list_parents.side_effect = mock_list_parents
        mock_organizations_client.list_roots.return_value = [{"Id": "r-1234567890", "Name": "Root"}]
        mock_organizations_client.list_organizational_units_for_parent.return_value = [
            {"Id": "ou-1234567890-abcdefgh", "Name": "Engineering"}
        ]

        path = _calculate_ou_path(mock_organizations_client, "111111111111")

        assert path == ["Root", "Engineering"]

    def test_calculate_ou_path_account_under_root(self, mock_organizations_client):
        """Test OU path calculation for account directly under root."""
        mock_organizations_client.list_parents.return_value = [
            {"Id": "r-1234567890", "Type": "ROOT"}
        ]
        mock_organizations_client.list_roots.return_value = [{"Id": "r-1234567890", "Name": "Root"}]

        path = _calculate_ou_path(mock_organizations_client, "111111111111")

        assert path == ["Root"]

    def test_calculate_ou_path_no_parents(self, mock_organizations_client):
        """Test OU path calculation with no parents."""
        mock_organizations_client.list_parents.return_value = []

        path = _calculate_ou_path(mock_organizations_client, "111111111111")

        assert path == []

    @patch("src.awsideman.aws_clients.manager.console")
    def test_calculate_ou_path_client_error(self, mock_console, mock_organizations_client):
        """Test OU path calculation with client error."""
        mock_organizations_client.list_parents.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}, "ListParents"
        )

        path = _calculate_ou_path(mock_organizations_client, "111111111111")

        assert path == []
        mock_console.print.assert_called()

    @patch("src.awsideman.aws_clients.manager.console")
    def test_calculate_ou_path_root_name_failure(self, mock_console, mock_organizations_client):
        """Test OU path calculation with root name retrieval failure."""
        mock_organizations_client.list_parents.return_value = [
            {"Id": "r-1234567890", "Type": "ROOT"}
        ]
        mock_organizations_client.list_roots.side_effect = Exception("Root error")

        path = _calculate_ou_path(mock_organizations_client, "111111111111")

        # Should use ID as fallback
        assert path == ["r-1234567890"]
        mock_console.print.assert_called()


class TestAccountMatchingFilters:
    """Test account matching filter functions."""

    def test_account_matches_ou_filter_direct_match(self):
        """Test OU filter with direct match."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={},
            ou_path=["Root", "Engineering", "Development"],
        )

        assert _account_matches_ou_filter(account, "Engineering") is True
        assert _account_matches_ou_filter(account, "Development") is True
        assert _account_matches_ou_filter(account, "Root") is True
        assert _account_matches_ou_filter(account, "Marketing") is False

    def test_account_matches_tag_filter_single_tag(self):
        """Test tag filter with single tag."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=[],
        )

        assert _account_matches_tag_filter(account, {"Environment": "Development"}) is True
        assert _account_matches_tag_filter(account, {"Team": "Engineering"}) is True
        assert _account_matches_tag_filter(account, {"Environment": "Production"}) is False
        assert _account_matches_tag_filter(account, {"NonExistent": "Value"}) is False

    def test_account_matches_tag_filter_multiple_tags(self):
        """Test tag filter with multiple tags."""
        account = AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering", "Project": "WebApp"},
            ou_path=[],
        )

        # All tags match
        assert (
            _account_matches_tag_filter(
                account, {"Environment": "Development", "Team": "Engineering"}
            )
            is True
        )

        # One tag doesn't match
        assert (
            _account_matches_tag_filter(
                account, {"Environment": "Development", "Team": "Marketing"}
            )
            is False
        )

        # Empty filter should match
        assert _account_matches_tag_filter(account, {}) is True


class TestSearchAccounts:
    """Test search_accounts function."""

    def test_search_accounts_success(self, mock_organizations_client):
        """Test successful account search."""
        # Mock get_all_accounts_in_organization
        with patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all:
            mock_get_all.return_value = [
                {"Id": "111111111111", "Name": "dev-account"},
                {"Id": "222222222222", "Name": "prod-account"},
                {"Id": "333333333333", "Name": "test-account"},
            ]

            # Mock get_account_details
            with patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details:
                mock_get_details.side_effect = [
                    AccountDetails(
                        id="111111111111",
                        name="dev-account",
                        email="dev@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={"Environment": "Development"},
                        ou_path=["Root", "Engineering"],
                    ),
                    AccountDetails(
                        id="333333333333",
                        name="test-account",
                        email="test@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={"Environment": "Testing"},
                        ou_path=["Root", "QA"],
                    ),
                ]

                # Search for accounts containing "dev" or "test"
                results = search_accounts(mock_organizations_client, "account")

                # Should return both matching accounts
                assert len(results) == 2
                assert results[0].name == "dev-account"
                assert results[1].name == "test-account"

    def test_search_accounts_empty_query(self, mock_organizations_client):
        """Test search with empty query."""
        with pytest.raises(ValueError, match="Search query cannot be empty"):
            search_accounts(mock_organizations_client, "")

        with pytest.raises(ValueError, match="Search query cannot be empty"):
            search_accounts(mock_organizations_client, "   ")

    def test_search_accounts_case_insensitive(self, mock_organizations_client):
        """Test case-insensitive search."""
        with patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all:
            mock_get_all.return_value = [
                {"Id": "111111111111", "Name": "DEV-Account"},
                {"Id": "222222222222", "Name": "prod-account"},
            ]

            with patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details:
                mock_get_details.return_value = AccountDetails(
                    id="111111111111",
                    name="DEV-Account",
                    email="dev@example.com",
                    status="ACTIVE",
                    joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                    tags={},
                    ou_path=[],
                )

                # Search with lowercase should match uppercase account name
                results = search_accounts(mock_organizations_client, "dev")

                assert len(results) == 1
                assert results[0].name == "DEV-Account"

    def test_search_accounts_with_ou_filter(self, mock_organizations_client):
        """Test search with OU filter."""
        with patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all:
            mock_get_all.return_value = [
                {"Id": "111111111111", "Name": "dev-account"},
                {"Id": "222222222222", "Name": "dev-account-2"},
            ]

            with patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details:
                mock_get_details.side_effect = [
                    AccountDetails(
                        id="111111111111",
                        name="dev-account",
                        email="dev@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={},
                        ou_path=["Root", "Engineering"],
                    ),
                    AccountDetails(
                        id="222222222222",
                        name="dev-account-2",
                        email="dev2@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={},
                        ou_path=["Root", "Marketing"],
                    ),
                ]

                # Search with OU filter
                results = search_accounts(mock_organizations_client, "dev", ou_filter="Engineering")

                # Should only return account in Engineering OU
                assert len(results) == 1
                assert results[0].id == "111111111111"

    def test_search_accounts_with_tag_filter(self, mock_organizations_client):
        """Test search with tag filter."""
        with patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all:
            mock_get_all.return_value = [
                {"Id": "111111111111", "Name": "dev-account"},
                {"Id": "222222222222", "Name": "dev-account-2"},
            ]

            with patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details:
                mock_get_details.side_effect = [
                    AccountDetails(
                        id="111111111111",
                        name="dev-account",
                        email="dev@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={"Environment": "Development"},
                        ou_path=[],
                    ),
                    AccountDetails(
                        id="222222222222",
                        name="dev-account-2",
                        email="dev2@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={"Environment": "Production"},
                        ou_path=[],
                    ),
                ]

                # Search with tag filter
                results = search_accounts(
                    mock_organizations_client, "dev", tag_filter={"Environment": "Development"}
                )

                # Should only return account with matching tag
                assert len(results) == 1
                assert results[0].id == "111111111111"

    @patch("src.awsideman.aws_clients.manager.console")
    def test_search_accounts_account_details_failure(self, mock_console, mock_organizations_client):
        """Test search with account details retrieval failure."""
        with patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all:
            mock_get_all.return_value = [
                {"Id": "111111111111", "Name": "dev-account"},
                {"Id": "222222222222", "Name": "good-account"},
            ]

            with patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details:

                def mock_details_side_effect(client, account_id):
                    if account_id == "111111111111":
                        raise Exception("Account details error")
                    return AccountDetails(
                        id="222222222222",
                        name="good-account",
                        email="good@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                        tags={},
                        ou_path=[],
                    )

                mock_get_details.side_effect = mock_details_side_effect

                # Search should continue despite one account failing
                results = search_accounts(mock_organizations_client, "account")

                # Should return only the successful account
                assert len(results) == 1
                assert results[0].id == "222222222222"

                # Should have printed warning
                mock_console.print.assert_called()


class TestGetAllAccountsInOrganization:
    """Test _get_all_accounts_in_organization function."""

    def test_get_all_accounts_success(self, mock_organizations_client):
        """Test successful retrieval of all accounts."""
        # Mock build_organization_hierarchy
        with patch("src.awsideman.aws_clients.manager.build_organization_hierarchy") as mock_build:
            # Create a mock hierarchy
            account1 = OrgNode("111111111111", "dev-account", NodeType.ACCOUNT, [])
            account2 = OrgNode("222222222222", "prod-account", NodeType.ACCOUNT, [])
            ou = OrgNode("ou-1234", "Engineering", NodeType.OU, [account1, account2])
            root = OrgNode("r-1234", "Root", NodeType.ROOT, [ou])

            mock_build.return_value = [root]

            # Mock describe_account calls
            mock_organizations_client.describe_account.side_effect = [
                {"Id": "111111111111", "Name": "dev-account"},
                {"Id": "222222222222", "Name": "prod-account"},
            ]

            # Get all accounts
            accounts = _get_all_accounts_in_organization(mock_organizations_client)

            # Should return both accounts
            assert len(accounts) == 2
            assert accounts[0]["Id"] == "111111111111"
            assert accounts[1]["Id"] == "222222222222"

    @patch("src.awsideman.aws_clients.manager.console")
    def test_get_all_accounts_describe_failure(self, mock_console, mock_organizations_client):
        """Test retrieval with describe_account failure."""
        with patch("src.awsideman.aws_clients.manager.build_organization_hierarchy") as mock_build:
            account1 = OrgNode("111111111111", "dev-account", NodeType.ACCOUNT, [])
            account2 = OrgNode("222222222222", "prod-account", NodeType.ACCOUNT, [])
            root = OrgNode("r-1234", "Root", NodeType.ROOT, [account1, account2])

            mock_build.return_value = [root]

            # Mock describe_account - first fails, second succeeds
            def mock_describe_side_effect(account_id):
                if account_id == "111111111111":
                    raise Exception("Describe error")
                return {"Id": "222222222222", "Name": "prod-account"}

            mock_organizations_client.describe_account.side_effect = mock_describe_side_effect

            # Get all accounts
            accounts = _get_all_accounts_in_organization(mock_organizations_client)

            # Should return only the successful account
            assert len(accounts) == 1
            assert accounts[0]["Id"] == "222222222222"

            # Should have printed warning
            mock_console.print.assert_called()


class TestEdgeCasesAndMalformedData:
    """Test edge cases and malformed data handling."""

    def test_empty_organization_structure(self, mock_organizations_client):
        """Test handling of empty organization structure."""
        mock_organizations_client.list_roots.return_value = []

        with pytest.raises(ValueError, match="No organization roots found"):
            build_organization_hierarchy(mock_organizations_client)

    def test_malformed_root_data(self, mock_organizations_client):
        """Test handling of malformed root data."""
        # Root with missing ID
        malformed_data = {"Name": "Root"}

        with pytest.raises(ValueError, match="Missing required 'Id' field"):
            _create_org_node_from_data(malformed_data, NodeType.ROOT)

    def test_malformed_ou_data(self, mock_organizations_client):
        """Test handling of malformed OU data."""
        # OU with missing name
        malformed_data = {"Id": "ou-1234567890-abcdefgh"}

        with pytest.raises(ValueError, match="Missing required 'Name' field in OU data"):
            _create_org_node_from_data(malformed_data, NodeType.OU)

    def test_malformed_account_data_fallbacks(self, mock_organizations_client):
        """Test handling of malformed account data with fallbacks."""
        # Account with only ID
        minimal_data = {"Id": "111111111111"}
        node = _create_org_node_from_data(minimal_data, NodeType.ACCOUNT)
        assert node.name == "Account-111111111111"

        # Account with ID and email but no name
        email_data = {"Id": "111111111111", "Email": "test@example.com"}
        node = _create_org_node_from_data(email_data, NodeType.ACCOUNT)
        assert node.name == "test@example.com"

    def test_circular_reference_protection(self, mock_organizations_client):
        """Test protection against circular references in hierarchy."""
        # This is more of a conceptual test since AWS Organizations
        # shouldn't have circular references, but we test the robustness

        # Mock a scenario where we hit an error during traversal
        # (simulating what would happen with circular references)
        call_count = 0

        def mock_list_parents(child_id):
            nonlocal call_count
            call_count += 1
            if call_count > 10:  # Prevent infinite loop in test
                raise Exception("Too many calls - simulating circular reference detection")
            return [{"Id": "ou-1234", "Type": "ORGANIZATIONAL_UNIT"}]

        mock_organizations_client.list_parents.side_effect = mock_list_parents

        # The function should handle this gracefully
        with patch("src.awsideman.aws_clients.manager.console"):
            path = _calculate_ou_path(mock_organizations_client, "111111111111")
            # Should return empty path when error occurs
            assert path == []

    def test_unicode_and_special_characters(self, mock_organizations_client):
        """Test handling of unicode and special characters in names."""
        # Test with unicode characters
        unicode_data = {"Id": "ou-1234567890-abcdefgh", "Name": "Engineering-部门-🚀"}

        node = _create_org_node_from_data(unicode_data, NodeType.OU)
        assert node.name == "Engineering-部门-🚀"
        assert node.id == "ou-1234567890-abcdefgh"

    def test_very_long_names(self, mock_organizations_client):
        """Test handling of very long names."""
        long_name = "A" * 1000  # Very long name
        data = {"Id": "ou-1234567890-abcdefgh", "Name": long_name}

        node = _create_org_node_from_data(data, NodeType.OU)
        assert node.name == long_name
        assert len(node.name) == 1000

    def test_empty_string_values(self, mock_organizations_client):
        """Test handling of empty string values."""
        # Empty name should be handled appropriately
        data = {"Id": "ou-1234567890-abcdefgh", "Name": ""}

        # For OU, empty name should raise error
        with pytest.raises(ValueError, match="Missing required 'Name' field in OU data"):
            _create_org_node_from_data(data, NodeType.OU)

        # For account, empty name should use fallback
        account_data = {"Id": "111111111111", "Name": "", "Email": "test@example.com"}

        node = _create_org_node_from_data(account_data, NodeType.ACCOUNT)
        assert node.name == "test@example.com"  # Should use email as fallback
