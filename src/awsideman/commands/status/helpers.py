"""Shared utility functions for status monitoring commands."""

import asyncio
import json
from dataclasses import asdict
from typing import Optional

import typer
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from rich.console import Console
from rich.panel import Panel

from ...aws_clients.manager import AWSClientManager
from ...utils.config import Config
from ...utils.monitoring_config import MonitoringConfig, MonitoringConfigManager
from ...utils.notification_system import NotificationSystem
from ...utils.output_formatters import (
    CSVFormatter,
    JSONFormatter,
    OutputFormatError,
    TableFormatter,
)
from ...utils.status_models import OutputFormat, StatusLevel

console = Console()
config = Config()


def validate_profile(profile_name: Optional[str] = None) -> tuple[str, dict]:
    """
    Validate the profile and return profile name and data.

    This function checks if the specified profile exists or uses the default profile.
    It handles cases where no profile is specified and no default profile is set,
    or when the specified profile does not exist.

    Args:
        profile_name: AWS profile name to use

    Returns:
        Tuple of (profile_name, profile_data)

    Raises:
        typer.Exit: If profile validation fails with a clear error message
    """
    # Use the provided profile name or fall back to the default profile
    profile_name = profile_name or config.get("default_profile")

    # Check if a profile name is available
    if not profile_name:
        console.print("[red]Error: No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        raise typer.Exit(1)

    # Get all profiles and check if the specified profile exists
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Error: Profile '{profile_name}' does not exist.[/red]")
        console.print("Use 'awsideman profile add' to create a new profile.")
        raise typer.Exit(1)

    # Return the profile name and profile data
    return profile_name, profiles[profile_name]


def validate_sso_instance(profile_data: dict) -> tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    It handles cases where no SSO instance is configured for the profile and provides
    helpful guidance on how to configure an SSO instance.

    Args:
        profile_data: Profile data dictionary containing configuration

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # Check if both the instance ARN and identity store ID are available
    if not instance_arn or not identity_store_id:
        console.print("[red]Error: No SSO instance configured for this profile.[/red]")
        console.print(
            "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
        )
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)

    # Return the instance ARN and identity store ID
    return instance_arn, identity_store_id


def validate_output_format(format_str: Optional[str]) -> OutputFormat:
    """
    Validate and convert output format string to OutputFormat enum.

    Args:
        format_str: Output format string ('json', 'csv', 'table', or None)

    Returns:
        OutputFormat: Validated output format enum

    Raises:
        typer.Exit: If format is invalid
    """
    if format_str is None:
        return OutputFormat.TABLE

    format_str = format_str.lower()
    format_mapping = {
        "json": OutputFormat.JSON,
        "csv": OutputFormat.CSV,
        "table": OutputFormat.TABLE,
    }

    if format_str not in format_mapping:
        console.print(f"[red]Error: Invalid output format '{format_str}'.[/red]")
        console.print("Valid formats: json, csv, table")
        raise typer.Exit(1)

    return format_mapping[format_str]


def validate_status_type(status_type: Optional[str]) -> Optional[str]:
    """
    Validate status type parameter.

    Args:
        status_type: Status type string

    Returns:
        str: Validated status type or None for comprehensive check

    Raises:
        typer.Exit: If status type is invalid
    """
    if status_type is None:
        return None

    valid_types = ["health", "provisioning", "orphaned", "sync", "resource", "summary"]
    if status_type not in valid_types:
        console.print(f"[red]Error: Invalid status type '{status_type}'.[/red]")
        console.print(f"Valid types: {', '.join(valid_types)}")
        raise typer.Exit(1)

    return status_type


