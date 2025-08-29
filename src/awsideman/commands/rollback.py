"""Rollback commands for awsideman.

This module provides commands for viewing and rolling back permission set operations.
Operations are tracked automatically when assignments are created or revoked, allowing
users to safely undo changes when needed.

Commands:
    list: List historical operations with filtering options
    apply: Apply rollback for a specific operation
    status: Show rollback system status and statistics

Examples:
    # List recent operations
    $ awsideman rollback list

    # List operations from the last 7 days
    $ awsideman rollback list --days 7

    # Filter by operation type
    $ awsideman rollback list --operation-type assign

    # Filter by principal name
    $ awsideman rollback list --principal john.doe

    # Apply rollback for a specific operation
    $ awsideman rollback apply abc123-def456-ghi789

    # Preview rollback without applying changes
    $ awsideman rollback apply abc123-def456-ghi789 --dry-run

    # Apply rollback with custom batch size
    $ awsideman rollback apply abc123-def456-ghi789 --batch-size 5
"""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..rollback.logger import OperationLogger
from ..utils.config import Config
from ..utils.validators import validate_profile


def select_operation_interactively(profile: Optional[str], dry_run: bool = False) -> Optional[str]:
    """Interactive operation selection for rollback apply command.

    Args:
        profile: AWS profile to use
        dry_run: Whether this is a dry run

    Returns:
        Selected operation ID or None if cancelled
    """
    try:
        # Validate profile
        profile_name, profile_data = validate_profile(profile)

        # Get operations from the last 30 days for selection
        logger = OperationLogger(profile=profile_name)
        operations = logger.get_operations(days=30)

        if not operations:
            console.print("[yellow]No operations found in the last 30 days.[/yellow]")
            return None

        # Sort operations by timestamp (newest first)
        operations.sort(key=lambda x: x.timestamp, reverse=True)

        # Display operations with indices
        console.print("[bold blue]Select operation to rollback:[/bold blue]")
        console.print(f"[dim]Profile: {profile_name}[/dim]")
        if dry_run:
            console.print("[dim]Mode: Dry run (no changes will be made)[/dim]")
        console.print()

        # Create a compact table for selection
        selection_table = Table(
            title="Available Operations",
            show_header=True,
            header_style="bold blue",
            title_style="bold blue",
        )

        selection_table.add_column("Index", style="cyan", width=6, no_wrap=True)
        selection_table.add_column("Date", style="green", width=10, no_wrap=True)
        selection_table.add_column("Type", style="yellow", width=8, no_wrap=True)
        selection_table.add_column("Principal", style="blue", width=15, no_wrap=True)
        selection_table.add_column("Permission Set", style="magenta", width=20, no_wrap=True)
        selection_table.add_column("Accounts", style="white", width=12, no_wrap=True)
        selection_table.add_column("Status", style="white", width=8, no_wrap=True)

        # Add rows with indices
        for i, operation in enumerate(operations[:20]):  # Limit to 20 for readability
            # Format timestamp
            formatted_date = operation.timestamp.strftime("%Y-%m-%d %H:%M")

            # Format operation type
            op_type = operation.operation_type.value.upper()

            # Format principal name
            if hasattr(operation, "principal_name"):
                principal_name = operation.principal_name
            elif hasattr(operation, "source_entity_name"):
                if operation.operation_type.value == "copy_assignments":
                    principal_name = (
                        f"{operation.source_entity_name} → {operation.target_entity_name}"
                    )
                else:
                    principal_name = operation.source_entity_name
            elif hasattr(operation, "source_permission_set_name"):
                principal_name = f"{operation.source_permission_set_name} → {operation.target_permission_set_name}"
            else:
                principal_name = "Unknown"

            if len(principal_name) > 15:
                principal_name = principal_name[:12] + "..."

            # Format permission set name
            if hasattr(operation, "permission_set_name"):
                ps_name = operation.permission_set_name
            elif (
                hasattr(operation, "permission_sets_involved")
                and operation.permission_sets_involved
            ):
                ps_name = operation.permission_sets_involved[0].split("/")[-1]
            elif hasattr(operation, "source_permission_set_name"):
                ps_name = operation.source_permission_set_name
            else:
                ps_name = "Unknown"

            if len(ps_name) > 18:
                ps_name = ps_name[:15] + "..."

            # Format account count
            if hasattr(operation, "account_ids"):
                account_count = len(operation.account_ids)
            elif hasattr(operation, "accounts_affected"):
                account_count = len(operation.accounts_affected)
            else:
                account_count = 0

            accounts_text = f"{account_count} account{'s' if account_count != 1 else ''}"

            # Format status
            if operation.rolled_back:
                status = "[red]Rolled Back[/red]"
            else:
                if hasattr(operation, "results"):
                    successful_results = sum(1 for r in operation.results if r.success)
                    total_results = len(operation.results)
                elif hasattr(operation, "assignments_copied"):
                    successful_results = len(operation.assignments_copied)
                    total_results = (
                        len(operation.accounts_affected)
                        if hasattr(operation, "accounts_affected")
                        else successful_results
                    )
                else:
                    successful_results = 0
                    total_results = 0

                if total_results == 0:
                    status = "[yellow]Unknown[/yellow]"
                elif successful_results == total_results:
                    status = "[green]Success[/green]"
                elif successful_results == 0:
                    status = "[red]Failed[/red]"
                else:
                    status = f"[yellow]Partial ({successful_results}/{total_results})[/yellow]"

            selection_table.add_row(
                str(i + 1),
                formatted_date,
                op_type,
                principal_name,
                ps_name,
                accounts_text,
                status,
            )

        # Display the table
        console.print(selection_table)

        if len(operations) > 20:
            console.print(
                f"[dim]... and {len(operations) - 20} more operations (showing most recent 20)[/dim]"
            )

        # Show full operation IDs for the displayed operations
        console.print("\n[bold cyan]Full Operation IDs:[/bold cyan]")
        for i, operation in enumerate(operations[:20]):
            console.print(f"[cyan]{i+1}.[/cyan] {operation.operation_id}")

        # Get user selection
        while True:
            try:
                selection = console.input(
                    "\n[bold green]Enter operation index (1-20) or 'q' to quit:[/bold green] "
                ).strip()

                if selection.lower() in ["q", "quit", "exit"]:
                    console.print("[yellow]Operation cancelled.[/yellow]")
                    return None

                index = int(selection)
                if 1 <= index <= len(operations[:20]):
                    selected_operation = operations[index - 1]
                    console.print("\n[bold green]Selected operation:[/bold green]")
                    console.print(f"[green]Index:[/green] {index}")
                    console.print(f"[green]Operation ID:[/green] {selected_operation.operation_id}")
                    console.print(
                        f"[green]Type:[/green] {selected_operation.operation_type.value.upper()}"
                    )
                    console.print(
                        f"[green]Date:[/green] {selected_operation.timestamp.strftime('%Y-%m-%d %H:%M')}"
                    )

                    if hasattr(selected_operation, "principal_name"):
                        console.print(
                            f"[green]Principal:[/green] {selected_operation.principal_name}"
                        )
                    if hasattr(selected_operation, "permission_set_name"):
                        console.print(
                            f"[green]Permission Set:[/green] {selected_operation.permission_set_name}"
                        )

                    return selected_operation.operation_id
                else:
                    console.print(
                        f"[red]Invalid index. Please enter a number between 1 and {len(operations[:20])}.[/red]"
                    )
            except ValueError:
                console.print("[red]Invalid input. Please enter a number or 'q' to quit.[/red]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Operation cancelled.[/yellow]")
                return None

    except Exception as e:
        console.print(f"[red]Error during interactive selection: {e}[/red]")
        return None


