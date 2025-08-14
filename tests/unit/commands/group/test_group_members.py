"""Fast unit tests for group members module."""

import inspect

import pytest


def test_members_module_import():
    """Test that the members module can be imported successfully."""
    try:
        from src.awsideman.commands.group.members import add_member, list_members, remove_member

        assert list_members is not None
        assert add_member is not None
        assert remove_member is not None
    except Exception as e:
        pytest.fail(f"Failed to import members module: {e}")


def test_list_members_function_signature():
    """Test that the list_members function has the expected signature."""
    try:
        from src.awsideman.commands.group.members import list_members

        sig = inspect.signature(list_members)
        expected_params = ["group_identifier", "limit", "next_token", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in list_members"
        assert callable(list_members)
    except Exception as e:
        pytest.fail(f"Failed to test list_members function signature: {e}")


def test_add_member_function_signature():
    """Test that the add_member function has the expected signature."""
    try:
        from src.awsideman.commands.group.members import add_member

        sig = inspect.signature(add_member)
        expected_params = ["group_identifier", "user_identifier", "profile"]
        for param_name in expected_params:
            assert param_name in sig.parameters, f"Parameter '{param_name}' not found in add_member"
        assert callable(add_member)
    except Exception as e:
        pytest.fail(f"Failed to test add_member function signature: {e}")


def test_remove_member_function_signature():
    """Test that the remove_member function has the expected signature."""
    try:
        from src.awsideman.commands.group.members import remove_member

        sig = inspect.signature(remove_member)
        expected_params = ["group_identifier", "user_identifier", "force", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in remove_member"
        assert callable(remove_member)
    except Exception as e:
        pytest.fail(f"Failed to test remove_member function signature: {e}")


def test_members_help_text():
    """Test that the member functions have proper help text."""
    try:
        from src.awsideman.commands.group.members import add_member, list_members, remove_member

        list_doc = list_members.__doc__
        assert list_doc is not None
        assert "List all members" in list_doc
        assert "paginated" in list_doc.lower()

        add_doc = add_member.__doc__
        assert add_doc is not None
        assert "Add a user to a group" in add_doc
        assert "adds" in add_doc.lower()

        remove_doc = remove_member.__doc__
        assert remove_doc is not None
        assert "Remove a user from a group" in remove_doc
        assert "removes" in remove_doc.lower()

    except Exception as e:
        pytest.fail(f"Failed to test members help text: {e}")


def test_members_typer_integration():
    """Test that the member functions are properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.members import add_member, list_members, remove_member

        for func in [list_members, add_member, remove_member]:
            assert hasattr(func, "__name__")
            assert hasattr(func, "__doc__")
            assert hasattr(func, "__annotations__")
            assert callable(func)

    except Exception as e:
        pytest.fail(f"Failed to test members Typer integration: {e}")


def test_members_parameter_types():
    """Test that the member functions have the expected parameter types."""
    try:
        from src.awsideman.commands.group.members import add_member, list_members, remove_member

        # Test list_members parameter types
        list_sig = inspect.signature(list_members)
        assert list_sig.parameters["group_identifier"].annotation == str
        assert (
            "Optional" in str(list_sig.parameters["limit"].annotation)
            or list_sig.parameters["limit"].annotation == int
        )
        assert (
            "Optional" in str(list_sig.parameters["next_token"].annotation)
            or list_sig.parameters["next_token"].annotation == str
        )
        assert (
            "Optional" in str(list_sig.parameters["profile"].annotation)
            or list_sig.parameters["profile"].annotation == str
        )

        # Test add_member parameter types
        add_sig = inspect.signature(add_member)
        assert add_sig.parameters["group_identifier"].annotation == str
        assert add_sig.parameters["user_identifier"].annotation == str
        assert (
            "Optional" in str(add_sig.parameters["profile"].annotation)
            or add_sig.parameters["profile"].annotation == str
        )

        # Test remove_member parameter types
        remove_sig = inspect.signature(remove_member)
        assert remove_sig.parameters["group_identifier"].annotation == str
        assert remove_sig.parameters["user_identifier"].annotation == str
        assert remove_sig.parameters["force"].annotation == bool
        assert (
            "Optional" in str(remove_sig.parameters["profile"].annotation)
            or remove_sig.parameters["profile"].annotation == str
        )

    except Exception as e:
        pytest.fail(f"Failed to test members parameter types: {e}")
