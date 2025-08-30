"""
Base interfaces for backup and restore system components.

This module defines the abstract interfaces that all backup-restore components
must implement, ensuring consistent behavior and enabling dependency injection.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupResult,
    ExportFormat,
    GroupData,
    ImportSource,
    PermissionSetData,
    RestoreOptions,
    RestorePreview,
    RestoreResult,
    ScheduleConfig,
    UserData,
    ValidationResult,
)


class BackupManagerInterface(ABC):
    """Interface for backup management operations."""

    @abstractmethod
    async def create_backup(self, options: BackupOptions) -> BackupResult:
        """
        Create a new backup with the specified options.

        Args:
            options: Configuration options for the backup operation

        Returns:
            BackupResult containing the outcome of the backup operation
        """
        pass

    @abstractmethod
    async def list_backups(self, filters: Optional[Dict[str, Any]] = None) -> List[BackupMetadata]:
        """
        List available backups with optional filtering.

        Args:
            filters: Optional filters to apply to the backup list

        Returns:
            List of backup metadata objects
        """
        pass

    @abstractmethod
    async def validate_backup(self, backup_id: str) -> ValidationResult:
        """
        Validate the integrity and completeness of a backup.

        Args:
            backup_id: Unique identifier of the backup to validate

        Returns:
            ValidationResult containing validation status and details
        """
        pass

    @abstractmethod
    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a backup and all associated data.

        Args:
            backup_id: Unique identifier of the backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Retrieve metadata for a specific backup.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupMetadata if found, None otherwise
        """
        pass


class RestoreManagerInterface(ABC):
    """Interface for restore management operations."""

    @abstractmethod
    async def restore_backup(self, backup_id: str, options: RestoreOptions) -> RestoreResult:
        """
        Restore a backup with the specified options.

        Args:
            backup_id: Unique identifier of the backup to restore
            options: Configuration options for the restore operation

        Returns:
            RestoreResult containing the outcome of the restore operation
        """
        pass

    @abstractmethod
    async def preview_restore(self, backup_id: str, options: RestoreOptions) -> RestorePreview:
        """
        Preview the changes that would be made by a restore operation.

        Args:
            backup_id: Unique identifier of the backup to preview
            options: Configuration options for the restore operation

        Returns:
            RestorePreview containing details of planned changes
        """
        pass

    @abstractmethod
    async def validate_compatibility(
        self, backup_id: str, target_instance_arn: str
    ) -> ValidationResult:
        """
        Validate compatibility between a backup and target environment.

        Args:
            backup_id: Unique identifier of the backup
            target_instance_arn: ARN of the target Identity Center instance

        Returns:
            ValidationResult containing compatibility status and details
        """
        pass


