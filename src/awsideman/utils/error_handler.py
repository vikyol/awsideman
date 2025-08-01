"""Error handling utilities for awsideman."""
import typer
from rich.console import Console
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from typing import Optional, Dict, Any, Callable
import time
import functools

console = Console()

# Common AWS API error codes and their user-friendly messages
AWS_ERROR_MESSAGES = {
    # Access and authentication errors
    "AccessDeniedException": "You do not have sufficient permissions to perform this action.",
    "UnauthorizedException": "You are not authorized to perform this action.",
    "InvalidCredentialsException": "The provided credentials are invalid or expired.",
    "ExpiredTokenException": "Your authentication token has expired. Please refresh your credentials.",
    "TokenExpiredException": "Your authentication token has expired. Please refresh your credentials.",
    "AuthorizationErrorException": "You are not authorized to perform this action.",
    
    # Resource errors
    "ResourceNotFoundException": "The requested resource was not found.",
    "ResourceExistsException": "The resource already exists.",
    "ConflictException": "The request could not be completed due to a conflict with the current state of the resource.",
    "LimitExceededException": "You have exceeded the allowed limit for this resource or operation.",
    "ServiceQuotaExceededException": "You have exceeded the service quota for this resource.",
    
    # Validation errors
    "ValidationException": "The input parameters are invalid.",
    "InvalidParameterException": "One or more parameters are invalid.",
    "MissingParameterException": "A required parameter is missing.",
    "InvalidInputException": "The input is invalid.",
    
    # Service errors
    "ServiceException": "An error occurred in the AWS service.",
    "InternalServerException": "An internal server error occurred.",
    "ServiceUnavailableException": "The service is currently unavailable. Please try again later.",
    "ThrottlingException": "The request was denied due to request throttling. Please reduce the frequency of requests.",
    
    # Network errors
    "RequestTimeoutException": "The request timed out. Please try again.",
    "ConnectionClosedException": "The connection was closed unexpectedly. Please try again.",
}

# Permission guidance for common operations
PERMISSION_GUIDANCE = {
    # Group operations
    "ListGroups": [
        "identitystore:ListGroups",
        "sso:ListInstances"
    ],
    "DescribeGroup": [
        "identitystore:DescribeGroup",
        "sso:ListInstances"
    ],
    "CreateGroup": [
        "identitystore:CreateGroup",
        "sso:ListInstances"
    ],
    "UpdateGroup": [
        "identitystore:UpdateGroup",
        "sso:ListInstances"
    ],
    "DeleteGroup": [
        "identitystore:DeleteGroup",
        "sso:ListInstances"
    ],
    
    # Group membership operations
    "ListGroupMemberships": [
        "identitystore:ListGroupMemberships",
        "sso:ListInstances"
    ],
    "CreateGroupMembership": [
        "identitystore:CreateGroupMembership",
        "identitystore:DescribeGroup",
        "identitystore:DescribeUser",
        "sso:ListInstances"
    ],
    "DeleteGroupMembership": [
        "identitystore:DeleteGroupMembership",
        "identitystore:DescribeGroup",
        "identitystore:DescribeUser",
        "sso:ListInstances"
    ],
    
    # User operations
    "ListUsers": [
        "identitystore:ListUsers",
        "sso:ListInstances"
    ],
    "DescribeUser": [
        "identitystore:DescribeUser",
        "sso:ListInstances"
    ],
    "CreateUser": [
        "identitystore:CreateUser",
        "sso:ListInstances"
    ],
    "UpdateUser": [
        "identitystore:UpdateUser",
        "sso:ListInstances"
    ],
    "DeleteUser": [
        "identitystore:DeleteUser",
        "sso:ListInstances"
    ],
}

# IAM policy templates for common operations
IAM_POLICY_TEMPLATES = {
    "GroupManagement": {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "identitystore:ListGroups",
                    "identitystore:DescribeGroup",
                    "identitystore:CreateGroup",
                    "identitystore:UpdateGroup",
                    "identitystore:DeleteGroup",
                    "identitystore:ListGroupMemberships",
                    "identitystore:CreateGroupMembership",
                    "identitystore:DeleteGroupMembership",
                    "sso:ListInstances"
                ],
                "Resource": "*"
            }
        ]
    },
    "ReadOnlyAccess": {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "identitystore:ListGroups",
                    "identitystore:DescribeGroup",
                    "identitystore:ListUsers",
                    "identitystore:DescribeUser",
                    "identitystore:ListGroupMemberships",
                    "sso:ListInstances"
                ],
                "Resource": "*"
            }
        ]
    }
}


