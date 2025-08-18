"""List templates command for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def list_templates(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed template information"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """List all available templates.

    Shows a list of all templates stored in the template directory with basic metadata.
    Use --verbose for detailed information about each template.

    Examples:
        # List all templates
        $ awsideman templates list

        # List with detailed information
        $ awsideman templates list --verbose

        # List using a specific AWS profile
        $ awsideman templates list --profile dev-account
    """
    try:
        # Load configuration
        config = Config()

        # Initialize template storage manager
        storage_manager = TemplateStorageManager(config=config)

        # Get template list
        templates = storage_manager.list_templates()

        if not templates:
            console.print("[yellow]No templates found.[/yellow]")
            console.print(f"[blue]Template directory: {storage_manager.templates_dir}[/blue]")
            console.print(
                "[blue]Use 'awsideman templates create' to create your first template.[/blue]"
            )
            return

        # Display template count and storage info
        console.print(f"[blue]Found {len(templates)} template(s)[/blue]")
        console.print(f"[blue]Storage directory: {storage_manager.templates_dir}[/blue]")

        if verbose:
            # Detailed view with individual template information
            for i, template_info in enumerate(templates, 1):
                console.print(f"\n[bold]Template {i}: {template_info.name}[/bold]")

                # Create detailed table for each template
                info_table = Table(show_header=False, box=None)
                info_table.add_column("Property", style="bold blue")
                info_table.add_column("Value")

                info_table.add_row("File", str(template_info.file_path))
                if template_info.metadata.description:
                    info_table.add_row("Description", template_info.metadata.description)
                if template_info.metadata.author:
                    info_table.add_row("Author", template_info.metadata.author)
                if template_info.metadata.version:
                    info_table.add_row("Version", template_info.metadata.version)
                if template_info.metadata.created_at:
                    info_table.add_row(
                        "Created", template_info.metadata.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    )
                if template_info.metadata.updated_at:
                    info_table.add_row(
                        "Updated", template_info.metadata.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                    )
                if template_info.last_modified:
                    info_table.add_row(
                        "Last Modified", template_info.last_modified.strftime("%Y-%m-%d %H:%M:%S")
                    )

                info_table.add_row("Assignments", str(template_info.assignment_count))
                info_table.add_row("Entities", str(template_info.entity_count))
                info_table.add_row("Permission Sets", str(template_info.permission_set_count))

                console.print(info_table)

                # Show tags if available
                if hasattr(template_info.metadata, "tags") and template_info.metadata.tags:
                    tags_str = ", ".join(
                        [f"{k}={v}" for k, v in template_info.metadata.tags.items()]
                    )
                    console.print(f"[blue]Tags: {tags_str}[/blue]")

                if i < len(templates):
                    console.print("─" * 50)
        else:
            # Summary view with all templates in a table
            summary_table = Table(show_header=True, header_style="bold magenta")
            summary_table.add_column("Name")
            summary_table.add_column("Description")
            summary_table.add_column("Author")
            summary_table.add_column("Version")
            summary_table.add_column("Assignments")
            summary_table.add_column("Entities")
            summary_table.add_column("Permission Sets")
            summary_table.add_column("Last Modified")

            for template_info in templates:
                description = template_info.metadata.description or "-"
                author = template_info.metadata.author or "-"
                version = template_info.metadata.version or "-"
                last_modified = (
                    template_info.last_modified.strftime("%Y-%m-%d")
                    if template_info.last_modified
                    else "-"
                )

                summary_table.add_row(
                    template_info.name,
                    description,
                    author,
                    version,
                    str(template_info.assignment_count),
                    str(template_info.entity_count),
                    str(template_info.permission_set_count),
                    last_modified,
                )

            console.print(summary_table)

        # Show storage statistics
        try:
            stats = storage_manager.get_storage_stats()
            console.print("\n[blue]Storage Statistics:[/blue]")
            stats_table = Table(show_header=False, box=None)
            stats_table.add_column("Metric", style="bold blue")
            stats_table.add_column("Value")

            stats_table.add_row("Total Templates", str(stats["total_templates"]))
            stats_table.add_row("Total Assignments", str(stats["total_assignments"]))
            stats_table.add_row("Total Entities", str(stats["total_entities"]))
            stats_table.add_row("Total Permission Sets", str(stats["total_permission_sets"]))
            stats_table.add_row("Total Size", f"{stats['total_size_bytes']} bytes")

            console.print(stats_table)
        except Exception as e:
            console.print(f"[yellow]Could not retrieve storage statistics: {e}[/yellow]")

    except Exception as e:
        console.print(f"[red]Error listing templates: {e}[/red]")
        raise typer.Exit(1)
