"""Validate template command for awsideman."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...templates.errors import TemplateErrorCollector, TemplateErrorHandler
from ...templates.parser import TemplateParser
from ...templates.progress import TemplateProgressBar, TemplateUserFeedback
from ...templates.validator import TemplateValidator

console = Console()


def validate_template(
    template_file: Path = typer.Argument(..., help="Path to the template file to validate"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed validation information"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Validate a template file.

    Validates the structure, entities, permission sets, and accounts in a template file.
    This command performs comprehensive validation to ensure the template is ready for use.

    Examples:
        # Validate a template file
        $ awsideman templates validate ./templates/developer-access.yaml

        # Validate with detailed output
        $ awsideman templates validate ./templates/admin-access.yaml --verbose

        # Validate using a specific AWS profile
        $ awsideman templates validate ./templates/custom.yaml --profile dev-account
    """
    # Initialize error collector and user feedback
    error_collector = TemplateErrorCollector()
    progress_bar = TemplateProgressBar(console)
    user_feedback = TemplateUserFeedback(console)

    try:
        # Check if template file exists
        if not template_file.exists():
            error = TemplateErrorHandler.create_parsing_error(
                "file_not_found", file_path=str(template_file)
            )
            error_collector.add_error(error)
            user_feedback.show_error(
                f"Template file '{template_file}' not found.", "File Not Found"
            )
            raise typer.Exit(1)

        if not template_file.is_file():
            error = TemplateErrorHandler.create_parsing_error(
                "file_not_readable", file_path=str(template_file)
            )
            error_collector.add_error(error)
            user_feedback.show_error(f"'{template_file}' is not a file.", "Invalid File Type")
            raise typer.Exit(1)

        # Parse the template
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

        # Display template information
        user_feedback.show_info(
            f"Template: {template.metadata.name}\n"
            f"Description: {template.metadata.description or 'No description'}\n"
            f"Author: {template.metadata.author or 'Unknown'}\n"
            f"Version: {template.metadata.version or 'Unknown'}\n"
            f"Assignments: {len(template.assignments)}\n"
            f"Total entities: {template.get_entity_count()}\n"
            f"Total permission sets: {template.get_permission_set_count()}\n"
            f"Total assignments: {template.get_total_assignments()}",
            "Template Information",
        )

        # Validate template structure
        user_feedback.show_info("Validating template structure...", "Structure Validation")
        with progress_bar.create_spinner("Validating template structure..."):
            structure_errors = template.validate_structure()

        if structure_errors:
            user_feedback.show_error(
                f"Template structure validation failed with {len(structure_errors)} error(s):",
                "Structure Validation Failed",
            )
            for error_msg in structure_errors:
                error = TemplateErrorHandler.create_validation_error(
                    "missing_required_field", details=error_msg
                )
                error_collector.add_error(error)
                console.print(f"  [red]• {error_msg}[/red]")
        else:
            user_feedback.show_success(
                "Template structure validation passed", "Structure Validation"
            )

        # If structure validation failed, stop here
        if structure_errors:
            raise typer.Exit(1)

        # Initialize AWS client manager for entity validation
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
                warning = TemplateErrorHandler.create_validation_error(
                    "missing_required_field", details="No SSO instance configured for this profile"
                )
                error_collector.add_warning(warning)
                user_feedback.show_warning(
                    "No SSO instance configured for this profile. Entity validation will be limited.",
                    "Limited Validation",
                )
                user_feedback.show_info(
                    "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance.",
                    "Configuration Required",
                )
                instance_arn = None
                identity_store_id = None
            else:
                user_feedback.show_info(
                    f"Using configured SSO instance: {instance_arn}", "SSO Instance"
                )
                user_feedback.show_info(f"Identity Store ID: {identity_store_id}", "Identity Store")

            # Initialize validator
            validator = TemplateValidator(
                client_manager=aws_client,
                instance_arn=instance_arn,
                identity_store_id=identity_store_id,
            )

            # Perform comprehensive validation
            user_feedback.show_info(
                "Validating entities and permission sets...", "Entity Validation"
            )

            total_validation_steps = 3  # entities, permission sets, accounts
            with progress_bar.create_progress(
                "Validating template...", total_validation_steps
            ) as task:
                # Update progress for each validation step
                progress_bar.update_progress(task, 1, "Validating entities...")
                validation_result = validator.validate_template(template)
                progress_bar.update_progress(task, 2, "Validating permission sets...")
                progress_bar.update_progress(task, 3, "Validation complete")

            # Display validation results
            if validation_result.is_valid:
                user_feedback.show_success("Template validation passed!", "Validation Complete")

                if verbose:
                    console.print(
                        f"\n[blue]Resolved entities: {len(validation_result.resolved_entities)}[/blue]"
                    )
                    console.print(
                        f"[blue]Resolved accounts: {len(validation_result.resolved_accounts)}[/blue]"
                    )

                    if validation_result.resolved_entities:
                        console.print("\n[bold]Resolved Entities:[/bold]")
                        entity_table = Table(show_header=True, header_style="bold magenta")
                        entity_table.add_column("Reference")
                        entity_table.add_column("Type")
                        entity_table.add_column("ID")
                        entity_table.add_column("Name")

                        for ref, entity in validation_result.resolved_entities.items():
                            entity_table.add_row(
                                ref, entity.entity_type.value, entity.entity_id, entity.entity_name
                            )
                        console.print(entity_table)

                    if validation_result.resolved_accounts:
                        console.print(
                            f"\n[bold]Resolved Accounts:[/bold] {len(validation_result.resolved_accounts)}"
                        )
                        for account_id in validation_result.resolved_accounts:
                            console.print(f"  • {account_id}")
            else:
                user_feedback.show_error(
                    f"Template validation failed with {len(validation_result.errors)} error(s):",
                    "Validation Failed",
                )

                if validation_result.errors:
                    console.print("\n[red]Errors:[/red]")
                    for error_msg in validation_result.errors:
                        error = TemplateErrorHandler.create_validation_error(
                            "missing_required_field", details=error_msg
                        )
                        error_collector.add_error(error)
                        console.print(f"  [red]• {error_msg}[/red]")

                if validation_result.warnings:
                    console.print("\n[yellow]Warnings:[/yellow]")
                    for warning_msg in validation_result.warnings:
                        warning = TemplateErrorHandler.create_validation_error(
                            "missing_required_field", details=warning_msg
                        )
                        error_collector.add_warning(warning)
                        console.print(f"  [yellow]• {warning_msg}[/yellow]")

                raise typer.Exit(1)

        except Exception as e:
            warning = TemplateErrorHandler.create_validation_error(
                "missing_required_field", details=str(e)
            )
            error_collector.add_warning(warning)
            user_feedback.show_warning(
                f"Could not perform full validation: {e}\n"
                "Template structure is valid, but entity validation was skipped.\n"
                "Use --verbose for more details.",
                "Partial Validation",
            )

        # Display template preview if verbose
        if verbose:
            console.print("\n[bold]Template Content:[/bold]")
            console.print(
                Panel(str(template.to_dict()), title="Template Structure", border_style="blue")
            )

        # Show final summary
        if error_collector.has_errors() or error_collector.has_warnings():
            summary = error_collector.get_error_summary()
            user_feedback.show_warning(
                f"Validation completed with {summary['total_errors']} error(s) and {summary['total_warnings']} warning(s).",
                "Validation Summary",
            )
        else:
            user_feedback.show_success(
                "Template validation completed successfully with no errors or warnings.",
                "Validation Complete",
            )

    except Exception as e:
        if not error_collector.has_errors():
            # Only add generic error if no specific errors were collected
            error = TemplateErrorHandler.create_validation_error(
                "missing_required_field", details=str(e)
            )
            error_collector.add_error(error)

        user_feedback.show_error(f"Error validating template: {e}", "Validation Error")
        raise typer.Exit(1)
