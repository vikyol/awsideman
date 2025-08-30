"""AWS client utilities for awsideman."""

import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

import boto3
from botocore.exceptions import ClientError
from rich.console import Console

from ..utils.models import (
    AccountDetails,
    HierarchyPath,
    NodeType,
    OrganizationTree,
    OrgNode,
    PolicyInfo,
    PolicyList,
    PolicyType,
)

logger = logging.getLogger(__name__)


# Simple error handling functions for backward compatibility
def handle_aws_error(error: ClientError, operation: str) -> None:
    """Simple AWS error handler for backward compatibility."""
    console.print(f"[red]AWS Error in {operation}: {error}[/red]")
    raise error


F = TypeVar("F", bound=Callable[..., Any])


def with_retry(max_retries: int = 3) -> Callable[[F], F]:
    """Simple retry decorator for backward compatibility."""

    def decorator(func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ClientError:
                    if attempt == max_retries - 1:
                        raise
                    console.print(
                        f"[yellow]Retry {attempt + 1}/{max_retries} for {func.__name__}[/yellow]"
                    )
            # This should never be reached, but mypy needs it
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


console = Console()


class AWSClientManager:
    """Manages AWS client connections for Identity Center operations."""

    def __init__(
        self,
        profile: Optional[str] = None,
        region: Optional[str] = None,
        enable_caching: bool = True,
        cache_manager: Optional[Any] = None,
        cache_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the AWS client manager.

        Args:
            profile: AWS profile name to use
            region: AWS region to use
            enable_caching: Whether to enable caching for read operations (default: True)
            cache_manager: Optional CacheManager instance for caching operations
            cache_config: Optional cache configuration dictionary
        """
        self.profile = profile
        self.region = region
        self.enable_caching = enable_caching
        self.cache_manager = cache_manager
        self.cache_config = cache_config or {}
        self.session = None
        self._cached_client: Optional[Any] = None
        self._init_session()

    def _init_session(self) -> None:
        """Initialize the AWS session."""
        session_kwargs = {}
        if self.profile:
            session_kwargs["profile_name"] = self.profile

        # Always explicitly set region_name to override AWS_DEFAULT_REGION
        # This ensures we use the region from the profile or the one provided
        if self.region:
            session_kwargs["region_name"] = self.region
        elif self.profile:
            # If no region is provided but a profile is, try to get the region from the profile
            try:
                # Create a temporary session to get the region from the profile
                temp_session = boto3.Session(profile_name=self.profile)
                profile_region = temp_session.region_name
                if profile_region:
                    session_kwargs["region_name"] = profile_region
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get region from profile: {str(e)}[/yellow]"
                )

        self.session = boto3.Session(**session_kwargs)

    def validate_session(self) -> bool:
        """
        Validate that the AWS session is active and credentials are valid.

        This method performs a simple test call to verify that the session
        can successfully make AWS API calls.

        Returns:
            True if the session is valid, False otherwise

        Raises:
            RuntimeError: If session is not initialized
            Exception: If session validation fails
        """
        if self.session is None:
            raise RuntimeError("Session not initialized")

        try:
            # Try to get caller identity using STS - this is a lightweight operation
            # that will fail if credentials are invalid or expired
            sts_client = self.session.client("sts")
            sts_client.get_caller_identity()
            return True
        except Exception as e:
            logger.debug(f"Session validation failed: {e}")
            return False

    @classmethod
    def with_cache_integration(
        cls,
        profile: Optional[str] = None,
        region: Optional[str] = None,
        enable_caching: bool = True,
        cache_config: Optional[Dict[str, Any]] = None,
    ) -> "AWSClientManager":
        """
        Create an AWS client manager with automatic cache integration.

        This factory method automatically configures the cache manager
        and provides a seamless integration experience.

        Args:
            profile: AWS profile name to use
            region: AWS region to use
            enable_caching: Whether to enable caching
            cache_config: Optional cache configuration dictionary

        Returns:
            Configured AWSClientManager instance with cache integration
        """
        cache_manager = None
        if enable_caching:
            try:
                from ..cache.utilities import create_cache_manager

                cache_manager = create_cache_manager()
                logger.debug("Auto-configured cache manager for AWS client manager")
            except Exception as e:
                logger.warning(f"Could not auto-configure cache manager: {e}")
        return cls(
            profile=profile,
            region=region,
            enable_caching=enable_caching,
            cache_manager=cache_manager,
            cache_config=cache_config,
        )

    def get_client(self, service_name: str) -> Any:
        """
        Get an AWS service client.

        Args:
            service_name: Name of the AWS service

        Returns:
            AWS service client
        """
        if self.session is None:
            raise RuntimeError("Session not initialized")
        return self.session.client(service_name)  # type: ignore[unreachable]

    def get_raw_identity_center_client(self) -> Any:
        """
        Get the raw AWS Identity Center client.

        Returns:
            AWS Identity Center client
        """
        return self.get_client("sso-admin")

    def get_raw_identity_store_client(self) -> Any:
        """
        Get the raw AWS Identity Store client.

        Returns:
            AWS Identity Store client
        """
        return self.get_client("identitystore")

    def get_raw_organizations_client(self) -> Any:
        """
        Get the raw AWS Organizations client.

        Returns:
            AWS Organizations client
        """
        return self.get_client("organizations")

    def get_cached_client(self) -> Any:
        """Get a cached AWS client wrapper."""
        if self._cached_client is None:
            from .cached_client import CachedAwsClient

            if self.cache_manager is None:
                try:
                    from ..cache.utilities import create_cache_manager

                    self.cache_manager = create_cache_manager()
                    logger.debug("Auto-configured cache manager for AWS client")
                except Exception as e:
                    logger.warning(f"Could not auto-configure cache manager: {e}")
                    from ..cache.manager import CacheManager

                    self.cache_manager = CacheManager()
            self._cached_client = CachedAwsClient(self, self.cache_manager)
        return self._cached_client

    def get_organizations_client(self) -> Any:
        """
        Get an Organizations client with optional caching support.

        Returns:
            OrganizationsClient or CachedOrganizationsClient based on enable_caching setting
        """
        if self.enable_caching:
            return self.get_cached_client().get_organizations_client()
        else:
            return OrganizationsClientWrapper(self)

    def get_identity_center_client(self) -> Any:
        """
        Get an Identity Center client with optional caching support.

        Returns:
            Identity Center client with or without caching based on enable_caching setting
        """
        if self.enable_caching:
            # Use the new unified cache system
            from ..cache.aws_client import CachedIdentityCenterClient
            from ..cache.manager import CacheManager

            cache_manager = self.cache_manager or CacheManager()
            raw_client = self.get_raw_identity_center_client()
            return CachedIdentityCenterClient(raw_client, cache_manager)
        else:
            return IdentityCenterClientWrapper(self)

    def get_identity_store_client(self) -> Any:
        """
        Get an Identity Store client with optional caching support.

        Returns:
            Identity Store client with or without caching based on enable_caching setting
        """
        if self.enable_caching:
            # Use the new unified cache system
            from ..cache.aws_client import CachedIdentityStoreClient
            from ..cache.manager import CacheManager

            cache_manager = self.cache_manager or CacheManager()
            raw_client = self.get_raw_identity_store_client()
            return CachedIdentityStoreClient(raw_client, cache_manager)
        else:
            return IdentityStoreClientWrapper(self)

    def get_sso_admin_client(self) -> Any:
        """
        Get an SSO Admin client with optional caching support.
        This is an alias for get_identity_center_client() for backward compatibility.

        Returns:
            SSO Admin client with or without caching based on enable_caching setting
        """
        return self.get_identity_center_client()

    def get_cache_manager(self) -> Optional[Any]:
        """
        Get the cache manager instance used by this client manager.

        Returns:
            CacheManager instance if available, None otherwise
        """
        return self.cache_manager

    def is_caching_enabled(self) -> bool:
        """
        Check if caching is enabled for this client manager.

        Returns:
            True if caching is enabled, False otherwise
        """
        return self.enable_caching and self.cache_manager is not None

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics if caching is enabled.

        Returns:
            Dictionary containing cache statistics or empty dict if caching disabled
        """
        if not self.is_caching_enabled():
            return {"caching_enabled": False}

        try:
            return self.cache_manager.get_cache_stats()
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"caching_enabled": True, "error": str(e)}

    def clear_cache(self) -> bool:
        """
        Clear the cache if caching is enabled.

        Returns:
            True if cache was cleared, False if caching is disabled or operation failed
        """
        if not self.is_caching_enabled():
            return False

        try:
            self.cache_manager.clear()
            return True
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")
            return False


class OrganizationsClientWrapper:
    """Wrapper for AWS Organizations client with error handling and retry logic."""

    def __init__(self, client_manager: AWSClientManager):
        """
        Initialize the Organizations client wrapper.

        Args:
            client_manager: AWSClientManager instance for session management
        """
        self.client_manager = client_manager
        self._client = None

    @property
    def client(self) -> Any:
        """Get the Organizations client, creating it if needed."""
        if self._client is None:
            self._client = self.client_manager.get_raw_organizations_client()
        return self._client

    @with_retry(max_retries=3)
    def list_roots(self) -> List[Dict[str, Any]]:
        """
        List all roots in the organization.

        Returns:
            List of root dictionaries containing Id, Name, Arn, and PolicyTypes

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_roots()
            result = response.get("Roots", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListRoots")
            # This should never be reached, but mypy needs it
            return []

    @with_retry(max_retries=3)
    def list_organizational_units_for_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List organizational units for a given parent (root or OU).

        Args:
            parent_id: The unique identifier of the parent root or OU

        Returns:
            List of OU dictionaries containing Id, Name, and Arn

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_organizational_units_for_parent(ParentId=parent_id)
            result = response.get("OrganizationalUnits", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListOrganizationalUnitsForParent")
            # This should never be reached, but mypy needs it
            return []

    @with_retry(max_retries=3)
    def list_accounts_for_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        List accounts for a given parent (root or OU).

        Args:
            parent_id: The unique identifier of the parent root or OU

        Returns:
            List of account dictionaries containing Id, Name, Email, Arn, Status, and JoinedTimestamp

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_accounts_for_parent(ParentId=parent_id)
            result = response.get("Accounts", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListAccountsForParent")
            # This should never be reached, but mypy needs it
            return []

    @with_retry(max_retries=3)
    def list_accounts(self) -> Dict[str, Any]:
        """
        List all accounts in the organization.

        Returns:
            Dictionary with 'Accounts' key containing list of account dictionaries

        Raises:
            ClientError: If the API call fails
        """
        try:
            # Use the basic AWS Organizations API to list all accounts
            response = self.client.list_accounts()
            return response
        except ClientError as e:
            handle_aws_error(e, "ListAccounts")
            # This should never be reached, but mypy needs it
            return {"Accounts": []}

    @with_retry(max_retries=3)
    def describe_account(self, account_id: str, **kwargs) -> Dict[str, Any]:
        """
        Get detailed information about an account.

        Args:
            account_id: The unique identifier of the account
            **kwargs: Additional keyword arguments (for compatibility)

        Returns:
            Account dictionary containing Id, Name, Email, Arn, Status, and JoinedTimestamp

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.describe_account(AccountId=account_id)
            result = response.get("Account", {})
            return result if isinstance(result, dict) else {}
        except ClientError as e:
            handle_aws_error(e, "DescribeAccount")
            # This should never be reached, but mypy needs it
            return {}

    @with_retry(max_retries=3)
    def list_tags_for_resource(self, resource_id: str) -> List[Dict[str, str]]:
        """
        List tags for a resource (account, OU, or root).

        Args:
            resource_id: The unique identifier of the resource

        Returns:
            List of tag dictionaries containing Key and Value

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_tags_for_resource(ResourceId=resource_id)
            result = response.get("Tags", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListTagsForResource")
            # This should never be reached, but mypy needs it
            return []

    @with_retry(max_retries=3)
    def list_policies_for_target(self, target_id: str, filter_type: str) -> List[Dict[str, Any]]:
        """
        List policies attached to a target (account, OU, or root).

        Args:
            target_id: The unique identifier of the target
            filter_type: The type of policy to filter by (SERVICE_CONTROL_POLICY or RESOURCE_CONTROL_POLICY)

        Returns:
            List of policy dictionaries containing Id, Name, Description, Type, and AwsManaged

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_policies_for_target(TargetId=target_id, Filter=filter_type)
            result = response.get("Policies", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListPoliciesForTarget")
            # This should never be reached, but mypy needs it
            return []

    @with_retry(max_retries=3)
    def list_parents(self, child_id: str) -> List[Dict[str, Any]]:
        """
        List the parents of a child (account or OU).

        Args:
            child_id: The unique identifier of the child

        Returns:
            List of parent dictionaries containing Id and Type

        Raises:
            ClientError: If the API call fails
        """
        try:
            response = self.client.list_parents(ChildId=child_id)
            result = response.get("Parents", [])
            return result if isinstance(result, list) else []
        except ClientError as e:
            handle_aws_error(e, "ListParents")
            # This should never be reached, but mypy needs it
            return []


class IdentityCenterClientWrapper:
    """Wrapper for AWS Identity Center (SSO Admin) client with error handling and retry logic."""

    def __init__(self, client_manager: AWSClientManager):
        """
        Initialize the Identity Center client wrapper.

        Args:
            client_manager: AWSClientManager instance for session management
        """
        self.client_manager = client_manager
        self._client = None

    @property
    def client(self) -> Any:
        """Get the Identity Center client, creating it if needed."""
        if self._client is None:
            self._client = self.client_manager.get_raw_identity_center_client()
        return self._client

    def __getattr__(self, name: str) -> Any:
        """Delegate all other method calls to the underlying client."""
        return getattr(self.client, name)


class IdentityStoreClientWrapper:
    """Wrapper for AWS Identity Store client with error handling and retry logic."""

    def __init__(self, client_manager: AWSClientManager):
        """
        Initialize the Identity Store client wrapper.

        Args:
            client_manager: AWSClientManager instance for session management
        """
        self.client_manager = client_manager
        self._client = None

    @property
    def client(self) -> Any:
        """Get the Identity Store client, creating it if needed."""
        if self._client is None:
            self._client = self.client_manager.get_raw_identity_store_client()
        return self._client

    def __getattr__(self, name: str) -> Any:
        """Delegate all other method calls to the underlying client."""
        return getattr(self.client, name)


def build_organization_hierarchy(
    organizations_client: OrganizationsClientWrapper,
) -> OrganizationTree:
    """
    Build the complete organization hierarchy tree structure.

    This function recursively constructs the organization tree starting from roots,
    then building OUs and accounts under each parent. It handles error cases
    gracefully and provides comprehensive error handling for incomplete or
    malformed organization data.

    Args:
        organizations_client: OrganizationsClient instance for API calls

    Returns:
        OrganizationTree: List of root OrgNode objects representing the complete hierarchy

    Raises:
        ClientError: If critical AWS API calls fail
        ValueError: If organization structure is malformed or incomplete
    """
    try:
        # Start by getting all roots
        roots_data = organizations_client.list_roots()
        if not roots_data:
            raise ValueError(
                "No organization roots found. This may indicate the account is not part of an organization."
            )

        organization_tree = []

        for root_data in roots_data:
            try:
                # Create root node
                root_node = _create_org_node_from_data(root_data, NodeType.ROOT)

                # Recursively build children for this root
                _build_children_recursive(organizations_client, root_node)

                organization_tree.append(root_node)

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to build hierarchy for root {root_data.get('Id', 'unknown')}: {str(e)}[/yellow]"
                )
                # Continue with other roots if one fails
                continue

        if not organization_tree:
            raise ValueError(
                "Failed to build organization hierarchy. No valid roots could be processed."
            )

        return organization_tree

    except ClientError as e:
        console.print(f"[red]Error: Failed to retrieve organization roots: {str(e)}[/red]")
        raise
    except Exception as e:
        console.print(
            f"[red]Error: Unexpected error building organization hierarchy: {str(e)}[/red]"
        )
        raise


def _build_children_recursive(
    organizations_client: OrganizationsClientWrapper, parent_node: OrgNode
) -> None:
    """
    Recursively build children (OUs and accounts) for a given parent node.

    Args:
        organizations_client: OrganizationsClient instance for API calls
        parent_node: The parent OrgNode to build children for

    Raises:
        ClientError: If AWS API calls fail
    """
    try:
        # Get organizational units under this parent
        ous_data = organizations_client.list_organizational_units_for_parent(parent_node.id)

        for ou_data in ous_data:
            try:
                # Create OU node
                ou_node = _create_org_node_from_data(ou_data, NodeType.OU)

                # Recursively build children for this OU BEFORE adding to parent
                _build_children_recursive(organizations_client, ou_node)

                parent_node.add_child(ou_node)

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to process OU {ou_data.get('Id', 'unknown')}: {str(e)}[/yellow]"
                )
                # Continue with other OUs if one fails
                continue

        # Get accounts under this parent
        accounts_data = organizations_client.list_accounts_for_parent(parent_node.id)

        for account_data in accounts_data:
            try:
                # Create account node
                account_node = _create_org_node_from_data(account_data, NodeType.ACCOUNT)

                parent_node.add_child(account_node)

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to process account {account_data.get('Id', 'unknown')}: {str(e)}[/yellow]"
                )
                # Continue with other accounts if one fails
                continue

    except ClientError as e:
        console.print(
            f"[yellow]Warning: Failed to retrieve children for {parent_node.id}: {str(e)}[/yellow]"
        )
        # Don't re-raise here as we want to continue building the rest of the tree
    except Exception as e:
        console.print(
            f"[yellow]Warning: Unexpected error building children for {parent_node.id}: {str(e)}[/yellow]"
        )


