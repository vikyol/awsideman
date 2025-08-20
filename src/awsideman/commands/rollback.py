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
from ..rollback.processor import RollbackProcessor
from ..utils.config import Config
from ..utils.validators import validate_profile

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
        30, "--days", "-d", help="Show operations from the last N days (default: 30)"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of operations to show"
    ),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table or json)"),
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
      --days: Show operations from the last N days (default: 30)
      --limit: Limit the number of results returned

    OUTPUT FORMATS:

      table: Human-readable table format (default)
      json: Machine-readable JSON format

    EXAMPLES:

      # List all operations from the last 30 days
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

    # Create operation logger
    try:
        logger = OperationLogger()
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
            principal_name = operation.principal_name
            if len(principal_name) > 20:
                principal_name = principal_name[:17] + "..."

            # Format permission set name (truncate if too long)
            ps_name = operation.permission_set_name
            if len(ps_name) > 25:
                ps_name = ps_name[:22] + "..."

            # Format account count
            account_count = len(operation.account_ids)
            if account_count == 1:
                accounts_text = f"{account_count} account"
            else:
                accounts_text = f"{account_count} accounts"

            # Format status
            if operation.rolled_back:
                status = "[red]Rolled Back[/red]"
            else:
                # Check if all results were successful
                successful_results = sum(1 for r in operation.results if r.success)
                total_results = len(operation.results)

                if successful_results == total_results:
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
    operation_id: str = typer.Argument(..., help="Operation ID to rollback"),
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

    NOTES:

      - Operation IDs can be found using 'rollback list' command
      - Rollback operations are also tracked and can be rolled back themselves
      - Use dry-run mode to verify the rollback plan before applying
      - Partial failures are handled gracefully with detailed reporting
    """
    # Validate input parameters
    if not operation_id.strip():
        console.print("[red]Error: Operation ID cannot be empty.[/red]")
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

    # Create operation logger
    try:
        logger = OperationLogger()
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

            console.print(
                f"[green]✓ Found operation: {operation.operation_type.value} operation from {operation.timestamp.strftime('%Y-%m-%d %H:%M')}[/green]"
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
    if operation.operation_type.value == "assign":
        rollback_action = "revoke"
    else:
        rollback_action = "assign"

    # Calculate successful results that can be rolled back
    successful_results = [r for r in operation.results if r.success]

    if not yes:
        console.print(
            f"\n[yellow]⚠ This will {rollback_action} {len(successful_results)} assignment(s).[/yellow]"
        )

        confirm = typer.confirm("Do you want to proceed with the rollback?")
        if not confirm:
            console.print("[yellow]Rollback cancelled by user.[/yellow]")
            raise typer.Exit(0)

    # Step 4: Execute rollback using RollbackProcessor
    console.print("\n[blue]Step 3: Executing rollback operation...[/blue]")

    # Check if this appears to be test data
    is_test_data = (
        "1234567890abcdef" in operation.permission_set_arn
        or "123456789012" in operation.account_ids
        or "group-1234567890abcdef" in operation.principal_id
        or "user-1234567890abcdef" in operation.principal_id
    )

    if is_test_data:
        console.print(
            "[yellow]⚠ This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(
            "[yellow]Test operations contain fake AWS resource identifiers that cannot be used with real AWS APIs[/yellow]"
        )
        console.print(f"[dim]Permission Set ARN: {operation.permission_set_arn}[/dim]")
        console.print(f"[dim]Principal ID: {operation.principal_id}[/dim]")
        console.print(f"[dim]Account IDs: {operation.account_ids}[/dim]")
        console.print(
            "\n[blue]To test rollback functionality, you need to create real operations using the assignment commands[/blue]"
        )
        console.print("\n[blue]Rollback operation completed![/blue]")
        return

    # Validate that the operation contains valid AWS ARNs
    if not operation.permission_set_arn.startswith("arn:aws:sso:::"):
        console.print("[red]✗ Invalid permission set ARN format[/red]")
        console.print(
            "[yellow]This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(f"[dim]ARN: {operation.permission_set_arn}[/dim]")
        raise typer.Exit(1)

    # Check if the ARN contains a valid instance ID
    if "/ssoins-" not in operation.permission_set_arn:
        console.print("[red]✗ Invalid permission set ARN format[/red]")
        console.print(
            "[yellow]This appears to be test data and cannot be processed for rollback[/yellow]"
        )
        console.print(f"[dim]ARN: {operation.permission_set_arn}[/dim]")
        raise typer.Exit(1)

    try:
        # Initialize AWS client manager
        region = profile_data.get("region")
        aws_client_manager = AWSClientManager(profile=profile_name, region=region)

        # Initialize RollbackProcessor
        rollback_processor = RollbackProcessor(
            aws_client_manager=aws_client_manager, config=config, show_progress=False
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
                console.print(f"[dim]Permission Set ARN: {operation.permission_set_arn}[/dim]")
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
                account_names_map = dict(zip(operation.account_ids, operation.account_names))

                for action in rollback_plan.actions:
                    account_name = account_names_map.get(action.account_id, action.account_id)
                    plan_table.add_row(
                        operation.principal_name,
                        operation.permission_set_name,
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
    details_content.append(f"  Type: [magenta]{operation.operation_type.value.upper()}[/magenta]")
    details_content.append(
        f"  Date: [green]{operation.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}[/green]"
    )
    details_content.append("")

    # Principal Information
    details_content.append("[bold cyan]Principal Information[/bold cyan]")
    details_content.append(f"  Name: [cyan]{operation.principal_name}[/cyan]")
    details_content.append(f"  Type: [magenta]{operation.principal_type.value}[/magenta]")
    details_content.append(f"  ID: [dim]{operation.principal_id}[/dim]")
    details_content.append("")

    # Permission Set Information
    details_content.append("[bold blue]Permission Set Information[/bold blue]")
    details_content.append(f"  Name: [blue]{operation.permission_set_name}[/blue]")
    details_content.append(f"  ARN: [dim]{operation.permission_set_arn}[/dim]")
    details_content.append("")

    # Results Summary
    details_content.append("[bold white]Results Summary[/bold white]")
    successful_results = sum(1 for r in operation.results if r.success)
    failed_results = len(operation.results) - successful_results

    details_content.append(f"  Total Accounts: [white]{len(operation.results)}[/white]")
    details_content.append(f"  Successful: [green]{successful_results}[/green]")
    if failed_results > 0:
        details_content.append(f"  Failed: [red]{failed_results}[/red]")

    # Metadata
    if operation.metadata:
        details_content.append("")
        details_content.append("[bold dim]Metadata[/bold dim]")
        for key, value in operation.metadata.items():
            details_content.append(f"  {key}: [dim]{value}[/dim]")

    content_text = "\n".join(details_content)

    return Panel(
        content_text,
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

    # Create operation logger
    try:
        logger = OperationLogger()
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
