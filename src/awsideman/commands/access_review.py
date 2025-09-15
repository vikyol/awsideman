"""
Access Review Commands

Provides basic access review functionality for exporting permissions
for specified accounts or principals.
"""

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config

app = typer.Typer(help="Access review commands for exporting permissions.")
console = Console()
config = Config()

# Rate limiting for permission set describe operations
_last_permission_set_call = 0
_permission_set_call_delay = 0.1  # 100ms delay between calls


def validate_profile(profile_name: Optional[str] = None) -> tuple[str, dict]:
    """Validate the profile and return profile name and data."""
    profile_name = profile_name or config.get("default_profile")

    if not profile_name:
        console.print("[red]Error: No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        raise typer.Exit(1)

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Error: Profile '{profile_name}' does not exist.[/red]")
        console.print("Use 'awsideman profile add' to create a new profile.")
        raise typer.Exit(1)

    return profile_name, profiles[profile_name]


def validate_sso_instance(profile_data: dict, profile_name: str = None) -> tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    If no SSO instance is configured, it attempts to auto-detect one when there's only
    one available in the AWS account. This implements the "lazy human" approach where
    awsideman automatically configures itself when possible.

    Args:
        profile_data: Profile data dictionary containing configuration
        profile_name: Profile name for auto-detection (optional)

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # If both are configured, return them immediately
    if instance_arn and identity_store_id:
        return instance_arn, identity_store_id

    # If not configured, try to auto-detect
    if profile_name:
        try:
            console.print("[blue]No SSO instance configured. Attempting auto-detection...[/blue]")

            # Create AWS client manager to discover SSO instances
            region = profile_data.get("region")
            aws_client = AWSClientManager(profile=profile_name, region=region)

            # List available SSO instances
            sso_client = aws_client.get_identity_center_client()
            response = sso_client.list_instances()
            instances = response.get("Instances", [])

            if not instances:
                console.print("[red]Error: No SSO instances found in AWS account.[/red]")
                console.print(
                    "[yellow]Make sure your AWS profile has access to AWS Identity Center.[/yellow]"
                )
                raise typer.Exit(1)

            if len(instances) == 1:
                # Auto-configure the single instance
                instance = instances[0]
                auto_instance_arn = instance["InstanceArn"]
                auto_identity_store_id = instance["IdentityStoreId"]

                console.print(
                    f"[green]Auto-detected single SSO instance: {auto_instance_arn}[/green]"
                )
                console.print(f"[green]Identity Store ID: {auto_identity_store_id}[/green]")

                # Auto-save the configuration for future use
                try:
                    profiles = config.get("profiles", {})
                    if profile_name in profiles:
                        profiles[profile_name]["sso_instance_arn"] = auto_instance_arn
                        profiles[profile_name]["identity_store_id"] = auto_identity_store_id
                        config.set("profiles", profiles)
                        console.print(
                            f"[green]Auto-configured SSO instance for profile '{profile_name}'[/green]"
                        )
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not save auto-configuration: {str(e)}[/yellow]"
                    )
                    console.print("[yellow]Configuration will be lost after this session.[/yellow]")

                return auto_instance_arn, auto_identity_store_id

            else:
                # Multiple instances found - user must choose
                console.print(
                    f"[red]Error: Found {len(instances)} SSO instances. Auto-detection not possible.[/red]"
                )
                console.print("[yellow]Available instances:[/yellow]")
                for i, instance in enumerate(instances, 1):
                    instance_id = instance["InstanceArn"].split("/")[-1]
                    console.print(f"[yellow]  {i}. Instance ID: {instance_id}[/yellow]")
                console.print(
                    "\n[yellow]Please use 'awsideman sso set <instance_arn> <identity_store_id>' to configure one.[/yellow]"
                )
                console.print("[yellow]You can find full ARNs with 'awsideman sso list'.[/yellow]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error during SSO instance auto-detection: {str(e)}[/red]")
            console.print("[yellow]Falling back to manual configuration.[/yellow]")

    # If auto-detection failed or profile_name not provided, show manual configuration message
    console.print("[red]Error: No SSO instance configured for this profile.[/red]")
    console.print(
        "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
    )
    console.print("You can find available SSO instances with 'awsideman sso list'.")
    raise typer.Exit(1)


