"""Organization management commands for awsideman."""

import json
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from ..aws_clients.manager import build_organization_hierarchy, get_account_details
from ..utils.config import Config
from ..utils.models import NodeType, OrgNode
from .common import (
    advanced_cache_option,
    extract_standard_params,
    get_aws_client_manager,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
)

app = typer.Typer(
    help="Manage AWS Organizations. Query organization structure, accounts, and policies."
)
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


@app.command("tree")
def tree(
    flat: bool = typer.Option(
        False, "--flat", help="Display in flat format instead of tree format"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Display the full AWS Organization hierarchy including roots, OUs, and accounts.

    Shows organizational units, their relationships, and accounts under each OU.
    Supports both tree and flat output formats, as well as JSON output.
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Show cache information if verbose
        show_cache_info(verbose)

        # Get AWS client manager with cache integration
        client_manager = get_aws_client_manager(
            profile=profile_param,
            region=region_param,
            enable_caching=enable_caching,
            verbose=verbose,
        )
        organizations_client = client_manager.get_organizations_client()

        # Build the organization hierarchy
        if not json_output:
            console.print("[blue]Building organization hierarchy...[/blue]")
        organization_tree = build_organization_hierarchy(organizations_client)

        # Output based on format requested
        if json_output:
            _output_tree_json(organization_tree)
        elif flat:
            _output_tree_flat(organization_tree)
        else:
            _output_tree_visual(organization_tree)

    except Exception as e:
        handle_aws_error(e, "building organization tree", verbose=verbose)
        raise typer.Exit(1)


@app.command("account")
def account(
    account_id: str = typer.Argument(..., help="AWS account ID to display details for"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Display detailed information about a specific AWS account.

    Shows comprehensive metadata including account name, ID, email, status,
    joined timestamp, tags, and the full OU path from root to account.
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Show cache information if verbose
        show_cache_info(verbose)

        # Validate account ID format (12-digit number)
        if not _is_valid_account_id(account_id):
            console.print(
                f"[red]Error: Invalid account ID format '{account_id}'. Account ID must be a 12-digit number.[/red]"
            )
            raise typer.Exit(1)

        # Get AWS client manager with cache integration
        client_manager = get_aws_client_manager(
            profile=profile_param,
            region=region_param,
            enable_caching=enable_caching,
            verbose=verbose,
        )
        organizations_client = client_manager.get_organizations_client()

        # Get account details
        if not json_output:
            console.print(f"[blue]Retrieving account details for {account_id}...[/blue]")

        account_details = get_account_details(organizations_client, account_id)

        # Output based on format requested
        if json_output:
            _output_account_json(account_details)
        else:
            _output_account_table(account_details)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Account name or substring to search for"),
    ou: Optional[str] = typer.Option(None, "--ou", help="Filter by organizational unit ID"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag in format 'Key=Value'"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Search for accounts by name or substring.

    Performs case-insensitive partial string matching on account names.
    Returns matching accounts with name, ID, email, and OU path.
    Supports optional filtering by OU and tags.
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Show cache information if verbose
        show_cache_info(verbose)

        # Parse tag filter if provided
        tag_filter = None
        if tag:
            tag_filter = _parse_tag_filter(tag)

        # Get AWS client manager with cache integration
        client_manager = get_aws_client_manager(
            profile=profile_param,
            region=region_param,
            enable_caching=enable_caching,
            verbose=verbose,
        )
        organizations_client = client_manager.get_organizations_client()

        # Perform the search
        if not json_output:
            console.print(f"[blue]Searching for accounts matching '{query}'...[/blue]")

        from ..aws_clients.manager import search_accounts

        matching_accounts = search_accounts(
            organizations_client=organizations_client,
            query=query,
            ou_filter=ou,
            tag_filter=tag_filter,
        )

        # Output results
        if not matching_accounts:
            if not json_output:
                console.print(f"[yellow]No accounts found matching '{query}'[/yellow]")
            else:
                console.print("[]")
            return

        if json_output:
            _output_search_results_json(matching_accounts)
        else:
            _output_search_results_table(matching_accounts, query)

    except Exception as e:
        handle_aws_error(e, "searching accounts", verbose=verbose)
        raise typer.Exit(1)


@app.command("trace-policies")
def trace_policies(
    account_id: str = typer.Argument(..., help="AWS account ID to trace policies for"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Trace all SCPs and RCPs affecting a given account.

    Resolves the full OU path and collects all attached policies from each level.
    Displays policy names, IDs, attachment points, and effective status.
    Distinguishes between SCPs and RCPs in the output.
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Show cache information if verbose
        show_cache_info(verbose)

        # Validate account ID format (12-digit number)
        if not _is_valid_account_id(account_id):
            console.print(
                f"[red]Error: Invalid account ID format '{account_id}'. Account ID must be a 12-digit number.[/red]"
            )
            raise typer.Exit(1)

        # Get AWS client manager with cache integration
        client_manager = get_aws_client_manager(
            profile=profile_param,
            region=region_param,
            enable_caching=enable_caching,
            verbose=verbose,
        )
        organizations_client = client_manager.get_organizations_client()

        # Initialize policy resolver
        from ..aws_clients.manager import PolicyResolver

        policy_resolver = PolicyResolver(organizations_client)

        # Trace policies for the account
        if not json_output:
            console.print(f"[blue]Tracing policies for account {account_id}...[/blue]")

        policies = policy_resolver.resolve_policies_for_account(account_id)

        # Output results
        if json_output:
            _output_policies_json(policies, account_id)
        else:
            _output_policies_table(policies, account_id)

    except Exception as e:
        handle_aws_error(e, "tracing policies", verbose=verbose)
        raise typer.Exit(1)


def _output_tree_json(organization_tree: List[OrgNode]) -> None:
    """Output the organization tree in JSON format."""

    def node_to_dict(node: OrgNode) -> Dict[str, Any]:
        """Convert an OrgNode to a dictionary for JSON serialization."""
        return {
            "id": node.id,
            "name": node.name,
            "type": node.type.value,
            "children": [node_to_dict(child) for child in node.children],
        }

    tree_data = [node_to_dict(root) for root in organization_tree]
    console.print(json.dumps(tree_data, indent=2))


def _output_tree_flat(organization_tree: List[OrgNode]) -> None:
    """Output the organization tree in flat format."""
    table = Table(title="AWS Organization Structure (Flat View)")
    table.add_column("Type", style="cyan")
    table.add_column("ID", style="yellow")
    table.add_column("Name", style="green")
    table.add_column("Path", style="blue")

    def add_node_to_table(node: OrgNode, path: List[str] = None) -> None:
        """Recursively add nodes to the flat table."""
        if path is None:
            path = []

        current_path = path + [node.name]
        path_str = " → ".join(current_path)

        # Add current node to table
        table.add_row(node.type.value, node.id, node.name, path_str)

        # Recursively add children
        for child in node.children:
            add_node_to_table(child, current_path)

    # Add all root nodes and their children
    for root in organization_tree:
        add_node_to_table(root)

    console.print(table)


def _output_tree_visual(organization_tree: List[OrgNode]) -> None:
    """Output the organization tree in visual tree format."""

    def add_node_to_tree(rich_tree: Tree, node: OrgNode) -> None:
        """Recursively add nodes to the Rich tree."""
        # Format node display based on type
        if node.type == NodeType.ROOT:
            node_display = f"[bold cyan]Root:[/bold cyan] {node.name} ({node.id})"
        elif node.type == NodeType.OU:
            node_display = f"[bold yellow]OU:[/bold yellow] {node.name} ({node.id})"
        elif node.type == NodeType.ACCOUNT:
            node_display = f"[bold green]Account:[/bold green] {node.name} ({node.id})"
        else:
            node_display = f"{node.name} ({node.id})"

        # Add this node to the tree
        branch = rich_tree.add(node_display)

        # Recursively add children
        for child in node.children:
            add_node_to_tree(branch, child)

    # Create the main tree structure
    if len(organization_tree) == 1:
        # Single root - use it as the main tree
        main_tree = Tree("[bold blue]AWS Organization Structure[/bold blue]")
        add_node_to_tree(main_tree, organization_tree[0])
    else:
        # Multiple roots - create a container tree
        main_tree = Tree("[bold blue]AWS Organization Structure[/bold blue]")
        for root in organization_tree:
            add_node_to_tree(main_tree, root)

    console.print(main_tree)


def _is_valid_account_id(account_id: str) -> bool:
    """
    Validate that the account ID is a 12-digit number.

    Args:
        account_id: The account ID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return account_id.isdigit() and len(account_id) == 12


def _output_account_json(account_details) -> None:
    """Output account details in JSON format."""
    account_dict = {
        "id": account_details.id,
        "name": account_details.name,
        "email": account_details.email,
        "status": account_details.status,
        "joined_timestamp": (
            account_details.joined_timestamp.isoformat()
            if account_details.joined_timestamp
            else None
        ),
        "tags": account_details.tags,
        "ou_path": account_details.ou_path,
    }
    console.print(json.dumps(account_dict, indent=2))


def _output_account_table(account_details) -> None:
    """Output account details in table format."""
    table = Table(title=f"Account Details: {account_details.name} ({account_details.id})")
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="green")

    # Add basic account information
    table.add_row("Account ID", account_details.id)
    table.add_row("Account Name", account_details.name)
    table.add_row("Email", account_details.email)
    table.add_row("Status", account_details.status)

    # Format joined timestamp
    if account_details.joined_timestamp:
        joined_str = account_details.joined_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        joined_str = "Unknown"
    table.add_row("Joined", joined_str)

    # Format OU path
    if account_details.ou_path:
        ou_path_str = " → ".join(account_details.ou_path)
    else:
        ou_path_str = "Root"
    table.add_row("OU Path", ou_path_str)

    # Add tags if present
    if account_details.tags:
        tags_str = ", ".join([f"{k}={v}" for k, v in account_details.tags.items()])
        table.add_row("Tags", tags_str)
    else:
        table.add_row("Tags", "None")

    console.print(table)


def _parse_tag_filter(tag_string: str) -> Dict[str, str]:
    """
    Parse a tag filter string in format 'Key=Value' into a dictionary.

    Args:
        tag_string: Tag filter string in format 'Key=Value'

    Returns:
        Dict[str, str]: Dictionary with tag key-value pair

    Raises:
        ValueError: If tag string format is invalid
    """
    if not tag_string or "=" not in tag_string:
        raise ValueError("Tag filter must be in format 'Key=Value'")

    parts = tag_string.split("=", 1)  # Split only on first '=' to handle values with '='
    if len(parts) != 2:
        raise ValueError("Tag filter must be in format 'Key=Value'")

    key, value = parts
    key = key.strip()
    value = value.strip()

    if not key:
        raise ValueError("Tag key cannot be empty")

    return {key: value}


def _output_search_results_json(matching_accounts: List) -> None:
    """Output search results in JSON format."""
    results = []
    for account in matching_accounts:
        account_dict = {
            "id": account.id,
            "name": account.name,
            "email": account.email,
            "status": account.status,
            "joined_timestamp": (
                account.joined_timestamp.isoformat() if account.joined_timestamp else None
            ),
            "tags": account.tags,
            "ou_path": account.ou_path,
        }
        results.append(account_dict)

    console.print(json.dumps(results, indent=2))


def _output_search_results_table(matching_accounts: List, query: str) -> None:
    """Output search results in table format."""
    table = Table(title=f"Search Results for '{query}' ({len(matching_accounts)} matches)")
    table.add_column("Account Name", style="green", width=20)
    table.add_column("Account ID", style="yellow", width=12)
    table.add_column("Email", style="blue", width=25)
    table.add_column("Status", style="cyan", width=8)
    table.add_column("OU Path", style="magenta", width=30)

    for account in matching_accounts:
        # Format OU path
        if account.ou_path:
            ou_path_str = " → ".join(account.ou_path)
        else:
            ou_path_str = "Root"

        table.add_row(account.name, account.id, account.email, account.status, ou_path_str)

    console.print(table)

    # Show summary
    console.print(f"\n[green]Found {len(matching_accounts)} account(s) matching '{query}'[/green]")


def _output_policies_json(policies: List, account_id: str) -> None:
    """Output policy trace results in JSON format."""
    policies_data = []

    for policy in policies:
        policy_dict = {
            "id": policy.id,
            "name": policy.name,
            "type": policy.type.value,
            "description": policy.description,
            "aws_managed": policy.aws_managed,
            "attachment_point": policy.attachment_point,
            "attachment_point_name": policy.attachment_point_name,
            "effective_status": policy.effective_status,
        }
        policies_data.append(policy_dict)

    result = {"account_id": account_id, "policies": policies_data}

    console.print(json.dumps(result, indent=2))


def _output_policies_table(policies: List, account_id: str) -> None:
    """Output policy trace results in table format."""
    if not policies:
        console.print(f"[yellow]No policies found affecting account {account_id}[/yellow]")
        return

    console.print(f"[bold blue]Policy Trace for Account: {account_id}[/bold blue]\n")

    # Separate SCPs and RCPs
    scps = [p for p in policies if p.is_scp()]
    rcps = [p for p in policies if p.is_rcp()]

    # Display SCPs
    if scps:
        console.print("[bold cyan]Service Control Policies (SCPs):[/bold cyan]")
        scp_table = Table()
        scp_table.add_column("Policy Name", style="green", width=25)
        scp_table.add_column("Policy ID", style="yellow", width=20)
        scp_table.add_column("Attachment Point", style="blue", width=25)
        scp_table.add_column("Status", style="cyan", width=12)
        scp_table.add_column("AWS Managed", style="magenta", width=12)

        for policy in scps:
            status_style = (
                "green"
                if policy.effective_status == "ENABLED"
                else "yellow" if policy.effective_status == "CONDITIONAL" else "red"
            )
            scp_table.add_row(
                policy.name,
                policy.id,
                policy.attachment_point_name or policy.attachment_point,
                f"[{status_style}]{policy.effective_status}[/{status_style}]",
                "Yes" if policy.aws_managed else "No",
            )

        console.print(scp_table)
        console.print()

    # Display RCPs
    if rcps:
        console.print("[bold magenta]Resource Control Policies (RCPs):[/bold magenta]")
        rcp_table = Table()
        rcp_table.add_column("Policy Name", style="green", width=25)
        rcp_table.add_column("Policy ID", style="yellow", width=20)
        rcp_table.add_column("Attachment Point", style="blue", width=25)
        rcp_table.add_column("Status", style="cyan", width=12)
        rcp_table.add_column("AWS Managed", style="magenta", width=12)

        for policy in rcps:
            status_style = (
                "green"
                if policy.effective_status == "ENABLED"
                else "yellow" if policy.effective_status == "CONDITIONAL" else "red"
            )
            rcp_table.add_row(
                policy.name,
                policy.id,
                policy.attachment_point_name or policy.attachment_point,
                f"[{status_style}]{policy.effective_status}[/{status_style}]",
                "Yes" if policy.aws_managed else "No",
            )

        console.print(rcp_table)
        console.print()

    # Summary
    total_policies = len(policies)
    scp_count = len(scps)
    rcp_count = len(rcps)

    console.print(f"[green]Total policies affecting account {account_id}: {total_policies}[/green]")
    if scp_count > 0:
        console.print(f"[cyan]  - Service Control Policies: {scp_count}[/cyan]")
    if rcp_count > 0:
        console.print(f"[magenta]  - Resource Control Policies: {rcp_count}[/magenta]")

    if total_policies == 0:
        console.print("[yellow]No policies are currently affecting this account.[/yellow]")
