"""User management commands for awsideman."""
import typer
import sys
import os
from typing import Optional, Tuple, List, Dict, Any
from rich.console import Console
from rich.table import Table
from botocore.exceptions import ClientError

from ..utils.config import Config
from ..utils.aws_client import AWSClientManager

app = typer.Typer(help="Manage users in AWS Identity Center. Create, list, update, and delete users in the Identity Store.")
console = Console()
config = Config()


def get_single_key():
    """
    Get a single key press without requiring Enter.
    
    Used for interactive pagination in the list command.
    Handles platform-specific keyboard input with fallbacks.
    """
    try:
        # Try to import platform-specific modules
        if sys.platform == "win32":
            import msvcrt
            return msvcrt.getch().decode('utf-8')
        else:
            import termios
            import tty
            
            # Save the terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                # Set terminal to raw mode
                tty.setraw(sys.stdin.fileno())
                # Read a single character
                key = sys.stdin.read(1)
                return key
            finally:
                # Restore terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except ImportError:
        # Fallback to input() if platform-specific modules are not available
        return input()
    except Exception:
        # Fallback to input() if anything goes wrong
        return input()


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
        console.print("Use --profile option or set a default profile with 'awsideman profile set-default'.")
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
        console.print("Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance.")
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)
    
    # Return the instance ARN and identity store ID
    return instance_arn, identity_store_id