@app.command("account")
def export_account(
    account_id: Optional[str] = typer.Argument(
        None, help="AWS account ID to review, or '*' for all accounts"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    include_inactive: bool = typer.Option(
        False, "--include-inactive", help="Include inactive assignments"
    ),
    filter_scope: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Filter accounts by scope: 'tag:env=dev' or 'tags:env=dev', 'ou:development', 'accounts:111111111111,222222222222'",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Export all permissions for a specific account or all accounts.

    Use '*' as account_id to export permissions across all accounts in the organization.
    This requires AWS Organizations access.

    Examples:
        # Export permissions for a specific account
        $ awsideman access-review account 111111111111

        # Export permissions for all accounts
        $ awsideman access-review account '*'

        # Export permissions for accounts with specific tag
        $ awsideman access-review account '*' --filter 'tag:env=dev'

        # Export permissions for accounts in development OU
        $ awsideman access-review account '*' --filter 'ou:development'

        # Export to CSV with tag filtering
        $ awsideman access-review account '*' --filter 'tag:Environment=Production' --format csv --output prod_permissions.csv
    """
    try:
        # Validate profile and SSO instance
        profile_name, profile_data = validate_profile(profile)

        # CRITICAL FIX: Use profile-specific SSO instance instead of list_instances()
        # This prevents profile mixing and security vulnerabilities

        # Check if profile has SSO instance configured
        instance_arn = profile_data.get("sso_instance_arn")
        identity_store_id = profile_data.get("identity_store_id")

        if not instance_arn or not identity_store_id:
            # Auto-detection is only safe when we have a single profile context
            # For security reasons, we require explicit configuration
            console.print("[red]Error: No SSO instance configured for this profile.[/red]")
            console.print("[yellow]For security reasons, auto-detection is disabled.[/yellow]")
            console.print(
                "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
            )
            console.print("You can find available SSO instances with 'awsideman sso list'.")
            raise typer.Exit(1)

        console.print(f"[green]Using configured SSO instance: {instance_arn}[/green]")
        console.print(f"[green]Identity Store ID: {identity_store_id}[/green]")

        # Initialize AWS clients with caching enabled
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region, enable_caching=True)
        sso_admin_client = client_manager.get_identity_center_client()
        identitystore_client = client_manager.get_identity_store_client()

        # Handle account_id logic
        if account_id is None:
            if filter_scope:
                # When no account_id is provided but filter is, treat as all accounts with filter
                account_id = "*"
            else:
                console.print("[red]Error: Either account_id or --filter must be specified[/red]")
                console.print(
                    "Use '*' for all accounts or specify a filter like '--filter tags:env=dev'"
                )
                raise typer.Exit(1)

        if account_id == "*":
            if filter_scope:
                console.print(
                    f"Exporting permissions for accounts matching filter: [bold]{filter_scope}[/bold]"
                )
                # Parse filter and get target accounts
                target_accounts = _parse_scope_and_get_accounts(filter_scope, client_manager)

                if not target_accounts:
                    console.print(
                        "[yellow]No accounts found matching the specified filter.[/yellow]"
                    )
                    return

                console.print(f"[blue]Found {len(target_accounts)} accounts matching filter[/blue]")

                # Get assignments for filtered accounts
                assignments = []
                total_accounts = len(target_accounts)
                for idx, account in enumerate(target_accounts, start=1):
                    account_id = account["Id"]
                    account_name = account["Name"]
                    console.print(
                        f"[blue]Processing account {idx}/{total_accounts}: {account_name} ({account_id})[/blue]"
                    )
                    try:
                        account_assignments = _get_account_assignments(
                            sso_admin_client, instance_arn, account_id
                        )
                        # Add account info to each assignment
                        for assignment in account_assignments:
                            assignment["AccountId"] = account_id
                            assignment["AccountName"] = account_name
                        assignments.extend(account_assignments)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not get assignments for account {account_name}: {e}[/yellow]"
                        )
                        continue
            else:
                console.print("Exporting permissions for all accounts")
                # Get all assignments across all accounts
                assignments = _get_all_account_assignments(
                    sso_admin_client, instance_arn, client_manager
                )
        else:
            console.print(f"Exporting permissions for account: [bold]{account_id}[/bold]")
            # Get all assignments for the specific account
            assignments = _get_account_assignments(sso_admin_client, instance_arn, account_id)

        # Enrich assignments with details
        enriched_assignments = []
        for assignment in assignments:
            enriched = _enrich_assignment(
                sso_admin_client, identitystore_client, instance_arn, identity_store_id, assignment
            )
            if enriched and (include_inactive or enriched.get("status") == "ACTIVE"):
                enriched_assignments.append(enriched)

        # Generate output
        if output_format == "json":
            if account_id == "*":
                if filter_scope:
                    output_data = {
                        "scope": f"filtered_accounts: {filter_scope}",
                        "export_timestamp": datetime.now(timezone.utc).isoformat(),
                        "total_assignments": len(enriched_assignments),
                        "assignments": enriched_assignments,
                    }
                else:
                    output_data = {
                        "scope": "all_accounts",
                        "export_timestamp": datetime.now(timezone.utc).isoformat(),
                        "total_assignments": len(enriched_assignments),
                        "assignments": enriched_assignments,
                    }
            else:
                output_data = {
                    "account_id": account_id,
                    "export_timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_assignments": len(enriched_assignments),
                    "assignments": enriched_assignments,
                }
            _output_json(output_data, output_file)
        elif output_format == "csv":
            if account_id == "*":
                if filter_scope:
                    # Create a safe filename from the filter
                    safe_filter = filter_scope.replace(":", "_").replace("=", "_").replace(",", "_")
                    _output_csv(
                        enriched_assignments,
                        output_file,
                        f"filtered_accounts_{safe_filter}_permissions",
                    )
                else:
                    _output_csv(enriched_assignments, output_file, "all_accounts_permissions")
            else:
                _output_csv(enriched_assignments, output_file, f"account_{account_id}_permissions")
        else:
            if account_id == "*":
                if filter_scope:
                    _output_table(
                        enriched_assignments, f"Permissions for Filtered Accounts: {filter_scope}"
                    )
                else:
                    _output_table(enriched_assignments, "Permissions for All Accounts")
            else:
                _output_table(enriched_assignments, f"Permissions for Account: {account_id}")

        console.print(f"[green]Found {len(enriched_assignments)} permission assignments[/green]")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error exporting account permissions: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("principal")
def export_principal(
    principal_name: str = typer.Argument(..., help="Principal name (user or group)"),
    principal_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Principal type (USER or GROUP, auto-detected if not specified)"
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="Specific account ID to check (optional, searches all accounts if omitted)",
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    include_inactive: bool = typer.Option(
        False, "--include-inactive", help="Include inactive assignments"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Export all permissions for a specific principal (user or group)."""
    try:
        # Validate profile and SSO instance
        profile_name, profile_data = validate_profile(profile)
        instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)

        # Initialize AWS clients with caching enabled
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region, enable_caching=True)
        sso_admin_client = client_manager.get_identity_center_client()
        identitystore_client = client_manager.get_identity_store_client()

        console.print(f"Exporting permissions for principal: [bold]{principal_name}[/bold]")

        # Resolve principal ID and type
        principal_id, resolved_type = _resolve_principal(
            identitystore_client, identity_store_id, principal_name, principal_type
        )

        if not principal_id:
            console.print(f"[red]Error: Principal '{principal_name}' not found[/red]")
            raise typer.Exit(1)

        # Get all assignments for the principal
        if account_id:
            # If account ID is specified, only check that account
            assignments = _get_principal_assignments_for_account(
                sso_admin_client, instance_arn, principal_id, resolved_type, account_id
            )

            # For users, also get inherited assignments from group memberships for this account
            inherited_assignments = []
            if resolved_type == "USER":
                inherited_assignments = _get_user_inherited_assignments(
                    sso_admin_client,
                    identitystore_client,
                    instance_arn,
                    identity_store_id,
                    principal_id,
                    account_id,
                    client_manager,
                )
        else:
            # Use consolidated search for organization-wide queries (much more efficient)
            console.print(
                f"[blue]Searching {resolved_type} across the entire organization (optimized)...[/blue]"
            )
            assignments, inherited_assignments = _get_consolidated_principal_assignments(
                sso_admin_client,
                identitystore_client,
                instance_arn,
                identity_store_id,
                principal_id,
                resolved_type,
                client_manager,
            )

        # Mark direct assignments
        for assignment in assignments:
            assignment["inheritance_source"] = "DIRECT"

        # Combine direct and inherited assignments
        all_assignments = assignments + inherited_assignments

        # Resolve account names for all assignments
        if not account_id:  # Only resolve names when searching across all accounts
            all_assignments = _resolve_account_names(all_assignments, client_manager)

        # Enrich assignments with details
        enriched_assignments = []
        for assignment in all_assignments:
            enriched = _enrich_assignment(
                sso_admin_client, identitystore_client, instance_arn, identity_store_id, assignment
            )
            if enriched and (include_inactive or enriched.get("status") == "ACTIVE"):
                enriched_assignments.append(enriched)

        # Generate output
        if output_format == "json":
            # Separate direct and inherited assignments for better JSON structure
            direct_assignments = [
                a for a in enriched_assignments if a.get("inheritance_source") == "DIRECT"
            ]
            inherited_assignments = [
                a for a in enriched_assignments if a.get("inheritance_source") == "GROUP"
            ]

            output_data = {
                "principal_name": principal_name,
                "principal_id": principal_id,
                "principal_type": resolved_type,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_assignments": len(enriched_assignments),
                "direct_assignments_count": len(direct_assignments),
                "inherited_assignments_count": len(inherited_assignments),
                "assignments": enriched_assignments,
            }

            # Add inheritance summary for users
            if resolved_type == "USER" and inherited_assignments:
                groups_with_permissions = set()
                for assignment in inherited_assignments:
                    if assignment.get("inheritance_group_name"):
                        groups_with_permissions.add(assignment["inheritance_group_name"])
                output_data["inherited_from_groups"] = list(groups_with_permissions)

            _output_json(output_data, output_file)
        elif output_format == "csv":
            _output_csv(
                enriched_assignments, output_file, f"principal_{principal_name}_permissions"
            )
        else:
            _output_table(
                enriched_assignments, f"Permissions for {resolved_type}: {principal_name}"
            )

        # Generate summary
        direct_count = len(
            [a for a in enriched_assignments if a.get("inheritance_source") == "DIRECT"]
        )
        inherited_count = len(
            [a for a in enriched_assignments if a.get("inheritance_source") == "GROUP"]
        )

        if resolved_type == "USER" and inherited_count > 0:
            console.print(
                f"[green]Found {len(enriched_assignments)} total permission assignments[/green]"
            )
            console.print(f"[blue]  • {direct_count} direct assignments[/blue]")
            console.print(f"[blue]  • {inherited_count} inherited from group memberships[/blue]")
        else:
            console.print(
                f"[green]Found {len(enriched_assignments)} permission assignments[/green]"
            )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error exporting principal permissions: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("permission-set")
