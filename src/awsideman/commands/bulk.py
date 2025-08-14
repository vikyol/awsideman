"""Bulk operations commands for awsideman.

This module provides commands for performing bulk permission set assignments using input files
with human-readable names. Names are automatically resolved to AWS resource identifiers using
Identity Store, SSO Admin, and Organizations APIs.

Features:
    - Support for CSV and JSON input formats
    - Automatic name resolution with caching for performance
    - Preview mode with user confirmation
    - Dry-run validation without making changes
    - Batch processing with configurable parallelism
    - Comprehensive error handling and reporting
    - Progress tracking with Rich terminal output

Commands:
    assign: Bulk assign permission sets from input file
    revoke: Bulk revoke permission sets from input file

File Format Requirements:
    CSV: principal_name,permission_set_name,account_name,principal_type
    JSON: {"assignments": [{"principal_name": "...", "permission_set_name": "...", "account_name": "...", "principal_type": "..."}]}

Name Resolution:
    - Principal names → Principal IDs (via Identity Store API)
    - Permission set names → Permission set ARNs (via SSO Admin API)
    - Account names → Account IDs (via Organizations API)
    - Results are cached for performance optimization

Examples:
    # Basic bulk assign from CSV with human-readable names
    $ awsideman bulk assign user-assignments.csv

    # Validate and preview without making changes
    $ awsideman bulk assign assignments.csv --dry-run

    # Bulk revoke with force option to skip confirmations
    $ awsideman bulk revoke assignments.json --force

    # Custom batch size for rate-limited environments
    $ awsideman bulk assign assignments.csv --batch-size 5

    # Use specific AWS profile
    $ awsideman bulk assign assignments.csv --profile production

Troubleshooting:
    - Names are case-sensitive and must match exactly
    - Ensure AWS credentials have Identity Store, SSO Admin, and Organizations access
    - Use smaller batch sizes if encountering AWS API rate limits
    - Check profile configuration if name resolution fails
"""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from ..utils.validators import validate_profile, validate_sso_instance

app = typer.Typer(
    help="""Perform bulk operations for permission set assignments.

Supports CSV and JSON input formats for efficient management of multiple assignments.
Uses human-readable names that are automatically resolved to AWS resource identifiers.

File Format Requirements:
  CSV: principal_name,permission_set_name,account_name,principal_type
  JSON: {"assignments": [{"principal_name": "...", "permission_set_name": "...", "account_name": "...", "principal_type": "..."}]}

Common Issues:
  - Names are case-sensitive and must match exactly
  - Ensure AWS credentials have Identity Store, SSO Admin, and Organizations access
  - Use smaller batch sizes if encountering rate limits
  - Check profile configuration if name resolution fails

Examples:
  awsideman bulk assign assignments.csv
  awsideman bulk assign assignments.json --dry-run
  awsideman bulk revoke assignments.csv --force
"""
)
console = Console()
config = Config()


