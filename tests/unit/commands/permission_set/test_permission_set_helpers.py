"""Fast unit tests for permission_set helpers module."""

import inspect

import pytest


def test_permission_set_helpers_module_import():
    """Test that the permission_set helpers module can be imported successfully."""
    try:
        from src.awsideman.commands.permission_set.helpers import (
            format_permission_set_for_display,
            get_single_key,
            resolve_permission_set_identifier,
            validate_aws_managed_policy_arn,
            validate_permission_set_description,
            validate_permission_set_name,
            validate_profile,
            validate_sso_instance,
        )

        assert all(
            [
                get_single_key,
                validate_profile,
                validate_sso_instance,
                validate_permission_set_name,
                validate_permission_set_description,
                validate_aws_managed_policy_arn,
                format_permission_set_for_display,
                resolve_permission_set_identifier,
            ]
        )
    except Exception as e:
        pytest.fail(f"Failed to import permission_set helpers: {e}")


def test_permission_set_helpers_console_instance():
    """Test that the console instance is properly imported."""
    try:
        from src.awsideman.commands.permission_set.helpers import console

        assert console is not None
        assert hasattr(console, "print")
    except Exception as e:
        pytest.fail(f"Failed to test console instance: {e}")


def test_permission_set_helpers_config_instance():
    """Test that the config instance is properly imported."""
    try:
        from src.awsideman.commands.permission_set.helpers import config

        assert config is not None
        assert hasattr(config, "get")
    except Exception as e:
        pytest.fail(f"Failed to test config instance: {e}")


def test_permission_set_helpers_get_single_key():
    """Test that get_single_key function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import get_single_key

        # Check function signature
        sig = inspect.signature(get_single_key)
        assert len(sig.parameters) == 0, "get_single_key should take no parameters"

        # Check docstring
        assert get_single_key.__doc__ is not None
        assert "single key press" in get_single_key.__doc__.lower()

        # Check that function is callable
        assert callable(get_single_key)

    except Exception as e:
        pytest.fail(f"Failed to test get_single_key: {e}")


def test_permission_set_helpers_validate_profile():
    """Test that validate_profile function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import validate_profile

        # Check function signature
        sig = inspect.signature(validate_profile)
        assert "profile_name" in sig.parameters
        assert sig.parameters["profile_name"].annotation == "Optional[str]" or "Optional" in str(
            sig.parameters["profile_name"].annotation
        )

        # Check docstring
        assert validate_profile.__doc__ is not None
        assert "validate the profile" in validate_profile.__doc__.lower()

        # Check that function is callable
        assert callable(validate_profile)

    except Exception as e:
        pytest.fail(f"Failed to test validate_profile: {e}")


def test_permission_set_helpers_validate_sso_instance():
    """Test that validate_sso_instance function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import validate_sso_instance

        # Check function signature
        sig = inspect.signature(validate_sso_instance)
        assert "profile_data" in sig.parameters
        assert sig.parameters["profile_data"].annotation == dict

        # Check docstring
        assert validate_sso_instance.__doc__ is not None
        assert "validate the sso instance" in validate_sso_instance.__doc__.lower()

        # Check that function is callable
        assert callable(validate_sso_instance)

    except Exception as e:
        pytest.fail(f"Failed to test validate_sso_instance: {e}")


def test_permission_set_helpers_validate_permission_set_name():
    """Test that validate_permission_set_name function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import validate_permission_set_name

        # Check function signature
        sig = inspect.signature(validate_permission_set_name)
        assert "name" in sig.parameters
        assert sig.parameters["name"].annotation == str

        # Check docstring
        assert validate_permission_set_name.__doc__ is not None
        assert "validate permission set name" in validate_permission_set_name.__doc__.lower()

        # Check that function is callable
        assert callable(validate_permission_set_name)

    except Exception as e:
        pytest.fail(f"Failed to test validate_permission_set_name: {e}")


def test_permission_set_helpers_validate_permission_set_description():
    """Test that validate_permission_set_description function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import (
            validate_permission_set_description,
        )

        # Check function signature
        sig = inspect.signature(validate_permission_set_description)
        assert "description" in sig.parameters
        assert "Optional" in str(sig.parameters["description"].annotation)

        # Check docstring
        assert validate_permission_set_description.__doc__ is not None
        assert (
            "validate permission set description"
            in validate_permission_set_description.__doc__.lower()
        )

        # Check that function is callable
        assert callable(validate_permission_set_description)

    except Exception as e:
        pytest.fail(f"Failed to test validate_permission_set_description: {e}")


def test_permission_set_helpers_validate_aws_managed_policy_arn():
    """Test that validate_aws_managed_policy_arn function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import validate_aws_managed_policy_arn

        # Check function signature
        sig = inspect.signature(validate_aws_managed_policy_arn)
        assert "policy_arn" in sig.parameters
        assert sig.parameters["policy_arn"].annotation == str

        # Check docstring
        assert validate_aws_managed_policy_arn.__doc__ is not None
        assert "validate aws managed policy arn" in validate_aws_managed_policy_arn.__doc__.lower()

        # Check that function is callable
        assert callable(validate_aws_managed_policy_arn)

    except Exception as e:
        pytest.fail(f"Failed to test validate_aws_managed_policy_arn: {e}")


def test_permission_set_helpers_format_permission_set_for_display():
    """Test that format_permission_set_for_display function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import format_permission_set_for_display

        # Check function signature
        sig = inspect.signature(format_permission_set_for_display)
        assert "permission_set" in sig.parameters
        assert "Dict" in str(sig.parameters["permission_set"].annotation)

        # Check docstring
        assert format_permission_set_for_display.__doc__ is not None
        assert "format permission set data" in format_permission_set_for_display.__doc__.lower()

        # Check that function is callable
        assert callable(format_permission_set_for_display)

    except Exception as e:
        pytest.fail(f"Failed to test format_permission_set_for_display: {e}")


def test_permission_set_helpers_resolve_permission_set_identifier():
    """Test that resolve_permission_set_identifier function has proper structure."""
    try:
        from src.awsideman.commands.permission_set.helpers import resolve_permission_set_identifier

        # Check function signature
        sig = inspect.signature(resolve_permission_set_identifier)
        expected_params = ["sso_admin_client", "instance_arn", "identifier", "identity_store_id"]
        for param_name in expected_params:
            assert param_name in sig.parameters, f"Parameter '{param_name}' not found"

        # Check docstring
        assert resolve_permission_set_identifier.__doc__ is not None
        assert (
            "resolve a permission set identifier"
            in resolve_permission_set_identifier.__doc__.lower()
        )

        # Check that function is callable
        assert callable(resolve_permission_set_identifier)

    except Exception as e:
        pytest.fail(f"Failed to test resolve_permission_set_identifier: {e}")
