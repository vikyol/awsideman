"""Resource inspection command implementation."""

import asyncio
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...aws_clients.manager import AWSClientManager
from ...utils.resource_inspector import ResourceInspector
from ...utils.status_models import OutputFormat, StatusLevel
from .helpers import (
    validate_aws_credentials,
    validate_output_format,
    validate_profile,
    validate_sso_instance,
)

console = Console()


def inspect_resource(
    resource_type: str = typer.Argument(
        ..., help="Resource type to inspect: user, group, permission-set"
    ),
    resource_id: str = typer.Argument(..., help="Resource identifier (ID, name, or ARN)"),
    output_format: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output format: json, csv, table (default: table)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Inspect detailed status of a specific resource.

    Provides detailed status information for individual users, groups, or permission sets.
    Shows resource health, configuration, and suggests similar resources if not found.

    Examples:
        awsideman status inspect user john.doe@example.com
        awsideman status inspect group Administrators
        awsideman status inspect permission-set ReadOnlyAccess
    """
    try:
        # Validate inputs
        output_fmt = validate_output_format(output_format)

        # Validate resource type
        valid_resource_types = ["user", "group", "permission-set"]
        if resource_type not in valid_resource_types:
            console.print(f"[red]Error: Invalid resource type '{resource_type}'.[/red]")
            console.print(f"Valid types: {', '.join(valid_resource_types)}")
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Validate AWS credentials before proceeding
        validate_aws_credentials(aws_client)

        # Initialize the resource inspector
        inspector = ResourceInspector(aws_client)

        # Show progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Inspecting {resource_type} '{resource_id}'...", total=None)

            # Perform resource inspection based on type
            if resource_type == "user":
                result = asyncio.run(inspector.inspect_user(resource_id))
            elif resource_type == "group":
                result = asyncio.run(inspector.inspect_group(resource_id))
            elif resource_type == "permission-set":
                result = asyncio.run(inspector.inspect_permission_set(resource_id))

            progress.remove_task(task)

        # Format and display result
        _display_resource_inspection_result(result, output_fmt, resource_type, resource_id)

    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _display_resource_inspection_result(
    result, output_fmt: OutputFormat, resource_type: str, resource_id: str
) -> None:
    """Display resource inspection result."""
    if output_fmt == OutputFormat.JSON:
        # Convert result to JSON
        import json
        from dataclasses import asdict

        try:
            result_dict = asdict(result)
            console.print(json.dumps(result_dict, indent=2, default=str))
        except Exception as e:
            console.print(f"[red]Error formatting JSON: {str(e)}[/red]")
            raise typer.Exit(1)

    elif output_fmt == OutputFormat.CSV:
        # Simple CSV output for resource inspection
        console.print("Resource Type,Resource ID,Status,Found,Message")
        found = "Yes" if result.resource_found() else "No"
        console.print(
            f"{resource_type},{resource_id},{result.status.value},{found},{result.message}"
        )

    else:
        # Table format (default)
        _display_resource_inspection_table(result, resource_type, resource_id)


def _display_resource_inspection_table(result, resource_type: str, resource_id: str) -> None:
    """Display resource inspection result as a table."""
    # Create status indicator
    status_indicators = {
        StatusLevel.HEALTHY: "✅",
        StatusLevel.WARNING: "⚠️ ",
        StatusLevel.CRITICAL: "❌",
        StatusLevel.CONNECTION_FAILED: "🔌",
    }
    indicator = status_indicators.get(result.status, "❓")

    # Create panel with resource information
    lines = []
    lines.append(f"Resource Type: {resource_type}")
    lines.append(f"Resource ID: {resource_id}")
    lines.append(f"Status: {indicator} {result.status.value}")
    lines.append(f"Found: {'Yes' if result.resource_found() else 'No'}")
    lines.append(f"Message: {result.message}")

    if result.timestamp:
        lines.append(f"Inspected: {result.timestamp.isoformat()}")

    # Add resource details if found
    if hasattr(result, "target_resource") and result.target_resource:
        resource = result.target_resource
        lines.append("\nResource Details:")
        lines.append(f"  Name: {resource.resource_name or 'N/A'}")
        lines.append(f"  Status: {resource.status.value}")

        if resource.last_updated:
            lines.append(f"  Last Updated: {resource.last_updated.isoformat()}")

        if resource.configuration:
            lines.append("  Configuration:")
            for key, value in resource.configuration.items():
                lines.append(f"    {key}: {value}")

    # Add suggestions if resource not found
    if result.has_suggestions():
        lines.append("\nSimilar Resources:")
        for suggestion in result.similar_resources[:5]:  # Show up to 5 suggestions
            lines.append(f"  • {suggestion}")

    # Add errors if present
    if hasattr(result, "errors") and result.errors:
        lines.append("\nErrors:")
        for error in result.errors:
            lines.append(f"  • {error}")

    # Create panel
    panel = Panel(
        "\n".join(lines),
        title=f"[bold blue]Resource Inspection: {resource_type}[/bold blue]",
        border_style="blue",
    )

    console.print(panel)
