#!/bin/bash

# rotate-permissions.sh
# Automated script for rotating permissions (removing old and assigning new)

set -e  # Exit on any error

# Script configuration
SCRIPT_NAME="rotate-permissions.sh"
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

Automated script for rotating permissions by removing old permission sets and assigning new ones.

USAGE:
    $SCRIPT_NAME <username> <old-permission-set> <new-permission-set> [OPTIONS]

ARGUMENTS:
    username              Username to rotate permissions for
    old-permission-set    Permission set to remove
    new-permission-set    Permission set to assign

OPTIONS:
    --filter FILTER       Account filter (default: "*" for all accounts)
    --dry-run            Preview operations without making changes
    --batch-size N       Number of accounts to process concurrently (default: $DEFAULT_BATCH_SIZE)
    --profile PROFILE    AWS profile to use
    --skip-revoke        Only assign new permissions, don't revoke old ones
    --skip-assign        Only revoke old permissions, don't assign new ones
    --force              Skip confirmation prompt
    --help               Show this help message

EXAMPLES:
    # Rotate from Developer to PowerUser access
    $SCRIPT_NAME john.doe DeveloperAccess PowerUserAccess

    # Rotate with specific account filter
    $SCRIPT_NAME jane.smith ReadOnlyAccess ManagerAccess --filter "tag:Environment=Production"

    # Preview rotation with dry-run
    $SCRIPT_NAME bob.wilson InternAccess DeveloperAccess --dry-run

    # Only assign new permissions (don't revoke old)
    $SCRIPT_NAME alice.cooper ReadOnlyAccess PowerUserAccess --skip-revoke

    # Only revoke old permissions (don't assign new)
    $SCRIPT_NAME charlie.brown PowerUserAccess ReadOnlyAccess --skip-assign

COMMON ROTATION SCENARIOS:
    1. Intern to Full-time Developer:
       InternAccess → DeveloperAccess

    2. Developer to DevOps:
       DeveloperAccess → PowerUserAccess

    3. Individual Contributor to Manager:
       DeveloperAccess → ManagerAccess

    4. Contractor to Employee:
       ContractorAccess → DeveloperAccess

    5. Role Change within Department:
       AnalystAccess → ManagerAccess

SAFETY FEATURES:
    - Dry-run mode to preview all changes
    - Confirmation prompt for destructive operations
    - Detailed logging of all operations
    - Option to skip revocation or assignment phases
    - Rollback guidance if operations fail
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
    else
        error "User $username not found in AWS SSO"
        exit 1
    fi
}

# Validate permission set exists
validate_permission_set() {
    local permission_set=$1
    local description=$2

    log "Validating $description permission set: $permission_set"

    if awsideman permission-set get "$permission_set" &> /dev/null; then
        success "$description permission set $permission_set found"
    else
        error "$description permission set $permission_set not found"
        exit 1
    fi
}

# Execute revocation
execute_revocation() {
    local username=$1
    local permission_set=$2
    local filter=$3
    local batch_size=$4
    local dry_run_flag=$5

    local cmd="awsideman assignment revoke \"$permission_set\" \"$username\" --filter \"$filter\" --batch-size $batch_size"

    if [[ "$dry_run_flag" == "true" ]]; then
        cmd="$cmd --dry-run"
    fi

    log "Revoking: $cmd"

    if eval "$cmd"; then
        if [[ "$dry_run_flag" == "true" ]]; then
            success "Dry-run completed for revoking $permission_set"
        else
            success "Successfully revoked $permission_set"
        fi
        return 0
    else
        error "Failed to revoke $permission_set"
        return 1
    fi
}

# Execute assignment
execute_assignment() {
    local username=$1
    local permission_set=$2
    local filter=$3
    local batch_size=$4
    local dry_run_flag=$5

    local cmd="awsideman assignment multi-assign \"$permission_set\" \"$username\" --filter \"$filter\" --batch-size $batch_size"

    if [[ "$dry_run_flag" == "true" ]]; then
        cmd="$cmd --dry-run"
    fi

    log "Assigning: $cmd"

    if eval "$cmd"; then
        if [[ "$dry_run_flag" == "true" ]]; then
            success "Dry-run completed for assigning $permission_set"
        else
            success "Successfully assigned $permission_set"
        fi
        return 0
    else
        error "Failed to assign $permission_set"
        return 1
    fi
}