def _create_org_node_from_data(data: Dict[str, Any], node_type: NodeType) -> OrgNode:
    """
    Create an OrgNode from AWS API response data.

    Args:
        data: Dictionary containing node data from AWS API
        node_type: The type of node to create

    Returns:
        OrgNode: Created organization node

    Raises:
        ValueError: If required data is missing or malformed
    """
    # Validate required fields
    node_id = data.get("Id")
    if not node_id:
        raise ValueError(f"Missing required 'Id' field in {node_type.value} data")

    # Handle different name fields based on node type
    if node_type == NodeType.ROOT:
        node_name = data.get("Name", f"Root-{node_id}")
    elif node_type == NodeType.OU:
        node_name = data.get("Name")
        if not node_name:
            raise ValueError(f"Missing required 'Name' field in OU data for {node_id}")
    elif node_type == NodeType.ACCOUNT:
        node_name = data.get("Name")
        if not node_name:
            # For accounts, try to use email as fallback name
            node_name = data.get("Email", f"Account-{node_id}")
    else:
        raise ValueError(f"Unknown node type: {node_type}")

    return OrgNode(id=node_id, name=node_name, type=node_type, children=[])


def get_account_details(
    organizations_client: OrganizationsClientWrapper, account_id: str
) -> AccountDetails:
    """
    Get comprehensive account details including metadata and organizational context.

    This function retrieves detailed information about an AWS account including
    its basic metadata (name, email, status, etc.), tags, and calculates the
    full organizational unit path from root to the account.

    Args:
        organizations_client: OrganizationsClient instance for API calls
        account_id: The unique identifier of the account to retrieve details for

    Returns:
        AccountDetails: Comprehensive account information including OU path

    Raises:
        ClientError: If AWS API calls fail
        ValueError: If account is not found or data is malformed
    """
    try:
        # Get basic account information
        account_data = organizations_client.describe_account(account_id)
        if not account_data:
            raise ValueError(f"Account {account_id} not found")

        # Extract basic account information
        account_name = account_data.get("Name", "")
        account_email = account_data.get("Email", "")
        account_status = account_data.get("Status", "UNKNOWN")
        joined_timestamp = account_data.get("JoinedTimestamp")

        # Convert joined timestamp to datetime if present
        if joined_timestamp:
            # AWS returns datetime objects, but ensure we handle string format too
            if isinstance(joined_timestamp, str):
                from datetime import datetime

                joined_timestamp = datetime.fromisoformat(joined_timestamp.replace("Z", "+00:00"))
        else:
            from datetime import datetime

            joined_timestamp = datetime.min

        # Get account tags
        try:
            tags_data = organizations_client.list_tags_for_resource(account_id)

            # Handle different return types from cached vs non-cached clients
            if isinstance(tags_data, dict) and "Tags" in tags_data:
                # Cached client returns {"Tags": [...]}
                tags_list = tags_data["Tags"]
            elif isinstance(tags_data, list):
                # Non-cached client returns [...] directly
                tags_list = tags_data
            else:
                # Fallback for unexpected types
                console.print(
                    f"[yellow]Warning: Unexpected tags data format for account {account_id}: {type(tags_data)}[/yellow]"
                )
                tags_list = []

            tags = {tag["Key"]: tag["Value"] for tag in tags_list}
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not retrieve tags for account {account_id}: {str(e)}[/yellow]"
            )
            tags = {}

        # Calculate full OU path from root to account
        ou_path = _calculate_ou_path(organizations_client, account_id)

        return AccountDetails(
            id=account_id,
            name=account_name,
            email=account_email,
            status=account_status,
            joined_timestamp=joined_timestamp,
            tags=tags,
            ou_path=ou_path,
        )

    except ClientError as e:
        console.print(
            f"[red]Error: Failed to retrieve account details for {account_id}: {str(e)}[/red]"
        )
        raise
    except Exception as e:
        console.print(
            f"[red]Error: Unexpected error retrieving account details for {account_id}: {str(e)}[/red]"
        )
        raise


