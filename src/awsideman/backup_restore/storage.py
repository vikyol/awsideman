"""
Storage engine implementation with multiple backend support.

This module provides the main storage engine that coordinates between different
storage backends (filesystem, S3) and handles encryption, compression, and
integrity verification.
"""

import gzip
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from botocore.exceptions import NoCredentialsError, TokenRetrievalError

    HAS_BOTOCORE = True
except ImportError:
    HAS_BOTOCORE = False

from .interfaces import EncryptionProviderInterface, StorageBackendInterface, StorageEngineInterface
from .models import BackupData, BackupMetadata, ValidationResult
from .serialization import BackupSerializer

logger = logging.getLogger(__name__)


class StorageEngine(StorageEngineInterface):
    """
    Main storage engine that coordinates backup storage operations.

    Supports multiple storage backends with encryption, compression,
    and integrity verification capabilities.
    """

    def __init__(
        self,
        backend: StorageBackendInterface,
        encryption_provider: Optional[EncryptionProviderInterface] = None,
        enable_compression: bool = True,
    ):
        """
        Initialize storage engine.

        Args:
            backend: Storage backend implementation
            encryption_provider: Optional encryption provider
            enable_compression: Whether to enable compression
        """
        self.backend = backend
        self.encryption_provider = encryption_provider
        self.enable_compression = enable_compression
        self.serializer = BackupSerializer()

    async def store_backup(self, backup_data: BackupData) -> str:
        """
        Store backup data and return a unique identifier.

        Args:
            backup_data: Complete backup data to store

        Returns:
            Unique identifier for the stored backup

        Raises:
            Exception: If storage operation fails
        """
        try:
            backup_id = backup_data.metadata.backup_id
            logger.info(f"Storing backup {backup_id}")

            # Serialize backup data
            serialized_data = await self.serializer.serialize(backup_data)

            # Compress if enabled
            if self.enable_compression:
                serialized_data = gzip.compress(serialized_data)
                logger.debug(f"Compressed backup data for {backup_id}")

            # Encrypt if provider is available
            encryption_metadata: Dict[str, Any] = {}
            if self.encryption_provider:
                serialized_data, encryption_metadata = await self.encryption_provider.encrypt(
                    serialized_data
                )
                logger.debug(f"Encrypted backup data for {backup_id}")

            # Calculate final checksum
            final_checksum = hashlib.sha256(serialized_data).hexdigest()
            backup_data.metadata.calculate_checksum(serialized_data)

            # Store main backup data
            data_key = f"backups/{backup_id}/data"
            success = await self.backend.write_data(data_key, serialized_data)
            if not success:
                raise Exception(f"Failed to store backup data for {backup_id}")

            # Store metadata separately for quick access
            metadata_dict = backup_data.metadata.to_dict()
            metadata_dict["encryption_metadata"] = encryption_metadata
            metadata_dict["compressed"] = self.enable_compression
            metadata_dict["final_checksum"] = final_checksum

            metadata_json = json.dumps(metadata_dict, indent=2, default=str)
            metadata_key = f"backups/{backup_id}/metadata.json"

            success = await self.backend.write_data(metadata_key, metadata_json.encode())
            if not success:
                raise Exception(f"Failed to store backup metadata for {backup_id}")

            logger.info(f"Successfully stored backup {backup_id}")
            return backup_id

        except Exception as e:
            logger.error(f"Failed to store backup {backup_data.metadata.backup_id}: {e}")
            raise

    async def retrieve_backup(self, backup_id: str) -> Optional[BackupData]:
        """
        Retrieve backup data by identifier.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupData if found, None otherwise
        """
        try:
            logger.info(f"Retrieving backup {backup_id}")

            # First, get metadata to understand storage format
            metadata_key = f"backups/{backup_id}/metadata.json"
            metadata_bytes = await self.backend.read_data(metadata_key)
            if not metadata_bytes:
                logger.warning(f"Metadata not found for backup {backup_id}")
                return None

            metadata_dict = json.loads(metadata_bytes.decode())

            # Get main backup data
            data_key = f"backups/{backup_id}/data"
            data_bytes = await self.backend.read_data(data_key)
            if not data_bytes:
                logger.warning(f"Data not found for backup {backup_id}")
                return None

            # Verify final checksum
            expected_checksum = metadata_dict.get("final_checksum")
            if expected_checksum:
                actual_checksum = hashlib.sha256(data_bytes).hexdigest()
                if actual_checksum != expected_checksum:
                    raise Exception(f"Checksum mismatch for backup {backup_id}")

            # Decrypt if needed
            encryption_metadata = metadata_dict.get("encryption_metadata", {})
            if encryption_metadata and self.encryption_provider:
                data_bytes = await self.encryption_provider.decrypt(data_bytes, encryption_metadata)
                logger.debug(f"Decrypted backup data for {backup_id}")

            # Decompress if needed
            if metadata_dict.get("compressed", False):
                data_bytes = gzip.decompress(data_bytes)
                logger.debug(f"Decompressed backup data for {backup_id}")

            # Deserialize backup data
            backup_data = await self.serializer.deserialize(data_bytes)

            logger.info(f"Successfully retrieved backup {backup_id}")
            return backup_data

        except Exception as e:
            # Check for authentication errors first
            if HAS_BOTOCORE and isinstance(e, (TokenRetrievalError, NoCredentialsError)):
                logger.error(f"Authentication error retrieving backup {backup_id}: {e}")
                # Re-raise authentication errors so they can be handled properly
                raise

            logger.error(f"Failed to retrieve backup {backup_id}: {e}")
            return None

    async def list_backups(self, filters: Optional[Dict[str, Any]] = None) -> List[BackupMetadata]:
        """
        List stored backups with optional filtering.

        Args:
            filters: Optional filters to apply to the backup list

        Returns:
            List of backup metadata objects
        """
        try:
            logger.debug("Listing backups")

            # Get all backup keys
            backup_keys = await self.backend.list_keys("backups/")
            metadata_keys = [key for key in backup_keys if key.endswith("/metadata.json")]

            backups = []
            for metadata_key in metadata_keys:
                try:
                    metadata_bytes = await self.backend.read_data(metadata_key)
                    if metadata_bytes:
                        metadata_dict = json.loads(metadata_bytes.decode())
                        # Remove storage-specific fields before creating BackupMetadata
                        storage_fields = ["encryption_metadata", "compressed", "final_checksum"]
                        for field in storage_fields:
                            metadata_dict.pop(field, None)

                        backup_metadata = BackupMetadata.from_dict(metadata_dict)

                        # Apply filters if provided
                        if self._matches_filters(backup_metadata, filters):
                            backups.append(backup_metadata)

                except Exception as e:
                    logger.warning(f"Failed to parse metadata from {metadata_key}: {e}")
                    continue

            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x.timestamp, reverse=True)

            logger.debug(f"Found {len(backups)} backups")
            return backups

        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []

    def _matches_filters(self, metadata: BackupMetadata, filters: Optional[Dict[str, Any]]) -> bool:
        """Check if backup metadata matches the provided filters."""
        if not filters:
            return True

        for key, value in filters.items():
            if key == "backup_type" and metadata.backup_type.value != value:
                return False
            elif key == "source_account" and metadata.source_account != value:
                return False
            elif key == "source_region" and metadata.source_region != value:
                return False
            elif key == "instance_arn" and metadata.instance_arn != value:
                return False
            elif key == "after" and metadata.timestamp < value:
                return False
            elif key == "before" and metadata.timestamp > value:
                return False

        return True

    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete stored backup data.

        Args:
            backup_id: Unique identifier of the backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            logger.info(f"Deleting backup {backup_id}")

            # Delete both data and metadata
            data_key = f"backups/{backup_id}/data"
            metadata_key = f"backups/{backup_id}/metadata.json"

            data_deleted = await self.backend.delete_data(data_key)
            metadata_deleted = await self.backend.delete_data(metadata_key)

            success = data_deleted and metadata_deleted
            if success:
                logger.info(f"Successfully deleted backup {backup_id}")
            else:
                logger.warning(f"Partial deletion for backup {backup_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            return False

    async def verify_integrity(self, backup_id: str) -> ValidationResult:
        """
        Verify the integrity of stored backup data.

        Args:
            backup_id: Unique identifier of the backup to verify

        Returns:
            ValidationResult containing integrity status and details
        """
        try:
            logger.info(f"Verifying integrity of backup {backup_id}")

            errors: List[str] = []
            warnings: List[str] = []
            details: Dict[str, Any] = {}

            # Check if backup exists
            metadata_key = f"backups/{backup_id}/metadata.json"
            data_key = f"backups/{backup_id}/data"

            metadata_exists = await self.backend.exists(metadata_key)
            data_exists = await self.backend.exists(data_key)

            if not metadata_exists:
                errors.append(f"Metadata file missing for backup {backup_id}")
            if not data_exists:
                errors.append(f"Data file missing for backup {backup_id}")

            if errors:
                return ValidationResult(
                    is_valid=False, errors=errors, warnings=warnings, details=details
                )

            # Verify checksums
            try:
                backup_data = await self.retrieve_backup(backup_id)
                if backup_data:
                    # Verify internal data integrity
                    if not backup_data.verify_integrity():
                        errors.append("Internal data integrity check failed")
                    else:
                        details["internal_integrity"] = "passed"

                    # Verify metadata checksum if available
                    if backup_data.metadata.checksum:
                        details["metadata_checksum"] = "verified"
                    else:
                        warnings.append("No metadata checksum available")

                else:
                    errors.append("Failed to retrieve backup data for verification")

            except Exception as e:
                errors.append(f"Error during data verification: {e}")

            is_valid = len(errors) == 0

            logger.info(
                f"Integrity verification for backup {backup_id}: {'passed' if is_valid else 'failed'}"
            )

            return ValidationResult(
                is_valid=is_valid, errors=errors, warnings=warnings, details=details
            )

        except Exception as e:
            logger.error(f"Failed to verify integrity of backup {backup_id}: {e}")
            return ValidationResult(
                is_valid=False, errors=[f"Verification failed: {e}"], warnings=[], details={}
            )

    async def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about storage usage and capacity.

        Returns:
            Dictionary containing storage information
        """
        try:
            logger.debug("Getting storage information")

            # Get all backup keys to calculate usage
            backup_keys = await self.backend.list_keys("backups/")

            total_backups = len([key for key in backup_keys if key.endswith("/metadata.json")])

            # Calculate total size (this is backend-dependent)
            total_size = 0
            for key in backup_keys:
                try:
                    metadata = await self.backend.get_metadata(key)
                    if metadata and "size" in metadata:
                        total_size += metadata["size"]
                except Exception:
                    # Skip if metadata not available
                    pass

            info = {
                "total_backups": total_backups,
                "total_size_bytes": total_size,
                "backend_type": type(self.backend).__name__,
                "compression_enabled": self.enable_compression,
                "encryption_enabled": self.encryption_provider is not None,
                "last_updated": datetime.now().isoformat(),
            }

            logger.debug(f"Storage info: {info}")
            return info

        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {"error": str(e), "last_updated": datetime.now().isoformat()}

    async def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Get metadata for a specific backup.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupMetadata if found, None otherwise
        """
        try:
            logger.debug(f"Getting metadata for backup: {backup_id}")

            metadata_key = f"backups/{backup_id}/metadata.json"
            metadata_data = await self.backend.read_data(metadata_key)

            if not metadata_data:
                logger.warning(f"Metadata not found for backup: {backup_id}")
                return None

            # Decrypt if necessary
            if self.encryption_provider:
                try:
                    # Try to parse as encrypted data first
                    encrypted_metadata = json.loads(metadata_data.decode())
                    if "encryption_metadata" in encrypted_metadata:
                        metadata_data = await self.encryption_provider.decrypt(
                            encrypted_metadata["data"], encrypted_metadata["encryption_metadata"]
                        )
                except (json.JSONDecodeError, KeyError):
                    # Data might not be encrypted, continue with original data
                    pass

            # Parse metadata
            metadata_dict = json.loads(metadata_data.decode())
            metadata = BackupMetadata.from_dict(metadata_dict)

            logger.debug(f"Retrieved metadata for backup: {backup_id}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to get backup metadata for {backup_id}: {e}")
            return None
