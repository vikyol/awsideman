"""Tests for group module structure and integration."""

import pytest


def test_group_module_import():
    """Test that the group module can be imported successfully."""
    try:
        from src.awsideman.commands.group import app

        assert app is not None
    except Exception as e:
        pytest.fail(f"Failed to import group module: {e}")


def test_group_app_commands():
    """Test that the group app has the expected commands."""
    try:
        from src.awsideman.commands.group import app

        commands = [cmd.name for cmd in app.registered_commands]
        expected_commands = [
            "list",
            "get",
            "create",
            "update",
            "delete",
            "list-members",
            "add-member",
            "remove-member",
        ]
        for expected_cmd in expected_commands:
            assert expected_cmd in commands, f"Command '{expected_cmd}' not found in group app"
    except Exception as e:
        pytest.fail(f"Failed to test group app commands: {e}")


def test_group_module_structure():
    """Test that the group module has the expected submodules."""
    try:
        from src.awsideman.commands.group import create, delete, get, helpers, list, members, update

        assert list is not None
        assert get is not None
        assert create is not None
        assert update is not None
        assert delete is not None
        assert members is not None
        assert helpers is not None
    except Exception as e:
        pytest.fail(f"Failed to import group submodules: {e}")


def test_group_commands_help_text():
    """Test that group commands have proper help text."""
    try:
        from src.awsideman.commands.group import create, delete, get, list, members, update

        assert list.list_groups.__doc__ is not None
        assert get.get_group.__doc__ is not None
        assert create.create_group.__doc__ is not None
        assert update.update_group.__doc__ is not None
        assert delete.delete_group.__doc__ is not None
        assert members.list_members.__doc__ is not None
        assert members.add_member.__doc__ is not None
        assert members.remove_member.__doc__ is not None

        # Check that docstrings contain expected content
        list_doc = list.list_groups.__doc__
        assert "List all groups" in list_doc
        assert "filter" in list_doc.lower()
        assert "paginated" in list_doc.lower()

        get_doc = get.get_group.__doc__
        assert "Get detailed information" in get_doc
        assert "group" in get_doc.lower()

        create_doc = create.create_group.__doc__
        assert "Create a new group" in create_doc
        assert "name" in create_doc.lower()

        update_doc = update.update_group.__doc__
        assert "Update a group's attributes" in update_doc
        assert "attributes" in update_doc.lower()

        delete_doc = delete.delete_group.__doc__
        assert "Delete a group" in delete_doc
        assert "permanently" in delete_doc.lower()

        members_list_doc = members.list_members.__doc__
        assert "List all members" in members_list_doc
        assert "paginated" in members_list_doc.lower()

        members_add_doc = members.add_member.__doc__
        assert "Add a user to a group" in members_add_doc
        assert "adds" in members_add_doc.lower()

        members_remove_doc = members.remove_member.__doc__
        assert "Remove a user from a group" in members_remove_doc
        assert "removes" in members_remove_doc.lower()

    except Exception as e:
        pytest.fail(f"Failed to test group command help text: {e}")


def test_group_helpers_functions():
    """Test that group helpers module has the expected functions."""
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

        assert get_single_key.__doc__ is not None
        assert validate_profile.__doc__ is not None
        assert validate_sso_instance.__doc__ is not None
        assert validate_group_name.__doc__ is not None
        assert validate_group_description.__doc__ is not None
        assert validate_filter.__doc__ is not None
        assert validate_limit.__doc__ is not None
        assert validate_non_empty.__doc__ is not None
        assert _find_user_id.__doc__ is not None
    except Exception as e:
        pytest.fail(f"Failed to test group helpers functions: {e}")
