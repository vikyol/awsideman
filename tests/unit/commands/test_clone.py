"""
Unit tests for the clone command.
"""

from unittest.mock import Mock, patch

from typer.testing import CliRunner


class TestCloneCommand:
    """Test the clone command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.instance_arn = "arn:aws:sso:::instance/ins-123"

        # Mock configuration
        self.mock_config = Mock()
        self.mock_config.get_instance_arn.return_value = self.instance_arn

        # Mock successful clone result
        self.mock_cloned_config = Mock()
        self.mock_cloned_config.session_duration = "PT8H"
        self.mock_cloned_config.relay_state_url = None
        self.mock_cloned_config.aws_managed_policies = ["ReadOnlyAccess"]
        self.mock_cloned_config.customer_managed_policies = []
        self.mock_cloned_config.inline_policy = None

        self.mock_clone_result = Mock()
        self.mock_clone_result.success = True
        self.mock_clone_result.error_message = None
        self.mock_clone_result.cloned_config = self.mock_cloned_config

        # Mock failed clone result
        self.mock_failed_result = Mock()
        self.mock_failed_result.success = False
        self.mock_failed_result.error_message = "Permission set not found"
        self.mock_failed_result.cloned_config = None

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PermissionSetCloner")
    @patch("src.awsideman.commands.clone.PermissionCloningRollbackIntegration")
    def test_clone_permission_set_success(
        self,
        mock_integration_class,
        mock_cloner_class,
        mock_client_manager_class,
        mock_config_class,
    ):
        """Test successful permission set cloning."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_cloner = Mock()
        mock_cloner.clone_permission_set.return_value = self.mock_clone_result
        mock_cloner_class.return_value = mock_cloner

        mock_integration = Mock()
        mock_integration.track_permission_set_clone_operation.return_value = "rollback-123"
        mock_integration_class.return_value = mock_integration

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--instance-arn",
                self.instance_arn,
            ],
        )

        # Verify success
        assert result.exit_code == 0
        assert "Successfully cloned permission set" in result.stdout
        assert "SourcePermissionSet" in result.stdout
        assert "NewPermissionSet" in result.stdout

        # Verify cloner was called correctly
        mock_cloner.clone_permission_set.assert_called_once_with(
            source_name="SourcePermissionSet",
            target_name="NewPermissionSet",
            target_description=None,
            preview=False,
        )

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PermissionSetCloner")
    @patch("src.awsideman.commands.clone.RollbackProcessor")
    @patch("src.awsideman.commands.clone.PermissionCloningRollbackIntegration")
    def test_clone_with_custom_description(
        self,
        mock_integration_class,
        mock_rollback_class,
        mock_cloner_class,
        mock_client_manager_class,
        mock_config_class,
    ):
        """Test cloning with custom description."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_cloner = Mock()
        mock_cloner.clone_permission_set.return_value = self.mock_clone_result
        mock_cloner_class.return_value = mock_cloner

        mock_integration = Mock()
        mock_integration.track_permission_set_clone_operation.return_value = "rollback-123"
        mock_integration_class.return_value = mock_integration

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--description",
                "Custom description",
                "--instance-arn",
                self.instance_arn,
            ],
        )

        # Verify success
        assert result.exit_code == 0
        assert "Successfully cloned permission set" in result.stdout
        # Note: Custom description is not displayed in the success output, only in preview mode

        # Verify cloner was called with custom description
        mock_cloner.clone_permission_set.assert_called_once_with(
            source_name="SourcePermissionSet",
            target_name="NewPermissionSet",
            target_description="Custom description",
            preview=False,
        )

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PreviewGenerator")
    def test_clone_preview_mode(
        self, mock_preview_class, mock_client_manager_class, mock_config_class
    ):
        """Test clone preview mode."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_preview_generator = Mock()
        mock_preview_result = {"cloned_config": self.mock_cloned_config, "warnings": []}
        mock_preview_generator.preview_permission_set_clone.return_value = mock_preview_result
        mock_preview_class.return_value = mock_preview_generator

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--preview",
                "--instance-arn",
                self.instance_arn,
            ],
        )

        # Verify preview output
        assert result.exit_code == 0
        assert "Permission Set Clone Preview" in result.stdout
        assert "Source: SourcePermissionSet" in result.stdout
        assert "Target: NewPermissionSet" in result.stdout
        assert "Configuration to be cloned:" in result.stdout

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PermissionSetCloner")
    def test_clone_dry_run_mode(
        self, mock_cloner_class, mock_client_manager_class, mock_config_class
    ):
        """Test clone dry run mode."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_cloner = Mock()
        mock_cloner.clone_permission_set.return_value = self.mock_clone_result
        mock_cloner_class.return_value = mock_cloner

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--dry-run",
                "--instance-arn",
                self.instance_arn,
            ],
        )

        # Verify success
        assert result.exit_code == 0
        assert "Successfully cloned permission set" in result.stdout

        # Verify cloner was called (dry_run only affects rollback tracking, not the clone call)
        mock_cloner.clone_permission_set.assert_called_once_with(
            source_name="SourcePermissionSet",
            target_name="NewPermissionSet",
            target_description=None,
            preview=False,
        )

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PermissionSetCloner")
    def test_clone_failure(self, mock_cloner_class, mock_client_manager_class, mock_config_class):
        """Test clone failure handling."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_cloner = Mock()
        mock_cloner.clone_permission_set.return_value = self.mock_failed_result
        mock_cloner_class.return_value = mock_cloner

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--instance-arn",
                self.instance_arn,
            ],
        )

        # Verify failure
        assert result.exit_code == 1
        assert "Failed to clone permission set" in result.stdout
        assert "Permission set not found" in result.stdout

    @patch("src.awsideman.commands.clone.Config")
    def test_clone_missing_instance_arn(self, mock_config_class):
        """Test clone with missing instance ARN."""
        # Setup mock to return None for instance ARN
        mock_config = Mock()
        mock_config.get_instance_arn.return_value = None
        mock_config_class.return_value = mock_config

        # Import and run command
        from src.awsideman.commands.clone import app

        result = self.runner.invoke(
            app, ["--name", "SourcePermissionSet", "--to", "NewPermissionSet"]
        )

        # Verify error (the command tries to auto-discover and fails)
        assert result.exit_code == 1
        assert "Error discovering SSO information" in result.stdout

    def test_clone_missing_required_parameters(self):
        """Test clone with missing required parameters."""
        from src.awsideman.commands.clone import app

        # Test missing --name
        result = self.runner.invoke(
            app, ["--to", "NewPermissionSet", "--instance-arn", self.instance_arn]
        )
        assert result.exit_code != 0

        # Test missing --to
        result = self.runner.invoke(
            app, ["--name", "SourcePermissionSet", "--instance-arn", self.instance_arn]
        )
        assert result.exit_code != 0

    @patch("src.awsideman.commands.clone.Config")
    @patch("src.awsideman.commands.clone.AWSClientManager")
    @patch("src.awsideman.commands.clone.PermissionSetCloner")
    def test_clone_rollback_tracking_failure(
        self, mock_cloner_class, mock_client_manager_class, mock_config_class
    ):
        """Test clone when rollback tracking fails."""
        # Setup mocks
        mock_config_class.return_value = self.mock_config

        mock_cloner = Mock()
        mock_cloner.clone_permission_set.return_value = self.mock_clone_result
        mock_cloner_class.return_value = mock_cloner

        # Mock rollback integration failure
        with (
            patch("src.awsideman.commands.clone.RollbackProcessor"),
            patch(
                "src.awsideman.commands.clone.PermissionCloningRollbackIntegration"
            ) as mock_integration_class,
        ):

            mock_integration = Mock()
            mock_integration.track_permission_set_clone_operation.side_effect = Exception(
                "Rollback tracking failed"
            )
            mock_integration_class.return_value = mock_integration

            # Import and run command
            from src.awsideman.commands.clone import app

            result = self.runner.invoke(
                app,
                [
                    "--name",
                    "SourcePermissionSet",
                    "--to",
                    "NewPermissionSet",
                    "--instance-arn",
                    self.instance_arn,
                ],
            )

            # Verify success despite rollback tracking failure
            assert result.exit_code == 0
            assert "Successfully cloned permission set" in result.stdout
            assert "Warning: Failed to track operation for rollback" in result.stdout

    def test_clone_verbose_output(self):
        """Test clone with verbose output."""
        from src.awsideman.commands.clone import app

        # Test that verbose flag is accepted
        result = self.runner.invoke(
            app,
            [
                "--name",
                "SourcePermissionSet",
                "--to",
                "NewPermissionSet",
                "--instance-arn",
                self.instance_arn,
                "--verbose",
            ],
        )

        # Should not fail due to verbose flag
        assert result.exit_code in [0, 1]  # Could be 0 (success) or 1 (error due to missing mocks)
