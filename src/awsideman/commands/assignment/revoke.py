"""Assignment revocation command for awsideman.

This module provides the revoke command for removing permission set assignments
in AWS Identity Center. It supports both single-account and multi-account revocations
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
from ...utils.error_handler import handle_aws_error
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import (
    console,
    log_individual_operation,
    resolve_permission_set_info,
    resolve_principal_info,
)

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


def revoke_permission_set(
    permission_set_name: str = typer.Argument(..., help="Permission set name"),
    principal_name: str = typer.Argument(..., help="Principal name (user or group)"),
    account_id: Optional[str] = typer.Argument(
        None, help="AWS account ID (for single account revocation)"
    ),
    account_filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Account filter for multi-account revocation (* for all accounts, or tag:Key=Value for tag-based filtering)",
    ),
    accounts: Optional[str] = typer.Option(
        None, "--accounts", help="Comma-separated list of account IDs for multi-account revocation"
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
    force: bool = typer.Option(
        False, "--force", "-f", help="Force revocation without confirmation"
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
    """Revoke a permission set assignment from a principal for one or more AWS accounts.

    This unified command supports both single-account and multi-account revocations:

    Single Account Revocation:
        Provide an account_id as the third argument to revoke from a specific account.

    Multi-Account Revocation:
        Use --filter or --accounts to revoke across multiple accounts.

    Examples:
        # Single account revocation
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012

        # Multi-account revocation from all accounts
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com --filter "*"

        # Multi-account revocation with tag filter
        $ awsideman assignment revoke PowerUserAccess developers --filter "tag:Environment=Production" --principal-type GROUP

        # Multi-account revocation from specific accounts
        $ awsideman assignment revoke ViewOnlyAccess jane.doe@company.com --accounts "123456789012,987654321098"

        # Preview multi-account revocation without making changes
        $ awsideman assignment revoke AdminAccess admin@company.com --filter "*" --dry-run

        # Force revocation without confirmation
        $ awsideman assignment revoke TempAccess temp.user@company.com 123456789012 --force
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
            "  Single account: awsideman assignment revoke ReadOnlyAccess user@company.com 123456789012"
        )
        console.print(
            "  Multi-account:  awsideman assignment revoke ReadOnlyAccess user@company.com --filter '*'"
        )
        console.print(
            "  OU-based:       awsideman assignment revoke ReadOnlyAccess user@company.com --ou-filter 'Root/Production'"
        )
        console.print(
            "  Pattern-based:  awsideman assignment revoke ReadOnlyAccess user@company.com --account-pattern '^prod-.*'"
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
        # Single account revocation
        return revoke_single_account(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            account_id=account_id,
            principal_type=principal_type,
            force=force,
            profile=profile,
            dry_run=dry_run,
        )
    else:
        # Multi-account revocation with explicit accounts
        if accounts:
            # Convert comma-separated account list to list
            account_list = [acc.strip() for acc in accounts.split(",") if acc.strip()]

            if not account_list:
                console.print(
                    "[red]Error: No valid account IDs provided in --accounts parameter.[/red]"
                )
                raise typer.Exit(1)

            # Use explicit account revocation
            return revoke_multi_account_explicit(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_list=account_list,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )

        elif account_filter:
            # Use account filter (existing multi-account revocation logic)
            return revoke_multi_account_with_filter(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_filter=account_filter,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        else:
            # Use advanced filtering options (OU or pattern)
            return revoke_multi_account_advanced(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                ou_filter=ou_filter,
                account_pattern=account_pattern,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )


def revoke_multi_account_with_filter(
    permission_set_name: str,
    principal_name: str,
    account_filter: str,
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
) -> None:
    """Revoke a permission set assignment from a principal across accounts matching a filter.

    Args:
        permission_set_name: Name of the permission set to revoke
        principal_name: Name of the principal (user or group)
        account_filter: Account filter string (* for all accounts, or tag:Key=Value)
        principal_type: Type of principal (USER or GROUP)
        force: Whether to force revocation without confirmation
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
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless force flag is used or dry run
        if not force and not dry_run:
            console.print(
                f"\n[bold red]⚠️  WARNING: You are about to revoke a permission set assignment across {len(accounts)} account(s)[/bold red]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            console.print(f"  Filter: [blue]{account_filter}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")
            console.print()
            console.print(
                "[red]This will remove the principal's access to the specified accounts through this permission set.[/red]"
            )

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
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
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
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

                # Group successful results by principal and permission set for efficient logging
                operation_groups = {}

                for account_result in results.successful_accounts:
                    # Create a key for grouping operations
                    key = (
                        account_result.principal_id,
                        account_result.principal_type,
                        account_result.permission_set_arn,
                    )

                    if key not in operation_groups:
                        operation_groups[key] = {
                            "principal_id": account_result.principal_id,
                            "principal_type": account_result.principal_type,
                            "principal_name": account_result.principal_name,
                            "permission_set_arn": account_result.permission_set_arn,
                            "permission_set_name": account_result.permission_set_name,
                            "account_ids": [],
                            "account_names": [],
                            "results": [],
                        }

                    # Add account information
                    operation_groups[key]["account_ids"].append(account_result.account_id)
                    operation_groups[key]["account_names"].append(account_result.account_name)
                    operation_groups[key]["results"].append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log each operation group
                for group_data in operation_groups.values():
                    try:
                        operation_id = logger.log_operation(
                            operation_type="revoke",
                            principal_id=group_data["principal_id"],
                            principal_type=group_data["principal_type"],
                            principal_name=group_data["principal_name"],
                            permission_set_arn=group_data["permission_set_arn"],
                            permission_set_name=group_data["permission_set_name"],
                            account_ids=group_data["account_ids"],
                            account_names=group_data["account_names"],
                            results=group_data["results"],
                            metadata={
                                "source": "multi_account_revoke_with_filter",
                                "account_filter": account_filter,
                                "batch_size": batch_size,
                                "total_accounts": len(accounts),
                                "successful_count": len(results.successful_accounts),
                                "failed_count": len(results.failed_accounts),
                            },
                        )

                        console.print(f"[dim]Logged bulk revoke operation: {operation_id}[/dim]")

                    except Exception as e:
                        # Don't fail the main operation if logging fails
                        console.print(
                            f"[yellow]Warning: Failed to log bulk revoke operation: {str(e)}[/yellow]"
                        )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        from ...utils.error_handler import handle_network_error

        handle_network_error(e)


def revoke_multi_account_explicit(
    permission_set_name: str,
    principal_name: str,
    account_list: list,
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
) -> None:
    """Revoke a permission set assignment from a principal across specific accounts.

    Args:
        permission_set_name: Name of the permission set to revoke
        principal_name: Name of the principal (user or group)
        account_list: List of account IDs to revoke from
        principal_type: Type of principal (USER or GROUP)
        force: Whether to force revocation without confirmation
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
        console.print("[red]Error: Batch size must be greater than 0.[/red]")
        raise typer.Exit(1)

    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)

        # Create AWS client manager
        aws_client = AWSClientManager(profile=profile_name, region=profile_data.get("region"))

        # Convert account IDs to AccountInfo objects
        from ...utils.models import AccountInfo

        accounts = []
        for account_id in account_list:
            account_info = AccountInfo(
                account_id=account_id,
                account_name=f"Account-{account_id}",
                email="",
                status="ACTIVE",
                tags={},
                ou_path=[],
            )
            accounts.append(account_info)

        console.print(f"[green]Found {len(accounts)} account(s) for revocation.[/green]")

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
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless force flag is used or dry run
        if not force and not dry_run:
            console.print(
                f"\n[bold red]⚠️  WARNING: You are about to revoke a permission set assignment across {len(accounts)} account(s)[/bold red]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            console.print(f"  Account Count: {len(accounts)}")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")
            console.print()
            console.print(
                "[red]This will remove the principal's access to the specified accounts through this permission set.[/red]"
            )

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
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
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
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

                # Group successful results by principal and permission set for efficient logging
                operation_groups = {}

                for account_result in results.successful_accounts:
                    # Create a key for grouping operations
                    key = (
                        account_result.principal_id,
                        account_result.principal_type,
                        account_result.permission_set_arn,
                    )

                    if key not in operation_groups:
                        operation_groups[key] = {
                            "principal_id": account_result.principal_id,
                            "principal_type": account_result.principal_type,
                            "principal_name": account_result.principal_name,
                            "permission_set_arn": account_result.permission_set_arn,
                            "permission_set_name": account_result.permission_set_name,
                            "account_ids": [],
                            "account_names": [],
                            "results": [],
                        }

                    # Add account information
                    operation_groups[key]["account_ids"].append(account_result.account_id)
                    operation_groups[key]["account_names"].append(account_result.account_name)
                    operation_groups[key]["results"].append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log each operation group
                for group_data in operation_groups.values():
                    try:
                        operation_id = logger.log_operation(
                            operation_type="revoke",
                            principal_id=group_data["principal_id"],
                            principal_type=group_data["principal_type"],
                            principal_name=group_data["principal_name"],
                            permission_set_arn=group_data["permission_set_arn"],
                            permission_set_name=group_data["permission_set_name"],
                            account_ids=group_data["account_ids"],
                            account_names=group_data["account_names"],
                            results=group_data["results"],
                            metadata={
                                "source": "multi_account_revoke_explicit",
                                "account_list": account_list,
                                "batch_size": batch_size,
                                "total_accounts": len(accounts),
                                "successful_count": len(results.successful_accounts),
                                "failed_count": len(results.failed_accounts),
                            },
                        )

                        console.print(f"[dim]Logged bulk revoke operation: {operation_id}[/dim]")

                    except Exception as e:
                        # Don't fail the main operation if logging fails
                        console.print(
                            f"[yellow]Warning: Failed to log bulk revoke operation: {str(e)}[/yellow]"
                        )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        from ...utils.error_handler import handle_aws_error

        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        from ...utils.error_handler import handle_network_error

        handle_network_error(e)


def revoke_multi_account_advanced(
    permission_set_name: str,
    principal_name: str,
    ou_filter: Optional[str] = None,
    account_pattern: Optional[str] = None,
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
) -> None:
    """Revoke a permission set assignment from a principal using advanced filtering options.

    Args:
        permission_set_name: Name of the permission set to revoke
        principal_name: Name of the principal (user or group)
        ou_filter: Organizational unit path filter (e.g., 'Root/Production')
        account_pattern: Regex pattern for account name matching
        principal_type: Type of principal (USER or GROUP)
        force: Whether to force revocation without confirmation
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
        console.print("[red]Error: Either OU filter or account pattern must be specified.[/red]")
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

        # Resolve accounts based on advanced filters
        console.print("[blue]Resolving accounts using advanced filters...[/blue]")

        accounts = []

        if ou_filter:
            console.print(f"  OU Filter: {ou_filter}")
            # Use the existing hierarchy builder to get accounts by OU
            from ...utils.hierarchy_builder import build_organization_hierarchy, search_accounts

            org_hierarchy = build_organization_hierarchy(aws_client)
            ou_accounts = search_accounts(org_hierarchy, ou_filter)
            accounts.extend(ou_accounts)

        if account_pattern:
            console.print(f"  Account Pattern: {account_pattern}")
            # Get all accounts and filter by pattern
            all_accounts = _get_all_accounts(aws_client)
            import re

            pattern = re.compile(account_pattern, re.IGNORECASE)
            pattern_accounts = [acc for acc in all_accounts if pattern.search(acc.account_name)]
            accounts.extend(pattern_accounts)

        # Remove duplicates while preserving order
        seen = set()
        unique_accounts = []
        for account in accounts:
            if account.account_id not in seen:
                seen.add(account.account_id)
                unique_accounts.append(account)
        accounts = unique_accounts

        if not accounts:
            console.print(
                "[yellow]No accounts found matching the advanced filter criteria.[/yellow]"
            )
            return

        console.print(
            f"[green]Found {len(accounts)} account(s) matching advanced filter criteria.[/green]"
        )

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
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless force flag is used or dry run
        if not force and not dry_run:
            console.print(
                f"\n[bold red]⚠️  WARNING: You are about to revoke a permission set assignment across {len(accounts)} account(s)[/bold red]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            if ou_filter:
                console.print(f"  OU Filter: [blue]{ou_filter}[/blue]")
            if account_pattern:
                console.print(f"  Account Pattern: [blue]{account_pattern}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")
            console.print()
            console.print(
                "[red]This will remove the principal's access to the specified accounts through this permission set.[/red]"
            )

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
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
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                error_handling="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
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

                # Group successful results by principal and permission set for efficient logging
                operation_groups = {}

                for account_result in results.successful_accounts:
                    # Create a key for grouping operations
                    key = (
                        account_result.principal_id,
                        account_result.principal_type,
                        account_result.permission_set_arn,
                    )

                    if key not in operation_groups:
                        operation_groups[key] = {
                            "principal_id": account_result.principal_id,
                            "principal_type": account_result.principal_type,
                            "principal_name": account_result.principal_name,
                            "permission_set_arn": account_result.permission_set_arn,
                            "permission_set_name": account_result.permission_set_name,
                            "account_ids": [],
                            "account_names": [],
                            "results": [],
                        }

                    # Add account information
                    operation_groups[key]["account_ids"].append(account_result.account_id)
                    operation_groups[key]["account_names"].append(account_result.account_name)
                    operation_groups[key]["results"].append(
                        {
                            "account_id": account_result.account_id,
                            "success": True,
                            "error": None,
                            "duration_ms": int((account_result.processing_time or 0) * 1000),
                        }
                    )

                # Log each operation group
                for group_data in operation_groups.values():
                    try:
                        operation_id = logger.log_operation(
                            operation_type="revoke",
                            principal_id=group_data["principal_id"],
                            principal_type=group_data["principal_type"],
                            principal_name=group_data["principal_name"],
                            permission_set_arn=group_data["permission_set_arn"],
                            permission_set_name=group_data["permission_set_name"],
                            account_ids=group_data["account_ids"],
                            account_names=group_data["account_names"],
                            results=group_data["results"],
                            metadata={
                                "source": "multi_account_revoke_advanced",
                                "ou_filter": ou_filter,
                                "account_pattern": account_pattern,
                                "batch_size": batch_size,
                                "total_accounts": len(accounts),
                                "successful_count": len(results.successful_accounts),
                                "failed_count": len(results.failed_accounts),
                            },
                        )

                        console.print(f"[dim]Logged bulk revoke operation: {operation_id}[/dim]")

                    except Exception as e:
                        # Don't fail the main operation if logging fails
                        console.print(
                            f"[yellow]Warning: Failed to log bulk revoke operation: {str(e)}[/yellow]"
                        )

            except Exception as e:
                # Don't fail the main operation if logging fails
                console.print(
                    f"[yellow]Warning: Failed to initialize bulk operation logging: {str(e)}[/yellow]"
                )

    except ClientError as e:
        from ...utils.error_handler import handle_aws_error

        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        from ...utils.error_handler import handle_network_error

        handle_network_error(e)


def revoke_single_account(
    permission_set_name: str,
    principal_name: str,
    account_id: str,
    principal_type: str = "USER",
    force: bool = False,
    profile: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Revoke a permission set assignment from a principal.

    Removes an assignment linking a permission set to a principal (user or group) for a specific AWS account.
    This will remove the principal's access to the specified account through the permission set.

    Examples:
        # Revoke a permission set assignment from a user
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012

        # Revoke a permission set assignment from a group
        $ awsideman assignment revoke PowerUserAccess developers 123456789012 --principal-type GROUP

        # Force revocation without confirmation
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012 --force
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

    # Get identity store client
    try:
        identity_store_client = aws_client.get_identity_store_client()
    except Exception as e:
        console.print(f"[red]Error: Failed to create identity store client: {str(e)}[/red]")
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

    # Handle dry-run mode early to avoid hanging API calls
    if dry_run:
        console.print("[green]✓ DRY RUN MODE - No changes will be made[/green]")
        console.print()
        console.print("[bold]Assignment that would be revoked:[/bold]")
        console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
        console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
        console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
        console.print()
        console.print(
            "[yellow]This is a preview. Use --force to actually revoke the assignment.[/yellow]"
        )
        return

    # Display a message indicating that we're checking the assignment
    with console.status("[blue]Checking assignment details...[/blue]"):
        try:
            # First, check if the assignment exists
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

            if not existing_assignments:
                console.print("[red]Error: Assignment not found.[/red]")
                console.print("[yellow]No assignment found for:[/yellow]")
                console.print(f"  Permission Set: {permission_set_name}")
                console.print(f"  Principal: {principal_name} ({principal_type})")
                console.print(f"  Account ID: {account_id}")
                console.print(
                    "[yellow]Use 'awsideman assignment list' to see all available assignments.[/yellow]"
                )
                raise typer.Exit(1)

            # Resolve names for display
            try:
                permission_set_info = resolve_permission_set_info(
                    instance_arn, permission_set_arn, sso_admin_client
                )
                permission_set_display_name = permission_set_info.get("Name", "Unknown")
            except typer.Exit:
                permission_set_display_name = "Unknown"

            try:
                principal_info = resolve_principal_info(
                    identity_store_id, principal_id, principal_type, identity_store_client
                )
                principal_display_name = principal_info.get("DisplayName", "Unknown")
            except typer.Exit:
                principal_display_name = "Unknown"

            # Show confirmation prompt unless force flag is used
            if not force:
                console.print()
                console.print(
                    "[bold red]⚠️  WARNING: You are about to revoke a permission set assignment[/bold red]"
                )
                console.print()
                console.print("[bold]Assignment to be revoked:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[red]This will remove the principal's access to the specified account through this permission set.[/red]"
                )
                console.print()

                # Get user confirmation
                confirm = typer.confirm("Are you sure you want to revoke this assignment?")
                if not confirm:
                    console.print("[yellow]Assignment revocation cancelled.[/yellow]")
                    raise typer.Exit(0)

            # Revoke the assignment
            # Create the revocation parameters
            delete_params = {
                "InstanceArn": instance_arn,
                "TargetId": account_id,
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": permission_set_arn,
                "PrincipalType": principal_type,
                "PrincipalId": principal_id,
            }

            # Make the API call to delete the assignment
            response = sso_admin_client.delete_account_assignment(**delete_params)

            # Extract the request ID for tracking
            request_id = response.get("AccountAssignmentDeletionStatus", {}).get("RequestId")

            # The assignment deletion is asynchronous, so we get a request status
            assignment_status = response.get("AccountAssignmentDeletionStatus", {})
            status = assignment_status.get("Status", "UNKNOWN")

            # Handle the response and display appropriate output
            if status == "IN_PROGRESS":
                console.print("[green]✓ Assignment revocation initiated successfully.[/green]")
                console.print()
                console.print("[bold]Revoked Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Note: Assignment revocation is asynchronous and may take a few moments to complete.[/yellow]"
                )
                console.print(
                    "[yellow]You can verify the revocation using 'awsideman assignment list' command.[/yellow]"
                )

                # Log the successful revocation operation
                log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_display_name,
                    permission_set_arn,
                    permission_set_display_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                    profile=profile_name,
                )

                # Invalidate cache to ensure assignment data is fresh
                try:
                    # Clear internal data storage to ensure fresh data
                    if aws_client.is_caching_enabled():
                        aws_client.clear_cache()

                except Exception:
                    # Don't fail the command if cache invalidation fails
                    pass

            elif status == "SUCCEEDED":
                console.print("[green]✓ Assignment revoked successfully.[/green]")
                console.print()
                console.print("[bold]Revoked Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[green]The principal no longer has access to the specified account through this permission set.[/green]"
                )

                # Log the successful revocation operation
                log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_display_name,
                    permission_set_arn,
                    permission_set_display_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                    profile=profile_name,
                )
            elif status == "FAILED":
                failure_reason = assignment_status.get("FailureReason", "Unknown error")
                console.print(f"[red]✗ Assignment revocation failed: {failure_reason}[/red]")
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                raise typer.Exit(1)
            else:
                console.print(f"[yellow]Assignment revocation status: {status}[/yellow]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Please check the assignment status using 'awsideman assignment list' command.[/yellow]"
                )

        except ClientError as e:
            # Handle AWS API errors
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                console.print("[red]✗ Assignment revocation failed: Assignment not found.[/red]")
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set ARN: {permission_set_arn}")
                console.print(f"  Principal ID: {principal_id}")
                console.print(f"  Principal Type: {principal_type}")
                console.print(f"  Account ID: {account_id}")
                console.print()
                console.print("[yellow]Troubleshooting:[/yellow]")
                console.print("• The assignment may have already been revoked")
                console.print("• The assignment may never have existed")
                console.print("• Use 'awsideman assignment list' to see all available assignments")
            else:
                console.print(
                    f"[red]✗ Assignment revocation failed ({error_code}): {error_message}[/red]"
                )
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set ARN: {permission_set_arn}")
                console.print(f"  Principal ID: {principal_id}")
                console.print(f"  Principal Type: {principal_type}")
                console.print(f"  Account ID: {account_id}")
                console.print()

                if error_code == "AccessDeniedException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• You do not have sufficient permissions to revoke assignments")
                    console.print(
                        "• Ensure your AWS credentials have the necessary SSO Admin permissions"
                    )
                    console.print(
                        "• Required permissions: sso:DeleteAccountAssignment, sso:ListAccountAssignments"
                    )
                elif error_code == "ValidationException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• Check that the permission set ARN is valid and exists")
                    console.print("• Verify that the principal ID exists in the identity store")
                    console.print("• Ensure the account ID is a valid 12-digit AWS account number")
                    console.print(
                        "• Confirm the principal type matches the actual principal (USER or GROUP)"
                    )
                elif error_code == "ConflictException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• There may be a conflicting assignment operation in progress")
                    console.print("• Wait a few moments and try again")
                    console.print(
                        "• Check if the assignment is currently being created or modified"
                    )
                else:
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print(
                        "• This could be due to an issue with the AWS Identity Center service"
                    )
                    console.print("• Check AWS service health status")
                    console.print("• Verify your AWS region configuration")

            raise typer.Exit(1)
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]✗ Assignment revocation failed: {str(e)}[/red]")
            console.print()
            console.print("[bold]Attempted Revocation:[/bold]")
            console.print(f"  Permission Set ARN: {permission_set_arn}")
            console.print(f"  Principal ID: {principal_id}")
            console.print(f"  Principal Type: {principal_type}")
            console.print(f"  Account ID: {account_id}")
            console.print()
            console.print(
                "[yellow]This could be due to an unexpected error. Please try again or contact support.[/yellow]"
            )
            raise typer.Exit(1)