class StorageEngineInterface(ABC):
    """Interface for backup storage operations."""

    @abstractmethod
    async def store_backup(self, backup_data: BackupData) -> str:
        """
        Store backup data and return a unique identifier.

        Args:
            backup_data: Complete backup data to store

        Returns:
            Unique identifier for the stored backup
        """
        pass

    @abstractmethod
    async def retrieve_backup(self, backup_id: str) -> Optional[BackupData]:
        """
        Retrieve backup data by identifier.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupData if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_backups(self, filters: Optional[Dict[str, Any]] = None) -> List[BackupMetadata]:
        """
        List stored backups with optional filtering.

        Args:
            filters: Optional filters to apply to the backup list

        Returns:
            List of backup metadata objects
        """
        pass

    @abstractmethod
    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete stored backup data.

        Args:
            backup_id: Unique identifier of the backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    async def verify_integrity(self, backup_id: str) -> ValidationResult:
        """
        Verify the integrity of stored backup data.

        Args:
            backup_id: Unique identifier of the backup to verify

        Returns:
            ValidationResult containing integrity status and details
        """
        pass

    @abstractmethod
    async def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about storage usage and capacity.

        Returns:
            Dictionary containing storage information
        """
        pass

    @abstractmethod
    async def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Get metadata for a specific backup.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupMetadata if found, None otherwise
        """
        pass


class CollectorInterface(ABC):
    """Interface for collecting Identity Center data."""

    @abstractmethod
    async def collect_users(self, options: BackupOptions) -> List[UserData]:
        """
        Collect user data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of user data objects
        """
        pass

    @abstractmethod
    async def collect_groups(self, options: BackupOptions) -> List[GroupData]:
        """
        Collect group data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of group data objects
        """
        pass

    @abstractmethod
    async def collect_permission_sets(self, options: BackupOptions) -> List[PermissionSetData]:
        """
        Collect permission set data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of permission set data objects
        """
        pass

    @abstractmethod
    async def collect_assignments(self, options: BackupOptions) -> List[AssignmentData]:
        """
        Collect assignment data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of assignment data objects
        """
        pass

    @abstractmethod
    async def collect_incremental(self, since: datetime, options: BackupOptions) -> BackupData:
        """
        Collect only data that has changed since the specified timestamp.

        Args:
            since: Timestamp to collect changes from
            options: Backup options that may affect collection behavior

        Returns:
            BackupData containing only changed resources
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> ValidationResult:
        """
        Validate connection to Identity Center and required permissions.

        Returns:
            ValidationResult containing connection status and details
        """
        pass

    @abstractmethod
    async def validate_cross_account_access(
        self, cross_account_configs: List[Any]
    ) -> ValidationResult:
        """
        Validate cross-account access configurations.

        Args:
            cross_account_configs: List of cross-account configuration objects

        Returns:
            ValidationResult containing validation status and details
        """
        pass

    @abstractmethod
    async def collect_cross_account_data(self, options: BackupOptions) -> Dict[str, BackupData]:
        """
        Collect data from multiple accounts using cross-account configurations.

        Args:
            options: Backup options including cross-account configurations

        Returns:
            Dictionary mapping account IDs to their backup data
        """
        pass


class ExportImportManagerInterface(ABC):
    """Interface for export and import operations."""

    @abstractmethod
    async def export_backup(
        self, backup_id: str, format_config: ExportFormat, target_path: str
    ) -> bool:
        """
        Export a backup to the specified format and location.

        Args:
            backup_id: Unique identifier of the backup to export
            format_config: Configuration for the export format
            target_path: Path where the exported data should be saved

        Returns:
            True if export was successful, False otherwise
        """
        pass

    @abstractmethod
    async def import_backup(self, source: ImportSource, format_config: ExportFormat) -> str:
        """
        Import backup data from an external source.

        Args:
            source: Configuration for the import source
            format_config: Configuration for the import format

        Returns:
            Unique identifier of the imported backup
        """
        pass

    @abstractmethod
    async def validate_import_format(
        self, source: ImportSource, format_config: ExportFormat
    ) -> ValidationResult:
        """
        Validate the format and structure of import data.

        Args:
            source: Configuration for the import source
            format_config: Configuration for the import format

        Returns:
            ValidationResult containing format validation status and details
        """
        pass

    @abstractmethod
    async def convert_format(
        self, backup_id: str, from_format: ExportFormat, to_format: ExportFormat
    ) -> str:
        """
        Convert backup data from one format to another.

        Args:
            backup_id: Unique identifier of the backup to convert
            from_format: Source format configuration
            to_format: Target format configuration

        Returns:
            Path to the converted data
        """
        pass


