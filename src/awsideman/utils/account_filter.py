"""Account filtering infrastructure for multi-account operations."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Generator, List, Optional

from ..aws_clients.manager import OrganizationsClientWrapper
from .models import AccountDetails

logger = logging.getLogger(__name__)


class FilterType(str, Enum):
    """Enumeration for account filter types."""

    WILDCARD = "WILDCARD"
    TAG = "TAG"
    EXPLICIT = "EXPLICIT"
    OU = "OU"
    PATTERN = "PATTERN"


@dataclass
class ValidationError:
    """Represents a validation error with context."""

    message: str
    field: Optional[str] = None
    value: Optional[str] = None


@dataclass
class AccountInfo:
    """
    Account information for multi-account operations.

    Contains essential account metadata needed for filtering and operations.
    """

    account_id: str
    account_name: str
    email: str
    status: str
    tags: Dict[str, str]
    ou_path: List[str]

    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.tags is None:
            self.tags = {}
        if self.ou_path is None:
            self.ou_path = []

    def matches_tag_filter(self, tag_key: str, tag_value: str) -> bool:
        """
        Check if account matches a specific tag filter.

        Args:
            tag_key: Tag key to match
            tag_value: Tag value to match

        Returns:
            True if account has the tag with matching value, False otherwise
        """
        return self.tags.get(tag_key) == tag_value

    def get_display_name(self) -> str:
        """
        Get a human-readable display name for the account.

        Returns:
            Account name with ID in parentheses
        """
        return f"{self.account_name} ({self.account_id})"

    @classmethod
    def from_account_details(cls, account_details: AccountDetails) -> "AccountInfo":
        """
        Create AccountInfo from AccountDetails.

        Args:
            account_details: AccountDetails object to convert

        Returns:
            AccountInfo instance
        """
        return cls(
            account_id=account_details.id,
            account_name=account_details.name,
            email=account_details.email,
            status=account_details.status,
            tags=account_details.tags.copy(),
            ou_path=account_details.ou_path.copy(),
        )


class AccountFilter:
    """
    Account filter for multi-account operations.

    Supports wildcard, tag-based, explicit account list, OU-based, and regex pattern filtering of AWS accounts.
    """

    def __init__(
        self,
        filter_expression: Optional[str] = None,
        organizations_client: OrganizationsClientWrapper = None,
        explicit_accounts: Optional[List[str]] = None,
        ou_filter: Optional[str] = None,
        account_name_pattern: Optional[str] = None,
    ):
        """
        Initialize the account filter.

        Args:
            filter_expression: Filter expression (e.g., "*" or "tag:Environment=Production")
            organizations_client: Organizations client for account discovery
            explicit_accounts: List of explicit account IDs to target
            ou_filter: Organizational unit path filter (e.g., "Root/Production")
            account_name_pattern: Regex pattern for account name matching
        """
        self._original_filter_expression = filter_expression
        self.filter_expression = (
            filter_expression.strip() if filter_expression and filter_expression.strip() else None
        )
        self.organizations_client = organizations_client
        self.explicit_accounts = explicit_accounts
        self.ou_filter = ou_filter.strip() if ou_filter is not None and ou_filter.strip() else None
        self.account_name_pattern = (
            account_name_pattern.strip()
            if account_name_pattern is not None and account_name_pattern.strip()
            else None
        )
        self.filter_type = self._determine_filter_type()
        self.tag_filters = self._parse_tag_filters() if self.filter_type == FilterType.TAG else []

    def _determine_filter_type(self) -> FilterType:
        """
        Determine the type of filter based on the expression and explicit accounts.

        Returns:
            FilterType enum value
        """
        if self.explicit_accounts is not None:
            return FilterType.EXPLICIT
        elif self.ou_filter is not None:
            return FilterType.OU
        elif self.account_name_pattern is not None:
            return FilterType.PATTERN
        elif self.filter_expression == "*":
            return FilterType.WILDCARD
        elif self.filter_expression and self.filter_expression.startswith("tag:"):
            return FilterType.TAG
        else:
            # Default to wildcard for backward compatibility
            return FilterType.WILDCARD

    def _parse_tag_filters(self) -> List[Dict[str, str]]:
        """
        Parse tag filter expressions.

        Supports formats:
        - tag:Key=Value
        - tag:Key=Value,Key2=Value2

        Returns:
            List of tag filter dictionaries with 'key' and 'value' keys

        Raises:
            ValueError: If tag filter format is invalid
        """
        if not self.filter_expression.startswith("tag:"):
            return []

        # Remove "tag:" prefix
        tag_part = self.filter_expression[4:]

        if not tag_part:
            raise ValueError("Tag filter expression cannot be empty after 'tag:' prefix")

        tag_filters = []

        # Split by comma for multiple tag filters
        tag_expressions = [expr.strip() for expr in tag_part.split(",")]

        for expr in tag_expressions:
            if not expr:
                continue

            # Parse Key=Value format
            if "=" not in expr:
                raise ValueError(f"Invalid tag filter format: '{expr}'. Expected format: Key=Value")

            key, value = expr.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                raise ValueError(f"Tag key cannot be empty in filter: '{expr}'")

            if not value:
                raise ValueError(f"Tag value cannot be empty in filter: '{expr}'")

            tag_filters.append({"key": key, "value": value})

        if not tag_filters:
            raise ValueError("No valid tag filters found in expression")

        return tag_filters

    def validate_filter(self) -> List[ValidationError]:
        """
        Validate the filter expression and all filter options.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check for mutually exclusive filter options
        # Note: We need to check for non-None values, not just truthy values
        filter_options = [
            ("explicit_accounts", self.explicit_accounts is not None),
            ("filter_expression", self.filter_expression is not None),
            ("ou_filter", self.ou_filter is not None),
            ("account_name_pattern", self.account_name_pattern is not None),
        ]

        active_filters = [name for name, active in filter_options if active]

        if len(active_filters) > 1:
            errors.append(
                ValidationError(
                    message=f"Cannot specify multiple filter options simultaneously. Active filters: {', '.join(active_filters)}",
                    field="filter_options",
                    value=f"active_filters={active_filters}",
                )
            )
            return errors

        if len(active_filters) == 0:
            errors.append(
                ValidationError(
                    message="Must specify at least one filter option",
                    field="filter_options",
                    value="no_filters_specified",
                )
            )
            return errors

        # Validate specific filter types
        if self.filter_type == FilterType.EXPLICIT:
            errors.extend(self._validate_explicit_accounts())
        elif self.filter_type == FilterType.OU:
            errors.extend(self._validate_ou_filter())
        elif self.filter_type == FilterType.PATTERN:
            errors.extend(self._validate_pattern_filter())
        elif self.filter_type == FilterType.TAG:
            errors.extend(self._validate_tag_filter())
        elif self.filter_type == FilterType.WILDCARD:
            errors.extend(self._validate_wildcard_filter())

        return errors

    def _validate_explicit_accounts(self) -> List[ValidationError]:
        """Validate explicit accounts list."""
        errors = []

        if not self.explicit_accounts:
            errors.append(
                ValidationError(
                    message="Explicit accounts list cannot be empty",
                    field="explicit_accounts",
                    value=str(self.explicit_accounts),
                )
            )
            return errors

        # Validate account ID format
        for account_id in self.explicit_accounts:
            if not account_id.strip():
                errors.append(
                    ValidationError(
                        message="Account ID cannot be empty",
                        field="explicit_accounts",
                        value=account_id,
                    )
                )
            elif not account_id.isdigit() or len(account_id) != 12:
                errors.append(
                    ValidationError(
                        message=f"Invalid account ID format: '{account_id}'. Account ID must be a 12-digit number",
                        field="explicit_accounts",
                        value=account_id,
                    )
                )

        return errors

    def _validate_ou_filter(self) -> List[ValidationError]:
        """Validate organizational unit filter."""
        errors = []

        if not self.ou_filter:
            errors.append(
                ValidationError(
                    message="OU filter cannot be empty", field="ou_filter", value=self.ou_filter
                )
            )
            return errors

        # Basic validation - OU path should not contain invalid characters
        invalid_chars = ["<", ">", "|", "&", ";"]
        for char in invalid_chars:
            if char in self.ou_filter:
                errors.append(
                    ValidationError(
                        message=f"OU filter contains invalid character: '{char}'",
                        field="ou_filter",
                        value=self.ou_filter,
                    )
                )

        return errors

    def _validate_pattern_filter(self) -> List[ValidationError]:
        """Validate regex pattern filter."""
        errors = []

        if not self.account_name_pattern:
            errors.append(
                ValidationError(
                    message="Account name pattern cannot be empty",
                    field="account_name_pattern",
                    value=self.account_name_pattern,
                )
            )
            return errors

        # Validate regex pattern
        try:
            re.compile(self.account_name_pattern)
        except re.error as e:
            errors.append(
                ValidationError(
                    message=f"Invalid regex pattern: {str(e)}",
                    field="account_name_pattern",
                    value=self.account_name_pattern,
                )
            )

        return errors

    def _validate_tag_filter(self) -> List[ValidationError]:
        """Validate tag filter."""
        errors = []

        if not self.filter_expression:
            errors.append(
                ValidationError(
                    message="Filter expression cannot be empty",
                    field="filter_expression",
                    value=self._original_filter_expression,
                )
            )
            return errors

        try:
            self._parse_tag_filters()
        except ValueError as e:
            errors.append(
                ValidationError(
                    message=str(e), field="filter_expression", value=self.filter_expression
                )
            )

        return errors

    def _validate_wildcard_filter(self) -> List[ValidationError]:
        """Validate wildcard filter."""
        errors = []

        if not self.filter_expression:
            errors.append(
                ValidationError(
                    message="Filter expression cannot be empty",
                    field="filter_expression",
                    value=self._original_filter_expression,
                )
            )
            return errors

        if self.filter_expression != "*":
            errors.append(
                ValidationError(
                    message=f"Invalid wildcard filter: '{self.filter_expression}'. Only '*' is supported",
                    field="filter_expression",
                    value=self.filter_expression,
                )
            )

        return errors

    def get_filter_description(self) -> str:
        """
        Get a human-readable description of the filter.

        Returns:
            Description string
        """
        if self.filter_type == FilterType.WILDCARD:
            return "All accounts in the organization"
        elif self.filter_type == FilterType.TAG:
            tag_descriptions = []
            for tag_filter in self.tag_filters:
                tag_descriptions.append(f"{tag_filter['key']}={tag_filter['value']}")
            return f"Accounts with tags: {', '.join(tag_descriptions)}"
        elif self.filter_type == FilterType.EXPLICIT:
            if len(self.explicit_accounts) <= 3:
                return f"Explicit accounts: {', '.join(self.explicit_accounts)}"
            else:
                return f"Explicit accounts: {', '.join(self.explicit_accounts[:3])}, ... ({len(self.explicit_accounts)} total)"
        elif self.filter_type == FilterType.OU:
            return f"Accounts in organizational unit: {self.ou_filter}"
        elif self.filter_type == FilterType.PATTERN:
            return f"Accounts matching pattern: {self.account_name_pattern}"
        else:
            return f"Unknown filter type: {self.filter_expression}"

    def resolve_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts based on the filter expression or explicit account list.

        Returns:
            List of AccountInfo objects matching the filter

        Raises:
            ValueError: If filter validation fails
            ClientError: If AWS API calls fail
        """
        # Validate filter first
        validation_errors = self.validate_filter()
        if validation_errors:
            error_messages = [error.message for error in validation_errors]
            raise ValueError(f"Filter validation failed: {'; '.join(error_messages)}")

        if self.filter_type == FilterType.WILDCARD:
            return self._resolve_wildcard_accounts()
        elif self.filter_type == FilterType.TAG:
            return self._resolve_tag_filtered_accounts()
        elif self.filter_type == FilterType.EXPLICIT:
            return self._resolve_explicit_accounts()
        elif self.filter_type == FilterType.OU:
            return self._resolve_ou_filtered_accounts()
        elif self.filter_type == FilterType.PATTERN:
            return self._resolve_pattern_filtered_accounts()
        else:
            raise ValueError(f"Unsupported filter type: {self.filter_type}")

    def resolve_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve accounts using streaming with lazy evaluation for memory efficiency.

        This method uses Python generators to process accounts on-demand, making it
        suitable for handling thousands of accounts without loading them all into memory.

        Args:
            chunk_size: Number of accounts to process in each chunk for very large account sets

        Yields:
            AccountInfo objects matching the filter, one at a time

        Raises:
            ValueError: If filter validation fails
            ClientError: If AWS API calls fail
        """
        # Validate filter first
        validation_errors = self.validate_filter()
        if validation_errors:
            error_messages = [error.message for error in validation_errors]
            raise ValueError(f"Filter validation failed: {'; '.join(error_messages)}")

        if self.filter_type == FilterType.WILDCARD:
            yield from self._resolve_wildcard_accounts_streaming(chunk_size)
        elif self.filter_type == FilterType.TAG:
            yield from self._resolve_tag_filtered_accounts_streaming(chunk_size)
        elif self.filter_type == FilterType.EXPLICIT:
            yield from self._resolve_explicit_accounts_streaming(chunk_size)
        elif self.filter_type == FilterType.OU:
            yield from self._resolve_ou_filtered_accounts_streaming(chunk_size)
        elif self.filter_type == FilterType.PATTERN:
            yield from self._resolve_pattern_filtered_accounts_streaming(chunk_size)
        else:
            raise ValueError(f"Unsupported filter type: {self.filter_type}")

    def _resolve_wildcard_accounts(self) -> List[AccountInfo]:
        """
        Resolve all accounts in the organization using optimized caching.

        Returns:
            List of all AccountInfo objects in the organization
        """
        from .account_cache_optimizer import AccountCacheOptimizer

        # Get profile from the organizations client's client manager
        profile = getattr(self.organizations_client.client_manager, "profile", None)

        # Normalize profile name - use the actual profile being used by the client manager
        if profile is None:
            # If no profile was explicitly set, use "default" as the cache key
            # This ensures consistency regardless of what the actual default profile is
            profile = "default"

        # Use the optimized account cache for much better performance
        optimizer = AccountCacheOptimizer(self.organizations_client, profile=profile)
        return optimizer.get_all_accounts_optimized()

    def _resolve_wildcard_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve all accounts in the organization using streaming with chunked processing.

        This method processes accounts in chunks to handle very large account sets efficiently
        while maintaining memory efficiency through lazy evaluation.

        Args:
            chunk_size: Number of accounts to process in each chunk

        Yields:
            AccountInfo objects for all accounts in the organization
        """

        # Get profile from the organizations client's client manager
        profile = getattr(self.organizations_client.client_manager, "profile", None)

        # Normalize profile name - use the actual profile being used by the client manager
        if profile is None:
            # If no profile was explicitly set, use "default" as the cache key
            # This ensures consistency regardless of what the actual default profile is
            profile = "default"

        # Use streaming account resolution for memory efficiency

        # Process accounts in chunks for very large account sets
        current_chunk = []

        # Get accounts using the streaming approach from the organization hierarchy
        for account in self._get_all_accounts_streaming():
            current_chunk.append(account)

            # Yield chunk when it reaches the specified size
            if len(current_chunk) >= chunk_size:
                for account_info in current_chunk:
                    yield account_info
                current_chunk = []

        # Yield remaining accounts in the final chunk
        for account_info in current_chunk:
            yield account_info

    def _resolve_tag_filtered_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts matching tag filters.

        Returns:
            List of AccountInfo objects matching all tag filters
        """
        # First get all accounts
        all_accounts = self._resolve_wildcard_accounts()

        # Filter by tags
        filtered_accounts = []
        for account in all_accounts:
            if self._account_matches_all_tag_filters(account):
                filtered_accounts.append(account)

        return filtered_accounts

    def _resolve_tag_filtered_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve accounts matching tag filters using streaming with lazy evaluation.

        This method processes accounts on-demand and only yields accounts that match
        all specified tag filters, providing memory efficiency for large account sets.

        Args:
            chunk_size: Number of accounts to process in each chunk

        Yields:
            AccountInfo objects matching all tag filters
        """
        # Stream all accounts and filter by tags on-demand
        for account in self._resolve_wildcard_accounts_streaming(chunk_size):
            if self._account_matches_all_tag_filters(account):
                yield account

    def _resolve_explicit_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts from explicit account ID list.

        Returns:
            List of AccountInfo objects for the specified account IDs

        Raises:
            ValueError: If any account ID is invalid or inaccessible
        """
        resolved_accounts = []

        for account_id in self.explicit_accounts:
            try:
                # Get account details from Organizations API
                account_data = self.organizations_client.describe_account(account_id)

                # Convert to AccountInfo
                account_info = AccountInfo(
                    account_id=account_data.get("Id", account_id),
                    account_name=account_data.get("Name", f"Account-{account_id}"),
                    email=account_data.get("Email", ""),
                    status=account_data.get("Status", "UNKNOWN"),
                    tags=account_data.get("Tags", {}),
                    ou_path=[],  # OU path not needed for explicit accounts
                )

                resolved_accounts.append(account_info)

            except Exception as e:
                # Handle account not found or access denied
                error_msg = str(e).lower()
                if "accountnotfound" in error_msg or "does not exist" in error_msg:
                    raise ValueError(
                        f"Account ID '{account_id}' does not exist or is not accessible"
                    )
                elif "accessdenied" in error_msg or "unauthorized" in error_msg:
                    raise ValueError(
                        f"Access denied to account ID '{account_id}'. Check your permissions"
                    )
                else:
                    raise ValueError(f"Failed to access account ID '{account_id}': {str(e)}")

        return resolved_accounts

    def _resolve_explicit_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve accounts from explicit account ID list using streaming with chunked processing.

        This method processes explicit account IDs in chunks to handle very large
        explicit account lists efficiently while maintaining memory efficiency.

        Args:
            chunk_size: Number of account IDs to process in each chunk

        Yields:
            AccountInfo objects for the specified account IDs

        Raises:
            ValueError: If any account ID is invalid or inaccessible
        """
        # Process explicit accounts in chunks for very large lists
        for i in range(0, len(self.explicit_accounts), chunk_size):
            chunk = self.explicit_accounts[i : i + chunk_size]

            for account_id in chunk:
                try:
                    # Get account details from Organizations API
                    account_data = self.organizations_client.describe_account(account_id)

                    # Convert to AccountInfo
                    account_info = AccountInfo(
                        account_id=account_data.get("Id", account_id),
                        account_name=account_data.get("Name", f"Account-{account_id}"),
                        email=account_data.get("Email", ""),
                        status=account_data.get("Status", "UNKNOWN"),
                        tags=account_data.get("Tags", {}),
                        ou_path=[],  # OU path not needed for explicit accounts
                    )

                    yield account_info

                except Exception as e:
                    # Handle account not found or access denied
                    error_msg = str(e).lower()
                    if "accountnotfound" in error_msg or "does not exist" in error_msg:
                        raise ValueError(
                            f"Account ID '{account_id}' does not exist or is not accessible"
                        )
                    elif "accessdenied" in error_msg or "unauthorized" in error_msg:
                        raise ValueError(
                            f"Access denied to account ID '{account_id}'. Check your permissions"
                        )
                    else:
                        raise ValueError(f"Failed to access account ID '{account_id}': {str(e)}")

    def _account_matches_all_tag_filters(self, account: AccountInfo) -> bool:
        """
        Check if an account matches all tag filters.

        Args:
            account: AccountInfo to check

        Returns:
            True if account matches all tag filters, False otherwise
        """
        for tag_filter in self.tag_filters:
            if not account.matches_tag_filter(tag_filter["key"], tag_filter["value"]):
                return False
        return True

    def _get_all_accounts_in_organization(self) -> List[Dict[str, Any]]:
        """
        Get all accounts in the organization by traversing the hierarchy.

        Returns:
            List of account data dictionaries
        """
        from ..aws_clients.manager import build_organization_hierarchy
        from .models import OrgNode

        all_accounts = []

        # Build the organization hierarchy to get all accounts
        organization_tree = build_organization_hierarchy(self.organizations_client)

        # Recursively collect all accounts from the tree
        def collect_accounts_from_node(node: OrgNode) -> None:
            """Recursively collect account data from organization tree."""
            if node.is_account():
                # For account nodes, we need to get the full account data
                try:
                    account_data = self.organizations_client.describe_account(node.id)
                    all_accounts.append(account_data)
                except Exception as e:
                    from rich.console import Console

                    console = Console()
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

    def _get_all_accounts_streaming(self) -> Generator[AccountInfo, None, None]:
        """
        Get all accounts in the organization using streaming with lazy evaluation.

        This method uses generators to process accounts on-demand from the organization
        hierarchy, providing memory efficiency for very large account sets.

        Yields:
            AccountInfo objects for all accounts in the organization
        """
        from ..aws_clients.manager import build_organization_hierarchy
        from .models import OrgNode

        # Build the organization hierarchy to get all accounts
        organization_tree = build_organization_hierarchy(self.organizations_client)

        # Recursively yield accounts from the tree using generators
        def stream_accounts_from_node(node: OrgNode) -> Generator[AccountInfo, None, None]:
            """Recursively stream account data from organization tree."""
            if node.is_account():
                # For account nodes, we need to get the full account data
                try:
                    account_data = self.organizations_client.describe_account(node.id)

                    # Convert to AccountInfo and yield immediately
                    account_info = AccountInfo(
                        account_id=account_data.get("Id", node.id),
                        account_name=account_data.get("Name", f"Account-{node.id}"),
                        email=account_data.get("Email", ""),
                        status=account_data.get("Status", "UNKNOWN"),
                        tags=account_data.get("Tags", {}),
                        ou_path=getattr(node, "ou_path", []),
                    )

                    yield account_info

                except Exception as e:
                    from rich.console import Console

                    console = Console()
                    console.print(
                        f"[yellow]Warning: Could not get account data for {node.id}: {str(e)}[/yellow]"
                    )

            # Recursively process children
            for child in node.children:
                yield from stream_accounts_from_node(child)

        # Stream accounts from all root nodes
        for root in organization_tree:
            yield from stream_accounts_from_node(root)

    def _resolve_ou_filtered_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts matching organizational unit filter.

        Returns:
            List of AccountInfo objects in the specified OU path
        """
        # First get all accounts
        all_accounts = self._resolve_wildcard_accounts()

        logger.info(f"OU Filter: Retrieved {len(all_accounts)} total accounts")
        logger.info(f"OU Filter: Looking for accounts matching OU path: '{self.ou_filter}'")

        # Filter by OU path
        filtered_accounts = []
        for account in all_accounts:
            if self._account_matches_ou_filter(account):
                filtered_accounts.append(account)
                logger.debug(
                    f"OU Filter: Account {account.account_name} ({account.account_id}) matches OU path: {account.ou_path}"
                )
            else:
                logger.debug(
                    f"OU Filter: Account {account.account_name} ({account.account_id}) does not match OU path: {account.ou_path}"
                )

        logger.info(
            f"OU Filter: Found {len(filtered_accounts)} accounts matching OU filter '{self.ou_filter}'"
        )
        return filtered_accounts

    def _resolve_ou_filtered_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve accounts matching organizational unit filter using streaming.

        Args:
            chunk_size: Number of accounts to process in each chunk

        Yields:
            AccountInfo objects in the specified OU path
        """
        # Stream all accounts and filter by OU path on-demand
        for account in self._resolve_wildcard_accounts_streaming(chunk_size):
            if self._account_matches_ou_filter(account):
                yield account

    def _resolve_pattern_filtered_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts matching regex pattern filter.

        Returns:
            List of AccountInfo objects with names matching the pattern
        """
        # First get all accounts
        all_accounts = self._resolve_wildcard_accounts()

        # Filter by account name pattern
        filtered_accounts = []
        for account in all_accounts:
            if self._account_matches_pattern_filter(account):
                filtered_accounts.append(account)

        return filtered_accounts

    def _resolve_pattern_filtered_accounts_streaming(
        self, chunk_size: int = 100
    ) -> Generator[AccountInfo, None, None]:
        """
        Resolve accounts matching regex pattern filter using streaming.

        Args:
            chunk_size: Number of accounts to process in each chunk

        Yields:
            AccountInfo objects with names matching the pattern
        """
        # Stream all accounts and filter by pattern on-demand
        for account in self._resolve_wildcard_accounts_streaming(chunk_size):
            if self._account_matches_pattern_filter(account):
                yield account

    def _account_matches_ou_filter(self, account: AccountInfo) -> bool:
        """
        Check if an account matches the OU filter.

        Args:
            account: AccountInfo to check

        Returns:
            True if account is in the specified OU path, False otherwise
        """
        if not self.ou_filter or not account.ou_path:
            logger.debug(
                f"OU Filter: Account {account.account_name} ({account.account_id}) - no filter or no OU path"
            )
            return False

        # Convert OU path to string for matching
        account_ou_path = "/".join(account.ou_path)

        logger.debug(
            f"OU Filter: Comparing account OU path '{account_ou_path}' with filter '{self.ou_filter}'"
        )

        # Support both exact match and prefix match
        # Exact match: "Root/Production" matches exactly "Root/Production"
        # Prefix match: "Root/Production" matches "Root/Production/SubOU"
        matches = account_ou_path == self.ou_filter or account_ou_path.startswith(
            self.ou_filter + "/"
        )

        if matches:
            logger.debug(
                f"OU Filter: Account {account.account_name} ({account.account_id}) MATCHES filter '{self.ou_filter}'"
            )
        else:
            logger.debug(
                f"OU Filter: Account {account.account_name} ({account.account_id}) does NOT match filter '{self.ou_filter}'"
            )

        return matches

    def _account_matches_pattern_filter(self, account: AccountInfo) -> bool:
        """
        Check if an account matches the regex pattern filter.

        Args:
            account: AccountInfo to check

        Returns:
            True if account name matches the pattern, False otherwise
        """
        if not self.account_name_pattern:
            return False

        try:
            pattern = re.compile(self.account_name_pattern)
            return bool(pattern.search(account.account_name))
        except re.error:
            # If regex is invalid, return False (should be caught in validation)
            return False