@app.command("list")
def list_users(
    filter: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter users by attribute in format 'attribute=value' (e.g., UserName=john)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum number of users to return in a single page"),
    next_token: Optional[str] = typer.Option(None, "--next-token", "-n", help="Pagination token (for internal use)"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"),
):
    """List all users in the Identity Store.
    
    Displays a table of users with their IDs, usernames, emails, names, and status.
    Results can be filtered and paginated. Press ENTER to see the next page of results.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)
        
        # Check if AWS_DEFAULT_REGION environment variable is set
        import os
        if os.environ.get("AWS_DEFAULT_REGION"):
            console.print(f"[yellow]Warning: AWS_DEFAULT_REGION environment variable is set to '{os.environ.get('AWS_DEFAULT_REGION')}'. This may override the region in your profile.[/yellow]")
        
        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)
        
        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        
        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()
        
        # Prepare the list_users API call parameters
        list_users_params = {
            "IdentityStoreId": identity_store_id
        }
        
        # Add optional parameters if provided
        if filter:
            # Check if filter is in the format "attribute=value"
            if "=" not in filter:
                raise ValueError("Filter must be in the format 'attribute=value'")
                
            attribute_path, attribute_value = filter.split("=", 1)
            list_users_params["Filters"] = [
                {
                    "AttributePath": attribute_path,
                    "AttributeValue": attribute_value
                }
            ]
        
        if limit:
            list_users_params["MaxResults"] = limit
            
        if next_token:
            list_users_params["NextToken"] = next_token
            
        # Make the API call to list users
        response = identity_store.list_users(**list_users_params)
        
        # Extract users and next token from the response
        users = response.get("Users", [])
        next_token = response.get("NextToken")
        
        # Display the results using a Rich table
        if not users:
            console.print("[yellow]No users found.[/yellow]")
            return [], next_token
            
        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"
            
        console.print(f"[green]Found {len(users)} users{page_info}.[/green]")
            
        # Create a table for displaying users
        table = Table(title=f"Users in Identity Store {identity_store_id}")
        
        # Add columns to the table
        table.add_column("User ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Email", style="blue")
        table.add_column("Name", style="magenta")
        table.add_column("Status", style="yellow")
        
        # Add rows to the table
        for user in users:
            user_id = user.get("UserId", "")
            username = user.get("UserName", "")
            
            # Extract email from user attributes
            email = ""
            for attr in user.get("Emails", []):
                if attr.get("Primary", False):
                    email = attr.get("Value", "")
                    break
            
            # Extract name components
            given_name = user.get("Name", {}).get("GivenName", "")
            family_name = user.get("Name", {}).get("FamilyName", "")
            display_name = user.get("DisplayName", "")
            
            # Format the name for display
            if display_name:
                name = display_name
            elif given_name or family_name:
                name = f"{given_name} {family_name}".strip()
            else:
                name = ""
                
            # Get user status
            status = user.get("Status", "")
            
            # Add the row to the table
            table.add_row(user_id, username, email, name, status)
            
        # Display the table
        console.print(table)
        
        # Handle pagination - interactive by default
        if next_token:
            console.print("\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]")
            try:
                # Wait for single key press
                key = get_single_key()
                
                # If the user pressed Enter (or Return), fetch the next page
                if key in ['\r', '\n', '']:
                    console.print("\n[blue]Fetching next page...[/blue]\n")
                    # Call list_users recursively with the next token
                    return list_users(
                        filter=filter,
                        limit=limit,
                        next_token=next_token,
                        profile=profile
                    )
                else:
                    console.print("\n[yellow]Pagination stopped.[/yellow]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Pagination stopped by user.[/yellow]")
        
        # Return the users and next token for further processing
        return users, next_token
        
    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("Filter format should be 'attribute=value'.")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("get")
def get_user(
    identifier: str = typer.Argument(..., help="Username, email, or user ID to search for"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"),
):
    """Get detailed information about a specific user.
    
    Retrieves and displays comprehensive information about a user by their username, email, or user ID.
    Shows all available user attributes including contact information, status, and timestamps.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)
        
        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)
        
        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        
        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()
        
        # Check if identifier is a UUID (user ID) or if we need to search
        import re
        uuid_pattern = r'^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        
        if re.match(uuid_pattern, identifier):
            # Direct lookup by user ID
            user_id = identifier
        else:
            # Search for user by username or email
            console.print(f"[blue]Searching for user: {identifier}[/blue]")
            
            # Try searching by username first
            try:
                search_response = identity_store.list_users(
                    IdentityStoreId=identity_store_id,
                    Filters=[
                        {
                            "AttributePath": "UserName",
                            "AttributeValue": identifier
                        }
                    ]
                )
                
                users = search_response.get("Users", [])
                
                # If no users found by username, we need to list all users and filter by email manually
                # since the AWS API doesn't support filtering by email directly
                if not users:
                    # Get all users (with pagination if needed)
                    all_users = []
                    next_token = None
                    
                    while True:
                        list_params = {"IdentityStoreId": identity_store_id}
                        if next_token:
                            list_params["NextToken"] = next_token
                            
                        list_response = identity_store.list_users(**list_params)
                        batch_users = list_response.get("Users", [])
                        all_users.extend(batch_users)
                        
                        next_token = list_response.get("NextToken")
                        if not next_token:
                            break
                    
                    # Filter users by email manually
                    users = []
                    for user in all_users:
                        emails = user.get("Emails", [])
                        for email in emails:
                            if email.get("Value", "").lower() == identifier.lower():
                                users.append(user)
                                break
                
                # Handle search results
                if not users:
                    console.print(f"[red]Error: No user found with username or email '{identifier}'.[/red]")
                    raise typer.Exit(1)
                elif len(users) > 1:
                    console.print(f"[yellow]Warning: Multiple users found matching '{identifier}'. Showing the first match.[/yellow]")
                
                # Use the first user found
                user_id = users[0].get("UserId")
                console.print(f"[green]Found user: {users[0].get('UserName', 'N/A')} (ID: {user_id})[/green]")
                
            except ClientError as search_error:
                console.print(f"[red]Error searching for user: {search_error}[/red]")
                raise typer.Exit(1)
        
        # Make the API call to describe the user
        response = identity_store.describe_user(
            IdentityStoreId=identity_store_id,
            UserId=user_id
        )
        
        # Format and display the user details
        user = response
        
        # Create a rich panel for displaying user details
        from rich.panel import Panel
        from rich.table import Table
        from rich.console import Group
        
        # Create a table for displaying user details
        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        # Add basic user information
        table.add_row("User ID", user.get("UserId", ""))
        table.add_row("Username", user.get("UserName", ""))
        
        # Add name information
        name_info = user.get("Name", {})
        if name_info.get("GivenName"):
            table.add_row("Given Name", name_info.get("GivenName", ""))
        if name_info.get("FamilyName"):
            table.add_row("Family Name", name_info.get("FamilyName", ""))
        if user.get("DisplayName"):
            table.add_row("Display Name", user.get("DisplayName", ""))
        
        # Add email information
        emails = user.get("Emails", [])
        if emails:
            for i, email in enumerate(emails):
                email_label = "Email"
                if len(emails) > 1:
                    email_label = f"Email {i+1}"
                if email.get("Primary", False):
                    email_label += " (Primary)"
                table.add_row(email_label, email.get("Value", ""))
        
        # Add phone numbers if available
        phone_numbers = user.get("PhoneNumbers", [])
        if phone_numbers:
            for i, phone in enumerate(phone_numbers):
                phone_label = "Phone"
                if len(phone_numbers) > 1:
                    phone_label = f"Phone {i+1}"
                if phone.get("Primary", False):
                    phone_label += " (Primary)"
                table.add_row(phone_label, phone.get("Value", ""))
        
        # Add addresses if available
        addresses = user.get("Addresses", [])
        if addresses:
            for i, address in enumerate(addresses):
                address_label = "Address"
                if len(addresses) > 1:
                    address_label = f"Address {i+1}"
                if address.get("Primary", False):
                    address_label += " (Primary)"
                
                # Format address components
                address_parts = []
                if address.get("StreetAddress"):
                    address_parts.append(address.get("StreetAddress"))
                if address.get("Locality"):
                    address_parts.append(address.get("Locality"))
                if address.get("Region"):
                    address_parts.append(address.get("Region"))
                if address.get("PostalCode"):
                    address_parts.append(address.get("PostalCode"))
                if address.get("Country"):
                    address_parts.append(address.get("Country"))
                
                formatted_address = ", ".join(address_parts)
                table.add_row(address_label, formatted_address)
        
        # Add status information
        if user.get("Status"):
            status = user.get("Status", "")
            status_style = "green" if status == "ENABLED" else "yellow"
            table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
        
        # Add creation and modification timestamps if available
        if user.get("CreatedDate"):
            from datetime import datetime
            created_date = user.get("CreatedDate")
            if isinstance(created_date, datetime):
                table.add_row("Created", created_date.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                table.add_row("Created", str(created_date))
                
        if user.get("LastModifiedDate"):
            from datetime import datetime
            modified_date = user.get("LastModifiedDate")
            if isinstance(modified_date, datetime):
                table.add_row("Last Modified", modified_date.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                table.add_row("Last Modified", str(modified_date))
        
        # Add external IDs if available
        external_ids = user.get("ExternalIds", [])
        if external_ids:
            for i, ext_id in enumerate(external_ids):
                ext_id_label = "External ID"
                if len(external_ids) > 1:
                    ext_id_label = f"External ID {i+1}"
                if ext_id.get("Issuer"):
                    ext_id_label += f" ({ext_id.get('Issuer')})"
                table.add_row(ext_id_label, ext_id.get("Id", ""))
        
        # Add user type if available
        if user.get("UserType"):
            table.add_row("User Type", user.get("UserType", ""))
        
        # Add any custom attributes if available
        custom_attributes = user.get("CustomAttributes", {})
        if custom_attributes:
            for key, value in custom_attributes.items():
                table.add_row(f"Custom: {key}", str(value))
        
        # Create a title for the panel
        display_name = user.get("DisplayName", "")
        username = user.get("UserName", "")
        user_id_short = user.get("UserId", "")[:8] + "..." if user.get("UserId") else ""
        
        if display_name:
            title = f"{display_name} ({username})"
        else:
            title = username or user_id_short
        
        # Create a panel with the table
        panel = Panel(
            table,
            title=f"[bold green]User Details: {title}[/bold green]",
            border_style="blue",
            expand=False
        )
        
        # Display the panel
        console.print(panel)
        
        # Return the user data for further processing if needed
        return user
        
    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        
        # Handle specific error cases
        if error_code == "ResourceNotFoundException":
            console.print(f"[red]Error: User '{identifier}' not found.[/red]")
            console.print("Please check the user ID and try again.")
        else:
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("create")
def create_user(
    username: str = typer.Option(..., "--username", help="Username for the new user (required)"),
    email: str = typer.Option(..., "--email", help="Email address for the new user (required)"),
    given_name: Optional[str] = typer.Option(None, "--given-name", help="User's first name (optional)"),
    family_name: Optional[str] = typer.Option(None, "--family-name", help="User's last name (optional)"),
    display_name: Optional[str] = typer.Option(None, "--display-name", help="Display name for the user (optional)"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"),
):
    """Create a new user in the Identity Store.
    
    Creates a new user with the specified attributes and displays the new user's details.
    Username and email are required. Name fields are optional.
    Validates that the username is unique before creating the user.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)
        
        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)
        
        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        
        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()
        
        # Validate required parameters
        if not username:
            console.print("[red]Error: Username is required.[/red]")
            raise typer.Exit(1)
            
        if not email:
            console.print("[red]Error: Email is required.[/red]")
            raise typer.Exit(1)
            
        # Validate email format (basic check)
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            console.print("[red]Error: Invalid email format.[/red]")
            raise typer.Exit(1)
            
        # Prepare user attributes for the API call
        user_attributes = {
            "UserName": username,
            "Emails": [
                {
                    "Value": email,
                    "Primary": True
                }
            ]
        }
        
        # Add name information if provided
        if given_name or family_name:
            name_dict = {}
            if given_name:
                name_dict["GivenName"] = given_name
            if family_name:
                name_dict["FamilyName"] = family_name
            user_attributes["Name"] = name_dict
            
        # Add display name if provided
        if display_name:
            user_attributes["DisplayName"] = display_name
            
        # Log the operation
        console.print(f"[blue]Creating user '{username}' in Identity Store {identity_store_id}...[/blue]")
        
        # Check if a user with the same username already exists
        try:
            # Search for existing user with the same username
            search_response = identity_store.list_users(
                IdentityStoreId=identity_store_id,
                Filters=[
                    {
                        "AttributePath": "UserName",
                        "AttributeValue": username
                    }
                ]
            )
            
            existing_users = search_response.get("Users", [])
            if existing_users:
                console.print(f"[red]Error: A user with username '{username}' already exists.[/red]")
                console.print("Please choose a different username.")
                raise typer.Exit(1)
                
        except ClientError as search_error:
            # If the search fails, log the error but continue with creation attempt
            console.print(f"[yellow]Warning: Could not check for existing username: {search_error}[/yellow]")
        
        # Make the API call to create the user
        try:
            response = identity_store.create_user(
                IdentityStoreId=identity_store_id,
                **user_attributes
            )
            
            # Extract the user ID from the response
            user_id = response.get("UserId")
            
            # Display success message
            console.print(f"[green]User created successfully![/green]")
            
            # Get the full user details to display
            try:
                # Make the API call to describe the user
                user_details = identity_store.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id
                )
                
                # Create a rich panel for displaying user details
                from rich.panel import Panel
                from rich.table import Table
                
                # Create a table for displaying user details
                table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
                table.add_column("Field", style="cyan", width=20)
                table.add_column("Value", style="white")
                
                # Add basic user information
                table.add_row("User ID", user_details.get("UserId", ""))
                table.add_row("Username", user_details.get("UserName", ""))
                
                # Add name information
                name_info = user_details.get("Name", {})
                if name_info.get("GivenName"):
                    table.add_row("Given Name", name_info.get("GivenName", ""))
                if name_info.get("FamilyName"):
                    table.add_row("Family Name", name_info.get("FamilyName", ""))
                if user_details.get("DisplayName"):
                    table.add_row("Display Name", user_details.get("DisplayName", ""))
                
                # Add email information
                emails = user_details.get("Emails", [])
                if emails:
                    for i, email in enumerate(emails):
                        email_label = "Email"
                        if len(emails) > 1:
                            email_label = f"Email {i+1}"
                        if email.get("Primary", False):
                            email_label += " (Primary)"
                        table.add_row(email_label, email.get("Value", ""))
                
                # Add status information
                if user_details.get("Status"):
                    status = user_details.get("Status", "")
                    status_style = "green" if status == "ENABLED" else "yellow"
                    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
                
                # Create a title for the panel
                display_name = user_details.get("DisplayName", "")
                username = user_details.get("UserName", "")
                
                if display_name:
                    title = f"{display_name} ({username})"
                else:
                    title = username
                
                # Create a panel with the table
                panel = Panel(
                    table,
                    title=f"[bold green]New User Created: {title}[/bold green]",
                    border_style="blue",
                    expand=False
                )
                
                # Display the panel
                console.print(panel)
                
            except ClientError as detail_error:
                # If we can't get detailed information, just show the basic info
                console.print(f"[green]User ID: {user_id}[/green]")
                console.print("[yellow]Could not retrieve detailed user information.[/yellow]")
            
            # Return the user ID and attributes for further processing if needed
            return user_id, user_attributes
            
        except ClientError as create_error:
            error_code = create_error.response.get("Error", {}).get("Code", "Unknown")
            error_message = create_error.response.get("Error", {}).get("Message", str(create_error))
            
            # Handle specific error cases
            if "DuplicateValue" in error_code or "already exists" in error_message.lower():
                console.print(f"[red]Error: A user with username '{username}' already exists.[/red]")
                console.print("Please choose a different username.")
            else:
                console.print(f"[red]Error creating user: {error_message} (Code: {error_code})[/red]")
            raise typer.Exit(1)
        
    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        
        # Handle specific error cases
        if error_code == "ResourceNotFoundException":
            console.print("[red]Error: Identity Store not found.[/red]")
            console.print("Please check your SSO configuration and try again.")
        elif error_code == "ValidationException":
            console.print(f"[red]Error: {error_message}[/red]")
        else:
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("update")
def update_user(
    user_id: str = typer.Argument(..., help="User ID of the user to update"),
    username: Optional[str] = typer.Option(None, "--username", help="Updated username"),
    email: Optional[str] = typer.Option(None, "--email", help="Updated email address"),
    given_name: Optional[str] = typer.Option(None, "--given-name", help="Updated first name"),
    family_name: Optional[str] = typer.Option(None, "--family-name", help="Updated last name"),
    display_name: Optional[str] = typer.Option(None, "--display-name", help="Updated display name (Note: AWS API currently doesn't support updating display name)"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"),
):
    """Update an existing user in the Identity Store.
    
    Updates user attributes for the specified user ID. At least one attribute must be provided to update.
    Displays the updated user details after successful update.
    If no attributes are provided to update, a message will indicate that no changes were made.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)
        
        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)
        
        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        
        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()
        
        # Check if any update parameters were provided
        if not any([username, email, given_name, family_name, display_name]):
            console.print("[yellow]No update parameters provided. No changes will be made.[/yellow]")
            raise typer.Exit(0)
        
        # Validate email format if provided
        if email:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                console.print("[red]Error: Invalid email format.[/red]")
                raise typer.Exit(1)
        
        # Log the operation
        console.print(f"[blue]Updating user with ID '{user_id}' in Identity Store {identity_store_id}...[/blue]")
        
        # First, check if the user exists
        try:
            # Make the API call to describe the user
            existing_user = identity_store.describe_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            
            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: User with ID '{user_id}' not found.[/red]")
                console.print("Please check the user ID and try again.")
            else:
                console.print(f"[red]Error ({error_code}): {error_message}[/red]")
            raise typer.Exit(1)
            
        # Prepare operations for the update
        operations = []
        
        # Add username update if provided
        if username:
            operations.append({
                "AttributePath": "UserName",
                "AttributeValue": username
            })
        
        # Add email update if provided
        if email:
            operations.append({
                "AttributePath": "Emails",
                "AttributeValue": [
                    {
                        "Value": email,
                        "Primary": True
                    }
                ]
            })
        
        # Add name updates if provided
        if given_name or family_name:
            # Get existing name data
            existing_name = existing_user.get("Name", {})
            
            # Update with new values
            name_dict = {}
            if given_name:
                name_dict["GivenName"] = given_name
            elif existing_name.get("GivenName"):
                name_dict["GivenName"] = existing_name.get("GivenName")
                
            if family_name:
                name_dict["FamilyName"] = family_name
            elif existing_name.get("FamilyName"):
                name_dict["FamilyName"] = existing_name.get("FamilyName")
            
            if name_dict:
                operations.append({
                    "AttributePath": "Name",
                    "AttributeValue": name_dict
                })
        
        # Add display name update if provided
        # Note: AWS Identity Store API currently doesn't support updating DisplayName directly
        # We'll warn the user about this limitation
        if display_name:
            console.print("[yellow]Warning: AWS Identity Store API does not support updating DisplayName directly.[/yellow]")
            console.print("[yellow]The DisplayName parameter will be ignored.[/yellow]")
            # We don't add this to operations since it's not supported
            
        # Make the API call to update the user
        try:
            # Check if there are any operations to perform
            if not operations:
                console.print("[yellow]No changes to make. User remains unchanged.[/yellow]")
                return existing_user
                
            # Log what we're updating
            update_fields = []
            for op in operations:
                field = op["AttributePath"]
                if field == "Emails":
                    update_fields.append("email")
                elif field == "Name":
                    if "GivenName" in op["AttributeValue"]:
                        update_fields.append("given name")
                    if "FamilyName" in op["AttributeValue"]:
                        update_fields.append("family name")
                else:
                    update_fields.append(field.lower())
                    
            # If no operations are left after filtering out unsupported attributes
            if not update_fields:
                console.print("[yellow]No supported attributes to update. User remains unchanged.[/yellow]")
                return existing_user
                    
            console.print(f"[blue]Updating {', '.join(update_fields)}...[/blue]")
            
            # Perform the update
            identity_store.update_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id,
                Operations=operations
            )
            
            # Display success message
            console.print(f"[green]User updated successfully![/green]")
            
            # Get the updated user details to display
            try:
                # Make the API call to describe the user
                updated_user = identity_store.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id
                )
                
                # Display the updated user details
                from rich.panel import Panel
                from rich.table import Table
                
                # Create a table for displaying user details
                table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
                table.add_column("Field", style="cyan", width=20)
                table.add_column("Value", style="white")
                
                # Add basic user information
                table.add_row("User ID", updated_user.get("UserId", ""))
                table.add_row("Username", updated_user.get("UserName", ""))
                
                # Add name information
                name_info = updated_user.get("Name", {})
                if name_info.get("GivenName"):
                    table.add_row("Given Name", name_info.get("GivenName", ""))
                if name_info.get("FamilyName"):
                    table.add_row("Family Name", name_info.get("FamilyName", ""))
                if updated_user.get("DisplayName"):
                    table.add_row("Display Name", updated_user.get("DisplayName", ""))
                
                # Add email information
                emails = updated_user.get("Emails", [])
                if emails:
                    for i, email in enumerate(emails):
                        email_label = "Email"
                        if len(emails) > 1:
                            email_label = f"Email {i+1}"
                        if email.get("Primary", False):
                            email_label += " (Primary)"
                        table.add_row(email_label, email.get("Value", ""))
                
                # Add status information
                if updated_user.get("Status"):
                    status = updated_user.get("Status", "")
                    status_style = "green" if status == "ENABLED" else "yellow"
                    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
                
                # Add last modified timestamp if available
                if updated_user.get("LastModifiedDate"):
                    from datetime import datetime
                    modified_date = updated_user.get("LastModifiedDate")
                    if isinstance(modified_date, datetime):
                        table.add_row("Last Modified", modified_date.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        table.add_row("Last Modified", str(modified_date))
                
                # Create a title for the panel
                display_name = updated_user.get("DisplayName", "")
                username = updated_user.get("UserName", "")
                
                if display_name:
                    title = f"{display_name} ({username})"
                else:
                    title = username
                
                # Create a panel with the table
                panel = Panel(
                    table,
                    title=f"[bold green]Updated User: {title}[/bold green]",
                    border_style="blue",
                    expand=False
                )
                
                # Display the panel
                console.print(panel)
                
                # Return the updated user data for further processing if needed
                return updated_user
                
            except ClientError as detail_error:
                error_code = detail_error.response.get("Error", {}).get("Code", "Unknown")
                error_message = detail_error.response.get("Error", {}).get("Message", str(detail_error))
                # If we can't get detailed information, just show success message
                console.print("[yellow]User was updated, but could not retrieve updated user information.[/yellow]")
                console.print(f"[yellow]Error: {error_message} (Code: {error_code})[/yellow]")
            
        except ClientError as update_error:
            error_code = update_error.response.get("Error", {}).get("Code", "Unknown")
            error_message = update_error.response.get("Error", {}).get("Message", str(update_error))
            
            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: User with ID '{user_id}' not found.[/red]")
                console.print("Please check the user ID and try again.")
            elif "DuplicateValue" in error_code or "already exists" in error_message.lower():
                console.print(f"[red]Error: The provided value already exists for another user.[/red]")
                console.print("Please choose different values and try again.")
            else:
                console.print(f"[red]Error updating user: {error_message} (Code: {error_code})[/red]")
            raise typer.Exit(1)
        
    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        
        # Handle specific error cases
        if error_code == "ResourceNotFoundException":
            console.print("[red]Error: Identity Store not found.[/red]")
            console.print("Please check your SSO configuration and try again.")
        elif error_code == "ValidationException":
            console.print(f"[red]Error: {error_message}[/red]")
        else:
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_user(
    user_id: str = typer.Argument(..., help="User ID of the user to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"),
):
    """Delete a user from the Identity Store.
    
    Removes the specified user from the Identity Store. By default, prompts for confirmation
    before deletion. Use the --force option to skip the confirmation prompt.
    Displays a confirmation message after successful deletion.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)
        
        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)
        
        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)
        
        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()
        
        # Verify the user exists before attempting to delete
        try:
            # Make the API call to describe the user
            user_details = identity_store.describe_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id
            )
            
            # Get the username for confirmation message
            username = user_details.get("UserName", "Unknown")
            
            # Log the operation
            console.print(f"[blue]Preparing to delete user '{username}' (ID: {user_id}) from Identity Store {identity_store_id}...[/blue]")
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            # Handle user not found error
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: User with ID '{user_id}' not found.[/red]")
                console.print("Please check the user ID and try again.")
                raise typer.Exit(1)
            else:
                # Re-raise other errors to be caught by the outer try-except
                raise
        
        # Check if force option is used, otherwise prompt for confirmation
        if not force:
            console.print(f"[yellow]Warning: This will permanently delete user '{username}' (ID: {user_id}).[/yellow]")
            console.print("[yellow]This action cannot be undone.[/yellow]")
            console.print("\n[blue]Are you sure you want to continue? (y/N)[/blue]")
            
            try:
                # Wait for user input
                confirmation = get_single_key().lower()
                
                # Check if the user confirmed the deletion
                if confirmation != 'y':
                    console.print("\n[yellow]User deletion cancelled.[/yellow]")
                    raise typer.Exit(0)
                    
                console.print()  # Add a newline for better formatting
                
            except KeyboardInterrupt:
                console.print("\n[yellow]User deletion cancelled.[/yellow]")
                raise typer.Exit(0)
        
        # Make the API call to delete the user
        try:
            identity_store.delete_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id
            )
            
            # Display success message with enhanced formatting using Rich
            from rich.panel import Panel
            from rich.table import Table
            
            # Create a table for displaying deletion details
            table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
            table.add_column("Field", style="cyan", width=20)
            table.add_column("Value", style="white")
            
            # Add user information to the table
            table.add_row("User ID", user_id)
            table.add_row("Username", username)
            
            # Add additional information if available
            if user_details.get("DisplayName"):
                table.add_row("Display Name", user_details.get("DisplayName"))
                
            # Add email information if available
            emails = user_details.get("Emails", [])
            if emails:
                for email in emails:
                    if email.get("Primary", False):
                        table.add_row("Email", email.get("Value", ""))
                        break
            
            # Create a panel with the table
            panel = Panel(
                table,
                title="[bold green]User Successfully Deleted[/bold green]",
                border_style="blue",
                expand=False
            )
            
            # Display the panel
            console.print(panel)
            
            return True
            
        except ClientError as delete_error:
            error_code = delete_error.response.get("Error", {}).get("Code", "Unknown")
            error_message = delete_error.response.get("Error", {}).get("Message", str(delete_error))
            
            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: User with ID '{user_id}' not found or already deleted.[/red]")
            else:
                console.print(f"[red]Error deleting user: ({error_code}): {error_message}[/red]")
            
            raise typer.Exit(1)
        
    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)