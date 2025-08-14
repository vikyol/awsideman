"""Tests for backend factory implementation."""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory


class TestBackendFactory:
    """Test cases for BackendFactory."""

    def test_create_file_backend(self):
        """Test creating file backend."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            config = AdvancedCacheConfig(backend_type="file", file_cache_dir=temp_dir)

            backend = BackendFactory.create_backend(config)

            assert isinstance(backend, FileBackend)
            assert backend.backend_type == "file"

    def test_create_dynamodb_backend(self):
        """Test creating DynamoDB backend."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            dynamodb_region="us-east-1",
            dynamodb_profile="test-profile",
        )

        # Mock the DynamoDB backend import and creation
        mock_dynamodb_backend = Mock()
        mock_dynamodb_backend.backend_type = "dynamodb"

        with patch(
            "src.awsideman.cache.backends.dynamodb.DynamoDBBackend",
            return_value=mock_dynamodb_backend,
        ):
            backend = BackendFactory.create_backend(config)

        assert backend == mock_dynamodb_backend

    def test_create_dynamodb_backend_import_error(self):
        """Test creating DynamoDB backend with import error."""
        config = AdvancedCacheConfig(backend_type="dynamodb", dynamodb_table_name="test-table")

        with patch(
            "src.awsideman.cache.backends.dynamodb.DynamoDBBackend",
            side_effect=ImportError("boto3 not found"),
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory.create_backend(config)

            assert "requires boto3 to be installed" in str(exc_info.value)
            assert exc_info.value.backend_type == "dynamodb"

    def test_create_hybrid_backend(self):
        """Test creating hybrid backend."""
        config = AdvancedCacheConfig(
            backend_type="hybrid", dynamodb_table_name="test-table", hybrid_local_ttl=600
        )

        # Mock the hybrid backend and its dependencies
        mock_file_backend = Mock()
        mock_dynamodb_backend = Mock()
        mock_hybrid_backend = Mock()
        mock_hybrid_backend.backend_type = "hybrid"

        with patch(
            "src.awsideman.cache.backends.hybrid.HybridBackend", return_value=mock_hybrid_backend
        ):
            with patch.object(
                BackendFactory, "_create_file_backend", return_value=mock_file_backend
            ):
                with patch.object(
                    BackendFactory, "_create_dynamodb_backend", return_value=mock_dynamodb_backend
                ):
                    backend = BackendFactory.create_backend(config)

        assert backend == mock_hybrid_backend

    def test_create_hybrid_backend_import_error(self):
        """Test creating hybrid backend with import error."""
        config = AdvancedCacheConfig(backend_type="hybrid", dynamodb_table_name="test-table")

        with patch(
            "src.awsideman.cache.backends.hybrid.HybridBackend",
            side_effect=ImportError("Missing dependency"),
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory.create_backend(config)

            assert "requires additional dependencies" in str(exc_info.value)
            assert exc_info.value.backend_type == "hybrid"

    def test_create_unknown_backend(self):
        """Test creating unknown backend type."""
        config = AdvancedCacheConfig(backend_type="unknown")

        with pytest.raises(CacheBackendError) as exc_info:
            BackendFactory.create_backend(config)

        assert "Unknown backend type: unknown" in str(exc_info.value)

    def test_create_backend_unexpected_error(self):
        """Test creating backend with unexpected error."""
        config = AdvancedCacheConfig(backend_type="file")

        with patch.object(
            BackendFactory, "_create_file_backend", side_effect=Exception("Unexpected error")
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory.create_backend(config)

            assert "Failed to create file backend" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_create_backend_with_fallback_success(self):
        """Test creating backend with fallback when primary succeeds."""
        config = AdvancedCacheConfig(backend_type="file")

        backend = BackendFactory.create_backend_with_fallback(config)

        assert isinstance(backend, FileBackend)

    def test_create_backend_with_fallback_to_file(self):
        """Test creating backend with fallback to file backend."""
        config = AdvancedCacheConfig(backend_type="dynamodb", dynamodb_table_name="test-table")

        # Mock DynamoDB backend creation to fail
        with patch.object(
            BackendFactory, "create_backend", side_effect=CacheBackendError("DynamoDB failed")
        ):
            with patch.object(BackendFactory, "_create_file_backend") as mock_create_file:
                mock_file_backend = Mock()
                mock_create_file.return_value = mock_file_backend

                backend = BackendFactory.create_backend_with_fallback(config)

                assert backend == mock_file_backend
                mock_create_file.assert_called_once()

    def test_create_backend_with_fallback_file_primary_fails(self):
        """Test creating backend with fallback when file is primary and fails."""
        config = AdvancedCacheConfig(backend_type="file")

        with patch.object(
            BackendFactory, "create_backend", side_effect=CacheBackendError("File backend failed")
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory.create_backend_with_fallback(config)

            assert "File backend failed" in str(exc_info.value)

    def test_create_backend_with_fallback_both_fail(self):
        """Test creating backend with fallback when both primary and fallback fail."""
        config = AdvancedCacheConfig(backend_type="dynamodb", dynamodb_table_name="test-table")

        with patch.object(
            BackendFactory, "create_backend", side_effect=CacheBackendError("DynamoDB failed")
        ):
            with patch.object(
                BackendFactory,
                "_create_file_backend",
                side_effect=Exception("File fallback failed"),
            ):
                with pytest.raises(CacheBackendError) as exc_info:
                    BackendFactory.create_backend_with_fallback(config)

                assert "Both dynamodb backend and file backend fallback failed" in str(
                    exc_info.value
                )
                assert exc_info.value.backend_type == "fallback"

    def test_create_file_backend_success(self):
        """Test successful file backend creation."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            config = AdvancedCacheConfig(file_cache_dir=temp_dir)

            backend = BackendFactory._create_file_backend(config)

            assert isinstance(backend, FileBackend)

    def test_create_file_backend_error(self):
        """Test file backend creation with error."""
        config = AdvancedCacheConfig(file_cache_dir="/invalid/path")

        with patch(
            "src.awsideman.cache.backends.file.FileBackend",
            side_effect=Exception("Creation failed"),
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory._create_file_backend(config)

            assert "Failed to create file backend" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_create_dynamodb_backend_success(self):
        """Test successful DynamoDB backend creation."""
        config = AdvancedCacheConfig(
            dynamodb_table_name="test-table",
            dynamodb_region="us-east-1",
            dynamodb_profile="test-profile",
        )

        mock_backend = Mock()

        with patch(
            "src.awsideman.cache.backends.dynamodb.DynamoDBBackend", return_value=mock_backend
        ) as mock_class:
            backend = BackendFactory._create_dynamodb_backend(config)

            assert backend == mock_backend
            mock_class.assert_called_once_with(
                table_name="test-table", region="us-east-1", profile="test-profile"
            )

    def test_create_dynamodb_backend_error(self):
        """Test DynamoDB backend creation with error."""
        config = AdvancedCacheConfig(dynamodb_table_name="test-table")

        with patch(
            "src.awsideman.cache.backends.dynamodb.DynamoDBBackend",
            side_effect=Exception("Creation failed"),
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory._create_dynamodb_backend(config)

            assert "Failed to create DynamoDB backend" in str(exc_info.value)
            assert exc_info.value.backend_type == "dynamodb"

    def test_create_hybrid_backend_success(self):
        """Test successful hybrid backend creation."""
        config = AdvancedCacheConfig(
            backend_type="hybrid", dynamodb_table_name="test-table", hybrid_local_ttl=600
        )

        mock_file_backend = Mock()
        mock_dynamodb_backend = Mock()
        mock_hybrid_backend = Mock()

        with patch(
            "src.awsideman.cache.backends.hybrid.HybridBackend", return_value=mock_hybrid_backend
        ) as mock_class:
            with patch.object(
                BackendFactory, "_create_file_backend", return_value=mock_file_backend
            ):
                with patch.object(
                    BackendFactory, "_create_dynamodb_backend", return_value=mock_dynamodb_backend
                ):
                    backend = BackendFactory._create_hybrid_backend(config)

                    assert backend == mock_hybrid_backend
                    mock_class.assert_called_once_with(
                        local_backend=mock_file_backend,
                        remote_backend=mock_dynamodb_backend,
                        local_ttl=600,
                    )

    def test_create_hybrid_backend_sub_backend_error(self):
        """Test hybrid backend creation when sub-backend creation fails."""
        config = AdvancedCacheConfig(backend_type="hybrid", dynamodb_table_name="test-table")

        with patch.object(
            BackendFactory, "_create_file_backend", side_effect=CacheBackendError("File failed")
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                BackendFactory._create_hybrid_backend(config)

            assert "File failed" in str(exc_info.value)

    def test_create_hybrid_backend_error(self):
        """Test hybrid backend creation with error."""
        config = AdvancedCacheConfig(backend_type="hybrid", dynamodb_table_name="test-table")

        mock_file_backend = Mock()
        mock_dynamodb_backend = Mock()

        with patch(
            "src.awsideman.cache.backends.hybrid.HybridBackend",
            side_effect=Exception("Creation failed"),
        ):
            with patch.object(
                BackendFactory, "_create_file_backend", return_value=mock_file_backend
            ):
                with patch.object(
                    BackendFactory, "_create_dynamodb_backend", return_value=mock_dynamodb_backend
                ):
                    with pytest.raises(CacheBackendError) as exc_info:
                        BackendFactory._create_hybrid_backend(config)

                    assert "Failed to create hybrid backend" in str(exc_info.value)
                    assert exc_info.value.backend_type == "hybrid"

    def test_get_available_backends_file_only(self):
        """Test getting available backends when only file is available."""
        # Mock the import to fail
        with patch("builtins.__import__") as mock_import:

            def side_effect(name, *args, **kwargs):
                if name == "boto3":
                    raise ImportError("No module named 'boto3'")
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            backends = BackendFactory.get_available_backends()

            assert backends == ["file"]

    def test_get_available_backends_all(self):
        """Test getting available backends when all are available."""
        # Just test the current state - if boto3 is available, all backends should be available
        backends = BackendFactory.get_available_backends()

        assert "file" in backends
        # Only check for other backends if boto3 is actually available
        try:
            import boto3  # noqa: F401

            assert "dynamodb" in backends
            assert "hybrid" in backends
        except ImportError:
            # If boto3 is not available, that's fine for this test
            pass

    def test_validate_backend_availability_file(self):
        """Test validating file backend availability."""
        assert BackendFactory.validate_backend_availability("file") is True
        assert BackendFactory.validate_backend_availability("FILE") is True

    def test_validate_backend_availability_dynamodb(self):
        """Test validating DynamoDB backend availability."""
        # Test based on actual boto3 availability
        try:
            import boto3  # noqa: F401

            assert BackendFactory.validate_backend_availability("dynamodb") is True
            assert BackendFactory.validate_backend_availability("DYNAMODB") is True
        except ImportError:
            assert BackendFactory.validate_backend_availability("dynamodb") is False

    def test_validate_backend_availability_unknown(self):
        """Test validating unknown backend availability."""
        assert BackendFactory.validate_backend_availability("unknown") is False

    def test_get_backend_info_file(self):
        """Test getting file backend information."""
        info = BackendFactory.get_backend_info("file")

        assert info["name"] == "File Backend"
        assert "Local file-based cache storage" in info["description"]
        assert info["requirements"] == []
        assert "Local storage" in info["features"]
        assert info["available"] is True

    def test_get_backend_info_dynamodb(self):
        """Test getting DynamoDB backend information."""
        info = BackendFactory.get_backend_info("dynamodb")

        assert info["name"] == "DynamoDB Backend"
        assert "AWS DynamoDB-based cache storage" in info["description"]
        assert "boto3" in info["requirements"]
        assert "Shared cache" in info["features"]
        # Availability depends on whether boto3 is actually installed
        try:
            import boto3  # noqa: F401

            assert info["available"] is True
        except ImportError:
            assert info["available"] is False

    def test_get_backend_info_hybrid(self):
        """Test getting hybrid backend information."""
        info = BackendFactory.get_backend_info("hybrid")

        assert info["name"] == "Hybrid Backend"
        assert "Combination of local file and DynamoDB storage" in info["description"]
        assert "boto3" in info["requirements"]
        assert "Best of both worlds" in info["features"]
        # Availability depends on whether boto3 is actually installed
        try:
            import boto3  # noqa: F401

            assert info["available"] is True
        except ImportError:
            assert info["available"] is False

    def test_get_backend_info_unknown(self):
        """Test getting unknown backend information."""
        info = BackendFactory.get_backend_info("unknown")

        assert info["name"] == "Unknown Backend"
        assert info["description"] == "Unknown backend type"
        assert info["requirements"] == []
        assert info["features"] == []
        assert info["available"] is False

    def test_get_backend_info_case_insensitive(self):
        """Test getting backend information is case insensitive."""
        info_lower = BackendFactory.get_backend_info("file")
        info_upper = BackendFactory.get_backend_info("FILE")
        info_mixed = BackendFactory.get_backend_info("File")

        assert info_lower == info_upper == info_mixed
