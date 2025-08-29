"""Assignment creation command for awsideman.

This module provides the assign command for creating permission set assignments
in AWS Identity Center. It supports both single-account and multi-account assignments
with various filtering options.
"""

from typing import Optional

import typer
from botocore.exceptions import ClientError

from ...aws_clients.manager import AWSClientManager
from ...bulk.performance_optimizer import (
    create_performance_optimized_processor,
    display_performance_recommendations,
)
from ...bulk.resolver import ResourceResolver
from ...commands.permission_set.helpers import resolve_permission_set_identifier
from ...utils.config import Config
from ...utils.error_handler import handle_aws_error, handle_network_error
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import console, log_individual_operation

config = Config()


def _get_all_accounts(aws_client: AWSClientManager) -> list:
    """Get all accounts from AWS Organizations."""
    try:
        orgs_client = aws_client.get_raw_organizations_client()
        accounts = []

        paginator = orgs_client.get_paginator("list_accounts")
        for page in paginator.paginate():
            page_accounts = page.get("Accounts", [])
            for account in page_accounts:
                if account.get("Status") == "ACTIVE":
                    # Create AccountInfo object
                    from ...utils.models import AccountInfo

                    account_info = AccountInfo(
                        account_id=account["Id"],
                        account_name=account.get("Name", "Unknown"),
                        email=account.get("Email", ""),
                        status=account.get("Status", ""),
                        tags={},
                        ou_path=[],
                    )
                    accounts.append(account_info)

        return accounts
    except Exception as e:
        console.print(f"[red]Error getting accounts: {str(e)}[/red]")
        raise


def _get_accounts_by_tag(aws_client: AWSClientManager, tag_key: str, tag_value: str) -> list:
    """Get accounts by tag filter."""
    try:
        orgs_client = aws_client.get_raw_organizations_client()
        accounts = []

        paginator = orgs_client.get_paginator("list_accounts")
        for page in paginator.paginate():
            page_accounts = page.get("Accounts", [])
            for account in page_accounts:
                if account.get("Status") == "ACTIVE":
                    # Get account tags
                    try:
                        tags_response = orgs_client.list_tags_for_resource(ResourceId=account["Id"])
                        account_tags = {
                            tag["Key"]: tag["Value"] for tag in tags_response.get("Tags", [])
                        }

                        # Check if account matches the tag filter
                        if account_tags.get(tag_key) == tag_value:
                            from ...utils.models import AccountInfo

                            account_info = AccountInfo(
                                account_id=account["Id"],
                                account_name=account.get("Name", "Unknown"),
                                email=account.get("Email", ""),
                                status=account.get("Status", ""),
                                tags=account_tags,
                                ou_path=[],
                            )
                            accounts.append(account_info)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not get tags for account {account['Id']}: {str(e)}[/yellow]"
                        )
                        continue

        return accounts
    except Exception as e:
        console.print(f"[red]Error getting accounts by tag: {str(e)}[/red]")
        raise