def export_permission_set(
    permission_set_name: str = typer.Argument(..., help="Permission set name"),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="Specific account ID to check (optional, searches all accounts if omitted)",
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    include_inactive: bool = typer.Option(
        False, "--include-inactive", help="Include inactive assignments"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Export all assignments for a specific permission set."""
    try:
        # Validate profile and SSO instance
        profile_name, profile_data = validate_profile(profile)
        instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)

        # Initialize AWS clients
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region, enable_caching=True)
        sso_admin_client = client_manager.get_identity_center_client()
        identitystore_client = client_manager.get_identity_store_client()

        console.print(
            f"Exporting assignments for permission set: [bold]{permission_set_name}[/bold]"
        )

        # Resolve permission set ARN
        permission_set_arn = _resolve_permission_set(
            sso_admin_client, instance_arn, permission_set_name
        )

        if not permission_set_arn:
            console.print(f"[red]Error: Permission set '{permission_set_name}' not found[/red]")
            raise typer.Exit(1)

        # Get all assignments for the permission set
        if account_id:
            # If account ID is specified, only check that account
            assignments = _get_permission_set_assignments_for_account(
                sso_admin_client, instance_arn, permission_set_arn, account_id
            )
        else:
            # Try to get assignments across all accounts (requires Organizations access)
            assignments = _get_permission_set_assignments(
                sso_admin_client, instance_arn, permission_set_arn, client_manager
            )

        # Resolve account names for all assignments
        if not account_id:  # Only resolve names when searching across all accounts
            assignments = _resolve_account_names(assignments, client_manager)

        # Enrich assignments with details
        enriched_assignments = []
        for assignment in assignments:
            enriched = _enrich_assignment(
                sso_admin_client, identitystore_client, instance_arn, identity_store_id, assignment
            )
            if enriched and (include_inactive or enriched.get("status") == "ACTIVE"):
                enriched_assignments.append(enriched)

        # Generate output
        if output_format == "json":
            output_data = {
                "permission_set_name": permission_set_name,
                "permission_set_arn": permission_set_arn,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_assignments": len(enriched_assignments),
                "assignments": enriched_assignments,
            }
            _output_json(output_data, output_file)
        elif output_format == "csv":
            _output_csv(
                enriched_assignments,
                output_file,
                f"permission_set_{permission_set_name}_assignments",
            )
        else:
            _output_table(
                enriched_assignments, f"Assignments for Permission Set: {permission_set_name}"
            )

        console.print(f"[green]Found {len(enriched_assignments)} assignments[/green]")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error exporting permission set assignments: {str(e)}[/red]")
        raise typer.Exit(1)


def _get_account_assignments(
    sso_admin_client, instance_arn: str, account_id: str
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific account."""
    assignments = []

    try:
        # First, get all permission sets in the instance
        ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
        permission_sets = []

        for page in ps_paginator.paginate(InstanceArn=instance_arn):
            permission_sets.extend(page.get("PermissionSets", []))

        # For each permission set, get assignments for this account
        for permission_set_arn in permission_sets:
            try:
                response = sso_admin_client.list_account_assignments(
                    InstanceArn=instance_arn,
                    AccountId=account_id,
                    PermissionSetArn=permission_set_arn,
                )
                assignments.extend(response.get("AccountAssignments", []))
            except Exception as e:
                # Skip permission sets that cause errors (might not have assignments)
                console.print(
                    f"[yellow]Warning: Could not get assignments for permission set {permission_set_arn}: {str(e)}[/yellow]"
                )
                continue

    except ClientError as e:
        console.print(f"[red]Error getting account assignments: {str(e)}[/red]")
        raise  # Re-raise ClientError to be handled by the calling function
    except Exception as e:
        console.print(f"[red]Error getting account assignments: {str(e)}[/red]")

    return assignments


def _get_all_account_assignments(
    sso_admin_client, instance_arn: str, client_manager: AWSClientManager
) -> List[Dict[str, Any]]:
    """Get all assignments across all accounts."""
    assignments = []

    try:
        # Get all accounts first
        raw_org_client = client_manager.get_raw_organizations_client()
        paginator = raw_org_client.get_paginator("list_accounts")
        all_accounts = []
        for page in paginator.paginate():
            all_accounts.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts
        accounts = [acc for acc in all_accounts if acc.get("Status") == "ACTIVE"]
        suspended_count = len(all_accounts) - len(accounts)

        total_accounts = len(accounts)
        console.print(
            f"[blue]Found {len(all_accounts)} total accounts, {suspended_count} suspended/closed (excluded), {total_accounts} active accounts to process[/blue]"
        )

        # Get all permission sets
        ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
        permission_sets = []
        for page in ps_paginator.paginate(InstanceArn=instance_arn):
            permission_sets.extend(page.get("PermissionSets", []))
        console.print(f"[blue]Found {len(permission_sets)} permission sets[/blue]")

        # For each account and permission set combination, get assignments
        for idx, account in enumerate(accounts, start=1):
            account_id = account["Id"]
            account_name = account["Name"]
            console.print(
                f"[blue]Processing account {idx}/{total_accounts}: {account_name} ({account_id})[/blue]"
            )

            for permission_set_arn in permission_sets:
                try:
                    response = sso_admin_client.list_account_assignments(
                        InstanceArn=instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=permission_set_arn,
                    )
                    account_assignments = response.get("AccountAssignments", [])

                    # Add account info to each assignment
                    for assignment in account_assignments:
                        assignment["AccountId"] = account_id
                        assignment["AccountName"] = account_name

                    assignments.extend(account_assignments)

                except ClientError as e:
                    # Skip permission sets that don't have assignments for this account
                    if e.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                        console.print(
                            f"[yellow]Warning: Could not get assignments for account {account_name} ({account_id}): {e}[/yellow]"
                        )
                    continue

    except ClientError as e:
        console.print(f"[red]Error getting all account assignments: {e}[/red]")
        raise

    console.print(
        f"[green]Collected {len(assignments)} assignments across {total_accounts if 'total_accounts' in locals() else 'N/A'} accounts[/green]"
    )
    return assignments


def _get_principal_assignments_for_account(
    sso_admin_client, instance_arn: str, principal_id: str, principal_type: str, account_id: str
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific principal in a specific account."""
    assignments = []

    try:
        # Get all permission sets first
        ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
        permission_sets = []

        for page in ps_paginator.paginate(InstanceArn=instance_arn):
            permission_sets.extend(page.get("PermissionSets", []))

        # For each permission set, check if this principal has assignments in the account
        for permission_set_arn in permission_sets:
            try:
                response = sso_admin_client.list_account_assignments(
                    InstanceArn=instance_arn,
                    AccountId=account_id,
                    PermissionSetArn=permission_set_arn,
                )
                for assignment in response.get("AccountAssignments", []):
                    if (
                        assignment["PrincipalId"] == principal_id
                        and assignment["PrincipalType"] == principal_type
                    ):
                        assignments.append(assignment)
            except Exception:
                # Skip permission sets that cause errors
                continue

    except Exception as e:
        console.print(
            f"[yellow]Warning: Could not get assignments for principal in account {account_id}: {str(e)}[/yellow]"
        )

    return assignments


def _get_principal_assignments(
    sso_admin_client,
    instance_arn: str,
    principal_id: str,
    principal_type: str,
    client_manager: AWSClientManager,
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific principal across all accounts."""
    assignments = []

    # Get all accounts first
    try:
        # Use the passed client manager to get organizations client with proper credentials
        raw_org_client = client_manager.get_raw_organizations_client()
        paginator = raw_org_client.get_paginator("list_accounts")
        all_accounts = []
        for page in paginator.paginate():
            all_accounts.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts
        accounts = [acc for acc in all_accounts if acc.get("Status") == "ACTIVE"]

    except Exception as e:
        # If Organizations access fails, we can't enumerate all accounts
        console.print(
            f"[yellow]Warning: Unable to access AWS Organizations. Cannot enumerate all accounts. Error: {str(e)}[/yellow]"
        )
        return assignments

    # Check assignments for each account
    for account in accounts:
        account_id = account["Id"]
        try:
            # Get all permission sets first
            ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
            permission_sets = []

            for page in ps_paginator.paginate(InstanceArn=instance_arn):
                permission_sets.extend(page.get("PermissionSets", []))

            # For each permission set, check if this principal has assignments in the account
            for permission_set_arn in permission_sets:
                try:
                    response = sso_admin_client.list_account_assignments(
                        InstanceArn=instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=permission_set_arn,
                    )
                    for assignment in response.get("AccountAssignments", []):
                        if (
                            assignment["PrincipalId"] == principal_id
                            and assignment["PrincipalType"] == principal_type
                        ):
                            assignments.append(assignment)
                except Exception:
                    # Skip permission sets that cause errors
                    continue
        except Exception:
            # Skip accounts we can't access
            continue

    return assignments


def _get_permission_set_assignments_for_account(
    sso_admin_client, instance_arn: str, permission_set_arn: str, account_id: str
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific permission set in a specific account."""
    assignments = []

    try:
        response = sso_admin_client.list_account_assignments(
            InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=permission_set_arn
        )
        assignments.extend(response.get("AccountAssignments", []))
    except Exception as e:
        console.print(
            f"[yellow]Warning: Could not get assignments for permission set in account {account_id}: {str(e)}[/yellow]"
        )

    return assignments


def _get_permission_set_assignments(
    sso_admin_client, instance_arn: str, permission_set_arn: str, client_manager: AWSClientManager
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific permission set across all accounts."""
    assignments = []

    # Get all accounts first
    try:
        # Use the passed client manager to get organizations client with proper credentials
        raw_org_client = client_manager.get_raw_organizations_client()
        paginator = raw_org_client.get_paginator("list_accounts")
        all_accounts = []
        for page in paginator.paginate():
            all_accounts.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts
        accounts = [acc for acc in all_accounts if acc.get("Status") == "ACTIVE"]
    except Exception as e:
        # If Organizations access fails, we can't enumerate all accounts
        console.print(
            f"[yellow]Warning: Unable to access AWS Organizations. Cannot enumerate all accounts. Error: {str(e)}[/yellow]"
        )
        return assignments

    # Check assignments for each account
    for account in accounts:
        account_id = account["Id"]
        try:
            response = sso_admin_client.list_account_assignments(
                InstanceArn=instance_arn,
                AccountId=account_id,
                PermissionSetArn=permission_set_arn,
            )
            assignments.extend(response.get("AccountAssignments", []))
        except Exception:
            # Skip accounts we can't access
            continue

    return assignments


def _resolve_principal(
    identitystore_client, identity_store_id: str, principal_name: str, principal_type: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Resolve principal name to ID and determine type."""
    # Try to find as user first
    if not principal_type or principal_type == "USER":
        try:
            response = identitystore_client.list_users(
                IdentityStoreId=identity_store_id,
                Filters=[{"AttributePath": "UserName", "AttributeValue": principal_name}],
            )
            if response.get("Users"):
                return response["Users"][0]["UserId"], "USER"
        except Exception:
            pass

    # Try to find as group
    if not principal_type or principal_type == "GROUP":
        try:
            response = identitystore_client.list_groups(
                IdentityStoreId=identity_store_id,
                Filters=[{"AttributePath": "DisplayName", "AttributeValue": principal_name}],
            )
            if response.get("Groups"):
                return response["Groups"][0]["GroupId"], "GROUP"
        except Exception:
            pass

    return None, None


def _resolve_permission_set(
    sso_admin_client, instance_arn: str, permission_set_name: str
) -> Optional[str]:
    """Resolve permission set name to ARN."""
    try:
        paginator = sso_admin_client.get_paginator("list_permission_sets")
        for page in paginator.paginate(InstanceArn=instance_arn):
            for ps_arn in page.get("PermissionSets", []):
                response = sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=ps_arn
                )
                if response["PermissionSet"]["Name"] == permission_set_name:
                    return ps_arn
    except Exception:
        pass

    return None


def _get_user_group_memberships(
    identitystore_client, identity_store_id: str, user_id: str
) -> List[Dict[str, Any]]:
    """Get all groups that a user is a member of."""
    groups = []

    try:
        # List all groups and check if the user is a member of each
        paginator = identitystore_client.get_paginator("list_groups")
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            for group in page.get("Groups", []):
                group_id = group["GroupId"]

                # Check if user is a member of this group
                try:
                    memberships_response = identitystore_client.list_group_memberships(
                        IdentityStoreId=identity_store_id, GroupId=group_id
                    )

                    for membership in memberships_response.get("GroupMemberships", []):
                        member_id = membership.get("MemberId", {})
                        if member_id.get("UserId") == user_id:
                            groups.append(
                                {
                                    "GroupId": group_id,
                                    "DisplayName": group.get("DisplayName", ""),
                                    "Description": group.get("Description", ""),
                                }
                            )
                            break
                except Exception:
                    # Skip groups we can't access
                    continue
    except Exception:
        # If we can't list groups, return empty list
        pass

    return groups


def _get_user_inherited_assignments(
    sso_admin_client,
    identitystore_client,
    instance_arn: str,
    identity_store_id: str,
    user_id: str,
    account_id: Optional[str],
    client_manager: AWSClientManager,
) -> List[Dict[str, Any]]:
    """Get all assignments inherited from group memberships."""
    inherited_assignments = []

    # Get all groups the user is a member of
    user_groups = _get_user_group_memberships(identitystore_client, identity_store_id, user_id)

    for group in user_groups:
        group_id = group["GroupId"]
        group_name = group["DisplayName"]

        # Get assignments for this group
        if account_id:
            group_assignments = _get_principal_assignments_for_account(
                sso_admin_client, instance_arn, group_id, "GROUP", account_id
            )
        else:
            console.print(
                f"[blue]Searching GROUP {group_name} across the entire organization...[/blue]"
            )
            group_assignments = _get_principal_assignments(
                sso_admin_client, instance_arn, group_id, "GROUP", client_manager
            )

        # Mark these assignments as inherited
        for assignment in group_assignments:
            inherited_assignment = assignment.copy()
            inherited_assignment["inheritance_source"] = "GROUP"
            inherited_assignment["inheritance_group_id"] = group_id
            inherited_assignment["inheritance_group_name"] = group_name
            inherited_assignments.append(inherited_assignment)

    return inherited_assignments


def _resolve_account_names(
    assignments: List[Dict[str, Any]], client_manager: AWSClientManager
) -> List[Dict[str, Any]]:
    """Resolve account names for assignments using AWS Organizations."""
    try:
        # Get organizations client to resolve account names
        org_client = client_manager.get_raw_organizations_client()

        # Create a mapping of account IDs to names
        account_name_map = {}

        # Get all accounts from organizations
        paginator = org_client.get_paginator("list_accounts")
        for page in paginator.paginate():
            for account in page.get("Accounts", []):
                account_name_map[account["Id"]] = account["Name"]

        # Update assignments with account names
        for assignment in assignments:
            account_id = assignment.get("AccountId")
            if account_id and account_id in account_name_map:
                assignment["account_name"] = account_name_map[account_id]
            else:
                assignment["account_name"] = account_id  # Fallback to account ID

        return assignments
    except Exception:
        # If we can't resolve account names, leave them as account IDs
        for assignment in assignments:
            assignment["account_name"] = assignment.get("AccountId")
        return assignments


def _enrich_assignment(
    sso_admin_client,
    identitystore_client,
    instance_arn: str,
    identity_store_id: str,
    assignment: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Enrich assignment with additional details."""
    global _last_permission_set_call

    try:
        enriched = assignment.copy()

        # Rate limiting for permission set describe operations
        current_time = time.time()
        time_since_last_call = current_time - _last_permission_set_call
        if time_since_last_call < _permission_set_call_delay:
            time.sleep(_permission_set_call_delay - time_since_last_call)

        # Get permission set details
        ps_response = sso_admin_client.describe_permission_set(
            InstanceArn=instance_arn, PermissionSetArn=assignment["PermissionSetArn"]
        )
        _last_permission_set_call = time.time()
        enriched["permission_set_name"] = ps_response["PermissionSet"]["Name"]
        enriched["permission_set_description"] = ps_response["PermissionSet"].get("Description", "")

        # Get principal details
        enriched["principal_type"] = assignment["PrincipalType"]
        if assignment["PrincipalType"] == "USER":
            try:
                user_response = identitystore_client.describe_user(
                    IdentityStoreId=identity_store_id, UserId=assignment["PrincipalId"]
                )
                enriched["principal_name"] = user_response["UserName"]
                enriched["principal_display_name"] = user_response.get("DisplayName", "")
                enriched["principal_email"] = user_response.get("Emails", [{}])[0].get("Value", "")
            except Exception:
                enriched["principal_name"] = assignment["PrincipalId"]
        else:  # GROUP
            try:
                group_response = identitystore_client.describe_group(
                    IdentityStoreId=identity_store_id, GroupId=assignment["PrincipalId"]
                )
                enriched["principal_name"] = group_response["DisplayName"]
                enriched["principal_description"] = group_response.get("Description", "")
            except Exception:
                enriched["principal_name"] = assignment["PrincipalId"]

        # Add status (assume ACTIVE for now, could be enhanced with provisioning status)
        enriched["status"] = "ACTIVE"
        enriched["export_timestamp"] = datetime.now(timezone.utc).isoformat()

        # Preserve inheritance information if present
        if "inheritance_source" in assignment:
            enriched["inheritance_source"] = assignment["inheritance_source"]
        if "inheritance_group_id" in assignment:
            enriched["inheritance_group_id"] = assignment["inheritance_group_id"]
        if "inheritance_group_name" in assignment:
            enriched["inheritance_group_name"] = assignment["inheritance_group_name"]

        return enriched

    except Exception:
        return None


def _output_json(data: Dict[str, Any], output_file: Optional[str]):
    """Output data as JSON."""
    json_str = json.dumps(data, indent=2, default=str)

    if output_file:
        Path(output_file).write_text(json_str)
        console.print(f"[green]JSON output written to: {output_file}[/green]")
    else:
        console.print(json_str)


def _output_csv(
    assignments: List[Dict[str, Any]], output_file: Optional[str], default_filename: str
):
    """Output assignments as CSV."""
    if not assignments:
        console.print("[yellow]No assignments to export[/yellow]")
        return

    # Check if we have inheritance information
    has_inheritance = any("inheritance_source" in assignment for assignment in assignments)

    # Define CSV columns
    columns = [
        "account_id",
        "account_name",
        "principal_id",
        "principal_name",
        "principal_type",
        "permission_set_arn",
        "permission_set_name",
        "permission_set_description",
        "status",
        "export_timestamp",
    ]

    # Add inheritance columns if needed
    if has_inheritance:
        columns.extend(
            [
                "inheritance_source",
                "inheritance_group_id",
                "inheritance_group_name",
            ]
        )

    # Prepare CSV data
    csv_data = []
    for assignment in assignments:
        row = {
            "account_id": assignment.get("AccountId", ""),
            "account_name": assignment.get("account_name", "") or assignment.get("AccountName", ""),
            "principal_id": assignment.get("PrincipalId", ""),
            "principal_name": assignment.get("principal_name", ""),
            "principal_type": assignment.get("PrincipalType", ""),
            "permission_set_arn": assignment.get("PermissionSetArn", ""),
            "permission_set_name": assignment.get("permission_set_name", ""),
            "permission_set_description": assignment.get("permission_set_description", ""),
            "status": assignment.get("status", ""),
            "export_timestamp": assignment.get("export_timestamp", ""),
        }

        # Add inheritance information if present
        if has_inheritance:
            row["inheritance_source"] = assignment.get("inheritance_source", "DIRECT")
            row["inheritance_group_id"] = assignment.get("inheritance_group_id", "")
            row["inheritance_group_name"] = assignment.get("inheritance_group_name", "")

        csv_data.append(row)

    # Write CSV
    filename = output_file or f"{default_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filename, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        writer.writerows(csv_data)

    console.print(f"[green]CSV output written to: {filename}[/green]")


def _output_table(assignments: List[Dict[str, Any]], title: str):
    """Output assignments as formatted table."""
    if not assignments:
        console.print("[yellow]No assignments found[/yellow]")
        return

    # Check if we have inheritance information
    has_inheritance = any("inheritance_source" in assignment for assignment in assignments)

    # Create Rich table
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Account", style="cyan")
    table.add_column("Principal", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Permission Set", style="blue")
    if has_inheritance:
        table.add_column("Source", style="magenta")
    table.add_column("Status", style="red")

    for assignment in assignments:
        account_display = f"{assignment.get('AccountName', assignment.get('account_name', assignment['AccountId']))} ({assignment['AccountId']})"
        principal_display = assignment.get("principal_name", assignment["PrincipalId"])
        permission_set_display = assignment.get(
            "permission_set_name", assignment["PermissionSetArn"].split("/")[-1]
        )
        status_display = assignment.get("status", "UNKNOWN")

        # Determine inheritance source display
        inheritance_display = ""
        if has_inheritance:
            inheritance_source = assignment.get("inheritance_source", "DIRECT")
            if inheritance_source == "DIRECT":
                inheritance_display = "Direct"
            elif inheritance_source == "GROUP":
                group_name = assignment.get("inheritance_group_name", "Unknown Group")
                inheritance_display = f"Group: {group_name}"
            else:
                inheritance_display = inheritance_source

        row_data = [
            account_display,
            principal_display,
            assignment["PrincipalType"],
            permission_set_display,
        ]

        if has_inheritance:
            row_data.append(inheritance_display)

        row_data.append(status_display)

        table.add_row(*row_data)

    console.print(table)


def _get_consolidated_principal_assignments(
    sso_admin_client,
    identitystore_client,
    instance_arn: str,
    identity_store_id: str,
    principal_id: str,
    principal_type: str,
    client_manager: AWSClientManager,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Get both direct and inherited assignments for a principal in a single efficient pass.

    Returns:
        Tuple of (direct_assignments, inherited_assignments)
    """
    direct_assignments = []
    inherited_assignments = []

    try:
        # Get all accounts once (this will be cached)
        org_client = client_manager.get_organizations_client()
        paginator = org_client.client.get_paginator("list_accounts")
        all_accounts_raw = []
        for page in paginator.paginate():
            all_accounts_raw.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts
        accounts = [acc for acc in all_accounts_raw if acc.get("Status") == "ACTIVE"]
        suspended_count = len(all_accounts_raw) - len(accounts)

        console.print(
            f"[blue]Found {len(all_accounts_raw)} total accounts, {suspended_count} suspended/closed (excluded), {len(accounts)} active accounts in organization[/blue]"
        )

        # Get all permission sets once (this will be cached)
        console.print(
            "[blue]Fetching permission sets (this will be cached for future runs)...[/blue]"
        )
        ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
        permission_sets = []
        for page in ps_paginator.paginate(InstanceArn=instance_arn):
            permission_sets.extend(page.get("PermissionSets", []))

        console.print(f"[blue]Found {len(permission_sets)} permission sets[/blue]")

        # If this is a user, get their group memberships for inherited permissions
        user_groups = {}
        if principal_type == "USER":
            try:
                group_memberships = identitystore_client.list_group_memberships_for_member(
                    IdentityStoreId=identity_store_id, MemberId={"UserId": principal_id}
                )

                if group_memberships.get("GroupMemberships"):
                    # Get group details for better display
                    for gm in group_memberships["GroupMemberships"]:
                        group_id = gm["GroupId"]
                        try:
                            group_response = identitystore_client.describe_group(
                                IdentityStoreId=identity_store_id, GroupId=group_id
                            )
                            user_groups[group_id] = group_response.get("DisplayName", group_id)
                        except Exception:
                            user_groups[group_id] = group_id

                    console.print(f"[blue]User is member of {len(user_groups)} groups[/blue]")
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get user group memberships: {str(e)}[/yellow]"
                )

        # Check assignments for each account
        for i, account in enumerate(accounts, 1):
            account_id = account["Id"]
            account_name = account.get("Name", "Unknown")

            console.print(
                f"[blue]Checking account {i}/{len(accounts)}: {account_name} ({account_id})[/blue]"
            )

            try:
                # For each permission set, check assignments for both the principal and their groups
                for permission_set_arn in permission_sets:
                    try:
                        response = sso_admin_client.list_account_assignments(
                            InstanceArn=instance_arn,
                            AccountId=account_id,
                            PermissionSetArn=permission_set_arn,
                        )

                        for assignment in response.get("AccountAssignments", []):
                            # Check for direct assignments
                            if (
                                assignment["PrincipalId"] == principal_id
                                and assignment["PrincipalType"] == principal_type
                            ):
                                assignment_copy = assignment.copy()
                                assignment_copy["AccountId"] = account_id
                                assignment_copy["AccountName"] = account_name
                                direct_assignments.append(assignment_copy)

                            # Check for inherited assignments from groups (only for users)
                            elif (
                                principal_type == "USER"
                                and assignment["PrincipalType"] == "GROUP"
                                and assignment["PrincipalId"] in user_groups
                            ):
                                assignment_copy = assignment.copy()
                                assignment_copy["AccountId"] = account_id
                                assignment_copy["AccountName"] = account_name
                                assignment_copy["inheritance_source"] = "GROUP"
                                assignment_copy["inheritance_group_name"] = user_groups[
                                    assignment["PrincipalId"]
                                ]
                                assignment_copy["inheritance_group_id"] = assignment["PrincipalId"]
                                inherited_assignments.append(assignment_copy)

                    except Exception:
                        # Skip permission sets that cause errors
                        continue
            except Exception:
                # Skip accounts we can't access
                continue

    except Exception as e:
        console.print(f"[yellow]Warning: Error during consolidated search: {str(e)}[/yellow]")

    return direct_assignments, inherited_assignments


@app.command("summarize")
def summarize_access(
    scope: str = typer.Argument(
        ...,
        help="Scope for summarization: 'accounts:tag:Environment=Production', 'ou:development', 'ou:root', or 'accounts:111111111111,222222222222'",
    ),
    metric: str = typer.Option(
        "unique-users",
        "--metric",
        "-m",
        help="Metric to calculate (unique-users, unique-groups, unique-permission-sets)",
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    include_inactive: bool = typer.Option(
        False, "--include-inactive", help="Include inactive assignments"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Summarize access patterns across accounts, OUs, or tags.

    Provides aggregated statistics about users, groups, and permission sets
    based on organizational scope or account filtering.

    Examples:
        # Summarize unique users in production accounts
        $ awsideman access-review summarize "accounts:tag:Environment=Production" --metric unique-users

        # Summarize access in development OU
        $ awsideman access-review summarize "ou:development" --metric unique-permission-sets

        # Summarize specific accounts
        $ awsideman access-review summarize "accounts:111111111111,222222222222" --metric unique-users

        # Export to CSV
        $ awsideman access-review summarize "ou:root" --metric unique-users --format csv --output summary.csv
    """
    try:
        # Validate profile and SSO instance
        profile_name, profile_data = validate_profile(profile)
        instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)

        # Initialize AWS clients
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region, enable_caching=True)
        sso_admin_client = client_manager.get_identity_center_client()
        identitystore_client = client_manager.get_identity_store_client()

        console.print(f"[green]Summarizing access for scope: {scope}[/green]")

        # Parse scope and get target accounts
        target_accounts = _parse_scope_and_get_accounts(scope, client_manager)

        if not target_accounts:
            console.print("[yellow]No accounts found matching the specified scope.[/yellow]")
            return

        console.print(f"[blue]Found {len(target_accounts)} accounts to analyze[/blue]")

        # Get all assignments for target accounts
        all_assignments = []
        for account in target_accounts:
            account_id = account["Id"]
            account_name = account["Name"]

            try:
                assignments = _get_account_assignments(sso_admin_client, instance_arn, account_id)

                # Enrich assignments with details
                for assignment in assignments:
                    enriched = _enrich_assignment(
                        sso_admin_client,
                        identitystore_client,
                        instance_arn,
                        identity_store_id,
                        assignment,
                    )
                    if enriched and (include_inactive or enriched.get("status") == "ACTIVE"):
                        enriched["AccountId"] = account_id
                        enriched["AccountName"] = account_name
                        all_assignments.append(enriched)

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not get assignments for account {account_name}: {e}[/yellow]"
                )
                continue

        # Calculate metrics
        summary_data = _calculate_summary_metrics(all_assignments, metric, scope)

        # Generate output
        if output_format == "json":
            output_data = {
                "scope": scope,
                "metric": metric,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_accounts": len(target_accounts),
                "total_assignments": len(all_assignments),
                "summary": summary_data,
            }

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(output_data, f, indent=2)
                console.print(f"[green]Summary exported to {output_file}[/green]")
            else:
                print(json.dumps(output_data, indent=2))

        elif output_format == "csv":
            if not summary_data:
                console.print("[yellow]No data to export.[/yellow]")
                return

            # Convert summary to CSV format
            csv_data = []
            for key, value in summary_data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        csv_data.append(
                            {
                                "category": key,
                                "subcategory": sub_key,
                                "count": sub_value,
                                "scope": scope,
                                "metric": metric,
                            }
                        )
                else:
                    csv_data.append(
                        {
                            "category": key,
                            "subcategory": "",
                            "count": value,
                            "scope": scope,
                            "metric": metric,
                        }
                    )

            fieldnames = ["category", "subcategory", "count", "scope", "metric"]

            if output_file:
                with open(output_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_data)
                console.print(f"[green]Summary exported to {output_file}[/green]")
            else:
                import sys

                writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_data)
        else:
            # Table format
            _output_summary_table(summary_data, scope, metric)

        console.print(
            f"[green]Summary completed for {len(target_accounts)} accounts with {len(all_assignments)} assignments[/green]"
        )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error generating summary: {str(e)}[/red]")
        raise typer.Exit(1)


def _parse_scope_and_get_accounts(
    scope: str, client_manager: AWSClientManager
) -> List[Dict[str, Any]]:
    """Parse scope string and return list of target accounts."""
    accounts = []

    try:
        if scope.startswith("tags:") or scope.startswith("tag:"):
            # Handle tag filtering: tags:env=dev or tag:env=dev
            if scope.startswith("tags:"):
                tag_filter = scope[5:]  # Remove "tags:" prefix
            else:
                tag_filter = scope[4:]  # Remove "tag:" prefix

            if "=" not in tag_filter:
                raise ValueError("Tag filter must be in format 'Key=Value'")

            key, value = tag_filter.split("=", 1)
            accounts = _get_accounts_by_tag(client_manager, key, value)
        elif scope.startswith("accounts:"):
            # Handle account list or tag filtering
            scope_value = scope[9:]  # Remove "accounts:" prefix

            if scope_value == "*":
                # All accounts
                accounts = _get_all_accounts(client_manager)
            elif scope_value.startswith("tag:"):
                # Tag-based filtering: accounts:tag:Environment=Production
                tag_filter = scope_value[4:]  # Remove "tag:" prefix
                if "=" not in tag_filter:
                    raise ValueError("Tag filter must be in format 'Key=Value'")

                key, value = tag_filter.split("=", 1)
                accounts = _get_accounts_by_tag(client_manager, key, value)
            else:
                # Comma-separated account IDs
                account_ids = [aid.strip() for aid in scope_value.split(",")]
                accounts = _get_accounts_by_ids(client_manager, account_ids)

        elif scope.startswith("ou:"):
            # OU-based filtering: ou:development, ou:root
            ou_name = scope[3:]  # Remove "ou:" prefix
            accounts = _get_accounts_by_ou(client_manager, ou_name)
        else:
            raise ValueError(f"Unsupported scope format: {scope}")

    except Exception as e:
        console.print(f"[red]Error parsing scope '{scope}': {e}[/red]")
        raise typer.Exit(1)

    return accounts


def _get_all_accounts(client_manager: AWSClientManager) -> List[Dict[str, Any]]:
    """Get all accounts in the organization."""
    try:
        org_client = client_manager.get_raw_organizations_client()
        paginator = org_client.get_paginator("list_accounts")
        all_accounts_raw = []

        for page in paginator.paginate():
            all_accounts_raw.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts
        all_accounts = [acc for acc in all_accounts_raw if acc.get("Status") == "ACTIVE"]
        suspended_count = len(all_accounts_raw) - len(all_accounts)

        console.print(
            f"[green]Found {len(all_accounts_raw)} total accounts, {suspended_count} suspended/closed (excluded), {len(all_accounts)} active accounts in the organization[/green]"
        )
        return all_accounts

    except Exception as e:
        console.print(f"[red]Error getting all accounts: {e}[/red]")
        return []


def _get_accounts_by_tag(
    client_manager: AWSClientManager, tag_key: str, tag_value: str
) -> List[Dict[str, Any]]:
    """Get accounts filtered by tag using manual tag checking."""
    try:
        # Use manual tag filtering to check account tags directly

        # Get all accounts and check their tags manually
        org_client = client_manager.get_raw_organizations_client()
        paginator = org_client.get_paginator("list_accounts")
        all_accounts_raw = []

        for page in paginator.paginate():
            all_accounts_raw.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts first
        all_accounts = [acc for acc in all_accounts_raw if acc.get("Status") == "ACTIVE"]
        suspended_count = len(all_accounts_raw) - len(all_accounts)

        filtered_accounts = []

        # Check tags for each active account
        for account in all_accounts:
            try:
                account_id = account.get("Id")
                if account_id:
                    # Get account tags
                    tags_response = org_client.list_tags_for_resource(ResourceId=account_id)
                    account_tags = {
                        tag["Key"]: tag["Value"] for tag in tags_response.get("Tags", [])
                    }

                    # Check if account has the specified tag
                    if account_tags.get(tag_key) == tag_value:
                        filtered_accounts.append(account)

            except Exception:
                # Skip accounts where we can't check tags
                continue

        console.print(
            f"[green]Found {len(filtered_accounts)} active accounts with tag {tag_key}={tag_value} (excluded {suspended_count} suspended/closed accounts)[/green]"
        )
        return filtered_accounts

    except Exception as e:
        console.print(f"[red]Error getting accounts by tag: {e}[/red]")
        return []


def _get_accounts_by_ids(
    client_manager: AWSClientManager, account_ids: List[str]
) -> List[Dict[str, Any]]:
    """Get accounts by specific IDs."""
    try:
        org_client = client_manager.get_raw_organizations_client()
        paginator = org_client.get_paginator("list_accounts")
        all_accounts_raw = []

        for page in paginator.paginate():
            all_accounts_raw.extend(page.get("Accounts", []))

        # Filter out suspended/closed accounts first
        all_accounts = [acc for acc in all_accounts_raw if acc.get("Status") == "ACTIVE"]

        # Filter to requested account IDs
        filtered_accounts = []
        for account in all_accounts:
            if account["Id"] in account_ids:
                filtered_accounts.append(account)

        return filtered_accounts

    except Exception as e:
        console.print(f"[red]Error getting accounts by IDs: {e}[/red]")
        return []


def _get_accounts_by_ou(client_manager: AWSClientManager, ou_name: str) -> List[Dict[str, Any]]:
    """Get accounts by organizational unit."""
    try:
        org_client = client_manager.get_raw_organizations_client()

        # Get all OUs
        root_ou_id = None

        # Find root OU first
        try:
            root_response = org_client.describe_organization()
            root_ou_id = root_response["Organization"]["MasterAccountId"]
        except Exception:
            # Fallback: try to find root OU
            root_ou_id = "r-0000"  # This is a placeholder

        # Find the target OU
        target_ou_id = _find_ou_by_name(org_client, root_ou_id, ou_name)
        if not target_ou_id:
            console.print(f"[yellow]OU '{ou_name}' not found[/yellow]")
            return []

        # Get accounts in the OU
        accounts = []
        try:
            account_paginator = org_client.get_paginator("list_accounts_for_parent")
            for page in account_paginator.paginate(ParentId=target_ou_id):
                accounts.extend(page.get("Accounts", []))
        except Exception:
            # If direct OU listing fails, try recursive search
            accounts = _get_accounts_recursively(org_client, target_ou_id)

        return accounts

    except Exception as e:
        console.print(f"[red]Error getting accounts by OU: {e}[/red]")
        return []


def _find_ou_by_name(org_client, parent_ou_id: str, ou_name: str) -> Optional[str]:
    """Recursively find OU by name."""
    try:
        ou_paginator = org_client.get_paginator("list_organizational_units_for_parent")
        for page in ou_paginator.paginate(ParentId=parent_ou_id):
            for ou in page.get("OrganizationalUnits", []):
                if ou["Name"].lower() == ou_name.lower():
                    return ou["Id"]
                # Recursively search child OUs
                child_result = _find_ou_by_name(org_client, ou["Id"], ou_name)
                if child_result:
                    return child_result
    except Exception:
        pass
    return None


def _get_accounts_recursively(org_client, ou_id: str) -> List[Dict[str, Any]]:
    """Recursively get all accounts in an OU and its children."""
    accounts = []

    try:
        # Get direct accounts
        account_paginator = org_client.get_paginator("list_accounts_for_parent")
        for page in account_paginator.paginate(ParentId=ou_id):
            accounts.extend(page.get("Accounts", []))

        # Get child OUs and their accounts
        ou_paginator = org_client.get_paginator("list_organizational_units_for_parent")
        for page in ou_paginator.paginate(ParentId=ou_id):
            for ou in page.get("OrganizationalUnits", []):
                accounts.extend(_get_accounts_recursively(org_client, ou["Id"]))
    except Exception:
        pass

    return accounts


def _calculate_summary_metrics(
    assignments: List[Dict[str, Any]], metric: str, scope: str
) -> Dict[str, Any]:
    """Calculate summary metrics from assignments."""
    summary = {}

    if metric == "unique-users":
        # Count unique users
        users = set()
        for assignment in assignments:
            if assignment.get("principal_type") == "USER":
                users.add(assignment.get("principal_name", ""))

        summary["unique_users"] = len(users)
        summary["user_list"] = sorted(list(users))

    elif metric == "unique-groups":
        # Count unique groups
        groups = set()
        for assignment in assignments:
            if assignment.get("principal_type") == "GROUP":
                groups.add(assignment.get("principal_name", ""))

        summary["unique_groups"] = len(groups)
        summary["group_list"] = sorted(list(groups))

    elif metric == "unique-permission-sets":
        # Count unique permission sets
        permission_sets = set()
        for assignment in assignments:
            ps_name = assignment.get("permission_set_name", "")
            if ps_name:
                permission_sets.add(ps_name)

        summary["unique_permission_sets"] = len(permission_sets)
        summary["permission_set_list"] = sorted(list(permission_sets))

    else:
        # Default: comprehensive summary
        users = set()
        groups = set()
        permission_sets = set()
        accounts = set()

        for assignment in assignments:
            if assignment.get("principal_type") == "USER":
                users.add(assignment.get("principal_name", ""))
            elif assignment.get("principal_type") == "GROUP":
                groups.add(assignment.get("principal_name", ""))

            ps_name = assignment.get("permission_set_name", "")
            if ps_name:
                permission_sets.add(ps_name)

            account_name = assignment.get("AccountName", "")
            if account_name:
                accounts.add(account_name)

        summary = {
            "unique_users": len(users),
            "unique_groups": len(groups),
            "unique_permission_sets": len(permission_sets),
            "unique_accounts": len(accounts),
            "total_assignments": len(assignments),
        }

    return summary


def _output_summary_table(summary_data: Dict[str, Any], scope: str, metric: str) -> None:
    """Output summary data in table format."""
    from rich.table import Table

    table = Table(title=f"Access Summary - {scope}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    for key, value in summary_data.items():
        if isinstance(value, list):
            table.add_row(key, f"{len(value)} items")
        else:
            table.add_row(key, str(value))

    console.print(table)
