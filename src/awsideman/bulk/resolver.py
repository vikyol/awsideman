"""Resource resolution components for bulk operations.

This module provides classes for resolving human-readable names to AWS resource identifiers
for bulk operations. Includes caching for performance optimization.

Classes:
    ResourceResolver: Resolves names to IDs/ARNs using AWS APIs
    AssignmentValidator: Validates resolved assignments against AWS resources
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

from ..aws_clients.manager import AWSClientManager

console = Console()


@dataclass
class ResolutionResult:
    """Result of a name resolution operation."""

    success: bool
    resolved_value: Optional[str] = None
    error_message: Optional[str] = None


class ResourceResolver:
    """Resolves human-readable names to AWS resource identifiers."""

    def __init__(
        self, aws_client_manager: AWSClientManager, instance_arn: str, identity_store_id: str
    ):
        """Initialize the resource resolver.

        Args:
            aws_client_manager: AWS client manager for API access
            instance_arn: SSO instance ARN
            identity_store_id: Identity Store ID
        """
        self.aws_client_manager = aws_client_manager
        self.instance_arn = instance_arn
        self.identity_store_id = identity_store_id

        # Initialize clients
        self.identity_store_client = aws_client_manager.get_identity_store_client()
        self.sso_admin_client = aws_client_manager.get_identity_center_client()
        self.organizations_client = aws_client_manager.get_organizations_client()

        # Caches for resolved names
        self._principal_cache: Dict[str, ResolutionResult] = {}
        self._permission_set_cache: Dict[str, ResolutionResult] = {}
        self._account_cache: Dict[str, ResolutionResult] = {}

        # Cache for account name to ID mapping from Organizations API
        self._account_name_to_id_cache: Dict[str, str] = {}
        self._account_id_to_name_cache: Dict[str, str] = {}

    def resolve_principal_name(self, principal_name: str, principal_type: str) -> ResolutionResult:
        """Resolve principal name to principal ID.

        Args:
            principal_name: Name of the user or group
            principal_type: Type of principal ('USER' or 'GROUP')

        Returns:
            ResolutionResult with principal ID or error message
        """
        cache_key = f"{principal_type}:{principal_name}"

        # Check cache first
        if cache_key in self._principal_cache:
            return self._principal_cache[cache_key]

        try:
            if principal_type.upper() == "USER":
                result = self._resolve_user_name(principal_name)
            elif principal_type.upper() == "GROUP":
                result = self._resolve_group_name(principal_name)
            else:
                result = ResolutionResult(
                    success=False,
                    error_message=f"Invalid principal type '{principal_type}'. Must be 'USER' or 'GROUP'",
                )

            # Cache the result
            self._principal_cache[cache_key] = result
            return result

        except Exception as e:
            result = ResolutionResult(
                success=False,
                error_message=f"Error resolving principal '{principal_name}': {str(e)}",
            )
            self._principal_cache[cache_key] = result
            return result

    def _resolve_user_name(self, user_name: str) -> ResolutionResult:
        """Resolve user name to user ID using Identity Store API."""
        try:
            # Use list_users with UserName filter
            response = self.identity_store_client.list_users(
                IdentityStoreId=self.identity_store_id,
                Filters=[{"AttributePath": "UserName", "AttributeValue": user_name}],
            )

            users = response.get("Users", [])

            if not users:
                return ResolutionResult(
                    success=False, error_message=f"User '{user_name}' not found in Identity Store"
                )

            if len(users) > 1:
                return ResolutionResult(
                    success=False, error_message=f"Multiple users found with name '{user_name}'"
                )

            user_id = users[0]["UserId"]
            return ResolutionResult(success=True, resolved_value=user_id)

        except ClientError as e:
            error_msg = f"AWS API error resolving user '{user_name}': {str(e)}"
            return ResolutionResult(success=False, error_message=error_msg)

    def _resolve_group_name(self, group_name: str) -> ResolutionResult:
        """Resolve group name to group ID using Identity Store API."""
        try:
            # Use list_groups with DisplayName filter
            response = self.identity_store_client.list_groups(
                IdentityStoreId=self.identity_store_id,
                Filters=[{"AttributePath": "DisplayName", "AttributeValue": group_name}],
            )

            groups = response.get("Groups", [])

            if not groups:
                return ResolutionResult(
                    success=False, error_message=f"Group '{group_name}' not found in Identity Store"
                )

            if len(groups) > 1:
                return ResolutionResult(
                    success=False, error_message=f"Multiple groups found with name '{group_name}'"
                )

            group_id = groups[0]["GroupId"]
            return ResolutionResult(success=True, resolved_value=group_id)

        except ClientError as e:
            error_msg = f"AWS API error resolving group '{group_name}': {str(e)}"
            return ResolutionResult(success=False, error_message=error_msg)

    def resolve_permission_set_name(self, permission_set_name: str) -> ResolutionResult:
        """Resolve permission set name to permission set ARN.

        Args:
            permission_set_name: Name of the permission set

        Returns:
            ResolutionResult with permission set ARN or error message
        """
        # Check cache first
        if permission_set_name in self._permission_set_cache:
            return self._permission_set_cache[permission_set_name]

        try:
            # List all permission sets and find by name
            response = self.sso_admin_client.list_permission_sets(InstanceArn=self.instance_arn)

            permission_set_arns = response.get("PermissionSets", [])

            # Check each permission set to find matching name
            for permission_set_arn in permission_set_arns:
                try:
                    ps_response = self.sso_admin_client.describe_permission_set(
                        InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                    )

                    ps_data = ps_response.get("PermissionSet", {})
                    ps_name = ps_data.get("Name", "")

                    if ps_name == permission_set_name:
                        result = ResolutionResult(success=True, resolved_value=permission_set_arn)
                        self._permission_set_cache[permission_set_name] = result
                        return result

                except ClientError as e:
                    # Continue checking other permission sets if one fails
                    console.print(
                        f"[yellow]Warning: Could not describe permission set {permission_set_arn}: {str(e)}[/yellow]"
                    )
                    continue

            # Permission set not found
            result = ResolutionResult(
                success=False, error_message=f"Permission set '{permission_set_name}' not found"
            )
            self._permission_set_cache[permission_set_name] = result
            return result

        except ClientError as e:
            error_msg = f"AWS API error resolving permission set '{permission_set_name}': {str(e)}"
            result = ResolutionResult(success=False, error_message=error_msg)
            self._permission_set_cache[permission_set_name] = result
            return result
        except Exception as e:
            error_msg = f"Error resolving permission set '{permission_set_name}': {str(e)}"
            result = ResolutionResult(success=False, error_message=error_msg)
            self._permission_set_cache[permission_set_name] = result
            return result

    def resolve_account_name(self, account_name: str) -> ResolutionResult:
        """Resolve account name to account ID.

        Args:
            account_name: Name of the AWS account

        Returns:
            ResolutionResult with account ID or error message
        """
        # Check cache first
        if account_name in self._account_cache:
            return self._account_cache[account_name]

        try:
            # Populate account cache if empty
            if not self._account_name_to_id_cache:
                self._populate_account_cache()

            # Look up account by name
            if account_name in self._account_name_to_id_cache:
                account_id = self._account_name_to_id_cache[account_name]
                result = ResolutionResult(success=True, resolved_value=account_id)
            else:
                result = ResolutionResult(
                    success=False,
                    error_message=f"Account '{account_name}' not found in organization",
                )

            self._account_cache[account_name] = result
            return result

        except Exception as e:
            error_msg = f"Error resolving account '{account_name}': {str(e)}"
            result = ResolutionResult(success=False, error_message=error_msg)
            self._account_cache[account_name] = result
            return result

    def _populate_account_cache(self):
        """Populate the account name to ID cache using Organizations API."""
        try:
            # Get all accounts in the organization
            from ..aws_clients.manager import build_organization_hierarchy

            organization_tree = build_organization_hierarchy(self.organizations_client)

            # Extract all accounts from the hierarchy
            def extract_accounts(node):
                """Recursively extract account information from organization tree."""
                if node.is_account():
                    # Get account details
                    try:
                        account_data = self.organizations_client.describe_account(node.id)
                        account_name = account_data.get("Name", "")
                        account_id = account_data.get("Id", "")

                        if account_name and account_id:
                            self._account_name_to_id_cache[account_name] = account_id
                            self._account_id_to_name_cache[account_id] = account_name
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not get details for account {node.id}: {str(e)}[/yellow]"
                        )

                # Process children
                for child in node.children:
                    extract_accounts(child)

            # Extract accounts from all roots
            for root in organization_tree:
                extract_accounts(root)

        except Exception as e:
            console.print(f"[yellow]Warning: Could not populate account cache: {str(e)}[/yellow]")

    def resolve_assignment(self, assignment: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve all names in assignment to IDs/ARNs.

        Args:
            assignment: Assignment dictionary with name-based fields

        Returns:
            Dictionary with resolved assignment data and resolution results
        """
        resolved_assignment = assignment.copy()
        resolution_errors = []

        # Resolve principal name to ID
        principal_name = assignment.get("principal_name", "")
        principal_type = assignment.get("principal_type", "USER")

        if principal_name:
            principal_result = self.resolve_principal_name(principal_name, principal_type)
            if principal_result.success:
                resolved_assignment["principal_id"] = principal_result.resolved_value
            else:
                resolution_errors.append(principal_result.error_message)

        # Resolve permission set name to ARN
        permission_set_name = assignment.get("permission_set_name", "")
        if permission_set_name:
            ps_result = self.resolve_permission_set_name(permission_set_name)
            if ps_result.success:
                resolved_assignment["permission_set_arn"] = ps_result.resolved_value
            else:
                resolution_errors.append(ps_result.error_message)

        # Resolve account name to ID
        account_name = assignment.get("account_name", "")
        if account_name:
            account_result = self.resolve_account_name(account_name)
            if account_result.success:
                resolved_assignment["account_id"] = account_result.resolved_value
            else:
                resolution_errors.append(account_result.error_message)

        # Add resolution status
        resolved_assignment["resolution_success"] = len(resolution_errors) == 0
        resolved_assignment["resolution_errors"] = resolution_errors

        return resolved_assignment

    def clear_cache(self):
        """Clear all resolution caches."""
        self._principal_cache.clear()
        self._permission_set_cache.clear()
        self._account_cache.clear()
        self._account_name_to_id_cache.clear()
        self._account_id_to_name_cache.clear()

    def clear_principal_cache(self):
        """Clear only the principal cache."""
        self._principal_cache.clear()

    def clear_permission_set_cache(self):
        """Clear only the permission set cache."""
        self._permission_set_cache.clear()

    def clear_account_cache(self):
        """Clear only the account cache."""
        self._account_cache.clear()
        self._account_name_to_id_cache.clear()
        self._account_id_to_name_cache.clear()

    def invalidate_principal(self, principal_name: str, principal_type: str):
        """Invalidate a specific principal from cache.

        Args:
            principal_name: Name of the principal to invalidate
            principal_type: Type of principal ('USER' or 'GROUP')
        """
        cache_key = f"{principal_type}:{principal_name}"
        self._principal_cache.pop(cache_key, None)

    def invalidate_permission_set(self, permission_set_name: str):
        """Invalidate a specific permission set from cache.

        Args:
            permission_set_name: Name of the permission set to invalidate
        """
        self._permission_set_cache.pop(permission_set_name, None)

    def invalidate_account(self, account_name: str):
        """Invalidate a specific account from cache.

        Args:
            account_name: Name of the account to invalidate
        """
        self._account_cache.pop(account_name, None)
        # Also remove from name-to-id mapping if present
        if account_name in self._account_name_to_id_cache:
            account_id = self._account_name_to_id_cache.pop(account_name)
            self._account_id_to_name_cache.pop(account_id, None)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache sizes
        """
        return {
            "principals": len(self._principal_cache),
            "permission_sets": len(self._permission_set_cache),
            "accounts": len(self._account_cache),
            "account_mappings": len(self._account_name_to_id_cache),
        }

    def get_cache_hit_ratio(self) -> Dict[str, float]:
        """Get cache hit ratios for performance monitoring.

        Returns:
            Dictionary with cache hit ratios (requires tracking hits/misses)
        """
        # This would require additional tracking of hits/misses
        # For now, return cache sizes as a proxy for effectiveness
        stats = self.get_cache_stats()
        return {
            "principals_cached": stats["principals"],
            "permission_sets_cached": stats["permission_sets"],
            "accounts_cached": stats["accounts"],
            "account_mappings_cached": stats["account_mappings"],
        }

    def warm_cache_for_assignments(self, assignments: List[Dict[str, Any]]):
        """Pre-warm caches for a list of assignments to optimize batch processing.

        Args:
            assignments: List of assignment dictionaries
        """
        # Extract unique names for pre-warming
        principal_names = set()
        permission_set_names = set()
        account_names = set()

        for assignment in assignments:
            principal_name = assignment.get("principal_name")
            principal_type = assignment.get("principal_type", "USER")
            permission_set_name = assignment.get("permission_set_name")
            account_name = assignment.get("account_name")

            if principal_name:
                principal_names.add((principal_name, principal_type))
            if permission_set_name:
                permission_set_names.add(permission_set_name)
            if account_name:
                account_names.add(account_name)

        # Pre-populate account cache first (most expensive operation)
        if account_names and not self._account_name_to_id_cache:
            try:
                self._populate_account_cache()
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not pre-warm account cache: {str(e)}[/yellow]"
                )

        # Pre-resolve permission sets
        for ps_name in permission_set_names:
            if ps_name not in self._permission_set_cache:
                try:
                    self.resolve_permission_set_name(ps_name)
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not pre-warm permission set '{ps_name}': {str(e)}[/yellow]"
                    )

        # Pre-resolve principals
        for principal_name, principal_type in principal_names:
            cache_key = f"{principal_type}:{principal_name}"
            if cache_key not in self._principal_cache:
                try:
                    self.resolve_principal_name(principal_name, principal_type)
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not pre-warm principal '{principal_name}': {str(e)}[/yellow]"
                    )


class AssignmentValidator:
    """Validates individual assignments against AWS resources."""

    def __init__(
        self, aws_client_manager: AWSClientManager, instance_arn: str, identity_store_id: str
    ):
        """Initialize the assignment validator.

        Args:
            aws_client_manager: AWS client manager for API access
            instance_arn: SSO instance ARN
            identity_store_id: Identity Store ID
        """
        self.aws_client_manager = aws_client_manager
        self.instance_arn = instance_arn
        self.identity_store_id = identity_store_id

        # Initialize clients
        self.identity_store_client = aws_client_manager.get_identity_store_client()
        self.sso_admin_client = aws_client_manager.get_identity_center_client()
        self.organizations_client = aws_client_manager.get_organizations_client()

    def validate_assignment(self, assignment: Dict[str, Any]) -> List[str]:
        """Validate a single assignment and return list of validation errors.

        Args:
            assignment: Assignment dictionary with resolved IDs/ARNs

        Returns:
            List of validation error messages
        """
        errors = []

        # Check if assignment has required resolved fields
        principal_id = assignment.get("principal_id")
        permission_set_arn = assignment.get("permission_set_arn")
        account_id = assignment.get("account_id")
        principal_type = assignment.get("principal_type", "USER")

        if not principal_id:
            errors.append("Missing resolved principal ID")

        if not permission_set_arn:
            errors.append("Missing resolved permission set ARN")

        if not account_id:
            errors.append("Missing resolved account ID")

        # If we have resolution errors, don't proceed with validation
        if assignment.get("resolution_errors"):
            errors.extend(assignment["resolution_errors"])
            return errors

        # Validate principal exists
        if principal_id:
            if not self.validate_principal(principal_id, principal_type):
                errors.append(
                    f"Principal {principal_id} ({principal_type}) does not exist or is not accessible"
                )

        # Validate permission set exists
        if permission_set_arn:
            if not self.validate_permission_set(permission_set_arn):
                errors.append(
                    f"Permission set {permission_set_arn} does not exist or is not accessible"
                )

        # Validate account exists
        if account_id:
            if not self.validate_account(account_id):
                errors.append(f"Account {account_id} does not exist or is not accessible")

        return errors

    def validate_principal(self, principal_id: str, principal_type: str) -> bool:
        """Validate that principal exists in Identity Store.

        Args:
            principal_id: Principal ID to validate
            principal_type: Type of principal ('USER' or 'GROUP')

        Returns:
            True if principal exists, False otherwise
        """
        try:
            if principal_type.upper() == "USER":
                self.identity_store_client.describe_user(
                    IdentityStoreId=self.identity_store_id, UserId=principal_id
                )
            elif principal_type.upper() == "GROUP":
                self.identity_store_client.describe_group(
                    IdentityStoreId=self.identity_store_id, GroupId=principal_id
                )
            else:
                return False

            return True

        except ClientError as e:
            if e.response["Error"]["Code"] in ["ResourceNotFoundException", "ValidationException"]:
                return False
            # For other errors, log and return False
            console.print(
                f"[yellow]Warning: Error validating principal {principal_id}: {str(e)}[/yellow]"
            )
            return False
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error validating principal {principal_id}: {str(e)}[/yellow]"
            )
            return False

    def validate_permission_set(self, permission_set_arn: str) -> bool:
        """Validate that permission set exists.

        Args:
            permission_set_arn: Permission set ARN to validate

        Returns:
            True if permission set exists, False otherwise
        """
        try:
            self.sso_admin_client.describe_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] in ["ResourceNotFoundException", "ValidationException"]:
                return False
            # For other errors, log and return False
            console.print(
                f"[yellow]Warning: Error validating permission set {permission_set_arn}: {str(e)}[/yellow]"
            )
            return False
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error validating permission set {permission_set_arn}: {str(e)}[/yellow]"
            )
            return False

    def validate_account(self, account_id: str) -> bool:
        """Validate that account exists and is accessible.

        Args:
            account_id: Account ID to validate

        Returns:
            True if account exists, False otherwise
        """
        try:
            self.organizations_client.describe_account(account_id)
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] in ["AccountNotFoundException", "ValidationException"]:
                return False
            # For other errors, log and return False
            console.print(
                f"[yellow]Warning: Error validating account {account_id}: {str(e)}[/yellow]"
            )
            return False
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error validating account {account_id}: {str(e)}[/yellow]"
            )
            return False

    def check_assignment_exists(
        self, principal_id: str, permission_set_arn: str, account_id: str
    ) -> bool:
        """Check if an assignment already exists.

        Args:
            principal_id: Principal ID
            permission_set_arn: Permission set ARN
            account_id: Account ID

        Returns:
            True if assignment exists, False otherwise
        """
        try:
            # List account assignments for the permission set and account
            response = self.sso_admin_client.list_account_assignments(
                InstanceArn=self.instance_arn,
                AccountId=account_id,
                PermissionSetArn=permission_set_arn,
            )

            assignments = response.get("AccountAssignments", [])

            # Check if any assignment matches the principal
            for assignment in assignments:
                if assignment.get("PrincipalId") == principal_id:
                    return True

            return False

        except ClientError as e:
            console.print(
                f"[yellow]Warning: Error checking assignment existence: {str(e)}[/yellow]"
            )
            return False
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error checking assignment existence: {str(e)}[/yellow]"
            )
            return False
