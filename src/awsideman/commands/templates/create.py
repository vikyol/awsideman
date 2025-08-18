"""Create template command for awsideman."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ...templates.models import Template, TemplateAssignment, TemplateMetadata, TemplateTarget
from ...templates.storage import TemplateStorageManager
from ...utils.config import Config

console = Console()


def create_template(
    name: str = typer.Option(..., "--name", "-n", help="Name for the new template"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Description for the template"
    ),
    author: Optional[str] = typer.Option(None, "--author", "-a", help="Author of the template"),
    version: Optional[str] = typer.Option("1.0", "--version", "-v", help="Template version"),
    example: bool = typer.Option(
        False, "--example", "-e", help="Create an example template with sample content"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path (default: auto-generated)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Create a new template file.

    Creates a new template file with the specified name and optional metadata.
    The template can be created as a blank template or with example content.

    Examples:
        # Create a blank template
        $ awsideman templates create --name "developer-access"

        # Create a template with description and author
        $ awsideman templates create --name "admin-access" --description "Admin access template" --author "DevOps Team"

        # Create an example template with sample content
        $ awsideman templates create --name "example-template" --example

        # Create a template in a specific location
        $ awsideman templates create --name "custom-template" --output "./my-templates/custom.yaml"
    """
    try:
        # Validate template name
        if not name or not name.strip():
            console.print("[red]Error: Template name is required.[/red]")
            raise typer.Exit(1)

        # Load configuration
        config = Config()

        # Initialize template storage manager
        storage_manager = TemplateStorageManager(config=config)

        # Check if template already exists
        if storage_manager.template_exists(name):
            console.print(f"[yellow]Warning: Template '{name}' already exists.[/yellow]")
            if not typer.confirm("Do you want to overwrite it?"):
                console.print("[blue]Template creation cancelled.[/blue]")
                raise typer.Exit(0)

        # Create template metadata
        metadata = TemplateMetadata(
            name=name, description=description, author=author, version=version
        )

        if example:
            # Create example template
            template = Template.create_example()
            template.metadata = metadata
        else:
            # Create blank template
            targets = TemplateTarget(account_ids=["123456789012"])
            assignment = TemplateAssignment(
                entities=["user:example-user"],
                permission_sets=["ExamplePermissionSet"],
                targets=targets,
            )
            template = Template(metadata=metadata, assignments=[assignment])

        # Determine output file path
        if output_file:
            file_path = output_file
        else:
            file_path = storage_manager.save_template(template)

        # Display success message
        console.print(f"[green]✓ Template '{name}' created successfully![/green]")
        console.print(f"[blue]File: {file_path}[/blue]")

        if example:
            console.print(
                "\n[yellow]Note: This is an example template. Please customize it for your needs.[/yellow]"
            )

        # Show template preview
        console.print("\n[bold]Template Preview:[/bold]")
        import yaml

        try:
            template_yaml = yaml.dump(template.to_dict(), default_flow_style=False, indent=2)
            console.print(
                Panel(
                    Text(template_yaml, style="dim"), title="Template Content", border_style="blue"
                )
            )
        except Exception:
            # Fallback to simple text if YAML formatting fails
            console.print(
                Panel(
                    Text(str(template.to_dict()), style="dim"),
                    title="Template Content (Raw)",
                    border_style="blue",
                )
            )

    except Exception as e:
        console.print(f"[red]Error creating template: {e}[/red]")
        raise typer.Exit(1)