def validate_aws_credentials(aws_client: AWSClientManager) -> None:
    """
    Validate AWS credentials before running status checks.

    This function performs a quick credential validation by making a simple
    AWS API call to verify that credentials are valid and not expired.

    Args:
        aws_client: AWS client manager instance

    Raises:
        typer.Exit: If credentials are invalid, expired, or missing with helpful error message
    """
    try:
        # Use STS get-caller-identity as a lightweight credential validation
        sts_client = aws_client.get_client("sts")
        response = sts_client.get_caller_identity()

        # Log successful validation for debugging
        account_id = response.get("Account", "Unknown")
        console.print(f"[dim]✓ AWS credentials validated for account {account_id}[/dim]")

    except NoCredentialsError:
        console.print("[red]❌ Error: AWS credentials not found or not configured.[/red]")
        console.print("\n[yellow]To fix this issue:[/yellow]")
        console.print("1. Configure AWS credentials: [cyan]aws configure[/cyan]")
        console.print(
            "2. Or set environment variables: [cyan]AWS_ACCESS_KEY_ID[/cyan] and [cyan]AWS_SECRET_ACCESS_KEY[/cyan]"
        )
        console.print("3. Or use an AWS profile: [cyan]--profile your-profile-name[/cyan]")
        console.print("\n[blue]For more information:[/blue]")
        console.print("https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html")
        raise typer.Exit(1)

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        if error_code in ["ExpiredToken", "TokenRefreshRequired"]:
            console.print("[red]❌ Error: AWS credentials have expired.[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print("1. Refresh your AWS credentials")
            console.print("2. If using SSO: [cyan]aws sso login --profile your-profile[/cyan]")
            console.print("3. If using temporary credentials, obtain new ones")

        elif error_code in ["AccessDenied", "UnauthorizedOperation"]:
            console.print("[red]❌ Error: AWS credentials lack required permissions.[/red]")
            console.print(f"[red]Details: {error_message}[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print("1. Ensure your AWS user/role has Identity Center permissions")
            console.print(
                "2. Required permissions: [cyan]sso:*[/cyan], [cyan]identitystore:*[/cyan], [cyan]organizations:*[/cyan]"
            )
            console.print("3. Contact your AWS administrator if you need additional permissions")

        elif error_code == "InvalidUserType":
            console.print("[red]❌ Error: Invalid AWS credentials or user type.[/red]")
            console.print(f"[red]Details: {error_message}[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print("1. Verify you're using the correct AWS credentials")
            console.print("2. Ensure credentials are for the correct AWS account")

        else:
            console.print(f"[red]❌ Error: AWS credential validation failed ({error_code}).[/red]")
            console.print(f"[red]Details: {error_message}[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print(
                "1. Verify your AWS credentials: [cyan]aws sts get-caller-identity[/cyan]"
            )
            console.print("2. Check your AWS profile configuration")
            console.print("3. Ensure you have network connectivity to AWS")

        raise typer.Exit(1)

    except EndpointConnectionError:
        console.print("[red]❌ Error: Cannot connect to AWS services.[/red]")
        console.print("\n[yellow]To fix this issue:[/yellow]")
        console.print("1. Check your internet connection")
        console.print("2. Verify AWS region is accessible")
        console.print("3. Check if you're behind a firewall or proxy")
        console.print("4. Try a different AWS region if the current one is experiencing issues")
        raise typer.Exit(1)

    except Exception as e:
        error_str = str(e).lower()

        # Handle SSO token expiration specifically
        if "token has expired" in error_str or "refresh failed" in error_str:
            console.print("[red]❌ Error: AWS SSO token has expired.[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print(
                "1. Refresh your SSO login: [cyan]aws sso login --profile your-profile[/cyan]"
            )
            console.print("2. Or use a different profile: [cyan]--profile other-profile[/cyan]")
            console.print("3. Verify your SSO configuration is correct")

        # Handle SSO configuration issues
        elif "sso" in error_str and ("not configured" in error_str or "invalid" in error_str):
            console.print("[red]❌ Error: AWS SSO configuration issue.[/red]")
            console.print(f"[red]Details: {str(e)}[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print("1. Configure AWS SSO: [cyan]aws configure sso[/cyan]")
            console.print("2. Or use regular AWS credentials instead of SSO")
            console.print("3. Verify your SSO settings in AWS config")

        else:
            console.print(
                f"[red]❌ Error: Unexpected error during credential validation: {str(e)}[/red]"
            )
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print(
                "1. Verify your AWS credentials: [cyan]aws sts get-caller-identity[/cyan]"
            )
            console.print("2. Check your AWS configuration")
            console.print("3. Try running the command again")

        raise typer.Exit(1)


def display_comprehensive_status_report(status_report, output_fmt: OutputFormat) -> None:
    """Display comprehensive status report in the specified format."""
    try:
        # Select appropriate formatter
        if output_fmt == OutputFormat.JSON:
            formatter = JSONFormatter()
        elif output_fmt == OutputFormat.CSV:
            formatter = CSVFormatter()
        else:
            formatter = TableFormatter()

        # Format the output
        formatted_output = formatter.format(status_report)

        # Display the formatted content
        console.print(formatted_output.content)

        # Show metadata for non-table formats
        if output_fmt != OutputFormat.TABLE:
            console.print(f"\n[dim]Output format: {formatted_output.format_type.value}[/dim]")
            console.print(
                f"[dim]Size: {formatted_output.metadata.get('size_bytes', 0)} bytes[/dim]"
            )

    except OutputFormatError as e:
        console.print(f"[red]Error formatting output: {str(e)}[/red]")
        raise typer.Exit(1)


def display_specific_status_result(result, output_fmt: OutputFormat, check_type: str) -> None:
    """Display specific status check result."""
    if output_fmt == OutputFormat.JSON:
        # Convert result to JSON
        try:
            result_dict = asdict(result)
            # Handle datetime serialization
            for key, value in result_dict.items():
                if hasattr(value, "isoformat"):
                    result_dict[key] = value.isoformat()

            console.print(json.dumps(result_dict, indent=2, default=str))
        except Exception as e:
            console.print(f"[red]Error formatting JSON: {str(e)}[/red]")
            raise typer.Exit(1)

    elif output_fmt == OutputFormat.CSV:
        # Simple CSV output for specific results
        console.print("Component,Status,Message,Timestamp")
        timestamp = result.timestamp.isoformat() if result.timestamp else "N/A"
        console.print(f"{check_type},{result.status.value},{result.message},{timestamp}")

    else:
        # Table format (default)
        display_specific_status_table(result, check_type)


def display_specific_status_table(result, check_type: str) -> None:
    """Display specific status result as a table."""
    # Create status indicator
    status_indicators = {
        StatusLevel.HEALTHY: "✅",
        StatusLevel.WARNING: "⚠️ ",
        StatusLevel.CRITICAL: "❌",
        StatusLevel.CONNECTION_FAILED: "🔌",
    }
    indicator = status_indicators.get(result.status, "❓")

    # Create panel with status information
    lines = []
    lines.append(f"Status: {indicator} {result.status.value}")
    lines.append(f"Message: {result.message}")

    if result.timestamp:
        lines.append(f"Timestamp: {result.timestamp.isoformat()}")

    # Add component-specific details
    if hasattr(result, "details") and result.details:
        lines.append("\nDetails:")
        for key, value in result.details.items():
            lines.append(f"  {key.replace('_', ' ').title()}: {value}")

    # Add errors if present
    if hasattr(result, "errors") and result.errors:
        lines.append("\nErrors:")
        for error in result.errors:
            lines.append(f"  • {error}")

    # Create panel
    panel = Panel(
        "\n".join(lines),
        title=f"[bold blue]{check_type.title()} Status[/bold blue]",
        border_style="blue",
    )

    console.print(panel)


def display_resource_inspection_result(
    result, output_fmt: OutputFormat, resource_type: str, resource_id: str
) -> None:
    """Display resource inspection result."""
    if output_fmt == OutputFormat.JSON:
        # Convert result to JSON
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
        display_resource_inspection_table(result, resource_type, resource_id)


def display_resource_inspection_table(result, resource_type: str, resource_id: str) -> None:
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
        lines.append(f"Timestamp: {result.timestamp.isoformat()}")

    # Add resource-specific details
    if hasattr(result, "details") and result.details:
        lines.append("\nDetails:")
        for key, value in result.details.items():
            lines.append(f"  {key.replace('_', ' ').title()}: {value}")

    # Add suggestions if resource not found
    if hasattr(result, "suggestions") and result.suggestions:
        lines.append("\nSuggestions:")
        for suggestion in result.suggestions:
            lines.append(f"  • {suggestion}")

    # Create panel
    panel = Panel(
        "\n".join(lines),
        title=f"[bold blue]{resource_type.title()} Inspection[/bold blue]",
        border_style="blue",
    )

    console.print(panel)


def show_monitoring_config(monitoring_config: MonitoringConfig):
    """Display current monitoring configuration."""
    # Main status
    status_color = "green" if monitoring_config.enabled else "red"
    console.print(
        f"[bold]Monitoring Status:[/bold] [{status_color}]{'Enabled' if monitoring_config.enabled else 'Disabled'}[/{status_color}]"
    )

    if not monitoring_config.enabled:
        console.print(
            "\n[yellow]Use 'awsideman status monitor enable' to enable monitoring.[/yellow]"
        )
        return

    # Profiles
    if monitoring_config.profiles:
        console.print(f"\n[bold]Monitored Profiles:[/bold] {', '.join(monitoring_config.profiles)}")
    else:
        console.print("\n[bold]Monitored Profiles:[/bold] [yellow]All configured profiles[/yellow]")

    # Status types
    console.print(f"[bold]Status Types:[/bold] {', '.join(monitoring_config.status_types)}")

    # Thresholds
    if monitoring_config.thresholds:
        console.print("\n[bold]Thresholds:[/bold]")
        for name, threshold in monitoring_config.thresholds.items():
            status = "✅" if threshold.enabled else "❌"
            console.print(f"  {status} {name.title()}: {threshold.level.value}")

            details = []
            if threshold.orphaned_assignment_count:
                details.append(f"Orphaned assignments ≥ {threshold.orphaned_assignment_count}")
            if threshold.provisioning_failure_count:
                details.append(f"Provisioning failures ≥ {threshold.provisioning_failure_count}")
            if threshold.sync_delay_hours:
                details.append(f"Sync delay ≥ {threshold.sync_delay_hours}h")

            if details:
                console.print(f"    Triggers: {', '.join(details)}")

    # Notifications
    console.print("\n[bold]Notifications:[/bold]")

    if monitoring_config.email_notifications is not None:
        status = "✅" if monitoring_config.email_notifications.enabled else "❌"
        console.print(f"  {status} Email: {monitoring_config.email_notifications.smtp_server}")
        if (
            monitoring_config.email_notifications.enabled
            and monitoring_config.email_notifications.to_addresses
        ):
            console.print(
                f"    Recipients: {', '.join(monitoring_config.email_notifications.to_addresses)}"
            )

    if monitoring_config.webhook_notifications is not None:
        status = "✅" if monitoring_config.webhook_notifications.enabled else "❌"
        console.print(f"  {status} Webhook: {monitoring_config.webhook_notifications.url}")

    if monitoring_config.log_notifications is not None:
        status = "✅" if monitoring_config.log_notifications.enabled else "❌"
        log_dest = monitoring_config.log_notifications.log_file or "console"
        console.print(f"  {status} Log: {log_dest}")

    # Schedule
    if monitoring_config.schedule is not None:
        console.print("\n[bold]Schedule:[/bold]")
        status = "✅" if monitoring_config.schedule.enabled else "❌"
        console.print(
            f"  {status} Automated checks: Every {monitoring_config.schedule.interval_minutes} minutes"
        )

        if monitoring_config.schedule.enabled:
            console.print(f"    Max concurrent: {monitoring_config.schedule.max_concurrent_checks}")
            console.print(f"    Timeout: {monitoring_config.schedule.timeout_seconds}s")
            console.print(
                f"    Retry on failure: {'Yes' if monitoring_config.schedule.retry_on_failure else 'No'}"
            )


def enable_monitoring(
    config_manager: MonitoringConfigManager,
    monitoring_config: MonitoringConfig,
    profile: Optional[str],
):
    """Enable monitoring with default or specified configuration."""
    if monitoring_config.enabled:
        console.print("[yellow]Monitoring is already enabled.[/yellow]")
        return

    # Enable monitoring
    monitoring_config.enabled = True

    # Set profile if specified
    if profile:
        monitoring_config.profiles = [profile]

    # Enable basic log notifications by default
    if not monitoring_config.log_notifications:
        from ...utils.monitoring_config import LogNotificationConfig

        monitoring_config.log_notifications = LogNotificationConfig(enabled=True)

    # Save configuration
    config_manager.save_monitoring_config(monitoring_config)

    console.print("[green]✅ Monitoring enabled successfully![/green]")
    console.print("\n[blue]Next steps:[/blue]")
    console.print("1. Configure notifications: Edit ~/.awsideman/config.yaml")
    console.print("2. Test notifications: awsideman status monitor test")
    console.print("3. Enable scheduling: Set monitoring.schedule.enabled = true in config")
    console.print("4. View configuration: awsideman status monitor show")


def disable_monitoring(
    config_manager: MonitoringConfigManager, monitoring_config: MonitoringConfig
):
    """Disable monitoring."""
    if not monitoring_config.enabled:
        console.print("[yellow]Monitoring is already disabled.[/yellow]")
        return

    # Confirm disable
    confirm = typer.confirm("Are you sure you want to disable monitoring?")
    if not confirm:
        console.print("[blue]Monitoring disable cancelled.[/blue]")
        return

    # Disable monitoring
    monitoring_config.enabled = False
    config_manager.save_monitoring_config(monitoring_config)

    console.print("[green]✅ Monitoring disabled successfully.[/green]")


def test_notifications(monitoring_config: MonitoringConfig):
    """Test notification systems."""
    if not monitoring_config.enabled:
        console.print("[red]Error: Monitoring is disabled. Enable monitoring first.[/red]")
        raise typer.Exit(1)

    # Check if any notifications are configured
    has_notifications = (
        (
            monitoring_config.email_notifications is not None
            and monitoring_config.email_notifications.enabled
        )
        or (
            monitoring_config.webhook_notifications is not None
            and monitoring_config.webhook_notifications.enabled
        )
        or (
            monitoring_config.log_notifications is not None
            and monitoring_config.log_notifications.enabled
        )
    )

    if not has_notifications:
        console.print("[yellow]No notification methods are configured and enabled.[/yellow]")
        console.print("Configure notifications in ~/.awsideman/config.yaml")
        return

    console.print("[blue]Testing notification systems...[/blue]")

    # Test notifications
    try:
        notification_system = NotificationSystem(monitoring_config)
    except Exception as e:
        console.print(f"[red]Error creating notification system: {str(e)}[/red]")
        console.print(f"[red]Error type: {type(e).__name__}[/red]")
        import traceback

        console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        raise typer.Exit(1)

    with console.status("Sending test notifications..."):
        results = asyncio.run(notification_system.test_notifications())

    # Display results
    console.print("\n[bold]Test Results:[/bold]")

    for notification_type, success in results.items():
        status = "✅" if success else "❌"
        result = "Success" if success else "Failed"
        console.print(f"  {status} {notification_type.title()}: {result}")

    if all(results.values()):
        console.print("\n[green]All notification tests passed![/green]")
    else:
        console.print("\n[yellow]Some notification tests failed. Check logs for details.[/yellow]")


def show_scheduler_status(monitoring_config: MonitoringConfig):
    """Show scheduler status."""
    if not monitoring_config.enabled:
        console.print("[red]Monitoring is disabled.[/red]")
        return

    if not monitoring_config.schedule or not monitoring_config.schedule.enabled:
        console.print("[yellow]Scheduled monitoring is disabled.[/yellow]")
        console.print("Enable scheduling in ~/.awsideman/config.yaml:")
        console.print("  monitoring:")
        console.print("    schedule:")
        console.print("      enabled: true")
        console.print("      interval_minutes: 60")
        return

    console.print("[bold]Scheduler Configuration:[/bold]")
    console.print("  Status: [green]Enabled[/green]")
    console.print(f"  Interval: {monitoring_config.schedule.interval_minutes} minutes")
    console.print(f"  Max concurrent checks: {monitoring_config.schedule.max_concurrent_checks}")
    console.print(f"  Timeout: {monitoring_config.schedule.timeout_seconds} seconds")
    console.print(
        f"  Retry on failure: {'Yes' if monitoring_config.schedule.retry_on_failure else 'No'}"
    )

    console.print("\n[blue]To run the scheduler as a service:[/blue]")
    console.print("  python -m awsideman.utils.monitoring_scheduler")

    console.print("\n[blue]To run a manual check:[/blue]")
    console.print("  awsideman status check --profile <profile_name>")
