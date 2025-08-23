"""DynamoDB backend implementation for advanced cache features."""

import base64
import gzip
import time
import uuid
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from ...utils.security import get_secure_logger, input_validator
from .base import CacheBackend, CacheBackendError

# Use secure logger instead of standard logger
logger = get_secure_logger(__name__)

# DynamoDB item size limit is 400KB, we use a smaller chunk size for safety
MAX_ITEM_SIZE = 350 * 1024  # 350KB to leave room for metadata
COMPRESSION_THRESHOLD = 1024  # Compress items larger than 1KB
CHUNK_SIZE = MAX_ITEM_SIZE - 1024  # Leave room for metadata in each chunk


class DynamoDBBackend(CacheBackend):
    """
    DynamoDB backend implementation for cache storage.

    Provides distributed cache storage using AWS DynamoDB with support for
    TTL-based expiration, automatic table creation, and proper error handling.
    """

    def __init__(
        self, table_name: str, region: Optional[str] = None, profile: Optional[str] = None
    ):
        """
        Initialize DynamoDB backend.

        Args:
            table_name: Name of the DynamoDB table to use
            region: AWS region for DynamoDB table
            profile: AWS profile to use for authentication
        """
        self.table_name = table_name
        self.region = region
        self.profile = profile
        self._client = None
        self._table = None
        self._table_exists = None  # Cache table existence check

        logger.debug(
            f"Initialized DynamoDB backend: table={table_name}, region={region}, profile={profile}"
        )

    @property
    def client(self):
        """Get DynamoDB client, creating it if needed."""
        if self._client is None:
            try:
                session_kwargs = {}
                if self.profile:
                    session_kwargs["profile_name"] = self.profile
                elif not self.profile:
                    # Auto-configure profile if none specified
                    try:
                        from ...utils.config import Config

                        config = Config()
                        default_profile = config.get("default_profile")
                        if default_profile:
                            session_kwargs["profile_name"] = default_profile
                            logger.debug(
                                f"Auto-configured DynamoDB client to use default profile: {default_profile}"
                            )
                    except Exception as e:
                        logger.debug(f"Could not auto-configure default profile: {e}")

                if self.region:
                    session_kwargs["region_name"] = self.region

                session = boto3.Session(**session_kwargs)
                self._client = session.client("dynamodb")
                logger.debug("Created DynamoDB client")
            except Exception as e:
                raise CacheBackendError(
                    f"Failed to create DynamoDB client: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        return self._client

    @property
    def table(self):
        """Get DynamoDB table resource, creating it if needed."""
        if self._table is None:
            try:
                session_kwargs = {}
                if self.profile:
                    session_kwargs["profile_name"] = self.profile
                elif not self.profile:
                    # Auto-configure profile if none specified
                    try:
                        from ...utils.config import Config

                        config = Config()
                        default_profile = config.get("default_profile")
                        if default_profile:
                            session_kwargs["profile_name"] = default_profile
                            logger.debug(
                                f"Auto-configured DynamoDB table resource to use default profile: {default_profile}"
                            )
                    except Exception as e:
                        logger.debug(f"Could not auto-configure default profile: {e}")

                if self.region:
                    session_kwargs["region_name"] = self.region

                session = boto3.Session(**session_kwargs)
                dynamodb = session.resource("dynamodb")
                self._table = dynamodb.Table(self.table_name)
                logger.debug(f"Created DynamoDB table resource: {self.table_name}")
            except Exception as e:
                raise CacheBackendError(
                    f"Failed to create DynamoDB table resource: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        return self._table

    def get(self, key: str) -> Optional[bytes]:
        """
        Retrieve raw data from DynamoDB with input validation.

        Args:
            key: Cache key to retrieve

        Returns:
            Raw bytes data if found and not expired, None otherwise

        Raises:
            CacheBackendError: If DynamoDB operation fails
        """
        try:
            # Validate cache key
            if not input_validator.validate_cache_key(key):
                logger.security_event(
                    "invalid_cache_key",
                    {
                        "operation": "get",
                        "key": input_validator.sanitize_log_data(key),
                        "backend": "dynamodb",
                    },
                    "WARNING",
                )
                raise CacheBackendError(f"Invalid cache key format: {key}")

            # Ensure table exists before attempting operations
            self._ensure_table_exists()

            response = self.table.get_item(Key={"cache_key": key})

            if "Item" not in response:
                logger.debug(f"Cache miss for key: {key}")
                return None

            item = response["Item"]

            # Check TTL expiration
            if "ttl" in item:
                current_time = int(time.time())
                if item["ttl"] < current_time:
                    logger.debug(f"Cache entry expired for key: {key}")
                    return None

            # Check if this is a chunked item
            if item.get("is_chunked", False):
                return self._get_chunked_data(key, item)
            else:
                # Handle single item
                return self._decode_item_data(item)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ResourceNotFoundException":
                logger.warning(f"DynamoDB table {self.table_name} not found")
                return None
            elif error_code in ["ProvisionedThroughputExceededException", "RequestLimitExceeded"]:
                logger.warning(f"DynamoDB throttling for get operation on key {key}")
                return None
            else:
                raise CacheBackendError(
                    f"DynamoDB get operation failed for key {key}: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        except Exception as e:
            raise CacheBackendError(
                f"Unexpected error during DynamoDB get operation for key {key}: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def set(
        self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"
    ) -> None:
        """
        Store raw data to DynamoDB with input validation.

        Args:
            key: Cache key to store data under
            data: Raw bytes data to store
            ttl: Optional TTL in seconds
            operation: AWS operation that generated this data

        Raises:
            CacheBackendError: If DynamoDB operation fails
        """
        try:
            # Validate cache key
            if not input_validator.validate_cache_key(key):
                logger.security_event(
                    "invalid_cache_key",
                    {
                        "operation": "set",
                        "key": input_validator.sanitize_log_data(key),
                        "backend": "dynamodb",
                    },
                    "WARNING",
                )
                raise CacheBackendError(f"Invalid cache key format: {key}")

            # Validate data
            if not isinstance(data, bytes):
                raise CacheBackendError("Data must be bytes")

            # Validate TTL
            if ttl is not None and (not isinstance(ttl, int) or ttl <= 0):
                raise CacheBackendError("TTL must be a positive integer")

            # Ensure table exists before attempting operations
            self._ensure_table_exists()

            # Check if data needs to be compressed
            compressed_data = self._compress_data_if_needed(data)

            # Check if data needs to be chunked
            if len(compressed_data) > MAX_ITEM_SIZE:
                self._set_chunked_data(key, compressed_data, ttl, operation)
            else:
                # Store as single item
                item = {
                    "cache_key": key,
                    "data": base64.b64encode(compressed_data).decode("utf-8"),
                    "operation": operation,
                    "created_at": int(time.time()),
                    "is_compressed": len(compressed_data) != len(data),
                    "original_size": len(data),
                }

                # Add TTL if specified
                if ttl and ttl > 0:
                    item["ttl"] = int(time.time() + ttl)

                # Store item in DynamoDB
                self._put_item_with_retry(item)

            logger.debug(f"Stored cache entry for key: {key}")

        except Exception as e:
            if isinstance(e, CacheBackendError):
                raise
            else:
                raise CacheBackendError(
                    f"Unexpected error during DynamoDB set operation for key {key}: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )

    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Remove cache entries from DynamoDB.

        Args:
            key: Cache key to invalidate. If None, invalidates all cache entries.

        Raises:
            CacheBackendError: If DynamoDB operation fails
        """
        try:
            # Ensure table exists before attempting operations
            self._ensure_table_exists()

            if key is None:
                # Invalidate all entries by scanning and deleting
                self._invalidate_all_entries()
            else:
                # Check if this is a chunked entry
                response = self.table.get_item(Key={"cache_key": key})
                if "Item" in response:
                    item = response["Item"]
                    if item.get("is_chunked", False):
                        # Delete chunks first
                        chunk_id = item.get("chunk_id")
                        if chunk_id:
                            self._cleanup_chunks(key, chunk_id)

                # Delete the main entry
                self.table.delete_item(Key={"cache_key": key})
                logger.debug(f"Invalidated cache entry for key: {key}")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ResourceNotFoundException":
                logger.debug(f"Table {self.table_name} not found during invalidation")
                # Table doesn't exist, so nothing to invalidate
                return
            elif error_code in ["ProvisionedThroughputExceededException", "RequestLimitExceeded"]:
                logger.warning("DynamoDB throttling during invalidation")
                # Don't raise error for throttling during invalidation
            else:
                raise CacheBackendError(
                    f"DynamoDB invalidate operation failed: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        except Exception as e:
            raise CacheBackendError(
                f"Unexpected error during DynamoDB invalidate operation: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get DynamoDB backend statistics.

        Returns:
            Dictionary containing backend statistics and metadata

        Raises:
            CacheBackendError: If DynamoDB operation fails
        """
        try:
            stats = {
                "backend_type": "dynamodb",
                "table_name": self.table_name,
                "region": self.region,
                "profile": self.profile,
                "table_exists": False,
                "item_count": 0,
                "table_size_bytes": 0,
                "table_status": "UNKNOWN",
            }

            # Check if table exists and get basic info
            if self._check_table_exists():
                stats["table_exists"] = True

                # Get table description
                table_description = self.client.describe_table(TableName=self.table_name)
                table_info = table_description["Table"]

                # Get real-time item count using scan (ItemCount from describe_table is not real-time)
                try:
                    scan_response = self.client.scan(TableName=self.table_name, Select="COUNT")
                    real_time_item_count = scan_response.get("Count", 0)
                    logger.debug(f"Real-time item count: {real_time_item_count}")
                except Exception as e:
                    logger.warning(
                        f"Failed to get real-time item count, using describe_table value: {e}"
                    )
                    real_time_item_count = table_info.get("ItemCount", 0)

                stats.update(
                    {
                        "table_status": table_info.get("TableStatus", "UNKNOWN"),
                        "item_count": real_time_item_count,
                        "table_size_bytes": table_info.get("TableSizeBytes", 0),
                        "creation_date": table_info.get("CreationDateTime"),
                        "billing_mode": table_info.get("BillingModeSummary", {}).get(
                            "BillingMode", "UNKNOWN"
                        ),
                        "ttl_enabled": self._is_ttl_enabled(),
                        "chunking_enabled": True,
                        "compression_enabled": True,
                        "max_item_size": MAX_ITEM_SIZE,
                        "chunk_size": CHUNK_SIZE,
                    }
                )

            return stats

        except ClientError as e:
            # Return partial stats with error information
            return {
                "backend_type": "dynamodb",
                "table_name": self.table_name,
                "region": self.region,
                "profile": self.profile,
                "error": str(e),
                "table_exists": False,
            }
        except Exception as e:
            raise CacheBackendError(
                f"Failed to get DynamoDB backend statistics: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def health_check(self) -> bool:
        """
        Check if DynamoDB backend is healthy and accessible.

        Returns:
            True if backend is healthy, False otherwise
        """
        try:
            # Try to describe the table or list tables to check connectivity
            if self._check_table_exists():
                # Table exists, try a simple operation
                self.client.describe_table(TableName=self.table_name)
                return True
            else:
                # Table doesn't exist, but we can connect to DynamoDB
                self.client.list_tables(Limit=1)
                return True

        except NoCredentialsError:
            logger.error("DynamoDB health check failed: No AWS credentials available")
            return False
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ["AccessDenied", "UnauthorizedOperation"]:
                logger.error(f"DynamoDB health check failed: Access denied - {e}")
                return False
            else:
                logger.error(f"DynamoDB health check failed: {e}")
                return False
        except Exception as e:
            logger.error(f"DynamoDB health check failed with unexpected error: {e}")
            return False

    def _ensure_table_exists(self) -> None:
        """
        Ensure the DynamoDB table exists, creating it if necessary.

        Raises:
            CacheBackendError: If table creation fails
        """
        if self._table_exists is None:
            self._table_exists = self._check_table_exists()

        if not self._table_exists:
            logger.info(f"Creating DynamoDB table: {self.table_name}")
            self._create_table()
            self._table_exists = True

    def _check_table_exists(self) -> bool:
        """
        Check if the DynamoDB table exists.

        Returns:
            True if table exists, False otherwise
        """
        try:
            self.client.describe_table(TableName=self.table_name)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return False
            else:
                # Other errors indicate connectivity issues
                raise CacheBackendError(
                    f"Failed to check if table exists: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )

    def _create_table(self) -> None:
        """
        Create the DynamoDB table with proper configuration.

        Raises:
            CacheBackendError: If table creation fails
        """
        try:
            # Create table with pay-per-request billing and TTL enabled
            table_definition = {
                "TableName": self.table_name,
                "KeySchema": [{"AttributeName": "cache_key", "KeyType": "HASH"}],
                "AttributeDefinitions": [{"AttributeName": "cache_key", "AttributeType": "S"}],
                "BillingMode": "PAY_PER_REQUEST",
            }

            # Create the table
            self.client.create_table(**table_definition)
            logger.info(f"Created DynamoDB table: {self.table_name}")

            # Wait for table to become active
            waiter = self.client.get_waiter("table_exists")
            waiter.wait(TableName=self.table_name, WaiterConfig={"Delay": 2, "MaxAttempts": 30})

            # Enable TTL on the table
            self._enable_ttl()

            logger.info(f"DynamoDB table {self.table_name} is ready")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ResourceInUseException":
                # Table already exists (race condition), that's fine
                logger.debug(f"Table {self.table_name} already exists")
                return
            else:
                raise CacheBackendError(
                    f"Failed to create DynamoDB table {self.table_name}: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        except Exception as e:
            raise CacheBackendError(
                f"Unexpected error creating DynamoDB table {self.table_name}: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def _enable_ttl(self) -> None:
        """
        Enable TTL on the DynamoDB table.

        Raises:
            CacheBackendError: If TTL configuration fails
        """
        try:
            self.client.update_time_to_live(
                TableName=self.table_name,
                TimeToLiveSpecification={"AttributeName": "ttl", "Enabled": True},
            )
            logger.debug(f"Enabled TTL on table {self.table_name}")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ValidationException" and "already enabled" in str(e):
                # TTL already enabled, that's fine
                logger.debug(f"TTL already enabled on table {self.table_name}")
                return
            else:
                # Log warning but don't fail - TTL is not critical
                logger.warning(f"Failed to enable TTL on table {self.table_name}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error enabling TTL on table {self.table_name}: {e}")

    def _is_ttl_enabled(self) -> bool:
        """
        Check if TTL is enabled on the table.

        Returns:
            True if TTL is enabled, False otherwise
        """
        try:
            response = self.client.describe_time_to_live(TableName=self.table_name)
            ttl_description = response.get("TimeToLiveDescription", {})
            return ttl_description.get("TimeToLiveStatus") == "ENABLED"
        except Exception as e:
            logger.debug(f"Could not check TTL status for table {self.table_name}: {e}")
            return False

    def validate_table_schema(self) -> Dict[str, Any]:
        """
        Validate that the DynamoDB table has the correct schema.

        Returns:
            Dictionary with validation results
        """
        validation_result = {"valid": False, "errors": [], "warnings": [], "table_info": {}}

        try:
            if not self._check_table_exists():
                validation_result["errors"].append("Table does not exist")
                return validation_result

            # Get table description
            table_description = self.client.describe_table(TableName=self.table_name)
            table_info = table_description["Table"]
            validation_result["table_info"] = table_info

            # Validate key schema
            key_schema = table_info.get("KeySchema", [])
            if len(key_schema) != 1:
                validation_result["errors"].append(
                    f"Expected 1 key attribute, found {len(key_schema)}"
                )
            elif (
                key_schema[0].get("AttributeName") != "cache_key"
                or key_schema[0].get("KeyType") != "HASH"
            ):
                validation_result["errors"].append("Key schema should have 'cache_key' as HASH key")

            # Validate attribute definitions
            attributes = table_info.get("AttributeDefinitions", [])
            cache_key_attr = next(
                (attr for attr in attributes if attr["AttributeName"] == "cache_key"), None
            )
            if not cache_key_attr:
                validation_result["errors"].append("Missing 'cache_key' attribute definition")
            elif cache_key_attr.get("AttributeType") != "S":
                validation_result["errors"].append("'cache_key' should be of type String (S)")

            # Check table status
            table_status = table_info.get("TableStatus", "UNKNOWN")
            if table_status != "ACTIVE":
                validation_result["warnings"].append(
                    f"Table status is {table_status}, expected ACTIVE"
                )

            # Check billing mode
            billing_mode = table_info.get("BillingModeSummary", {}).get("BillingMode", "UNKNOWN")
            if billing_mode not in ["PAY_PER_REQUEST", "PROVISIONED"]:
                validation_result["warnings"].append(f"Unexpected billing mode: {billing_mode}")

            # Check TTL configuration
            if not self._is_ttl_enabled():
                validation_result["warnings"].append("TTL is not enabled on the table")

            # If no errors, mark as valid
            if not validation_result["errors"]:
                validation_result["valid"] = True

            return validation_result

        except ClientError as e:
            validation_result["errors"].append(f"AWS API error: {e}")
            return validation_result
        except Exception as e:
            validation_result["errors"].append(f"Unexpected error: {e}")
            return validation_result

    def get_table_info(self) -> Dict[str, Any]:
        """
        Get comprehensive table information.

        Returns:
            Dictionary with table information
        """
        try:
            if not self._check_table_exists():
                return {
                    "exists": False,
                    "table_name": self.table_name,
                    "region": self.region,
                    "profile": self.profile,
                }

            # Get table description
            table_description = self.client.describe_table(TableName=self.table_name)
            table_info = table_description["Table"]

            # Get TTL information
            ttl_info = {}
            try:
                ttl_response = self.client.describe_time_to_live(TableName=self.table_name)
                ttl_info = ttl_response.get("TimeToLiveDescription", {})
            except Exception as e:
                logger.debug(f"Could not get TTL info: {e}")

            return {
                "exists": True,
                "table_name": self.table_name,
                "region": self.region,
                "profile": self.profile,
                "table_status": table_info.get("TableStatus"),
                "creation_date": table_info.get("CreationDateTime"),
                "item_count": table_info.get("ItemCount", 0),
                "table_size_bytes": table_info.get("TableSizeBytes", 0),
                "billing_mode": table_info.get("BillingModeSummary", {}).get("BillingMode"),
                "read_capacity": table_info.get("ProvisionedThroughput", {}).get(
                    "ReadCapacityUnits"
                ),
                "write_capacity": table_info.get("ProvisionedThroughput", {}).get(
                    "WriteCapacityUnits"
                ),
                "key_schema": table_info.get("KeySchema", []),
                "attribute_definitions": table_info.get("AttributeDefinitions", []),
                "ttl_status": ttl_info.get("TimeToLiveStatus"),
                "ttl_attribute": ttl_info.get("AttributeName"),
                "global_secondary_indexes": table_info.get("GlobalSecondaryIndexes", []),
                "local_secondary_indexes": table_info.get("LocalSecondaryIndexes", []),
                "stream_specification": table_info.get("StreamSpecification", {}),
                "sse_description": table_info.get("SSEDescription", {}),
            }

        except ClientError as e:
            return {
                "exists": False,
                "table_name": self.table_name,
                "region": self.region,
                "profile": self.profile,
                "error": str(e),
            }
        except Exception as e:
            return {
                "exists": False,
                "table_name": self.table_name,
                "region": self.region,
                "profile": self.profile,
                "error": f"Unexpected error: {e}",
            }

    def repair_table(self) -> Dict[str, Any]:
        """
        Attempt to repair table configuration issues.

        Returns:
            Dictionary with repair results
        """
        repair_result = {"success": False, "actions_taken": [], "errors": []}

        try:
            # First validate the table
            validation = self.validate_table_schema()

            if not validation["valid"]:
                # If table doesn't exist, create it
                if "Table does not exist" in validation["errors"]:
                    try:
                        self._create_table()
                        repair_result["actions_taken"].append("Created missing table")
                    except Exception as e:
                        repair_result["errors"].append(f"Failed to create table: {e}")
                        return repair_result

                # If TTL is not enabled, enable it
                if "TTL is not enabled on the table" in validation["warnings"]:
                    try:
                        self._enable_ttl()
                        repair_result["actions_taken"].append("Enabled TTL on table")
                    except Exception as e:
                        repair_result["errors"].append(f"Failed to enable TTL: {e}")

                # Re-validate after repairs
                validation = self.validate_table_schema()
                if validation["valid"]:
                    repair_result["success"] = True
                else:
                    repair_result["errors"].extend(validation["errors"])
            else:
                repair_result["success"] = True
                repair_result["actions_taken"].append("Table is already valid")

            return repair_result

        except Exception as e:
            repair_result["errors"].append(f"Unexpected error during repair: {e}")
            return repair_result

    def _compress_data_if_needed(self, data: bytes) -> bytes:
        """
        Compress data if it's larger than the compression threshold.

        Args:
            data: Raw bytes data to potentially compress

        Returns:
            Compressed or original data
        """
        if len(data) > COMPRESSION_THRESHOLD:
            try:
                compressed = gzip.compress(data)
                # Only use compression if it actually reduces size
                if len(compressed) < len(data):
                    logger.debug(f"Compressed data from {len(data)} to {len(compressed)} bytes")
                    return compressed
            except Exception as e:
                logger.warning(f"Failed to compress data: {e}")

        return data

    def _decompress_data_if_needed(self, data: bytes, is_compressed: bool) -> bytes:
        """
        Decompress data if it was compressed.

        Args:
            data: Potentially compressed bytes data
            is_compressed: Whether the data is compressed

        Returns:
            Decompressed or original data
        """
        if is_compressed:
            try:
                return gzip.decompress(data)
            except Exception as e:
                logger.error(f"Failed to decompress data: {e}")
                raise CacheBackendError(
                    f"Failed to decompress cache data: {e}",
                    backend_type="dynamodb",
                    original_error=e,
                )
        return data

    def _decode_item_data(self, item: Dict[str, Any]) -> bytes:
        """
        Decode and decompress item data.

        Args:
            item: DynamoDB item

        Returns:
            Decoded bytes data
        """
        try:
            # Decode base64 data
            data = base64.b64decode(item["data"])

            # Decompress if needed
            is_compressed = item.get("is_compressed", False)
            data = self._decompress_data_if_needed(data, is_compressed)

            return data
        except Exception as e:
            logger.error(f"Failed to decode item data: {e}")
            raise CacheBackendError(
                f"Failed to decode cache data: {e}", backend_type="dynamodb", original_error=e
            )

    def _set_chunked_data(self, key: str, data: bytes, ttl: Optional[int], operation: str) -> None:
        """
        Store large data as multiple chunks.

        Args:
            key: Cache key
            data: Data to chunk and store
            ttl: Optional TTL in seconds
            operation: AWS operation name
        """
        try:
            # Generate unique chunk ID to avoid conflicts
            chunk_id = str(uuid.uuid4())
            chunks = []

            # Split data into chunks
            for i in range(0, len(data), CHUNK_SIZE):
                chunk_data = data[i : i + CHUNK_SIZE]
                chunk_key = f"{key}#chunk#{chunk_id}#{i // CHUNK_SIZE}"
                chunks.append(
                    {
                        "chunk_key": chunk_key,
                        "chunk_index": i // CHUNK_SIZE,
                        "chunk_data": base64.b64encode(chunk_data).decode("utf-8"),
                    }
                )

            # Create metadata item
            metadata_item = {
                "cache_key": key,
                "operation": operation,
                "created_at": int(time.time()),
                "is_chunked": True,
                "chunk_id": chunk_id,
                "chunk_count": len(chunks),
                "original_size": len(data),
                "is_compressed": True,  # Data is already compressed at this point
            }

            # Add TTL if specified
            if ttl and ttl > 0:
                ttl_timestamp = int(time.time() + ttl)
                metadata_item["ttl"] = ttl_timestamp

                # Add TTL to all chunks
                for chunk in chunks:
                    chunk["ttl"] = ttl_timestamp

            # Store chunks and metadata using batch operations
            self._store_chunks_batch(chunks, metadata_item)

            logger.debug(f"Stored chunked cache entry for key: {key} ({len(chunks)} chunks)")

        except Exception as e:
            logger.error(f"Failed to store chunked data for key {key}: {e}")
            # Clean up any partially stored chunks
            try:
                self._cleanup_chunks(key, chunk_id)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup chunks after error: {cleanup_error}")

            raise CacheBackendError(
                f"Failed to store chunked data for key {key}: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def _get_chunked_data(self, key: str, metadata_item: Dict[str, Any]) -> Optional[bytes]:
        """
        Retrieve and reassemble chunked data.

        Args:
            key: Cache key
            metadata_item: Metadata item containing chunk information

        Returns:
            Reassembled bytes data or None if chunks are missing
        """
        try:
            chunk_id = metadata_item["chunk_id"]
            chunk_count = metadata_item["chunk_count"]
            is_compressed = metadata_item.get("is_compressed", False)

            # Retrieve all chunks
            chunks = self._get_chunks_batch(key, chunk_id, chunk_count)

            if len(chunks) != chunk_count:
                logger.warning(
                    f"Missing chunks for key {key}: expected {chunk_count}, got {len(chunks)}"
                )
                return None

            # Sort chunks by index and reassemble data
            chunks.sort(key=lambda x: x["chunk_index"])
            reassembled_data = b""

            for chunk in chunks:
                chunk_data = base64.b64decode(chunk["chunk_data"])
                reassembled_data += chunk_data

            # Decompress if needed
            data = self._decompress_data_if_needed(reassembled_data, is_compressed)

            logger.debug(f"Retrieved chunked cache entry for key: {key} ({len(chunks)} chunks)")
            return data

        except Exception as e:
            logger.error(f"Failed to retrieve chunked data for key {key}: {e}")
            return None

    def _store_chunks_batch(
        self, chunks: List[Dict[str, Any]], metadata_item: Dict[str, Any]
    ) -> None:
        """
        Store chunks and metadata using batch operations.

        Args:
            chunks: List of chunk items to store
            metadata_item: Metadata item to store
        """
        try:
            # Store chunks in batches of 25 (DynamoDB batch limit)
            batch_size = 25

            with self.table.batch_writer() as batch:
                # Store metadata first
                batch.put_item(Item=metadata_item)

                # Store chunks in batches
                for i in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[i : i + batch_size]
                    for chunk in batch_chunks:
                        chunk_item = {
                            "cache_key": chunk["chunk_key"],
                            "chunk_index": chunk["chunk_index"],
                            "data": chunk["chunk_data"],
                            "is_chunk": True,
                            "parent_key": metadata_item["cache_key"],
                            "chunk_id": metadata_item["chunk_id"],
                        }

                        # Add TTL if present in chunk
                        if "ttl" in chunk:
                            chunk_item["ttl"] = chunk["ttl"]

                        batch.put_item(Item=chunk_item)

        except Exception as e:
            raise CacheBackendError(
                f"Failed to store chunks in batch: {e}", backend_type="dynamodb", original_error=e
            )

    def _get_chunks_batch(self, key: str, chunk_id: str, chunk_count: int) -> List[Dict[str, Any]]:
        """
        Retrieve chunks using batch operations.

        Args:
            key: Original cache key
            chunk_id: Unique chunk identifier
            chunk_count: Expected number of chunks

        Returns:
            List of chunk items
        """
        try:
            chunks = []

            # Build list of chunk keys to retrieve
            chunk_keys = []
            for i in range(chunk_count):
                chunk_key = f"{key}#chunk#{chunk_id}#{i}"
                chunk_keys.append({"cache_key": chunk_key})

            # Retrieve chunks in batches of 100 (DynamoDB batch limit)
            batch_size = 100

            for i in range(0, len(chunk_keys), batch_size):
                batch_keys = chunk_keys[i : i + batch_size]

                response = self.client.batch_get_item(
                    RequestItems={self.table_name: {"Keys": batch_keys}}
                )

                # Process retrieved items
                items = response.get("Responses", {}).get(self.table_name, [])
                for item in items:
                    chunks.append({"chunk_index": item["chunk_index"], "chunk_data": item["data"]})

                # Handle unprocessed keys (retry logic could be added here)
                unprocessed = response.get("UnprocessedKeys", {})
                if unprocessed:
                    logger.warning(f"Some chunks were not retrieved for key {key}")

            return chunks

        except Exception as e:
            raise CacheBackendError(
                f"Failed to retrieve chunks for key {key}: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def _cleanup_chunks(self, key: str, chunk_id: str) -> None:
        """
        Clean up orphaned chunks for a given key and chunk ID.

        Args:
            key: Original cache key
            chunk_id: Unique chunk identifier
        """
        try:
            # Scan for chunks with the given chunk_id
            scan_kwargs = {
                "FilterExpression": "chunk_id = :chunk_id",
                "ExpressionAttributeValues": {":chunk_id": chunk_id},
                "ProjectionExpression": "cache_key",
            }

            chunks_to_delete = []

            while True:
                response = self.table.scan(**scan_kwargs)
                items = response.get("Items", [])

                for item in items:
                    chunks_to_delete.append({"cache_key": item["cache_key"]})

                # Check if there are more items to scan
                if "LastEvaluatedKey" not in response:
                    break

                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            # Delete chunks in batches
            if chunks_to_delete:
                with self.table.batch_writer() as batch:
                    for chunk_key in chunks_to_delete:
                        batch.delete_item(Key=chunk_key)

                logger.debug(f"Cleaned up {len(chunks_to_delete)} orphaned chunks for key {key}")

        except Exception as e:
            logger.warning(f"Failed to cleanup chunks for key {key}: {e}")

    def _put_item_with_retry(self, item: Dict[str, Any]) -> None:
        """
        Put item with retry logic for common errors.

        Args:
            item: Item to store
        """
        try:
            self.table.put_item(Item=item)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ResourceNotFoundException":
                # Try to create table and retry once
                logger.info(f"Table {self.table_name} not found, attempting to create")
                self._create_table()
                self.table.put_item(Item=item)
            elif error_code in ["ProvisionedThroughputExceededException", "RequestLimitExceeded"]:
                logger.warning("DynamoDB throttling for put operation")
                # Don't raise error for throttling, just log and continue
            else:
                raise CacheBackendError(
                    f"DynamoDB put operation failed: {e}", backend_type="dynamodb", original_error=e
                )

    def cleanup_orphaned_chunks(self) -> Dict[str, Any]:
        """
        Clean up orphaned chunks that don't have corresponding metadata entries.

        Returns:
            Dictionary with cleanup results
        """
        cleanup_result = {"success": False, "chunks_found": 0, "chunks_deleted": 0, "errors": []}

        try:
            # Scan for all chunk items
            chunk_items = []
            scan_kwargs = {
                "FilterExpression": "attribute_exists(is_chunk)",
                "ProjectionExpression": "cache_key, parent_key, chunk_id",
            }

            while True:
                response = self.table.scan(**scan_kwargs)
                items = response.get("Items", [])
                chunk_items.extend(items)

                if "LastEvaluatedKey" not in response:
                    break

                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            cleanup_result["chunks_found"] = len(chunk_items)

            # Group chunks by parent key and chunk_id
            chunk_groups = {}
            for chunk in chunk_items:
                parent_key = chunk.get("parent_key")
                chunk_id = chunk.get("chunk_id")
                if parent_key and chunk_id:
                    group_key = f"{parent_key}#{chunk_id}"
                    if group_key not in chunk_groups:
                        chunk_groups[group_key] = []
                    chunk_groups[group_key].append(chunk["cache_key"])

            # Check which chunk groups are orphaned
            orphaned_chunks = []
            for group_key, chunk_keys in chunk_groups.items():
                parent_key = group_key.split("#")[0]

                # Check if parent metadata exists
                try:
                    response = self.table.get_item(Key={"cache_key": parent_key})
                    if "Item" not in response or not response["Item"].get("is_chunked", False):
                        # Parent doesn't exist or is not chunked, these are orphaned
                        orphaned_chunks.extend(chunk_keys)
                except Exception as e:
                    logger.warning(f"Error checking parent key {parent_key}: {e}")
                    # Assume orphaned if we can't check
                    orphaned_chunks.extend(chunk_keys)

            # Delete orphaned chunks
            if orphaned_chunks:
                with self.table.batch_writer() as batch:
                    for chunk_key in orphaned_chunks:
                        batch.delete_item(Key={"cache_key": chunk_key})
                        cleanup_result["chunks_deleted"] += 1

            cleanup_result["success"] = True
            logger.info(f"Cleaned up {cleanup_result['chunks_deleted']} orphaned chunks")

            return cleanup_result

        except Exception as e:
            cleanup_result["errors"].append(f"Unexpected error during cleanup: {e}")
            logger.error(f"Failed to cleanup orphaned chunks: {e}")
            return cleanup_result

    def _invalidate_all_entries(self) -> None:
        """
        Invalidate all cache entries by scanning and deleting them.

        This is an expensive operation and should be used sparingly.

        Raises:
            CacheBackendError: If scan/delete operations fail
        """
        try:
            # Scan all items and delete them in batches
            scan_kwargs = {"ProjectionExpression": "cache_key"}

            deleted_count = 0

            while True:
                response = self.table.scan(**scan_kwargs)
                items = response.get("Items", [])

                if not items:
                    break

                # Delete items in batches
                with self.table.batch_writer() as batch:
                    for item in items:
                        batch.delete_item(Key={"cache_key": item["cache_key"]})
                        deleted_count += 1

                # Check if there are more items to scan
                if "LastEvaluatedKey" not in response:
                    break

                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            logger.info(f"Invalidated {deleted_count} cache entries from DynamoDB")

        except ClientError as e:
            raise CacheBackendError(
                f"Failed to invalidate all cache entries: {e}",
                backend_type="dynamodb",
                original_error=e,
            )
        except Exception as e:
            raise CacheBackendError(
                f"Unexpected error invalidating all cache entries: {e}",
                backend_type="dynamodb",
                original_error=e,
            )

    def get_recent_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent cache entries from DynamoDB.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of dictionaries containing entry metadata
        """
        try:
            # Ensure table exists before attempting operations
            self._ensure_table_exists()

            # Scan the table to get recent entries, sorted by creation time
            response = self.table.scan(
                ProjectionExpression="cache_key, operation, created_at, #ttl, original_size, is_compressed, is_chunked",
                ExpressionAttributeNames={"#ttl": "ttl"},  # ttl is a reserved word
                Limit=limit * 2,  # Get more items to account for filtering
            )

            items = response.get("Items", [])
            if not items:
                return []

            # Convert and sort items by creation time (newest first)
            entries = []
            current_time = int(time.time())

            for item in items:
                try:
                    created_at = int(item.get("created_at", 0))
                    ttl_value = item.get("ttl")

                    # Calculate age
                    age_seconds = current_time - created_at
                    if age_seconds < 60:
                        age = f"{age_seconds}s"
                    elif age_seconds < 3600:
                        age = f"{age_seconds // 60}m"
                    else:
                        age = f"{age_seconds // 3600}h"

                    # Format TTL
                    ttl_display = "None"
                    is_expired = False
                    if ttl_value:
                        ttl_int = int(ttl_value)
                        if ttl_int > current_time:
                            remaining = ttl_int - current_time
                            if remaining < 60:
                                ttl_display = f"{remaining}s"
                            elif remaining < 3600:
                                ttl_display = f"{remaining // 60}m"
                            else:
                                ttl_display = f"{remaining // 3600}h"
                        else:
                            ttl_display = "Expired"
                            is_expired = True

                    # Format size
                    original_size = item.get("original_size", 0)
                    logger.debug(
                        f"Original size value: {original_size}, type: {type(original_size)}"
                    )

                    # Handle both int/float and Decimal types (DynamoDB may return Decimal)
                    if isinstance(original_size, (int, float)):
                        size_value = original_size
                    elif hasattr(original_size, "__float__"):  # Handle Decimal type
                        size_value = float(original_size)
                    else:
                        logger.debug(
                            f"Unexpected original_size type: {type(original_size)}, value: {original_size}"
                        )
                        size_value = 0

                    if size_value > 0:
                        if size_value < 1024:
                            size_display = f"{int(size_value)}B"
                        elif size_value < 1024 * 1024:
                            size_display = f"{size_value / 1024:.1f}KB"
                        else:
                            size_display = f"{size_value / (1024 * 1024):.1f}MB"
                    else:
                        size_display = "0B"

                    # Skip chunk entries for cleaner display
                    cache_key = item.get("cache_key", "")
                    if "#chunk#" in cache_key:
                        continue

                    entry = {
                        "key": cache_key,
                        "operation": item.get("operation", "Unknown"),
                        "age": age,
                        "ttl": ttl_display,
                        "size": size_display,
                        "created_at": created_at,
                        "is_expired": is_expired,
                        "is_compressed": item.get("is_compressed", False),
                        "is_chunked": item.get("is_chunked", False),
                    }
                    entries.append(entry)

                except Exception as e:
                    logger.debug(f"Error processing cache entry: {e}")
                    continue

            # Sort by creation time (newest first) and limit results
            entries.sort(key=lambda x: x["created_at"], reverse=True)
            return entries[:limit]

        except ClientError as e:
            logger.warning(f"Failed to get recent entries from DynamoDB: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error getting recent entries: {e}")
            return []
