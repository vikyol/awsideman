#!/bin/bash
# bulk-rollback.sh
# Script for rolling back multiple operations with safety checks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --days N            Rollback operations from last N days (default: 1)"
    echo "  --operation-type T  Filter by operation type: assign, revoke (optional)"
    echo "  --principal P       Filter by principal name (optional)"
    echo "  --permission-set PS Filter by permission set name (optional)"
    echo "  --profile PROFILE   AWS profile to use (optional)"
    echo "  --batch-size N      Batch size for rollback operations (default: 10)"
    echo "  --force             Skip individual confirmations (dangerous!)"
    echo "  --dry-run           Preview all rollbacks without executing"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --days 1                                    # Rollback all operations from last day"
    echo "  $0 --operation-type assign --principal john.doe # Rollback john.doe's assignments"
    echo "  $0 --permission-set AdminAccess --dry-run       # Preview AdminAccess rollbacks"
    echo "  $0 --days 7 --force                            # Rollback last 7 days (no confirmation)"
}

# Parse command line arguments
DAYS=1
OPERATION_TYPE=""
PRINCIPAL=""
PERMISSION_SET=""
PROFILE=""
BATCH_SIZE=10
FORCE=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --days)
            DAYS="$2"
            shift 2
            ;;
        --operation-type)
            OPERATION_TYPE="$2"
            shift 2
            ;;
        --principal)
            PRINCIPAL="$2"
            shift 2
            ;;
        --permission-set)
            PERMISSION_SET="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate parameters
if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [ "$DAYS" -lt 1 ]; then
    print_error "Days must be a positive number"
    exit 1
fi

if [ -n "$OPERATION_TYPE" ] && [[ ! "$OPERATION_TYPE" =~ ^(assign|revoke)$ ]]; then
    print_error "Operation type must be 'assign' or 'revoke'"
    exit 1
fi

if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE" -lt 1 ] || [ "$BATCH_SIZE" -gt 20 ]; then
    print_error "Batch size must be a number between 1 and 20"
    exit 1
fi

# Check dependencies
if ! command -v jq >/dev/null 2>&1; then
    print_error "jq is required but not installed"
    exit 1
fi

# Build awsideman command with profile if specified
AWSIDEMAN_CMD="awsideman"
if [ -n "$PROFILE" ]; then
    AWSIDEMAN_CMD="$AWSIDEMAN_CMD --profile $PROFILE"
fi

print_status "Bulk Rollback Script"
print_status "==================="
print_status "Days: $DAYS"
if [ -n "$OPERATION_TYPE" ]; then
    print_status "Operation Type: $OPERATION_TYPE"
fi
if [ -n "$PRINCIPAL" ]; then
    print_status "Principal: $PRINCIPAL"
fi
if [ -n "$PERMISSION_SET" ]; then
    print_status "Permission Set: $PERMISSION_SET"
fi
if [ -n "$PROFILE" ]; then
    print_status "AWS Profile: $PROFILE"
fi
print_status "Batch Size: $BATCH_SIZE"
print_status "Force Mode: $FORCE"
print_status "Dry Run: $DRY_RUN"
echo ""

# Step 1: Check rollback system health
print_status "Step 1: Checking rollback system health..."
if ! $AWSIDEMAN_CMD rollback status > /dev/null 2>&1; then
    print_error "Rollback system health check failed"
    exit 1
fi
print_success "Rollback system is healthy"
echo ""

# Step 2: Build filter command
print_status "Step 2: Retrieving operations to rollback..."

LIST_CMD="$AWSIDEMAN_CMD rollback list --format json --days $DAYS"
if [ -n "$OPERATION_TYPE" ]; then
    LIST_CMD="$LIST_CMD --operation-type $OPERATION_TYPE"
fi
if [ -n "$PRINCIPAL" ]; then
    LIST_CMD="$LIST_CMD --principal $PRINCIPAL"
fi
if [ -n "$PERMISSION_SET" ]; then
    LIST_CMD="$LIST_CMD --permission-set $PERMISSION_SET"
fi

# Get operations
OPERATIONS_JSON=$(eval "$LIST_CMD" 2>/dev/null || echo '{"operations":[]}')

# Filter out already rolled back operations and rollback operations themselves
ELIGIBLE_OPS=$(echo "$OPERATIONS_JSON" | jq -r '.operations[] | select(.rolled_back == false and .operation_type != "rollback") | .operation_id')

