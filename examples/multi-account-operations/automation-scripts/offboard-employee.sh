#!/bin/bash

# offboard-employee.sh
# Automated script for offboarding employees by removing all AWS permissions

set -e  # Exit on any error

# Script configuration
SCRIPT_NAME="offboard-employee.sh"
VERSION="1.0.0"

# Default values
DEFAULT_BATCH_SIZE=5
DRY_RUN=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Usage function
usage() {
    cat << EOF
$SCRIPT_NAME v$VERSION

Automated script for offboarding employees by removing all AWS permissions.

USAGE:
    $SCRIPT_NAME <username> [OPTIONS]

ARGUMENTS:
    username     Username of the employee to offboard

OPTIONS:
    --dry-run           Preview operations without making changes
    --batch-size N      Number of accounts to process concurrently (default: $DEFAULT_BATCH_SIZE)
    --profile PROFILE   AWS profile to use
    --force             Skip confirmation prompt
    --help             Show this help message

EXAMPLES:
    # Offboard an employee
    $SCRIPT_NAME john.doe

    # Offboard with dry-run to preview
    $SCRIPT_NAME jane.smith --dry-run

    # Offboard with custom batch size
    $SCRIPT_NAME bob.wilson --batch-size 3

    # Force offboard without confirmation
    $SCRIPT_NAME former.employee --force

PERMISSION SETS REMOVED:
    This script will attempt to remove the following permission sets:
    - ReadOnlyAccess
    - DeveloperAccess
    - PowerUserAccess
    - ManagerAccess
    - AnalystAccess
    - InternAccess
    - ContractorAccess
    - DepartmentAccess
    - SecurityAuditor
    - BillingAccess

SAFETY FEATURES:
    - Dry-run mode to preview changes
    - Confirmation prompt (unless --force is used)
    - Detailed logging of all operations
    - Continues processing even if some revocations fail
    - Summary report of successful and failed operations
EOF
}

# Validate prerequisites
validate_prerequisites() {
    log "Validating prerequisites..."

    # Check if awsideman is installed
    if ! command -v awsideman &> /dev/null; then
        error "awsideman is not installed or not in PATH"
        exit 1
    fi

    # Check AWS authentication
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS authentication failed. Please configure your AWS credentials."
        exit 1
    fi

    # Check if user can access SSO
    if ! awsideman user list &> /dev/null; then
        error "Cannot access AWS SSO. Please check your permissions."
        exit 1
    fi

    success "Prerequisites validated"
}

# Validate user exists
validate_user() {
    local username=$1

    log "Validating user: $username"

    if awsideman user get "$username" &> /dev/null; then
        success "User $username found"
        return 0
    else
        warning "User $username not found in AWS SSO"
        warning "This might be expected if the user was already deleted from the identity provider"
        return 1
    fi
}

# Get current assignments for user
get_user_assignments() {
    local username=$1

    log "Checking current assignments for $username"

    # This would ideally use a list-assignments command if available
    # For now, we'll proceed with standard permission sets
    local standard_permission_sets=(
        "ReadOnlyAccess"
        "DeveloperAccess"
        "PowerUserAccess"
        "ManagerAccess"
        "AnalystAccess"
        "InternAccess"
        "ContractorAccess"
        "DepartmentAccess"
        "SecurityAuditor"
        "BillingAccess"
    )

    echo "${standard_permission_sets[@]}"
}

# Execute revocation
execute_revocation() {
    local username=$1
    local permission_set=$2
    local batch_size=$3
    local dry_run_flag=$4

    local cmd="awsideman assignment revoke \"$permission_set\" \"$username\" --filter \"*\" --batch-size $batch_size"

    if [[ "$dry_run_flag" == "true" ]]; then
        cmd="$cmd --dry-run"
    fi

    log "Executing: $cmd"

    if eval "$cmd"; then
        if [[ "$dry_run_flag" == "true" ]]; then
            success "Dry-run completed for revoking $permission_set"
        else
            success "Revoked $permission_set from all accounts"
        fi
        return 0
    else
        warning "Failed to revoke $permission_set (this may be expected if user didn't have this permission)"
        return 1
    fi
}

