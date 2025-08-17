"""
Serialization utilities for backup and restore data models.

This module provides comprehensive serialization and deserialization functions
for all data models, supporting multiple formats (JSON, YAML, binary) with
compression and encryption capabilities.
"""

import bz2
import gzip
import hashlib
import json
import lzma
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar, Union

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupResult,
    EncryptionMetadata,
    ExportFormat,
    GroupData,
    ImportSource,
    NotificationSettings,
    PermissionSetData,
    RestoreOptions,
    RestoreResult,
    RetentionPolicy,
    ScheduleConfig,
    UserData,
    ValidationResult,
)

T = TypeVar("T")


class SerializationError(Exception):
    """Custom exception for serialization errors."""

    pass


class CompressionType:
    """Supported compression types."""

    NONE = "none"
    GZIP = "gzip"
    BZ2 = "bz2"
    LZMA = "lzma"


class SerializationFormat:
    """Supported serialization formats."""

    JSON = "json"
    YAML = "yaml"
    PICKLE = "pickle"
    BINARY = "binary"


class DataSerializer:
    """Comprehensive serializer for backup-restore data models."""

    def __init__(
        self,
        default_format: str = SerializationFormat.JSON,
        default_compression: str = CompressionType.GZIP,
    ):
        """
        Initialize the serializer with default settings.

        Args:
            default_format: Default serialization format to use
            default_compression: Default compression type to use
        """
        self.default_format = default_format
        self.default_compression = default_compression

        # Mapping of model classes to their serialization methods
        self._serializers = {
            BackupData: self._serialize_backup_data,
            BackupMetadata: self._serialize_backup_metadata,
            BackupOptions: self._serialize_backup_options,
            RestoreOptions: self._serialize_restore_options,
            UserData: self._serialize_user_data,
            GroupData: self._serialize_group_data,
            PermissionSetData: self._serialize_permission_set_data,
            AssignmentData: self._serialize_assignment_data,
            ValidationResult: self._serialize_validation_result,
            BackupResult: self._serialize_backup_result,
            RestoreResult: self._serialize_restore_result,
            RetentionPolicy: self._serialize_retention_policy,
            EncryptionMetadata: self._serialize_encryption_metadata,
            ScheduleConfig: self._serialize_schedule_config,
            NotificationSettings: self._serialize_notification_settings,
            ExportFormat: self._serialize_export_format,
            ImportSource: self._serialize_import_source,
        }

        # Mapping of model classes to their deserialization methods
        self._deserializers = {
            BackupData: BackupData.from_dict,
            BackupMetadata: BackupMetadata.from_dict,
            BackupOptions: BackupOptions.from_dict,
            RestoreOptions: RestoreOptions.from_dict,
            UserData: UserData.from_dict,
            GroupData: GroupData.from_dict,
            PermissionSetData: PermissionSetData.from_dict,
            AssignmentData: AssignmentData.from_dict,
            RetentionPolicy: RetentionPolicy.from_dict,
            EncryptionMetadata: EncryptionMetadata.from_dict,
            ScheduleConfig: ScheduleConfig.from_dict,
        }

    def serialize(
        self, obj: Any, format_type: Optional[str] = None, compression: Optional[str] = None
    ) -> bytes:
        """
        Serialize an object to bytes with optional compression.

        Args:
            obj: Object to serialize
            format_type: Serialization format (defaults to instance default)
            compression: Compression type (defaults to instance default)

        Returns:
            Serialized and optionally compressed bytes

        Raises:
            SerializationError: If serialization fails
        """
        format_type = format_type or self.default_format
        compression = compression or self.default_compression

        try:
            # Convert object to serializable format
            if hasattr(obj, "to_dict"):
                data = obj.to_dict()
            elif isinstance(obj, (dict, list, str, int, float, bool, type(None))):
                data = obj
            else:
                # Try to find a custom serializer
                obj_type = type(obj)
                if obj_type in self._serializers:
                    data = self._serializers[obj_type](obj)
                else:
                    raise SerializationError(f"No serializer found for type: {obj_type}")

            # Add metadata
            serialized_data = {
                "data": data,
                "metadata": {
                    "format": format_type,
                    "compression": compression,
                    "timestamp": datetime.now().isoformat(),
                    "type": (
                        obj.__class__.__name__ if hasattr(obj, "__class__") else type(obj).__name__
                    ),
                    "version": "1.0",
                },
            }

            # Serialize to bytes based on format
            if format_type == SerializationFormat.JSON:
                serialized_bytes = json.dumps(
                    serialized_data, default=self._json_serializer, ensure_ascii=False, indent=None
                ).encode("utf-8")
            elif format_type == SerializationFormat.YAML:
                if not YAML_AVAILABLE:
                    raise SerializationError("YAML serialization requires PyYAML package")
                serialized_bytes = yaml.dump(
                    serialized_data, default_flow_style=False, allow_unicode=True
                ).encode("utf-8")
            elif format_type == SerializationFormat.PICKLE:
                serialized_bytes = pickle.dumps(serialized_data, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                raise SerializationError(f"Unsupported serialization format: {format_type}")

            # Apply compression
            compressed_bytes = self._compress_data(serialized_bytes, compression)

            return compressed_bytes

        except Exception as e:
            raise SerializationError(f"Serialization failed: {e}") from e

    def deserialize(
        self,
        data: bytes,
        target_type: Type[T],
        format_type: Optional[str] = None,
        compression: Optional[str] = None,
    ) -> T:
        """
        Deserialize bytes to an object of the specified type.

        Args:
            data: Serialized and optionally compressed bytes
            target_type: Type to deserialize to
            format_type: Serialization format (auto-detected if None)
            compression: Compression type (auto-detected if None)

        Returns:
            Deserialized object of target_type

        Raises:
            SerializationError: If deserialization fails
        """
        try:
            # Decompress data
            if compression:
                decompressed_data = self._decompress_data(data, compression)
            else:
                # Try to auto-detect compression
                decompressed_data = self._auto_decompress(data)

            # Deserialize based on format
            if format_type == SerializationFormat.JSON or format_type is None:
                try:
                    serialized_data = json.loads(decompressed_data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if format_type == SerializationFormat.JSON:
                        raise SerializationError("Failed to parse JSON data")
                    serialized_data = None

            if format_type == SerializationFormat.YAML or (
                format_type is None and serialized_data is None
            ):
                if not YAML_AVAILABLE:
                    if format_type == SerializationFormat.YAML:
                        raise SerializationError("YAML deserialization requires PyYAML package")
                else:
                    try:
                        serialized_data = yaml.safe_load(decompressed_data.decode("utf-8"))
                    except (yaml.YAMLError, UnicodeDecodeError):
                        if format_type == SerializationFormat.YAML:
                            raise SerializationError("Failed to parse YAML data")
                        serialized_data = None

            if format_type == SerializationFormat.PICKLE or (
                format_type is None and serialized_data is None
            ):
                try:
                    serialized_data = pickle.loads(decompressed_data)
                except pickle.PickleError:
                    if format_type == SerializationFormat.PICKLE:
                        raise SerializationError("Failed to parse pickle data")
                    serialized_data = None

            if serialized_data is None:
                raise SerializationError("Could not detect or parse serialization format")

            # Extract actual data
            if isinstance(serialized_data, dict) and "data" in serialized_data:
                actual_data = serialized_data["data"]
            else:
                # Legacy format without metadata wrapper
                actual_data = serialized_data

            # Deserialize to target type
            if target_type in self._deserializers:
                return self._deserializers[target_type](actual_data)
            elif hasattr(target_type, "from_dict"):
                return target_type.from_dict(actual_data)
            elif isinstance(actual_data, target_type):
                return actual_data
            else:
                # Try direct instantiation
                return target_type(actual_data)

        except Exception as e:
            raise SerializationError(f"Deserialization failed: {e}") from e

    def serialize_to_file(
        self,
        obj: Any,
        file_path: Union[str, Path],
        format_type: Optional[str] = None,
        compression: Optional[str] = None,
    ) -> None:
        """
        Serialize an object and save to file.

        Args:
            obj: Object to serialize
            file_path: Path to save the serialized data
            format_type: Serialization format (defaults to instance default)
            compression: Compression type (defaults to instance default)

        Raises:
            SerializationError: If serialization or file writing fails
        """
        try:
            serialized_data = self.serialize(obj, format_type, compression)

            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "wb") as f:
                f.write(serialized_data)

        except Exception as e:
            raise SerializationError(f"Failed to serialize to file {file_path}: {e}") from e

    def deserialize_from_file(
        self,
        file_path: Union[str, Path],
        target_type: Type[T],
        format_type: Optional[str] = None,
        compression: Optional[str] = None,
    ) -> T:
        """
        Deserialize an object from file.

        Args:
            file_path: Path to the serialized data file
            target_type: Type to deserialize to
            format_type: Serialization format (auto-detected if None)
            compression: Compression type (auto-detected if None)

        Returns:
            Deserialized object of target_type

        Raises:
            SerializationError: If file reading or deserialization fails
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                raise SerializationError(f"File not found: {file_path}")

            with open(file_path, "rb") as f:
                serialized_data = f.read()

            return self.deserialize(serialized_data, target_type, format_type, compression)

        except Exception as e:
            raise SerializationError(f"Failed to deserialize from file {file_path}: {e}") from e

    def calculate_checksum(self, data: bytes) -> str:
        """
        Calculate SHA-256 checksum for data.

        Args:
            data: Data to calculate checksum for

        Returns:
            Hexadecimal checksum string
        """
        return hashlib.sha256(data).hexdigest()

    def verify_checksum(self, data: bytes, expected_checksum: str) -> bool:
        """
        Verify data against expected checksum.

        Args:
            data: Data to verify
            expected_checksum: Expected checksum value

        Returns:
            True if checksums match, False otherwise
        """
        actual_checksum = self.calculate_checksum(data)
        return actual_checksum == expected_checksum

    def _compress_data(self, data: bytes, compression: str) -> bytes:
        """Compress data using the specified compression type."""
        if compression == CompressionType.NONE:
            return data
        elif compression == CompressionType.GZIP:
            return gzip.compress(data)
        elif compression == CompressionType.BZ2:
            return bz2.compress(data)
        elif compression == CompressionType.LZMA:
            return lzma.compress(data)
        else:
            raise SerializationError(f"Unsupported compression type: {compression}")

    def _decompress_data(self, data: bytes, compression: str) -> bytes:
        """Decompress data using the specified compression type."""
        if compression == CompressionType.NONE:
            return data
        elif compression == CompressionType.GZIP:
            return gzip.decompress(data)
        elif compression == CompressionType.BZ2:
            return bz2.decompress(data)
        elif compression == CompressionType.LZMA:
            return lzma.decompress(data)
        else:
            raise SerializationError(f"Unsupported compression type: {compression}")

    def _auto_decompress(self, data: bytes) -> bytes:
        """Attempt to auto-detect and decompress data."""
        # Try different compression formats
        for compression in [CompressionType.GZIP, CompressionType.BZ2, CompressionType.LZMA]:
            try:
                return self._decompress_data(data, compression)
            except Exception:
                continue

        # If no compression worked, return original data
        return data

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for non-standard types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "to_dict"):
            return obj.to_dict()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        else:
            return str(obj)

    # Custom serializers for specific model types
    def _serialize_backup_data(self, obj: BackupData) -> Dict[str, Any]:
        """Serialize BackupData object."""
        return obj.to_dict()

    def _serialize_backup_metadata(self, obj: BackupMetadata) -> Dict[str, Any]:
        """Serialize BackupMetadata object."""
        return obj.to_dict()

    def _serialize_backup_options(self, obj: BackupOptions) -> Dict[str, Any]:
        """Serialize BackupOptions object."""
        return obj.to_dict()

    def _serialize_restore_options(self, obj: RestoreOptions) -> Dict[str, Any]:
        """Serialize RestoreOptions object."""
        return obj.to_dict()

    def _serialize_user_data(self, obj: UserData) -> Dict[str, Any]:
        """Serialize UserData object."""
        return obj.to_dict()

    def _serialize_group_data(self, obj: GroupData) -> Dict[str, Any]:
        """Serialize GroupData object."""
        return obj.to_dict()

    def _serialize_permission_set_data(self, obj: PermissionSetData) -> Dict[str, Any]:
        """Serialize PermissionSetData object."""
        return obj.to_dict()

    def _serialize_assignment_data(self, obj: AssignmentData) -> Dict[str, Any]:
        """Serialize AssignmentData object."""
        return obj.to_dict()

    def _serialize_validation_result(self, obj: ValidationResult) -> Dict[str, Any]:
        """Serialize ValidationResult object."""
        return obj.to_dict()

    def _serialize_backup_result(self, obj: BackupResult) -> Dict[str, Any]:
        """Serialize BackupResult object."""
        return obj.to_dict()

    def _serialize_restore_result(self, obj: RestoreResult) -> Dict[str, Any]:
        """Serialize RestoreResult object."""
        return obj.to_dict()

    def _serialize_retention_policy(self, obj: RetentionPolicy) -> Dict[str, Any]:
        """Serialize RetentionPolicy object."""
        return obj.to_dict()

    def _serialize_encryption_metadata(self, obj: EncryptionMetadata) -> Dict[str, Any]:
        """Serialize EncryptionMetadata object."""
        return obj.to_dict()

    def _serialize_schedule_config(self, obj: ScheduleConfig) -> Dict[str, Any]:
        """Serialize ScheduleConfig object."""
        return obj.to_dict()

    def _serialize_notification_settings(self, obj: NotificationSettings) -> Dict[str, Any]:
        """Serialize NotificationSettings object."""
        return obj.to_dict()

    def _serialize_export_format(self, obj: ExportFormat) -> Dict[str, Any]:
        """Serialize ExportFormat object."""
        return obj.to_dict()

    def _serialize_import_source(self, obj: ImportSource) -> Dict[str, Any]:
        """Serialize ImportSource object."""
        return obj.to_dict()


# Convenience functions for common serialization tasks
def serialize_backup_data(
    backup_data: BackupData,
    format_type: str = SerializationFormat.JSON,
    compression: str = CompressionType.GZIP,
) -> bytes:
    """
    Convenience function to serialize BackupData.

    Args:
        backup_data: BackupData object to serialize
        format_type: Serialization format
        compression: Compression type

    Returns:
        Serialized bytes
    """
    serializer = DataSerializer()
    return serializer.serialize(backup_data, format_type, compression)


def deserialize_backup_data(
    data: bytes, format_type: Optional[str] = None, compression: Optional[str] = None
) -> BackupData:
    """
    Convenience function to deserialize BackupData.

    Args:
        data: Serialized bytes
        format_type: Serialization format (auto-detected if None)
        compression: Compression type (auto-detected if None)

    Returns:
        Deserialized BackupData object
    """
    serializer = DataSerializer()
    return serializer.deserialize(data, BackupData, format_type, compression)


def save_backup_to_file(
    backup_data: BackupData,
    file_path: Union[str, Path],
    format_type: str = SerializationFormat.JSON,
    compression: str = CompressionType.GZIP,
) -> None:
    """
    Convenience function to save BackupData to file.

    Args:
        backup_data: BackupData object to save
        file_path: Path to save the file
        format_type: Serialization format
        compression: Compression type
    """
    serializer = DataSerializer()
    serializer.serialize_to_file(backup_data, file_path, format_type, compression)


def load_backup_from_file(
    file_path: Union[str, Path],
    format_type: Optional[str] = None,
    compression: Optional[str] = None,
) -> BackupData:
    """
    Convenience function to load BackupData from file.

    Args:
        file_path: Path to the backup file
        format_type: Serialization format (auto-detected if None)
        compression: Compression type (auto-detected if None)

    Returns:
        Loaded BackupData object
    """
    serializer = DataSerializer()
    return serializer.deserialize_from_file(file_path, BackupData, format_type, compression)


class BackupSerializer:
    """
    Simplified serializer specifically for BackupData objects.

    This class provides a simple interface for serializing and deserializing
    BackupData objects, used by the storage engine.
    """

    def __init__(self):
        """Initialize the backup serializer."""
        self.data_serializer = DataSerializer()

    async def serialize(self, backup_data: BackupData) -> bytes:
        """
        Serialize BackupData to bytes.

        Args:
            backup_data: BackupData object to serialize

        Returns:
            Serialized bytes
        """
        return self.data_serializer.serialize(backup_data)

    async def deserialize(self, data: bytes) -> BackupData:
        """
        Deserialize bytes to BackupData.

        Args:
            data: Serialized bytes

        Returns:
            Deserialized BackupData object
        """
        return self.data_serializer.deserialize(data, BackupData)
