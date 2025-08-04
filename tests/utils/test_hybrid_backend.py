"""Tests for hybrid backend implementation."""

import json
import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from src.awsideman.cache.backends.hybrid import HybridBackend
from src.awsideman.cache.backends.base import CacheBackendError, BackendHealthStatus
from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.cache.backends.dynamodb import DynamoDBBackend


class TestHybridBackend:
    """Test cases for HybridBackend class."""
    
    @pytest.fixture
    def mock_file_backend(self):
        """Create a mock file backend."""
        backend = Mock(spec=FileBackend)
        backend.backend_type = "file"
        return backend
    
    @pytest.fixture
    def mock_dynamodb_backend(self):
        """Create a mock DynamoDB backend."""
        backend = Mock(spec=DynamoDBBackend)
        backend.backend_type = "dynamodb"
        return backend
    
    @pytest.fixture
    def hybrid_backend(self, mock_file_backend, mock_dynamodb_backend):
        """Create a hybrid backend with mocked sub-backends."""
        return HybridBackend(
            local_backend=mock_file_backend,
            remote_backend=mock_dynamodb_backend,
            local_ttl=300
        )
    
    def test_init(self, mock_file_backend, mock_dynamodb_backend):
        """Test hybrid backend initialization."""
        backend = HybridBackend(
            local_backend=mock_file_backend,
            remote_backend=mock_dynamodb_backend,
            local_ttl=600
        )
        
        assert backend.local_backend == mock_file_backend
        assert backend.remote_backend == mock_dynamodb_backend
        assert backend.local_ttl == 600
        assert backend.backend_type == "hybrid"
        assert backend._access_counts == {}
        assert backend._last_access_times == {}
    
    def test_get_local_cache_hit(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation with local cache hit."""
        test_data = b'{"test": "data"}'
        mock_file_backend.get.return_value = test_data
        
        result = hybrid_backend.get("test_key")
        
        assert result == test_data
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_not_called()
        
        # Check access tracking
        assert hybrid_backend._access_counts["test_key"] == 1
        assert "test_key" in hybrid_backend._last_access_times
    
    def test_get_remote_cache_hit_with_promotion(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation with remote cache hit and promotion to local."""
        test_data = b'{"test": "data"}'
        mock_file_backend.get.return_value = None
        mock_dynamodb_backend.get.return_value = test_data
        
        # Simulate multiple accesses to trigger promotion
        hybrid_backend._access_counts["test_key"] = 1
        
        result = hybrid_backend.get("test_key")
        
        assert result == test_data
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
        mock_file_backend.set.assert_called_once_with("test_key", test_data, 300, "promotion")
        
        # Check access tracking
        assert hybrid_backend._access_counts["test_key"] == 2
    
    def test_get_remote_cache_hit_no_promotion(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation with remote cache hit but no promotion."""
        test_data = b'{"test": "data"}'
        mock_file_backend.get.return_value = None
        mock_dynamodb_backend.get.return_value = test_data
        
        # Mock should_promote_to_local to return False for this test
        with patch.object(hybrid_backend, '_should_promote_to_local', return_value=False):
            result = hybrid_backend.get("test_key")
        
        assert result == test_data
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
        mock_file_backend.set.assert_not_called()  # No promotion when should_promote_to_local returns False
    
    def test_get_cache_miss(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation with cache miss in both backends."""
        mock_file_backend.get.return_value = None
        mock_dynamodb_backend.get.return_value = None
        
        result = hybrid_backend.get("test_key")
        
        assert result is None
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
    
    def test_get_local_backend_error(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation when local backend fails but remote succeeds."""
        test_data = b'{"test": "data"}'
        mock_file_backend.get.side_effect = CacheBackendError("Local error", "file")
        mock_dynamodb_backend.get.return_value = test_data
        
        result = hybrid_backend.get("test_key")
        
        assert result == test_data
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
    
    def test_get_remote_backend_error(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test get operation when remote backend fails."""
        mock_file_backend.get.return_value = None
        mock_dynamodb_backend.get.side_effect = CacheBackendError("Remote error", "dynamodb")
        
        with pytest.raises(CacheBackendError) as exc_info:
            hybrid_backend.get("test_key")
        
        assert "Remote error" in str(exc_info.value)
        mock_file_backend.get.assert_called_once_with("test_key")
        mock_dynamodb_backend.get.assert_called_once_with("test_key")
    
    def test_set_success(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test successful set operation to both backends."""
        test_data = b'{"test": "data"}'
        
        # Mock should_cache_locally to return True
        with patch.object(hybrid_backend, '_should_cache_locally', return_value=True):
            hybrid_backend.set("test_key", test_data, 3600, "test_operation")
        
        mock_dynamodb_backend.set.assert_called_once_with("test_key", test_data, 3600, "test_operation")
        mock_file_backend.set.assert_called_once_with("test_key", test_data, 300, "test_operation")
        
        # Check access tracking
        assert hybrid_backend._access_counts["test_key"] == 1
    
    def test_set_no_local_cache(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test set operation when local caching is not appropriate."""
        test_data = b'{"test": "data"}'
        
        # Mock should_cache_locally to return False
        with patch.object(hybrid_backend, '_should_cache_locally', return_value=False):
            hybrid_backend.set("test_key", test_data, 3600, "test_operation")
        
        mock_dynamodb_backend.set.assert_called_once_with("test_key", test_data, 3600, "test_operation")
        mock_file_backend.set.assert_not_called()
    
    def test_set_remote_failure(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test set operation when remote backend fails."""
        test_data = b'{"test": "data"}'
        mock_dynamodb_backend.set.side_effect = CacheBackendError("Remote error", "dynamodb")
        
        with patch.object(hybrid_backend, '_should_cache_locally', return_value=True):
            with pytest.raises(CacheBackendError) as exc_info:
                hybrid_backend.set("test_key", test_data, 3600, "test_operation")
        
        assert "Remote error" in str(exc_info.value)
        mock_dynamodb_backend.set.assert_called_once()
        # Local set should not be called if remote fails first
    
    def test_set_local_failure_remote_success(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test set operation when local backend fails but remote succeeds."""
        test_data = b'{"test": "data"}'
        mock_file_backend.set.side_effect = CacheBackendError("Local error", "file")
        
        with patch.object(hybrid_backend, '_should_cache_locally', return_value=True):
            # Should not raise error since remote succeeded
            hybrid_backend.set("test_key", test_data, 3600, "test_operation")
        
        mock_dynamodb_backend.set.assert_called_once_with("test_key", test_data, 3600, "test_operation")
        mock_file_backend.set.assert_called_once_with("test_key", test_data, 300, "test_operation")
    
    def test_invalidate_single_key(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test invalidating a single key from both backends."""
        # Set up some access tracking data
        hybrid_backend._access_counts["test_key"] = 5
        hybrid_backend._last_access_times["test_key"] = time.time()
        
        hybrid_backend.invalidate("test_key")
        
        mock_file_backend.invalidate.assert_called_once_with("test_key")
        mock_dynamodb_backend.invalidate.assert_called_once_with("test_key")
        
        # Check that access tracking data was cleared
        assert "test_key" not in hybrid_backend._access_counts
        assert "test_key" not in hybrid_backend._last_access_times
    
    def test_invalidate_all_keys(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test invalidating all keys from both backends."""
        # Set up some access tracking data
        hybrid_backend._access_counts = {"key1": 1, "key2": 2}
        hybrid_backend._last_access_times = {"key1": time.time(), "key2": time.time()}
        
        hybrid_backend.invalidate(None)
        
        mock_file_backend.invalidate.assert_called_once_with(None)
        mock_dynamodb_backend.invalidate.assert_called_once_with(None)
        
        # Check that all access tracking data was cleared
        assert hybrid_backend._access_counts == {}
        assert hybrid_backend._last_access_times == {}
    
    def test_invalidate_partial_failure(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test invalidate operation when one backend fails."""
        mock_file_backend.invalidate.side_effect = CacheBackendError("Local error", "file")
        
        # Should not raise error if only local fails
        hybrid_backend.invalidate("test_key")
        
        mock_file_backend.invalidate.assert_called_once_with("test_key")
        mock_dynamodb_backend.invalidate.assert_called_once_with("test_key")
    
    def test_invalidate_remote_failure(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test invalidate operation when remote backend fails."""
        mock_dynamodb_backend.invalidate.side_effect = CacheBackendError("Remote error", "dynamodb")
        
        with pytest.raises(CacheBackendError) as exc_info:
            hybrid_backend.invalidate("test_key")
        
        assert "Remote error" in str(exc_info.value)
    
    def test_get_stats(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test getting statistics from hybrid backend."""
        # Set up mock stats
        local_stats = {
            'backend_type': 'file',
            'valid_entries': 10,
            'total_size_mb': 5.2
        }
        remote_stats = {
            'backend_type': 'dynamodb',
            'item_count': 50,
            'table_size_bytes': 1024000
        }
        
        mock_file_backend.get_stats.return_value = local_stats
        mock_dynamodb_backend.get_stats.return_value = remote_stats
        
        # Set up some access tracking data
        hybrid_backend._access_counts = {"key1": 5, "key2": 3, "key3": 1}
        
        stats = hybrid_backend.get_stats()
        
        assert stats['backend_type'] == 'hybrid'
        assert stats['local_ttl'] == 300
        assert stats['local_backend'] == local_stats
        assert stats['remote_backend'] == remote_stats
        assert stats['access_tracking']['tracked_keys'] == 3
        assert stats['access_tracking']['total_accesses'] == 9
        assert stats['cache_efficiency']['local_entries'] == 10
        assert stats['cache_efficiency']['remote_entries'] == 50
        assert "20.0%" in stats['cache_efficiency']['local_hit_potential']
    
    def test_get_stats_backend_errors(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test getting statistics when sub-backends fail."""
        mock_file_backend.get_stats.side_effect = CacheBackendError("Local error", "file")
        mock_dynamodb_backend.get_stats.side_effect = CacheBackendError("Remote error", "dynamodb")
        
        stats = hybrid_backend.get_stats()
        
        assert stats['backend_type'] == 'hybrid'
        assert 'error' in stats['local_backend']
        assert 'error' in stats['remote_backend']
    
    def test_health_check_both_healthy(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test health check when both backends are healthy."""
        mock_file_backend.health_check.return_value = True
        mock_dynamodb_backend.health_check.return_value = True
        
        result = hybrid_backend.health_check()
        
        assert result is True
        mock_file_backend.health_check.assert_called_once()
        mock_dynamodb_backend.health_check.assert_called_once()
    
    def test_health_check_local_healthy_only(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test health check when only local backend is healthy."""
        mock_file_backend.health_check.return_value = True
        mock_dynamodb_backend.health_check.return_value = False
        
        result = hybrid_backend.health_check()
        
        assert result is True  # Should be healthy if at least one backend is healthy
    
    def test_health_check_remote_healthy_only(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test health check when only remote backend is healthy."""
        mock_file_backend.health_check.return_value = False
        mock_dynamodb_backend.health_check.return_value = True
        
        result = hybrid_backend.health_check()
        
        assert result is True  # Should be healthy if at least one backend is healthy
    
    def test_health_check_both_unhealthy(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test health check when both backends are unhealthy."""
        mock_file_backend.health_check.return_value = False
        mock_dynamodb_backend.health_check.return_value = False
        
        result = hybrid_backend.health_check()
        
        assert result is False
    
    def test_health_check_with_exceptions(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test health check when backends raise exceptions."""
        mock_file_backend.health_check.side_effect = Exception("Local error")
        mock_dynamodb_backend.health_check.return_value = True
        
        result = hybrid_backend.health_check()
        
        assert result is True  # Should still be healthy if remote is healthy
    
    def test_should_promote_to_local_multiple_accesses(self, hybrid_backend):
        """Test promotion logic for keys with multiple accesses."""
        hybrid_backend._access_counts["test_key"] = 2
        hybrid_backend._last_access_times["test_key"] = time.time()
        
        result = hybrid_backend._should_promote_to_local("test_key")
        
        assert result is True
    
    def test_should_promote_to_local_recent_access(self, hybrid_backend):
        """Test promotion logic for recently accessed keys."""
        current_time = time.time()
        hybrid_backend._access_counts["test_key"] = 1
        hybrid_backend._last_access_times["test_key"] = current_time - 50  # Within 25% of 300s TTL
        
        result = hybrid_backend._should_promote_to_local("test_key")
        
        assert result is True
    
    def test_should_promote_to_local_no_promotion(self, hybrid_backend):
        """Test promotion logic when promotion is not warranted."""
        current_time = time.time()
        hybrid_backend._access_counts["test_key"] = 1
        hybrid_backend._last_access_times["test_key"] = current_time - 200  # Outside promotion window
        
        result = hybrid_backend._should_promote_to_local("test_key")
        
        assert result is False
    
    def test_should_cache_locally_previous_access(self, hybrid_backend):
        """Test local caching logic for previously accessed keys."""
        hybrid_backend._access_counts["test_key"] = 1
        
        result = hybrid_backend._should_cache_locally("test_key", "unknown")
        
        assert result is True
    
    def test_should_cache_locally_high_frequency_operation(self, hybrid_backend):
        """Test local caching logic for high-frequency operations."""
        result = hybrid_backend._should_cache_locally("new_key", "list_roots")
        
        assert result is True
    
    def test_should_cache_locally_no_caching(self, hybrid_backend):
        """Test local caching logic when caching is not appropriate."""
        result = hybrid_backend._should_cache_locally("new_key", "unknown_operation")
        
        assert result is False
    
    def test_track_access(self, hybrid_backend):
        """Test access tracking functionality."""
        hybrid_backend._track_access("test_key")
        
        assert hybrid_backend._access_counts["test_key"] == 1
        assert "test_key" in hybrid_backend._last_access_times
        
        # Track again
        hybrid_backend._track_access("test_key")
        
        assert hybrid_backend._access_counts["test_key"] == 2
    
    def test_cleanup_old_tracking_data(self, hybrid_backend):
        """Test cleanup of old access tracking data."""
        current_time = time.time()
        old_time = current_time - 1000  # Very old
        
        # Set up old tracking data
        hybrid_backend._access_counts = {"old_key": 1, "new_key": 2}
        hybrid_backend._last_access_times = {"old_key": old_time, "new_key": current_time}
        
        hybrid_backend._cleanup_old_tracking_data()
        
        # Old key should be removed, new key should remain
        assert "old_key" not in hybrid_backend._access_counts
        assert "new_key" in hybrid_backend._access_counts
        assert "old_key" not in hybrid_backend._last_access_times
        assert "new_key" in hybrid_backend._last_access_times
    
    def test_get_most_accessed_keys(self, hybrid_backend):
        """Test getting most accessed keys."""
        hybrid_backend._access_counts = {
            "key1": 5,
            "key2": 3,
            "key3": 8,
            "key4": 1
        }
        
        result = hybrid_backend._get_most_accessed_keys(3)
        
        assert len(result) == 3
        assert result[0] == ("key3", 8)
        assert result[1] == ("key1", 5)
        assert result[2] == ("key2", 3)
    
    def test_get_most_accessed_keys_empty(self, hybrid_backend):
        """Test getting most accessed keys when no data exists."""
        result = hybrid_backend._get_most_accessed_keys(5)
        
        assert result == []
    
    def test_sync_backends(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test backend synchronization."""
        mock_file_backend.get_stats.return_value = {'backend_type': 'file'}
        mock_dynamodb_backend.get_stats.return_value = {'backend_type': 'dynamodb'}
        mock_file_backend.health_check.return_value = True
        mock_dynamodb_backend.health_check.return_value = True
        
        result = hybrid_backend.sync_backends()
        
        assert result['success'] is True
        assert len(result['errors']) == 0
    
    def test_sync_backends_unhealthy(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test backend synchronization when backends are unhealthy."""
        mock_file_backend.get_stats.return_value = {'backend_type': 'file'}
        mock_dynamodb_backend.get_stats.return_value = {'backend_type': 'dynamodb'}
        mock_file_backend.health_check.return_value = False
        mock_dynamodb_backend.health_check.return_value = False
        
        result = hybrid_backend.sync_backends()
        
        assert result['success'] is False
        assert len(result['errors']) > 0
    
    def test_get_detailed_health_status(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test getting detailed health status."""
        # Mock detailed health status methods
        local_status = BackendHealthStatus(True, "file", "Local healthy", 10.0)
        remote_status = BackendHealthStatus(True, "dynamodb", "Remote healthy", 20.0)
        
        # Add the method to the mock
        mock_file_backend.get_detailed_health_status = Mock(return_value=local_status)
        mock_dynamodb_backend.get_detailed_health_status = Mock(return_value=remote_status)
        
        status = hybrid_backend.get_detailed_health_status()
        
        assert status.is_healthy is True
        assert status.backend_type == "hybrid"
        assert "Both local and remote backends are healthy" in status.message
        assert status.response_time_ms is not None
    
    def test_get_detailed_health_status_mixed(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test getting detailed health status with mixed backend health."""
        # Mock one healthy, one unhealthy
        local_status = BackendHealthStatus(True, "file", "Local healthy", 10.0)
        remote_status = BackendHealthStatus(False, "dynamodb", "Remote unhealthy", 20.0)
        
        # Add the method to the mock
        mock_file_backend.get_detailed_health_status = Mock(return_value=local_status)
        mock_dynamodb_backend.get_detailed_health_status = Mock(return_value=remote_status)
        
        status = hybrid_backend.get_detailed_health_status()
        
        assert status.is_healthy is True  # Should be healthy if at least one is healthy
        assert status.backend_type == "hybrid"
        assert "Local backend healthy, remote backend unhealthy" in status.message
    
    def test_get_detailed_health_status_fallback(self, hybrid_backend, mock_file_backend, mock_dynamodb_backend):
        """Test getting detailed health status when backends don't have detailed method."""
        # Remove detailed health status methods
        del mock_file_backend.get_detailed_health_status
        del mock_dynamodb_backend.get_detailed_health_status
        
        mock_file_backend.health_check.return_value = True
        mock_dynamodb_backend.health_check.return_value = False
        
        status = hybrid_backend.get_detailed_health_status()
        
        assert status.is_healthy is True
        assert status.backend_type == "hybrid"
        assert status.response_time_ms is not None