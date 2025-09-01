"""
Local metadata index for managing backup metadata across all storage backends.

This module provides a unified metadata index that stores backup information
locally, enabling consistent operations across filesystem and S3 storage
without requiring users to specify storage backend details.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import BackupMetadata

logger = logging.getLogger(__name__)


class LocalMetadataIndex:
    """
    Local metadata index for managing backup metadata across storage backends.

    This class maintains a local index of all backup metadata, enabling:
    - Unified listing of backups across storage backends
    - Fast metadata queries without remote API calls
    - Consistent operations regardless of storage location
    - Offline access to backup information
    """

    def __init__(self, index_path: str = None, profile: Optional[str] = None):
        """
        Initialize the local metadata index.

        Args:
            index_path: Path to store the metadata index (defaults to ~/.awsideman/metadata)
            profile: AWS profile name for isolation
        """
        if index_path is None:
            from awsideman.utils.config import CONFIG_DIR

            self.index_path = Path(CONFIG_DIR) / "metadata"
        else:
            self.index_path = Path(index_path)

        # Add profile isolation
        profile_name = profile or "default"
        self.index_path = self.index_path / "profiles" / profile_name

        self.index_path.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.index_path / "backup_index.json"
        self.storage_locations_file = self.index_path / "storage_locations.json"

        # Initialize index files if they don't exist
        self._initialize_index_files()

    def _initialize_index_files(self):
        """Initialize index files with default structure."""
        if not self.metadata_file.exists():
            self._save_metadata_index({})

        if not self.storage_locations_file.exists():
            self._save_storage_locations({})

    def _load_metadata_index(self) -> Dict[str, Any]:
        """Load the metadata index from disk."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, "r") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Failed to load metadata index: {e}")
            return {}

    def _save_metadata_index(self, index: Dict[str, Any]):
        """Save the metadata index to disk."""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(index, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metadata index: {e}")

    def _load_storage_locations(self) -> Dict[str, Dict[str, str]]:
        """Load storage location mappings from disk."""
        try:
            if self.storage_locations_file.exists():
                with open(self.storage_locations_file, "r") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Failed to load storage locations: {e}")
            return {}

    def _save_storage_locations(self, locations: Dict[str, Dict[str, str]]):
        """Save storage location mappings to disk."""
        try:
            with open(self.storage_locations_file, "w") as f:
                json.dump(locations, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save storage locations: {e}")

    def add_backup_metadata(
        self, backup_id: str, metadata: BackupMetadata, storage_backend: str, storage_location: str
    ):
        """
        Add or update backup metadata in the local index.

        Args:
            backup_id: Unique backup identifier
            metadata: Backup metadata object
            storage_backend: Storage backend type ('filesystem' or 's3')
            storage_location: Storage-specific location (path or bucket/prefix)
        """
        try:
            # Load current index
            index = self._load_metadata_index()
            locations = self._load_storage_locations()

            # Add metadata to index
            index[backup_id] = metadata.to_dict()

            # Add storage location mapping
            locations[backup_id] = {
                "backend": storage_backend,
                "location": storage_location,
                "added_at": datetime.now().isoformat(),
                "last_verified": datetime.now().isoformat(),
            }

            # Save updated index
            self._save_metadata_index(index)
            self._save_storage_locations(locations)

            logger.debug(f"Added backup {backup_id} to local metadata index")

        except Exception as e:
            logger.error(f"Failed to add backup {backup_id} to metadata index: {e}")

    def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Get backup metadata from local index.

        Args:
            backup_id: Unique backup identifier

        Returns:
            BackupMetadata if found, None otherwise
        """
        try:
            index = self._load_metadata_index()
            if backup_id in index:
                metadata_dict = index[backup_id]
                return BackupMetadata.from_dict(metadata_dict)
            return None
        except Exception as e:
            logger.error(f"Failed to get backup {backup_id} from metadata index: {e}")
            return None

    def get_storage_location(self, backup_id: str) -> Optional[Dict[str, str]]:
        """
        Get storage location information for a backup.

        Args:
            backup_id: Unique backup identifier

        Returns:
            Storage location dict with 'backend' and 'location' keys, or None
        """
        try:
            locations = self._load_storage_locations()
            return locations.get(backup_id)
        except Exception as e:
            logger.error(f"Failed to get storage location for {backup_id}: {e}")
            return None

    def list_backups(self, filters: Optional[Dict[str, Any]] = None) -> List[BackupMetadata]:
        """
        List all backups from local index with optional filtering.

        Args:
            filters: Optional filters to apply

        Returns:
            List of BackupMetadata objects
        """
        try:
            index = self._load_metadata_index()
            backups = []

            for backup_id, metadata_dict in index.items():
                try:
                    metadata = BackupMetadata.from_dict(metadata_dict)

                    # Apply filters if specified
                    if filters:
                        if not self._matches_filters(metadata, filters):
                            continue

                    backups.append(metadata)

                except Exception as e:
                    logger.warning(f"Failed to parse metadata for {backup_id}: {e}")
                    continue

            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x.timestamp, reverse=True)

            return backups

        except Exception as e:
            logger.error(f"Failed to list backups from metadata index: {e}")
            return []

    def _matches_filters(self, metadata: BackupMetadata, filters: Dict[str, Any]) -> bool:
        """Check if metadata matches the specified filters."""
        try:
            for filter_key, filter_value in filters.items():
                if filter_key == "since_date":
                    if metadata.timestamp < filter_value:
                        return False
                elif filter_key == "backup_type":
                    if metadata.backup_type.value != filter_value:
                        return False
                elif filter_key == "storage_backend":
                    # This would require checking storage locations
                    storage_info = self.get_storage_location(metadata.backup_id)
                    if not storage_info or storage_info.get("backend") != filter_value:
                        return False
                # Add more filter types as needed

            return True

        except Exception as e:
            logger.warning(f"Filter matching failed: {e}")
            return False

    def remove_backup_metadata(self, backup_id: str):
        """
        Remove backup metadata from local index.

        Args:
            backup_id: Unique backup identifier to remove
        """
        try:
            # Load current index
            index = self._load_metadata_index()
            locations = self._load_storage_locations()

            # Remove from both indexes
            if backup_id in index:
                del index[backup_id]
            if backup_id in locations:
                del locations[backup_id]

            # Save updated indexes
            self._save_metadata_index(index)
            self._save_storage_locations(locations)

            logger.debug(f"Removed backup {backup_id} from local metadata index")

        except Exception as e:
            logger.error(f"Failed to remove backup {backup_id} from metadata index: {e}")

    def sync_with_storage_backend(self, storage_backend, storage_location: str = ""):
        """
        Sync local index with a storage backend to ensure consistency.

        Args:
            storage_backend: Storage backend instance to sync with
            storage_location: Storage-specific location identifier
        """
        try:
            logger.info(f"Syncing local metadata index with {storage_backend.__class__.__name__}")

            # Get backups from storage backend
            import asyncio

            from .storage import StorageEngine

            storage_engine = StorageEngine(backend=storage_backend)

            # List backups from storage
            remote_backups = asyncio.run(storage_engine.list_backups())

            # Update local index
            for backup_metadata in remote_backups:
                self.add_backup_metadata(
                    backup_metadata.backup_id,
                    backup_metadata,
                    storage_backend.__class__.__name__.lower().replace("storagebackend", ""),
                    storage_location,
                )

            logger.info(f"Synced {len(remote_backups)} backups from storage backend")

        except Exception as e:
            logger.error(f"Failed to sync with storage backend: {e}")

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the local metadata index."""
        try:
            index = self._load_metadata_index()
            locations = self._load_storage_locations()

            # Count by storage backend
            backend_counts = {}
            for location_info in locations.values():
                backend = location_info.get("backend", "unknown")
                backend_counts[backend] = backend_counts.get(backend, 0) + 1

            # Count by backup type
            type_counts = {}
            for backup_id, metadata_dict in index.items():
                try:
                    backup_type = metadata_dict.get("backup_type", "unknown")
                    type_counts[backup_type] = type_counts.get(backup_type, 0) + 1
                except Exception:
                    type_counts["unknown"] = type_counts.get("unknown", 0) + 1

            return {
                "total_backups": len(index),
                "by_backend": backend_counts,
                "by_type": type_counts,
                "index_size_bytes": (
                    self.metadata_file.stat().st_size if self.metadata_file.exists() else 0
                ),
                "last_updated": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {"error": str(e)}

    def cleanup_orphaned_entries(self):
        """Remove metadata entries that no longer exist in storage."""
        try:
            index = self._load_metadata_index()
            locations = self._load_storage_locations()

            orphaned_ids = []

            for backup_id in index.keys():
                storage_info = locations.get(backup_id)
                if not storage_info:
                    orphaned_ids.append(backup_id)
                    continue

                # Check if backup still exists in storage
                # This would require backend-specific verification
                # For now, we'll just log potential orphans
                logger.debug(f"Backup {backup_id} storage info: {storage_info}")

            if orphaned_ids:
                logger.info(f"Found {len(orphaned_ids)} potentially orphaned backup entries")
                # Could implement automatic cleanup here if desired

        except Exception as e:
            logger.error(f"Failed to cleanup orphaned entries: {e}")


# Global instance for easy access
_global_index: Optional[LocalMetadataIndex] = None


def get_global_metadata_index() -> LocalMetadataIndex:
    """Get the global metadata index instance."""
    global _global_index
    if _global_index is None:
        _global_index = LocalMetadataIndex()
    return _global_index
