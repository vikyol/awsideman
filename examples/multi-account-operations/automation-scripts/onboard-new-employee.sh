#!/bin/bash

# onboard-new-employee.sh
# Automated script for onboarding new employees with appropriate AWS permissions

set -e  # Exit on any error

# Script configuration
SCRIPT_NAME="onboard-new-employee.sh"
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

Automated script for onboarding new employees with appropriate AWS permissions.

USAGE:
    $SCRIPT_NAME <username> <department> <role> [OPTIONS]

ARGUMENTS:
    username     Username of the new employee
    department   Department (Engineering, Finance, HR, Marketing, etc.)
    role         Role (Developer, Manager, Analyst, DevOps, etc.)

OPTIONS:
    --dry-run           Preview operations without making changes
    --batch-size N      Number of accounts to process concurrently (default: $DEFAULT_BATCH_SIZE)
    --profile PROFILE   AWS profile to use
    --help             Show this help message

EXAMPLES:
    # Onboard a developer
    $SCRIPT_NAME john.doe Engineering Developer

    # Onboard a manager with dry-run
    $SCRIPT_NAME jane.smith Finance Manager --dry-run

    # Onboard with custom batch size
    $SCRIPT_NAME bob.wilson HR Analyst --batch-size 3

SUPPORTED ROLES:
    Developer    - Development environment access
    DevOps       - Development and staging environment access
    Manager      - Department-wide access
    Analyst      - Read-only access with department-specific permissions
    Intern       - Limited development environment access
    Contractor   - Restricted access based on department

SUPPORTED DEPARTMENTS:
    Engineering, Finance, HR, Marketing, Sales, Operations, Security
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

# Get permission sets for role
get_permission_sets_for_role() {
    local role=$1
    local department=$2

    case $role in
        "Developer")
            echo "ReadOnlyAccess DeveloperAccess"
            ;;
        "DevOps")
            echo "ReadOnlyAccess PowerUserAccess"
            ;;
        "Manager")
            echo "ReadOnlyAccess ManagerAccess"
            ;;
        "Analyst")
            echo "ReadOnlyAccess AnalystAccess"
            ;;
        "Intern")
            echo "ReadOnlyAccess InternAccess"
            ;;
        "Contractor")
            echo "ReadOnlyAccess ContractorAccess"
            ;;
        *)
            echo "ReadOnlyAccess"
            ;;
    esac
}

# Get environments for role
get_environments_for_role() {
    local role=$1

    case $role in
        "Developer"|"Intern")
            echo "Development"
            ;;
        "DevOps")
            echo "Development Staging"
            ;;
        "Manager")
            echo "Development Staging Production"
            ;;
        "Analyst"|"Contractor")
            echo "Development"
            ;;
        *)
            echo "Development"
            ;;
    esac
}

# Execute assignment
execute_assignment() {
    local username=$1
    local permission_set=$2
    local filter=$3
    local batch_size=$4
    local dry_run_flag=$5

    local cmd="awsideman assignment assign \"$permission_set\" \"$username\" --filter \"$filter\" --batch-size $batch_size"

    if [[ "$dry_run_flag" == "true" ]]; then
        cmd="$cmd --dry-run"
    fi

    log "Executing: $cmd"

    if eval "$cmd"; then
        if [[ "$dry_run_flag" == "true" ]]; then
            success "Dry-run completed for $permission_set with filter: $filter"
        else
            success "Assigned $permission_set with filter: $filter"
        fi
    else
        error "Failed to assign $permission_set with filter: $filter"
        return 1
    fi
}

# Main onboarding function
onboard_employee() {
    local username=$1
    local department=$2
    local role=$3
    local batch_size=$4
    local dry_run_flag=$5

    log "Starting onboarding process for $username"
    log "Department: $department, Role: $role"

    if [[ "$dry_run_flag" == "true" ]]; then
        warning "DRY-RUN MODE: No actual changes will be made"
    fi

    # Step 1: Assign basic read access to all accounts
    log "Step 1: Assigning basic read access to all accounts"
    execute_assignment "$username" "ReadOnlyAccess" "*" "$batch_size" "$dry_run_flag"

    # Step 2: Assign department-specific access
    log "Step 2: Assigning department-specific access"
    execute_assignment "$username" "DepartmentAccess" "tag:Department=$department" "$batch_size" "$dry_run_flag"

    # Step 3: Assign role-specific permissions
    log "Step 3: Assigning role-specific permissions"

    local permission_sets
    permission_sets=$(get_permission_sets_for_role "$role" "$department")

    local environments
    environments=$(get_environments_for_role "$role")

    for permission_set in $permission_sets; do
        if [[ "$permission_set" == "ReadOnlyAccess" ]]; then
            continue  # Already assigned in step 1
        fi

        for environment in $environments; do
            log "Assigning $permission_set to $environment environment"
            execute_assignment "$username" "$permission_set" "tag:Environment=$environment" "$batch_size" "$dry_run_flag"
        done
    done

    # Step 4: Summary
    if [[ "$dry_run_flag" == "true" ]]; then
        success "Dry-run onboarding completed for $username"
        log "Remove --dry-run flag to execute actual assignments"
    else
        success "Onboarding completed successfully for $username"
        log "User $username now has appropriate access based on role: $role"
    fi
}

# Parse command line arguments
parse_arguments() {
    local username=""
    local department=""
    local role=""
    local batch_size=$DEFAULT_BATCH_SIZE
    local profile=""

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
                elif [[ -z "$department" ]]; then
                    department="$1"
                elif [[ -z "$role" ]]; then
                    role="$1"
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
    if [[ -z "$username" || -z "$department" || -z "$role" ]]; then
        error "Missing required arguments"
        usage
        exit 1
    fi

    # Validate batch size
    if ! [[ "$batch_size" =~ ^[0-9]+$ ]] || [[ "$batch_size" -lt 1 ]]; then
        error "Batch size must be a positive integer"
        exit 1
    fi

    echo "$username|$department|$role|$batch_size"
}

# Main execution
main() {
    log "Starting $SCRIPT_NAME v$VERSION"

    # Parse arguments
    local args
    args=$(parse_arguments "$@")
    IFS='|' read -r username department role batch_size <<< "$args"

    # Validate prerequisites
    validate_prerequisites

    # Validate user exists
    validate_user "$username"

    # Confirm operation if not dry-run
    if [[ "$DRY_RUN" == "false" ]]; then
        echo
        warning "You are about to onboard $username with the following configuration:"
        echo "  Username: $username"
        echo "  Department: $department"
        echo "  Role: $role"
        echo "  Batch Size: $batch_size"
        echo
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Operation cancelled by user"
            exit 0
        fi
    fi

    # Execute onboarding
    onboard_employee "$username" "$department" "$role" "$batch_size" "$DRY_RUN"

    log "Script completed successfully"
}

# Execute main function with all arguments
main "$@"