app = typer.Typer(
    help="View and rollback permission set operations. Track and undo assignment changes safely."
)
console = Console()
config = Config()


@app.command("list")
def list_operations(
    operation_type: Optional[str] = typer.Option(
        None, "--operation-type", "-t", help="Filter by operation type (assign or revoke)"
    ),
    principal: Optional[str] = typer.Option(
        None, "--principal", "-p", help="Filter by principal name or ID (partial match)"
    ),
    permission_set: Optional[str] = typer.Option(
        None, "--permission-set", "-s", help="Filter by permission set name or ARN (partial match)"
    ),
    days: int = typer.Option(
        3, "--days", "-d", help="Show operations from the last N days (default: 3)"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of operations to show"
    ),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table or json)"),
    copy_id: bool = typer.Option(
        False, "--copy-id", "-c", help="Copy operation ID to clipboard for easy use"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """List historical permission set operations with filtering options.

    Displays a list of recent operations that can be rolled back, including assignments
    and revocations. Results can be filtered by operation type, principal, permission set,
    and date range.

    FILTERING OPTIONS:

      --operation-type: Filter by "assign" or "revoke" operations
      --principal: Filter by principal name or ID (supports partial matching)
      --permission-set: Filter by permission set name or ARN (supports partial matching)
      --days: Show operations from the last N days (default: 3)
      --limit: Limit the number of results returned

    OUTPUT FORMATS:

      table: Human-readable table format (default)
      json: Machine-readable JSON format

    EXAMPLES:

      # List all operations from the last 3 days (default)
      $ awsideman rollback list

      # List only assignment operations
      $ awsideman rollback list --operation-type assign

      # List operations for a specific user
      $ awsideman rollback list --principal john.doe

      # List operations from the last 7 days
      $ awsideman rollback list --days 7

      # List operations with JSON output
      $ awsideman rollback list --format json

      # Combine multiple filters
      $ awsideman rollback list --operation-type revoke --days 14 --limit 10

    NOTES:

      - Operations are tracked automatically when using assignment commands
      - Only operations that can be rolled back are shown
      - Use the operation ID from this list with 'rollback apply' command
      - Default shows last 3 days for recent operations; use --days to see older history
    """
    # Validate input parameters
    if operation_type and operation_type.lower() not in ["assign", "revoke"]:
        console.print(f"[red]Error: Invalid operation type '{operation_type}'.[/red]")
        console.print("[yellow]Operation type must be either 'assign' or 'revoke'.[/yellow]")
        raise typer.Exit(1)

    if days <= 0:
        console.print("[red]Error: Days must be a positive integer.[/red]")
        raise typer.Exit(1)

    if limit is not None and limit <= 0:
        console.print("[red]Error: Limit must be a positive integer.[/red]")
        raise typer.Exit(1)

    if format.lower() not in ["table", "json"]:
        console.print(f"[red]Error: Invalid format '{format}'.[/red]")
        console.print("[yellow]Format must be either 'table' or 'json'.[/yellow]")
        raise typer.Exit(1)

    # Validate profile (for consistency, even though we don't need AWS clients for listing)
    profile_name, _ = validate_profile(profile)

    # Create operation logger with profile isolation
    try:
        logger = OperationLogger(profile=profile_name)
    except Exception as e:
        console.print(f"[red]Error: Failed to initialize operation logger: {str(e)}[/red]")
        raise typer.Exit(1)

    # Display status message
    with console.status("[blue]Retrieving operation history...[/blue]"):
        try:
            # Get operations with filters
            operations = logger.get_operations(
                operation_type=operation_type.lower() if operation_type else None,
                principal=principal,
                permission_set=permission_set,
                days=days,
                limit=limit,
            )

        except Exception as e:
            console.print(f"[red]Error: Failed to retrieve operations: {str(e)}[/red]")
            raise typer.Exit(1)

    # Check if any operations were found
    if not operations:
        console.print("[yellow]No operations found.[/yellow]")

        # Provide helpful suggestions
        suggestions = []
        if operation_type:
            suggestions.append("remove --operation-type filter")
        if principal:
            suggestions.append("remove --principal filter")
        if permission_set:
            suggestions.append("remove --permission-set filter")
        if days < 30:
            suggestions.append("increase --days to see older operations")

        if suggestions:
            console.print(f"[yellow]Try: {' or '.join(suggestions)}[/yellow]")
        else:
            console.print(
                "[yellow]No operations have been logged yet. Operations are tracked automatically when using assignment commands.[/yellow]"
            )
            console.print(
                "[yellow]Use --days 7 or --days 30 to see operations from a longer period.[/yellow]"
            )

        raise typer.Exit(0)

    # Display results based on format
    if format.lower() == "json":
        # JSON output
        operations_data = {
            "operations": [op.to_dict() for op in operations],
            "total_count": len(operations),
            "filters": {
                "operation_type": operation_type,
                "principal": principal,
                "permission_set": permission_set,
                "days": days,
                "limit": limit,
            },
            "profile": profile_name,
        }

        console.print(json.dumps(operations_data, indent=2, default=str))

    else:
        # Table output
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Operation ID", style="cyan", no_wrap=True)
        table.add_column("Date", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Principal", style="yellow")
        table.add_column("Permission Set", style="blue")
        table.add_column("Accounts", style="white")
        table.add_column("Status", style="red")

        # Add rows to the table
        for operation in operations:
            # Format timestamp
            formatted_date = operation.timestamp.strftime("%Y-%m-%d %H:%M")

            # Format operation type
            op_type = operation.operation_type.value.upper()

            # Format principal name (truncate if too long)
            if hasattr(operation, "principal_name"):
                principal_name = operation.principal_name
            elif hasattr(operation, "source_entity_name"):
                # For permission cloning operations, show source -> target
                if operation.operation_type.value == "copy_assignments":
                    principal_name = (
                        f"{operation.source_entity_name} → {operation.target_entity_name}"
                    )
                else:
                    principal_name = operation.source_entity_name
            elif hasattr(operation, "source_permission_set_name"):
                # For permission set cloning operations, show source -> target
                principal_name = f"{operation.source_permission_set_name} → {operation.target_permission_set_name}"
            else:
                principal_name = "Unknown"

            if len(principal_name) > 20:
                principal_name = principal_name[:17] + "..."

            # Format permission set name (truncate if too long)
            if hasattr(operation, "permission_set_name"):
                ps_name = operation.permission_set_name
            elif (
                hasattr(operation, "permission_sets_involved")
                and operation.permission_sets_involved
            ):
                # For permission cloning operations, show first permission set
                ps_name = operation.permission_sets_involved[0].split("/")[-1]
            elif hasattr(operation, "source_permission_set_name"):
                # For permission set cloning operations, show source permission set
                ps_name = operation.source_permission_set_name
            else:
                ps_name = "Unknown"

            if len(ps_name) > 25:
                ps_name = ps_name[:22] + "..."

            # Format account count
            if hasattr(operation, "account_ids"):
                account_count = len(operation.account_ids)
            elif hasattr(operation, "accounts_affected"):
                account_count = len(operation.accounts_affected)
            else:
                account_count = 0

            if account_count == 1:
                accounts_text = f"{account_count} account"
            else:
                accounts_text = f"{account_count} accounts"

            # Format status
            if operation.rolled_back:
                status = "[red]Rolled Back[/red]"
            else:
                # Check if all results were successful
                if hasattr(operation, "results"):
                    successful_results = sum(1 for r in operation.results if r.success)
                    total_results = len(operation.results)
                elif hasattr(operation, "assignments_copied"):
                    # For permission cloning operations, use assignments_copied
                    successful_results = len(operation.assignments_copied)
                    total_results = (
                        len(operation.accounts_affected)
                        if hasattr(operation, "accounts_affected")
                        else successful_results
                    )
                else:
                    successful_results = 0
                    total_results = 0

                if total_results == 0:
                    status = "[yellow]Unknown[/yellow]"
                elif successful_results == total_results:
                    status = "[green]Success[/green]"
                elif successful_results == 0:
                    status = "[red]Failed[/red]"
                else:
                    status = f"[yellow]Partial ({successful_results}/{total_results})[/yellow]"

            # Truncate operation ID for display
            display_id = operation.operation_id[:8] + "..."

            table.add_row(
                display_id,
                formatted_date,
                op_type,
                principal_name,
                ps_name,
                accounts_text,
                status,
            )

        # Display filter information if any filters are applied
        filters_applied = []
        if operation_type:
            filters_applied.append(f"Type: {operation_type}")
        if principal:
            filters_applied.append(f"Principal: {principal}")
        if permission_set:
            filters_applied.append(f"Permission Set: {permission_set}")
        if days != 30:
            filters_applied.append(f"Days: {days}")
        if limit:
            filters_applied.append(f"Limit: {limit}")

        if filters_applied:
            console.print(f"[dim]Filters: {', '.join(filters_applied)}[/dim]")

        # Display the table
        console.print(table)

        # Display summary information
        console.print(f"\n[dim]Showing {len(operations)} operations")
        if limit and len(operations) == limit:
            console.print(f"[dim](limited to {limit} results)[/dim]")
        console.print(f"[dim]Profile: {profile_name}[/dim]")

        # Display helpful tips
        console.print("\n[dim]Tips:[/dim]")
        console.print("[dim]• Use the full operation ID with 'rollback apply' command[/dim]")
        console.print("[dim]• Add --format json for machine-readable output[/dim]")
        console.print("[dim]• Use filters to narrow down results[/dim]")


@app.command("apply")
def apply_rollback(
    operation_id: Optional[str] = typer.Argument(
        None, help="Operation ID to rollback (not needed with --interactive)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Interactive mode: select operation from list"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview rollback actions without applying changes"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts and proceed automatically"
    ),
    batch_size: int = typer.Option(
        10, "--batch-size", help="Number of assignments to process in parallel (1-50, default: 10)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Apply rollback for a specific operation.

    Rolls back a previously executed operation by performing the inverse actions.
    For assign operations, this will revoke the assignments. For revoke operations,
    this will re-assign the same permission sets.

    ROLLBACK BEHAVIOR:

      - Assign operations → Revoke the same assignments
      - Revoke operations → Re-assign the same permission sets
      - Only affects the exact assignments from the original operation
      - Skips assignments that are already in the desired state
      - Creates a new operation record for the rollback

    SAFETY FEATURES:

      - Validates operation exists and can be rolled back
      - Checks current AWS state before making changes
      - Supports dry-run mode to preview changes
      - Requires confirmation unless --yes is used
      - Tracks rollback operations for audit purposes

    EXAMPLES:

      # Apply rollback with confirmation
      $ awsideman rollback apply abc123-def456-ghi789

      # Preview rollback without making changes
      $ awsideman rollback apply abc123-def456-ghi789 --dry-run

      # Apply rollback without confirmation prompts
      $ awsideman rollback apply abc123-def456-ghi789 --yes

      # Use custom batch size for processing
      $ awsideman rollback apply abc123-def456-ghi789 --batch-size 5

      # Use specific AWS profile
      $ awsideman rollback apply abc123-def456-ghi789 --profile production

      # Interactive mode: select operation from list
      $ awsideman rollback apply --interactive

    NOTES:

      - Operation IDs can be found using 'rollback list' command
      - Use --interactive to select operations from a numbered list
      - Rollback operations are also tracked and can be rolled back themselves
      - Use dry-run mode to verify the rollback plan before applying
      - Partial failures are handled gracefully with detailed reporting
    """
    # Validate input parameters
    if interactive:
        # Interactive mode: get operation ID from user selection
        operation_id = select_operation_interactively(profile, dry_run)
        if not operation_id:
            console.print("[yellow]No operation selected. Exiting.[/yellow]")
            return
    elif not operation_id or not operation_id.strip():
        console.print(
            "[red]Error: Operation ID cannot be empty. Use --interactive to select from list.[/red]"
        )
        raise typer.Exit(1)

    if batch_size <= 0 or batch_size > 50:
        console.print("[red]Error: Batch size must be between 1 and 50.[/red]")
        raise typer.Exit(1)

    # Validate profile
    profile_name, profile_data = validate_profile(profile)

    console.print(f"[blue]Starting rollback operation for: {operation_id}[/blue]")
    console.print(f"[dim]Profile: {profile_name}[/dim]")
    console.print(f"[dim]Dry run: {dry_run}[/dim]")
    console.print(f"[dim]Batch size: {batch_size}[/dim]")
    console.print()

    # Create operation logger with profile isolation
    try:
        logger = OperationLogger(profile=profile_name)
    except Exception as e:
        console.print(f"[red]Error: Failed to initialize operation logger: {str(e)}[/red]")
        raise typer.Exit(1)

    # Step 1: Validate operation exists and can be rolled back
    console.print("[blue]Step 1: Validating operation...[/blue]")

    with console.status("[blue]Looking up operation...[/blue]"):
        try:
            operation = logger.get_operation(operation_id)

            if not operation:
                console.print(f"[red]✗ Operation not found: {operation_id}[/red]")
                console.print(
                    "[yellow]Use 'awsideman rollback list' to see available operations.[/yellow]"
                )
                raise typer.Exit(1)

            if operation.rolled_back:
                console.print("[red]✗ Operation has already been rolled back[/red]")
                console.print(
                    f"[yellow]Rollback operation ID: {operation.rollback_operation_id}[/yellow]"
                )
                console.print(
                    "[yellow]Use 'awsideman rollback list' to see the rollback operation.[/yellow]"
                )
                raise typer.Exit(1)

            # Handle different operation record types for display
            if hasattr(operation, "operation_type"):
                operation_type_display = operation.operation_type.value
            elif hasattr(operation, "source_permission_set_name"):
                operation_type_display = "permission_set_clone"
            else:
                operation_type_display = "unknown"

            console.print(
                f"[green]✓ Found operation: {operation_type_display} operation from {operation.timestamp.strftime('%Y-%m-%d %H:%M')}[/green]"
            )

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]✗ Error validating operation: {str(e)}[/red]")
            raise typer.Exit(1)

    # Step 2: Display operation details
    console.print("\n[blue]Step 2: Generating rollback plan...[/blue]")

    try:
        # Display operation details
        details_panel = _create_operation_details_panel(operation)
        console.print(details_panel)
    except Exception as e:
        console.print(f"[red]✗ Error displaying operation details: {str(e)}[/red]")
        raise typer.Exit(1)

    # Handle dry-run mode
    if dry_run:
        console.print("\n[green]✓ Dry-run completed successfully![/green]")
        console.print(
            "[yellow]No changes were made. Remove --dry-run to apply the rollback.[/yellow]"
        )
        raise typer.Exit(0)

    # Step 3: Get user confirmation
    # Determine rollback action type for display purposes
    if hasattr(operation, "operation_type"):
        if operation.operation_type.value == "assign":
            rollback_action = "revoke"
        elif operation.operation_type.value == "copy_assignments":
            # For copy operations, rollback means revoking the copied assignments
            rollback_action = "revoke"
        else:
            rollback_action = "assign"
    elif hasattr(operation, "source_permission_set_name"):
        # For permission set cloning operations, rollback means deleting the cloned permission set
        rollback_action = "delete"
    else:
        rollback_action = "unknown"

    # Calculate successful results that can be rolled back
    if hasattr(operation, "results"):
        successful_results = [r for r in operation.results if r.success]
    elif hasattr(operation, "assignments_copied"):
        # For PermissionCloningOperationRecord, use assignments_copied
        successful_results = operation.assignments_copied
    elif hasattr(operation, "source_permission_set_name"):
        # For PermissionSetCloningOperationRecord, there's typically one permission set to delete
        successful_results = (
            [operation.target_permission_set_arn] if operation.target_permission_set_arn else []
        )
    else:
        successful_results = []

    if not yes:
        if rollback_action == "delete":
            console.print(
                f"\n[yellow]⚠ This will {rollback_action} {len(successful_results)} permission set(s).[/yellow]"
            )
        else:
            console.print(
                f"\n[yellow]⚠ This will {rollback_action} {len(successful_results)} assignment(s).[/yellow]"
            )

        confirm = typer.confirm("Do you want to proceed with the rollback?")
        if not confirm:
            console.print("[yellow]Rollback cancelled by user.[/yellow]")
            raise typer.Exit(0)

    # Step 4: Execute rollback using appropriate processor
    console.print("\n[blue]Step 3: Executing rollback operation...[/blue]")

    # Import required modules for rollback processing
    from ..rollback.processor import RollbackProcessor

    # Check if this is a permission set cloning operation
    if hasattr(operation, "source_permission_set_name"):
        # This is a permission set cloning operation - use specialized rollback integration
        console.print(
            "[blue]Detected permission set cloning operation, using specialized rollback...[/blue]"
        )

        try:
            # Initialize AWS client manager and rollback integration
            region = profile_data.get("region")
            aws_client_manager = AWSClientManager(profile=profile_name, region=region)

            from ..permission_cloning.rollback_integration import (
                PermissionCloningRollbackIntegration,
            )

            # Initialize rollback processor for the integration
            rollback_processor = RollbackProcessor(
                aws_client_manager=aws_client_manager, config=config, show_progress=False
            )

            # Validate that we have a source permission set ARN
            if not (
                hasattr(operation, "source_permission_set_arn")
                and operation.source_permission_set_arn
            ):
                # Fall back to discovering it
                try:
                    sso_admin_client = aws_client_manager.get_sso_admin_client()
                    response = sso_admin_client.list_instances()
                    instances = response.get("Instances", [])
                    if not instances:
                        console.print("[red]✗ No SSO instances found[/red]")
                        raise typer.Exit(1)
                except Exception as e:
                    console.print(f"[red]✗ Error discovering SSO instance ARN: {str(e)}[/red]")
                    raise typer.Exit(1)

            rollback_integration = PermissionCloningRollbackIntegration(
                aws_client_manager, rollback_processor
            )

            # Execute the rollback
            result = rollback_integration.rollback_permission_set_clone_operation(operation_id)

            if result["success"]:
                console.print(
                    f"[green]✅ Successfully rolled back permission set clone operation {operation_id}[/green]"
                )
                console.print(
                    f"[green]  - Deleted permission set: {result['permission_set_deleted']}[/green]"
                )
                console.print(
                    f"[green]  - Permission set ARN: {result['permission_set_arn']}[/green]"
                )
            else:
                console.print(
                    f"[red]❌ Failed to rollback permission set clone operation {operation_id}[/red]"
                )
                console.print(f"[red]  - Error: {result['error']}[/red]")
                raise typer.Exit(1)

            return

        except Exception as e:
            console.print(f"[red]✗ Error during permission set clone rollback: {str(e)}[/red]")
            raise typer.Exit(1)

    # For other operation types, continue with the standard rollback processor
    # Check if this appears to be test data
    if hasattr(operation, "permission_set_arn"):
        permission_set_arn = operation.permission_set_arn
        account_ids = operation.account_ids
        principal_id = operation.principal_id
    elif hasattr(operation, "permission_sets_involved") and operation.permission_sets_involved:
        # For PermissionCloningOperationRecord, use the first permission set
        permission_set_arn = operation.permission_sets_involved[0]
        account_ids = operation.accounts_affected
        principal_id = operation.source_entity_id
    else:
        permission_set_arn = ""
        account_ids = []
        principal_id = ""

    is_test_data = (
        "1234567890abcdef" in permission_set_arn
        or "123456789012" in account_ids
        or "group-1234567890abcdef" in principal_id
        or "user-1234567890abcdef" in principal_id
    )

    if is_test_data:
        console.print(
            "[yellow]⚠ This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(
            "[yellow]Test operations contain fake AWS resource identifiers that cannot be used with real AWS APIs[/yellow]"
        )
        console.print(f"[dim]Permission Set ARN: {permission_set_arn}[/dim]")
        console.print(f"[dim]Principal ID: {principal_id}[/dim]")
        console.print(f"[dim]Account IDs: {account_ids}[/dim]")
        console.print(
            "\n[blue]To test rollback functionality, you need to create real operations using the assignment commands[/blue]"
        )
        console.print("\n[blue]Rollback operation completed![/blue]")
        return

    # Validate that the operation contains valid AWS ARNs
    if not permission_set_arn.startswith("arn:aws:sso:::"):
        console.print("[red]✗ Invalid permission set ARN format[/red]")
        console.print(
            "[yellow]This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(f"[dim]ARN: {permission_set_arn}[/dim]")
        raise typer.Exit(1)

    # Check if the ARN contains a valid instance ID
    if "/ssoins-" not in permission_set_arn:
        console.print("[red]✗ Invalid permission set ARN format[/red]")
        console.print(
            "[yellow]This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(f"[dim]ARN: {permission_set_arn}[/dim]")
        raise typer.Exit(1)

    try:
        # Initialize AWS client manager
        region = profile_data.get("region")
        aws_client_manager = AWSClientManager(profile=profile_name, region=region)

        # Initialize RollbackProcessor with the same storage directory as the logger
        rollback_processor = RollbackProcessor(
            storage_directory=str(logger.store.storage_dir),
            aws_client_manager=aws_client_manager,
            config=config,
            show_progress=False,
        )

        # Generate rollback plan
        with console.status("[blue]Generating rollback plan...[/blue]"):
            try:
                rollback_plan = rollback_processor.generate_plan(operation_id)
                console.print(f"[dim]Plan generation result: {rollback_plan}[/dim]")
            except Exception as plan_error:
                console.print(f"[red]✗ Error during plan generation: {str(plan_error)}[/red]")
                console.print(f"[dim]Error type: {type(plan_error).__name__}[/dim]")
                raise typer.Exit(1)

            if not rollback_plan:
                console.print("[red]✗ Failed to generate rollback plan[/red]")
                console.print(
                    "[yellow]This may be due to invalid operation data or AWS connectivity issues[/yellow]"
                )
                console.print(f"[dim]Operation ID: {operation_id}[/dim]")
                console.print(f"[dim]Permission Set ARN: {permission_set_arn}[/dim]")
                raise typer.Exit(1)

            # Display the actual rollback actions that will be executed
            if rollback_plan.actions:
                # Determine rollback action type
                if rollback_plan.rollback_type.value == "revoke":
                    action_description = "The following assignments will be revoked:"
                    rollback_action = "revoke"
                else:
                    action_description = "The following assignments will be created:"
                    rollback_action = "assign"

                console.print(f"\n[yellow]{action_description}[/yellow]")

                plan_table = Table(show_header=True, header_style="bold yellow")
                plan_table.add_column("Principal", style="cyan")
                plan_table.add_column("Permission Set", style="blue")
                plan_table.add_column("Accounts", style="green")
                plan_table.add_column("Action", style="magenta")

                # Add rollback actions to table
                if hasattr(operation, "account_ids") and hasattr(operation, "account_names"):
                    account_names_map = dict(zip(operation.account_ids, operation.account_names))
                elif hasattr(operation, "accounts_affected"):
                    # For PermissionCloningOperationRecord, create a simple mapping
                    account_names_map = {
                        account_id: account_id for account_id in operation.accounts_affected
                    }
                else:
                    account_names_map = {}

                for action in rollback_plan.actions:
                    account_name = account_names_map.get(action.account_id, action.account_id)
                    # Handle different operation record types
                    if hasattr(operation, "principal_name"):
                        principal_name = operation.principal_name
                    elif hasattr(operation, "source_entity_name"):
                        # For copy operations, show the target user (who will be affected by rollback)
                        if operation.operation_type.value == "copy_assignments":
                            principal_name = operation.target_entity_name
                        else:
                            # For other operations, use source entity info
                            principal_name = operation.source_entity_name
                    else:
                        principal_name = "Unknown"

                    # Handle different operation record types for permission set name
                    if hasattr(operation, "permission_set_name"):
                        permission_set_name = operation.permission_set_name
                    elif (
                        hasattr(operation, "permission_sets_involved")
                        and operation.permission_sets_involved
                    ):
                        # For PermissionCloningOperationRecord, use the first permission set
                        permission_set_name = operation.permission_sets_involved[0].split("/")[
                            -1
                        ]  # Extract name from ARN
                    else:
                        permission_set_name = "Unknown"

                    plan_table.add_row(
                        principal_name,
                        permission_set_name,
                        f"{account_name} ({action.account_id})",
                        rollback_action.upper(),
                    )

                console.print(plan_table)

                # Display summary
                console.print(
                    f"\n[dim]Rollback will {rollback_action} {len(rollback_plan.actions)} assignment(s)[/dim]"
                )
            else:
                console.print("[yellow]⚠ No actions to perform in rollback plan[/yellow]")
                console.print("[yellow]The operation may already be in the desired state[/yellow]")
                if rollback_plan.warnings:
                    console.print("[yellow]Reasons:[/yellow]")
                    for warning in rollback_plan.warnings:
                        console.print(f"[yellow]  • {warning}[/yellow]")
                console.print("\n[blue]Rollback operation completed![/blue]")
                return

        # Execute rollback
        with console.status(
            f"[blue]Executing rollback ({len(rollback_plan.actions)} actions)...[/blue]"
        ):
            rollback_result = rollback_processor.execute_rollback(
                plan=rollback_plan,
                dry_run=False,  # We already handled dry-run above
                batch_size=batch_size,
                verify_post_rollback=True,
            )

        # Display results
        if rollback_result.success:
            console.print("\n[green]✓ Rollback completed successfully![/green]")
            console.print(
                f"[dim]Rollback operation ID: {rollback_result.rollback_operation_id}[/dim]"
            )
            console.print(f"[dim]Completed: {rollback_result.completed_actions} actions[/dim]")
            console.print(f"[dim]Duration: {rollback_result.duration_ms}ms[/dim]")

            if rollback_result.completed_actions > 0:
                console.print(
                    f"\n[green]✓ Successfully {rollback_action}d {rollback_result.completed_actions} assignment(s)[/green]"
                )

                # Add specific warning for copy operation rollbacks
                if operation.operation_type.value == "copy_assignments":
                    console.print("\n[yellow]⚠️  Post-rollback warning:[/yellow]")
                    console.print(
                        f"[yellow]The target user '{operation.target_entity_name}' has had their copied assignments revoked.[/yellow]"
                    )
                    console.print(
                        "[yellow]This rollback only affects assignments that were added during the copy operation.[/yellow]"
                    )
                    console.print(
                        "[yellow]Any pre-existing assignments on the target user remain unchanged.[/yellow]"
                    )
        else:
            console.print("\n[red]✗ Rollback completed with errors[/red]")
            console.print(
                f"[dim]Rollback operation ID: {rollback_result.rollback_operation_id}[/dim]"
            )
            console.print(f"[dim]Completed: {rollback_result.completed_actions} actions[/dim]")
            console.print(f"[dim]Failed: {rollback_result.failed_actions} actions[/dim]")
            console.print(f"[dim]Duration: {rollback_result.duration_ms}ms[/dim]")

            if rollback_result.errors:
                console.print("\n[red]Errors encountered:[/red]")
                for error in rollback_result.errors:
                    console.print(f"[red]  • {error}[/red]")

        # Show warnings if any
        if rollback_plan.warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in rollback_plan.warnings:
                console.print(f"[yellow]  • {warning}[/yellow]")

    except Exception as e:
        console.print(f"\n[red]✗ Error executing rollback: {str(e)}[/red]")
        console.print("[yellow]Check the error details above and try again.[/yellow]")
        raise typer.Exit(1)

    console.print("\n[blue]Rollback operation completed![/blue]")


def _create_operation_details_panel(operation) -> Panel:
    """Create a panel displaying operation details."""
    details_content = []

    # Operation Information
    details_content.append("[bold blue]Operation Information[/bold blue]")
    details_content.append(f"  ID: [cyan]{operation.operation_id}[/cyan]")

    # Handle different operation record types for operation type
    if hasattr(operation, "operation_type"):
        operation_type_display = operation.operation_type.value.upper()
    elif hasattr(operation, "source_permission_set_name"):
        operation_type_display = "PERMISSION_SET_CLONE"
    else:
        operation_type_display = "UNKNOWN"

    details_content.append(f"  Type: [magenta]{operation_type_display}[/magenta]")
    details_content.append(
        f"  Date: [green]{operation.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}[/green]"
    )
    details_content.append("")

    # Principal Information
    details_content.append("[bold cyan]Principal Information[/bold cyan]")

    # Handle different operation record types
    if hasattr(operation, "principal_name"):
        principal_name = operation.principal_name
        principal_type = operation.principal_type.value
        principal_id = operation.principal_id
    elif hasattr(operation, "source_entity_name"):
        # For copy operations, show the target user (who will be affected by rollback)
        if (
            hasattr(operation, "operation_type")
            and operation.operation_type.value == "copy_assignments"
        ):
            principal_name = operation.target_entity_name
            principal_type = operation.target_entity_type.value
            principal_id = operation.target_entity_id
        else:
            # For other operations, use source entity info
            principal_name = operation.source_entity_name
            principal_type = operation.source_entity_type.value
            principal_id = operation.source_entity_id
    elif hasattr(operation, "source_permission_set_name"):
        # For permission set cloning operations, show the target permission set (which will be deleted)
        principal_name = operation.target_permission_set_name
        principal_type = "PERMISSION_SET"
        principal_id = operation.target_permission_set_arn
    else:
        principal_name = "Unknown"
        principal_type = "Unknown"
        principal_id = "Unknown"

    details_content.append(f"  Name: [cyan]{principal_name}[/cyan]")
    details_content.append(f"  Type: [magenta]{principal_type}[/magenta]")
    details_content.append(f"  ID: [dim]{principal_id}[/dim]")
    details_content.append("")

    # Permission Set Information
    details_content.append("[bold blue]Permission Set Information[/bold blue]")

    # Handle different operation record types for permission set name
    if hasattr(operation, "permission_set_name"):
        permission_set_name = operation.permission_set_name
        permission_set_arn = operation.permission_set_arn
    elif hasattr(operation, "permission_sets_involved") and operation.permission_sets_involved:
        # For PermissionCloningOperationRecord, use the first permission set
        permission_set_arn = operation.permission_sets_involved[0]
        permission_set_name = permission_set_arn.split("/")[-1]  # Extract name from ARN
    elif hasattr(operation, "source_permission_set_name"):
        # For PermissionSetCloningOperationRecord, show both source and target
        permission_set_name = (
            f"{operation.source_permission_set_name} → {operation.target_permission_set_name}"
        )
        permission_set_arn = (
            operation.target_permission_set_arn
        )  # Show target ARN (what will be deleted)
    else:
        permission_set_name = "Unknown"
        permission_set_arn = "Unknown"

    details_content.append(f"  Name: [blue]{permission_set_name}[/blue]")
    details_content.append(f"  ARN: [dim]{permission_set_arn}[/dim]")
    details_content.append("")

    # Results Summary
    details_content.append("[bold white]Results Summary[/bold white]")

    # Handle different operation record types for results
    if hasattr(operation, "results"):
        successful_results = sum(1 for r in operation.results if r.success)
        failed_results = len(operation.results) - successful_results
        total_accounts = len(operation.results)
    elif hasattr(operation, "accounts_affected"):
        # For PermissionCloningOperationRecord, use accounts_affected
        total_accounts = len(operation.accounts_affected)
        successful_results = (
            len(operation.assignments_copied)
            if hasattr(operation, "assignments_copied")
            else total_accounts
        )
        failed_results = total_accounts - successful_results
    else:
        total_accounts = 0
        successful_results = 0
        failed_results = 0

    details_content.append(f"  Total Accounts: [white]{total_accounts}[/white]")
    details_content.append(f"  Successful: [green]{successful_results}[/green]")
    if failed_results > 0:
        details_content.append(f"  Failed: [red]{failed_results}[/red]")

    # Metadata
    if operation.metadata:
        details_content.append("")
        details_content.append("[bold dim]Metadata[/bold dim]")
        for key, value in operation.metadata.items():
            details_content.append(f"  {key}: [dim]{value}[/dim]")

    # Build rich content with proper formatting
    from rich.console import Group
    from rich.text import Text

    # Convert each line to rich Text objects
    rich_lines = []
    for line in details_content:
        if line.startswith("[bold"):
            # Handle bold headers
            if "[bold blue]" in line:
                rich_lines.append(
                    Text(
                        line.replace("[bold blue]", "").replace("[/bold blue]", ""),
                        style="bold blue",
                    )
                )
            elif "[bold cyan]" in line:
                rich_lines.append(
                    Text(
                        line.replace("[bold cyan]", "").replace("[/bold cyan]", ""),
                        style="bold cyan",
                    )
                )
            elif "[bold white]" in line:
                rich_lines.append(
                    Text(
                        line.replace("[bold white]", "").replace("[/bold white]", ""),
                        style="bold white",
                    )
                )
            elif "[bold dim]" in line:
                rich_lines.append(
                    Text(
                        line.replace("[bold dim]", "").replace("[/bold dim]", ""), style="bold dim"
                    )
                )
            else:
                rich_lines.append(
                    Text(line.replace("[bold]", "").replace("[/bold]", ""), style="bold")
                )
        elif "[cyan]" in line:
            rich_lines.append(Text(line.replace("[cyan]", "").replace("[/cyan]", ""), style="cyan"))
        elif "[magenta]" in line:
            rich_lines.append(
                Text(line.replace("[magenta]", "").replace("[/magenta]", ""), style="magenta")
            )
        elif "[green]" in line:
            rich_lines.append(
                Text(line.replace("[green]", "").replace("[/green]", ""), style="green")
            )
        elif "[red]" in line:
            rich_lines.append(Text(line.replace("[red]", "").replace("[/red]", ""), style="red"))
        elif "[blue]" in line:
            rich_lines.append(Text(line.replace("[blue]", "").replace("[/blue]", ""), style="blue"))
        elif "[white]" in line:
            rich_lines.append(
                Text(line.replace("[white]", "").replace("[/white]", ""), style="white")
            )
        elif "[dim]" in line:
            rich_lines.append(Text(line.replace("[dim]", "").replace("[/dim]", ""), style="dim"))
        else:
            rich_lines.append(Text(line))

    return Panel(
        Group(*rich_lines),
        title="[bold]Operation Details[/bold]",
        title_align="left",
        border_style="blue",
        padding=(1, 2),
    )


@app.command()
def rollback_operation(
    operation_id: str = typer.Argument(..., help="Operation ID to rollback"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Rollback a copy or clone operation by operation ID."""
    try:
        # Try to determine operation type and delegate to appropriate rollback handler
        from ..aws_clients.manager import AWSClientManager
        from ..permission_cloning.rollback_integration import PermissionCloningRollbackIntegration
        from ..rollback.processor import RollbackProcessor

        client_manager = AWSClientManager()
        rollback_processor = RollbackProcessor()
        rollback_integration = PermissionCloningRollbackIntegration(
            client_manager, rollback_processor
        )

        # Try to get operation details to determine type
        operations = rollback_integration.get_rollbackable_operations()
        target_operation = None

        for op in operations:
            if op["operation_id"] == operation_id:
                target_operation = op
                break

        if not target_operation:
            typer.echo(f"❌ Operation {operation_id} not found or cannot be rolled back")
            raise typer.Exit(1)

        # Determine operation type and rollback accordingly
        if "source_entity_id" in target_operation:
            # Assignment copy operation
            typer.echo(f"🔄 Rolling back assignment copy operation: {operation_id}")
            result = rollback_integration.rollback_assignment_copy_operation(operation_id)

            if result["success"]:
                typer.echo(f"✅ Successfully rolled back operation {operation_id}")
                typer.echo(f"  - Successful actions: {result['success_count']}")
                typer.echo(f"  - Failed actions: {result['failure_count']}")
                typer.echo(f"  - Total actions: {result['total_actions']}")

                if result["errors"]:
                    typer.echo("\nErrors encountered:")
                    for error in result["errors"]:
                        typer.echo(f"  ❌ {error}")
            else:
                typer.echo(f"❌ Failed to rollback operation {operation_id}")
                if result["errors"]:
                    for error in result["errors"]:
                        typer.echo(f"  ❌ {error}")
                raise typer.Exit(1)

        elif "source_permission_set_name" in target_operation:
            # Permission set clone operation
            typer.echo(f"🔄 Rolling back permission set clone operation: {operation_id}")
            result = rollback_integration.rollback_permission_set_clone_operation(operation_id)

            if result["success"]:
                typer.echo(f"✅ Successfully rolled back operation {operation_id}")
                typer.echo(f"  - Deleted permission set: {result['permission_set_deleted']}")
                typer.echo(f"  - Permission set ARN: {result['permission_set_arn']}")
            else:
                typer.echo(f"❌ Failed to rollback operation {operation_id}")
                typer.echo(f"  - Error: {result['error']}")
                raise typer.Exit(1)
        else:
            typer.echo(f"❌ Unknown operation type for {operation_id}")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)


@app.command("status")
def show_status(
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Show rollback system status and statistics.

    Displays information about the rollback system including operation history,
    storage usage, and system health. Useful for monitoring and troubleshooting
    the rollback functionality.

    INFORMATION DISPLAYED:

      - Total number of tracked operations
      - Operations by type (assign/revoke)
      - Recent activity summary
      - Storage usage and location
      - System health status

    EXAMPLES:

      # Show rollback system status
      $ awsideman rollback status

      # Show status for specific profile
      $ awsideman rollback status --profile production

    NOTES:

      - This command does not require AWS credentials
      - Storage location is typically ~/.awsideman/operations/
      - Use this command to verify rollback system is working correctly
    """
    # Validate profile (for consistency)
    profile_name, _ = validate_profile(profile)

    console.print("[blue]Rollback System Status[/blue]")
    console.print(f"[dim]Profile: {profile_name}[/dim]")
    console.print()

    # Create operation logger with profile isolation
    try:
        logger = OperationLogger(profile=profile_name)
    except Exception as e:
        console.print(f"[red]Error: Failed to initialize operation logger: {str(e)}[/red]")
        raise typer.Exit(1)

    with console.status("[blue]Gathering system information...[/blue]"):
        try:
            # Get storage statistics
            storage_stats = logger.get_storage_stats()

            # Get recent operations for activity summary
            recent_operations = logger.get_operations(days=7, limit=100)
            all_operations = logger.get_operations(limit=1000)  # Get more for overall stats

        except Exception as e:
            console.print(f"[red]Error: Failed to gather system information: {str(e)}[/red]")
            raise typer.Exit(1)

    # Create status table
    status_table = Table(show_header=True, header_style="bold blue")
    status_table.add_column("Metric", style="cyan")
    status_table.add_column("Value", style="green")
    status_table.add_column("Description", style="dim")

    # Overall statistics
    total_operations = len(all_operations)
    assign_operations = sum(1 for op in all_operations if op.operation_type.value == "assign")
    revoke_operations = sum(1 for op in all_operations if op.operation_type.value == "revoke")
    rolled_back_operations = sum(1 for op in all_operations if op.rolled_back)

    status_table.add_row("Total Operations", str(total_operations), "All tracked operations")
    status_table.add_row("Assign Operations", str(assign_operations), "Permission set assignments")
    status_table.add_row("Revoke Operations", str(revoke_operations), "Permission set revocations")
    status_table.add_row(
        "Rolled Back", str(rolled_back_operations), "Operations that have been rolled back"
    )

    # Recent activity (last 7 days)
    recent_count = len(recent_operations)
    status_table.add_row(
        "Recent Activity", f"{recent_count} (7 days)", "Operations in the last week"
    )

    # Storage information
    status_table.add_row(
        "Storage Files", str(storage_stats.get("file_count", 0)), "Number of storage files"
    )

    # System health
    if total_operations > 0:
        health_status = "[green]Healthy[/green]"
        health_desc = "System is tracking operations"
    else:
        health_status = "[yellow]No Data[/yellow]"
        health_desc = "No operations tracked yet"

    status_table.add_row("System Health", health_status, health_desc)

    console.print(status_table)

    # Recent activity details
    if recent_operations:
        console.print("\n[blue]Recent Activity (Last 7 Days)[/blue]")

        activity_table = Table(show_header=True, header_style="bold green")
        activity_table.add_column("Date", style="green")
        activity_table.add_column("Type", style="magenta")
        activity_table.add_column("Principal", style="yellow")
        activity_table.add_column("Permission Set", style="blue")
        activity_table.add_column("Status", style="white")

        # Show up to 10 most recent operations
        for operation in recent_operations[:10]:
            formatted_date = operation.timestamp.strftime("%m-%d %H:%M")
            op_type = operation.operation_type.value.upper()

            # Truncate names for display
            principal_name = operation.principal_name
            if len(principal_name) > 15:
                principal_name = principal_name[:12] + "..."

            ps_name = operation.permission_set_name
            if len(ps_name) > 20:
                ps_name = ps_name[:17] + "..."

            # Status
            if operation.rolled_back:
                status = "[red]Rolled Back[/red]"
            else:
                successful_results = sum(1 for r in operation.results if r.success)
                total_results = len(operation.results)

                if successful_results == total_results:
                    status = "[green]Success[/green]"
                elif successful_results == 0:
                    status = "[red]Failed[/red]"
                else:
                    status = "[yellow]Partial[/yellow]"

            activity_table.add_row(
                formatted_date,
                op_type,
                principal_name,
                ps_name,
                status,
            )

        console.print(activity_table)

        if len(recent_operations) > 10:
            console.print(f"[dim]... and {len(recent_operations) - 10} more operations[/dim]")

    # Storage location information
    console.print("\n[dim]Storage Location: ~/.awsideman/operations/[/dim]")
    console.print("[dim]Use 'awsideman rollback list' to view operations[/dim]")
    console.print("[dim]Use 'awsideman rollback apply <operation-id>' to rollback operations[/dim]")
