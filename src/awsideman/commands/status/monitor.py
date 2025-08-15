"""Monitor configuration command implementation."""

import asyncio
from typing import Optional

import typer
from rich.console import Console

from ...utils.config import Config
from ...utils.monitoring_config import MonitoringConfig, MonitoringConfigManager
from ...utils.notification_system import NotificationSystem

console = Console()


def monitor_config(
    action: str = typer.Argument(
        ..., help="Action to perform: show, enable, disable, test, schedule"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Configure and manage automated monitoring.

    Actions:
        show     - Display current monitoring configuration
        enable   - Enable monitoring with default settings
        disable  - Disable monitoring
        test     - Test notification systems
        schedule - Show scheduler status

    Examples:
        awsideman status monitor show
        awsideman status monitor enable
        awsideman status monitor test
    """
    try:
        # Initialize configuration manager
        try:
            config = Config()
            config_manager = MonitoringConfigManager(config)
            monitoring_config = config_manager.get_monitoring_config()
        except Exception as e:
            console.print(f"[red]Error initializing monitoring config: {str(e)}[/red]")
            console.print(f"[red]Error type: {type(e).__name__}[/red]")
            import traceback

            console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
            raise typer.Exit(1)

        if action == "show":
            _show_monitoring_config(monitoring_config)
        elif action == "enable":
            _enable_monitoring(config_manager, monitoring_config, profile)
        elif action == "disable":
            _disable_monitoring(config_manager, monitoring_config)
        elif action == "test":
            _test_notifications(monitoring_config)
        elif action == "schedule":
            _show_scheduler_status(monitoring_config)
        else:
            console.print(f"[red]Error: Unknown action '{action}'.[/red]")
            console.print("Valid actions: show, enable, disable, test, schedule")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _show_monitoring_config(monitoring_config: MonitoringConfig):
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


def _enable_monitoring(
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


def _disable_monitoring(
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


def _test_notifications(monitoring_config: MonitoringConfig):
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


def _show_scheduler_status(monitoring_config: MonitoringConfig):
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
