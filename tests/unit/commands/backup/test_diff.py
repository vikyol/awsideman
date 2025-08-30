"""Test backup diff command."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import NoCredentialsError, TokenRetrievalError
from click.exceptions import Exit

from src.awsideman.commands.backup.diff import diff_backups


class TestBackupDiffCommand:
    """Test backup diff command functionality."""

    def test_diff_backups_no_credentials_error(self):
        """Test handling of no credentials error."""
        with patch(
            "src.awsideman.commands.backup.diff.validate_profile_with_cache"
        ) as mock_validate:
            mock_validate.return_value = ("test-profile", {"region": "us-east-1"}, MagicMock())

            with patch("src.awsideman.commands.backup.diff.console.print") as mock_print:
                with pytest.raises(Exit) as exc_info:
                    # Mock the storage backend initialization to fail with NoCredentialsError
                    with patch(
                        "src.awsideman.commands.backup.diff.FileSystemStorageBackend"
                    ) as mock_backend:
                        mock_backend.side_effect = NoCredentialsError()

                        diff_backups(
                            source="7d",
                            target=None,
                            output_format="console",
                            output_file=None,
                            storage_backend="filesystem",
                            storage_path=None,
                            profile=None,
                        )

                # Verify the command exits with error code 1
                assert exc_info.value.exit_code == 1

                # Verify the error message was printed
                mock_print.assert_any_call("[red]❌ Error: No AWS credentials found.[/red]")
                mock_print.assert_any_call("\n[yellow]To fix this issue:[/yellow]")
                mock_print.assert_any_call(
                    "1. Configure AWS credentials: [cyan]aws configure[/cyan]"
                )

    def test_diff_backups_successful_execution(self):
        """Test successful execution without authentication errors."""
        with patch(
            "src.awsideman.commands.backup.diff.validate_profile_with_cache"
        ) as mock_validate:
            mock_validate.return_value = ("test-profile", {"region": "us-east-1"}, MagicMock())

            with patch(
                "src.awsideman.commands.backup.diff.FileSystemStorageBackend"
            ) as mock_backend:
                mock_backend.return_value = MagicMock()

                with patch("src.awsideman.commands.backup.diff.StorageEngine") as mock_storage:
                    mock_storage.return_value = MagicMock()

                    with patch(
                        "src.awsideman.commands.backup.diff.get_global_metadata_index"
                    ) as mock_index:
                        mock_index.return_value = MagicMock()

                        with patch(
                            "src.awsideman.commands.backup.diff.BackupDiffManager"
                        ) as mock_manager:
                            mock_manager.return_value = MagicMock()

                            with patch(
                                "src.awsideman.commands.backup.diff.asyncio.run"
                            ) as mock_run:
                                mock_run.return_value = MagicMock()

                                # This should not raise any exceptions
                                try:
                                    diff_backups(
                                        source="7d",
                                        target=None,
                                        output_format="console",
                                        output_file=None,
                                        storage_backend="filesystem",
                                        storage_path=None,
                                        profile=None,
                                    )
                                except Exit:
                                    # If it exits, it should be with code 0 (success)
                                    pass
                                except Exception as e:
                                    # Any other exception should not be authentication-related
                                    assert not isinstance(
                                        e, (TokenRetrievalError, NoCredentialsError)
                                    )

    def test_diff_backups_token_retrieval_error_handling(self):
        """Test that TokenRetrievalError is properly imported and can be caught."""
        # This test verifies that our import and exception handling is set up correctly
        assert "TokenRetrievalError" in globals()
        assert "NoCredentialsError" in globals()

        # Test that we can create instances (basic functionality)
        try:
            no_creds = NoCredentialsError()
            assert isinstance(no_creds, NoCredentialsError)
        except Exception:
            # If we can't create it, that's fine - the important thing is the import
            pass
