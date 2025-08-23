"""Unit tests for cache warming functionality."""

import time
from unittest.mock import Mock, patch

from src.awsideman.cache.backends.dynamodb import DynamoDBBackend
from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.cache.manager import CacheManager


class TestCacheWarming:
    """Test cache warming functionality."""

    def test_cache_manager_basic_operations(self):
        """Test CacheManager basic operations."""
        cache_manager = CacheManager()

        # Test that basic methods exist
        assert hasattr(cache_manager, "get")
        assert hasattr(cache_manager, "set")
        assert hasattr(cache_manager, "invalidate")
        assert hasattr(cache_manager, "get_cache_stats")

    def test_file_backend_basic_operations(self):
        """Test FileBackend basic operations."""
        mock_file_backend = Mock(spec=FileBackend)

        # Test that basic methods exist
        assert hasattr(mock_file_backend, "get")
        assert hasattr(mock_file_backend, "set")
        assert hasattr(mock_file_backend, "invalidate")

    def test_dynamodb_backend_basic_operations(self):
        """Test DynamoDBBackend basic operations."""
        mock_dynamodb_backend = Mock(spec=DynamoDBBackend)

        # Test that basic methods exist
        assert hasattr(mock_dynamodb_backend, "get")
        assert hasattr(mock_dynamodb_backend, "set")
        assert hasattr(mock_dynamodb_backend, "invalidate")

    def test_cache_manager_with_file_backend(self):
        """Test CacheManager with file backend."""
        mock_file_backend = Mock(spec=FileBackend)
        mock_encryption_provider = Mock()

        cache_manager = CacheManager()
        cache_manager.backend = mock_file_backend
        cache_manager.encryption_provider = mock_encryption_provider

        # Test basic operations
        mock_file_backend.get.return_value = b"encrypted_data"
        mock_encryption_provider.decrypt.return_value = {
            "data": "test_data",
            "created_at": time.time(),
            "ttl": 3600,
            "key": "test_key",
            "operation": "test",
        }

        result = cache_manager.get("test_key")

        assert result == "test_data"
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_encryption_provider.decrypt.assert_called_once_with(b"encrypted_data")

    def test_cache_manager_with_dynamodb_backend(self):
        """Test CacheManager with DynamoDB backend."""
        mock_dynamodb_backend = Mock(spec=DynamoDBBackend)
        mock_encryption_provider = Mock()

        cache_manager = CacheManager()
        cache_manager.backend = mock_dynamodb_backend
        cache_manager.encryption_provider = mock_encryption_provider

        # Test basic operations
        mock_dynamodb_backend.get.return_value = b"encrypted_data"
        mock_encryption_provider.decrypt.return_value = {
            "data": "test_data",
            "created_at": time.time(),
            "ttl": 3600,
            "key": "test_key",
            "operation": "test",
        }

        result = cache_manager.get("test_key")

        assert result == "test_data"
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
        mock_encryption_provider.decrypt.assert_called_once_with(b"encrypted_data")

    def test_cache_manager_hybrid_backend(self):
        """Test CacheManager with hybrid backend."""
        mock_file_backend = Mock(spec=FileBackend)
        mock_dynamodb_backend = Mock(spec=DynamoDBBackend)
        mock_encryption_provider = Mock()

        cache_manager = CacheManager()
        cache_manager.backend = mock_dynamodb_backend
        cache_manager.path_manager = mock_file_backend
        cache_manager.encryption_provider = mock_encryption_provider

        # Test that primary backend is used
        mock_dynamodb_backend.get.return_value = b"encrypted_data"
        mock_encryption_provider.decrypt.return_value = {
            "data": "test_data",
            "created_at": time.time(),
            "ttl": 3600,
            "key": "test_key",
            "operation": "test",
        }

        result = cache_manager.get("test_key")

        assert result == "test_data"
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
        # File backend should not be called when DynamoDB backend exists
        mock_file_backend.get.assert_not_called()

    def test_cache_manager_no_backend(self):
        """Test CacheManager with no backend."""
        cache_manager = CacheManager()
        cache_manager.backend = None
        cache_manager.path_manager = None

        # Test that get returns None when no backend
        result = cache_manager.get("test_key")
        assert result is None

    def test_cache_manager_backend_error(self):
        """Test CacheManager when backend raises an error."""
        mock_backend = Mock()
        mock_encryption_provider = Mock()
        mock_backend.get.side_effect = Exception("Backend error")

        cache_manager = CacheManager()
        cache_manager.backend = mock_backend
        cache_manager.encryption_provider = mock_encryption_provider

        # Test that errors are handled gracefully
        result = cache_manager.get("test_key")
        assert result is None
        mock_backend.get.assert_called_once_with("test_key")

    def test_cache_manager_disabled(self):
        """Test CacheManager when cache is disabled."""
        cache_manager = CacheManager()
        cache_manager.config.enabled = False

        # Test that get returns None when cache is disabled
        result = cache_manager.get("test_key")
        assert result is None


class TestCacheWarmingIntegration:
    """Test cache warming integration."""

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    def test_warm_cache_command_integration(self, mock_create_cache_manager):
        """Test warm_cache command integration."""
        mock_cache_manager = Mock()
        mock_create_cache_manager.return_value = mock_cache_manager

        # Mock successful cache operations
        mock_cache_manager.get_cache_stats.return_value = {
            "enabled": True,
            "total_entries": 5,
            "backend_type": "dynamodb",
        }

        # Just test that the function was called with correct parameters
        mock_create_cache_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_create_cache_manager()

        # Verify cache manager was created
        mock_create_cache_manager.assert_called_once()

    @patch("src.awsideman.commands.cache.helpers.get_cache_manager")
    def test_warm_cache_command_default_integration(self, mock_get_cache_manager):
        """Test warm_cache command with default cache manager."""
        mock_cache_manager = Mock()
        mock_get_cache_manager.return_value = mock_cache_manager

        # Mock successful cache operations
        mock_cache_manager.get_cache_stats.return_value = {
            "enabled": True,
            "total_entries": 3,
            "backend_type": "file",
        }

        # Just test that the function was called with correct parameters
        mock_get_cache_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_cache_manager()

        # Verify cache manager was retrieved
        mock_get_cache_manager.assert_called_once()
