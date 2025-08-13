"""
Access Review Commands

Provides basic access review functionality for exporting permissions
for specified accounts or principals.
"""

import csv
import json
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


def validate_sso_instance(profile_data: dict) -> tuple[str, str]:
    """Validate the SSO instance configuration and return instance ARN and identity store ID."""
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    if not instance_arn or not identity_store_id:
        console.print("[red]Error: No SSO instance configured for this profile.[/red]")
        console.print(
            "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
        )
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)

    return instance_arn, identity_store_id


@app.command("export-account")
def export_account(
    account_id: str = typer.Argument(..., help="AWS account ID to review"),
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
    """Export all permissions for a specific account."""
    try:
        # Validate profile and SSO instance
        profile_name, profile_data = validate_profile(profile)
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize AWS clients
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region)
        sso_admin_client = client_manager.get_identity_center_client()
        identitystore_client = client_manager.get_identity_store_client()

        console.print(f"Exporting permissions for account: [bold]{account_id}[/bold]")

        # Get all assignments for the account
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
            output_data = {
                "account_id": account_id,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_assignments": len(enriched_assignments),
                "assignments": enriched_assignments,
            }
            _output_json(output_data, output_file)
        elif output_format == "csv":
            _output_csv(enriched_assignments, output_file, f"account_{account_id}_permissions")
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


@app.command("export-principal")
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
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize AWS clients
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region)
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
        else:
            # Try to get assignments across all accounts (requires Organizations access)
            assignments = _get_principal_assignments(
                sso_admin_client, instance_arn, principal_id, resolved_type, client_manager
            )

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
                "principal_name": principal_name,
                "principal_id": principal_id,
                "principal_type": resolved_type,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_assignments": len(enriched_assignments),
                "assignments": enriched_assignments,
            }
            _output_json(output_data, output_file)
        elif output_format == "csv":
            _output_csv(
                enriched_assignments, output_file, f"principal_{principal_name}_permissions"
            )
        else:
            _output_table(
                enriched_assignments, f"Permissions for {resolved_type}: {principal_name}"
            )

        console.print(f"[green]Found {len(enriched_assignments)} permission assignments[/green]")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error exporting principal permissions: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("export-permission-set")
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
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize AWS clients
        region = profile_data.get("region")
        client_manager = AWSClientManager(profile=profile_name, region=region)
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
        accounts = []
        for page in paginator.paginate():
            accounts.extend(page.get("Accounts", []))

        console.print(f"[blue]Searching across {len(accounts)} accounts in organization...[/blue]")
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
            paginator = sso_admin_client.get_paginator("list_account_assignments")
            for page in paginator.paginate(InstanceArn=instance_arn, AccountId=account_id):
                for assignment in page.get("AccountAssignments", []):
                    if (
                        assignment["PrincipalId"] == principal_id
                        and assignment["PrincipalType"] == principal_type
                    ):
                        assignments.append(assignment)
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
        accounts = []
        for page in paginator.paginate():
            accounts.extend(page.get("Accounts", []))
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
            paginator = sso_admin_client.get_paginator("list_account_assignments")
            for page in paginator.paginate(InstanceArn=instance_arn, AccountId=account_id):
                for assignment in page.get("AccountAssignments", []):
                    if assignment["PermissionSetArn"] == permission_set_arn:
                        assignments.append(assignment)
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


def _enrich_assignment(
    sso_admin_client,
    identitystore_client,
    instance_arn: str,
    identity_store_id: str,
    assignment: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Enrich assignment with additional details."""
    try:
        enriched = assignment.copy()

        # Get permission set details
        ps_response = sso_admin_client.describe_permission_set(
            InstanceArn=instance_arn, PermissionSetArn=assignment["PermissionSetArn"]
        )
        enriched["permission_set_name"] = ps_response["PermissionSet"]["Name"]
        enriched["permission_set_description"] = ps_response["PermissionSet"].get("Description", "")

        # Get principal details
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

        # Add account name if possible
        enriched["account_name"] = assignment["AccountId"]  # Default to account ID

        # Add status (assume ACTIVE for now, could be enhanced with provisioning status)
        enriched["status"] = "ACTIVE"
        enriched["export_timestamp"] = datetime.now(timezone.utc).isoformat()

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

    # Prepare CSV data
    csv_data = []
    for assignment in assignments:
        row = {
            "account_id": assignment.get("AccountId", ""),
            "account_name": assignment.get("account_name", ""),
            "principal_id": assignment.get("PrincipalId", ""),
            "principal_name": assignment.get("principal_name", ""),
            "principal_type": assignment.get("PrincipalType", ""),
            "permission_set_arn": assignment.get("PermissionSetArn", ""),
            "permission_set_name": assignment.get("permission_set_name", ""),
            "permission_set_description": assignment.get("permission_set_description", ""),
            "status": assignment.get("status", ""),
            "export_timestamp": assignment.get("export_timestamp", ""),
        }
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

    # Create Rich table
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Account", style="cyan")
    table.add_column("Principal", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Permission Set", style="blue")
    table.add_column("Status", style="red")

    for assignment in assignments:
        account_display = (
            f"{assignment.get('account_name', assignment['AccountId'])} ({assignment['AccountId']})"
        )
        principal_display = assignment.get("principal_name", assignment["PrincipalId"])
        permission_set_display = assignment.get(
            "permission_set_name", assignment["PermissionSetArn"].split("/")[-1]
        )
        status_display = assignment.get("status", "UNKNOWN")

        table.add_row(
            account_display,
            principal_display,
            assignment["PrincipalType"],
            permission_set_display,
            status_display,
        )

    console.print(table)
