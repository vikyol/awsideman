"""
Storage backend implementations for different storage types.

This module provides concrete implementations of storage backends including
filesystem and S3 storage with proper error handling and metadata support.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import aiofiles.os

try:
    import aioboto3
    from botocore.exceptions import NoCredentialsError, TokenRetrievalError

    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

from .interfaces import StorageBackendInterface

logger = logging.getLogger(__name__)


class FileSystemStorageBackend(StorageBackendInterface):
    """
    Filesystem-based storage backend for local backup storage.

    Stores backups in a local directory structure with proper
    file organization and metadata tracking.
    """

    def __init__(self, base_path: str, create_dirs: bool = True, profile: Optional[str] = None):
        """
        Initialize filesystem storage backend.

        Args:
            base_path: Base directory path for storing backups
            create_dirs: Whether to create directories if they don't exist
            profile: AWS profile name for isolation
        """
        self.base_path = Path(base_path)
        self.create_dirs = create_dirs
        self.profile = profile

        # Add profile isolation
        profile_name = profile or "default"
        self.base_path = self.base_path / "profiles" / profile_name

        if create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized filesystem storage at {self.base_path}")

    async def write_data(self, key: str, data: bytes) -> bool:
        """
        Write data to filesystem.

        Args:
            key: Storage key/path for the data
            data: Raw data to store

        Returns:
            True if write was successful, False otherwise
        """
        try:
            file_path = self.base_path / key

            # Create parent directories if needed
            if self.create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write data atomically using temporary file
            temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(data)

            # Atomic move to final location
            await aiofiles.os.rename(str(temp_path), str(file_path))

            logger.debug(f"Successfully wrote data to {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to write data to {key}: {e}")
            # Clean up temporary file if it exists
            temp_path = self.base_path / key
            temp_path = temp_path.with_suffix(temp_path.suffix + ".tmp")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False

    async def read_data(self, key: str) -> Optional[bytes]:
        """
        Read data from filesystem.

        Args:
            key: Storage key/path for the data

        Returns:
            Raw data if found, None otherwise
        """
        try:
            file_path = self.base_path / key

            if not file_path.exists():
                logger.debug(f"File not found: {key}")
                return None

            async with aiofiles.open(file_path, "rb") as f:
                data = await f.read()

            logger.debug(f"Successfully read data from {key}")
            return data

        except Exception as e:
            logger.error(f"Failed to read data from {key}: {e}")
            return None

    async def delete_data(self, key: str) -> bool:
        """
        Delete data from filesystem.

        Args:
            key: Storage key/path for the data to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            file_path = self.base_path / key

            if not file_path.exists():
                logger.debug(f"File not found for deletion: {key}")
                return True  # Consider non-existent file as successfully deleted

            await aiofiles.os.remove(str(file_path))

            # Clean up empty parent directories
            try:
                parent = file_path.parent
                while parent != self.base_path and parent.exists():
                    if not any(parent.iterdir()):  # Directory is empty
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
            except Exception:
                # Ignore errors in cleanup
                pass

            logger.debug(f"Successfully deleted data at {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete data at {key}: {e}")
            return False

    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """
        List available keys in filesystem storage.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            List of storage keys
        """
        try:
            keys = []
            search_path = self.base_path

            if prefix:
                search_path = self.base_path / prefix
                if not search_path.exists():
                    return []

            # Recursively find all files
            for file_path in search_path.rglob("*"):
                if file_path.is_file():
                    # Convert to relative path from base_path
                    relative_path = file_path.relative_to(self.base_path)
                    key = str(relative_path).replace(os.sep, "/")

                    # Apply prefix filter if specified
                    if prefix is None or key.startswith(prefix):
                        keys.append(key)

            logger.debug(f"Found {len(keys)} keys with prefix '{prefix}'")
            return sorted(keys)

        except Exception as e:
            logger.error(f"Failed to list keys with prefix '{prefix}': {e}")
            return []

    async def exists(self, key: str) -> bool:
        """
        Check if data exists at the specified key.

        Args:
            key: Storage key/path to check

        Returns:
            True if data exists, False otherwise
        """
        try:
            file_path = self.base_path / key
            return file_path.exists() and file_path.is_file()
        except Exception as e:
            logger.error(f"Failed to check existence of {key}: {e}")
            return False

    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for stored data.

        Args:
            key: Storage key/path for the data

        Returns:
            Metadata dictionary if found, None otherwise
        """
        try:
            file_path = self.base_path / key

            if not file_path.exists():
                return None

            stat = file_path.stat()

            metadata = {
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "path": str(file_path),
                "backend": "filesystem",
            }

            return metadata

        except Exception as e:
            logger.error(f"Failed to get metadata for {key}: {e}")
            return None


class S3StorageBackend(StorageBackendInterface):
    """
    S3-based storage backend for cloud backup storage.

    Stores backups in Amazon S3 with proper error handling,
    retry logic, and metadata support.
    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        profile_name: Optional[str] = None,
        profile: Optional[str] = None,
    ):
        """
        Initialize S3 storage backend.

        Args:
            bucket_name: S3 bucket name
            prefix: Optional prefix for all keys
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
            aws_session_token: AWS session token (for temporary credentials)
            region_name: AWS region name
            endpoint_url: Custom S3 endpoint URL (for S3-compatible services)
            profile_name: AWS profile name (for SSO or named profiles)
            profile: AWS profile name for isolation (adds to prefix)
        """
        if not HAS_BOTO3:
            raise ImportError("boto3 and aioboto3 are required for S3 storage backend")

        self.bucket_name = bucket_name
        self.profile_name = profile_name
        self.profile = profile

        # Build prefix with profile isolation
        # For S3, profile is mandatory - each account should have its own bucket/data
        if not profile:
            raise ValueError(
                "Profile is required for S3 storage backend. Each AWS account should have its own S3 storage."
            )

        base_prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.prefix = f"{base_prefix}profiles/{profile}/"

        # AWS credentials and configuration
        self.aws_config = {
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "aws_session_token": aws_session_token,
            "region_name": region_name,
            "endpoint_url": endpoint_url,
        }

        # Remove None values
        self.aws_config = {k: v for k, v in self.aws_config.items() if v is not None}

        logger.info(f"Initialized S3 storage for bucket {bucket_name} with prefix '{self.prefix}'")

    def _get_s3_key(self, key: str) -> str:
        """Convert storage key to S3 key with prefix."""
        return f"{self.prefix}{key}"

    def _create_session(self) -> aioboto3.Session:
        """Create aioboto3 session with profile or explicit credentials."""
        if self.profile_name:
            # Use profile-based session for SSO and named profiles
            return aioboto3.Session(profile_name=self.profile_name)
        else:
            # Use explicit credentials or default credential chain
            return aioboto3.Session()

    async def write_data(self, key: str, data: bytes) -> bool:
        """
        Write data to S3.

        Args:
            key: Storage key/path for the data
            data: Raw data to store

        Returns:
            True if write was successful, False otherwise
        """
        try:
            s3_key = self._get_s3_key(key)

            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=data,
                    ServerSideEncryption="AES256",  # Enable server-side encryption
                    Metadata={"backup-system": "awsideman", "created": datetime.now().isoformat()},
                )

            logger.debug(f"Successfully wrote data to S3 key {s3_key}")
            return True

        except Exception as e:
            # Check for authentication errors first
            if isinstance(e, (TokenRetrievalError, NoCredentialsError)):
                logger.error(f"Authentication error writing to S3 key {key}: {e}")
                # Re-raise authentication errors so they can be handled properly
                raise

            logger.error(f"Failed to write data to S3 key {key}: {e}")
            return False

    async def read_data(self, key: str) -> Optional[bytes]:
        """
        Read data from S3.

        Args:
            key: Storage key/path for the data

        Returns:
            Raw data if found, None otherwise
        """
        try:
            s3_key = self._get_s3_key(key)

            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                data = await response["Body"].read()

            logger.debug(f"Successfully read data from S3 key {s3_key}")
            return data

        except Exception as e:
            # Check for authentication errors first
            if isinstance(e, (TokenRetrievalError, NoCredentialsError)):
                logger.error(f"Authentication error reading S3 key {key}: {e}")
                # Re-raise authentication errors so they can be handled properly
                raise

            if "NoSuchKey" in str(e):
                logger.debug(f"S3 key not found: {s3_key}")
            else:
                logger.error(f"Failed to read data from S3 key {key}: {e}")
            return None

    async def delete_data(self, key: str) -> bool:
        """
        Delete data from S3.

        Args:
            key: Storage key/path for the data to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            s3_key = self._get_s3_key(key)

            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.debug(f"Successfully deleted S3 key {s3_key}")
            return True

        except Exception as e:
            # Check for authentication errors first
            if isinstance(e, (TokenRetrievalError, NoCredentialsError)):
                logger.error(f"Authentication error deleting S3 key {key}: {e}")
                # Re-raise authentication errors so they can be handled properly
                raise

            logger.error(f"Failed to delete S3 key {key}: {e}")
            return False

    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """
        List available keys in S3 storage.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            List of storage keys
        """
        try:
            search_prefix = self.prefix
            if prefix:
                search_prefix += prefix

            keys = []
            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                paginator = s3.get_paginator("list_objects_v2")

                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=search_prefix):
                    if "Contents" in page:
                        for obj in page["Contents"]:
                            s3_key = obj["Key"]
                            # Remove our prefix to get the storage key
                            if s3_key.startswith(self.prefix):
                                storage_key = s3_key[len(self.prefix) :]
                                keys.append(storage_key)

            logger.debug(f"Found {len(keys)} S3 keys with prefix '{prefix}'")
            return sorted(keys)

        except Exception as e:
            logger.error(f"Failed to list S3 keys with prefix '{prefix}': {e}")
            return []

    async def exists(self, key: str) -> bool:
        """
        Check if data exists at the specified S3 key.

        Args:
            key: Storage key/path to check

        Returns:
            True if data exists, False otherwise
        """
        try:
            s3_key = self._get_s3_key(key)

            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=s3_key)

            return True

        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                return False
            else:
                logger.error(f"Failed to check existence of S3 key {key}: {e}")
                return False

    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for stored S3 object.

        Args:
            key: Storage key/path for the data

        Returns:
            Metadata dictionary if found, None otherwise
        """
        try:
            s3_key = self._get_s3_key(key)

            session = self._create_session()
            async with session.client("s3", **self.aws_config) as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=s3_key)

            metadata = {
                "size": response.get("ContentLength", 0),
                "created": response.get("LastModified", datetime.now()).isoformat(),
                "modified": response.get("LastModified", datetime.now()).isoformat(),
                "etag": response.get("ETag", "").strip('"'),
                "storage_class": response.get("StorageClass", "STANDARD"),
                "server_side_encryption": response.get("ServerSideEncryption"),
                "bucket": self.bucket_name,
                "key": s3_key,
                "backend": "s3",
            }

            # Include custom metadata if present
            if "Metadata" in response:
                metadata["custom_metadata"] = response["Metadata"]

            return metadata

        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                logger.debug(f"S3 key not found: {s3_key}")
            else:
                logger.error(f"Failed to get metadata for S3 key {key}: {e}")
            return None


