#!/bin/bash
# emergency-rollback.sh
# Emergency rollback script with safety checks and confirmation

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
    echo "Usage: $0 <operation-id> [options]"
    echo ""
    echo "Options:"
    echo "  --force, -f     Skip confirmation prompts"
    echo "  --batch-size N  Set batch size for rollback (default: 10)"
    echo "  --profile P     AWS profile to use"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 abc123-def456-ghi789"
    echo "  $0 abc123-def456-ghi789 --force --batch-size 5"
    echo "  $0 abc123-def456-ghi789 --profile production"
}

# Parse command line arguments
OPERATION_ID=""
FORCE=false
BATCH_SIZE=10
PROFILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f)
            FORCE=true
            shift
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        -*)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            if [ -z "$OPERATION_ID" ]; then
                OPERATION_ID="$1"
            else
                print_error "Multiple operation IDs provided"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate required arguments
if [ -z "$OPERATION_ID" ]; then
    print_error "Operation ID is required"
    show_usage
    exit 1
fi

# Validate batch size
if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE" -lt 1 ] || [ "$BATCH_SIZE" -gt 20 ]; then
    print_error "Batch size must be a number between 1 and 20"
    exit 1
fi

# Build awsideman command with profile if specified
AWSIDEMAN_CMD="awsideman"
if [ -n "$PROFILE" ]; then
    AWSIDEMAN_CMD="$AWSIDEMAN_CMD --profile $PROFILE"
fi

print_status "Emergency Rollback Script"
print_status "========================="
print_status "Operation ID: $OPERATION_ID"
print_status "Batch Size: $BATCH_SIZE"
if [ -n "$PROFILE" ]; then
    print_status "AWS Profile: $PROFILE"
fi
print_status "Force Mode: $FORCE"
echo ""

# Step 1: Check rollback system health
print_status "Step 1: Checking rollback system health..."
if ! $AWSIDEMAN_CMD rollback status > /dev/null 2>&1; then
    print_error "Rollback system health check failed"
    print_error "Please check your configuration and try again"
    exit 1
fi
print_success "Rollback system is healthy"
echo ""

# Step 2: Verify operation exists
print_status "Step 2: Verifying operation exists..."
OPERATION_INFO=$($AWSIDEMAN_CMD rollback list --format json --days 365 2>/dev/null | jq -r ".operations[] | select(.operation_id == \"$OPERATION_ID\")")

if [ -z "$OPERATION_INFO" ]; then
    print_error "Operation with ID '$OPERATION_ID' not found"
    print_warning "Available operations from the last 30 days:"
    $AWSIDEMAN_CMD rollback list --days 30
    exit 1
fi

# Extract operation details
OP_TYPE=$(echo "$OPERATION_INFO" | jq -r '.operation_type')
OP_PRINCIPAL=$(echo "$OPERATION_INFO" | jq -r '.principal_name')
OP_PERMISSION_SET=$(echo "$OPERATION_INFO" | jq -r '.permission_set_name')
OP_ACCOUNTS=$(echo "$OPERATION_INFO" | jq -r '.account_ids | length')
OP_TIMESTAMP=$(echo "$OPERATION_INFO" | jq -r '.timestamp')
OP_ROLLED_BACK=$(echo "$OPERATION_INFO" | jq -r '.rolled_back')

print_success "Operation found"
echo "  Type: $OP_TYPE"
echo "  Principal: $OP_PRINCIPAL"
echo "  Permission Set: $OP_PERMISSION_SET"
echo "  Accounts: $OP_ACCOUNTS"
echo "  Timestamp: $OP_TIMESTAMP"
echo "  Already Rolled Back: $OP_ROLLED_BACK"
echo ""

# Step 3: Check if already rolled back
if [ "$OP_ROLLED_BACK" = "true" ]; then
    print_warning "This operation has already been rolled back"
    if [ "$FORCE" = false ]; then
        read -p "Do you want to continue anyway? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            print_status "Rollback cancelled"
            exit 0
        fi
    fi
fi

