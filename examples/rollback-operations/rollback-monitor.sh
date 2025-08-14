#!/bin/bash
# rollback-monitor.sh
# Monitoring script for rollback system health and statistics

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

# Configuration
ALERT_THRESHOLD_ROLLBACKS_PER_DAY=5
ALERT_THRESHOLD_FAILED_OPS_PERCENT=10
STORAGE_WARNING_THRESHOLD_MB=100
RETENTION_WARNING_DAYS=7

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --profile P     AWS profile to use"
    echo "  --days N        Number of days to analyze (default: 7)"
    echo "  --alert         Enable alerting mode (exit with error code on issues)"
    echo "  --json          Output in JSON format"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                          # Basic health check"
    echo "  $0 --days 30 --alert       # 30-day analysis with alerting"
    echo "  $0 --profile prod --json    # JSON output for production profile"
}

# Parse command line arguments
PROFILE=""
DAYS=7
ALERT_MODE=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --days)
            DAYS="$2"
            shift 2
            ;;
        --alert)
            ALERT_MODE=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
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

# Validate days parameter
if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [ "$DAYS" -lt 1 ]; then
    print_error "Days must be a positive number"
    exit 1
fi

# Build awsideman command with profile if specified
AWSIDEMAN_CMD="awsideman"
if [ -n "$PROFILE" ]; then
    AWSIDEMAN_CMD="$AWSIDEMAN_CMD --profile $PROFILE"
fi

# Initialize alert status
ALERT_STATUS=0
ALERTS=()

# Function to add alert
add_alert() {
    ALERTS+=("$1")
    if [ "$ALERT_MODE" = true ]; then
        ALERT_STATUS=1
    fi
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check dependencies
if ! command_exists jq; then
    print_error "jq is required but not installed"
    exit 1
fi

if [ "$JSON_OUTPUT" = false ]; then
    print_status "Rollback System Health Monitor"
    print_status "=============================="
    if [ -n "$PROFILE" ]; then
        print_status "AWS Profile: $PROFILE"
    fi
    print_status "Analysis Period: Last $DAYS days"
    print_status "Timestamp: $(date)"
    echo ""
fi

# Step 1: Check rollback system health
if [ "$JSON_OUTPUT" = false ]; then
    print_status "1. Checking rollback system health..."
fi

SYSTEM_HEALTHY=true
if ! $AWSIDEMAN_CMD rollback status > /dev/null 2>&1; then
    SYSTEM_HEALTHY=false
    add_alert "Rollback system health check failed"
fi

# Step 2: Get operation statistics
if [ "$JSON_OUTPUT" = false ]; then
    print_status "2. Analyzing operation statistics..."
fi

# Get operations data
OPERATIONS_JSON=$($AWSIDEMAN_CMD rollback list --format json --days "$DAYS" 2>/dev/null || echo '{"operations":[]}')

# Calculate statistics
TOTAL_OPS=$(echo "$OPERATIONS_JSON" | jq '.operations | length')
ASSIGN_OPS=$(echo "$OPERATIONS_JSON" | jq '[.operations[] | select(.operation_type == "assign")] | length')
REVOKE_OPS=$(echo "$OPERATIONS_JSON" | jq '[.operations[] | select(.operation_type == "revoke")] | length')
ROLLBACK_OPS=$(echo "$OPERATIONS_JSON" | jq '[.operations[] | select(.operation_type == "rollback")] | length')

# Calculate daily rollback rate
ROLLBACKS_PER_DAY=$(echo "scale=2; $ROLLBACK_OPS / $DAYS" | bc -l 2>/dev/null || echo "0")

# Check for high rollback frequency
if (( $(echo "$ROLLBACKS_PER_DAY > $ALERT_THRESHOLD_ROLLBACKS_PER_DAY" | bc -l) )); then
    add_alert "High rollback frequency: $ROLLBACKS_PER_DAY rollbacks per day (threshold: $ALERT_THRESHOLD_ROLLBACKS_PER_DAY)"
fi

# Step 3: Analyze operation success rates
if [ "$JSON_OUTPUT" = false ]; then
    print_status "3. Analyzing operation success rates..."
fi

# Calculate failed operations
FAILED_OPS=0
if [ "$TOTAL_OPS" -gt 0 ]; then
    FAILED_OPS=$(echo "$OPERATIONS_JSON" | jq '[.operations[] | select(.results[] | .success == false)] | length')
fi

FAILED_PERCENT=0
if [ "$TOTAL_OPS" -gt 0 ]; then
    FAILED_PERCENT=$(echo "scale=2; $FAILED_OPS * 100 / $TOTAL_OPS" | bc -l 2>/dev/null || echo "0")
fi

# Check for high failure rate
if (( $(echo "$FAILED_PERCENT > $ALERT_THRESHOLD_FAILED_OPS_PERCENT" | bc -l) )); then
    add_alert "High operation failure rate: ${FAILED_PERCENT}% (threshold: ${ALERT_THRESHOLD_FAILED_OPS_PERCENT}%)"
fi

# Step 4: Check storage usage
if [ "$JSON_OUTPUT" = false ]; then
    print_status "4. Checking storage usage..."
fi

STORAGE_DIR="$HOME/.awsideman/operations"
STORAGE_SIZE_MB=0
STORAGE_FILES=0

if [ -d "$STORAGE_DIR" ]; then
    STORAGE_SIZE_KB=$(du -sk "$STORAGE_DIR" 2>/dev/null | cut -f1 || echo "0")
    STORAGE_SIZE_MB=$(echo "scale=2; $STORAGE_SIZE_KB / 1024" | bc -l 2>/dev/null || echo "0")
    STORAGE_FILES=$(find "$STORAGE_DIR" -type f | wc -l)

    # Check storage size warning
    if (( $(echo "$STORAGE_SIZE_MB > $STORAGE_WARNING_THRESHOLD_MB" | bc -l) )); then
        add_alert "Storage usage is high: ${STORAGE_SIZE_MB}MB (threshold: ${STORAGE_WARNING_THRESHOLD_MB}MB)"
    fi
fi

# Step 5: Check recent rollback patterns
if [ "$JSON_OUTPUT" = false ]; then
    print_status "5. Analyzing rollback patterns..."
fi

# Get rollbacks from last 24 hours
RECENT_ROLLBACKS=$(echo "$OPERATIONS_JSON" | jq --arg date "$(date -d '1 day ago' -u +%Y-%m-%dT%H:%M:%SZ)" '[.operations[] | select(.operation_type == "rollback" and .timestamp > $date)] | length')

# Get most rolled back permission sets
TOP_ROLLED_BACK_PS=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.operation_type == "rollback")] | group_by(.permission_set_name) | map({permission_set: .[0].permission_set_name, count: length}) | sort_by(.count) | reverse | .[0:3]')

