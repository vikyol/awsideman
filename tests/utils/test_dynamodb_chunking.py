"""Tests for DynamoDB backend chunking functionality."""

import base64
import gzip
from unittest.mock import Mock, patch

import pytest

from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.cache.backends.dynamodb import (
    CHUNK_SIZE,
    COMPRESSION_THRESHOLD,
    MAX_ITEM_SIZE,
    DynamoDBBackend,
)


class TestDynamoDBChunking:
    """Test cases for DynamoDB chunking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backend = DynamoDBBackend(table_name="test-cache-table", region="us-east-1")

    def test_compress_data_if_needed_small_data(self):
        """Test compression is not applied to small data."""
        small_data = b"small data"
        result = self.backend._compress_data_if_needed(small_data)
        assert result == small_data

    def test_compress_data_if_needed_large_data(self):
        """Test compression is applied to large data."""
        # Create data larger than compression threshold
        large_data = b"x" * (COMPRESSION_THRESHOLD + 100)
        result = self.backend._compress_data_if_needed(large_data)

        # Result should be compressed (and smaller)
        assert result != large_data
        assert len(result) < len(large_data)

        # Verify it can be decompressed
        decompressed = gzip.decompress(result)
        assert decompressed == large_data

    def test_compress_data_if_needed_incompressible_data(self):
        """Test compression is not used if it doesn't reduce size."""
        # Create random-like data that doesn't compress well
        import os

        random_data = os.urandom(COMPRESSION_THRESHOLD + 100)

        with patch("gzip.compress") as mock_compress:
            # Mock compression to return larger data
            mock_compress.return_value = random_data + b"extra"

            result = self.backend._compress_data_if_needed(random_data)
            assert result == random_data  # Should return original data

    def test_decompress_data_if_needed_compressed(self):
        """Test decompression of compressed data."""
        original_data = b"test data to compress"
        compressed_data = gzip.compress(original_data)

        result = self.backend._decompress_data_if_needed(compressed_data, True)
        assert result == original_data

    def test_decompress_data_if_needed_not_compressed(self):
        """Test handling of non-compressed data."""
        original_data = b"test data"
        result = self.backend._decompress_data_if_needed(original_data, False)
        assert result == original_data

    def test_decompress_data_if_needed_error(self):
        """Test error handling during decompression."""
        invalid_data = b"not compressed data"

        with pytest.raises(CacheBackendError) as exc_info:
            self.backend._decompress_data_if_needed(invalid_data, True)

        assert "Failed to decompress cache data" in str(exc_info.value)

    def test_decode_item_data_simple(self):
        """Test decoding simple item data."""
        test_data = b"test cache data"
        encoded_data = base64.b64encode(test_data).decode("utf-8")

        item = {"data": encoded_data, "is_compressed": False}

        result = self.backend._decode_item_data(item)
        assert result == test_data

    def test_decode_item_data_compressed(self):
        """Test decoding compressed item data."""
        test_data = b"test cache data"
        compressed_data = gzip.compress(test_data)
        encoded_data = base64.b64encode(compressed_data).decode("utf-8")

        item = {"data": encoded_data, "is_compressed": True}

        result = self.backend._decode_item_data(item)
        assert result == test_data

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "_compress_data_if_needed")
    @patch.object(DynamoDBBackend, "_put_item_with_retry")
    def test_set_small_data(self, mock_put_item, mock_compress, mock_ensure_table):
        """Test storing small data that doesn't need chunking."""
        test_data = b"small test data"
        mock_compress.return_value = test_data

        self.backend.set("test-key", test_data, ttl=3600, operation="test-op")

        mock_ensure_table.assert_called_once()
        mock_compress.assert_called_once_with(test_data)
        mock_put_item.assert_called_once()

        # Verify the item structure
        call_args = mock_put_item.call_args[0][0]
        assert call_args["cache_key"] == "test-key"
        assert base64.b64decode(call_args["data"]) == test_data
        assert call_args["operation"] == "test-op"
        assert call_args["is_compressed"] is False
        assert call_args["original_size"] == len(test_data)
        assert "ttl" in call_args

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "_compress_data_if_needed")
    @patch.object(DynamoDBBackend, "_set_chunked_data")
    def test_set_large_data(self, mock_set_chunked, mock_compress, mock_ensure_table):
        """Test storing large data that needs chunking."""
        # Create data larger than MAX_ITEM_SIZE
        large_data = b"x" * (MAX_ITEM_SIZE + 1000)
        mock_compress.return_value = large_data

        self.backend.set("test-key", large_data, ttl=3600, operation="test-op")

        mock_ensure_table.assert_called_once()
        mock_compress.assert_called_once_with(large_data)
        mock_set_chunked.assert_called_once_with("test-key", large_data, 3600, "test-op")

    @patch.object(DynamoDBBackend, "_store_chunks_batch")
    @patch("uuid.uuid4")
    def test_set_chunked_data(self, mock_uuid, mock_store_chunks):
        """Test chunking large data."""
        mock_uuid.return_value.return_value = "test-chunk-id"

        # Create data that will be split into multiple chunks
        large_data = b"x" * (CHUNK_SIZE * 2 + 100)

        self.backend._set_chunked_data("test-key", large_data, 3600, "test-op")

        mock_store_chunks.assert_called_once()

        # Verify the call arguments
        chunks, metadata = mock_store_chunks.call_args[0]

        # Check metadata
        assert metadata["cache_key"] == "test-key"
        assert metadata["operation"] == "test-op"
        assert metadata["is_chunked"] is True
        assert metadata["chunk_count"] == 3  # Should be 3 chunks
        assert metadata["original_size"] == len(large_data)
        assert "ttl" in metadata

        # Check chunks
        assert len(chunks) == 3
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i
            assert "chunk_data" in chunk
            assert "ttl" in chunk

    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_store_chunks_batch(self, mock_table):
        """Test storing chunks in batch."""
        chunks = [
            {"chunk_key": "key#chunk#id#0", "chunk_index": 0, "chunk_data": "data0"},
            {"chunk_key": "key#chunk#id#1", "chunk_index": 1, "chunk_data": "data1"},
        ]

        metadata = {"cache_key": "test-key", "chunk_id": "test-id", "chunk_count": 2}

        # Mock batch writer context manager
        mock_batch = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_batch)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_table.batch_writer.return_value = mock_context_manager

        self.backend._store_chunks_batch(chunks, metadata)

        # Verify batch operations
        assert mock_batch.put_item.call_count == 3  # 1 metadata + 2 chunks

    @patch.object(DynamoDBBackend, "client", new_callable=lambda: Mock())
    def test_get_chunks_batch(self, mock_client):
        """Test retrieving chunks in batch."""
        # Mock batch_get_item response
        mock_client.batch_get_item.return_value = {
            "Responses": {
                "test-cache-table": [
                    {"chunk_index": 0, "data": "chunk0data"},
                    {"chunk_index": 1, "data": "chunk1data"},
                ]
            },
            "UnprocessedKeys": {},
        }

        result = self.backend._get_chunks_batch("test-key", "chunk-id", 2)

        assert len(result) == 2
        assert result[0]["chunk_index"] == 0
        assert result[0]["chunk_data"] == "chunk0data"
        assert result[1]["chunk_index"] == 1
        assert result[1]["chunk_data"] == "chunk1data"

    @patch.object(DynamoDBBackend, "_get_chunks_batch")
    @patch.object(DynamoDBBackend, "_decompress_data_if_needed")
    def test_get_chunked_data(self, mock_decompress, mock_get_chunks):
        """Test retrieving and reassembling chunked data."""
        # Mock chunks (out of order to test sorting)
        mock_get_chunks.return_value = [
            {"chunk_index": 1, "chunk_data": base64.b64encode(b"chunk1").decode()},
            {"chunk_index": 0, "chunk_data": base64.b64encode(b"chunk0").decode()},
            {"chunk_index": 2, "chunk_data": base64.b64encode(b"chunk2").decode()},
        ]

        mock_decompress.return_value = b"chunk0chunk1chunk2"

        metadata = {"chunk_id": "test-id", "chunk_count": 3, "is_compressed": True}

        result = self.backend._get_chunked_data("test-key", metadata)

        assert result == b"chunk0chunk1chunk2"
        mock_get_chunks.assert_called_once_with("test-key", "test-id", 3)
        mock_decompress.assert_called_once_with(b"chunk0chunk1chunk2", True)

    @patch.object(DynamoDBBackend, "_get_chunks_batch")
    def test_get_chunked_data_missing_chunks(self, mock_get_chunks):
        """Test handling missing chunks."""
        # Return fewer chunks than expected
        mock_get_chunks.return_value = [
            {"chunk_index": 0, "chunk_data": base64.b64encode(b"chunk0").decode()}
        ]

        metadata = {"chunk_id": "test-id", "chunk_count": 3, "is_compressed": False}

        result = self.backend._get_chunked_data("test-key", metadata)

        assert result is None  # Should return None for missing chunks

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_get_chunked_data")
    def test_get_chunked_entry(self, mock_get_chunked, mock_table, mock_ensure_table):
        """Test getting a chunked cache entry."""
        # Mock table response for chunked item
        mock_table.get_item.return_value = {
            "Item": {
                "cache_key": "test-key",
                "is_chunked": True,
                "chunk_id": "test-id",
                "chunk_count": 2,
            }
        }

        mock_get_chunked.return_value = b"reassembled data"

        result = self.backend.get("test-key")

        assert result == b"reassembled data"
        mock_get_chunked.assert_called_once()

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_decode_item_data")
    def test_get_single_entry(self, mock_decode, mock_table, mock_ensure_table):
        """Test getting a single (non-chunked) cache entry."""
        # Mock table response for single item
        mock_table.get_item.return_value = {
            "Item": {"cache_key": "test-key", "data": "encoded-data", "is_chunked": False}
        }

        mock_decode.return_value = b"decoded data"

        result = self.backend.get("test-key")

        assert result == b"decoded data"
        mock_decode.assert_called_once()

    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_cleanup_chunks(self, mock_table):
        """Test cleanup of chunks."""
        # Mock scan response
        mock_table.scan.return_value = {
            "Items": [{"cache_key": "key#chunk#id#0"}, {"cache_key": "key#chunk#id#1"}]
        }

        # Mock batch writer context manager
        mock_batch = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_batch)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_table.batch_writer.return_value = mock_context_manager

        self.backend._cleanup_chunks("test-key", "test-id")

        # Verify scan was called
        mock_table.scan.assert_called_once()

        # Verify batch delete was called
        assert mock_batch.delete_item.call_count == 2

    @patch.object(DynamoDBBackend, "_ensure_table_exists")
    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    @patch.object(DynamoDBBackend, "_cleanup_chunks")
    def test_invalidate_chunked_entry(self, mock_cleanup, mock_table, mock_ensure_table):
        """Test invalidating a chunked cache entry."""
        # Mock table response for chunked item
        mock_table.get_item.return_value = {
            "Item": {"cache_key": "test-key", "is_chunked": True, "chunk_id": "test-id"}
        }

        self.backend.invalidate("test-key")

        mock_cleanup.assert_called_once_with("test-key", "test-id")
        mock_table.delete_item.assert_called_once_with(Key={"cache_key": "test-key"})

    @patch.object(DynamoDBBackend, "table", new_callable=lambda: Mock())
    def test_cleanup_orphaned_chunks(self, mock_table):
        """Test cleanup of orphaned chunks."""
        # Mock scan response for chunks
        mock_table.scan.return_value = {
            "Items": [
                {"cache_key": "key1#chunk#id1#0", "parent_key": "key1", "chunk_id": "id1"},
                {"cache_key": "key2#chunk#id2#0", "parent_key": "key2", "chunk_id": "id2"},
            ]
        }

        # Mock get_item responses - key1 exists, key2 doesn't
        def mock_get_item(Key):
            if Key["cache_key"] == "key1":
                return {"Item": {"is_chunked": True}}
            else:
                return {}  # key2 doesn't exist

        mock_table.get_item.side_effect = mock_get_item

        # Mock batch writer context manager
        mock_batch = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_batch)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_table.batch_writer.return_value = mock_context_manager

        result = self.backend.cleanup_orphaned_chunks()

        assert result["success"] is True
        assert result["chunks_found"] == 2
        assert result["chunks_deleted"] == 1  # Only key2's chunk should be deleted

        # Verify only orphaned chunk was deleted
        mock_batch.delete_item.assert_called_once_with(Key={"cache_key": "key2#chunk#id2#0"})