def search_accounts(
    organizations_client: OrganizationsClientWrapper,
    query: str,
    ou_filter: Optional[str] = None,
    tag_filter: Optional[Dict[str, str]] = None,
) -> List[AccountDetails]:
    """
    Search for accounts by name with optional filtering by OU and tags.

    This function performs case-insensitive partial string matching on account names
    and returns matching accounts with comprehensive details including OU path.
    Supports optional filtering by organizational unit and tags.

    Args:
        organizations_client: OrganizationsClient instance for API calls
        query: Account name or substring to search for (case-insensitive)
        ou_filter: Optional OU ID to filter accounts by organizational unit
        tag_filter: Optional dictionary of tag key-value pairs to filter by

    Returns:
        List[AccountDetails]: List of matching accounts with full metadata

    Raises:
        ClientError: If AWS API calls fail
        ValueError: If search parameters are invalid
    """
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")

    # Normalize query for case-insensitive matching
    query_lower = query.strip().lower()

    try:
        # Get all accounts in the organization by traversing the hierarchy
        all_accounts = _get_all_accounts_in_organization(organizations_client)

        matching_accounts = []

        for account_data in all_accounts:
            account_id = account_data["Id"]
            account_name = account_data.get("Name", "")

            # Perform case-insensitive partial string matching on account name
            if query_lower not in account_name.lower():
                continue

            try:
                # Get comprehensive account details
                account_details = get_account_details(organizations_client, account_id)

                # Apply OU filter if specified
                if ou_filter and not _account_matches_ou_filter(account_details, ou_filter):
                    continue

                # Apply tag filter if specified
                if tag_filter and not _account_matches_tag_filter(account_details, tag_filter):
                    continue

                matching_accounts.append(account_details)

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get details for account {account_id}: {str(e)}[/yellow]"
                )
                continue

        return matching_accounts

    except ClientError as e:
        console.print(f"[red]Error: Failed to search accounts: {str(e)}[/red]")
        raise
    except Exception as e:
        console.print(f"[red]Error: Unexpected error during account search: {str(e)}[/red]")
        raise


