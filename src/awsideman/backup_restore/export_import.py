"""
Export and import manager for backup data portability.

This module provides comprehensive export and import capabilities for backup data,
supporting multiple formats (JSON, YAML, CSV) with streaming, validation, and
audit trail functionality.
"""

import csv
import json
import logging
import uuid
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, TextIO

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .interfaces import ExportImportManagerInterface, StorageEngineInterface
from .models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    ExportFormat,
    GroupData,
    ImportSource,
    PermissionSetData,
    UserData,
    ValidationResult,
)
from .serialization import DataSerializer

logger = logging.getLogger(__name__)


class ExportImportError(Exception):
    """Custom exception for export/import operations."""

    pass


class AuditLogger:
    """Audit logger for export/import operations."""

    def __init__(self):
        """Initialize the audit logger."""
        self.audit_log = logging.getLogger(f"{__name__}.audit")

    async def log_export_start(
        self, operation_id: str, backup_id: str, format_config: ExportFormat, target_path: str
    ) -> None:
        """Log the start of an export operation."""
        self.audit_log.info(
            "Export operation started",
            extra={
                "operation_id": operation_id,
                "operation_type": "export",
                "backup_id": backup_id,
                "format": format_config.format_type,
                "target_path": target_path,
                "timestamp": datetime.now().isoformat(),
                "compression": format_config.compression,
                "encryption": format_config.encryption,
            },
        )

    async def log_export_complete(
        self,
        operation_id: str,
        success: bool,
        file_size: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log the completion of an export operation."""
        self.audit_log.info(
            "Export operation completed",
            extra={
                "operation_id": operation_id,
                "operation_type": "export",
                "success": success,
                "file_size": file_size,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def log_import_start(
        self, operation_id: str, source: ImportSource, format_config: ExportFormat
    ) -> None:
        """Log the start of an import operation."""
        self.audit_log.info(
            "Import operation started",
            extra={
                "operation_id": operation_id,
                "operation_type": "import",
                "source_type": source.source_type,
                "source_location": source.location,
                "format": format_config.format_type,
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def log_import_complete(
        self,
        operation_id: str,
        success: bool,
        backup_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log the completion of an import operation."""
        self.audit_log.info(
            "Import operation completed",
            extra={
                "operation_id": operation_id,
                "operation_type": "import",
                "success": success,
                "backup_id": backup_id,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            },
        )


class FormatConverter:
    """Handles conversion between different export formats."""

    def __init__(self):
        """Initialize the format converter."""
        self.serializer = DataSerializer()

    async def convert_to_json(self, backup_data: BackupData, pretty_print: bool = True) -> str:
        """
        Convert backup data to JSON format.

        Args:
            backup_data: Backup data to convert
            pretty_print: Whether to format JSON with indentation

        Returns:
            JSON string representation
        """
        data_dict = backup_data.to_dict()

        if pretty_print:
            return json.dumps(
                data_dict, indent=2, default=self._json_serializer, ensure_ascii=False
            )
        else:
            return json.dumps(data_dict, default=self._json_serializer, ensure_ascii=False)

    async def convert_to_yaml(self, backup_data: BackupData) -> str:
        """
        Convert backup data to YAML format.

        Args:
            backup_data: Backup data to convert

        Returns:
            YAML string representation

        Raises:
            ExportImportError: If YAML is not available
        """
        if not YAML_AVAILABLE:
            raise ExportImportError("YAML export requires PyYAML package")

        data_dict = backup_data.to_dict()
        return yaml.dump(data_dict, default_flow_style=False, allow_unicode=True)

    async def convert_to_csv(self, backup_data: BackupData) -> Dict[str, str]:
        """
        Convert backup data to CSV format (multiple files).

        Args:
            backup_data: Backup data to convert

        Returns:
            Dictionary mapping resource type to CSV content
        """
        csv_files = {}

        # Convert users to CSV
        if backup_data.users:
            csv_files["users"] = await self._users_to_csv(backup_data.users)

        # Convert groups to CSV
        if backup_data.groups:
            csv_files["groups"] = await self._groups_to_csv(backup_data.groups)

        # Convert permission sets to CSV
        if backup_data.permission_sets:
            csv_files["permission_sets"] = await self._permission_sets_to_csv(
                backup_data.permission_sets
            )

        # Convert assignments to CSV
        if backup_data.assignments:
            csv_files["assignments"] = await self._assignments_to_csv(backup_data.assignments)

        # Add metadata CSV
        csv_files["metadata"] = await self._metadata_to_csv(backup_data.metadata)

        return csv_files

    async def convert_from_json(self, json_data: str) -> BackupData:
        """
        Convert JSON data to BackupData.

        Args:
            json_data: JSON string to convert

        Returns:
            BackupData object
        """
        try:
            data_dict = json.loads(json_data)
            return BackupData.from_dict(data_dict)
        except json.JSONDecodeError as e:
            raise ExportImportError(f"Invalid JSON format: {e}")

    async def convert_from_yaml(self, yaml_data: str) -> BackupData:
        """
        Convert YAML data to BackupData.

        Args:
            yaml_data: YAML string to convert

        Returns:
            BackupData object

        Raises:
            ExportImportError: If YAML is not available or invalid
        """
        if not YAML_AVAILABLE:
            raise ExportImportError("YAML import requires PyYAML package")

        try:
            data_dict = yaml.safe_load(yaml_data)
            return BackupData.from_dict(data_dict)
        except yaml.YAMLError as e:
            raise ExportImportError(f"Invalid YAML format: {e}")

    async def convert_from_csv(self, csv_files: Dict[str, str]) -> BackupData:
        """
        Convert CSV files to BackupData.

        Args:
            csv_files: Dictionary mapping resource type to CSV content

        Returns:
            BackupData object
        """
        # Parse metadata
        if "metadata" not in csv_files:
            raise ExportImportError("Metadata CSV file is required")

        metadata = await self._csv_to_metadata(csv_files["metadata"])

        # Parse users
        users = []
        if "users" in csv_files:
            users = await self._csv_to_users(csv_files["users"])

        # Parse groups
        groups = []
        if "groups" in csv_files:
            groups = await self._csv_to_groups(csv_files["groups"])

        # Parse permission sets
        permission_sets = []
        if "permission_sets" in csv_files:
            permission_sets = await self._csv_to_permission_sets(csv_files["permission_sets"])

        # Parse assignments
        assignments = []
        if "assignments" in csv_files:
            assignments = await self._csv_to_assignments(csv_files["assignments"])

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
        )

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

    async def _users_to_csv(self, users: List[UserData]) -> str:
        """Convert users to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "user_id",
                "user_name",
                "display_name",
                "email",
                "given_name",
                "family_name",
                "active",
                "external_ids",
            ]
        )

        # Write data
        for user in users:
            writer.writerow(
                [
                    user.user_id,
                    user.user_name,
                    user.display_name or "",
                    user.email or "",
                    user.given_name or "",
                    user.family_name or "",
                    user.active,
                    json.dumps(user.external_ids) if user.external_ids else "",
                ]
            )

        return output.getvalue()

    async def _groups_to_csv(self, groups: List[GroupData]) -> str:
        """Convert groups to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["group_id", "display_name", "description", "members"])

        # Write data
        for group in groups:
            writer.writerow(
                [
                    group.group_id,
                    group.display_name,
                    group.description or "",
                    json.dumps(group.members) if group.members else "",
                ]
            )

        return output.getvalue()

    async def _permission_sets_to_csv(self, permission_sets: List[PermissionSetData]) -> str:
        """Convert permission sets to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "permission_set_arn",
                "name",
                "description",
                "session_duration",
                "relay_state",
                "inline_policy",
                "managed_policies",
                "customer_managed_policies",
                "permissions_boundary",
            ]
        )

        # Write data
        for ps in permission_sets:
            writer.writerow(
                [
                    ps.permission_set_arn,
                    ps.name,
                    ps.description or "",
                    ps.session_duration or "",
                    ps.relay_state or "",
                    ps.inline_policy or "",
                    json.dumps(ps.managed_policies) if ps.managed_policies else "",
                    (
                        json.dumps(ps.customer_managed_policies)
                        if ps.customer_managed_policies
                        else ""
                    ),
                    json.dumps(ps.permissions_boundary) if ps.permissions_boundary else "",
                ]
            )

        return output.getvalue()

    async def _assignments_to_csv(self, assignments: List[AssignmentData]) -> str:
        """Convert assignments to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["account_id", "permission_set_arn", "principal_type", "principal_id"])

        # Write data
        for assignment in assignments:
            writer.writerow(
                [
                    assignment.account_id,
                    assignment.permission_set_arn,
                    assignment.principal_type,
                    assignment.principal_id,
                ]
            )

        return output.getvalue()

    async def _metadata_to_csv(self, metadata: BackupMetadata) -> str:
        """Convert metadata to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["key", "value"])

        # Write data
        metadata_dict = metadata.to_dict()
        for key, value in metadata_dict.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            writer.writerow([key, str(value)])

        return output.getvalue()

    async def _csv_to_users(self, csv_data: str) -> List[UserData]:
        """Convert CSV data to users."""
        users = []
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            external_ids = {}
            if row.get("external_ids"):
                try:
                    external_ids = json.loads(row["external_ids"])
                except json.JSONDecodeError:
                    pass

            users.append(
                UserData(
                    user_id=row["user_id"],
                    user_name=row["user_name"],
                    display_name=row.get("display_name") or None,
                    email=row.get("email") or None,
                    given_name=row.get("given_name") or None,
                    family_name=row.get("family_name") or None,
                    active=row.get("active", "True").lower() == "true",
                    external_ids=external_ids,
                )
            )

        return users

    async def _csv_to_groups(self, csv_data: str) -> List[GroupData]:
        """Convert CSV data to groups."""
        groups = []
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            members = []
            if row.get("members"):
                try:
                    members = json.loads(row["members"])
                except json.JSONDecodeError:
                    pass

            groups.append(
                GroupData(
                    group_id=row["group_id"],
                    display_name=row["display_name"],
                    description=row.get("description") or None,
                    members=members,
                )
            )

        return groups

    async def _csv_to_permission_sets(self, csv_data: str) -> List[PermissionSetData]:
        """Convert CSV data to permission sets."""
        permission_sets = []
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            managed_policies = []
            if row.get("managed_policies"):
                try:
                    managed_policies = json.loads(row["managed_policies"])
                except json.JSONDecodeError:
                    pass

            customer_managed_policies = []
            if row.get("customer_managed_policies"):
                try:
                    customer_managed_policies = json.loads(row["customer_managed_policies"])
                except json.JSONDecodeError:
                    pass

            permissions_boundary = None
            if row.get("permissions_boundary"):
                try:
                    permissions_boundary = json.loads(row["permissions_boundary"])
                except json.JSONDecodeError:
                    pass

            permission_sets.append(
                PermissionSetData(
                    permission_set_arn=row["permission_set_arn"],
                    name=row["name"],
                    description=row.get("description") or None,
                    session_duration=row.get("session_duration") or None,
                    relay_state=row.get("relay_state") or None,
                    inline_policy=row.get("inline_policy") or None,
                    managed_policies=managed_policies,
                    customer_managed_policies=customer_managed_policies,
                    permissions_boundary=permissions_boundary,
                )
            )

        return permission_sets

    async def _csv_to_assignments(self, csv_data: str) -> List[AssignmentData]:
        """Convert CSV data to assignments."""
        assignments = []
        reader = csv.DictReader(StringIO(csv_data))

        for row in reader:
            assignments.append(
                AssignmentData(
                    account_id=row["account_id"],
                    permission_set_arn=row["permission_set_arn"],
                    principal_type=row["principal_type"],
                    principal_id=row["principal_id"],
                )
            )

        return assignments

    async def _csv_to_metadata(self, csv_data: str) -> BackupMetadata:
        """Convert CSV data to metadata."""
        reader = csv.DictReader(StringIO(csv_data))
        metadata_dict = {}

        for row in reader:
            key = row["key"]
            value = row["value"]

            # Try to parse JSON values
            if key in ["retention_policy", "encryption_info", "resource_counts"]:
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass

            metadata_dict[key] = value

        return BackupMetadata.from_dict(metadata_dict)


class StreamingProcessor:
    """Handles streaming operations for large datasets."""

    def __init__(self, chunk_size: int = 1000):
        """
        Initialize the streaming processor.

        Args:
            chunk_size: Number of records to process in each chunk
        """
        self.chunk_size = chunk_size

    async def stream_export(
        self, backup_data: BackupData, format_config: ExportFormat, output_stream: TextIO
    ) -> None:
        """
        Stream export of backup data to avoid memory issues.

        Args:
            backup_data: Backup data to export
            format_config: Export format configuration
            output_stream: Output stream to write to
        """
        if format_config.format_type.upper() == "JSON":
            await self._stream_json_export(backup_data, output_stream)
        elif format_config.format_type.upper() == "YAML":
            await self._stream_yaml_export(backup_data, output_stream)
        elif format_config.format_type.upper() == "CSV":
            await self._stream_csv_export(backup_data, output_stream)
        else:
            raise ExportImportError(
                f"Streaming not supported for format: {format_config.format_type}"
            )

    async def stream_import(
        self, input_stream: TextIO, format_config: ExportFormat
    ) -> AsyncIterator[BackupData]:
        """
        Stream import of backup data to avoid memory issues.

        Args:
            input_stream: Input stream to read from
            format_config: Import format configuration

        Yields:
            Chunks of BackupData
        """
        if format_config.format_type.upper() == "JSON":
            async for chunk in self._stream_json_import(input_stream):
                yield chunk
        elif format_config.format_type.upper() == "YAML":
            async for chunk in self._stream_yaml_import(input_stream):
                yield chunk
        else:
            raise ExportImportError(
                f"Streaming import not supported for format: {format_config.format_type}"
            )

    async def _stream_json_export(self, backup_data: BackupData, output_stream: TextIO) -> None:
        """Stream JSON export."""
        # Write opening brace and metadata
        output_stream.write("{\n")
        output_stream.write(
            f'  "metadata": {json.dumps(backup_data.metadata.to_dict(), indent=2)},\n'
        )

        # Stream users
        output_stream.write('  "users": [\n')
        for i, user in enumerate(backup_data.users):
            if i > 0:
                output_stream.write(",\n")
            output_stream.write(f"    {json.dumps(user.to_dict(), indent=4)}")
        output_stream.write("\n  ],\n")

        # Stream groups
        output_stream.write('  "groups": [\n')
        for i, group in enumerate(backup_data.groups):
            if i > 0:
                output_stream.write(",\n")
            output_stream.write(f"    {json.dumps(group.to_dict(), indent=4)}")
        output_stream.write("\n  ],\n")

        # Stream permission sets
        output_stream.write('  "permission_sets": [\n')
        for i, ps in enumerate(backup_data.permission_sets):
            if i > 0:
                output_stream.write(",\n")
            output_stream.write(f"    {json.dumps(ps.to_dict(), indent=4)}")
        output_stream.write("\n  ],\n")

        # Stream assignments
        output_stream.write('  "assignments": [\n')
        for i, assignment in enumerate(backup_data.assignments):
            if i > 0:
                output_stream.write(",\n")
            output_stream.write(f"    {json.dumps(assignment.to_dict(), indent=4)}")
        output_stream.write("\n  ],\n")

        # Write remaining fields
        output_stream.write(
            f'  "relationships": {json.dumps(backup_data.relationships.to_dict(), indent=2)},\n'
        )
        output_stream.write(f'  "checksums": {json.dumps(backup_data.checksums, indent=2)}\n')
        output_stream.write("}\n")

    async def _stream_yaml_export(self, backup_data: BackupData, output_stream: TextIO) -> None:
        """Stream YAML export."""
        if not YAML_AVAILABLE:
            raise ExportImportError("YAML export requires PyYAML package")

        # Convert to dict and write as YAML
        data_dict = backup_data.to_dict()
        yaml.dump(data_dict, output_stream, default_flow_style=False, allow_unicode=True)

    async def _stream_csv_export(self, backup_data: BackupData, output_stream: TextIO) -> None:
        """Stream CSV export (writes multiple CSV sections)."""
        converter = FormatConverter()
        csv_files = await converter.convert_to_csv(backup_data)

        for resource_type, csv_content in csv_files.items():
            output_stream.write(f"# {resource_type.upper()}\n")
            output_stream.write(csv_content)
            output_stream.write("\n\n")

    async def _stream_json_import(self, input_stream: TextIO) -> AsyncIterator[BackupData]:
        """Stream JSON import."""
        # For simplicity, read entire JSON and parse
        # In a real implementation, you might use a streaming JSON parser
        content = input_stream.read()
        data_dict = json.loads(content)
        backup_data = BackupData.from_dict(data_dict)
        yield backup_data

    async def _stream_yaml_import(self, input_stream: TextIO) -> AsyncIterator[BackupData]:
        """Stream YAML import."""
        if not YAML_AVAILABLE:
            raise ExportImportError("YAML import requires PyYAML package")

        content = input_stream.read()
        data_dict = yaml.safe_load(content)
        backup_data = BackupData.from_dict(data_dict)
        yield backup_data


class ExportImportManager(ExportImportManagerInterface):
    """
    Manager for export and import operations with comprehensive format support.

    This class provides export and import capabilities for backup data with support
    for multiple formats, streaming operations, validation, and audit logging.
    """

    def __init__(self, storage_engine: StorageEngineInterface):
        """
        Initialize the export/import manager.

        Args:
            storage_engine: Storage engine for backup operations
        """
        self.storage_engine = storage_engine
        self.format_converter = FormatConverter()
        self.streaming_processor = StreamingProcessor()
        self.audit_logger = AuditLogger()
        self.serializer = DataSerializer()

        logger.info("ExportImportManager initialized")

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
        operation_id = str(uuid.uuid4())

        try:
            await self.audit_logger.log_export_start(
                operation_id, backup_id, format_config, target_path
            )

            logger.info(f"Starting export of backup {backup_id} to {target_path}")

            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                raise ExportImportError(f"Backup not found: {backup_id}")

            # Validate backup integrity
            if not backup_data.verify_integrity():
                logger.warning(f"Backup {backup_id} failed integrity check")

            # Create target directory if needed
            target_path_obj = Path(target_path)
            target_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Export based on format
            format_type = format_config.format_type.upper()

            if format_type == "JSON":
                await self._export_json(backup_data, target_path_obj, format_config)
            elif format_type == "YAML":
                await self._export_yaml(backup_data, target_path_obj, format_config)
            elif format_type == "CSV":
                await self._export_csv(backup_data, target_path_obj, format_config)
            else:
                raise ExportImportError(f"Unsupported export format: {format_type}")

            # Get file size for audit
            file_size = target_path_obj.stat().st_size if target_path_obj.exists() else None

            await self.audit_logger.log_export_complete(operation_id, True, file_size)

            logger.info(f"Successfully exported backup {backup_id} to {target_path}")
            return True

        except Exception as e:
            logger.error(f"Export failed for backup {backup_id}: {e}")
            await self.audit_logger.log_export_complete(operation_id, False, error=str(e))
            return False

    async def import_backup(self, source: ImportSource, format_config: ExportFormat) -> str:
        """
        Import backup data from an external source.

        Args:
            source: Configuration for the import source
            format_config: Configuration for the import format

        Returns:
            Unique identifier of the imported backup
        """
        operation_id = str(uuid.uuid4())

        try:
            await self.audit_logger.log_import_start(operation_id, source, format_config)

            logger.info(f"Starting import from {source.location}")

            # Read source data
            backup_data = await self._read_source_data(source, format_config)

            # Validate imported data
            validation_result = await self._validate_backup_data(backup_data)
            if not validation_result.is_valid:
                raise ExportImportError(f"Invalid backup data: {validation_result.errors}")

            # Generate new backup ID for imported data
            backup_id = (
                f"imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            )
            backup_data.metadata.backup_id = backup_id

            # Store the imported backup
            stored_backup_id = await self.storage_engine.store_backup(backup_data)

            await self.audit_logger.log_import_complete(operation_id, True, stored_backup_id)

            logger.info(f"Successfully imported backup with ID: {stored_backup_id}")
            return stored_backup_id

        except Exception as e:
            logger.error(f"Import failed from {source.location}: {e}")
            await self.audit_logger.log_import_complete(operation_id, False, error=str(e))
            raise ExportImportError(f"Import failed: {e}") from e

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
        try:
            logger.info(f"Validating import format for {source.location}")

            # Try to read and parse the data
            backup_data = await self._read_source_data(source, format_config)

            # Validate the parsed data
            validation_result = await self._validate_backup_data(backup_data)

            logger.info(f"Format validation completed for {source.location}")
            return validation_result

        except Exception as e:
            logger.error(f"Format validation failed for {source.location}: {e}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Format validation failed: {e}"],
                details={"source": source.location, "format": format_config.format_type},
            )

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
        try:
            logger.info(
                f"Converting backup {backup_id} from {from_format.format_type} to {to_format.format_type}"
            )

            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                raise ExportImportError(f"Backup not found: {backup_id}")

            # Create temporary file for conversion
            temp_path = Path(
                f"/tmp/converted_{backup_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

            # Export to target format
            success = await self.export_backup(backup_id, to_format, str(temp_path))
            if not success:
                raise ExportImportError("Format conversion failed during export")

            logger.info(f"Successfully converted backup {backup_id} to {temp_path}")
            return str(temp_path)

        except Exception as e:
            logger.error(f"Format conversion failed for backup {backup_id}: {e}")
            raise ExportImportError(f"Format conversion failed: {e}") from e

    async def _export_json(
        self, backup_data: BackupData, target_path: Path, format_config: ExportFormat
    ) -> None:
        """Export backup data to JSON format."""
        json_content = await self.format_converter.convert_to_json(backup_data)

        if format_config.compression:
            # Apply compression
            compressed_data = self.serializer._compress_data(
                json_content.encode("utf-8"), format_config.compression
            )
            with open(target_path, "wb") as f:
                f.write(compressed_data)
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(json_content)

    async def _export_yaml(
        self, backup_data: BackupData, target_path: Path, format_config: ExportFormat
    ) -> None:
        """Export backup data to YAML format."""
        yaml_content = await self.format_converter.convert_to_yaml(backup_data)

        if format_config.compression:
            # Apply compression
            compressed_data = self.serializer._compress_data(
                yaml_content.encode("utf-8"), format_config.compression
            )
            with open(target_path, "wb") as f:
                f.write(compressed_data)
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

    async def _export_csv(
        self, backup_data: BackupData, target_path: Path, format_config: ExportFormat
    ) -> None:
        """Export backup data to CSV format (creates a directory with multiple CSV files)."""
        # Create directory for CSV files
        csv_dir = target_path.with_suffix("")
        csv_dir.mkdir(parents=True, exist_ok=True)

        csv_files = await self.format_converter.convert_to_csv(backup_data)

        for resource_type, csv_content in csv_files.items():
            csv_file_path = csv_dir / f"{resource_type}.csv"

            if format_config.compression:
                # Apply compression
                compressed_data = self.serializer._compress_data(
                    csv_content.encode("utf-8"), format_config.compression
                )
                with open(csv_file_path.with_suffix(".csv.gz"), "wb") as f:
                    f.write(compressed_data)
            else:
                with open(csv_file_path, "w", encoding="utf-8") as f:
                    f.write(csv_content)

    async def _read_source_data(
        self, source: ImportSource, format_config: ExportFormat
    ) -> BackupData:
        """Read and parse data from import source."""
        if source.source_type.lower() == "filesystem":
            return await self._read_filesystem_source(source, format_config)
        elif source.source_type.lower() == "s3":
            return await self._read_s3_source(source, format_config)
        elif source.source_type.lower() == "url":
            return await self._read_url_source(source, format_config)
        else:
            raise ExportImportError(f"Unsupported source type: {source.source_type}")

    async def _read_filesystem_source(
        self, source: ImportSource, format_config: ExportFormat
    ) -> BackupData:
        """Read data from filesystem source."""
        source_path = Path(source.location)

        if not source_path.exists():
            raise ExportImportError(f"Source file not found: {source.location}")

        format_type = format_config.format_type.upper()

        if format_type == "CSV":
            # Handle CSV directory
            if source_path.is_dir():
                csv_files = {}
                for csv_file in source_path.glob("*.csv"):
                    resource_type = csv_file.stem
                    with open(csv_file, "r", encoding="utf-8") as f:
                        csv_files[resource_type] = f.read()
                return await self.format_converter.convert_from_csv(csv_files)
            else:
                raise ExportImportError("CSV import requires a directory with CSV files")
        else:
            # Handle single file formats
            if format_config.compression:
                with open(source_path, "rb") as f:
                    compressed_data = f.read()
                decompressed_data = self.serializer._decompress_data(
                    compressed_data, format_config.compression
                )
                content = decompressed_data.decode("utf-8")
            else:
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()

            if format_type == "JSON":
                return await self.format_converter.convert_from_json(content)
            elif format_type == "YAML":
                return await self.format_converter.convert_from_yaml(content)
            else:
                raise ExportImportError(f"Unsupported format for filesystem import: {format_type}")

    async def _read_s3_source(
        self, source: ImportSource, format_config: ExportFormat
    ) -> BackupData:
        """Read data from S3 source."""
        # This would require boto3 implementation
        # For now, raise not implemented
        raise ExportImportError("S3 import not yet implemented")

    async def _read_url_source(
        self, source: ImportSource, format_config: ExportFormat
    ) -> BackupData:
        """Read data from URL source."""
        # This would require HTTP client implementation
        # For now, raise not implemented
        raise ExportImportError("URL import not yet implemented")

    async def _validate_backup_data(self, backup_data: BackupData) -> ValidationResult:
        """Validate imported backup data."""
        errors = []
        warnings = []

        try:
            # Check required fields
            if not backup_data.metadata:
                errors.append("Missing backup metadata")
            elif not backup_data.metadata.backup_id:
                errors.append("Missing backup ID in metadata")

            # Validate data integrity
            if not backup_data.verify_integrity():
                warnings.append("Backup data failed integrity check")

            # Check for empty backup
            total_resources = (
                len(backup_data.users)
                + len(backup_data.groups)
                + len(backup_data.permission_sets)
                + len(backup_data.assignments)
            )
            if total_resources == 0:
                warnings.append("Backup contains no resources")

            # Validate individual resources
            for i, user in enumerate(backup_data.users):
                if not user.user_id or not user.user_name:
                    errors.append(f"Invalid user data at index {i}: missing required fields")

            for i, group in enumerate(backup_data.groups):
                if not group.group_id or not group.display_name:
                    errors.append(f"Invalid group data at index {i}: missing required fields")

            for i, ps in enumerate(backup_data.permission_sets):
                if not ps.permission_set_arn or not ps.name:
                    errors.append(
                        f"Invalid permission set data at index {i}: missing required fields"
                    )

            for i, assignment in enumerate(backup_data.assignments):
                if not all(
                    [
                        assignment.account_id,
                        assignment.permission_set_arn,
                        assignment.principal_type,
                        assignment.principal_id,
                    ]
                ):
                    errors.append(f"Invalid assignment data at index {i}: missing required fields")

            is_valid = len(errors) == 0

            return ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                details={
                    "total_users": len(backup_data.users),
                    "total_groups": len(backup_data.groups),
                    "total_permission_sets": len(backup_data.permission_sets),
                    "total_assignments": len(backup_data.assignments),
                },
            )

        except Exception as e:
            return ValidationResult(
                is_valid=False, errors=[f"Validation error: {e}"], warnings=warnings
            )
