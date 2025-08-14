"""Fast unit tests for group helpers module."""

import inspect

import pytest


def test_helpers_module_import():
    """Test that the helpers module can be imported successfully."""
    try:
        from src.awsideman.commands.group.helpers import (
            _find_user_id,
            get_single_key,
            validate_filter,
            validate_group_description,
            validate_group_name,
            validate_limit,
            validate_non_empty,
            validate_profile,
            validate_sso_instance,
        )

        assert get_single_key is not None
        assert validate_profile is not None
        assert validate_sso_instance is not None
        assert validate_group_name is not None
        assert validate_group_description is not None
        assert validate_filter is not None
        assert validate_limit is not None
        assert validate_non_empty is not None
        assert _find_user_id is not None
    except Exception as e:
        pytest.fail(f"Failed to import helpers module: {e}")


def test_helpers_console_instance():
    """Test that the helpers module has the console instance."""
    try:
        from src.awsideman.commands.group.helpers import console

        assert console is not None
        assert hasattr(console, "print")
    except Exception as e:
        pytest.fail(f"Failed to test helpers console instance: {e}")


def test_helpers_config_instance():
    """Test that the helpers module has the config instance."""
    try:
        from src.awsideman.commands.group.helpers import config

        assert config is not None
        assert hasattr(config, "get")
    except Exception as e:
        pytest.fail(f"Failed to test helpers config instance: {e}")


def test_helpers_functions_docstrings():
    """Test that all helper functions have docstrings."""
    try:
        from src.awsideman.commands.group.helpers import (
            _find_user_id,
            get_single_key,
            validate_filter,
            validate_group_description,
            validate_group_name,
            validate_limit,
            validate_non_empty,
            validate_profile,
            validate_sso_instance,
        )

        functions = [
            get_single_key,
            validate_profile,
            validate_sso_instance,
            validate_group_name,
            validate_group_description,
            validate_filter,
            validate_limit,
            validate_non_empty,
            _find_user_id,
        ]

        for func in functions:
            assert func.__doc__ is not None, f"Function {func.__name__} should have a docstring"

    except Exception as e:
        pytest.fail(f"Failed to test helpers function docstrings: {e}")


def test_helpers_functions_callable():
    """Test that all helper functions are callable."""
    try:
        from src.awsideman.commands.group.helpers import (
            _find_user_id,
            get_single_key,
            validate_filter,
            validate_group_description,
            validate_group_name,
            validate_limit,
            validate_non_empty,
            validate_profile,
            validate_sso_instance,
        )

        functions = [
            get_single_key,
            validate_profile,
            validate_sso_instance,
            validate_group_name,
            validate_group_description,
            validate_filter,
            validate_limit,
            validate_non_empty,
            _find_user_id,
        ]

        for func in functions:
            assert callable(func), f"Function {func.__name__} should be callable"

    except Exception as e:
        pytest.fail(f"Failed to test helpers function callability: {e}")


def test_helpers_function_signatures():
    """Test that helper functions have the expected signatures."""
    try:
        from src.awsideman.commands.group.helpers import (
            _find_user_id,
            validate_filter,
            validate_group_description,
            validate_group_name,
            validate_limit,
            validate_non_empty,
            validate_profile,
            validate_sso_instance,
        )

        # Test validate_profile signature
        profile_sig = inspect.signature(validate_profile)
        assert "profile_name" in profile_sig.parameters
        assert (
            "Optional" in str(profile_sig.parameters["profile_name"].annotation)
            or profile_sig.parameters["profile_name"].annotation == str
        )

        # Test validate_sso_instance signature
        sso_sig = inspect.signature(validate_sso_instance)
        assert "profile_data" in sso_sig.parameters
        assert sso_sig.parameters["profile_data"].annotation == dict

        # Test validate_group_name signature
        name_sig = inspect.signature(validate_group_name)
        assert "name" in name_sig.parameters
        assert name_sig.parameters["name"].annotation == str

        # Test validate_group_description signature
        desc_sig = inspect.signature(validate_group_description)
        assert "description" in desc_sig.parameters
        assert (
            "Optional" in str(desc_sig.parameters["description"].annotation)
            or desc_sig.parameters["description"].annotation == str
        )

        # Test validate_filter signature
        filter_sig = inspect.signature(validate_filter)
        assert "filter_str" in filter_sig.parameters
        assert filter_sig.parameters["filter_str"].annotation == str

        # Test validate_limit signature
        limit_sig = inspect.signature(validate_limit)
        assert "limit" in limit_sig.parameters
        assert limit_sig.parameters["limit"].annotation == int

        # Test validate_non_empty signature
        nonempty_sig = inspect.signature(validate_non_empty)
        assert "value" in nonempty_sig.parameters
        assert "field_name" in nonempty_sig.parameters
        assert nonempty_sig.parameters["value"].annotation == str
        assert nonempty_sig.parameters["field_name"].annotation == str

        # Test _find_user_id signature
        find_sig = inspect.signature(_find_user_id)
        assert "identity_store_client" in find_sig.parameters
        assert "identity_store_id" in find_sig.parameters
        assert "user_identifier" in find_sig.parameters
        assert find_sig.parameters["identity_store_id"].annotation == str
        assert find_sig.parameters["user_identifier"].annotation == str

    except Exception as e:
        pytest.fail(f"Failed to test helpers function signatures: {e}")
