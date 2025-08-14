"""Tests for user command helper functions."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from src.awsideman.commands.user import validate_profile, validate_sso_instance


@pytest.fixture
def mock_config():
    """Create a mock Config object."""
    mock = MagicMock()
    mock.get.side_effect = lambda key, default=None: {
        "default_profile": "default",
        "profiles": {
            "default": {
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "identity_store_id": "d-1234567890",
            },
            "test": {
                "region": "us-west-2",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-abcdef1234567890",
                "identity_store_id": "d-0987654321",
            },
            "incomplete": {"region": "eu-west-1"},
        },
    }.get(key, default)
    return mock


@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.config")
def test_validate_profile_with_valid_profile(mock_config_module, mock_console, mock_config):
    """Test validate_profile with a valid profile."""
    mock_config_module.get.side_effect = mock_config.get

    # Test with explicit profile
    profile_name, profile_data = validate_profile("test")
    assert profile_name == "test"
    assert profile_data == {
        "region": "us-west-2",
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-abcdef1234567890",
        "identity_store_id": "d-0987654321",
    }

    # Test with default profile
    profile_name, profile_data = validate_profile(None)
    assert profile_name == "default"
    assert profile_data == {
        "region": "us-east-1",
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "identity_store_id": "d-1234567890",
    }


@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.config")
def test_validate_profile_with_no_profile(mock_config_module, mock_console, mock_config):
    """Test validate_profile with no profile specified and no default profile."""
    # Override the default_profile to None
    mock_config_module.get.side_effect = lambda key, default=None: {
        "default_profile": None,
        "profiles": mock_config.get("profiles"),
    }.get(key, default)

    # Test with no profile and no default
    with pytest.raises(typer.Exit):
        validate_profile(None)

    # Verify error message
    mock_console.print.assert_any_call(
        "[red]Error: No profile specified and no default profile set.[/red]"
    )


@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.config")
def test_validate_profile_with_invalid_profile(mock_config_module, mock_console, mock_config):
    """Test validate_profile with an invalid profile."""
    mock_config_module.get.side_effect = mock_config.get

    # Test with non-existent profile
    with pytest.raises(typer.Exit):
        validate_profile("nonexistent")

    # Verify error message
    mock_console.print.assert_any_call("[red]Error: Profile 'nonexistent' does not exist.[/red]")


@patch("src.awsideman.commands.user.console")
def test_validate_sso_instance_with_valid_instance(mock_console):
    """Test validate_sso_instance with a valid SSO instance."""
    profile_data = {
        "region": "us-east-1",
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "identity_store_id": "d-1234567890",
    }

    instance_arn, identity_store_id = validate_sso_instance(profile_data)
    assert instance_arn == "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    assert identity_store_id == "d-1234567890"


@patch("src.awsideman.commands.user.console")
def test_validate_sso_instance_with_missing_instance_arn(mock_console):
    """Test validate_sso_instance with missing instance ARN."""
    profile_data = {"region": "us-east-1", "identity_store_id": "d-1234567890"}

    with pytest.raises(typer.Exit):
        validate_sso_instance(profile_data)

    # Verify error message
    mock_console.print.assert_any_call(
        "[red]Error: No SSO instance configured for this profile.[/red]"
    )


@patch("src.awsideman.commands.user.console")
def test_validate_sso_instance_with_missing_identity_store_id(mock_console):
    """Test validate_sso_instance with missing identity store ID."""
    profile_data = {
        "region": "us-east-1",
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
    }

    with pytest.raises(typer.Exit):
        validate_sso_instance(profile_data)

    # Verify error message
    mock_console.print.assert_any_call(
        "[red]Error: No SSO instance configured for this profile.[/red]"
    )