def _get_all_accounts_in_organization(
    organizations_client: OrganizationsClientWrapper,
) -> List[Dict[str, Any]]:
    """
    Get all accounts in the organization by traversing the complete hierarchy.

    Args:
        organizations_client: OrganizationsClient instance for API calls

    Returns:
        List[Dict[str, Any]]: List of all account data dictionaries in the organization

    Raises:
        ClientError: If AWS API calls fail
    """
    all_accounts = []

    # Build the organization hierarchy to get all accounts
    organization_tree = build_organization_hierarchy(organizations_client)

    # Recursively collect all accounts from the tree
    def collect_accounts_from_node(node: OrgNode) -> None:
        """Recursively collect account data from organization tree."""
        if node.is_account():
            # For account nodes, we need to get the full account data
            try:
                account_data = organizations_client.describe_account(node.id)
                all_accounts.append(account_data)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get account data for {node.id}: {str(e)}[/yellow]"
                )

        # Recursively process children
        for child in node.children:
            collect_accounts_from_node(child)

    # Collect accounts from all root nodes
    for root in organization_tree:
        collect_accounts_from_node(root)

    return all_accounts


def _account_matches_ou_filter(account_details: AccountDetails, ou_filter: str) -> bool:
    """
    Check if an account matches the OU filter.

    Args:
        account_details: AccountDetails object to check
        ou_filter: OU ID to filter by

    Returns:
        bool: True if account is in the specified OU or its children, False otherwise
    """
    # Check if the account's OU path contains the specified OU
    # This includes both direct membership and membership in child OUs
    return ou_filter in account_details.ou_path


