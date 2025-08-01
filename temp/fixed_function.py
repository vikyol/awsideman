def validate_permission_set_name(name: str) -> bool:
    """
    Validate a permission set name.
    
    Args:
        name: The permission set name to validate
        
    Returns:
        True if the name is valid, False otherwise
        
    Raises:
        typer.Exit: If validation fails
    """
    if not name or name.strip() == "":
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        return False
        
    # Check length
    if len(name) > 32:
        console.print("[red]Error: Permission set name cannot exceed 32 characters.[/red]")
        return False
        
    # Check for invalid characters
    if not re.match(r'^[a-zA-Z0-9+=,.@_-]+$', name):
        console.print("[red]Error: Permission set name contains invalid characters.[/red]")
        console.print("[yellow]Permission set names can only contain alphanumeric characters and the following special characters: +=,.@_-[/yellow]")
        return False
        
    return True

@app.command("delete")