# Main rotation function
rotate_permissions() {
    local username=$1
    local old_permission_set=$2
    local new_permission_set=$3
    local filter=$4
    local batch_size=$5
    local dry_run_flag=$6
    local skip_revoke=$7
    local skip_assign=$8

    log "Starting permission rotation for $username"
    log "Old permission set: $old_permission_set"
    log "New permission set: $new_permission_set"
    log "Account filter: $filter"

    if [[ "$dry_run_flag" == "true" ]]; then
        warning "DRY-RUN MODE: No actual changes will be made"
    fi

    local revoke_success=true
    local assign_success=true

    # Phase 1: Revoke old permissions
    if [[ "$skip_revoke" == "false" ]]; then
        log "Phase 1: Revoking old permission set"
        if ! execute_revocation "$username" "$old_permission_set" "$filter" "$batch_size" "$dry_run_flag"; then
            revoke_success=false
            warning "Revocation phase failed, but continuing with assignment phase"
        fi
    else
        log "Phase 1: Skipping revocation as requested"
    fi

    # Small delay between phases
    if [[ "$dry_run_flag" == "false" ]]; then
        log "Waiting 5 seconds between phases..."
        sleep 5
    fi

    # Phase 2: Assign new permissions
    if [[ "$skip_assign" == "false" ]]; then
        log "Phase 2: Assigning new permission set"
        if ! execute_assignment "$username" "$new_permission_set" "$filter" "$batch_size" "$dry_run_flag"; then
            assign_success=false
            error "Assignment phase failed"
        fi
    else
        log "Phase 2: Skipping assignment as requested"
    fi

    # Summary
    log "Permission rotation summary for $username:"

    if [[ "$skip_revoke" == "false" ]]; then
        if [[ "$revoke_success" == "true" ]]; then
            log "  ✅ Revocation: SUCCESS"
        else
            log "  ❌ Revocation: FAILED"
        fi
    else
        log "  ⏭️  Revocation: SKIPPED"
    fi

    if [[ "$skip_assign" == "false" ]]; then
        if [[ "$assign_success" == "true" ]]; then
            log "  ✅ Assignment: SUCCESS"
        else
            log "  ❌ Assignment: FAILED"
        fi
    else
        log "  ⏭️  Assignment: SKIPPED"
    fi

    if [[ "$dry_run_flag" == "true" ]]; then
        success "Dry-run permission rotation completed for $username"
        log "Remove --dry-run flag to execute actual rotation"
    else
        if [[ "$revoke_success" == "true" && "$assign_success" == "true" ]]; then
            success "Permission rotation completed successfully for $username"
        elif [[ "$assign_success" == "true" && "$skip_revoke" == "true" ]]; then
            success "Permission assignment completed successfully for $username"
        elif [[ "$revoke_success" == "true" && "$skip_assign" == "true" ]]; then
            success "Permission revocation completed successfully for $username"
        else
            error "Permission rotation completed with errors for $username"

            # Provide rollback guidance
            echo
            warning "ROLLBACK GUIDANCE:"
            if [[ "$revoke_success" == "true" && "$assign_success" == "false" ]]; then
                warning "Old permissions were revoked but new permissions failed to assign."
                warning "To rollback, run:"
                warning "  $SCRIPT_NAME $username $new_permission_set $old_permission_set --filter \"$filter\" --skip-revoke"
            elif [[ "$revoke_success" == "false" && "$assign_success" == "true" ]]; then
                warning "New permissions were assigned but old permissions failed to revoke."
                warning "User now has both old and new permissions."
                warning "To clean up, manually revoke the old permissions:"
                warning "  awsideman assignment revoke \"$old_permission_set\" \"$username\" --filter \"$filter\""
            fi

            exit 1
        fi
    fi
}

# Parse command line arguments
parse_arguments() {
    local username=""
    local old_permission_set=""
    local new_permission_set=""
    local filter="*"
    local batch_size=$DEFAULT_BATCH_SIZE
    local profile=""
    local skip_revoke=false
    local skip_assign=false
    local force=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --filter)
                filter="$2"
                shift 2
                ;;
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
            --skip-revoke)
                skip_revoke=true
                shift
                ;;
            --skip-assign)
                skip_assign=true
                shift
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
                elif [[ -z "$old_permission_set" ]]; then
                    old_permission_set="$1"
                elif [[ -z "$new_permission_set" ]]; then
                    new_permission_set="$1"
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
    if [[ -z "$username" || -z "$old_permission_set" || -z "$new_permission_set" ]]; then
        error "Missing required arguments"
        usage
        exit 1
    fi

    # Validate conflicting options
    if [[ "$skip_revoke" == "true" && "$skip_assign" == "true" ]]; then
        error "Cannot skip both revoke and assign operations"
        exit 1
    fi

    # Validate batch size
    if ! [[ "$batch_size" =~ ^[0-9]+$ ]] || [[ "$batch_size" -lt 1 ]]; then
        error "Batch size must be a positive integer"
        exit 1
    fi

    echo "$username|$old_permission_set|$new_permission_set|$filter|$batch_size|$skip_revoke|$skip_assign|$force"
}

# Confirmation prompt
confirm_rotation() {
    local username=$1
    local old_permission_set=$2
    local new_permission_set=$3
    local filter=$4
    local skip_revoke=$5
    local skip_assign=$6
    local force=$7

    if [[ "$force" == "true" || "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    echo
    warning "You are about to rotate permissions for user: $username"
    echo "  Account Filter: $filter"

    if [[ "$skip_revoke" == "false" ]]; then
        echo "  Will REVOKE: $old_permission_set"
    fi

    if [[ "$skip_assign" == "false" ]]; then
        echo "  Will ASSIGN: $new_permission_set"
    fi

    echo
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Operation cancelled by user"
        exit 0
    fi

    log "User confirmed rotation operation"
}

# Main execution
main() {
    log "Starting $SCRIPT_NAME v$VERSION"

    # Parse arguments
    local args
    args=$(parse_arguments "$@")
    IFS='|' read -r username old_permission_set new_permission_set filter batch_size skip_revoke skip_assign force <<< "$args"

    # Validate prerequisites
    validate_prerequisites

    # Validate user exists
    validate_user "$username"

    # Validate permission sets exist
    if [[ "$skip_revoke" == "false" ]]; then
        validate_permission_set "$old_permission_set" "old"
    fi

    if [[ "$skip_assign" == "false" ]]; then
        validate_permission_set "$new_permission_set" "new"
    fi

    # Confirm operation
    confirm_rotation "$username" "$old_permission_set" "$new_permission_set" "$filter" "$skip_revoke" "$skip_assign" "$force"

    # Execute rotation
    rotate_permissions "$username" "$old_permission_set" "$new_permission_set" "$filter" "$batch_size" "$DRY_RUN" "$skip_revoke" "$skip_assign"

    log "Script completed successfully"
}

# Execute main function with all arguments
main "$@"
