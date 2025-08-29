"""Shared utility functions for assignment commands.

This module contains common utility functions used across assignment command modules.
These functions handle operations like resolving permission sets and principals,
logging operations, and interactive input.
"""

import sys
from typing import Any, Dict, Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console

from ...utils.error_handler import handle_aws_error

console = Console()


def get_single_key():
    """
    Get a single key press without requiring Enter.

    Used for interactive pagination in the list command.
    Handles platform-specific keyboard input with fallbacks.
    """
    try:
        # Try to import platform-specific modules
        if sys.platform == "win32":
            import msvcrt

            return msvcrt.getch().decode("utf-8")
        else:
            import termios
            import tty

            # Save the terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                # Set terminal to raw mode
                tty.setraw(sys.stdin.fileno())
                # Read a single character
                key = sys.stdin.read(1)
                return key
            finally:
                # Restore terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except ImportError:
        # Fallback to input() if platform-specific modules are not available
        return input()
    except Exception:
        # Fallback to input() if anything goes wrong
        return input()


def resolve_permission_set_info(
    instance_arn: str, permission_set_arn: str, sso_admin_client: Any
) -> Dict[str, Any]:
    """
    Resolve permission set information from ARN.

    This function retrieves detailed information about a permission set based on its ARN.
    It provides error handling for invalid permission set ARNs.

    Args:
        instance_arn: SSO instance ARN
        permission_set_arn: Permission set ARN
        sso_admin_client: SSO admin client

    Returns:
        Dictionary containing permission set information including:
        - PermissionSetArn: The ARN of the permission set
        - Name: The name of the permission set
        - Description: The description of the permission set (if available)
        - SessionDuration: The session duration of the permission set

    Raises:
        typer.Exit: If the permission set cannot be found or an error occurs
    """
    try:
        # Make the API call to describe the permission set
        response = sso_admin_client.describe_permission_set(
            InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
        )

        # Extract permission set information
        permission_set = response.get("PermissionSet", {})

        # Create a dictionary with the permission set information
        permission_set_info = {
            "PermissionSetArn": permission_set_arn,
            "Name": permission_set.get("Name", "Unknown"),
            "Description": permission_set.get("Description", None),
            "SessionDuration": permission_set.get("SessionDuration", "PT1H"),
        }

        return permission_set_info

    except sso_admin_client.exceptions.ResourceNotFoundException:
        console.print(
            f"[red]Error: Permission set with ARN '{permission_set_arn}' not found.[/red]"
        )
        console.print("[yellow]Check the permission set ARN and try again.[/yellow]")
        console.print(
            "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
        )
        raise typer.Exit(1)
    except ClientError as e:
        # Handle AWS API errors with centralized error handling
        handle_aws_error(e, "DescribePermissionSet")
        # This line is unreachable as handle_aws_error raises an exception
        return {}  # type: ignore[unreachable]
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def resolve_principal_info(
    identity_store_id: str, principal_id: str, principal_type: str, identity_store_client: Any
) -> Dict[str, Any]:
    """
    Resolve principal information (name, type) from principal ID.

    This function retrieves detailed information about a principal (user or group)
    based on its ID and type. It handles both USER and GROUP principal types and
    provides error handling for invalid principal IDs.

    Args:
        identity_store_id: Identity store ID
        principal_id: Principal ID to resolve
        principal_type: Type of principal (USER or GROUP)
        identity_store_client: Identity store client

    Returns:
        Dictionary containing principal information including:
        - PrincipalId: The ID of the principal
        - PrincipalType: The type of principal (USER or GROUP)
        - PrincipalName: The name of the principal (username for users, display name for groups)
        - DisplayName: The display name of the principal (if available)

    Raises:
        typer.Exit: If the principal cannot be found or an error occurs
    """
    try:
        principal_info = {
            "PrincipalId": principal_id,
            "PrincipalType": principal_type,
            "PrincipalName": None,
            "DisplayName": None,
        }

        # Handle USER principal type
        if principal_type.upper() == "USER":
            try:
                # Get user details
                user_response = identity_store_client.describe_user(
                    IdentityStoreId=identity_store_id, UserId=principal_id
                )

                # Extract user information
                principal_info["PrincipalName"] = user_response.get("UserName", "Unknown")
                principal_info["DisplayName"] = user_response.get("DisplayName", None)

                # If no display name is available, try to construct one from name components
                if not principal_info["DisplayName"]:
                    name_info = user_response.get("Name", {})
                    given_name = name_info.get("GivenName", "")
                    family_name = name_info.get("FamilyName", "")

                    if given_name or family_name:
                        principal_info["DisplayName"] = f"{given_name} {family_name}".strip()

                # If we still don't have a display name, use the username
                if not principal_info["DisplayName"]:
                    principal_info["DisplayName"] = principal_info["PrincipalName"]

                return principal_info

            except identity_store_client.exceptions.ResourceNotFoundException:
                console.print(f"[red]Error: User with ID '{principal_id}' not found.[/red]")
                console.print("[yellow]Check the user ID and try again.[/yellow]")
                raise typer.Exit(1)

        # Handle GROUP principal type
        elif principal_type.upper() == "GROUP":
            try:
                # Get group details
                group_response = identity_store_client.describe_group(
                    IdentityStoreId=identity_store_id, GroupId=principal_id
                )

                # Extract group information
                principal_info["PrincipalName"] = group_response.get("DisplayName", "Unknown")
                principal_info["DisplayName"] = group_response.get("DisplayName", "Unknown")

                return principal_info

            except identity_store_client.exceptions.ResourceNotFoundException:
                console.print(f"[red]Error: Group with ID '{principal_id}' not found.[/red]")
                console.print("[yellow]Check the group ID and try again.[/yellow]")
                raise typer.Exit(1)

        # Handle invalid principal type
        else:
            console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
            console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with centralized error handling
        operation = "DescribeUser" if principal_type.upper() == "USER" else "DescribeGroup"
        handle_aws_error(e, operation)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def log_individual_operation(
    operation_type: str,
    principal_id: str,
    principal_type: str,
    principal_name: str,
    permission_set_arn: str,
    permission_set_name: str,
    account_id: str,
    success: bool = True,
    error: Optional[str] = None,
    request_id: Optional[str] = None,
    profile: Optional[str] = None,
) -> None:
    """Log an individual assignment operation for rollback tracking.

    Args:
        operation_type: Type of operation (assign or revoke)
        principal_id: Principal ID
        principal_type: Principal type (USER or GROUP)
        principal_name: Principal name for display
        permission_set_arn: Permission set ARN
        permission_set_name: Permission set name for display
        account_id: Target account ID
        success: Whether the operation was successful
        error: Error message if operation failed
        request_id: AWS request ID for tracking
    """
    from ...rollback.logger import OperationLogger

    try:
        # Create operation logger instance with profile isolation
        logger = OperationLogger(profile=profile)

        # Create result for this single account operation
        result = {
            "account_id": account_id,
            "success": success,
            "error": error,
        }

        # Create metadata with request ID
        metadata = {"source": "individual_assignment"}
        if request_id:
            metadata["request_id"] = request_id

        # Log the operation with the correct interface
        operation_id = logger.log_operation(
            operation_type=operation_type,
            principal_id=principal_id,
            principal_type=principal_type,
            principal_name=principal_name,
            permission_set_arn=permission_set_arn,
            permission_set_name=permission_set_name,
            account_ids=[account_id],
            account_names=[account_id],  # Use account ID as name if name not available
            results=[result],
            metadata=metadata,
        )

        # Print success message
        console.print(f"[green]Logged {operation_type} operation: {operation_id}[/green]")

    except Exception as e:
        # Don't fail the main operation if logging fails
        console.print(f"[yellow]Warning: Failed to log operation: {str(e)}[/yellow]")
