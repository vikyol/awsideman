"""Show template command for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def show_template(
    template_name: str = typer.Argument(..., help="Name of the template to show"),
    format: str = typer.Option("yaml", "--format", "-f", help="Output format: yaml, json, or raw"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Show the full contents of a template.

    Displays the complete template content including metadata, assignments, and all configuration.
    The template can be displayed in different formats for easy reading or processing.

    Examples:
        # Show template in YAML format
        $ awsideman templates show developer-access

        # Show template in JSON format
        $ awsideman templates show admin-access --format json

        # Show template using a specific AWS profile
        $ awsideman templates show custom-template --profile dev-account
    """
    try:
        # Load configuration
        config = Config()

        # Initialize template storage manager
        storage_manager = TemplateStorageManager(config=config)

        # Get template by name
        template = storage_manager.get_template(template_name)

        if not template:
            console.print(f"[red]Error: Template '{template_name}' not found.[/red]")

            # Try to find similar templates
            all_templates = storage_manager.list_templates()
            if all_templates:
                console.print("\n[blue]Available templates:[/blue]")
                for template_info in all_templates:
                    console.print(f"  • {template_info.name}")
                console.print("\n[blue]Use 'awsideman templates list' to see all templates.[/blue]")
            else:
                console.print(
                    f"\n[blue]No templates found in {storage_manager.templates_dir}[/blue]"
                )
                console.print(
                    "[blue]Use 'awsideman templates create' to create your first template.[/blue]"
                )

            raise typer.Exit(1)

        # Display template header
        console.print(f"\n[bold]Template: {template.metadata.name}[/bold]")
        console.print("=" * 60)

        # Show metadata
        console.print("\n[bold blue]Metadata:[/bold blue]")
        metadata_table = Table(show_header=False, box=None)
        metadata_table.add_column("Property", style="bold blue", width=20)
        metadata_table.add_column("Value")

        metadata_table.add_row("Name", template.metadata.name)
        if template.metadata.description:
            metadata_table.add_row("Description", template.metadata.description)
        if template.metadata.author:
            metadata_table.add_row("Author", template.metadata.author)
        if template.metadata.version:
            metadata_table.add_row("Version", template.metadata.version)
        if template.metadata.created_at:
            metadata_table.add_row(
                "Created", template.metadata.created_at.strftime("%Y-%m-%d %H:%M:%S")
            )
        if template.metadata.updated_at:
            metadata_table.add_row(
                "Updated", template.metadata.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            )

        # Add tags if available
        if hasattr(template.metadata, "tags") and template.metadata.tags:
            tags_str = ", ".join([f"{k}={v}" for k, v in template.metadata.tags.items()])
            metadata_table.add_row("Tags", tags_str)

        console.print(metadata_table)

        # Show summary statistics
        console.print("\n[bold blue]Summary:[/bold blue]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Metric", style="bold blue", width=20)
        summary_table.add_column("Value")

        summary_table.add_row("Assignments", str(len(template.assignments)))
        summary_table.add_row("Total Entities", str(template.get_entity_count()))
        summary_table.add_row("Total Permission Sets", str(template.get_permission_set_count()))
        total_assignments = template.get_total_assignments()
        assignments_display = (
            str(total_assignments) if total_assignments >= 0 else "Variable (tag-based targeting)"
        )
        summary_table.add_row("Total Assignments", assignments_display)

        console.print(summary_table)

        # Show assignments
        console.print("\n[bold blue]Assignments:[/bold blue]")

        for i, assignment in enumerate(template.assignments, 1):
            console.print(f"\n[bold]Assignment {i}:[/bold]")

            # Entities
            console.print(f"  [blue]Entities ({len(assignment.entities)}):[/blue]")
            for entity in assignment.entities:
                console.print(f"    • {entity}")

            # Permission Sets
            console.print(f"  [blue]Permission Sets ({len(assignment.permission_sets)}):[/blue]")
            for ps in assignment.permission_sets:
                console.print(f"    • {ps}")

            # Targets
            console.print("  [blue]Targets:[/blue]")
            if assignment.targets.account_ids:
                console.print(f"    Account IDs: {', '.join(assignment.targets.account_ids)}")
            if assignment.targets.account_tags:
                tags_str = ", ".join(
                    [f"{k}={v}" for k, v in assignment.targets.account_tags.items()]
                )
                console.print(f"    Account Tags: {tags_str}")
            if assignment.targets.exclude_accounts:
                console.print(
                    f"    Exclude Accounts: {', '.join(assignment.targets.exclude_accounts)}"
                )

            if i < len(template.assignments):
                console.print("  " + "─" * 40)

        # Show raw content in specified format
        console.print(f"\n[bold blue]Raw Content ({format.upper()}):[/bold blue]")

        if format.lower() == "json":
            import json

            content = json.dumps(template.to_dict(), indent=2)
            syntax = Syntax(content, "json", theme="monokai")
        elif format.lower() == "yaml":
            import yaml

            content = yaml.dump(template.to_dict(), default_flow_style=False, sort_keys=False)
            syntax = Syntax(content, "yaml", theme="monokai")
        else:  # raw
            content = str(template.to_dict())
            syntax = Syntax(content, "text", theme="monokai")

        console.print(
            Panel(syntax, title=f"Template: {template.metadata.name}", border_style="blue")
        )

        # Show file information
        try:
            template_path = storage_manager.get_template_path(template_name)
            if template_path and template_path.exists():
                console.print(f"\n[blue]File: {template_path}[/blue]")
                console.print(f"[blue]Size: {template_path.stat().st_size} bytes[/blue]")
        except Exception:
            pass

    except Exception as e:
        console.print(f"[red]Error showing template: {e}[/red]")
        raise typer.Exit(1)