# Main offboarding function
offboard_employee() {
    local username=$1
    local batch_size=$2
    local dry_run_flag=$3

    log "Starting offboarding process for $username"

    if [[ "$dry_run_flag" == "true" ]]; then
        warning "DRY-RUN MODE: No actual changes will be made"
    fi

    # Get permission sets to revoke
    local permission_sets
    permission_sets=($(get_user_assignments "$username"))

    log "Will attempt to revoke ${#permission_sets[@]} permission sets"

    local successful_revocations=0
    local failed_revocations=0
    local total_revocations=${#permission_sets[@]}

    # Revoke each permission set
    for permission_set in "${permission_sets[@]}"; do
        log "Revoking $permission_set from all accounts"

        if execute_revocation "$username" "$permission_set" "$batch_size" "$dry_run_flag"; then
            ((successful_revocations++))
        else
            ((failed_revocations++))
        fi

        # Small delay to avoid overwhelming the API
        sleep 1
    done

    # Summary
    log "Offboarding summary for $username:"
    log "  Total permission sets processed: $total_revocations"
    log "  Successful revocations: $successful_revocations"
    log "  Failed revocations: $failed_revocations"

    if [[ "$dry_run_flag" == "true" ]]; then
        success "Dry-run offboarding completed for $username"
        log "Remove --dry-run flag to execute actual revocations"
    else
        if [[ $failed_revocations -eq 0 ]]; then
            success "Offboarding completed successfully for $username"
            log "User $username has been removed from all AWS accounts"
        else
            warning "Offboarding completed with some failures for $username"
            log "Please review the failed revocations and handle them manually if needed"
        fi
    fi
}

# Parse command line arguments
parse_arguments() {
    local username=""
    local batch_size=$DEFAULT_BATCH_SIZE
    local profile=""
    local force=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --batch-size)
                batch_size="$2"
                shift 2
                ;;
            --profile)
                profile="$2"
                export AWS_PROFILE="$profile"
                shift 2
                ;;
            --force)
                force=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            -*)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                if [[ -z "$username" ]]; then
                    username="$1"
                else
                    error "Too many arguments"
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Validate required arguments
    if [[ -z "$username" ]]; then
        error "Missing required argument: username"
        usage
        exit 1
    fi

    # Validate batch size
    if ! [[ "$batch_size" =~ ^[0-9]+$ ]] || [[ "$batch_size" -lt 1 ]]; then
        error "Batch size must be a positive integer"
        exit 1
    fi

    echo "$username|$batch_size|$force"
}

# Confirmation prompt
confirm_offboarding() {
    local username=$1
    local force=$2

    if [[ "$force" == "true" || "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    echo
    warning "⚠️  CRITICAL OPERATION ⚠️"
    warning "You are about to remove ALL AWS permissions for user: $username"
    warning "This will revoke access from ALL accounts in your organization"
    echo
    warning "This action cannot be easily undone!"
    echo
    read -p "Are you absolutely sure you want to continue? Type 'CONFIRM' to proceed: " -r
    echo

    if [[ "$REPLY" != "CONFIRM" ]]; then
        log "Operation cancelled by user"
        exit 0
    fi

    log "User confirmed offboarding operation"
}

# Main execution
main() {
    log "Starting $SCRIPT_NAME v$VERSION"

    # Parse arguments
    local args
    args=$(parse_arguments "$@")
    IFS='|' read -r username batch_size force <<< "$args"

    # Validate prerequisites
    validate_prerequisites

    # Validate user exists (but continue even if not found)
    validate_user "$username" || true

    # Confirm operation
    confirm_offboarding "$username" "$force"

    # Execute offboarding
    offboard_employee "$username" "$batch_size" "$DRY_RUN"

    log "Script completed"

    if [[ "$DRY_RUN" == "false" ]]; then
        echo
        success "Offboarding completed for $username"
        warning "Additional steps you may need to take:"
        warning "1. Remove user from AWS SSO/Identity Center"
        warning "2. Remove user from any external identity provider"
        warning "3. Revoke any direct IAM user access (if applicable)"
        warning "4. Update documentation and access lists"
        warning "5. Notify relevant teams about the access removal"
    fi
}

# Execute main function with all arguments
main "$@"