@app.command("assign")
def bulk_assign(
    input_file: Path = typer.Argument(
        ..., help="Input file (CSV or JSON) with assignment data using human-readable names"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate input and show preview without making changes"
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="Continue processing on individual failures (default: continue)",
    ),
    batch_size: int = typer.Option(
        10, "--batch-size", help="Number of assignments to process in parallel (1-50, default: 10)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile to use (uses default if not specified)"
    ),
):
    """Bulk assign permission sets from input file using human-readable names.

    Processes an input file (CSV or JSON) containing assignment data with human-readable names
    and creates permission set assignments in bulk. Names are automatically resolved to AWS
    resource identifiers using Identity Store, SSO Admin, and Organizations APIs.

    FILE FORMAT REQUIREMENTS:

    CSV Format (required columns):
      principal_name      - User or group name (e.g., "john.doe", "Developers")
      permission_set_name - Permission set name (e.g., "ReadOnlyAccess")
      account_name        - AWS account name (e.g., "Production")
      principal_type      - "USER" or "GROUP" (optional, defaults to "USER")

    JSON Format:
      {
        "assignments": [
          {
            "principal_name": "john.doe",
            "permission_set_name": "ReadOnlyAccess",
            "account_name": "Production",
            "principal_type": "USER"
          }
        ]
      }

    EXAMPLES:

      # Basic bulk assign from CSV with human-readable names
      $ awsideman bulk assign user-assignments.csv

      # Validate input and preview changes without applying them
      $ awsideman bulk assign assignments.csv --dry-run

      # Use specific AWS profile
      $ awsideman bulk assign assignments.csv --profile production

      # Process with smaller batch size for rate-limited environments
      $ awsideman bulk assign assignments.csv --batch-size 5

      # Stop processing on first error instead of continuing
      $ awsideman bulk assign assignments.csv --stop-on-error

      # Process JSON format file
      $ awsideman bulk assign assignments.json

    TROUBLESHOOTING:

      Name Resolution Errors:
        - Verify names match exactly (case-sensitive)
        - Check AWS credentials have required permissions
        - Ensure profile is configured for correct organization

      Rate Limiting:
        - Reduce batch size (--batch-size 5)
        - Check AWS service quotas

      Permission Errors:
        - Verify Identity Store read access
        - Verify SSO Admin read/write access
        - Verify Organizations read access
    """
    try:
        # Import bulk utilities
        from ..bulk import (
            BatchProcessor,
            FileFormatDetector,
            PreviewGenerator,
            ReportGenerator,
            ResourceResolver,
        )

        # Validate input parameters
        if batch_size <= 0:
            console.print("[red]Error: Batch size must be a positive integer.[/red]")
            raise typer.Exit(1)

        # Check if input file exists
        if not input_file.exists():
            console.print(f"[red]Error: Input file not found: {input_file}[/red]")
            raise typer.Exit(1)

        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Create AWS client manager
        aws_client = AWSClientManager(profile_name)

        console.print(f"[blue]Starting bulk assign operation for: {input_file}[/blue]")
        console.print(f"[dim]Profile: {profile_name}[/dim]")
        console.print(f"[dim]Dry run: {dry_run}[/dim]")
        console.print(f"[dim]Continue on error: {continue_on_error}[/dim]")
        console.print(f"[dim]Batch size: {batch_size}[/dim]")
        console.print()

        # Step 1: Process input file
        console.print("[blue]Step 1: Processing input file...[/blue]")

        try:
            # Detect file format and get appropriate processor
            processor = FileFormatDetector.get_processor(input_file)
            console.print(
                f"[green]✓ Detected file format: {FileFormatDetector.detect_format(input_file).upper()}[/green]"
            )

            # Validate file format
            validation_errors = processor.validate_format()
            if validation_errors:
                console.print("[red]✗ File validation failed:[/red]")
                for error in validation_errors:
                    if error.line_number:
                        console.print(f"  [red]Line {error.line_number}: {error.message}[/red]")
                    else:
                        console.print(f"  [red]{error.message}[/red]")
                raise typer.Exit(1)

            # Parse assignments from file
            assignments = processor.parse_assignments()
            console.print(f"[green]✓ Successfully parsed {len(assignments)} assignments[/green]")

        except ValueError as e:
            console.print(f"[red]✗ File processing error: {str(e)}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]✗ Unexpected error processing file: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 2: Resolve names to IDs/ARNs
        console.print("\n[blue]Step 2: Resolving names to AWS resource identifiers...[/blue]")

        try:
            # Create resource resolver
            resolver = ResourceResolver(aws_client, instance_arn, identity_store_id)

            # Pre-warm cache for better performance
            console.print("[dim]Pre-warming resolution cache...[/dim]")
            resolver.warm_cache_for_assignments(assignments)

            # Resolve all assignments
            resolved_assignments = []
            with console.status("[blue]Resolving names...[/blue]"):
                for assignment in assignments:
                    resolved_assignment = resolver.resolve_assignment(assignment)
                    resolved_assignments.append(resolved_assignment)

            # Count resolution results
            successful_resolutions = sum(
                1 for a in resolved_assignments if a.get("resolution_success", False)
            )
            failed_resolutions = len(resolved_assignments) - successful_resolutions

            console.print(
                f"[green]✓ Successfully resolved {successful_resolutions} assignments[/green]"
            )
            if failed_resolutions > 0:
                console.print(
                    f"[yellow]⚠ {failed_resolutions} assignments had resolution errors[/yellow]"
                )

        except Exception as e:
            console.print(f"[red]✗ Error during name resolution: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 3: Generate and display preview
        console.print("\n[blue]Step 3: Generating preview...[/blue]")

        try:
            # Filter out assignments with resolution errors early
            valid_assignments = [
                a for a in resolved_assignments if a.get("resolution_success", False)
            ]

            # Create preview generator
            preview_generator = PreviewGenerator(console)

            # Generate preview report
            preview_summary = preview_generator.generate_preview_report(
                resolved_assignments, "assign"
            )

            # Handle dry-run mode
            if dry_run:
                preview_generator.display_dry_run_message("assign", preview_summary)
                console.print("\n[green]Dry-run completed successfully![/green]")
                raise typer.Exit(0)

            # Check if there are valid assignments before showing confirmation
            if not valid_assignments:
                console.print("[red]✗ No valid assignments to process[/red]")
                console.print("[yellow]Fix the resolution errors above and try again.[/yellow]")
                raise typer.Exit(1)

            # Get user confirmation to proceed
            if not preview_generator.prompt_user_confirmation("assign", preview_summary):
                preview_generator.display_cancellation_message("assign")
                raise typer.Exit(0)

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]✗ Error generating preview: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 4: Execute bulk assignment operation
        console.print("\n[blue]Step 4: Executing bulk assignment operation...[/blue]")

        try:
            # Display operation summary
            preview_generator.display_operation_summary(
                "assign",
                len(resolved_assignments),
                len(valid_assignments),
                len(resolved_assignments) - len(valid_assignments),
            )

            # Create batch processor
            batch_processor = BatchProcessor(aws_client, batch_size)

            # Process assignments
            results = asyncio.run(
                batch_processor.process_assignments(
                    valid_assignments,
                    "assign",
                    instance_arn,
                    dry_run=False,
                    continue_on_error=continue_on_error,
                )
            )

        except Exception as e:
            console.print(f"[red]✗ Error during batch processing: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 5: Generate and display results
        console.print("\n[blue]Step 5: Generating results report...[/blue]")

        try:
            # Create report generator
            report_generator = ReportGenerator(console)

            # Generate summary report
            report_generator.generate_summary_report(results, "assign")

            # Generate error summary if there were failures
            if results.failed:
                report_generator.generate_error_summary(results)

            # Generate performance report
            report_generator.generate_performance_report(results)

            # Generate detailed report for failed assignments
            if results.failed:
                console.print("\n[yellow]Detailed information for failed assignments:[/yellow]")
                report_generator.generate_detailed_report(
                    results, show_successful=False, show_failed=True, show_skipped=False
                )

        except Exception as e:
            console.print(f"[red]✗ Error generating reports: {str(e)}[/red]")
            raise typer.Exit(1)

        # Final status
        if results.failure_count == 0:
            console.print("\n[green]🎉 Bulk assign operation completed successfully![/green]")
            console.print(f"[green]All {results.success_count} assignments were created.[/green]")
        elif results.success_count > 0:
            console.print(
                "\n[yellow]⚠ Bulk assign operation completed with some failures.[/yellow]"
            )
            console.print(
                f"[green]{results.success_count} assignments succeeded[/green], [red]{results.failure_count} failed[/red]"
            )
        else:
            console.print("\n[red]❌ Bulk assign operation failed.[/red]")
            console.print("[red]No assignments were created successfully.[/red]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[red]Unexpected error in bulk assign operation: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("revoke")
def bulk_revoke(
    input_file: Path = typer.Argument(
        ..., help="Input file (CSV or JSON) with assignment data using human-readable names"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate input and show preview without making changes"
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="Continue processing on individual failures (default: continue)",
    ),
    batch_size: int = typer.Option(
        10, "--batch-size", help="Number of assignments to process in parallel (1-50, default: 10)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompts and proceed automatically"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile to use (uses default if not specified)"
    ),
):
    """Bulk revoke permission sets from input file using human-readable names.

    Processes an input file (CSV or JSON) containing assignment data with human-readable names
    and revokes permission set assignments in bulk. Names are automatically resolved to AWS
    resource identifiers using Identity Store, SSO Admin, and Organizations APIs.

    FILE FORMAT REQUIREMENTS:

    CSV Format (required columns):
      principal_name      - User or group name (e.g., "john.doe", "Developers")
      permission_set_name - Permission set name (e.g., "ReadOnlyAccess")
      account_name        - AWS account name (e.g., "Production")
      principal_type      - "USER" or "GROUP" (optional, defaults to "USER")

    JSON Format:
      {
        "assignments": [
          {
            "principal_name": "john.doe",
            "permission_set_name": "ReadOnlyAccess",
            "account_name": "Production",
            "principal_type": "USER"
          }
        ]
      }

    EXAMPLES:

      # Basic bulk revoke from CSV with human-readable names
      $ awsideman bulk revoke user-assignments.csv

      # Validate input and preview changes without applying them
      $ awsideman bulk revoke assignments.csv --dry-run

      # Skip confirmation prompts for automated workflows
      $ awsideman bulk revoke assignments.csv --force

      # Use specific AWS profile
      $ awsideman bulk revoke assignments.csv --profile production

      # Process with smaller batch size for rate-limited environments
      $ awsideman bulk revoke assignments.csv --batch-size 5

      # Stop processing on first error instead of continuing
      $ awsideman bulk revoke assignments.csv --stop-on-error

      # Process JSON format file
      $ awsideman bulk revoke assignments.json

    TROUBLESHOOTING:

      Name Resolution Errors:
        - Verify names match exactly (case-sensitive)
        - Check AWS credentials have required permissions
        - Ensure profile is configured for correct organization

      Assignment Not Found:
        - Assignment may already be revoked
        - Verify assignment exists in target account
        - Check principal has access to the account

      Rate Limiting:
        - Reduce batch size (--batch-size 5)
        - Check AWS service quotas

      Permission Errors:
        - Verify Identity Store read access
        - Verify SSO Admin read/write access
        - Verify Organizations read access
    """
    try:
        # Import bulk utilities
        from ..bulk import (
            BatchProcessor,
            FileFormatDetector,
            PreviewGenerator,
            ReportGenerator,
            ResourceResolver,
        )

        # Validate input parameters
        if batch_size <= 0:
            console.print("[red]Error: Batch size must be a positive integer.[/red]")
            raise typer.Exit(1)

        # Check if input file exists
        if not input_file.exists():
            console.print(f"[red]Error: Input file not found: {input_file}[/red]")
            raise typer.Exit(1)

        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Create AWS client manager
        aws_client = AWSClientManager(profile_name)

        console.print(f"[blue]Starting bulk revoke operation for: {input_file}[/blue]")
        console.print(f"[dim]Profile: {profile_name}[/dim]")
        console.print(f"[dim]Dry run: {dry_run}[/dim]")
        console.print(f"[dim]Continue on error: {continue_on_error}[/dim]")
        console.print(f"[dim]Batch size: {batch_size}[/dim]")
        console.print(f"[dim]Force: {force}[/dim]")
        console.print()

        # Step 1: Process input file
        console.print("[blue]Step 1: Processing input file...[/blue]")

        try:
            # Detect file format and get appropriate processor
            processor = FileFormatDetector.get_processor(input_file)
            console.print(
                f"[green]✓ Detected file format: {FileFormatDetector.detect_format(input_file).upper()}[/green]"
            )

            # Validate file format
            validation_errors = processor.validate_format()
            if validation_errors:
                console.print("[red]✗ File validation failed:[/red]")
                for error in validation_errors:
                    if error.line_number:
                        console.print(f"  [red]Line {error.line_number}: {error.message}[/red]")
                    else:
                        console.print(f"  [red]{error.message}[/red]")
                raise typer.Exit(1)

            # Parse assignments from file
            assignments = processor.parse_assignments()
            console.print(f"[green]✓ Successfully parsed {len(assignments)} assignments[/green]")

        except ValueError as e:
            console.print(f"[red]✗ File processing error: {str(e)}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]✗ Unexpected error processing file: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 2: Resolve names to IDs/ARNs
        console.print("\n[blue]Step 2: Resolving names to AWS resource identifiers...[/blue]")

        try:
            # Create resource resolver
            resolver = ResourceResolver(aws_client, instance_arn, identity_store_id)

            # Pre-warm cache for better performance
            console.print("[dim]Pre-warming resolution cache...[/dim]")
            resolver.warm_cache_for_assignments(assignments)

            # Resolve all assignments
            resolved_assignments = []
            with console.status("[blue]Resolving names...[/blue]"):
                for assignment in assignments:
                    resolved_assignment = resolver.resolve_assignment(assignment)
                    resolved_assignments.append(resolved_assignment)

            # Count resolution results
            successful_resolutions = sum(
                1 for a in resolved_assignments if a.get("resolution_success", False)
            )
            failed_resolutions = len(resolved_assignments) - successful_resolutions

            console.print(
                f"[green]✓ Successfully resolved {successful_resolutions} assignments[/green]"
            )
            if failed_resolutions > 0:
                console.print(
                    f"[yellow]⚠ {failed_resolutions} assignments had resolution errors[/yellow]"
                )

        except Exception as e:
            console.print(f"[red]✗ Error during name resolution: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 3: Generate and display preview
        console.print("\n[blue]Step 3: Generating preview...[/blue]")

        try:
            # Filter out assignments with resolution errors early
            valid_assignments = [
                a for a in resolved_assignments if a.get("resolution_success", False)
            ]

            # Create preview generator
            preview_generator = PreviewGenerator(console)

            # Generate preview report
            preview_summary = preview_generator.generate_preview_report(
                resolved_assignments, "revoke"
            )

            # Handle dry-run mode
            if dry_run:
                preview_generator.display_dry_run_message("revoke", preview_summary)
                console.print("\n[green]Dry-run completed successfully![/green]")
                raise typer.Exit(0)

            # Check if there are valid assignments before showing confirmation
            if not valid_assignments:
                console.print("[red]✗ No valid assignments to process[/red]")
                console.print("[yellow]Fix the resolution errors above and try again.[/yellow]")
                raise typer.Exit(1)

            # Get user confirmation to proceed (with force option)
            if not preview_generator.prompt_user_confirmation(
                "revoke", preview_summary, force=force
            ):
                preview_generator.display_cancellation_message("revoke")
                raise typer.Exit(0)

        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]✗ Error generating preview: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 4: Execute bulk revoke operation
        console.print("\n[blue]Step 4: Executing bulk revoke operation...[/blue]")

        try:
            # Display operation summary
            preview_generator.display_operation_summary(
                "revoke",
                len(resolved_assignments),
                len(valid_assignments),
                len(resolved_assignments) - len(valid_assignments),
            )

            # Create batch processor
            batch_processor = BatchProcessor(aws_client, batch_size)

            # Process assignments
            results = asyncio.run(
                batch_processor.process_assignments(
                    valid_assignments,
                    "revoke",
                    instance_arn,
                    dry_run=False,
                    continue_on_error=continue_on_error,
                )
            )

        except Exception as e:
            console.print(f"[red]✗ Error during batch processing: {str(e)}[/red]")
            raise typer.Exit(1)

        # Step 5: Generate and display results
        console.print("\n[blue]Step 5: Generating results report...[/blue]")

        try:
            # Create report generator
            report_generator = ReportGenerator(console)

            # Generate summary report
            report_generator.generate_summary_report(results, "revoke")

            # Generate error summary if there were failures
            if results.failed:
                report_generator.generate_error_summary(results)

            # Generate performance report
            report_generator.generate_performance_report(results)

            # Generate detailed report for failed assignments
            if results.failed:
                console.print("\n[yellow]Detailed information for failed assignments:[/yellow]")
                report_generator.generate_detailed_report(
                    results, show_successful=False, show_failed=True, show_skipped=False
                )

        except Exception as e:
            console.print(f"[red]✗ Error generating reports: {str(e)}[/red]")
            raise typer.Exit(1)

        # Final status
        if results.failure_count == 0:
            console.print("\n[green]🎉 Bulk revoke operation completed successfully![/green]")
            console.print(f"[green]All {results.success_count} assignments were revoked.[/green]")
        elif results.success_count > 0:
            console.print(
                "\n[yellow]⚠ Bulk revoke operation completed with some failures.[/yellow]"
            )
            console.print(
                f"[green]{results.success_count} assignments succeeded[/green], [red]{results.failure_count} failed[/red]"
            )
        else:
            console.print("\n[red]❌ Bulk revoke operation failed.[/red]")
            console.print("[red]No assignments were revoked successfully.[/red]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[red]Unexpected error in bulk revoke operation: {str(e)}[/red]")
        raise typer.Exit(1)
