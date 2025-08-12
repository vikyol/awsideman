"""Tests for DynamoDB backend implementation."""

import base64
import time
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.cache.backends.dynamodb import DynamoDBBackend


class TestDynamoDBBackend:
    """Test cases for DynamoDB backend."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backend = DynamoDBBackend(
            table_name="test-cache-table", region="us-east-1", profile="test-profile"
        )

    def test_init(self):
        """Test backend initialization."""
        assert self.backend.table_name == "test-cache-table"
        assert self.backend.region == "us-east-1"
        assert self.backend.profile == "test-profile"
        assert self.backend._client is None
        assert self.backend._table is None
        assert self.backend._table_exists is None

    @patch("boto3.Session")
    def test_client_property(self, mock_session):
        """Test client property creates DynamoDB client."""
        mock_client = Mock()
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session.return_value = mock_session_instance

        client = self.backend.client

        assert client == mock_client
        mock_session.assert_called_once_with(profile_name="test-profile", region_name="us-east-1")
        mock_session_instance.client.assert_called_once_with("dynamodb")

    @patch("boto3.Session")
    def test_client_property_error(self, mock_session):
        """Test client property handles creation errors."""
        mock_session.side_effect = Exception("Connection failed")

        with pytest.raises(CacheBackendError) as exc_info:
            _ = self.backend.client

        assert "Failed to create DynamoDB client" in str(exc_info.value)
        assert exc_info.value.backend_type == "dynamodb"

    @patch("boto3.Session")
    def test_table_property(self, mock_session):
        """Test table property creates DynamoDB table resource."""
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_session_instance = Mock()
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance

        table = self.backend.table

        assert table == mock_table
        mock_session.assert_called_once_with(profile_name="test-profile", region_name="us-east-1")
        mock_session_instance.resource.assert_called_once_with("dynamodb")
        mock_dynamodb.Table.assert_called_once_with("test-cache-table")

    @patch("boto3.Session")
    def test_table_property_error(self, mock_session):
        """Test table property handles creation errors."""
        mock_session.side_effect = Exception("Connection failed")

        with pytest.raises(CacheBackendError) as exc_info:
            _ = self.backend.table

        assert "Failed to create DynamoDB table resource" in str(exc_info.value)
        assert exc_info.value.backend_type == "dynamodb"

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_success(self, mock_table, mock_ensure_table):
        """Test successful get operation."""
        # Setup mock response
        test_data = b"test cache data"
        encoded_data = base64.b64encode(test_data).decode("utf-8")

        mock_table.get_item.return_value = {
            "Item": {
                "cache_key": "test-key",
                "data": encoded_data,
                "operation": "test-op",
                "created_at": int(time.time()),
            }
        }

        result = self.backend.get("test-key")

        assert result == test_data
        mock_ensure_table.assert_called_once()
        mock_table.get_item.assert_called_once_with(Key={"cache_key": "test-key"})

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_not_found(self, mock_table, mock_ensure_table):
        """Test get operation when item not found."""
        mock_table.get_item.return_value = {}

        result = self.backend.get("nonexistent-key")

        assert result is None
        mock_ensure_table.assert_called_once()
        mock_table.get_item.assert_called_once_with(Key={"cache_key": "nonexistent-key"})

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_expired(self, mock_table, mock_ensure_table):
        """Test get operation with expired item."""
        test_data = b"test cache data"
        encoded_data = base64.b64encode(test_data).decode("utf-8")
        expired_ttl = int(time.time()) - 3600  # 1 hour ago

        mock_table.get_item.return_value = {
            "Item": {
                "cache_key": "test-key",
                "data": encoded_data,
                "operation": "test-op",
                "created_at": int(time.time()) - 3600,
                "ttl": expired_ttl,
            }
        }

        result = self.backend.get("test-key")

        assert result is None
        mock_ensure_table.assert_called_once()
        mock_table.get_item.assert_called_once_with(Key={"cache_key": "test-key"})

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_not_expired(self, mock_table, mock_ensure_table):
        """Test get operation with non-expired item."""
        test_data = b"test cache data"
        encoded_data = base64.b64encode(test_data).decode("utf-8")
        future_ttl = int(time.time()) + 3600  # 1 hour from now

        mock_table.get_item.return_value = {
            "Item": {
                "cache_key": "test-key",
                "data": encoded_data,
                "operation": "test-op",
                "created_at": int(time.time()),
                "ttl": future_ttl,
            }
        }

        result = self.backend.get("test-key")

        assert result == test_data
        mock_ensure_table.assert_called_once()
        mock_table.get_item.assert_called_once_with(Key={"cache_key": "test-key"})

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_client_error_resource_not_found(self, mock_table, mock_ensure_table):
        """Test get operation with ResourceNotFoundException."""
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "GetItem"
        )

        result = self.backend.get("test-key")

        assert result is None
        mock_ensure_table.assert_called_once()

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_client_error_throttling(self, mock_table, mock_ensure_table):
        """Test get operation with throttling error."""
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "GetItem"
        )

        result = self.backend.get("test-key")

        assert result is None
        mock_ensure_table.assert_called_once()

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_get_client_error_other(self, mock_table, mock_ensure_table):
        """Test get operation with other client error."""
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "GetItem"
        )

        with pytest.raises(CacheBackendError) as exc_info:
            self.backend.get("test-key")

        assert "DynamoDB get operation failed" in str(exc_info.value)
        assert exc_info.value.backend_type == "dynamodb"

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_set_success(self, mock_table, mock_ensure_table):
        """Test successful set operation."""
        test_data = b"test cache data"

        self.backend.set("test-key", test_data, ttl=3600, operation="test-op")

        mock_ensure_table.assert_called_once()
        mock_table.put_item.assert_called_once()

        # Verify the item structure
        call_args = mock_table.put_item.call_args[1]
        item = call_args["Item"]

        assert item["cache_key"] == "test-key"
        assert base64.b64decode(item["data"]) == test_data
        assert item["operation"] == "test-op"
        assert "created_at" in item
        assert "ttl" in item
        assert item["ttl"] > int(time.time())

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_set_no_ttl(self, mock_table, mock_ensure_table):
        """Test set operation without TTL."""
        test_data = b"test cache data"

        self.backend.set("test-key", test_data, operation="test-op")

        mock_ensure_table.assert_called_once()
        mock_table.put_item.assert_called_once()

        # Verify the item structure
        call_args = mock_table.put_item.call_args[1]
        item = call_args["Item"]

        assert item["cache_key"] == "test-key"
        assert base64.b64decode(item["data"]) == test_data
        assert item["operation"] == "test-op"
        assert "created_at" in item
        assert "ttl" not in item

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "_create_table")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_set_table_not_found(self, mock_table, mock_create_table, mock_ensure_table):
        """Test set operation when table doesn't exist."""
        test_data = b"test cache data"

        # First call fails with ResourceNotFoundException, second succeeds
        mock_table.put_item.side_effect = [
            ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "PutItem"),
            None,
        ]

        self.backend.set("test-key", test_data, operation="test-op")

        mock_ensure_table.assert_called_once()
        mock_create_table.assert_called_once()
        assert mock_table.put_item.call_count == 2

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_set_throttling(self, mock_table, mock_ensure_table):
        """Test set operation with throttling error."""
        test_data = b"test cache data"

        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"
        )

        # Should not raise error for throttling
        self.backend.set("test-key", test_data, operation="test-op")

        mock_ensure_table.assert_called_once()

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_set_client_error_other(self, mock_table, mock_ensure_table):
        """Test set operation with other client error."""
        test_data = b"test cache data"

        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "PutItem"
        )

        with pytest.raises(CacheBackendError) as exc_info:
            self.backend.set("test-key", test_data, operation="test-op")

        assert "DynamoDB put operation failed" in str(exc_info.value)
        assert exc_info.value.backend_type == "dynamodb"

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_invalidate_specific_key(self, mock_table, mock_ensure_table):
        """Test invalidate operation for specific key."""
        # Mock get_item to return non-chunked item
        mock_table.get_item.return_value = {"Item": {"cache_key": "test-key", "is_chunked": False}}

        self.backend.invalidate("test-key")

        mock_ensure_table.assert_called_once()
        mock_table.get_item.assert_called_once_with(Key={"cache_key": "test-key"})
        mock_table.delete_item.assert_called_once_with(Key={"cache_key": "test-key"})

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "_invalidate_all_entries")
    def test_invalidate_all_keys(self, mock_invalidate_all, mock_ensure_table):
        """Test invalidate operation for all keys."""
        self.backend.invalidate(None)

        mock_ensure_table.assert_called_once()
        mock_invalidate_all.assert_called_once()

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_invalidate_resource_not_found(self, mock_table, mock_ensure_table):
        """Test invalidate operation when table doesn't exist."""
        # Mock get_item to return empty response
        mock_table.get_item.return_value = {}

        mock_table.delete_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "DeleteItem"
        )

        # Should not raise error when table doesn't exist
        self.backend.invalidate("test-key")

        mock_ensure_table.assert_called_once()

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_get_stats_table_exists(self, mock_client, mock_check_table):
        """Test get_stats when table exists."""
        mock_check_table.return_value = True

        mock_client.describe_table.return_value = {
            "Table": {
                "TableStatus": "ACTIVE",
                "ItemCount": 100,
                "TableSizeBytes": 1024,
                "CreationDateTime": "2023-01-01T00:00:00Z",
                "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
            }
        }

        with patch.object(self.backend, "_is_ttl_enabled", return_value=True):
            stats = self.backend.get_stats()

        assert stats["backend_type"] == "dynamodb"
        assert stats["table_name"] == "test-cache-table"
        assert stats["region"] == "us-east-1"
        assert stats["profile"] == "test-profile"
        assert stats["table_exists"] is True
        assert stats["table_status"] == "ACTIVE"
        assert stats["item_count"] == 100
        assert stats["table_size_bytes"] == 1024
        assert stats["billing_mode"] == "PAY_PER_REQUEST"
        assert stats["ttl_enabled"] is True

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_get_stats_table_not_exists(self, mock_check_table):
        """Test get_stats when table doesn't exist."""
        mock_check_table.return_value = False

        stats = self.backend.get_stats()

        assert stats["backend_type"] == "dynamodb"
        assert stats["table_name"] == "test-cache-table"
        assert stats["table_exists"] is False
        assert stats["item_count"] == 0
        assert stats["table_size_bytes"] == 0
        assert stats["table_status"] == "UNKNOWN"

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_get_stats_error(self, mock_check_table):
        """Test get_stats with client error."""
        mock_check_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "DescribeTable"
        )

        stats = self.backend.get_stats()

        assert stats["backend_type"] == "dynamodb"
        assert stats["table_name"] == "test-cache-table"
        assert stats["table_exists"] is False
        assert "error" in stats

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_health_check_success_table_exists(self, mock_client, mock_check_table):
        """Test health check when table exists."""
        mock_check_table.return_value = True

        result = self.backend.health_check()

        assert result is True
        mock_client.describe_table.assert_called_once_with(TableName="test-cache-table")

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_health_check_success_table_not_exists(self, mock_client, mock_check_table):
        """Test health check when table doesn't exist but DynamoDB is accessible."""
        mock_check_table.return_value = False

        result = self.backend.health_check()

        assert result is True
        mock_client.list_tables.assert_called_once_with(Limit=1)

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_health_check_no_credentials(self, mock_check_table):
        """Test health check with no credentials."""
        mock_check_table.side_effect = NoCredentialsError()

        result = self.backend.health_check()

        assert result is False

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_health_check_access_denied(self, mock_check_table):
        """Test health check with access denied."""
        mock_check_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "DescribeTable"
        )

        result = self.backend.health_check()

        assert result is False

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_check_table_exists_true(self, mock_client):
        """Test _check_table_exists when table exists."""
        result = self.backend._check_table_exists()

        assert result is True
        mock_client.describe_table.assert_called_once_with(TableName="test-cache-table")

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_check_table_exists_false(self, mock_client):
        """Test _check_table_exists when table doesn't exist."""
        mock_client.describe_table.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeTable"
        )

        result = self.backend._check_table_exists()

        assert result is False

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_check_table_exists_error(self, mock_client):
        """Test _check_table_exists with other error."""
        mock_client.describe_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "DescribeTable"
        )

        with pytest.raises(CacheBackendError) as exc_info:
            self.backend._check_table_exists()

        assert "Failed to check if table exists" in str(exc_info.value)

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "_create_table")
    def test_ensure_table_exists_creates_table(self, mock_create_table, mock_check_table):
        """Test _ensure_table_exists creates table when it doesn't exist."""
        mock_check_table.return_value = False

        self.backend._ensure_table_exists()

        mock_create_table.assert_called_once()
        assert self.backend._table_exists is True

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_ensure_table_exists_table_exists(self, mock_check_table):
        """Test _ensure_table_exists when table already exists."""
        mock_check_table.return_value = True

        self.backend._ensure_table_exists()

        assert self.backend._table_exists is True

    def test_ensure_table_exists_cached(self):
        """Test _ensure_table_exists uses cached result."""
        self.backend._table_exists = True

        with patch.object(self.backend, "_check_table_exists") as mock_check:
            self.backend._ensure_table_exists()
            mock_check.assert_not_called()