if [ -z "$ELIGIBLE_OPS" ]; then
    print_warning "No eligible operations found for rollback"
    print_status "Criteria:"
    print_status "  - Not already rolled back"
    print_status "  - Not rollback operations themselves"
    print_status "  - Within specified time period and filters"
    exit 0
fi

# Count operations
OP_COUNT=$(echo "$ELIGIBLE_OPS" | wc -l)
print_success "Found $OP_COUNT operations eligible for rollback"
echo ""

# Step 3: Display operations to be rolled back
print_status "Step 3: Operations to be rolled back:"
echo "$OPERATIONS_JSON" | jq -r '.operations[] | select(.rolled_back == false and .operation_type != "rollback") |
    "  " + .operation_id + " | " + .timestamp + " | " + .operation_type + " | " + .principal_name + " | " + .permission_set_name + " | " + (.account_ids | length | tostring) + " accounts"'
echo ""

# Step 4: Safety confirmation
if [ "$FORCE" = false ] && [ "$DRY_RUN" = false ]; then
    print_warning "WARNING: This will rollback $OP_COUNT operations"
    print_warning "This action will modify AWS Identity Center permissions"
    echo ""

    # Show impact summary
    print_status "Impact Summary:"
    ASSIGN_COUNT=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.rolled_back == false and .operation_type == "assign")] | length')
    REVOKE_COUNT=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.rolled_back == false and .operation_type == "revoke")] | length')
    TOTAL_ACCOUNTS=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.rolled_back == false and .operation_type != "rollback") | .account_ids[]] | unique | length')
    UNIQUE_PRINCIPALS=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.rolled_back == false and .operation_type != "rollback") | .principal_name] | unique | length')

    echo "  - $ASSIGN_COUNT assignments will be revoked"
    echo "  - $REVOKE_COUNT revocations will be re-assigned"
    echo "  - $UNIQUE_PRINCIPALS unique principals affected"
    echo "  - $TOTAL_ACCOUNTS unique accounts affected"
    echo ""

    read -p "Are you sure you want to proceed? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_status "Bulk rollback cancelled by user"
        exit 0
    fi

    # Additional confirmation for large operations
    if [ "$OP_COUNT" -gt 10 ]; then
        print_warning "This is a large bulk rollback operation ($OP_COUNT operations)"
        read -p "Please confirm again that you want to proceed (y/N): " confirm2
        if [ "$confirm2" != "y" ] && [ "$confirm2" != "Y" ]; then
            print_status "Bulk rollback cancelled by user"
            exit 0
        fi
    fi
fi

# Step 5: Execute rollbacks
print_status "Step 4: Executing rollbacks..."
print_status "Started at: $(date)"

SUCCESSFUL_ROLLBACKS=0
FAILED_ROLLBACKS=0
SKIPPED_ROLLBACKS=0