class ScheduleManagerInterface(ABC):
    """Interface for backup scheduling operations."""

    @abstractmethod
    async def create_schedule(self, schedule_config: ScheduleConfig) -> str:
        """
        Create a new backup schedule.

        Args:
            schedule_config: Configuration for the backup schedule

        Returns:
            Unique identifier of the created schedule
        """
        pass

    @abstractmethod
    async def update_schedule(self, schedule_id: str, schedule_config: ScheduleConfig) -> bool:
        """
        Update an existing backup schedule.

        Args:
            schedule_id: Unique identifier of the schedule to update
            schedule_config: New configuration for the schedule

        Returns:
            True if update was successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_schedule(self, schedule_id: str) -> bool:
        """
        Delete a backup schedule.

        Args:
            schedule_id: Unique identifier of the schedule to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    async def list_schedules(self) -> List[Dict[str, Any]]:
        """
        List all backup schedules.

        Returns:
            List of schedule information dictionaries
        """
        pass

    @abstractmethod
    async def execute_scheduled_backup(self, schedule_id: str) -> BackupResult:
        """
        Execute a backup for the specified schedule.

        Args:
            schedule_id: Unique identifier of the schedule to execute

        Returns:
            BackupResult containing the outcome of the backup operation
        """
        pass

    @abstractmethod
    async def get_schedule_status(self, schedule_id: str) -> Dict[str, Any]:
        """
        Get the status and execution history of a schedule.

        Args:
            schedule_id: Unique identifier of the schedule

        Returns:
            Dictionary containing schedule status information
        """
        pass


class StorageBackendInterface(ABC):
    """Base interface for storage backend implementations."""

    @abstractmethod
    async def write_data(self, key: str, data: bytes) -> bool:
        """
        Write data to storage.

        Args:
            key: Storage key/path for the data
            data: Raw data to store

        Returns:
            True if write was successful, False otherwise
        """
        pass

    @abstractmethod
    async def read_data(self, key: str) -> Optional[bytes]:
        """
        Read data from storage.

        Args:
            key: Storage key/path for the data

        Returns:
            Raw data if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete_data(self, key: str) -> bool:
        """
        Delete data from storage.

        Args:
            key: Storage key/path for the data to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """
        List available keys in storage.

        Args:
            prefix: Optional prefix to filter keys

        Returns:
            List of storage keys
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if data exists at the specified key.

        Args:
            key: Storage key/path to check

        Returns:
            True if data exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for stored data.

        Args:
            key: Storage key/path for the data

        Returns:
            Metadata dictionary if found, None otherwise
        """
        pass


class EncryptionProviderInterface(ABC):
    """Interface for encryption operations."""

    @abstractmethod
    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data using the specified key.

        Args:
            data: Raw data to encrypt
            key_id: Optional key identifier to use for encryption

        Returns:
            Tuple of (encrypted_data, encryption_metadata)
        """
        pass

    @abstractmethod
    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Decrypt data using the provided metadata.

        Args:
            encrypted_data: Encrypted data to decrypt
            encryption_metadata: Metadata needed for decryption

        Returns:
            Decrypted raw data
        """
        pass

    @abstractmethod
    async def generate_key(self) -> str:
        """
        Generate a new encryption key.

        Returns:
            Key identifier for the generated key
        """
        pass

    @abstractmethod
    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate an encryption key.

        Args:
            old_key_id: Identifier of the key to rotate

        Returns:
            Identifier of the new key
        """
        pass


class ProgressReporterInterface(ABC):
    """Interface for reporting operation progress."""

    @abstractmethod
    async def start_operation(self, operation_id: str, total_steps: int, description: str) -> None:
        """
        Start tracking progress for an operation.

        Args:
            operation_id: Unique identifier for the operation
            total_steps: Total number of steps in the operation
            description: Human-readable description of the operation
        """
        pass

    @abstractmethod
    async def update_progress(
        self, operation_id: str, completed_steps: int, message: Optional[str] = None
    ) -> None:
        """
        Update progress for an operation.

        Args:
            operation_id: Unique identifier for the operation
            completed_steps: Number of completed steps
            message: Optional progress message
        """
        pass

    @abstractmethod
    async def complete_operation(
        self, operation_id: str, success: bool, message: Optional[str] = None
    ) -> None:
        """
        Mark an operation as complete.

        Args:
            operation_id: Unique identifier for the operation
            success: Whether the operation completed successfully
            message: Optional completion message
        """
        pass

    @abstractmethod
    async def get_progress(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current progress for an operation.

        Args:
            operation_id: Unique identifier for the operation

        Returns:
            Progress information dictionary if found, None otherwise
        """
        pass