class TestDynamoDBBackendTableManagement:
    """Test cases for DynamoDB table management operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backend = DynamoDBBackend(table_name="test-cache-table", region="us-east-1")

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_enable_ttl")
    def test_create_table_success(self, mock_enable_ttl, mock_client):
        """Test successful table creation."""
        mock_waiter = Mock()
        mock_client.get_waiter.return_value = mock_waiter

        self.backend._create_table()

        # Verify table creation call
        mock_client.create_table.assert_called_once()
        call_args = mock_client.create_table.call_args[1]

        assert call_args["TableName"] == "test-cache-table"
        assert call_args["BillingMode"] == "PAY_PER_REQUEST"
        assert len(call_args["KeySchema"]) == 1
        assert call_args["KeySchema"][0]["AttributeName"] == "cache_key"
        assert call_args["KeySchema"][0]["KeyType"] == "HASH"

        # Verify waiter was called
        mock_client.get_waiter.assert_called_once_with("table_exists")
        mock_waiter.wait.assert_called_once()

        # Verify TTL was enabled
        mock_enable_ttl.assert_called_once()

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_create_table_already_exists(self, mock_client):
        """Test table creation when table already exists."""
        mock_client.create_table.side_effect = ClientError(
            {"Error": {"Code": "ResourceInUseException"}}, "CreateTable"
        )

        # Should not raise error
        self.backend._create_table()

        mock_client.create_table.assert_called_once()

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_create_table_error(self, mock_client):
        """Test table creation with other error."""
        mock_client.create_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "CreateTable"
        )

        with pytest.raises(CacheBackendError) as exc_info:
            self.backend._create_table()

        assert "Failed to create DynamoDB table" in str(exc_info.value)

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_enable_ttl_success(self, mock_client):
        """Test successful TTL enablement."""
        self.backend._enable_ttl()

        mock_client.update_time_to_live.assert_called_once_with(
            TableName="test-cache-table",
            TimeToLiveSpecification={"AttributeName": "ttl", "Enabled": True},
        )

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_enable_ttl_already_enabled(self, mock_client):
        """Test TTL enablement when already enabled."""
        mock_client.update_time_to_live.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "already enabled"}},
            "UpdateTimeToLive",
        )

        # Should not raise error
        self.backend._enable_ttl()

        mock_client.update_time_to_live.assert_called_once()

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_is_ttl_enabled_true(self, mock_client):
        """Test TTL status check when enabled."""
        mock_client.describe_time_to_live.return_value = {
            "TimeToLiveDescription": {"TimeToLiveStatus": "ENABLED"}
        }

        result = self.backend._is_ttl_enabled()

        assert result is True
        mock_client.describe_time_to_live.assert_called_once_with(TableName="test-cache-table")

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_is_ttl_enabled_false(self, mock_client):
        """Test TTL status check when disabled."""
        mock_client.describe_time_to_live.return_value = {
            "TimeToLiveDescription": {"TimeToLiveStatus": "DISABLED"}
        }

        result = self.backend._is_ttl_enabled()

        assert result is False

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_is_ttl_enabled_error(self, mock_client):
        """Test TTL status check with error."""
        mock_client.describe_time_to_live.side_effect = Exception("API error")

        result = self.backend._is_ttl_enabled()

        assert result is False

    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_invalidate_all_entries(self, mock_table):
        """Test invalidating all cache entries."""
        # Mock scan responses
        mock_table.scan.side_effect = [
            {
                "Items": [{"cache_key": "key1"}, {"cache_key": "key2"}],
                "LastEvaluatedKey": {"cache_key": "key2"},
            },
            {"Items": [{"cache_key": "key3"}]},
        ]

        # Mock batch writer context manager
        mock_batch = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_batch)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_table.batch_writer.return_value = mock_context_manager

        self.backend._invalidate_all_entries()

        # Verify scan calls
        assert mock_table.scan.call_count == 2

        # Verify batch delete calls
        assert mock_batch.delete_item.call_count == 3
        mock_batch.delete_item.assert_any_call(Key={"cache_key": "key1"})
        mock_batch.delete_item.assert_any_call(Key={"cache_key": "key2"})
        mock_batch.delete_item.assert_any_call(Key={"cache_key": "key3"})

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_is_ttl_enabled")
    def test_validate_table_schema_valid(self, mock_is_ttl_enabled, mock_client, mock_check_table):
        """Test table schema validation for valid table."""
        mock_check_table.return_value = True
        mock_is_ttl_enabled.return_value = True

        mock_client.describe_table.return_value = {
            "Table": {
                "TableStatus": "ACTIVE",
                "KeySchema": [{"AttributeName": "cache_key", "KeyType": "HASH"}],
                "AttributeDefinitions": [{"AttributeName": "cache_key", "AttributeType": "S"}],
                "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
            }
        }

        result = self.backend.validate_table_schema()

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_validate_table_schema_table_not_exists(self, mock_check_table):
        """Test table schema validation when table doesn't exist."""
        mock_check_table.return_value = False

        result = self.backend.validate_table_schema()

        assert result["valid"] is False
        assert "Table does not exist" in result["errors"]

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_is_ttl_enabled")
    def test_validate_table_schema_invalid_key_schema(
        self, mock_is_ttl_enabled, mock_client, mock_check_table
    ):
        """Test table schema validation with invalid key schema."""
        mock_check_table.return_value = True
        mock_is_ttl_enabled.return_value = True

        mock_client.describe_table.return_value = {
            "Table": {
                "TableStatus": "ACTIVE",
                "KeySchema": [{"AttributeName": "wrong_key", "KeyType": "HASH"}],
                "AttributeDefinitions": [{"AttributeName": "wrong_key", "AttributeType": "S"}],
                "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
            }
        }

        result = self.backend.validate_table_schema()

        assert result["valid"] is False
        assert any(
            "Key schema should have 'cache_key' as HASH key" in error for error in result["errors"]
        )

    @patch.object(DynamoDBBackend, "_check_table_exists")
    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_get_table_info_exists(self, mock_client, mock_check_table):
        """Test get_table_info when table exists."""
        mock_check_table.return_value = True

        mock_client.describe_table.return_value = {
            "Table": {
                "TableStatus": "ACTIVE",
                "CreationDateTime": "2023-01-01T00:00:00Z",
                "ItemCount": 100,
                "TableSizeBytes": 1024,
                "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
                "KeySchema": [{"AttributeName": "cache_key", "KeyType": "HASH"}],
                "AttributeDefinitions": [{"AttributeName": "cache_key", "AttributeType": "S"}],
            }
        }

        mock_client.describe_time_to_live.return_value = {
            "TimeToLiveDescription": {"TimeToLiveStatus": "ENABLED", "AttributeName": "ttl"}
        }

        result = self.backend.get_table_info()

        assert result["exists"] is True
        assert result["table_name"] == "test-cache-table"
        assert result["table_status"] == "ACTIVE"
        assert result["item_count"] == 100
        assert result["ttl_status"] == "ENABLED"

    @patch.object(DynamoDBBackend, "_check_table_exists")
    def test_get_table_info_not_exists(self, mock_check_table):
        """Test get_table_info when table doesn't exist."""
        mock_check_table.return_value = False

        result = self.backend.get_table_info()

        assert result["exists"] is False
        assert result["table_name"] == "test-cache-table"

    @patch.object(DynamoDBBackend, "validate_table_schema")
    @patch.object(DynamoDBBackend, "_create_table")
    @patch.object(DynamoDBBackend, "_enable_ttl")
    def test_repair_table_create_missing(self, mock_enable_ttl, mock_create_table, mock_validate):
        """Test repair_table when table is missing."""
        # First validation shows table doesn't exist
        mock_validate.side_effect = [
            {"valid": False, "errors": ["Table does not exist"], "warnings": []},
            {"valid": True, "errors": [], "warnings": []},
        ]

        result = self.backend.repair_table()

        assert result["success"] is True
        assert "Created missing table" in result["actions_taken"]
        mock_create_table.assert_called_once()

    @patch.object(DynamoDBBackend, "validate_table_schema")
    @patch.object(DynamoDBBackend, "_enable_ttl")
    def test_repair_table_enable_ttl(self, mock_enable_ttl, mock_validate):
        """Test repair_table when TTL needs to be enabled."""
        # First validation shows TTL not enabled
        mock_validate.side_effect = [
            {"valid": False, "errors": [], "warnings": ["TTL is not enabled on the table"]},
            {"valid": True, "errors": [], "warnings": []},
        ]

        result = self.backend.repair_table()

        assert result["success"] is True
        assert "Enabled TTL on table" in result["actions_taken"]
        mock_enable_ttl.assert_called_once()

    @patch.object(DynamoDBBackend, "validate_table_schema")
    def test_repair_table_already_valid(self, mock_validate):
        """Test repair_table when table is already valid."""
        mock_validate.return_value = {"valid": True, "errors": [], "warnings": []}

        result = self.backend.repair_table()

        assert result["success"] is True
        assert "Table is already valid" in result["actions_taken"]