# Get most active principals in rollbacks
TOP_ROLLBACK_PRINCIPALS=$(echo "$OPERATIONS_JSON" | jq -r '[.operations[] | select(.operation_type == "rollback")] | group_by(.principal_name) | map({principal: .[0].principal_name, count: length}) | sort_by(.count) | reverse | .[0:3]')

# Step 6: Check configuration
if [ "$JSON_OUTPUT" = false ]; then
    print_status "6. Checking configuration..."
fi

CONFIG_FILE="$HOME/.awsideman/config.yaml"
CONFIG_ISSUES=()

if [ -f "$CONFIG_FILE" ]; then
    # Check if rollback is enabled
    if ! grep -q "rollback:" "$CONFIG_FILE" 2>/dev/null; then
        CONFIG_ISSUES+=("Rollback configuration not found in config file")
    fi

    # Check retention settings
    RETENTION_DAYS=$(grep -A 10 "rollback:" "$CONFIG_FILE" 2>/dev/null | grep "retention_days:" | sed 's/.*retention_days: *//' | head -1)
    if [ -n "$RETENTION_DAYS" ] && [ "$RETENTION_DAYS" -lt "$RETENTION_WARNING_DAYS" ]; then
        add_alert "Short retention period: ${RETENTION_DAYS} days (recommended: >${RETENTION_WARNING_DAYS} days)"
    fi
else
    CONFIG_ISSUES+=("Configuration file not found")
fi

