"""Integration tests for hybrid backend functionality."""

import tempfile
import time
from unittest.mock import Mock, patch
import pytest

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory
from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.encryption.provider import EncryptionProviderFactory


class TestHybridBackendIntegration:
    """Integration tests for hybrid backend."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('boto3.Session')
    def test_hybrid_backend_creation_integration(self, mock_session):
        """Test hybrid backend creation integration."""
        # Mock boto3 components for DynamoDB backend
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table exists
        mock_table.load.return_value = None
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="hybrid-test-table",
            dynamodb_region="us-east-1",
            hybrid_local_ttl=300,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Verify hybrid backend was created
        assert backend.backend_type == "hybrid"
        assert backend.local_ttl == 300
        
        # Verify sub-backends were created
        assert isinstance(backend.local_backend, FileBackend)
        assert backend.remote_backend.table_name == "hybrid-test-table"
    
    @patch('boto3.Session')
    def test_hybrid_cache_promotion_integration(self, mock_session):
        """Test hybrid cache promotion integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_table.put_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="promotion-table",
            hybrid_local_ttl=300,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"promotion": "test", "access_count": 0}
        encrypted_data = encryption.encrypt(test_data)
        
        # Store data in remote backend only (simulate remote-only data)
        import base64
        mock_table.get_item.return_value = {
            'Item': {
                'cache_key': 'promotion_key',
                'data': base64.b64encode(encrypted_data).decode('utf-8'),
                'operation': 'promotion_test',
                'created_at': int(time.time()),
                'ttl': int(time.time() + 3600)
            }
        }
        
        # First access - should get from remote and potentially promote
        retrieved_data = backend.get("promotion_key")
        assert retrieved_data == encrypted_data
        
        # Access again to trigger promotion logic
        retrieved_data2 = backend.get("promotion_key")
        assert retrieved_data2 == encrypted_data
        
        # Verify remote backend was accessed
        assert mock_table.get_item.called
    
    @patch('boto3.Session')
    def test_hybrid_local_cache_priority_integration(self, mock_session):
        """Test hybrid local cache priority integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_table.put_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="priority-table",
            hybrid_local_ttl=300,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"priority": "local", "fast_access": True}
        encrypted_data = encryption.encrypt(test_data)
        
        # Store data (should go to both backends)
        backend.set("priority_key", encrypted_data, ttl=3600, operation="priority_test")
        
        # Verify remote backend was called
        mock_table.put_item.assert_called_once()
        
        # Reset mock to track subsequent calls
        mock_table.get_item.reset_mock()
        
        # Get data - should come from local cache first
        retrieved_data = backend.get("priority_key")
        assert retrieved_data == encrypted_data
        
        # Verify remote backend was NOT called (local cache hit)
        mock_table.get_item.assert_not_called()
    
    @patch('boto3.Session')
    def test_hybrid_backend_health_check_integration(self, mock_session):
        """Test hybrid backend health check integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table exists and is healthy
        mock_table.load.return_value = None
        mock_client.describe_table.return_value = {
            'Table': {'TableStatus': 'ACTIVE'}
        }
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="health-table",
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Both backends healthy - should return True
        assert backend.health_check() is True
        
        # Test when remote backend is unhealthy but local is healthy
        mock_client.describe_table.side_effect = Exception("DynamoDB unavailable")
        
        # Should still return True (local backend is healthy)
        assert backend.health_check() is True
        
        # Test detailed health status
        if hasattr(backend, 'get_detailed_health_status'):
            status = backend.get_detailed_health_status()
            assert status.is_healthy is True  # At least local is healthy
            assert status.backend_type == "hybrid"
            assert "Local backend healthy" in status.message or "healthy" in status.message.lower()
    
    @patch('boto3.Session')
    def test_hybrid_stats_integration(self, mock_session):
        """Test hybrid backend stats integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_table.put_item.return_value = {}
        
        # Mock stats responses
        mock_client.describe_table.return_value = {
            'Table': {
                'TableStatus': 'ACTIVE',
                'ItemCount': 50,
                'TableSizeBytes': 1024
            }
        }
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="stats-table",
            hybrid_local_ttl=600,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Add some test data to local cache
        test_data = {"stats": "test"}
        encrypted_data = encryption.encrypt(test_data)
        backend.set("stats_key", encrypted_data, ttl=3600, operation="stats_test")
        
        # Get stats
        stats = backend.get_stats()
        
        # Verify hybrid-specific stats
        assert stats['backend_type'] == 'hybrid'
        assert stats['local_ttl'] == 600
        assert 'access_tracking' in stats
        assert 'local_backend' in stats
        assert 'remote_backend' in stats
        assert 'cache_efficiency' in stats
        
        # Verify sub-backend stats are included
        assert stats['local_backend']['backend_type'] == 'file'
        assert stats['remote_backend']['backend_type'] == 'dynamodb'
    
    @patch('boto3.Session')
    def test_hybrid_invalidation_integration(self, mock_session):
        """Test hybrid backend invalidation integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_table.put_item.return_value = {}
        mock_table.get_item.return_value = {'Item': {'is_chunked': False}}
        mock_table.delete_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="invalidation-table",
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Store test data
        test_data = {"invalidation": "test"}
        encrypted_data = encryption.encrypt(test_data)
        backend.set("invalidation_key", encrypted_data, ttl=3600, operation="invalidation_test")
        
        # Verify data exists in local cache
        local_data = backend.local_backend.get("invalidation_key")
        assert local_data is not None
        
        # Invalidate specific key
        backend.invalidate("invalidation_key")
        
        # Verify data is removed from both backends
        assert backend.local_backend.get("invalidation_key") is None
        mock_table.delete_item.assert_called_once()
        
        # Test invalidate all
        backend.set("test_key1", encrypted_data, ttl=3600, operation="test1")
        backend.set("test_key2", encrypted_data, ttl=3600, operation="test2")
        
        # Mock scan for invalidate all
        mock_table.scan.return_value = {
            'Items': [
                {'cache_key': 'test_key1'},
                {'cache_key': 'test_key2'}
            ]
        }
        
        # Mock batch writer
        mock_batch = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_batch)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_table.batch_writer.return_value = mock_context_manager
        
        backend.invalidate()  # Invalidate all
        
        # Verify local cache is cleared
        local_stats = backend.local_backend.get_stats()
        assert local_stats['valid_entries'] == 0
        
        # Verify remote invalidation was attempted
        mock_table.scan.assert_called()
    
    @patch('boto3.Session')
    def test_hybrid_error_handling_integration(self, mock_session):
        """Test hybrid backend error handling integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table exists initially
        mock_table.load.return_value = None
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="error-table",
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"error": "handling"}
        encrypted_data = encryption.encrypt(test_data)
        
        # Test remote backend failure during set
        from botocore.exceptions import ClientError
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}},
            'PutItem'
        )
        
        # Should still succeed due to local backend
        backend.set("error_key", encrypted_data, ttl=3600, operation="error_test")
        
        # Verify data is in local cache
        local_data = backend.local_backend.get("error_key")
        assert local_data == encrypted_data
        
        # Test remote backend failure during get
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}},
            'GetItem'
        )
        
        # Should still get data from local cache
        retrieved_data = backend.get("error_key")
        assert retrieved_data == encrypted_data
    
    @patch('boto3.Session')
    def test_hybrid_access_tracking_integration(self, mock_session):
        """Test hybrid backend access tracking integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_table.put_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="tracking-table",
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"tracking": "test"}
        encrypted_data = encryption.encrypt(test_data)
        
        # Store data
        backend.set("tracking_key", encrypted_data, ttl=3600, operation="tracking_test")
        
        # Access data multiple times to build tracking
        for _ in range(5):
            backend.get("tracking_key")
        
        # Check stats for access tracking
        stats = backend.get_stats()
        access_tracking = stats['access_tracking']
        
        assert access_tracking['tracked_keys'] >= 1
        assert access_tracking['total_accesses'] >= 5
        assert len(access_tracking['most_accessed_keys']) >= 1
        
        # Verify the most accessed key is tracked
        most_accessed = access_tracking['most_accessed_keys'][0]
        assert most_accessed[0] == 'tracking_key'
        assert most_accessed[1] >= 5  # Access count
    
    @patch('boto3.Session')
    def test_hybrid_sync_backends_integration(self, mock_session):
        """Test hybrid backend synchronization integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table operations
        mock_table.load.return_value = None
        mock_client.describe_table.return_value = {
            'Table': {'TableStatus': 'ACTIVE'}
        }
        
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="sync-table",
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Test sync operation
        sync_result = backend.sync_backends()
        
        # Verify sync result structure
        assert 'success' in sync_result
        assert 'local_to_remote' in sync_result
        assert 'remote_to_local' in sync_result
        assert 'errors' in sync_result
        
        # Should succeed when both backends are healthy
        assert sync_result['success'] is True
        assert len(sync_result['errors']) == 0
    
    def test_hybrid_backend_fallback_integration(self):
        """Test hybrid backend fallback when DynamoDB is unavailable."""
        config = AdvancedCacheConfig(
            backend_type="hybrid",
            dynamodb_table_name="fallback-table",
            file_cache_dir=self.temp_dir
        )
        
        # Mock boto3 unavailable
        with patch('src.awsideman.cache.backends.dynamodb.boto3', side_effect=ImportError("boto3 not available")):
            # Should fall back to file backend
            fallback_backend = BackendFactory.create_backend_with_fallback(config)
            
            assert fallback_backend.backend_type == "file"
            assert fallback_backend.health_check() is True
            
            # Should work normally as file backend
            encryption = EncryptionProviderFactory.create_provider("none")
            test_data = {"fallback": "test"}
            encrypted_data = encryption.encrypt(test_data)
            
            fallback_backend.set("fallback_key", encrypted_data, ttl=3600, operation="fallback_test")
            retrieved_data = fallback_backend.get("fallback_key")
            
            assert retrieved_data == encrypted_data
            decrypted_data = encryption.decrypt(retrieved_data)
            assert decrypted_data == test_data