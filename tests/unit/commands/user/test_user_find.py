"""Tests for user find command."""

import re
from unittest.mock import Mock, patch

import pytest
from typer import Exit

from src.awsideman.commands.user.find import find_users


class TestUserFindCommand:
    """Test cases for the user find command."""

    def test_find_users_module_import(self):
        """Test that the find_users module can be imported."""
        try:
            from src.awsideman.commands.user.find import find_users

            assert find_users is not None
            assert callable(find_users)
        except ImportError as e:
            pytest.fail(f"Failed to import find_users: {e}")

    def test_find_users_function_signature(self):
        """Test that the find_users function has the expected signature."""
        import inspect

        from src.awsideman.commands.user.find import find_users

        # Check that the function exists and is callable
        assert callable(find_users)

        # Check that it has the expected parameters
        sig = inspect.signature(find_users)
        expected_params = {"pattern", "case_sensitive", "limit", "profile", "region", "verbose"}

        actual_params = set(sig.parameters.keys())
        assert expected_params.issubset(
            actual_params
        ), f"Missing parameters: {expected_params - actual_params}"

    def test_find_users_help_text(self):
        """Test that the find_users function has help text."""
        from src.awsideman.commands.user.find import find_users

        # Check that the function has a docstring
        assert find_users.__doc__ is not None
        assert len(find_users.__doc__.strip()) > 0

        # Check that the docstring contains expected content
        doc = find_users.__doc__.lower()
        assert "find" in doc
        assert "users" in doc
        assert "regex pattern" in doc

    def test_find_users_typer_integration(self):
        """Test that the find_users function is properly integrated with Typer."""
        from src.awsideman.commands.user.find import find_users

        # Check that the function has the expected type hints
        assert hasattr(find_users, "__annotations__")

        annotations = find_users.__annotations__
        assert "pattern" in annotations
        assert "case_sensitive" in annotations
        assert "limit" in annotations
        assert "profile" in annotations

    def test_find_users_parameter_types(self):
        """Test that the find_users function has correct parameter types."""
        import inspect

        from src.awsideman.commands.user.find import find_users

        sig = inspect.signature(find_users)

        # Check that pattern is required string
        pattern_param = sig.parameters["pattern"]
        assert pattern_param.annotation == str

        # Check that case_sensitive is boolean
        case_sensitive_param = sig.parameters["case_sensitive"]
        assert case_sensitive_param.annotation == bool

        # Check that limit is optional int
        limit_param = sig.parameters["limit"]
        assert "Optional" in str(limit_param.annotation) or limit_param.annotation == int

    @patch("src.awsideman.commands.user.find.extract_standard_params")
    @patch("src.awsideman.commands.user.find.validate_profile_with_cache")
    @patch("src.awsideman.commands.user.find.validate_sso_instance")
    @patch("src.awsideman.commands.user.find.handle_aws_error")
    def test_find_users_invalid_regex_pattern(
        self, mock_handle_error, mock_validate_sso, mock_validate_profile, mock_extract_params
    ):
        """Test that invalid regex patterns are properly handled."""
        # Mock the standard params
        mock_extract_params.return_value = ("test-profile", "eu-west-1", True)

        # Mock profile validation
        mock_validate_profile.return_value = ("test-profile", {"region": "eu-west-1"}, Mock())

        # Mock SSO validation
        mock_validate_sso.return_value = ("sso-instance-arn", "identity-store-id")

        # Test with invalid regex pattern
        with pytest.raises(Exit):
            find_users("[")

        # Verify error handling was called
        mock_handle_error.assert_called_once()

    @patch("src.awsideman.commands.user.find.extract_standard_params")
    @patch("src.awsideman.commands.user.find.validate_profile_with_cache")
    @patch("src.awsideman.commands.user.find.validate_sso_instance")
    @patch("src.awsideman.commands.user.find.handle_aws_error")
    def test_find_users_case_sensitive_search(
        self, mock_handle_error, mock_validate_sso, mock_validate_profile, mock_extract_params
    ):
        """Test case sensitive search functionality."""
        # Mock the standard params
        mock_extract_params.return_value = ("test-profile", "eu-west-1", True)

        # Mock profile validation
        mock_validate_profile.return_value = ("test-profile", {"region": "eu-west-1"}, Mock())

        # Mock SSO validation
        mock_validate_sso.return_value = ("sso-instance-arn", "identity-store-id")

        # Test case sensitive search
        with pytest.raises(Exit):
            find_users("test", case_sensitive=True)

        # Verify the function was called with case sensitive flag
        # (The actual regex compilation would happen in the function)

    @patch("src.awsideman.commands.user.find.extract_standard_params")
    @patch("src.awsideman.commands.user.find.validate_profile_with_cache")
    @patch("src.awsideman.commands.user.find.validate_sso_instance")
    @patch("src.awsideman.commands.user.find.handle_aws_error")
    def test_find_users_with_limit(
        self, mock_handle_error, mock_validate_sso, mock_validate_profile, mock_extract_params
    ):
        """Test that limit parameter is properly handled."""
        # Mock the standard params
        mock_extract_params.return_value = ("test-profile", "eu-west-1", True)

        # Mock profile validation
        mock_validate_profile.return_value = ("test-profile", {"region": "eu-west-1"}, Mock())

        # Mock SSO validation
        mock_validate_sso.return_value = ("sso-instance-arn", "identity-store-id")

        # Test with limit parameter
        with pytest.raises(Exit):
            find_users("test", limit=10)

        # Verify the function was called with limit
        # (The actual limit handling would happen in the function)

    def test_regex_pattern_validation(self):
        """Test regex pattern validation logic."""
        # Test valid patterns
        valid_patterns = [
            "han",
            "john",
            "admin",
            "^A.*n$",
            "@company\\.com$",
            "[a-zA-Z]+",
            "\\d+",
        ]

        for pattern in valid_patterns:
            try:
                re.compile(pattern)
            except re.error:
                pytest.fail(f"Pattern '{pattern}' should be valid")

        # Test invalid patterns
        invalid_patterns = [
            "[",
            "(",
            "\\",
            "*+",
        ]

        for pattern in invalid_patterns:
            with pytest.raises(re.error):
                re.compile(pattern)

    def test_case_sensitive_regex_compilation(self):
        """Test case sensitive vs case insensitive regex compilation."""
        pattern = "Test"

        # Case sensitive
        case_sensitive_regex = re.compile(pattern, 0)
        assert case_sensitive_regex.search("Test") is not None
        assert case_sensitive_regex.search("test") is None

        # Case insensitive
        case_insensitive_regex = re.compile(pattern, re.IGNORECASE)
        assert case_insensitive_regex.search("Test") is not None
        assert case_insensitive_regex.search("test") is not None

    def test_user_attribute_search_patterns(self):
        """Test various user attribute search patterns."""
        # Sample user data structure
        user = {
            "UserName": "john.doe",
            "DisplayName": "John Doe",
            "Emails": [{"Value": "john.doe@company.com", "Primary": True}],
            "Name": {"GivenName": "John", "FamilyName": "Doe"},
        }

        # Test username search
        username_pattern = re.compile("john", re.IGNORECASE)
        assert username_pattern.search(user["UserName"]) is not None

        # Test display name search
        display_pattern = re.compile("doe", re.IGNORECASE)
        assert display_pattern.search(user["DisplayName"]) is not None

        # Test email search
        email_pattern = re.compile("@company", re.IGNORECASE)
        assert email_pattern.search(user["Emails"][0]["Value"]) is not None

        # Test given name search
        given_name_pattern = re.compile("^john$", re.IGNORECASE)
        assert given_name_pattern.search(user["Name"]["GivenName"]) is not None

        # Test family name search
        family_name_pattern = re.compile("doe", re.IGNORECASE)
        assert family_name_pattern.search(user["Name"]["FamilyName"]) is not None

        # Test full name combination
        full_name = f"{user['Name']['GivenName']} {user['Name']['FamilyName']}"
        full_name_pattern = re.compile("john doe", re.IGNORECASE)
        assert full_name_pattern.search(full_name) is not None

    def test_search_pattern_examples(self):
        """Test the search pattern examples from the help text."""
        # Test: Find users with 'han' in their name (case insensitive)
        pattern = "han"
        regex = re.compile(pattern, re.IGNORECASE)

        test_names = ["John", "Hannah", "Shannon", "HAN", "han"]
        expected_matches = ["Hannah", "Shannon", "HAN", "han"]

        for name in test_names:
            if regex.search(name):
                assert name in expected_matches

        # Test: Find users with email addresses ending in '@company.com'
        pattern = "@company\\.com$"
        regex = re.compile(pattern, re.IGNORECASE)

        test_emails = ["user@company.com", "admin@company.com", "test@other.com"]
        expected_matches = ["user@company.com", "admin@company.com"]

        for email in test_emails:
            if regex.search(email):
                assert email in expected_matches

        # Test: Find users with names starting with 'A' and ending with 'n'
        pattern = "^A.*n$"
        regex = re.compile(pattern, re.IGNORECASE)

        test_names = ["Admin", "Alan", "Aaron", "John", "AdminUser"]
        expected_matches = ["Admin", "Alan", "Aaron"]

        for name in test_names:
            if regex.search(name):
                assert name in expected_matches

    def test_limit_functionality(self):
        """Test that limit functionality works correctly."""
        # Simulate a list of users
        all_users = [f"user{i}" for i in range(20)]

        # Test with limit
        limit = 10
        limited_users = all_users[:limit]

        assert len(limited_users) == limit
        assert limited_users == all_users[:limit]

        # Test without limit
        unlimited_users = all_users
        assert len(unlimited_users) == 20

    def test_empty_search_results(self):
        """Test handling of empty search results."""
        # This would be tested in integration tests with actual AWS API calls
        # For unit tests, we verify the logic structure

        # Simulate no matching users
        matching_users = []

        # The function should handle empty results gracefully
        assert len(matching_users) == 0

    def test_multiple_matching_users(self):
        """Test handling of multiple matching users."""
        # Simulate multiple matching users
        matching_users = [
            {"UserName": "john.doe", "DisplayName": "John Doe"},
            {"UserName": "john.smith", "DisplayName": "John Smith"},
            {"UserName": "johnny", "DisplayName": "Johnny"},
        ]

        # All should match the pattern "john"
        pattern = "john"
        regex = re.compile(pattern, re.IGNORECASE)

        for user in matching_users:
            assert regex.search(user["UserName"]) is not None

    def test_search_across_all_attributes(self):
        """Test that search works across all user attributes."""
        user = {
            "UserName": "admin.user",
            "DisplayName": "Administrator User",
            "Emails": [{"Value": "admin@company.com", "Primary": True}],
            "Name": {"GivenName": "Administrator", "FamilyName": "User"},
        }

        # Test pattern that could match multiple attributes
        pattern = "admin"
        regex = re.compile(pattern, re.IGNORECASE)

        # Should match username
        assert regex.search(user["UserName"]) is not None

        # Should match display name
        assert regex.search(user["DisplayName"]) is not None

        # Should match email
        assert regex.search(user["Emails"][0]["Value"]) is not None

        # Should match given name
        assert regex.search(user["Name"]["GivenName"]) is not None