# Generate output
if [ "$JSON_OUTPUT" = true ]; then
    # JSON output
    cat << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "profile": "${PROFILE:-default}",
  "analysis_period_days": $DAYS,
  "system_health": {
    "healthy": $SYSTEM_HEALTHY,
    "alerts": $(printf '%s\n' "${ALERTS[@]}" | jq -R . | jq -s .)
  },
  "operation_statistics": {
    "total_operations": $TOTAL_OPS,
    "assign_operations": $ASSIGN_OPS,
    "revoke_operations": $REVOKE_OPS,
    "rollback_operations": $ROLLBACK_OPS,
    "rollbacks_per_day": $ROLLBACKS_PER_DAY,
    "recent_rollbacks_24h": $RECENT_ROLLBACKS,
    "failed_operations": $FAILED_OPS,
    "failure_rate_percent": $FAILED_PERCENT
  },
  "storage": {
    "directory": "$STORAGE_DIR",
    "size_mb": $STORAGE_SIZE_MB,
    "file_count": $STORAGE_FILES
  },
  "top_rolled_back_permission_sets": $TOP_ROLLED_BACK_PS,
  "top_rollback_principals": $TOP_ROLLBACK_PRINCIPALS,
  "configuration_issues": $(printf '%s\n' "${CONFIG_ISSUES[@]}" | jq -R . | jq -s .),
  "alert_status": $ALERT_STATUS
}
EOF
else
    # Human-readable output
    echo ""
    print_status "SUMMARY"
    print_status "======="

    if [ "$SYSTEM_HEALTHY" = true ]; then
        print_success "System Health: HEALTHY"
    else
        print_error "System Health: UNHEALTHY"
    fi

    echo ""
    print_status "Operation Statistics ($DAYS days):"
    echo "  Total Operations: $TOTAL_OPS"
    echo "  - Assignments: $ASSIGN_OPS"
    echo "  - Revocations: $REVOKE_OPS"
    echo "  - Rollbacks: $ROLLBACK_OPS"
    echo "  Rollbacks per day: $ROLLBACKS_PER_DAY"
    echo "  Recent rollbacks (24h): $RECENT_ROLLBACKS"
    echo "  Failed operations: $FAILED_OPS (${FAILED_PERCENT}%)"

    echo ""
    print_status "Storage Usage:"
    echo "  Directory: $STORAGE_DIR"
    echo "  Size: ${STORAGE_SIZE_MB}MB"
    echo "  Files: $STORAGE_FILES"

    if [ ${#CONFIG_ISSUES[@]} -gt 0 ]; then
        echo ""
        print_warning "Configuration Issues:"
        for issue in "${CONFIG_ISSUES[@]}"; do
            echo "  - $issue"
        done
    fi

    if [ ${#ALERTS[@]} -gt 0 ]; then
        echo ""
        print_warning "ALERTS:"
        for alert in "${ALERTS[@]}"; do
            print_warning "  - $alert"
        done
    else
        echo ""
        print_success "No alerts detected"
    fi

    # Show top patterns if there are rollbacks
    if [ "$ROLLBACK_OPS" -gt 0 ]; then
        echo ""
        print_status "Top Rolled Back Permission Sets:"
        echo "$TOP_ROLLED_BACK_PS" | jq -r '.[] | "  - \(.permission_set): \(.count) rollbacks"'

        echo ""
        print_status "Top Principals with Rollbacks:"
        echo "$TOP_ROLLBACK_PRINCIPALS" | jq -r '.[] | "  - \(.principal): \(.count) rollbacks"'
    fi

    echo ""
    print_status "Recommendations:"

    if [ "$ROLLBACK_OPS" -gt 0 ]; then
        echo "  - Review rollback patterns to identify process improvements"
        echo "  - Consider additional validation for frequently rolled back operations"
    fi

    if (( $(echo "$FAILED_PERCENT > 5" | bc -l) )); then
        echo "  - Investigate causes of operation failures"
        echo "  - Review AWS permissions and service limits"
    fi

    if (( $(echo "$STORAGE_SIZE_MB > 50" | bc -l) )); then
        echo "  - Consider enabling auto-cleanup for old operations"
        echo "  - Review retention period settings"
    fi

    echo "  - Regular monitoring helps maintain system health"
    echo "  - Use --alert flag for automated monitoring"
fi

# Exit with appropriate code
exit $ALERT_STATUS