# Create log file for this bulk rollback session
LOG_FILE="$HOME/.awsideman/bulk-rollback-$(date +%Y%m%d-%H%M%S).log"
echo "Bulk rollback session started at $(date)" > "$LOG_FILE"
echo "Parameters: days=$DAYS, operation_type=$OPERATION_TYPE, principal=$PRINCIPAL, permission_set=$PERMISSION_SET" >> "$LOG_FILE"
echo "Total operations to rollback: $OP_COUNT" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Process each operation
CURRENT=0
for op_id in $ELIGIBLE_OPS; do
    CURRENT=$((CURRENT + 1))
    print_status "Processing operation $CURRENT/$OP_COUNT: $op_id"

    # Get operation details for logging
    OP_DETAILS=$(echo "$OPERATIONS_JSON" | jq -r ".operations[] | select(.operation_id == \"$op_id\")")
    OP_TYPE=$(echo "$OP_DETAILS" | jq -r '.operation_type')
    OP_PRINCIPAL=$(echo "$OP_DETAILS" | jq -r '.principal_name')
    OP_PERMISSION_SET=$(echo "$OP_DETAILS" | jq -r '.permission_set_name')

    echo "[$CURRENT/$OP_COUNT] Processing $op_id ($OP_TYPE $OP_PERMISSION_SET for $OP_PRINCIPAL)" >> "$LOG_FILE"

    # Build rollback command
    ROLLBACK_CMD="$AWSIDEMAN_CMD rollback apply \"$op_id\" --batch-size $BATCH_SIZE"
    if [ "$DRY_RUN" = true ]; then
        ROLLBACK_CMD="$ROLLBACK_CMD --dry-run"
    elif [ "$FORCE" = true ]; then
        ROLLBACK_CMD="$ROLLBACK_CMD --yes"
    fi

    # Execute rollback
    if eval "$ROLLBACK_CMD" >> "$LOG_FILE" 2>&1; then
        if [ "$DRY_RUN" = true ]; then
            print_success "  ✓ Dry-run successful"
            echo "  Result: Dry-run successful" >> "$LOG_FILE"
        else
            print_success "  ✓ Rollback successful"
            echo "  Result: Rollback successful" >> "$LOG_FILE"
            SUCCESSFUL_ROLLBACKS=$((SUCCESSFUL_ROLLBACKS + 1))
        fi
    else
        print_error "  ✗ Rollback failed"
        echo "  Result: Rollback failed" >> "$LOG_FILE"
        FAILED_ROLLBACKS=$((FAILED_ROLLBACKS + 1))

        # Ask user if they want to continue on failure
        if [ "$FORCE" = false ] && [ "$DRY_RUN" = false ]; then
            read -p "  Continue with remaining rollbacks? (y/N): " continue_confirm
            if [ "$continue_confirm" != "y" ] && [ "$continue_confirm" != "Y" ]; then
                print_status "Bulk rollback stopped by user"
                SKIPPED_ROLLBACKS=$((OP_COUNT - CURRENT))
                break
            fi
        fi
    fi

    echo "" >> "$LOG_FILE"

    # Add small delay to avoid overwhelming AWS APIs
    if [ "$CURRENT" -lt "$OP_COUNT" ]; then
        sleep 1
    fi
done

print_status "Completed at: $(date)"
echo ""

# Step 6: Summary
print_status "BULK ROLLBACK SUMMARY"
print_status "===================="

if [ "$DRY_RUN" = true ]; then
    print_status "Mode: DRY RUN (no changes made)"
    print_status "Operations analyzed: $OP_COUNT"
    print_status "Successful previews: $((OP_COUNT - FAILED_ROLLBACKS))"
    print_status "Failed previews: $FAILED_ROLLBACKS"
else
    print_status "Total operations processed: $OP_COUNT"
    print_success "Successful rollbacks: $SUCCESSFUL_ROLLBACKS"
    if [ "$FAILED_ROLLBACKS" -gt 0 ]; then
        print_error "Failed rollbacks: $FAILED_ROLLBACKS"
    fi
    if [ "$SKIPPED_ROLLBACKS" -gt 0 ]; then
        print_warning "Skipped rollbacks: $SKIPPED_ROLLBACKS"
    fi
fi

echo ""
print_status "Session log saved to: $LOG_FILE"

# Add summary to log file
echo "" >> "$LOG_FILE"
echo "Bulk rollback session completed at $(date)" >> "$LOG_FILE"
echo "Summary:" >> "$LOG_FILE"
echo "  Total operations: $OP_COUNT" >> "$LOG_FILE"
echo "  Successful: $SUCCESSFUL_ROLLBACKS" >> "$LOG_FILE"
echo "  Failed: $FAILED_ROLLBACKS" >> "$LOG_FILE"
echo "  Skipped: $SKIPPED_ROLLBACKS" >> "$LOG_FILE"

# Show recent operations for verification
if [ "$DRY_RUN" = false ] && [ "$SUCCESSFUL_ROLLBACKS" -gt 0 ]; then
    echo ""
    print_status "Recent rollback operations (for verification):"
    $AWSIDEMAN_CMD rollback list --days 1 --operation-type rollback
fi

# Recommendations
echo ""
print_status "Recommendations:"
echo "  1. Verify the rollbacks in AWS Identity Center console"
echo "  2. Document the reason for this bulk rollback"
echo "  3. Review the original operations to prevent similar issues"
echo "  4. Consider implementing additional safeguards if needed"
echo "  5. Notify relevant stakeholders about the rollbacks"

if [ "$FAILED_ROLLBACKS" -gt 0 ]; then
    echo ""
    print_warning "Some rollbacks failed. Check the log file for details:"
    print_warning "  $LOG_FILE"
    print_warning "You may need to manually review and retry failed operations"
fi

# Exit with appropriate code
if [ "$FAILED_ROLLBACKS" -gt 0 ]; then
    exit 1
else
    exit 0
fi