def _account_matches_tag_filter(
    account_details: AccountDetails, tag_filter: Dict[str, str]
) -> bool:
    """
    Check if an account matches the tag filter.

    Args:
        account_details: AccountDetails object to check
        tag_filter: Dictionary of tag key-value pairs to match

    Returns:
        bool: True if account has all specified tags with matching values, False otherwise
    """
    for tag_key, tag_value in tag_filter.items():
        if not account_details.has_tag(tag_key, tag_value):
            return False
    return True


def _calculate_ou_path(
    organizations_client: OrganizationsClientWrapper, account_id: str
) -> List[str]:
    """
    Calculate the full organizational unit path from root to account.

    This function traverses up the organization hierarchy from the account
    to the root, collecting all parent OU IDs and names along the way.

    Args:
        organizations_client: OrganizationsClient instance for API calls
        account_id: The unique identifier of the account

    Returns:
        List[str]: List of OU names from root to account (excluding the account itself)

    Raises:
        ClientError: If AWS API calls fail
    """
    path = []
    current_id = account_id

    try:
        # Traverse up the hierarchy until we reach the root
        while True:
            # Get parents of current node
            parents = organizations_client.list_parents(current_id)

            if not parents:
                # No more parents, we've reached the top
                break

            # AWS Organizations guarantees each child has exactly one parent
            parent = parents[0]
            parent_id = parent["Id"]
            parent_type = parent["Type"]

            # If parent is a root, we're done
            if parent_type == "ROOT":
                # Get root name and add to path
                try:
                    roots = organizations_client.list_roots()
                    root_name = next(
                        (root["Name"] for root in roots if root["Id"] == parent_id), parent_id
                    )
                    path.append(root_name)
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not get root name for {parent_id}: {str(e)}[/yellow]"
                    )
                    path.append(parent_id)
                break

            # If parent is an OU, get its name and continue up the hierarchy
            elif parent_type == "ORGANIZATIONAL_UNIT":
                try:
                    # We need to find the OU name by looking at the parent's parent
                    # and listing OUs under it to find the one with matching ID
                    grandparents = organizations_client.list_parents(parent_id)
                    if grandparents:
                        grandparent_id = grandparents[0]["Id"]
                        ous = organizations_client.list_organizational_units_for_parent(
                            grandparent_id
                        )
                        ou_name = next(
                            (ou["Name"] for ou in ous if ou["Id"] == parent_id), parent_id
                        )
                        path.append(ou_name)
                    else:
                        path.append(parent_id)
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not get OU name for {parent_id}: {str(e)}[/yellow]"
                    )
                    path.append(parent_id)

                # Move up to the parent for next iteration
                current_id = parent_id
            else:
                # Unknown parent type, add ID and break
                path.append(parent_id)
                break

        # Reverse the path so it goes from root to account
        path.reverse()
        return path

    except ClientError as e:
        console.print(
            f"[yellow]Warning: Failed to calculate OU path for {account_id}: {str(e)}[/yellow]"
        )
        logger.warning(f"ClientError calculating OU path for {account_id}: {str(e)}")
        return []
    except Exception as e:
        console.print(
            f"[yellow]Warning: Unexpected error calculating OU path for {account_id}: {str(e)}[/yellow]"
        )
        logger.error(f"Unexpected error calculating OU path for {account_id}: {str(e)}")
        return []