def parse_multiple_tag_filters(tag_expressions: List[str]) -> List[Dict[str, str]]:
    """
    Parse multiple tag filter expressions from command line arguments.

    Supports formats like:
    - ["Environment=Production", "Team=Backend"]
    - ["Environment=Production,Team=Backend"]

    Args:
        tag_expressions: List of tag filter expressions

    Returns:
        List of tag filter dictionaries with 'key' and 'value' keys

    Raises:
        ValueError: If any tag filter format is invalid
    """
    all_tag_filters = []

    for expr in tag_expressions:
        expr = expr.strip()
        if not expr:
            continue

        # Handle comma-separated values within a single expression
        sub_expressions = [sub_expr.strip() for sub_expr in expr.split(",")]

        for sub_expr in sub_expressions:
            if not sub_expr:
                continue

            # Parse Key=Value format
            if "=" not in sub_expr:
                raise ValueError(
                    f"Invalid tag filter format: '{sub_expr}'. Expected format: Key=Value"
                )

            key, value = sub_expr.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                raise ValueError(f"Tag key cannot be empty in filter: '{sub_expr}'")

            if not value:
                raise ValueError(f"Tag value cannot be empty in filter: '{sub_expr}'")

            all_tag_filters.append({"key": key, "value": value})

    return all_tag_filters


def create_tag_filter_expression(tag_filters: List[Dict[str, str]]) -> str:
    """
    Create a tag filter expression from a list of tag filters.

    Args:
        tag_filters: List of tag filter dictionaries with 'key' and 'value' keys

    Returns:
        Tag filter expression string
    """
    if not tag_filters:
        return ""

    tag_expressions = []
    for tag_filter in tag_filters:
        tag_expressions.append(f"{tag_filter['key']}={tag_filter['value']}")

    return f"tag:{','.join(tag_expressions)}"