# Step 4: Preview rollback
print_status "Step 3: Previewing rollback operation..."
echo "This will perform the following rollback:"
if [ "$OP_TYPE" = "assign" ]; then
    echo "  Action: REVOKE $OP_PERMISSION_SET from $OP_PRINCIPAL"
elif [ "$OP_TYPE" = "revoke" ]; then
    echo "  Action: ASSIGN $OP_PERMISSION_SET to $OP_PRINCIPAL"
else
    echo "  Action: ROLLBACK $OP_TYPE operation"
fi
echo "  Accounts affected: $OP_ACCOUNTS"
echo ""

# Run dry-run to show detailed preview
print_status "Detailed rollback preview:"
if ! $AWSIDEMAN_CMD rollback apply --dry-run "$OPERATION_ID" --batch-size "$BATCH_SIZE"; then
    print_error "Rollback preview failed"
    print_error "This may indicate issues with the current AWS state"
    exit 1
fi
echo ""

# Step 5: Confirmation
if [ "$FORCE" = false ]; then
    print_warning "WARNING: This will modify AWS Identity Center permissions"
    print_warning "Make sure you understand the impact before proceeding"
    echo ""

    # Show current time for audit trail
    print_status "Current time: $(date)"
    echo ""

    read -p "Are you sure you want to proceed with this rollback? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_status "Rollback cancelled by user"
        exit 0
    fi

    # Double confirmation for high-privilege operations
    if [[ "$OP_PERMISSION_SET" == *"Admin"* ]] || [[ "$OP_PERMISSION_SET" == *"Full"* ]]; then
        print_warning "This operation involves high-privilege permissions"
        read -p "Please confirm again that you want to rollback this operation (y/N): " confirm2
        if [ "$confirm2" != "y" ] && [ "$confirm2" != "Y" ]; then
            print_status "Rollback cancelled by user"
            exit 0
        fi
    fi
fi

# Step 6: Execute rollback
print_status "Step 4: Executing rollback..."
print_status "Started at: $(date)"

# Build rollback command
ROLLBACK_CMD="$AWSIDEMAN_CMD rollback apply \"$OPERATION_ID\" --batch-size $BATCH_SIZE"
if [ "$FORCE" = true ]; then
    ROLLBACK_CMD="$ROLLBACK_CMD --yes"
fi

# Execute rollback with error handling
if eval "$ROLLBACK_CMD"; then
    print_success "Rollback completed successfully"
    print_status "Completed at: $(date)"

    # Log the rollback for audit purposes
    LOG_FILE="$HOME/.awsideman/emergency-rollbacks.log"
    echo "$(date): Emergency rollback of operation $OPERATION_ID completed by $(whoami)" >> "$LOG_FILE"
    print_status "Rollback logged to: $LOG_FILE"

else
    print_error "Rollback failed"
    print_error "Please check the error messages above and try again"

    # Log the failed rollback
    LOG_FILE="$HOME/.awsideman/emergency-rollbacks.log"
    echo "$(date): Emergency rollback of operation $OPERATION_ID FAILED for $(whoami)" >> "$LOG_FILE"

    exit 1
fi

# Step 7: Verification
print_status "Step 5: Verifying rollback..."
sleep 2  # Give AWS a moment to process

# Check if rollback was logged
ROLLBACK_OPS=$($AWSIDEMAN_CMD rollback list --format json --days 1 2>/dev/null | jq -r "[.operations[] | select(.operation_type == \"rollback\")] | length")
print_status "New rollback operations logged: $ROLLBACK_OPS"

# Show recent operations for verification
print_status "Recent operations (for verification):"
$AWSIDEMAN_CMD rollback list --days 1

echo ""
print_success "Emergency rollback procedure completed"
print_status "Please verify the changes in AWS Identity Center console"
print_status "Consider documenting the reason for this rollback in your change management system"

# Reminder about follow-up actions
echo ""
print_warning "Follow-up actions to consider:"
echo "  1. Verify the rollback in AWS Identity Center console"
echo "  2. Document the reason for this rollback"
echo "  3. Review the original operation to prevent similar issues"
echo "  4. Consider implementing additional safeguards if needed"
echo "  5. Notify relevant stakeholders about the rollback"