# Backward compatibility alias
OrganizationsClient = OrganizationsClientWrapper


class PolicyResolver:
    """
    Resolves and aggregates Service Control Policies (SCPs) and Resource Control Policies (RCPs)
    affecting a specific AWS account by traversing the organization hierarchy.

    This class handles the complex logic of tracing policies from an account up through
    its organizational unit hierarchy to the root, collecting all attached policies
    at each level and determining their effective status.
    """

    def __init__(self, organizations_client: OrganizationsClientWrapper):
        """
        Initialize the PolicyResolver.

        Args:
            organizations_client: OrganizationsClient instance for API calls
        """
        self.organizations_client = organizations_client

    def resolve_policies_for_account(self, account_id: str) -> PolicyList:
        """
        Resolve all SCPs and RCPs affecting a specific account.

        This method traverses the OU hierarchy from the account to the root,
        collecting all attached policies at each level. It handles both
        Service Control Policies and Resource Control Policies, determining
        their effective status and attachment points.

        Args:
            account_id: The unique identifier of the account to resolve policies for

        Returns:
            PolicyList: List of PolicyInfo objects representing all policies affecting the account

        Raises:
            ClientError: If AWS API calls fail
            ValueError: If account is not found or hierarchy is malformed
        """
        try:
            # Get the hierarchy path from account to root
            hierarchy_path = self._get_hierarchy_path(account_id)

            if not hierarchy_path.ids:
                raise ValueError(f"Could not determine hierarchy path for account {account_id}")

            all_policies = []

            # Traverse the hierarchy from account to root, collecting policies at each level
            for i, target_id in enumerate(hierarchy_path.ids):
                target_name = (
                    hierarchy_path.names[i] if i < len(hierarchy_path.names) else target_id
                )
                target_type = (
                    hierarchy_path.types[i] if i < len(hierarchy_path.types) else NodeType.OU
                )

                try:
                    # Get SCPs attached to this target
                    scps = self._get_policies_for_target(
                        target_id, PolicyType.SERVICE_CONTROL_POLICY, target_name, target_type
                    )
                    all_policies.extend(scps)

                    # Get RCPs attached to this target
                    rcps = self._get_policies_for_target(
                        target_id, PolicyType.RESOURCE_CONTROL_POLICY, target_name, target_type
                    )
                    all_policies.extend(rcps)

                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not get policies for {target_id} ({target_name}): {str(e)}[/yellow]"
                    )
                    continue

            return all_policies

        except ClientError as e:
            console.print(
                f"[red]Error: Failed to resolve policies for account {account_id}: {str(e)}[/red]"
            )
            raise
        except Exception as e:
            console.print(
                f"[red]Error: Unexpected error resolving policies for account {account_id}: {str(e)}[/red]"
            )
            raise

    def _get_hierarchy_path(self, account_id: str) -> HierarchyPath:
        """
        Get the complete hierarchy path from account to root.

        Args:
            account_id: The unique identifier of the account

        Returns:
            HierarchyPath: Complete path from account to root with IDs, names, and types

        Raises:
            ClientError: If AWS API calls fail
        """
        path_ids = []
        path_names = []
        path_types = []

        current_id = account_id

        try:
            # Start with the account itself
            try:
                account_data = self.organizations_client.describe_account(account_id)
                path_ids.append(account_id)
                path_names.append(account_data.get("Name", account_id))
                path_types.append(NodeType.ACCOUNT)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get account details for {account_id}: {str(e)}[/yellow]"
                )
                path_ids.append(account_id)
                path_names.append(account_id)
                path_types.append(NodeType.ACCOUNT)

            # Traverse up the hierarchy
            while True:
                parents = self.organizations_client.list_parents(current_id)

                if not parents:
                    break

                parent = parents[0]  # AWS Organizations guarantees exactly one parent
                parent_id = parent["Id"]
                parent_type = parent["Type"]

                if parent_type == "ROOT":
                    # Add root to path and we're done
                    try:
                        roots = self.organizations_client.list_roots()
                        root_name = next(
                            (root["Name"] for root in roots if root["Id"] == parent_id), parent_id
                        )
                        path_ids.append(parent_id)
                        path_names.append(root_name)
                        path_types.append(NodeType.ROOT)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not get root name for {parent_id}: {str(e)}[/yellow]"
                        )
                        path_ids.append(parent_id)
                        path_names.append(parent_id)
                        path_types.append(NodeType.ROOT)
                    break

                elif parent_type == "ORGANIZATIONAL_UNIT":
                    # Add OU to path and continue up
                    try:
                        # Get OU name by finding it in its parent's children
                        grandparents = self.organizations_client.list_parents(parent_id)
                        if grandparents:
                            grandparent_id = grandparents[0]["Id"]
                            ous = self.organizations_client.list_organizational_units_for_parent(
                                grandparent_id
                            )
                            ou_name = next(
                                (ou["Name"] for ou in ous if ou["Id"] == parent_id), parent_id
                            )
                            path_ids.append(parent_id)
                            path_names.append(ou_name)
                            path_types.append(NodeType.OU)
                        else:
                            path_ids.append(parent_id)
                            path_names.append(parent_id)
                            path_types.append(NodeType.OU)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not get OU name for {parent_id}: {str(e)}[/yellow]"
                        )
                        path_ids.append(parent_id)
                        path_names.append(parent_id)
                        path_types.append(NodeType.OU)

                    current_id = parent_id
                else:
                    # Unknown parent type, add and break
                    path_ids.append(parent_id)
                    path_names.append(parent_id)
                    path_types.append(NodeType.OU)
                    break

            # Reverse the path so it goes from root to account
            path_ids.reverse()
            path_names.reverse()
            path_types.reverse()

            return HierarchyPath(ids=path_ids, names=path_names, types=path_types)

        except ClientError as e:
            console.print(
                f"[yellow]Warning: Failed to get hierarchy path for {account_id}: {str(e)}[/yellow]"
            )
            return HierarchyPath(ids=[], names=[], types=[])
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error getting hierarchy path for {account_id}: {str(e)}[/yellow]"
            )
            return HierarchyPath(ids=[], names=[], types=[])

    def _get_policies_for_target(
        self, target_id: str, policy_type: PolicyType, target_name: str, target_node_type: NodeType
    ) -> PolicyList:
        """
        Get all policies of a specific type attached to a target.

        Args:
            target_id: The unique identifier of the target (account, OU, or root)
            policy_type: The type of policy to retrieve (SCP or RCP)
            target_name: Human-readable name of the target
            target_node_type: The type of the target node

        Returns:
            PolicyList: List of PolicyInfo objects for policies attached to the target

        Raises:
            ClientError: If AWS API calls fail
        """
        policies = []

        try:
            # Get policies attached to this target
            policy_data_list = self.organizations_client.list_policies_for_target(
                target_id, policy_type.value
            )

            for policy_data in policy_data_list:
                try:
                    # Extract policy information
                    policy_id = policy_data.get("Id", "")
                    policy_name = policy_data.get("Name", policy_id)
                    policy_description = policy_data.get("Description", "")
                    aws_managed = policy_data.get("AwsManaged", False)

                    # Determine effective status
                    # For now, we assume all attached policies are enabled
                    # In the future, this could be enhanced to check for conditional policies
                    effective_status = self._determine_policy_status(policy_data, target_node_type)

                    policy_info = PolicyInfo(
                        id=policy_id,
                        name=policy_name,
                        type=policy_type,
                        description=policy_description,
                        aws_managed=aws_managed,
                        attachment_point=target_id,
                        attachment_point_name=target_name,
                        effective_status=effective_status,
                    )

                    policies.append(policy_info)

                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not process policy data for {target_id}: {str(e)}[/yellow]"
                    )
                    continue

        except ClientError as e:
            # If the target doesn't support the policy type, that's expected
            if "PolicyTypeNotEnabledException" in str(
                e
            ) or "PolicyTypeNotAvailableForOrganizationException" in str(e):
                console.print(
                    f"[dim]Policy type {policy_type.value} not enabled for target {target_id}[/dim]"
                )
            else:
                console.print(
                    f"[yellow]Warning: Could not get {policy_type.value} policies for {target_id}: {str(e)}[/yellow]"
                )
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error getting {policy_type.value} policies for {target_id}: {str(e)}[/yellow]"
            )

        return policies

    def _determine_policy_status(
        self, policy_data: Dict[str, Any], target_node_type: NodeType
    ) -> str:
        """
        Determine the effective status of a policy.

        This method analyzes policy data and target context to determine if a policy
        is effectively enabled, disabled, or conditionally applied. Currently implements
        basic logic but can be extended for more complex conditional policy scenarios.

        Args:
            policy_data: Dictionary containing policy information from AWS API
            target_node_type: The type of node the policy is attached to

        Returns:
            str: The effective status of the policy ("ENABLED", "DISABLED", "CONDITIONAL")
        """
        # Basic implementation - assume all attached policies are enabled
        # This can be enhanced in the future to handle:
        # - Conditional policies based on request context
        # - Policies that are attached but disabled
        # - Time-based or condition-based policy activation

        # Check if policy has any conditional elements
        # For now, we'll use a simple heuristic based on policy metadata
        if policy_data.get("Type") and "CONDITIONAL" in str(policy_data.get("Type", "")).upper():
            return "CONDITIONAL"

        # Check for any disabled indicators in the policy data
        # AWS doesn't typically return disabled policies in list_policies_for_target,
        # but we'll check just in case
        if policy_data.get("Status") == "DISABLED":
            return "DISABLED"

        # Default to enabled for all attached policies
        return "ENABLED"
