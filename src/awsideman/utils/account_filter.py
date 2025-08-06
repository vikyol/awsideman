"""Account filtering infrastructure for multi-account operations."""
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Union
from enum import Enum

from .models import AccountDetails
from ..aws_clients.manager import OrganizationsClientWrapper


class FilterType(str, Enum):
    """Enumeration for account filter types."""
    WILDCARD = "WILDCARD"
    TAG = "TAG"


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
            ou_path=account_details.ou_path.copy()
        )


class AccountFilter:
    """
    Account filter for multi-account operations.
    
    Supports wildcard and tag-based filtering of AWS accounts.
    """
    
    def __init__(self, filter_expression: str, organizations_client: OrganizationsClientWrapper):
        """
        Initialize the account filter.
        
        Args:
            filter_expression: Filter expression (e.g., "*" or "tag:Environment=Production")
            organizations_client: Organizations client for account discovery
        """
        self.filter_expression = filter_expression.strip()
        self.organizations_client = organizations_client
        self.filter_type = self._determine_filter_type()
        self.tag_filters = self._parse_tag_filters() if self.filter_type == FilterType.TAG else []
    
    def _determine_filter_type(self) -> FilterType:
        """
        Determine the type of filter based on the expression.
        
        Returns:
            FilterType enum value
        """
        if self.filter_expression == "*":
            return FilterType.WILDCARD
        elif self.filter_expression.startswith("tag:"):
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
        Validate the filter expression.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if not self.filter_expression:
            errors.append(ValidationError(
                message="Filter expression cannot be empty",
                field="filter_expression",
                value=self.filter_expression
            ))
            return errors
        
        try:
            if self.filter_type == FilterType.TAG:
                # Validate tag filter parsing
                self._parse_tag_filters()
            elif self.filter_type == FilterType.WILDCARD:
                # Validate wildcard filter
                if self.filter_expression != "*":
                    errors.append(ValidationError(
                        message=f"Invalid wildcard filter: '{self.filter_expression}'. Only '*' is supported",
                        field="filter_expression",
                        value=self.filter_expression
                    ))
        except ValueError as e:
            errors.append(ValidationError(
                message=str(e),
                field="filter_expression",
                value=self.filter_expression
            ))
        
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
        else:
            return f"Unknown filter type: {self.filter_expression}"
    
    def resolve_accounts(self) -> List[AccountInfo]:
        """
        Resolve accounts based on the filter expression.
        
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
        else:
            raise ValueError(f"Unsupported filter type: {self.filter_type}")
    
    def _resolve_wildcard_accounts(self) -> List[AccountInfo]:
        """
        Resolve all accounts in the organization.
        
        Returns:
            List of all AccountInfo objects in the organization
        """
        from ..aws_clients.manager import get_account_details
        
        # Get all accounts by traversing the organization hierarchy
        all_accounts_data = self._get_all_accounts_in_organization()
        
        account_infos = []
        for account_data in all_accounts_data:
            try:
                account_details = get_account_details(self.organizations_client, account_data['Id'])
                account_info = AccountInfo.from_account_details(account_details)
                account_infos.append(account_info)
            except Exception as e:
                # Log warning but continue with other accounts
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]Warning: Could not get details for account {account_data.get('Id', 'unknown')}: {str(e)}[/yellow]")
                continue
        
        return account_infos
    
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
    
    def _account_matches_all_tag_filters(self, account: AccountInfo) -> bool:
        """
        Check if an account matches all tag filters.
        
        Args:
            account: AccountInfo to check
            
        Returns:
            True if account matches all tag filters, False otherwise
        """
        for tag_filter in self.tag_filters:
            if not account.matches_tag_filter(tag_filter['key'], tag_filter['value']):
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
                    console.print(f"[yellow]Warning: Could not get account data for {node.id}: {str(e)}[/yellow]")
            
            # Recursively process children
            for child in node.children:
                collect_accounts_from_node(child)
        
        # Collect accounts from all root nodes
        for root in organization_tree:
            collect_accounts_from_node(root)
        
        return all_accounts


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
                raise ValueError(f"Invalid tag filter format: '{sub_expr}'. Expected format: Key=Value")
            
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