def handle_aws_error(e: ClientError, operation: Optional[str] = None) -> None:
    """
    Handle AWS API errors with clear messages and guidance.
    
    Args:
        e: The ClientError exception
        operation: The operation being performed (e.g., 'ListGroups')
        
    Raises:
        typer.Exit: Always raises typer.Exit(1) after displaying error message
    """
    error_code = e.response.get("Error", {}).get("Code", "Unknown")
    error_message = e.response.get("Error", {}).get("Message", str(e))
    
    # Get user-friendly message if available
    friendly_message = AWS_ERROR_MESSAGES.get(error_code, error_message)
    
    # Display the error with code and message
    console.print(f"[red]Error ({error_code}): {friendly_message}[/red]")
    
    # Add specific guidance based on error code
    if error_code == "AccessDeniedException" or error_code == "UnauthorizedException":
        console.print("[yellow]This is a permissions issue. You need additional permissions to perform this action.[/yellow]")
        
        # If we know the operation, provide specific permission guidance
        if operation and operation in PERMISSION_GUIDANCE:
            console.print("[yellow]You may need the following permissions:[/yellow]")
            for permission in PERMISSION_GUIDANCE[operation]:
                console.print(f"  - {permission}")
            
            # Suggest an IAM policy template
            if "Group" in operation:
                console.print("\n[yellow]Example IAM policy for group management:[/yellow]")
                import json
                policy_json = json.dumps(IAM_POLICY_TEMPLATES["GroupManagement"], indent=2)
                console.print(f"```json\n{policy_json}\n```")
            elif operation in ["ListGroups", "DescribeGroup", "ListUsers", "DescribeUser", "ListGroupMemberships"]:
                console.print("\n[yellow]Example IAM policy for read-only access:[/yellow]")
                import json
                policy_json = json.dumps(IAM_POLICY_TEMPLATES["ReadOnlyAccess"], indent=2)
                console.print(f"```json\n{policy_json}\n```")
                
        console.print("\n[yellow]Troubleshooting steps for permission issues:[/yellow]")
        console.print("  1. Check if your IAM user or role has the necessary permissions")
        console.print("  2. Check if there are any IAM permission boundaries restricting your access")
        console.print("  3. Check if there are any resource-based policies denying access")
        console.print("  4. Check if there are any SCPs (Service Control Policies) restricting access")
        console.print("  5. Contact your AWS administrator if you need these permissions")
        
    elif error_code == "ResourceNotFoundException":
        console.print("[yellow]The resource you're trying to access doesn't exist. Check the identifier and try again.[/yellow]")
        
    elif error_code == "ValidationException" or error_code == "InvalidParameterException":
        console.print("[yellow]Check your input parameters and try again.[/yellow]")
        
    elif error_code == "ThrottlingException":
        console.print("[yellow]You're making too many requests too quickly. Try again after a short delay.[/yellow]")
        console.print("[yellow]Consider adding a delay between commands if you're running automated scripts.[/yellow]")
        
    elif error_code == "ServiceUnavailableException":
        console.print("[yellow]AWS service is temporarily unavailable. Please try again later.[/yellow]")
        console.print("[yellow]Check the AWS Service Health Dashboard for any ongoing issues: https://status.aws.amazon.com/[/yellow]")
        
    # Raise typer.Exit to terminate the command
    raise typer.Exit(1)


def handle_network_error(e: Exception) -> None:
    """
    Handle network-related errors with clear messages.
    
    Args:
        e: The exception
        
    Raises:
        typer.Exit: Always raises typer.Exit(1) after displaying error message
    """
    # Determine the type of network error
    if isinstance(e, ConnectionError):
        console.print("[red]Error: Network connection failed.[/red]")
        console.print("[yellow]Please check your internet connection and try again.[/yellow]")
    elif isinstance(e, EndpointConnectionError):
        console.print("[red]Error: Could not connect to AWS endpoint.[/red]")
        console.print("[yellow]This could be due to an incorrect region or endpoint configuration.[/yellow]")
    else:
        console.print(f"[red]Error: Network operation failed: {str(e)}[/red]")
        
    console.print("\n[yellow]Troubleshooting tips:[/yellow]")
    console.print("  1. Check your internet connection")
    console.print("  2. Verify your AWS region is correct in your profile configuration")
    console.print("  3. Check if you're behind a corporate proxy or firewall that might block AWS API calls")
    console.print("  4. Check if AWS service status page reports any outages: https://status.aws.amazon.com/")
    console.print("  5. Try using a different network connection")
    console.print("  6. Try again after a few minutes")
    
    console.print("\n[yellow]Network diagnostics:[/yellow]")
    try:
        import socket
        # Try to resolve AWS domain to check DNS
        try:
            socket.gethostbyname("identitystore.amazonaws.com")
            console.print("  ✓ DNS resolution: Working")
        except socket.gaierror:
            console.print("  ✗ DNS resolution: Failed (Could not resolve AWS domain)")
            
        # Try to connect to AWS endpoint to check connectivity
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("identitystore.us-east-1.amazonaws.com", 443))
            s.close()
            console.print("  ✓ Endpoint connectivity: Working")
        except (socket.timeout, socket.error):
            console.print("  ✗ Endpoint connectivity: Failed (Could not connect to AWS endpoint)")
    except Exception:
        # Ignore any errors in the diagnostic code
        pass
    
    # Raise typer.Exit to terminate the command
    raise typer.Exit(1)


