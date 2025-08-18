"""Preview template command for awsideman."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...templates.executor import TemplateExecutor
from ...templates.models import Template
from ...templates.parser import TemplateParser
from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def preview_template(
    template_file: Path = typer.Argument(
        ..., help="Path to the template file or template name to preview"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, or summary"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Preview what a template would do without executing it.

    Shows a detailed preview of what would happen if the template were applied,
    including all assignments that would be created, skipped, or failed.

    Examples:
        # Preview template execution
        $ awsideman templates preview ./templates/developer-access.yaml

        # Preview with JSON output
        $ awsideman templates preview ./templates/admin-access.yaml --format json

        # Preview using a specific AWS profile
        $ awsideman templates preview ./templates/custom.yaml --profile dev-account
    """
    try:
        # Load configuration
        config = Config()

        # Resolve template: file path or stored template name
        parser = TemplateParser()
        template: Template
        if template_file.exists() and template_file.is_file():
            console.print(f"[blue]Parsing template file: {template_file}[/blue]")
            try:
                template = parser.parse_file(template_file)
                console.print("[green]✓ Template file parsed successfully[/green]")
            except Exception as e:
                console.print(f"[red]Error parsing template file: {e}[/red]")
                raise typer.Exit(1)
        else:
            # Try to load by template name from storage
            storage_manager = TemplateStorageManager(config=config)
            template_name = str(template_file)
            console.print(Panel(f"Looking for template: {template_name}", title="Finding Template"))
            loaded = storage_manager.get_template(template_name)
            if not loaded:
                console.print(f"[red]Error: Template '{template_name}' not found.[/red]")
                console.print(
                    "[blue]Use 'awsideman templates list' to see available templates.[/blue]"
                )
                raise typer.Exit(1)
            template = loaded
            console.print(Panel(f"Template '{template_name}' found", title="Template Found"))

        # Display template information
        console.print(f"\n[bold]Template: {template.metadata.name}[/bold]")
        if template.metadata.description:
            console.print(f"Description: {template.metadata.description}")
        if template.metadata.author:
            console.print(f"Author: {template.metadata.author}")
        if template.metadata.version:
            console.print(f"Version: {template.metadata.version}")

        # Initialize AWS client manager
        try:
            # Validate profile and get region from config (use default if not provided)
            from ...utils.validators import validate_profile

            profile_name, profile_data = validate_profile(profile)
            region = profile_data.get("region")

            aws_client = AWSClientManager(profile=profile_name, region=region)

            # Get SSO instance information
            sso_client = aws_client.get_identity_center_client()
            instances = sso_client.list_instances()

            if not instances.get("Instances"):
                console.print(
                    "[red]Error: No SSO instances found. Cannot preview template execution.[/red]"
                )
                raise typer.Exit(1)

            instance = instances["Instances"][0]
            instance_arn = instance["InstanceArn"]
            identity_store_id = instance["IdentityStoreId"]

            console.print(f"[blue]Using SSO instance: {instance_arn}[/blue]")

            # Initialize executor for preview
            executor = TemplateExecutor(
                client_manager=aws_client,
                instance_arn=instance_arn,
                identity_store_id=identity_store_id,
            )

            # Generate preview
            console.print("\n[blue]Generating execution preview...[/blue]")
            preview_result = executor.preview_template(template)

            # Display preview results
            if output_format == "json":
                console.print("\n[bold]Preview Result (JSON):[/bold]")
                console.print(
                    Panel(str(preview_result.to_dict()), title="Preview Data", border_style="blue")
                )
            elif output_format == "summary":
                console.print("\n[bold]Preview Summary:[/bold]")
                summary = preview_result.get_summary()
                console.print(f"Template: {summary['template_name']}")
                console.print(f"Total assignments: {summary['total_assignments']}")
                console.print(f"Resolved accounts: {summary['resolved_accounts']}")
                console.print(f"Entities: {summary['entities']}")
                console.print(f"Permission sets: {summary['permission_sets']}")
            else:  # table format (default)
                console.print("\n[bold]Execution Preview:[/bold]")

                # Show account resolution
                if preview_result.resolved_accounts:
                    console.print(
                        f"\n[blue]Target Accounts ({len(preview_result.resolved_accounts)}):[/blue]"
                    )
                    account_table = Table(show_header=True, header_style="bold magenta")
                    account_table.add_column("Account ID")
                    account_table.add_column("Status")

                    for account_id in preview_result.resolved_accounts:
                        account_table.add_row(account_id, "Active")
                    console.print(account_table)

                # Show entity details
                if preview_result.entity_details:
                    console.print(
                        f"\n[blue]Entities ({len(preview_result.entity_details)}):[/blue]"
                    )
                    entity_table = Table(show_header=True, header_style="bold magenta")
                    entity_table.add_column("Reference")
                    entity_table.add_column("Status")

                    for entity in preview_result.entity_details:
                        status = (
                            "[green]✓ Found[/green]"
                            if entity.get("exists")
                            else "[red]✗ Not Found[/red]"
                        )
                        entity_table.add_row(entity.get("reference", "Unknown"), status)
                    console.print(entity_table)

                # Show permission set details
                if preview_result.permission_set_details:
                    console.print(
                        f"\n[blue]Permission Sets ({len(preview_result.permission_set_details)}):[/blue]"
                    )
                    ps_table = Table(show_header=True, header_style="bold magenta")
                    ps_table.add_column("Name")
                    ps_table.add_column("Status")

                    for ps in preview_result.permission_set_details:
                        status = (
                            "[green]✓ Found[/green]"
                            if ps.get("exists")
                            else "[red]✗ Not Found[/red]"
                        )
                        ps_table.add_row(ps.get("name", "Unknown"), status)
                    console.print(ps_table)

                # Show assignment breakdown
                console.print("\n[blue]Assignment Breakdown:[/blue]")
                console.print(
                    f"Total assignments to be created: {preview_result.total_assignments}"
                )

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

            console.print("\n[green]✓ Preview generated successfully![/green]")
            console.print("[yellow]Note: This is a preview. No changes have been made.[/yellow]")

        except Exception as e:
            console.print(f"[red]Error generating preview: {e}[/red]")
            console.print("[yellow]Showing basic template information only.[/yellow]")

            # Fallback to basic template display
            console.print("\n[bold]Template Structure:[/bold]")
            console.print(f"Assignments: {len(template.assignments)}")
            console.print(f"Total entities: {template.get_entity_count()}")
            console.print(f"Total permission sets: {template.get_permission_set_count()}")
            console.print(f"Total assignments: {template.get_total_assignments()}")

    except Exception as e:
        console.print(f"[red]Error previewing template: {e}[/red]")
        raise typer.Exit(1)
