"""Orphaned assignment detection component for AWS Identity Center status monitoring."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from .status_infrastructure import BaseStatusChecker, StatusCheckError
from .status_models import (
    CleanupResult,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    PrincipalType,
    StatusLevel,
)

logger = logging.getLogger(__name__)


def _ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is timezone-aware.

    If the datetime is timezone-naive, assume it's UTC and make it timezone-aware.
    If the datetime is already timezone-aware, return it as-is.

    Args:
        dt: Datetime to make timezone-aware

    Returns:
        Timezone-aware datetime or None if input is None
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)

    return dt


class OrphanedAssignmentDetector(BaseStatusChecker):
    """
    Orphaned assignment detector component for AWS Identity Center.

    Identifies permission set assignments where the principal (user or group)
    has been deleted from the identity provider but the assignment remains.
    Provides interactive cleanup functionality with user confirmation.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the orphaned assignment detector.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Status check configuration
        """
        super().__init__(idc_client, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Cache for assignment tracking
        self._assignment_cache: Dict[str, OrphanedAssignment] = {}
        self._last_check_time: Optional[datetime] = None

    async def check_status(self) -> OrphanedAssignmentStatus:
        """
        Perform comprehensive orphaned assignment detection.

        Returns:
            OrphanedAssignmentStatus: Orphaned assignment status with detected assignments
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        try:
            # Detect orphaned assignments
            orphaned_assignments = await self._detect_orphaned_assignments()

            # Determine overall status
            overall_status = self._determine_orphaned_assignment_status(orphaned_assignments)

            # Create orphaned assignment status result
            orphaned_status = OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=overall_status["status"],
                message=overall_status["message"],
                orphaned_assignments=orphaned_assignments,
                cleanup_available=True,
                last_cleanup=self._get_last_cleanup_time(),
                cleanup_history=self._get_cleanup_history(),
            )

            # Add detailed information
            orphaned_status.add_detail("total_orphaned", len(orphaned_assignments))
            orphaned_status.add_detail("user_orphans", len(orphaned_status.get_user_orphans()))
            orphaned_status.add_detail("group_orphans", len(orphaned_status.get_group_orphans()))
            orphaned_status.add_detail(
                "affected_accounts", len(orphaned_status.get_accounts_with_orphans())
            )
            orphaned_status.add_detail("check_duration_ms", (time.time() - start_time) * 1000)

            # Add account breakdown
            account_breakdown = self._get_account_breakdown(orphaned_assignments)
            orphaned_status.add_detail("account_breakdown", account_breakdown)

            # Add any errors encountered during detection
            if overall_status.get("errors"):
                orphaned_status.errors.extend(overall_status["errors"])

            self.logger.info(
                f"Orphaned assignment detection completed: {overall_status['status']} "
                f"({len(orphaned_assignments)} orphaned assignments found)"
            )

            # Update cache and last check time
            self._update_assignment_cache(orphaned_assignments)
            self._last_check_time = timestamp

            return orphaned_status

        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Unexpected error in orphaned assignment detection: {str(e)}")

            # Create error result
            orphaned_status = OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Orphaned assignment detection failed: {str(e)}",
                orphaned_assignments=[],
                cleanup_available=False,
                last_cleanup=None,
                cleanup_history=[],
            )

            orphaned_status.add_error(str(e))
            orphaned_status.add_detail("error_type", type(e).__name__)
            orphaned_status.add_detail("component", "OrphanedAssignmentDetector")

            return orphaned_status

    async def _detect_orphaned_assignments(self) -> List[OrphanedAssignment]:
        """
        Detect orphaned permission set assignments using robust principal existence checking.

        This approach:
        1. Gets ALL assignments for each permission set and account
        2. Uses individual API calls to verify each principal exists
        3. Has robust error handling to avoid false positives

        This is much more reliable than bulk listing users/groups which can fail.

        Returns:
            List[OrphanedAssignment]: List of orphaned assignments found
        """
        orphaned_assignments = []

        try:
            client = self.idc_client.get_sso_admin_client()
            identity_store_client = self.idc_client.get_identity_store_client()

            # Get the profile-specific SSO instance from the client manager
            profile_name = getattr(self.idc_client, "profile", None)
            if not profile_name:
                self.logger.error("No profile name available in client manager")
                raise StatusCheckError(
                    "Profile isolation failed: no profile name available",
                    "OrphanedAssignmentDetector",
                )

            # Get the profile configuration to find the SSO instance
            from ..utils.config import Config

            config = Config()
            profiles = config.get("profiles", {})

            if profile_name not in profiles:
                self.logger.error(f"Profile '{profile_name}' not found in configuration")
                raise StatusCheckError(
                    f"Profile '{profile_name}' not found in configuration",
                    "OrphanedAssignmentDetector",
                )

            profile_config = profiles[profile_name]
            instance_arn = profile_config.get("sso_instance_arn")
            identity_store_id = profile_config.get("identity_store_id")

            if not instance_arn or not identity_store_id:
                self.logger.error(
                    f"Missing SSO instance ARN or identity store ID for profile '{profile_name}'"
                )
                raise StatusCheckError(
                    f"Missing SSO instance ARN or identity store ID for profile '{profile_name}'",
                    "OrphanedAssignmentDetector",
                )

            self.logger.info(
                f"Using robust principal checking approach for profile '{profile_name}'"
            )

            # Get all accounts in the organization (for account names)
            all_accounts = {}
            try:
                org_client = self.idc_client.get_organizations_client()
                org_paginator = org_client.get_paginator("list_accounts")
                for page in org_paginator.paginate():
                    for account in page.get("Accounts", []):
                        all_accounts[account["Id"]] = account.get("Name", account["Id"])

                self.logger.info(f"Found {len(all_accounts)} accounts in organization")
            except Exception as e:
                self.logger.warning(f"Error accessing Organizations API: {str(e)}")
                all_accounts = {}

            # Get all permission sets and check assignments
            try:
                # First, get all permission sets
                ps_response = client.list_permission_sets(InstanceArn=instance_arn)
                permission_sets = ps_response.get("PermissionSets", [])
                self.logger.info(f"Found {len(permission_sets)} permission sets")

                # Get permission set names for better reporting
                permission_set_names = {}
                for ps_arn in permission_sets:
                    try:
                        ps_details = client.describe_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps_arn
                        )
                        ps_name = ps_details.get("PermissionSet", {}).get(
                            "Name", ps_arn.split("/")[-1]
                        )
                        permission_set_names[ps_arn] = ps_name
                    except Exception:
                        ps_name = ps_arn.split("/")[-1]
                        permission_set_names[ps_arn] = ps_name

                # Check each permission set for assignments
                for ps_arn in permission_sets:
                    ps_name = permission_set_names[ps_arn]
                    self.logger.debug(f"Checking permission set: {ps_name}")

                    try:
                        # Get all accounts with this permission set provisioned
                        accounts_response = client.list_accounts_for_provisioned_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps_arn
                        )

                        for account_id in accounts_response.get("AccountIds", []):
                            try:
                                # Get ALL assignments for this permission set and account
                                assignments_response = client.list_account_assignments(
                                    InstanceArn=instance_arn,
                                    AccountId=account_id,
                                    PermissionSetArn=ps_arn,
                                )

                                assignments = assignments_response.get("AccountAssignments", [])
                                if assignments:
                                    self.logger.debug(
                                        f"Found {len(assignments)} assignments for {ps_name} in account {account_id}"
                                    )

                                    # Check each assignment for orphaned principals using robust checking
                                    for assignment in assignments:
                                        principal_id = assignment.get("PrincipalId")
                                        principal_type = assignment.get("PrincipalType")

                                        if not principal_id or not principal_type:
                                            continue

                                        # Use robust principal existence checking
                                        principal_exists, principal_name, error_message = (
                                            await self._check_principal_exists(
                                                identity_store_id,
                                                principal_id,
                                                principal_type,
                                                identity_store_client,
                                            )
                                        )

                                        if not principal_exists:
                                            # This is an orphaned assignment!
                                            self.logger.info(
                                                f"Found orphaned assignment: {ps_name} -> {principal_id} in {account_id}"
                                            )

                                            # Get account name
                                            account_name = all_accounts.get(account_id, account_id)

                                            # Create orphaned assignment object
                                            orphaned_assignment = OrphanedAssignment(
                                                assignment_id=f"{ps_arn}#{principal_id}#{account_id}",
                                                permission_set_arn=ps_arn,
                                                permission_set_name=ps_name,
                                                account_id=account_id,
                                                account_name=account_name,
                                                principal_id=principal_id,
                                                principal_type=PrincipalType(principal_type),
                                                principal_name=principal_name,  # Use the name we found or None
                                                error_message=error_message
                                                or f"Principal {principal_type.lower()} with ID {principal_id} no longer exists in Identity Store",
                                                created_date=assignment.get("CreatedDate")
                                                or datetime.now(timezone.utc),
                                                last_accessed=None,
                                            )

                                            orphaned_assignments.append(orphaned_assignment)

                            except ClientError as e:
                                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                                if error_code not in ["AccessDenied", "ResourceNotFound"]:
                                    self.logger.warning(
                                        f"Error checking assignments for account {account_id}: {str(e)}"
                                    )
                            except Exception as e:
                                self.logger.warning(
                                    f"Unexpected error checking account {account_id}: {str(e)}"
                                )

                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "Unknown")
                        if error_code not in ["AccessDenied", "ResourceNotFound"]:
                            self.logger.warning(f"Error checking permission set {ps_arn}: {str(e)}")
                    except Exception as e:
                        self.logger.warning(
                            f"Unexpected error checking permission set {ps_arn}: {str(e)}"
                        )

            except Exception as e:
                self.logger.error(f"Error in assignment detection: {str(e)}")
                raise StatusCheckError(
                    f"Failed to detect orphaned assignments: {str(e)}", "OrphanedAssignmentDetector"
                )

        except Exception as e:
            self.logger.error(f"Error detecting orphaned assignments: {str(e)}")
            raise StatusCheckError(
                f"Failed to detect orphaned assignments: {str(e)}", "OrphanedAssignmentDetector"
            )

        self.logger.info(
            f"Orphaned assignment detection completed. Found {len(orphaned_assignments)} orphaned assignments."
        )
        return orphaned_assignments

    async def _check_assignments_for_account(
        self,
        instance_arn: str,
        ps_arn: str,
        ps_name: str,
        account_id: str,
        identity_store_id: str,
        client,
        identity_store_client,
    ) -> List[OrphanedAssignment]:
        """
        Check for orphaned assignments in a specific account.

        Args:
            instance_arn: Identity Center instance ARN
            ps_arn: Permission set ARN
            ps_name: Permission set name
            account_id: AWS account ID
            identity_store_id: Identity store ID
            client: Identity Center client
            identity_store_client: Identity Store client

        Returns:
            List[OrphanedAssignment]: Orphaned assignments found in this account
        """
        orphaned_assignments = []

        try:
            # Get account name for display
            try:
                # Try to get account name from Organizations
                org_client = self.idc_client.get_organizations_client()
                account_details = org_client.describe_account(account_id)
                account_name = account_details.get("Name", account_id)
            except Exception:
                account_name = account_id

            # List all assignments for this permission set and account
            assignments_response = client.list_account_assignments(
                InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=ps_arn
            )

            assignments = assignments_response.get("AccountAssignments", [])

            for assignment in assignments:
                principal_id = assignment.get("PrincipalId")
                principal_type = assignment.get("PrincipalType")
                created_date = _ensure_timezone_aware(
                    assignment.get("CreatedDate")
                ) or datetime.now(timezone.utc)

                if not principal_id or not principal_type:
                    continue

                # Check if the principal still exists
                (
                    principal_exists,
                    principal_name,
                    error_message,
                ) = await self._check_principal_exists(
                    identity_store_id, principal_id, principal_type, identity_store_client
                )

                if not principal_exists and error_message:
                    # This is an orphaned assignment
                    orphaned_assignment = OrphanedAssignment(
                        assignment_id=f"{ps_arn}#{principal_id}#{account_id}",
                        permission_set_arn=ps_arn,
                        permission_set_name=ps_name,
                        account_id=account_id,
                        account_name=account_name,
                        principal_id=principal_id,
                        principal_type=PrincipalType(principal_type),
                        principal_name=principal_name,
                        error_message=error_message,
                        created_date=created_date,
                        last_accessed=None,  # AWS doesn't provide last access info
                    )

                    orphaned_assignments.append(orphaned_assignment)

                    self.logger.debug(
                        f"Found orphaned assignment: {orphaned_assignment.get_display_name()}"
                    )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code not in ["AccessDenied", "ResourceNotFound"]:
                self.logger.warning(
                    f"Error checking assignments for account {account_id}: {str(e)}"
                )
        except Exception as e:
            self.logger.warning(
                f"Unexpected error checking assignments for account {account_id}: {str(e)}"
            )

        return orphaned_assignments

    async def _check_principal_exists(
        self, identity_store_id: str, principal_id: str, principal_type: str, identity_store_client
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a principal (user or group) still exists in the identity store.

        Args:
            identity_store_id: Identity store ID
            principal_id: Principal ID to check
            principal_type: Principal type (USER or GROUP)
            identity_store_client: Identity Store client

        Returns:
            Tuple of (exists, principal_name, error_message)
        """
        try:
            if principal_type == "USER":
                # Try to describe the user
                response = identity_store_client.describe_user(
                    IdentityStoreId=identity_store_id, UserId=principal_id
                )
                user_name = response.get("UserName") or response.get("DisplayName") or principal_id
                return True, user_name, None

            elif principal_type == "GROUP":
                # Try to describe the group
                response = identity_store_client.describe_group(
                    IdentityStoreId=identity_store_id, GroupId=principal_id
                )
                group_name = response.get("DisplayName") or principal_id
                return True, group_name, None

            else:
                return False, None, f"Unknown principal type: {principal_type}"

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            # These error codes indicate the principal no longer exists
            if error_code in [
                "ResourceNotFoundException",
                "ResourceNotFound",
                "NoSuchEntity",
                "NotFound",
            ]:
                aws_error_msg = f"AWS Error {error_code}: {error_message}"
                self.logger.debug(
                    f"Principal {principal_id} ({principal_type}) not found: {aws_error_msg}"
                )
                return False, None, aws_error_msg

            # These error codes might also indicate the principal doesn't exist
            elif error_code in ["ValidationException", "InvalidParameterValue"]:
                # Check if the error message suggests the principal doesn't exist
                error_lower = error_message.lower()
                if any(
                    keyword in error_lower
                    for keyword in ["not found", "does not exist", "invalid", "not exist"]
                ):
                    aws_error_msg = f"AWS Error {error_code}: {error_message}"
                    self.logger.debug(
                        f"Principal {principal_id} ({principal_type}) appears invalid: {aws_error_msg}"
                    )
                    return False, None, aws_error_msg

            # Other errors might indicate permission issues or temporary problems
            elif error_code in ["AccessDenied", "UnauthorizedOperation"]:
                self.logger.warning(
                    f"Permission denied checking principal {principal_id}: {error_message}"
                )
                # Assume principal exists if we can't check due to permissions
                return True, f"Unknown {principal_type.lower()}", None

            else:
                self.logger.warning(
                    f"Unexpected error checking principal {principal_id}: {error_message}"
                )
                # For other errors, assume principal exists to avoid false positives
                return True, f"Unknown {principal_type.lower()}", None

        except Exception as e:
            self.logger.warning(f"Unexpected error checking principal {principal_id}: {str(e)}")
            # For unexpected errors, assume principal exists to avoid false positives
            return True, f"Unknown {principal_type.lower()}", None

    def _determine_orphaned_assignment_status(
        self, orphaned_assignments: List[OrphanedAssignment]
    ) -> Dict[str, Any]:
        """
        Determine overall orphaned assignment status.

        Args:
            orphaned_assignments: List of orphaned assignments

        Returns:
            Dict containing status and message
        """
        orphaned_count = len(orphaned_assignments)

        # No orphaned assignments found
        if orphaned_count == 0:
            return {
                "status": StatusLevel.HEALTHY,
                "message": "No orphaned assignments found",
                "errors": [],
            }

        # Determine severity based on count and age
        old_assignments = []
        for assignment in orphaned_assignments:
            age_days = assignment.get_age_days()
            if age_days > 30:  # Assignments older than 30 days
                old_assignments.append(assignment)

        # Critical: Many orphaned assignments or very old ones
        if orphaned_count > 50 or len(old_assignments) > 10:
            return {
                "status": StatusLevel.CRITICAL,
                "message": f"Critical: {orphaned_count} orphaned assignments found ({len(old_assignments)} older than 30 days)",
                "errors": [f"High number of orphaned assignments: {orphaned_count}"],
            }

        # Warning: Some orphaned assignments found
        elif orphaned_count > 0:
            return {
                "status": StatusLevel.WARNING,
                "message": f"Warning: {orphaned_count} orphaned assignments found",
                "errors": [f"Orphaned assignments detected: {orphaned_count}"],
            }

        # This shouldn't be reached given the check above, but included for completeness
        return {
            "status": StatusLevel.HEALTHY,
            "message": "No orphaned assignments found",
            "errors": [],
        }

    def _get_account_breakdown(
        self, orphaned_assignments: List[OrphanedAssignment]
    ) -> Dict[str, int]:
        """
        Get breakdown of orphaned assignments by account.

        Args:
            orphaned_assignments: List of orphaned assignments

        Returns:
            Dict mapping account IDs to orphaned assignment counts
        """
        breakdown = {}
        for assignment in orphaned_assignments:
            account_id = assignment.account_id
            breakdown[account_id] = breakdown.get(account_id, 0) + 1
        return breakdown

    def _update_assignment_cache(self, orphaned_assignments: List[OrphanedAssignment]) -> None:
        """
        Update the internal assignment cache.

        Args:
            orphaned_assignments: Assignments to cache
        """
        try:
            # Clear old cache and update with new assignments
            self._assignment_cache.clear()

            for assignment in orphaned_assignments:
                self._assignment_cache[assignment.assignment_id] = assignment

            self.logger.debug(
                f"Updated assignment cache: {len(self._assignment_cache)} orphaned assignments cached"
            )

        except Exception as e:
            self.logger.warning(f"Error updating assignment cache: {str(e)}")

    def _get_last_cleanup_time(self) -> Optional[datetime]:
        """
        Get the timestamp of the last cleanup operation.

        Returns:
            datetime: Last cleanup time or None if no cleanup has been performed
        """
        # In a real implementation, this would be stored in a database or file
        # For now, return None to indicate no previous cleanup
        return None

    def _get_cleanup_history(self) -> List[CleanupResult]:
        """
        Get the history of cleanup operations.

        Returns:
            List[CleanupResult]: List of previous cleanup results
        """
        # In a real implementation, this would be stored in a database or file
        # For now, return empty list
        return []

    async def cleanup_orphaned_assignments(
        self, assignments: List[OrphanedAssignment]
    ) -> CleanupResult:
        """
        Clean up orphaned assignments with detailed tracking.

        Args:
            assignments: List of orphaned assignments to clean up

        Returns:
            CleanupResult: Results of the cleanup operation
        """
        start_time = time.time()

        cleanup_result = CleanupResult(
            total_attempted=len(assignments),
            successful_cleanups=0,
            failed_cleanups=0,
            cleanup_errors=[],
            cleaned_assignments=[],
            duration_seconds=0.0,
        )

        if not assignments:
            cleanup_result.duration_seconds = time.time() - start_time
            return cleanup_result

        try:
            client = self.idc_client.get_sso_admin_client()

            for assignment in assignments:
                try:
                    # Extract instance ARN from permission set ARN
                    # Permission set ARN format: arn:aws:sso:::permissionSet/ssoins-{instance-id}/ps-{ps-id}
                    ps_arn_parts = assignment.permission_set_arn.split("/")
                    if len(ps_arn_parts) >= 2:
                        instance_id = ps_arn_parts[1]  # ssoins-{instance-id}
                        instance_arn = f"arn:aws:sso:::instance/{instance_id}"
                    else:
                        raise ValueError(
                            f"Invalid permission set ARN format: {assignment.permission_set_arn}"
                        )

                    # Delete the account assignment
                    client.delete_account_assignment(
                        InstanceArn=instance_arn,
                        TargetId=assignment.account_id,
                        TargetType="AWS_ACCOUNT",
                        PermissionSetArn=assignment.permission_set_arn,
                        PrincipalType=assignment.principal_type.value,
                        PrincipalId=assignment.principal_id,
                    )

                    # Track successful cleanup
                    cleanup_result.successful_cleanups += 1
                    cleanup_result.cleaned_assignments.append(assignment.assignment_id)

                    self.logger.info(
                        f"Successfully cleaned up orphaned assignment: {assignment.get_display_name()}"
                    )

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    cleanup_result.failed_cleanups += 1
                    error_msg = f"Failed to clean up {assignment.get_display_name()}: {error_code} - {error_message}"
                    cleanup_result.cleanup_errors.append(error_msg)

                    self.logger.warning(error_msg)

                except Exception as e:
                    cleanup_result.failed_cleanups += 1
                    error_msg = (
                        f"Unexpected error cleaning up {assignment.get_display_name()}: {str(e)}"
                    )
                    cleanup_result.cleanup_errors.append(error_msg)

                    self.logger.error(error_msg)

        except Exception as e:
            error_msg = f"Critical error during cleanup operation: {str(e)}"
            cleanup_result.cleanup_errors.append(error_msg)
            self.logger.error(error_msg)

        finally:
            cleanup_result.duration_seconds = time.time() - start_time

        self.logger.info(
            f"Cleanup operation completed: {cleanup_result.successful_cleanups} successful, "
            f"{cleanup_result.failed_cleanups} failed in {cleanup_result.duration_seconds:.2f} seconds"
        )

        return cleanup_result

    def prompt_for_cleanup(self, orphaned_assignments: List[OrphanedAssignment]) -> bool:
        """
        Prompt the user for confirmation to clean up orphaned assignments.

        Args:
            orphaned_assignments: List of orphaned assignments to clean up

        Returns:
            bool: True if user confirms cleanup, False otherwise
        """
        if not orphaned_assignments:
            return False

        try:
            print(f"\n🔍 Found {len(orphaned_assignments)} orphaned assignment(s):")
            print("=" * 80)

            # Display orphaned assignments in a readable format
            for i, assignment in enumerate(orphaned_assignments[:10], 1):  # Show first 10
                print(f"{i:2d}. {assignment.get_display_name()}")
                print(f"    Account: {assignment.account_name or assignment.account_id}")
                print(f"    Error: {assignment.error_message}")
                print(f"    Age: {assignment.get_age_days()} days")
                print()

            if len(orphaned_assignments) > 10:
                print(f"    ... and {len(orphaned_assignments) - 10} more assignments")
                print()

            print("⚠️  WARNING: This will permanently delete these permission set assignments!")
            print(
                "   Make sure these principals are truly deleted and not just temporarily unavailable."
            )
            print()

            # Get user confirmation
            while True:
                try:
                    response = (
                        input("Do you want to clean up these orphaned assignments? (yes/no): ")
                        .strip()
                        .lower()
                    )

                    if response in ["yes", "y"]:
                        return True
                    elif response in ["no", "n"]:
                        return False
                    else:
                        print("Please enter 'yes' or 'no'")

                except KeyboardInterrupt:
                    print("\n\nOperation cancelled by user.")
                    return False
                except EOFError:
                    print("\n\nNo input received. Operation cancelled.")
                    return False

        except Exception as e:
            self.logger.error(f"Error during user prompt: {str(e)}")
            print(f"\nError during confirmation prompt: {str(e)}")
            return False

    def format_cleanup_summary(self, cleanup_result: CleanupResult) -> str:
        """
        Format a cleanup summary for display.

        Args:
            cleanup_result: Cleanup result to format

        Returns:
            str: Formatted cleanup summary
        """
        if cleanup_result.total_attempted == 0:
            return "No cleanup operations attempted"

        summary_parts = [
            f"Cleanup completed in {cleanup_result.duration_seconds:.2f}s",
            f"Attempted: {cleanup_result.total_attempted}",
            f"Successful: {cleanup_result.successful_cleanups}",
            f"Failed: {cleanup_result.failed_cleanups}",
            f"Success Rate: {cleanup_result.get_success_rate():.1f}%",
        ]

        return " | ".join(summary_parts)

    def get_assignment_errors(
        self, orphaned_assignments: List[OrphanedAssignment]
    ) -> List[Dict[str, Any]]:
        """
        Get detailed error information for orphaned assignments.

        Args:
            orphaned_assignments: List of orphaned assignments

        Returns:
            List of error detail dictionaries
        """
        error_details = []

        for assignment in orphaned_assignments:
            error_details.append(
                {
                    "assignment_id": assignment.assignment_id,
                    "permission_set_name": assignment.permission_set_name,
                    "permission_set_arn": assignment.permission_set_arn,
                    "account_id": assignment.account_id,
                    "account_name": assignment.account_name,
                    "principal_id": assignment.principal_id,
                    "principal_type": assignment.principal_type.value,
                    "principal_name": assignment.principal_name,
                    "error_message": assignment.error_message,
                    "created_date": assignment.created_date.isoformat(),
                    "age_days": assignment.get_age_days(),
                    "display_name": assignment.get_display_name(),
                }
            )

        return error_details

    def format_orphaned_assignment_summary(self, orphaned_status: OrphanedAssignmentStatus) -> str:
        """
        Format a concise orphaned assignment summary for display.

        Args:
            orphaned_status: Orphaned assignment status to format

        Returns:
            str: Formatted summary
        """
        summary_parts = [
            f"Status: {orphaned_status.status.value}",
            f"Message: {orphaned_status.message}",
        ]

        if orphaned_status.has_orphaned_assignments():
            summary_parts.append(f"Orphaned: {orphaned_status.get_orphaned_count()}")
            summary_parts.append(f"Users: {len(orphaned_status.get_user_orphans())}")
            summary_parts.append(f"Groups: {len(orphaned_status.get_group_orphans())}")
            summary_parts.append(f"Accounts: {len(orphaned_status.get_accounts_with_orphans())}")

        if orphaned_status.cleanup_available:
            summary_parts.append("Cleanup: Available")

        return " | ".join(summary_parts)
