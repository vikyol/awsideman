"""Delete template command for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm

from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def delete_template(
    name: str = typer.Argument(..., help="Name of the template to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Delete a template file.

    Removes a template from storage after confirmation. This operation cannot
    be undone, so use with caution. The command will prompt for confirmation
    unless the --force flag is used.

    Examples:
        # Delete a template with confirmation
        $ awsideman templates delete my-template

        # Delete without confirmation prompt
        $ awsideman templates delete my-template --force

        # Delete using a specific AWS profile
        $ awsideman templates delete my-template --profile dev-account
    """
    try:
        # Load configuration
        config = Config()

        # Initialize template storage manager
        storage_manager = TemplateStorageManager(config=config)

        # Check if template exists
        if not storage_manager.template_exists(name):
            console.print(f"[red]Error: Template '{name}' not found.[/red]")
            console.print("[blue]Use 'awsideman templates list' to see available templates.[/blue]")
            raise typer.Exit(1)

        # Get template info for confirmation
        template_info = None
        for template in storage_manager.list_templates():
            if template.name == name:
                template_info = template
                break

        if template_info:
            console.print(f"[bold]Template: {name}[/bold]")
            console.print(f"[blue]File: {template_info.file_path}[/blue]")
            console.print(f"[blue]Assignments: {template_info.assignment_count}[/blue]")
            console.print(f"[blue]Entities: {template_info.entity_count}[/blue]")
            console.print(f"[blue]Permission Sets: {template_info.permission_set_count}[/blue]")
            console.print(
                f"[blue]Last Modified: {template_info.last_modified.strftime('%Y-%m-%d %H:%M:%S')}[/blue]"
            )

        # Confirm deletion
        if not force:
            if not Confirm.ask(f"Are you sure you want to delete template '{name}'?"):
                console.print("[blue]Template deletion cancelled.[/blue]")
                raise typer.Exit(0)

        # Delete the template
        if storage_manager.delete_template(name):
            console.print(f"[green]✓ Template '{name}' deleted successfully![/green]")
            if template_info and template_info.file_path.exists():
                console.print(f"[blue]File removed: {template_info.file_path}[/blue]")
        else:
            console.print(f"[red]❌ Failed to delete template '{name}'.[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error deleting template: {e}[/red]")
        raise typer.Exit(1)
