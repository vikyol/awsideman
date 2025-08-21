"""Tests for cache warm command."""

import pytest
from unittest.mock import Mock, patch


def test_warm_cache_module_import():
    """Test that the warm_cache module can be imported."""
    try:
        from src.awsideman.commands.cache.warm import warm_cache

        assert warm_cache is not None
        assert callable(warm_cache)
    except ImportError as e:
        pytest.fail(f"Failed to import warm_cache: {e}")


def test_warm_cache_function_signature():
    """Test that the warm_cache function has the expected signature."""
    import inspect

    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function exists and is callable
    assert callable(warm_cache)

    # Check that it has the expected parameters
    sig = inspect.signature(warm_cache)
    expected_params = {"command", "profile", "region"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_warm_cache_help_text():
    """Test that the warm_cache function has help text."""
    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function has a docstring
    assert warm_cache.__doc__ is not None
    assert len(warm_cache.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = warm_cache.__doc__.lower()
    assert "warm" in doc
    assert "cache" in doc
    assert "command" in doc


def test_warm_cache_typer_integration():
    """Test that the warm_cache function is properly integrated with Typer."""
    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function has the expected type hints
    assert hasattr(warm_cache, "__annotations__")

    annotations = warm_cache.__annotations__
    assert "command" in annotations
    assert "profile" in annotations
    assert "region" in annotations


def test_warm_cache_parameter_types():
    """Test that the warm_cache function has correct parameter types."""
    import inspect

    from src.awsideman.commands.cache.warm import warm_cache

    sig = inspect.signature(warm_cache)

    # Check that command is a string
    assert sig.parameters["command"].annotation == str

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)

    # Check that region is optional string
    region_param = sig.parameters["region"]
    assert region_param.annotation == str or "Optional" in str(region_param.annotation)


@patch("src.awsideman.commands.cache.warm._execute_command_with_cli_runner")
@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_successful_execution(mock_get_cache_manager, mock_execute_command):
    """Test successful cache warming execution."""
    from src.awsideman.commands.cache.warm import warm_cache
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_cache_manager.get_cache_stats.side_effect = [
        {"total_entries": 10},  # Before
        {"total_entries": 15}   # After
    ]
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock command execution
    mock_execute_command.return_value = None
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        warm_cache("user list")
        
        # Verify cache manager was called
        assert mock_cache_manager.get_cache_stats.call_count == 2
        
        # Verify command execution was called (check first argument which should be the command parts)
        mock_execute_command.assert_called_once()
        call_args = mock_execute_command.call_args[0]
        assert call_args[0] == ["user", "list"]  # First argument should be command parts
        
        # Verify success message was printed
        mock_console.print.assert_any_call("[green]✓ Cache warmed successfully! Added 5 new cache entries.[/green]")


@patch("src.awsideman.commands.cache.warm._execute_command_with_cli_runner")
@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_no_new_entries(mock_get_cache_manager, mock_execute_command):
    """Test cache warming when no new entries are added."""
    from src.awsideman.commands.cache.warm import warm_cache
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_cache_manager.get_cache_stats.side_effect = [
        {"total_entries": 10},  # Before
        {"total_entries": 10}   # After (no change)
    ]
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock command execution
    mock_execute_command.return_value = None
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        warm_cache("user list")
        
        # Verify success message was printed
        mock_console.print.assert_any_call("[yellow]Cache was already warm for this command (no new entries added).[/yellow]")


@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_disabled(mock_get_cache_manager):
    """Test cache warming when cache is disabled."""
    from src.awsideman.commands.cache.warm import warm_cache
    
    # Mock cache manager with disabled cache
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = False
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        warm_cache("user list")
        
        # Verify warning message was printed
        mock_console.print.assert_any_call("[yellow]Cache is disabled. Cannot warm cache.[/yellow]")


@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_invalid_command(mock_get_cache_manager):
    """Test cache warming with invalid command."""
    from src.awsideman.commands.cache.warm import warm_cache
    import typer
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        with pytest.raises(typer.Exit):
            warm_cache("invalid_command")
        
        # Verify error message was printed
        mock_console.print.assert_any_call("[red]Error: Unknown command 'invalid_command'. Valid commands: user, group, permission-set, assignment, org, profile, sso[/red]")


@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_recursion_prevention(mock_get_cache_manager):
    """Test that cache warming prevents recursion by blocking cache commands."""
    from src.awsideman.commands.cache.warm import warm_cache
    import typer
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        with pytest.raises(typer.Exit):
            warm_cache("cache clear")
        
        # Verify error message was printed
        mock_console.print.assert_any_call("[red]Error: Cannot warm cache commands (would cause recursion)[/red]")


@patch("src.awsideman.commands.cache.warm._execute_command_with_cli_runner")
@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_with_profile_and_region(mock_get_cache_manager, mock_execute_command):
    """Test cache warming with profile and region options."""
    from src.awsideman.commands.cache.warm import warm_cache
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_cache_manager.get_cache_stats.side_effect = [
        {"total_entries": 10},  # Before
        {"total_entries": 12}   # After
    ]
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock command execution
    mock_execute_command.return_value = None
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        warm_cache("user list", profile="test-profile", region="us-west-2")
        
        # Verify command execution was called with profile and region
        mock_execute_command.assert_called_once_with(["user", "list"], "test-profile", "us-west-2")
        
        # Verify profile info was displayed
        mock_console.print.assert_any_call("[blue]Warming cache for command: user list (profile: test-profile, region: us-west-2)[/blue]")


@patch("src.awsideman.commands.cache.warm._execute_command_with_cli_runner")
@patch("src.awsideman.commands.cache.warm.get_cache_manager")
def test_warm_cache_command_execution_failure(mock_get_cache_manager, mock_execute_command):
    """Test cache warming when command execution fails."""
    from src.awsideman.commands.cache.warm import warm_cache
    import typer
    
    # Mock cache manager
    mock_cache_manager = Mock()
    mock_cache_manager.config.enabled = True
    mock_cache_manager.get_cache_stats.return_value = {"total_entries": 10}
    mock_get_cache_manager.return_value = mock_cache_manager
    
    # Mock command execution to fail
    mock_execute_command.side_effect = RuntimeError("Command failed")
    
    # Mock console to capture output
    with patch("src.awsideman.commands.cache.warm.console") as mock_console:
        with pytest.raises(typer.Exit):
            warm_cache("user list")
        
        # Verify error message was printed
        mock_console.print.assert_any_call("[red]Error executing command: Command failed[/red]")
