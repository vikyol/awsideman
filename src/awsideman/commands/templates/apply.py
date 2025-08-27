"""Apply template command for awsideman."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...templates.errors import RetryHandler, TemplateErrorCollector, TemplateErrorHandler
from ...templates.executor import TemplateExecutor
from ...templates.parser import TemplateParser
from ...templates.progress import TemplateProgressBar, TemplateUserFeedback
from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def apply_template(
    template_file: Path = typer.Argument(
        ..., help="Path to the template file or template name to apply"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Show what would be done without making changes"
    ),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Apply a template to create permission assignments.

    Executes a template to create permission assignments in AWS Identity Center.
    This command will create all assignments defined in the template for the specified accounts.

    Examples:
        # Apply a template by file path (with confirmation)
        $ awsideman templates apply ./templates/developer-access.yaml

        # Apply a template by name
        $ awsideman templates apply developer-access

        # Dry run to see what would happen
        $ awsideman templates apply admin-access --dry-run

        # Apply without confirmation prompt
        $ awsideman templates apply custom --confirm

        # Apply using a specific AWS profile
        $ awsideman templates apply production --profile prod-account
    """
    # Initialize error collector and user feedback
    error_collector = TemplateErrorCollector()
    progress_bar = TemplateProgressBar(console)
    user_feedback = TemplateUserFeedback(console)
    retry_handler = RetryHandler()

    try:
        # Load configuration
        config = Config()

        # Initialize template storage manager
        storage_manager = TemplateStorageManager(config=config)

        # Determine if input is a file path or template name
        template = None

        # First, try to treat it as a file path
        if template_file.exists() and template_file.is_file():
            user_feedback.show_info(f"Parsing template file: {template_file}", "Parsing Template")
            parser = TemplateParser()

            try:
                with progress_bar.create_spinner("Parsing template file..."):
                    template = parser.parse_file(template_file)
                user_feedback.show_success("Template file parsed successfully", "Parse Complete")
            except Exception as e:
                error = TemplateErrorHandler.create_parsing_error(
                    (
                        "invalid_yaml"
                        if str(template_file).endswith((".yaml", ".yml"))
                        else "invalid_json"
                    ),
                    details=str(e),
                )
                error_collector.add_error(error)
                user_feedback.show_error(f"Error parsing template file: {e}", "Parse Error")
                raise typer.Exit(1)

        # If not a file path, try to find template by name
        else:
            template_name = str(template_file)
            user_feedback.show_info(f"Looking for template: {template_name}", "Finding Template")

            try:
                with progress_bar.create_spinner("Finding template..."):
                    template = storage_manager.get_template(template_name)

                if template:
                    user_feedback.show_success(
                        f"Template '{template_name}' found", "Template Found"
                    )
                else:
                    error = TemplateErrorHandler.create_parsing_error(
                        "template_not_found", template_name=template_name
                    )
                    error_collector.add_error(error)
                    user_feedback.show_error(
                        f"Template '{template_name}' not found.", "Template Not Found"
                    )

                    # Try to find similar templates
                    all_templates = storage_manager.list_templates()
                    if all_templates:
                        user_feedback.show_info("Available templates:", "Available Templates")
                        for template_info in all_templates:
                            user_feedback.show_info(f"  • {template_info.name}", "Template List")
                        user_feedback.show_info(
                            "Use 'awsideman templates list' to see all templates.", "Help"
                        )
                    else:
                        user_feedback.show_info(
                            f"No templates found in {storage_manager.templates_dir}", "No Templates"
                        )
                        user_feedback.show_info(
                            "Use 'awsideman templates create --example' to create your first template.",
                            "Help",
                        )

                    raise typer.Exit(1)

            except Exception as e:
                error = TemplateErrorHandler.create_parsing_error(
                    "template_load_error", template_name=template_name, details=str(e)
                )
                error_collector.add_error(error)
                user_feedback.show_error(
                    f"Error loading template '{template_name}': {e}", "Template Load Error"
                )
                raise typer.Exit(1)

        # Display template information
        total_assignments = template.get_total_assignments()
        assignments_display = (
            str(total_assignments) if total_assignments >= 0 else "Variable (tag-based targeting)"
        )

        user_feedback.show_info(
            f"Template: {template.metadata.name}\n"
            f"Description: {template.metadata.description or 'No description'}\n"
            f"Author: {template.metadata.author or 'Unknown'}\n"
            f"Version: {template.metadata.version or 'Unknown'}\n"
            f"Assignments: {len(template.assignments)}\n"
            f"Total entities: {template.get_entity_count()}\n"
            f"Total permission sets: {template.get_permission_set_count()}\n"
            f"Total assignments: {assignments_display}",
            "Template Information",
        )

        # Initialize AWS client manager
        try:
            # Validate profile and get profile data
            from ...utils.validators import validate_profile

            profile_name, profile_data = validate_profile(profile)

            # Get region from profile data
            region = profile_data.get("region")

            # Create AWS client manager with validated profile
            aws_client = AWSClientManager(profile=profile_name, region=region)

            # CRITICAL FIX: Use profile-specific SSO instance instead of list_instances()
            # This prevents profile mixing and security vulnerabilities

            # Get SSO instance information from profile configuration
            instance_arn = profile_data.get("sso_instance_arn")
            identity_store_id = profile_data.get("identity_store_id")

            if not instance_arn or not identity_store_id:
                error = TemplateErrorHandler.create_configuration_error(
                    "missing_config", config_key="SSO instance"
                )
                error_collector.add_error(error)
                user_feedback.show_error(
                    "No SSO instance configured for this profile. Cannot apply template.",
                    "SSO Instance Not Configured",
                )
                user_feedback.show_info(
                    "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance.",
                    "Configuration Required",
                )
                raise typer.Exit(1)

            user_feedback.show_info(
                f"Using configured SSO instance: {instance_arn}", "SSO Instance"
            )
            user_feedback.show_info(f"Identity Store ID: {identity_store_id}", "Identity Store")

            # Initialize executor
            executor = TemplateExecutor(
                client_manager=aws_client,
                instance_arn=instance_arn,
                identity_store_id=identity_store_id,
            )

            if dry_run:
                # Generate preview for dry run
                user_feedback.show_info(
                    "Generating execution preview (dry run)...", "Dry Run Preview"
                )

                with progress_bar.create_spinner("Generating preview..."):
                    preview_result = executor.preview_template(template)

                user_feedback.show_success("Preview generated successfully", "Preview Complete")

                console.print("\n[bold]Dry Run Results:[/bold]")
                console.print(
                    f"Total assignments that would be created: {preview_result.total_assignments}"
                )
                console.print(f"Target accounts: {len(preview_result.resolved_accounts)}")

                if preview_result.total_assignments > 0:
                    assignment_table = Table(show_header=True, header_style="bold magenta")
                    assignment_table.add_column("Entity")
                    assignment_table.add_column("Permission Set")
                    assignment_table.add_column("Accounts")
                    assignment_table.add_column("Status")

                    for assignment in template.assignments:
                        for entity in assignment.entities:
                            for permission_set in assignment.permission_sets:
                                if assignment.targets.account_ids:
                                    accounts = ", ".join(assignment.targets.account_ids)
                                elif assignment.targets.account_tags:
                                    tags = ", ".join(
                                        [
                                            f"{k}={v}"
                                            for k, v in assignment.targets.account_tags.items()
                                        ]
                                    )
                                    accounts = f"Tag-based: {tags}"
                                else:
                                    accounts = "No targets"

                                assignment_table.add_row(
                                    entity, permission_set, accounts, "[blue]Would Create[/blue]"
                                )
                    console.print(assignment_table)

                user_feedback.show_info(
                    "Dry run completed. No changes were made.", "Dry Run Complete"
                )
                return

            # Pre-resolve to provide accurate confirmation info
            user_feedback.show_info(
                "Analyzing template to determine exact impact...", "Preflight Analysis"
            )
            with progress_bar.create_spinner(
                "Resolving accounts, entities, and permission sets..."
            ):
                preflight = executor.preview_template(template)

            # Show execution summary and ask for confirmation with exact numbers
            total_assignments = preflight.total_assignments
            assignments_text = (
                f"{total_assignments} permission assignments"
                if total_assignments >= 0
                else "permission assignments (exact count depends on account resolution)"
            )
            user_feedback.show_info(
                f"This will create {assignments_text}\n"
                f"across {len(template.assignments)} assignment groups.",
                "Execution Summary",
            )

            if not confirm:
                # Show destructive operation warning with resolved count
                user_feedback.show_destructive_operation_warning(
                    "create permission assignments", total_assignments
                )

                if not user_feedback.show_confirmation_prompt(
                    "Do you want to proceed with applying this template?"
                ):
                    user_feedback.show_info(
                        "Template application cancelled.", "Operation Cancelled"
                    )
                    raise typer.Exit(0)

            # Execute the template
            user_feedback.show_info(
                f"Applying template '{template.metadata.name}'...", "Template Execution"
            )

            # Handle progress bar for tag-based templates
            total_for_progress = template.get_total_assignments()
            if total_for_progress < 0:
                total_for_progress = 1  # Use 1 as a placeholder for indeterminate progress

            with progress_bar.create_progress("Applying template...", total_for_progress):
                # Execute with retry logic
                try:
                    execution_result = retry_handler.execute_with_retry(
                        executor.apply_template, template, dry_run=False
                    )
                except Exception as e:
                    error = TemplateErrorHandler.create_execution_error(
                        "assignment_failed", details=str(e)
                    )
                    error_collector.add_error(error)
                    user_feedback.show_error(f"Template execution failed: {e}", "Execution Failed")
                    raise

            # Display execution results
            user_feedback.show_info("Template execution completed", "Execution Complete")

            summary = execution_result.get_summary()
            console.print("\n[bold]Execution Results:[/bold]")
            console.print(f"Operation ID: {summary['operation_id']}")
            console.print(f"Execution time: {summary['execution_time']:.2f} seconds")
            console.print(f"Total assignments: {summary['total_assignments']}")
            console.print(f"Created: {summary['created']}")
            console.print(f"Skipped: {summary['skipped']}")
            console.print(f"Failed: {summary['failed']}")
            console.print(f"Success rate: {summary['success_rate']:.1%}")

            if execution_result.success:
                user_feedback.show_success("Template applied successfully!", "Success")
            else:
                user_feedback.show_warning(
                    f"Template applied with {summary['failed']} failure(s).", "Partial Success"
                )

            # Show detailed results
            if execution_result.assignments_created:
                console.print(
                    f"\n[green]Created Assignments ({len(execution_result.assignments_created)}):[/green]"
                )
                created_table = Table(show_header=True, header_style="bold green")
                created_table.add_column("Entity")
                created_table.add_column("Permission Set")
                created_table.add_column("Account")
                created_table.add_column("Status")

                for result in execution_result.assignments_created:
                    created_table.add_row(
                        f"{result.entity_type}:{result.entity_name}",
                        result.permission_set_name,
                        f"{result.account_id} ({result.account_name})",
                        "[green]✓ Created[/green]",
                    )
                console.print(created_table)

            if execution_result.assignments_skipped:
                console.print(
                    f"\n[yellow]Skipped Assignments ({len(execution_result.assignments_skipped)}):[/yellow]"
                )
                skipped_table = Table(show_header=True, header_style="bold yellow")
                skipped_table.add_column("Entity")
                skipped_table.add_column("Permission Set")
                skipped_table.add_column("Account")
                skipped_table.add_column("Reason")

                for result in execution_result.assignments_skipped:
                    reason = result.error_message or "Already exists"
                    skipped_table.add_row(
                        f"{result.entity_type}:{result.entity_name}",
                        result.permission_set_name,
                        f"{result.account_id} ({result.account_name})",
                        reason,
                    )
                console.print(skipped_table)

            if execution_result.assignments_failed:
                console.print(
                    f"\n[red]Failed Assignments ({len(execution_result.assignments_failed)}):[/red]"
                )
                failed_table = Table(show_header=True, header_style="bold red")
                failed_table.add_column("Entity")
                failed_table.add_column("Permission Set")
                failed_table.add_column("Account")
                failed_table.add_column("Error")

                for result in execution_result.assignments_failed:
                    error = result.error_message or "Unknown error"
                    failed_table.add_row(
                        f"{result.entity_type}:{result.entity_name}",
                        result.permission_set_name,
                        f"{result.account_id} ({result.account_name})",
                        error,
                    )
                console.print(failed_table)

        except Exception as e:
            error = TemplateErrorHandler.create_execution_error("assignment_failed", details=str(e))
            error_collector.add_error(error)
            user_feedback.show_error(f"Error applying template: {e}", "Execution Error")
            raise typer.Exit(1)

    except Exception as e:
        if not error_collector.has_errors():
            # Only add generic error if no specific errors were collected
            error = TemplateErrorHandler.create_execution_error("assignment_failed", details=str(e))
            error_collector.add_error(error)

        user_feedback.show_error(f"Error applying template: {e}", "Template Error")
        raise typer.Exit(1)
