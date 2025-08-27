"""SSO instance commands for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config

app = typer.Typer(help="Manage AWS SSO instances.")
console = Console()
config = Config()


@app.command("list")
def list_instances(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """List AWS SSO instances for the specified profile."""
    profile_name = profile or config.get("default_profile")

    if not profile_name:
        console.print("[red]No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        return

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Profile '{profile_name}' does not exist.[/red]")
        return

    try:
        # CRITICAL FIX: Only show instances for this specific profile
        # Do NOT call list_instances() as it returns ALL instances the credentials can access
        # This prevents profile mixing and security vulnerabilities

        # Check if profile has SSO instance configured
        profile_data = profiles[profile_name]
        configured_instance_arn = profile_data.get("sso_instance_arn")
        configured_identity_store_id = profile_data.get("identity_store_id")

        if not configured_instance_arn or not configured_identity_store_id:
            console.print(
                f"[yellow]Profile '{profile_name}' has no SSO instance configured.[/yellow]"
            )
            console.print(
                "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
            )
            return

        # Only show the configured instance for this profile
        instances = [
            {
                "InstanceArn": configured_instance_arn,
                "IdentityStoreId": configured_identity_store_id,
                "Name": profile_data.get("sso_instance_name", ""),
            }
        ]

        console.print(f"[blue]Showing SSO instance for profile '{profile_name}':[/blue]")

        table = Table(title=f"AWS SSO Instance for Profile '{profile_name}'")
        table.add_column("Instance ARN", style="cyan")
        table.add_column("Identity Store ID", style="green")
        table.add_column("Name", style="yellow")

        for instance in instances:
            instance_arn = instance.get("InstanceArn", "")
            identity_store_id = instance.get("IdentityStoreId", "")
            aws_name = instance.get("Name", "")

            # Check if we have a custom display name for this instance
            custom_name = ""
            if profile_data.get("sso_instance_name"):
                custom_name = profile_data.get("sso_instance_name")

            # Use custom name if available, otherwise use AWS name
            display_name = custom_name or aws_name

            table.add_row(instance_arn, identity_store_id, display_name)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing SSO instances: {str(e)}[/red]")


@app.command("set")
def set_instance(
    instance_arn: str = typer.Argument(...),
    identity_store_id: str = typer.Argument(...),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name for the SSO instance"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Set the SSO instance to use for operations."""
    profile_name = profile or config.get("default_profile")

    if not profile_name:
        console.print("[red]No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        return

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Profile '{profile_name}' does not exist.[/red]")
        return

    # Update the profile with SSO instance information
    profiles[profile_name]["sso_instance_arn"] = instance_arn
    profiles[profile_name]["identity_store_id"] = identity_store_id

    # Set the display name if provided
    if name:
        profiles[profile_name]["sso_instance_name"] = name

    config.set("profiles", profiles)
    console.print(f"[green]SSO instance set for profile '{profile_name}'.[/green]")


@app.command("set-name")
def set_instance_name(
    name: str = typer.Argument(...),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Set a display name for the SSO instance."""
    profile_name = profile or config.get("default_profile")

    if not profile_name:
        console.print("[red]No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        return

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Profile '{profile_name}' does not exist.[/red]")
        return

    profile_data = profiles[profile_name]
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    if not instance_arn or not identity_store_id:
        console.print(f"[yellow]No SSO instance configured for profile '{profile_name}'.[/yellow]")
        console.print("Use 'awsideman sso set' to configure an SSO instance first.")
        return

    # Update the profile with the new display name
    profiles[profile_name]["sso_instance_name"] = name
    config.set("profiles", profiles)
    console.print(
        f"[green]SSO instance display name set to '{name}' for profile '{profile_name}'.[/green]"
    )


@app.command("info")
def instance_info(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Show information about the configured SSO instance."""
    profile_name = profile or config.get("default_profile")

    if not profile_name:
        console.print("[red]No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        return

    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Profile '{profile_name}' does not exist.[/red]")
        return

    profile_data = profiles[profile_name]
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    if not instance_arn or not identity_store_id:
        console.print(f"[yellow]No SSO instance configured for profile '{profile_name}'.[/yellow]")
        console.print("Use 'awsideman sso set' to configure an SSO instance.")
        return

    console.print(f"[bold]SSO Instance for profile '{profile_name}':[/bold]")
    console.print(f"Instance ARN: {instance_arn}")
    console.print(f"Identity Store ID: {identity_store_id}")

    # Show custom display name if available
    custom_name = profile_data.get("sso_instance_name")
    if custom_name:
        console.print(f"Display Name: {custom_name}")

    # Try to get additional information from AWS
    try:
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        sso_admin_client = aws_client.get_identity_center_client()

        response = sso_admin_client.describe_instance(InstanceArn=instance_arn)
        instance = response.get("Instance", {})

        console.print(f"Name: {instance.get('Name', 'N/A')}")
        console.print(f"Status: {instance.get('Status', 'N/A')}")
        console.print(f"Created Date: {instance.get('CreatedDate', 'N/A')}")

    except Exception as e:
        console.print(
            f"[yellow]Could not retrieve additional instance information: {str(e)}[/yellow]"
        )
