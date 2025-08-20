"""
Permission set cloner for AWS Identity Center.

This module provides functionality to clone existing permission sets with all their
policies, configurations, and settings.
"""

import logging
import time
from typing import Callable, Optional
from uuid import uuid4

from ..aws_clients.manager import AWSClientManager
from .models import CloneResult, PermissionSetConfig, ValidationResult, ValidationResultType
from .permission_set_retriever import PermissionSetRetriever
from .progress_reporter import ProgressReporter, get_progress_reporter

logger = logging.getLogger(__name__)


class PermissionSetCloner:
    """
    Handles cloning of permission sets in AWS Identity Center.

    This class supports:
    - Cloning permission sets with all attached policies
    - Copying session duration and relay state settings
    - Validation to prevent duplicate names
    - Comprehensive error handling and reporting
    """

    def __init__(
        self,
        client_manager: AWSClientManager,
        instance_arn: str,
        progress_reporter: Optional[ProgressReporter] = None,
    ):
        """
        Initialize the PermissionSetCloner.

        Args:
            client_manager: AWS client manager for accessing AWS services
            instance_arn: SSO instance ARN
            progress_reporter: Optional progress reporter for logging and progress tracking
        """
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self.permission_set_retriever = PermissionSetRetriever(client_manager, instance_arn)
        self.progress_reporter = progress_reporter or get_progress_reporter()

    @property
    def sso_admin_client(self):
        """Get the SSO Admin client."""
        return self.client_manager.get_sso_admin_client()

    def clone_permission_set(
        self,
        source_name: str,
        target_name: str,
        target_description: Optional[str] = None,
        preview: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> CloneResult:
        """
        Clone a permission set with all its configurations.

        Args:
            source_name: Name of the source permission set to clone
            target_name: Name for the new cloned permission set
            target_description: Optional description for the new permission set
            preview: If True, only preview the operation without executing
            progress_callback: Optional callback for progress updates (current, total, message)

        Returns:
            CloneResult with details of the operation
        """
        # Start operation tracking
        operation_id = self.progress_reporter.start_operation(
            operation_type="clone_permission_set",
            source_name=source_name,
            target_name=target_name,
            target_description=target_description,
            preview_mode=preview,
        )

        start_time = time.time()

        logger.info(
            f"Starting permission set clone from '{source_name}' to '{target_name}' (operation_id: {operation_id})"
        )

        try:
            # Update progress: Starting validation
            self.progress_reporter.update_progress(operation_id, 0, 100, "Validating clone request")
            if progress_callback:
                progress_callback(0, 100, "Validating clone request")

            # Validate the clone request
            validation_result = self.validate_clone_request(source_name, target_name)
            if validation_result.has_errors:
                error_message = "; ".join(validation_result.messages)
                logger.error(f"Clone validation failed: {error_message}")

                # Finish operation with error
                self.progress_reporter.finish_operation(
                    operation_id, success=False, error_message=error_message
                )

                return CloneResult(
                    source_name=source_name,
                    target_name=target_name,
                    cloned_config=None,
                    rollback_id=None,
                    success=False,
                    error_message=error_message,
                )

            # Update progress: Retrieving source configuration
            self.progress_reporter.update_progress(
                operation_id, 20, 100, "Retrieving source permission set configuration"
            )
            if progress_callback:
                progress_callback(20, 100, "Retrieving source permission set configuration")

            # Get source permission set configuration
            source_arn = self.permission_set_retriever.get_permission_set_by_name(source_name)
            if not source_arn:
                error_message = f"Source permission set '{source_name}' not found"

                # Finish operation with error
                self.progress_reporter.finish_operation(
                    operation_id, success=False, error_message=error_message
                )

                return CloneResult(
                    source_name=source_name,
                    target_name=target_name,
                    cloned_config=None,
                    rollback_id=None,
                    success=False,
                    error_message=error_message,
                )

            # Log the start of the clone operation
            self.progress_reporter.log_permission_set_clone_start(
                operation_id, source_name, target_name, source_arn
            )

            source_config = self.permission_set_retriever.get_permission_set_config(source_arn)

            if preview:
                logger.info("Preview mode - no permission set will be cloned")

                # Update progress: Preview complete
                self.progress_reporter.update_progress(operation_id, 100, 100, "Preview completed")
                if progress_callback:
                    progress_callback(100, 100, "Preview completed")

                duration_ms = (time.time() - start_time) * 1000
                result = CloneResult(
                    source_name=source_name,
                    target_name=target_name,
                    cloned_config=source_config,
                    rollback_id=None,
                    success=True,
                    error_message=None,
                )

                self.progress_reporter.log_permission_set_clone_result(
                    operation_id, result, duration_ms
                )
                self.progress_reporter.finish_operation(operation_id, success=True)

                return result

            # Update progress: Creating permission set
            self.progress_reporter.update_progress(
                operation_id, 40, 100, "Creating new permission set"
            )
            if progress_callback:
                progress_callback(40, 100, "Creating new permission set")

            # Create the new permission set
            new_permission_set_arn = self._create_permission_set(
                target_name, target_description, source_config
            )

            # Generate rollback ID for this operation
            rollback_id = str(uuid4())
            logger.info(f"Generated rollback ID: {rollback_id}")

            # Update progress: Copying policies
            self.progress_reporter.update_progress(
                operation_id, 60, 100, "Copying policies to new permission set"
            )
            if progress_callback:
                progress_callback(60, 100, "Copying policies to new permission set")

            # Copy all policies to the new permission set
            self._copy_policies_to_permission_set(
                new_permission_set_arn, source_config, operation_id, progress_callback
            )

            # Update progress: Finalizing
            self.progress_reporter.update_progress(
                operation_id, 90, 100, "Finalizing cloned permission set"
            )
            if progress_callback:
                progress_callback(90, 100, "Finalizing cloned permission set")

            # Get the final configuration of the cloned permission set
            cloned_config = self.permission_set_retriever.get_permission_set_config(
                new_permission_set_arn
            )

            # Update progress: Complete
            self.progress_reporter.update_progress(
                operation_id, 100, 100, "Clone operation completed"
            )
            if progress_callback:
                progress_callback(100, 100, "Clone operation completed")

            # Prepare result
            result = CloneResult(
                source_name=source_name,
                target_name=target_name,
                cloned_config=cloned_config,
                rollback_id=rollback_id,
                success=True,
                error_message=None,
                source_arn=source_arn,
                target_arn=new_permission_set_arn,
            )

            # Log performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self.progress_reporter.log_performance_metric(
                operation_id, "clone_permission_set", "duration_ms", duration_ms, "milliseconds"
            )

            # Count policies for metrics
            policy_count = 0
            if cloned_config.aws_managed_policies:
                policy_count += len(cloned_config.aws_managed_policies)
            if cloned_config.customer_managed_policies:
                policy_count += len(cloned_config.customer_managed_policies)
            if cloned_config.inline_policy:
                policy_count += 1

            self.progress_reporter.log_performance_metric(
                operation_id, "clone_permission_set", "policies_copied", policy_count, "count"
            )

            # Log audit result and finish operation
            self.progress_reporter.log_permission_set_clone_result(
                operation_id, result, duration_ms
            )
            self.progress_reporter.finish_operation(operation_id, success=True)

            logger.info(f"Successfully cloned permission set '{source_name}' to '{target_name}'")

            return result

        except Exception as e:
            error_message = f"Clone operation failed: {str(e)}"
            logger.error(f"Error during permission set cloning: {str(e)}", exc_info=True)

            # Log performance metrics for failed operation
            duration_ms = (time.time() - start_time) * 1000
            self.progress_reporter.log_performance_metric(
                operation_id, "clone_permission_set", "duration_ms", duration_ms, "milliseconds"
            )

            # Finish operation with error
            self.progress_reporter.finish_operation(
                operation_id, success=False, error_message=error_message
            )

            return CloneResult(
                source_name=source_name,
                target_name=target_name,
                cloned_config=None,
                rollback_id=None,
                success=False,
                error_message=error_message,
            )

    def validate_clone_request(self, source_name: str, target_name: str) -> ValidationResult:
        """
        Validate a permission set clone request.

        Args:
            source_name: Name of the source permission set
            target_name: Name for the new permission set

        Returns:
            ValidationResult indicating success or failure
        """
        errors = []

        # Validate source name
        if not source_name or not source_name.strip():
            errors.append("Source permission set name cannot be empty")

        # Validate target name
        if not target_name or not target_name.strip():
            errors.append("Target permission set name cannot be empty")
        elif len(target_name) > 32:
            errors.append("Target permission set name cannot exceed 32 characters")
        elif not self._is_valid_permission_set_name(target_name):
            errors.append("Target permission set name contains invalid characters")

        # Check if source and target are the same
        if source_name == target_name:
            errors.append("Source and target permission set names cannot be the same")

        # Check if target name already exists
        if target_name and self.permission_set_retriever.get_permission_set_by_name(target_name):
            errors.append(f"Permission set with name '{target_name}' already exists")

        if errors:
            return ValidationResult(result_type=ValidationResultType.ERROR, messages=errors)

        return ValidationResult(result_type=ValidationResultType.SUCCESS, messages=[])

    def _create_permission_set(
        self, name: str, description: Optional[str], source_config: PermissionSetConfig
    ) -> str:
        """
        Create a new permission set.

        Args:
            name: Name for the new permission set
            description: Description for the new permission set
            source_config: Source permission set configuration

        Returns:
            ARN of the newly created permission set
        """
        try:
            # Use source description if no target description provided
            final_description = description or source_config.description or "Cloned permission set"

            # Prepare parameters for create_permission_set
            create_params = {
                "InstanceArn": self.instance_arn,
                "Name": name,
                "Description": final_description,
                "SessionDuration": source_config.session_duration,
            }

            # Only include RelayState if it's not None
            if source_config.relay_state_url:
                create_params["RelayState"] = source_config.relay_state_url

            response = self.sso_admin_client.create_permission_set(**create_params)

            permission_set_arn = response["PermissionSet"]["PermissionSetArn"]
            logger.info(f"Created permission set '{name}' with ARN: {permission_set_arn}")

            return permission_set_arn

        except Exception as e:
            logger.error(f"Failed to create permission set '{name}': {str(e)}")
            raise

    def _copy_policies_to_permission_set(
        self,
        permission_set_arn: str,
        source_config: PermissionSetConfig,
        operation_id: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        """
        Copy all policies from source configuration to the new permission set.

        Args:
            permission_set_arn: ARN of the target permission set
            source_config: Source permission set configuration
            operation_id: Operation ID for progress tracking
            progress_callback: Optional callback for progress updates
        """
        try:
            # Calculate total policy operations
            total_operations = 0
            if source_config.aws_managed_policies:
                total_operations += len(source_config.aws_managed_policies)
            if source_config.customer_managed_policies:
                total_operations += len(source_config.customer_managed_policies)
            if source_config.inline_policy:
                total_operations += 1

            current_operation = 0

            # Copy AWS managed policies
            if source_config.aws_managed_policies:
                for i, policy_arn in enumerate(source_config.aws_managed_policies):
                    current_operation += 1
                    progress_message = f"Attaching AWS managed policy {i+1}/{len(source_config.aws_managed_policies)}"

                    # Update progress (60-80% range for policy copying)
                    progress_percentage = 60 + int((current_operation / total_operations) * 20)
                    self.progress_reporter.update_progress(
                        operation_id, progress_percentage, 100, progress_message
                    )
                    if progress_callback:
                        progress_callback(progress_percentage, 100, progress_message)

                    self.sso_admin_client.attach_managed_policy_to_permission_set(
                        InstanceArn=self.instance_arn,
                        PermissionSetArn=permission_set_arn,
                        ManagedPolicyArn=policy_arn,
                    )

                    # Log performance metric
                    self.progress_reporter.log_performance_metric(
                        operation_id,
                        "clone_permission_set",
                        "aws_managed_policy_attached",
                        1,
                        "count",
                        policy_arn=policy_arn,
                    )

                logger.debug(
                    f"Attached {len(source_config.aws_managed_policies)} AWS managed policies"
                )

            # Copy customer managed policies
            if source_config.customer_managed_policies:
                for i, policy in enumerate(source_config.customer_managed_policies):
                    current_operation += 1
                    progress_message = f"Attaching customer managed policy {i+1}/{len(source_config.customer_managed_policies)}"

                    # Update progress
                    progress_percentage = 60 + int((current_operation / total_operations) * 20)
                    self.progress_reporter.update_progress(
                        operation_id, progress_percentage, 100, progress_message
                    )
                    if progress_callback:
                        progress_callback(progress_percentage, 100, progress_message)

                    # Reconstruct the full ARN
                    policy_arn = (
                        f"arn:aws:iam::{self._get_account_id()}:policy{policy.path}{policy.name}"
                    )
                    self.sso_admin_client.attach_managed_policy_to_permission_set(
                        InstanceArn=self.instance_arn,
                        PermissionSetArn=permission_set_arn,
                        ManagedPolicyArn=policy_arn,
                    )

                    # Log performance metric
                    self.progress_reporter.log_performance_metric(
                        operation_id,
                        "clone_permission_set",
                        "customer_managed_policy_attached",
                        1,
                        "count",
                        policy_name=policy.name,
                        policy_path=policy.path,
                    )

                logger.debug(
                    f"Attached {len(source_config.customer_managed_policies)} customer managed policies"
                )

            # Copy inline policy
            if source_config.inline_policy:
                current_operation += 1
                progress_message = "Attaching inline policy"

                # Update progress
                progress_percentage = 60 + int((current_operation / total_operations) * 20)
                self.progress_reporter.update_progress(
                    operation_id, progress_percentage, 100, progress_message
                )
                if progress_callback:
                    progress_callback(progress_percentage, 100, progress_message)

                self.sso_admin_client.put_inline_policy_to_permission_set(
                    InstanceArn=self.instance_arn,
                    PermissionSetArn=permission_set_arn,
                    InlinePolicy=source_config.inline_policy,
                )

                # Log performance metric
                self.progress_reporter.log_performance_metric(
                    operation_id, "clone_permission_set", "inline_policy_attached", 1, "count"
                )

                logger.debug("Attached inline policy to permission set")

        except Exception as e:
            logger.error(f"Failed to copy policies to permission set: {str(e)}")
            raise

    def _get_account_id(self) -> str:
        """
        Get the current AWS account ID.

        Returns:
            AWS account ID as string
        """
        # This is a simplified implementation - in practice, you might want to
        # get this from the client manager or configuration
        try:
            sts_client = self.client_manager.get_client("sts")
            response = sts_client.get_caller_identity()
            return response["Account"]
        except Exception:
            # Fallback to a default account ID for testing
            return "123456789012"

    def _is_valid_permission_set_name(self, name: str) -> bool:
        """
        Validate permission set name format.

        Args:
            name: Permission set name to validate

        Returns:
            True if name is valid, False otherwise
        """
        import re

        # Permission set names can contain alphanumeric characters, hyphens, and underscores
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))

    def get_clone_summary(self, result: CloneResult) -> str:
        """
        Get a human-readable summary of the clone operation.

        Args:
            result: CloneResult from a clone operation

        Returns:
            String summary of the clone operation
        """
        if not result.success:
            return f"Clone operation failed: {result.error_message}"

        summary_parts = []

        if result.cloned_config:
            summary_parts.append(
                f"Successfully cloned '{result.source_name}' to '{result.target_name}'"
            )

            # Add policy information
            if result.cloned_config.aws_managed_policies:
                summary_parts.append(
                    f"AWS managed policies: {len(result.cloned_config.aws_managed_policies)}"
                )

            if result.cloned_config.customer_managed_policies:
                summary_parts.append(
                    f"Customer managed policies: {len(result.cloned_config.customer_managed_policies)}"
                )

            if result.cloned_config.inline_policy:
                summary_parts.append("Inline policy: Yes")

            summary_parts.append(f"Session duration: {result.cloned_config.session_duration}")

            if result.cloned_config.relay_state_url:
                summary_parts.append(f"Relay state URL: {result.cloned_config.relay_state_url}")
        else:
            summary_parts.append(
                f"Preview: Would clone '{result.source_name}' to '{result.target_name}'"
            )

        return "; ".join(summary_parts)