def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0, 
               jitter: float = 0.1, max_delay: float = 30.0,
               retryable_errors: tuple = (ConnectionError, EndpointConnectionError, 
                                         "ThrottlingException", "ServiceUnavailableException",
                                         "RequestTimeoutException", "InternalServerException")):
    """
    Decorator to retry functions on specific exceptions with exponential backoff and jitter.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for subsequent retries
        jitter: Random jitter factor to add to delay (as a fraction of delay)
        max_delay: Maximum delay between retries in seconds
        retryable_errors: Tuple of exceptions or error codes to retry on
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    
                    # Check if this error code is retryable
                    if error_code in retryable_errors:
                        last_exception = e
                        if attempt < max_retries:
                            # Add jitter to delay for better distribution of retries
                            import random
                            jitter_value = random.uniform(-jitter * current_delay, jitter * current_delay)
                            actual_delay = min(current_delay + jitter_value, max_delay)
                            actual_delay = max(actual_delay, 0.1)  # Ensure minimum delay of 0.1s
                            
                            console.print(f"[yellow]Request failed with {error_code}. Retrying in {actual_delay:.1f} seconds... (Attempt {attempt + 1}/{max_retries})[/yellow]")
                            time.sleep(actual_delay)
                            current_delay = min(current_delay * backoff, max_delay)
                            continue
                    
                    # Not retryable or max retries reached
                    raise
                except Exception as e:
                    # Check if this exception type is retryable
                    if any(isinstance(e, err) for err in retryable_errors if isinstance(err, type)):
                        last_exception = e
                        if attempt < max_retries:
                            # Add jitter to delay for better distribution of retries
                            import random
                            jitter_value = random.uniform(-jitter * current_delay, jitter * current_delay)
                            actual_delay = min(current_delay + jitter_value, max_delay)
                            actual_delay = max(actual_delay, 0.1)  # Ensure minimum delay of 0.1s
                            
                            console.print(f"[yellow]Request failed with {type(e).__name__}. Retrying in {actual_delay:.1f} seconds... (Attempt {attempt + 1}/{max_retries})[/yellow]")
                            time.sleep(actual_delay)
                            current_delay = min(current_delay * backoff, max_delay)
                            continue
                    
                    # Not retryable or max retries reached
                    raise
            
            # If we get here, all retries failed
            if isinstance(last_exception, ClientError):
                console.print("[red]All retry attempts failed.[/red]")
                handle_aws_error(last_exception)
            else:
                console.print("[red]All retry attempts failed.[/red]")
                handle_network_error(last_exception)
                
        return wrapper
    return decorator

def check_network_connectivity(region: Optional[str] = None) -> bool:
    """
    Check network connectivity to AWS endpoints.
    
    Args:
        region: AWS region to check connectivity for
        
    Returns:
        True if connectivity is good, False otherwise
    """
    try:
        import socket
        
        # Default to us-east-1 if no region is provided
        region = region or "us-east-1"
        
        # Try to resolve AWS domain to check DNS
        try:
            socket.gethostbyname(f"identitystore.{region}.amazonaws.com")
        except socket.gaierror:
            console.print("[yellow]Warning: Could not resolve AWS domain. DNS resolution may be failing.[/yellow]")
            return False
            
        # Try to connect to AWS endpoint to check connectivity
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((f"identitystore.{region}.amazonaws.com", 443))
            s.close()
            return True
        except (socket.timeout, socket.error):
            console.print("[yellow]Warning: Could not connect to AWS endpoint. Network connectivity may be failing.[/yellow]")
            return False
    except Exception:
        # Ignore any errors in the diagnostic code
        return True  # Assume connectivity is good if we can't check