class StorageBackendFactory:
    """Factory for creating storage backend instances."""

    @staticmethod
    def create_filesystem_backend(base_path: str, **kwargs) -> FileSystemStorageBackend:
        """
        Create a filesystem storage backend.

        Args:
            base_path: Base directory path for storing backups
            **kwargs: Additional arguments for FileSystemStorageBackend

        Returns:
            FileSystemStorageBackend instance
        """
        return FileSystemStorageBackend(base_path, **kwargs)

    @staticmethod
    def create_s3_backend(bucket_name: str, **kwargs) -> S3StorageBackend:
        """
        Create an S3 storage backend.

        Args:
            bucket_name: S3 bucket name
            **kwargs: Additional arguments for S3StorageBackend

        Returns:
            S3StorageBackend instance
        """
        return S3StorageBackend(bucket_name, **kwargs)

    @staticmethod
    def create_backend(backend_type: str, **config) -> StorageBackendInterface:
        """
        Create a storage backend based on type and configuration.

        Args:
            backend_type: Type of backend ('filesystem' or 's3')
            **config: Configuration parameters for the backend

        Returns:
            StorageBackendInterface implementation

        Raises:
            ValueError: If backend_type is not supported
        """
        if backend_type.lower() == "filesystem":
            return StorageBackendFactory.create_filesystem_backend(**config)
        elif backend_type.lower() == "s3":
            return StorageBackendFactory.create_s3_backend(**config)
        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")
