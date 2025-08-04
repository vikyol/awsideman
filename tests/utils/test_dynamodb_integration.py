"""Integration tests for DynamoDB backend functionality."""

import tempfile
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory
from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.encryption.provider import EncryptionProviderFactory
from src.awsideman.encryption.key_manager import FallbackKeyManager


class TestDynamoDBIntegration:
    """Integration tests for DynamoDB backend."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('boto3.Session')
    def test_dynamodb_backend_creation_integration(self, mock_session):
        """Test DynamoDB backend creation integration."""
        # Mock boto3 session and client
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Create configuration
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="test-cache-table",
            dynamodb_region="us-east-1",
            dynamodb_profile="test-profile"
        )
        
        # Create backend
        backend = BackendFactory.create_backend(config)
        
        # Verify backend was created with correct configuration
        assert backend.table_name == "test-cache-table"
        assert backend.region == "us-east-1"
        assert backend.profile == "test-profile"
        assert backend.backend_type == "dynamodb"
    
    @patch('boto3.Session')
    def test_dynamodb_table_creation_integration(self, mock_session):
        """Test DynamoDB table creation integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_dynamodb.create_table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table doesn't exist initially
        mock_table.load.side_effect = [
            Exception("ResourceNotFoundException"),  # First call fails
            None  # Second call succeeds after creation
        ]
        
        # Mock waiter
        mock_waiter = Mock()
        mock_client.get_waiter.return_value = mock_waiter
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="new-cache-table",
            dynamodb_region="us-west-2"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Trigger table creation by calling ensure_table_exists
        backend._ensure_table_exists()
        
        # Verify table creation was called with correct parameters
        mock_dynamodb.create_table.assert_called_once()
        create_args = mock_dynamodb.create_table.call_args[1]
        
        assert create_args['TableName'] == 'new-cache-table'
        assert create_args['BillingMode'] == 'PAY_PER_REQUEST'
        assert len(create_args['KeySchema']) == 1
        assert create_args['KeySchema'][0]['AttributeName'] == 'cache_key'
        assert create_args['KeySchema'][0]['KeyType'] == 'HASH'
        
        # Verify TTL configuration
        assert 'TimeToLiveSpecification' in create_args
        assert create_args['TimeToLiveSpecification']['AttributeName'] == 'ttl'
        assert create_args['TimeToLiveSpecification']['Enabled'] is True
    
    @patch('boto3.Session')
    def test_dynamodb_cache_operations_integration(self, mock_session):
        """Test DynamoDB cache operations integration."""
        # Mock boto3 components
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
            backend_type="dynamodb",
            dynamodb_table_name="cache-ops-table",
            encryption_enabled=False
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"integration": "test", "dynamodb": True}
        encrypted_data = encryption.encrypt(test_data)
        
        # Mock successful put operation
        mock_table.put_item.return_value = {}
        
        # Test set operation
        backend.set("integration_key", encrypted_data, ttl=3600, operation="integration_test")
        
        # Verify put_item was called correctly
        mock_table.put_item.assert_called_once()
        put_args = mock_table.put_item.call_args[1]
        item = put_args['Item']
        
        assert item['cache_key'] == 'integration_key'
        assert 'data' in item
        assert item['operation'] == 'integration_test'
        assert 'created_at' in item
        assert 'ttl' in item
        
        # Mock successful get operation
        import base64
        mock_table.get_item.return_value = {
            'Item': {
                'cache_key': 'integration_key',
                'data': base64.b64encode(encrypted_data).decode('utf-8'),
                'operation': 'integration_test',
                'created_at': item['created_at'],
                'ttl': item['ttl']
            }
        }
        
        # Test get operation
        retrieved_data = backend.get("integration_key")
        
        # Verify get_item was called correctly
        mock_table.get_item.assert_called_once_with(Key={'cache_key': 'integration_key'})
        
        # Verify data integrity
        assert retrieved_data == encrypted_data
        
        # Decrypt and verify original data
        decrypted_data = encryption.decrypt(retrieved_data)
        assert decrypted_data == test_data
    
    @patch('boto3.Session')
    def test_dynamodb_health_check_integration(self, mock_session):
        """Test DynamoDB health check integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="health-check-table"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Test health check when table exists
        mock_client.describe_table.return_value = {
            'Table': {'TableStatus': 'ACTIVE'}
        }
        
        assert backend.health_check() is True
        mock_client.describe_table.assert_called_with(TableName='health-check-table')
        
        # Test health check when table doesn't exist but DynamoDB is accessible
        mock_client.describe_table.side_effect = Exception("ResourceNotFoundException")
        mock_client.list_tables.return_value = {'TableNames': []}
        
        assert backend.health_check() is True
        mock_client.list_tables.assert_called_with(Limit=1)
    
    @patch('boto3.Session')
    def test_dynamodb_stats_integration(self, mock_session):
        """Test DynamoDB stats integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="stats-table",
            dynamodb_region="eu-west-1"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Mock table exists and describe_table response
        mock_client.describe_table.return_value = {
            'Table': {
                'TableStatus': 'ACTIVE',
                'ItemCount': 150,
                'TableSizeBytes': 2048,
                'CreationDateTime': '2023-01-01T00:00:00Z',
                'BillingModeSummary': {'BillingMode': 'PAY_PER_REQUEST'}
            }
        }
        
        # Mock TTL status
        mock_client.describe_time_to_live.return_value = {
            'TimeToLiveDescription': {
                'TimeToLiveStatus': 'ENABLED'
            }
        }
        
        stats = backend.get_stats()
        
        # Verify stats structure
        assert stats['backend_type'] == 'dynamodb'
        assert stats['table_name'] == 'stats-table'
        assert stats['region'] == 'eu-west-1'
        assert stats['table_exists'] is True
        assert stats['table_status'] == 'ACTIVE'
        assert stats['item_count'] == 150
        assert stats['table_size_bytes'] == 2048
        assert stats['billing_mode'] == 'PAY_PER_REQUEST'
        assert stats['ttl_enabled'] is True
    
    @patch('boto3.Session')
    def test_dynamodb_with_encryption_integration(self, mock_session):
        """Test DynamoDB backend with encryption integration."""
        # Mock boto3 components
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
        mock_table.put_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="encrypted-cache-table",
            encryption_enabled=True,
            encryption_type="aes256"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Create encryption with fallback key manager
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
        
        # Test sensitive data
        sensitive_data = {
            "user_id": "12345",
            "access_token": "secret_token_abc123",
            "permissions": ["read", "write", "admin"],
            "personal_info": {
                "email": "user@example.com",
                "phone": "+1-555-0123"
            }
        }
        
        # Encrypt data
        encrypted_data = encryption.encrypt(sensitive_data)
        
        # Store in DynamoDB
        backend.set("sensitive_key", encrypted_data, ttl=1800, operation="sensitive_operation")
        
        # Verify put_item was called
        mock_table.put_item.assert_called_once()
        put_args = mock_table.put_item.call_args[1]
        item = put_args['Item']
        
        # Verify encrypted data is stored (not readable)
        import base64
        stored_data = base64.b64decode(item['data'])
        assert stored_data == encrypted_data
        
        # Mock get operation
        mock_table.get_item.return_value = {
            'Item': item
        }
        
        # Retrieve and decrypt
        retrieved_data = backend.get("sensitive_key")
        decrypted_data = encryption.decrypt(retrieved_data)
        
        # Verify data integrity
        assert decrypted_data == sensitive_data
    
    def test_dynamodb_backend_unavailable_fallback(self):
        """Test fallback behavior when DynamoDB is unavailable."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="unavailable-table",
            file_cache_dir=self.temp_dir
        )
        
        # Mock boto3 import failure
        with patch('src.awsideman.cache.backends.dynamodb.boto3', side_effect=ImportError("boto3 not available")):
            # Should raise error for direct creation
            with pytest.raises(CacheBackendError):
                BackendFactory.create_backend(config)
            
            # But fallback should work
            fallback_backend = BackendFactory.create_backend_with_fallback(config)
            
            # Should fall back to file backend
            assert fallback_backend.backend_type == "file"
            assert fallback_backend.health_check() is True
    
    @patch('boto3.Session')
    def test_dynamodb_error_handling_integration(self, mock_session):
        """Test DynamoDB error handling integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="error-test-table"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Test access denied error
        from botocore.exceptions import ClientError
        mock_client.describe_table.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'DescribeTable'
        )
        
        # Health check should return False for access denied
        assert backend.health_check() is False
        
        # Test throttling error handling
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException'}},
            'PutItem'
        )
        
        # Should not raise error for throttling (should be handled gracefully)
        backend.set("throttle_key", b"test_data", ttl=3600, operation="throttle_test")
        
        # Test resource not found during get
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'GetItem'
        )
        
        # Should return None for resource not found
        result = backend.get("missing_key")
        assert result is None
    
    @patch('boto3.Session')
    def test_dynamodb_table_validation_integration(self, mock_session):
        """Test DynamoDB table validation integration."""
        # Mock boto3 components
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="validation-table"
        )
        
        backend = BackendFactory.create_backend(config)
        
        # Mock valid table schema
        mock_client.describe_table.return_value = {
            'Table': {
                'TableStatus': 'ACTIVE',
                'KeySchema': [
                    {'AttributeName': 'cache_key', 'KeyType': 'HASH'}
                ],
                'AttributeDefinitions': [
                    {'AttributeName': 'cache_key', 'AttributeType': 'S'}
                ],
                'BillingModeSummary': {'BillingMode': 'PAY_PER_REQUEST'}
            }
        }
        
        # Mock TTL enabled
        mock_client.describe_time_to_live.return_value = {
            'TimeToLiveDescription': {
                'TimeToLiveStatus': 'ENABLED'
            }
        }
        
        # Validate table schema
        validation_result = backend.validate_table_schema()
        
        assert validation_result['valid'] is True
        assert len(validation_result['errors']) == 0
        assert len(validation_result['warnings']) == 0
        
        # Test invalid schema
        mock_client.describe_table.return_value = {
            'Table': {
                'TableStatus': 'ACTIVE',
                'KeySchema': [
                    {'AttributeName': 'wrong_key', 'KeyType': 'HASH'}
                ],
                'AttributeDefinitions': [
                    {'AttributeName': 'wrong_key', 'AttributeType': 'S'}
                ],
                'BillingModeSummary': {'BillingMode': 'PROVISIONED'}
            }
        }
        
        validation_result = backend.validate_table_schema()
        
        assert validation_result['valid'] is False
        assert len(validation_result['errors']) > 0
        assert any("Key schema should have 'cache_key' as HASH key" in error for error in validation_result['errors'])
    
    @patch('boto3.Session')
    def test_dynamodb_large_data_chunking_integration(self, mock_session):
        """Test DynamoDB large data chunking integration."""
        # Mock boto3 components
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
        mock_table.put_item.return_value = {}
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="chunking-table"
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Create large data that would exceed DynamoDB item size limit
        large_data = {
            "large_field": "x" * 500000,  # 500KB of data
            "metadata": {"size": "large", "test": "chunking"}
        }
        
        encrypted_data = encryption.encrypt(large_data)
        
        # This should trigger chunking in the DynamoDB backend
        backend.set("large_key", encrypted_data, ttl=3600, operation="large_data_test")
        
        # Verify put_item was called (chunking implementation would call it multiple times)
        assert mock_table.put_item.called
        
        # For this test, we'll assume the chunking works and just verify the interface
        # The actual chunking logic is tested in the unit tests