def assign_permission_set(
    permission_set_name: str = typer.Argument(..., help="Permission set name"),
    principal_name: str = typer.Argument(..., help="Principal name (user or group)"),
    account_id: Optional[str] = typer.Argument(
        None, help="AWS account ID (for single account assignment)"
    ),
    account_filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Account filter for multi-account assignment (* for all accounts, or tag:Key=Value for tag-based filtering)",
    ),
    accounts: Optional[str] = typer.Option(
        None, "--accounts", help="Comma-separated list of account IDs for multi-account assignment"
    ),
    ou_filter: Optional[str] = typer.Option(
        None, "--ou-filter", help="Organizational unit path filter (e.g., 'Root/Production')"
    ),
    account_pattern: Optional[str] = typer.Option(
        None, "--account-pattern", help="Regex pattern for account name matching"
    ),
    principal_type: str = typer.Option(
        "USER", "--principal-type", help="Principal type (USER or GROUP)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview operations without making changes"
    ),
    batch_size: int = typer.Option(
        10,
        "--batch-size",
        help="Number of accounts to process concurrently (for multi-account operations)",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="Continue processing on individual account failures (for multi-account operations)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
) -> None:
    """Assign a permission set to a principal for one or more AWS accounts.

    This unified command supports both single-account and multi-account assignments:

    Single Account Assignment:
        Provide an account_id as the third argument to assign to a specific account.

    Multi-Account Assignment:
        Use --filter or --accounts to assign across multiple accounts.

    Examples:
        # Single account assignment
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com 123456789012

        # Multi-account assignment to all accounts
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com --filter "*"

        # Multi-account assignment with tag filter
        $ awsideman assignment assign PowerUserAccess developers --filter "tag:Environment=Production" --principal-type GROUP

        # Multi-account assignment to specific accounts
        $ awsideman assignment assign ViewOnlyAccess jane.doe@company.com --accounts "123456789012,987654321098"

        # Preview multi-account assignment without making changes
        $ awsideman assignment assign AdminAccess admin@company.com --filter "*" --dry-run
    """
    # Validate mutually exclusive target options
    provided_options = sum(
        [
            bool(account_id),
            bool(account_filter),
            bool(accounts),
            bool(ou_filter),
            bool(account_pattern),
        ]
    )
    if provided_options == 0:
        console.print("[red]Error: Must specify one target option[/red]")
        console.print("[yellow]Examples:[/yellow]")
        console.print(
            "  Single account: awsideman assignment assign ReadOnlyAccess user@company.com 123456789012"
        )
        console.print(
            "  Multi-account:  awsideman assignment assign ReadOnlyAccess user@company.com --filter '*'"
        )
        console.print(
            "  OU-based:       awsideman assignment assign ReadOnlyAccess user@company.com --ou-filter 'Root/Production'"
        )
        console.print(
            "  Pattern-based:  awsideman assignment assign ReadOnlyAccess user@company.com --account-pattern '^prod-.*'"
        )
        raise typer.Exit(1)
    elif provided_options > 1:
        console.print("[red]Error: Cannot specify multiple target options simultaneously[/red]")
        console.print(
            "[yellow]Choose one of: account_id, --filter, --accounts, --ou-filter, or --account-pattern[/yellow]"
        )
        raise typer.Exit(1)

    # Route to appropriate implementation
    if account_id:
        # Single account assignment
        return assign_single_account(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            account_id=account_id,
            principal_type=principal_type,
            profile=profile,
        )
    else:
        # Multi-account assignment with various filter options
        if accounts:
            # Convert comma-separated account list to list
            account_list = [acc.strip() for acc in accounts.split(",") if acc.strip()]

            if not account_list:
                console.print(
                    "[red]Error: No valid account IDs provided in --accounts parameter.[/red]"
                )
                raise typer.Exit(1)

            # Use explicit account assignment
            return assign_multi_account_explicit(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_list=account_list,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        elif account_filter:
            # Use account filter (existing multi-account assignment logic)
            return assign_multi_account_with_filter(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_filter=account_filter,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        else:
            # Use advanced filtering options (OU or pattern)
            return assign_multi_account_advanced(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                ou_filter=ou_filter,
                account_pattern=account_pattern,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )


def assign_multi_account_with_filter(
    permission_set_name: str,
    principal_name: str,
    account_filter: str,
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
) -> None:
    """Assign a permission set to a principal across accounts matching a filter.

    Args:
        permission_set_name: Name of the permission set to assign
        principal_name: Name of the principal (user or group)
        account_filter: Account filter string (* for all accounts, or tag:Key=Value)
        principal_type: Type of principal (USER or GROUP)
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not account_filter.strip():
        console.print("[red]Error: Account filter cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be greater than 0.[/red]")
        raise typer.Exit(1)

    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)

        # Create AWS client manager
        aws_client = AWSClientManager(profile=profile_name, region=profile_data.get("region"))

        # Resolve accounts based on filter
        console.print(f"[blue]Resolving accounts using filter: {account_filter}[/blue]")

        if account_filter == "*":
            # Get all accounts from AWS Organizations
            accounts = _get_all_accounts(aws_client)
        elif account_filter.startswith("tag:"):
            # Parse tag filter (format: tag:Key=Value)
            tag_parts = account_filter[4:].split("=", 1)
            if len(tag_parts) != 2:
                console.print("[red]Error: Invalid tag filter format. Use 'tag:Key=Value'[/red]")
                raise typer.Exit(1)

            tag_key, tag_value = tag_parts
            accounts = _get_accounts_by_tag(aws_client, tag_key, tag_value)
        else:
            console.print(f"[red]Error: Unsupported account filter format: {account_filter}[/red]")
            console.print(
                "[yellow]Supported formats: '*' for all accounts, 'tag:Key=Value' for tag-based filtering[/yellow]"
            )
            raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            return

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        from ...bulk.multi_account_batch import MultiAccountAssignment

        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Filter: [blue]{account_filter}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration_seconds']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration_seconds"])

        # Log bulk operations for rollback tracking (only if not dry run)
        if not dry_run and results.successful_accounts:
            try:
                from ...rollback.logger import OperationLogger

                # Create operation logger with profile isolation
                logger = OperationLogger(profile=profile_name)

                # Get principal ID and permission set ARN from the resolved multi_assignment
                # We need to resolve these since they're not in AccountResult objects
                try:
                    # Create a temporary resolver to get the principal ID and permission set ARN
                    from ...bulk.resolver import ResourceResolver

                    resolver = ResourceResolver(
                        aws_client_manager=aws_client,
                        instance_arn=instance_arn,
                        identity_store_id=identity_store_id,
                    )

                    # Resolve principal ID
                    principal_result = resolver.resolve_principal_name(
                        principal_name, principal_type
                    )
                    if not principal_result.success:
                        console.print(
                            f"[yellow]Warning: Could not resolve principal ID for logging: {principal_result.error_message}[/yellow]"
                        )
                        return

                    principal_id = principal_result.resolved_value

                    # Resolve permission set ARN
                    permission_set_arn = resolve_permission_set_identifier(
                        aws_client.get_sso_admin_client(),
                        instance_arn,
                        permission_set_name,
                        identity_store_id,
                    )

                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not resolve resources for logging: {str(e)}[/yellow]"
                    )
                    return

                # Group successful results by account for efficient logging
                account_ids = []
                account_names = []
                results_data = []

                for account_result in results.successful_accounts:
                    account_ids.append(account_result.account_id)
                    account_names.append(account_result.account_name)
                    results_data.append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log the bulk operation
                try:
                    operation_id = logger.log_operation(
                        operation_type="assign",
                        principal_id=principal_id,
                        principal_type=principal_type,
                        principal_name=principal_name,
                        permission_set_arn=permission_set_arn,
                        permission_set_name=permission_set_name,
                        account_ids=account_ids,
                        account_names=account_names,
                        results=results_data,
                        metadata={
                            "source": "multi_account_assign_explicit",
                            "account_count": len(accounts),
                            "batch_size": batch_size,
                            "total_accounts": len(accounts),
                            "successful_count": len(results.successful_accounts),
                            "failed_count": len(results.failed_accounts),
                        },
                    )

                    console.print(f"[dim]Logged bulk assign operation: {operation_id}[/dim]")

                except Exception as e:
                    # Don't fail the main operation if logging fails
                    console.print(
                        f"[yellow]Warning: Failed to log bulk assign operation: {str(e)}[/yellow]"
                    )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        from ...utils.error_handler import handle_network_error

        handle_network_error(e)


def assign_single_account(
    permission_set_name: str,
    principal_name: str,
    account_id: str,
    principal_type: str = "USER",
    profile: Optional[str] = None,
) -> None:
    """Assign a permission set to a principal for a specific account.

    Creates an assignment linking a permission set to a principal (user or group) for a specific AWS account.
    This allows the principal to assume the permission set's role in the specified account.

    Examples:
        # Assign a permission set to a user
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com 123456789012

        # Assign a permission set to a group
        $ awsideman assignment assign PowerUserAccess developers 123456789012 --principal-type GROUP
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    # Convert principal type to uppercase
    principal_type = principal_type.upper()

    # Validate permission set name format (basic validation - should not be empty)
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate account ID format (basic validation - should be 12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        console.print("[red]Error: Invalid account ID format.[/red]")
        console.print("[yellow]Account ID should be a 12-digit number.[/yellow]")
        raise typer.Exit(1)

    # Validate principal name format (basic validation - should not be empty)
    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    # Get SSO admin client
    try:
        sso_admin_client = aws_client.get_sso_admin_client()
    except Exception as e:
        console.print(f"[red]Error: Failed to create SSO admin client: {str(e)}[/red]")
        raise typer.Exit(1)

    # Resolve permission set name to ARN
    with console.status("[blue]Resolving permission set name...[/blue]"):
        try:
            permission_set_arn = resolve_permission_set_identifier(
                sso_admin_client, instance_arn, permission_set_name, identity_store_id
            )
        except typer.Exit:
            # Error already handled by resolve_permission_set_identifier
            raise

    # Resolve principal name to ID
    with console.status("[blue]Resolving principal name...[/blue]"):
        try:
            resolver = ResourceResolver(
                aws_client_manager=aws_client,
                instance_arn=instance_arn,
                identity_store_id=identity_store_id,
            )

            principal_result = resolver.resolve_principal_name(principal_name, principal_type)
            if not principal_result.success:
                console.print(f"[red]Error: {principal_result.error_message}[/red]")
                console.print(
                    "[yellow]Use 'awsideman user list' or 'awsideman group list' to see available principals.[/yellow]"
                )
                raise typer.Exit(1)

            principal_id = principal_result.resolved_value
            if principal_id is None:
                console.print("[red]Error: Failed to resolve principal ID[/red]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error resolving principal name: {str(e)}[/red]")
            raise typer.Exit(1)

    # Display a message indicating that we're creating the assignment
    with console.status("[blue]Creating permission set assignment...[/blue]"):
        try:
            # First, check if the assignment already exists
            list_params = {
                "InstanceArn": instance_arn,
                "AccountId": account_id,
                "PermissionSetArn": permission_set_arn,
            }

            # Check for existing assignment
            existing_response = sso_admin_client.list_account_assignments(**list_params)
            all_assignments = existing_response.get("AccountAssignments", [])

            # Filter assignments by principal ID and type locally
            existing_assignments = [
                assignment
                for assignment in all_assignments
                if assignment.get("PrincipalId") == principal_id
                and assignment.get("PrincipalType") == principal_type
            ]

            if existing_assignments:
                console.print("[yellow]Assignment already exists.[/yellow]")
                console.print(
                    "Permission set is already assigned to this principal for the specified account."
                )
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                return

            # Create the assignment
            create_params = {
                "InstanceArn": instance_arn,
                "TargetId": account_id,
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": permission_set_arn,
                "PrincipalType": principal_type,
                "PrincipalId": principal_id,
            }

            # Make the API call to create the assignment
            response = sso_admin_client.create_account_assignment(**create_params)

            # Extract the request ID for tracking
            request_id = response.get("AccountAssignmentCreationStatus", {}).get("RequestId")

            # The assignment creation is asynchronous, so we get a request status
            assignment_status = response.get("AccountAssignmentCreationStatus", {})
            status = assignment_status.get("Status", "UNKNOWN")

            if status == "IN_PROGRESS":
                console.print("[green]✓ Assignment creation initiated successfully.[/green]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Note: Assignment creation is asynchronous and may take a few moments to complete.[/yellow]"
                )
                console.print(
                    "[yellow]You can verify the assignment using 'awsideman assignment get' command.[/yellow]"
                )

                # Log the successful assignment operation
                log_individual_operation(
                    "assign",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                    profile=profile_name,
                )

                # Clear internal data storage to ensure fresh data
                try:
                    if aws_client.is_caching_enabled():
                        aws_client.clear_cache()

                except Exception:
                    # Don't fail the command if cache invalidation fails
                    pass

            elif status == "SUCCEEDED":
                console.print("[green]✓ Assignment created successfully.[/green]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[green]The principal can now access the specified account with the assigned permission set.[/green]"
                )

                # Log the successful assignment operation
                log_individual_operation(
                    "assign",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                    profile=profile_name,
                )
            elif status == "FAILED":
                failure_reason = assignment_status.get("FailureReason", "Unknown error")
                console.print(f"[red]✗ Assignment creation failed: {failure_reason}[/red]")
                console.print()
                console.print("[bold]Attempted Assignment:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                raise typer.Exit(1)
            else:
                console.print(f"[yellow]Assignment creation status: {status}[/yellow]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Please check the assignment status using 'awsideman assignment get' command.[/yellow]"
                )

        except ClientError as e:
            # Handle AWS API errors with enhanced error handling
            handle_aws_error(e, "CreateAccountAssignment")
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)


# Note: The multi-account assignment functions (assign_multi_account_explicit,
# assign_multi_account_advanced, _execute_multi_account_assignment) are complex
# and would make this file very large. For now, we'll implement them as stubs
# that call back to the original functions until they can be properly extracted.


def assign_multi_account_explicit(
    permission_set_name: str,
    principal_name: str,
    account_list: list,
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Assign a permission set to a principal across explicit list of AWS accounts.

    Args:
        permission_set_name: Name of the permission set to assign
        principal_name: Name of the principal (user or group)
        account_list: List of explicit account IDs
        principal_type: Type of principal (USER or GROUP)
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not account_list:
        console.print("[red]Error: Account list cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account validation
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with explicit accounts
        from ...utils.account_filter import AccountFilter

        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=account_list,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid account list.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on explicit list
        with console.status("[blue]Validating explicit account list...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error validating accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No valid accounts found in the provided list.[/yellow]")
            return  # Return instead of raising typer.Exit(0)

        console.print(f"[green]Validated {len(accounts)} account(s) from explicit list.[/green]")

        # Show preview of accounts
        console.print("\n[bold]Accounts to be processed:[/bold]")
        for i, account in enumerate(accounts):
            console.print(f"  {i+1}. {account.get_display_name()}")

        # Create multi-account assignment
        from ...bulk.multi_account_batch import MultiAccountAssignment

        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration_seconds']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration_seconds"])

        # Log bulk operations for rollback tracking (only if not dry run)
        if not dry_run and results.successful_accounts:
            try:
                from ...rollback.logger import OperationLogger

                # Create operation logger with profile isolation
                logger = OperationLogger(profile=profile_name)

                # Get principal ID and permission set ARN from the resolved multi_assignment
                # We need to resolve these since they're not in AccountResult objects
                try:
                    # Create a temporary resolver to get the principal ID and permission set ARN
                    from ...bulk.resolver import ResourceResolver

                    resolver = ResourceResolver(
                        aws_client_manager=aws_client,
                        instance_arn=instance_arn,
                        identity_store_id=identity_store_id,
                    )

                    # Resolve principal ID
                    principal_result = resolver.resolve_principal_name(
                        principal_name, principal_type
                    )
                    if not principal_result.success:
                        console.print(
                            f"[yellow]Warning: Could not resolve principal ID for logging: {principal_result.error_message}[/yellow]"
                        )
                        return

                    principal_id = principal_result.resolved_value

                    # Resolve permission set ARN
                    permission_set_arn = resolve_permission_set_identifier(
                        aws_client.get_sso_admin_client(),
                        instance_arn,
                        permission_set_name,
                        identity_store_id,
                    )

                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not resolve resources for logging: {str(e)}[/yellow]"
                    )
                    return

                # Group successful results by account for efficient logging
                account_ids = []
                account_names = []
                results_data = []

                for account_result in results.successful_accounts:
                    account_ids.append(account_result.account_id)
                    account_names.append(account_result.account_name)
                    results_data.append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log the bulk operation
                try:
                    operation_id = logger.log_operation(
                        operation_type="assign",
                        principal_id=principal_id,
                        principal_type=principal_type,
                        principal_name=principal_name,
                        permission_set_arn=permission_set_arn,
                        permission_set_name=permission_set_name,
                        account_ids=account_ids,
                        account_names=account_names,
                        results=results_data,
                        metadata={
                            "source": "multi_account_assign_explicit",
                            "account_count": len(accounts),
                            "batch_size": batch_size,
                            "total_accounts": len(accounts),
                            "successful_count": len(results.successful_accounts),
                            "failed_count": len(results.failed_accounts),
                        },
                    )

                    console.print(f"[dim]Logged bulk assign operation: {operation_id}[/dim]")

                except Exception as e:
                    # Don't fail the main operation if logging fails
                    console.print(
                        f"[yellow]Warning: Failed to log bulk assign operation: {str(e)}[/yellow]"
                    )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        handle_network_error(e)


def assign_multi_account_advanced(
    permission_set_name: str,
    principal_name: str,
    ou_filter: Optional[str] = None,
    account_pattern: Optional[str] = None,
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Assign a permission set to a principal using advanced filtering options.

    Args:
        permission_set_name: Name of the permission set to assign
        principal_name: Name of the principal (user or group)
        ou_filter: Organizational unit path filter
        account_pattern: Regex pattern for account name matching
        principal_type: Type of principal (USER or GROUP)
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not ou_filter and not account_pattern:
        console.print("[red]Error: Must specify either --ou-filter or --account-pattern.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account filtering
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with advanced options
        from ...utils.account_filter import AccountFilter

        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=None,
            ou_filter=ou_filter,
            account_name_pattern=account_pattern,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid filter options.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on filter
        with console.status("[blue]Resolving accounts based on filter...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error resolving accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            console.print("[yellow]Please check your filter options and try again.[/yellow]")
            return  # Return instead of raising typer.Exit(0)

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        from ...bulk.multi_account_batch import MultiAccountAssignment

        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Filter Type: [blue]{'OU' if ou_filter else 'Pattern'}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration_seconds']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration_seconds"])

        # Log bulk operations for rollback tracking (only if not dry run)
        if not dry_run and results.successful_accounts:
            try:
                from ...rollback.logger import OperationLogger

                # Create operation logger with profile isolation
                logger = OperationLogger(profile=profile_name)

                # Get principal ID and permission set ARN from the resolved multi_assignment
                # We need to resolve these since they're not in AccountResult objects
                try:
                    # Create a temporary resolver to get the principal ID and permission set ARN
                    from ...bulk.resolver import ResourceResolver

                    resolver = ResourceResolver(
                        aws_client_manager=aws_client,
                        instance_arn=instance_arn,
                        identity_store_id=identity_store_id,
                    )

                    # Resolve principal ID
                    principal_result = resolver.resolve_principal_name(
                        principal_name, principal_type
                    )
                    if not principal_result.success:
                        console.print(
                            f"[yellow]Warning: Could not resolve principal ID for logging: {principal_result.error_message}[/yellow]"
                        )
                        return

                    principal_id = principal_result.resolved_value

                    # Resolve permission set ARN
                    permission_set_arn = resolve_permission_set_identifier(
                        aws_client.get_sso_admin_client(),
                        instance_arn,
                        permission_set_name,
                        identity_store_id,
                    )

                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not resolve resources for logging: {str(e)}[/yellow]"
                    )
                    return

                # Group successful results by account for efficient logging
                account_ids = []
                account_names = []
                results_data = []

                for account_result in results.successful_accounts:
                    account_ids.append(account_result.account_id)
                    account_names.append(account_result.account_name)
                    results_data.append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log the bulk operation
                try:
                    operation_id = logger.log_operation(
                        operation_type="assign",
                        principal_id=principal_id,
                        principal_type=principal_type,
                        principal_name=principal_name,
                        permission_set_arn=permission_set_arn,
                        permission_set_name=permission_set_name,
                        account_ids=account_ids,
                        account_names=account_names,
                        results=results_data,
                        metadata={
                            "source": "multi_account_assign_advanced",
                            "ou_filter": ou_filter,
                            "account_pattern": account_pattern,
                            "batch_size": batch_size,
                            "total_accounts": len(accounts),
                            "successful_count": len(results.successful_accounts),
                            "failed_count": len(results.failed_accounts),
                        },
                    )

                    console.print(f"[dim]Logged bulk assign operation: {operation_id}[/dim]")

                except Exception as e:
                    # Don't fail the main operation if logging fails
                    console.print(
                        f"[yellow]Warning: Failed to log bulk assign operation: {str(e)}[/yellow]"
                    )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        from ...utils.error_handler import handle_network_error

        handle_network_error(e)


# Removed the stub function - replaced with proper implementation above