class CompressionProviderInterface(ABC):
    """Interface for compression providers."""

    @abstractmethod
    async def compress(self, data: bytes, algorithm: Optional[str] = None) -> Any:
        """
        Compress data using the specified or default algorithm.

        Args:
            data: Data to compress
            algorithm: Compression algorithm to use

        Returns:
            Compression result with compressed data and metadata
        """
        pass

    @abstractmethod
    async def decompress(self, data: bytes, algorithm: str) -> bytes:
        """
        Decompress data using the specified algorithm.

        Args:
            data: Compressed data
            algorithm: Algorithm used for compression

        Returns:
            Decompressed data
        """
        pass

    @abstractmethod
    def get_best_algorithm(self, data_sample: bytes) -> str:
        """
        Determine the best compression algorithm for given data.

        Args:
            data_sample: Sample of data to analyze

        Returns:
            Best algorithm name
        """
        pass

    @abstractmethod
    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        pass


class DeduplicationProviderInterface(ABC):
    """Interface for deduplication providers."""

    @abstractmethod
    async def deduplicate(self, data: bytes) -> Any:
        """
        Deduplicate data by identifying and removing duplicate blocks.

        Args:
            data: Data to deduplicate

        Returns:
            Deduplication result with deduplicated data and metadata
        """
        pass

    @abstractmethod
    async def rehydrate(self, deduplicated_data: bytes) -> bytes:
        """
        Rehydrate deduplicated data back to original form.

        Args:
            deduplicated_data: Deduplicated data to rehydrate

        Returns:
            Original data
        """
        pass

    @abstractmethod
    def clear_cache(self) -> None:
        """Clear the deduplication cache."""
        pass

    @abstractmethod
    def get_deduplication_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        pass


class PerformanceOptimizerInterface(ABC):
    """Interface for performance optimization coordination."""

    @abstractmethod
    async def optimize_backup_data(self, backup_data: Any) -> tuple[bytes, Dict[str, Any]]:
        """
        Optimize backup data using all enabled optimization techniques.

        Args:
            backup_data: Backup data to optimize

        Returns:
            Tuple of (optimized_data, optimization_metadata)
        """
        pass

    @abstractmethod
    async def restore_optimized_data(
        self, optimized_data: bytes, optimization_metadata: Dict[str, Any]
    ) -> Any:
        """
        Restore optimized data back to original BackupData.

        Args:
            optimized_data: Optimized data to restore
            optimization_metadata: Metadata about applied optimizations

        Returns:
            Original BackupData
        """
        pass

    @abstractmethod
    def get_performance_metrics(self) -> List[Any]:
        """Get collected performance metrics."""
        pass

    @abstractmethod
    async def process_parallel_collection(
        self, collection_tasks: List[Any], *args: Any, **kwargs: Any
    ) -> List[Any]:
        """
        Process data collection tasks in parallel.

        Args:
            collection_tasks: List of collection functions to execute
            *args: Additional arguments for collection functions
            **kwargs: Additional keyword arguments for collection functions

        Returns:
            List of collection results
        """
        pass

    @abstractmethod
    def get_resource_usage(self, duration: Optional[Any] = None) -> Dict[str, Any]:
        """
        Get resource usage statistics.

        Args:
            duration: Optional duration to analyze

        Returns:
            Resource usage statistics
        """
        pass

    @abstractmethod
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get optimization statistics from all components."""
        pass

    @abstractmethod
    def clear_caches(self) -> None:
        """Clear all optimization caches."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the performance optimizer."""
        pass
