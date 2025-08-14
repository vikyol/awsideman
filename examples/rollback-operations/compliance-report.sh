#!/bin/bash
# compliance-report.sh
# Generate compliance reports from rollback operation history

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
    echo "  --profile P     AWS profile to use"
    echo "  --days N        Number of days to analyze (default: 90)"
    echo "  --output FILE   Output file for report (default: compliance-report.json)"
    echo "  --format FORMAT Report format: json, csv, html (default: json)"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # 90-day report in JSON"
    echo "  $0 --days 365 --format html          # Annual report in HTML"
    echo "  $0 --profile prod --output audit.csv # Production audit in CSV"
}

# Parse command line arguments
PROFILE=""
DAYS=90
OUTPUT_FILE="compliance-report.json"
FORMAT="json"

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
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --format)
            FORMAT="$2"
            shift 2
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

if [[ ! "$FORMAT" =~ ^(json|csv|html)$ ]]; then
    print_error "Format must be json, csv, or html"
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

print_status "Generating Compliance Report"
print_status "============================"
if [ -n "$PROFILE" ]; then
    print_status "AWS Profile: $PROFILE"
fi
print_status "Analysis Period: Last $DAYS days"
print_status "Output Format: $FORMAT"
print_status "Output File: $OUTPUT_FILE"
print_status "Timestamp: $(date)"
echo ""

# Get operations data
print_status "Retrieving operation data..."
OPERATIONS_JSON=$($AWSIDEMAN_CMD rollback list --format json --days "$DAYS" 2>/dev/null || echo '{"operations":[]}')

if [ "$(echo "$OPERATIONS_JSON" | jq '.operations | length')" -eq 0 ]; then
    print_warning "No operations found in the specified time period"
    exit 0
fi

print_success "Retrieved $(echo "$OPERATIONS_JSON" | jq '.operations | length') operations"

# Generate report data
print_status "Analyzing operation data..."

REPORT_DATA=$(echo "$OPERATIONS_JSON" | jq --arg start_date "$(date -d "$DAYS days ago" -u +%Y-%m-%dT%H:%M:%SZ)" --arg end_date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg profile "${PROFILE:-default}" '
{
  "report_metadata": {
    "generated_at": $end_date,
    "period_start": $start_date,
    "period_end": $end_date,
    "days_analyzed": '$DAYS',
    "aws_profile": $profile,
    "total_operations": (.operations | length)
  },
  "summary_statistics": {
    "total_operations": (.operations | length),
    "operations_by_type": [
      .operations | group_by(.operation_type) | .[] | {
        "type": .[0].operation_type,
        "count": length,
        "percentage": ((length * 100) / (.operations | length) | round)
      }
    ],
    "operations_by_principal_type": [
      .operations | group_by(.principal_type) | .[] | {
        "type": .[0].principal_type,
        "count": length,
        "percentage": ((length * 100) / (.operations | length) | round)
      }
    ],
    "success_rate": {
      "total_actions": [.operations[].results[] | length] | add,
      "successful_actions": [.operations[].results[] | select(.success == true) | length] | add,
      "failed_actions": [.operations[].results[] | select(.success == false) | length] | add,
      "success_percentage": (([.operations[].results[] | select(.success == true) | length] | add) * 100 / ([.operations[].results[] | length] | add) | round)
    }
  },
  "high_privilege_operations": [
    .operations[] | select(.permission_set_name | test("Admin|Full|Root"; "i")) | {
      "operation_id": .operation_id,
      "timestamp": .timestamp,
      "operation_type": .operation_type,
      "principal_name": .principal_name,
      "principal_type": .principal_type,
      "permission_set_name": .permission_set_name,
      "account_count": (.account_ids | length),
      "rolled_back": .rolled_back,
      "user": .metadata.user
    }
  ],
  "rollback_analysis": {
    "total_rollbacks": [.operations[] | select(.operation_type == "rollback")] | length,
    "rollback_rate": (([.operations[] | select(.operation_type == "rollback")] | length) * 100 / (.operations | length) | round),
    "most_rolled_back_permission_sets": [
      .operations[] | select(.operation_type == "rollback") | group_by(.permission_set_name) | .[] | {
        "permission_set": .[0].permission_set_name,
        "rollback_count": length
      }
    ] | sort_by(.rollback_count) | reverse | .[0:5],
    "most_rolled_back_principals": [
      .operations[] | select(.operation_type == "rollback") | group_by(.principal_name) | .[] | {
        "principal": .[0].principal_name,
        "principal_type": .[0].principal_type,
        "rollback_count": length
      }
    ] | sort_by(.rollback_count) | reverse | .[0:5]
  },
  "user_activity": [
    .operations | group_by(.metadata.user // "unknown") | .[] | {
      "user": .[0].metadata.user // "unknown",
      "operation_count": length,
      "operations_by_type": [group_by(.operation_type) | .[] | {"type": .[0].operation_type, "count": length}],
      "rollback_count": [.[] | select(.operation_type == "rollback")] | length
    }
  ] | sort_by(.operation_count) | reverse,
  "permission_set_activity": [
    .operations | group_by(.permission_set_name) | .[] | {
      "permission_set": .[0].permission_set_name,
      "operation_count": length,
      "assign_count": [.[] | select(.operation_type == "assign")] | length,
      "revoke_count": [.[] | select(.operation_type == "revoke")] | length,
      "rollback_count": [.[] | select(.operation_type == "rollback")] | length,
      "unique_principals": [.[].principal_name] | unique | length,
      "unique_accounts": [.[].account_ids[]] | unique | length
    }
  ] | sort_by(.operation_count) | reverse,
  "account_activity": [
    .operations | map({account_ids: .account_ids, account_names: .account_names, operation_type: .operation_type}) |
    map(.account_ids[] as $id | .account_names[(.account_ids | index($id))] as $name | {account_id: $id, account_name: $name, operation_type: .operation_type}) |
    group_by(.account_id) | .[] | {
      "account_id": .[0].account_id,
      "account_name": .[0].account_name,
      "operation_count": length,
      "assign_count": [.[] | select(.operation_type == "assign")] | length,
      "revoke_count": [.[] | select(.operation_type == "revoke")] | length,
      "rollback_count": [.[] | select(.operation_type == "rollback")] | length
    }
  ] | sort_by(.operation_count) | reverse,
  "error_analysis": {
    "operations_with_errors": [
      .operations[] | select(.results[] | .success == false) | {
        "operation_id": .operation_id,
        "timestamp": .timestamp,
        "operation_type": .operation_type,
        "principal_name": .principal_name,
        "permission_set_name": .permission_set_name,
        "errors": [.results[] | select(.success == false) | {account_id: .account_id, error: .error}]
      }
    ],
    "error_types": [
      .operations[].results[] | select(.success == false) | .error
    ] | group_by(.) | map({error_type: .[0], count: length}) | sort_by(.count) | reverse
  },
  "compliance_flags": {
    "high_privilege_without_rollback": [
      .operations[] | select(.permission_set_name | test("Admin|Full|Root"; "i")) | select(.rolled_back == false) | select(.operation_type != "rollback")
    ] | length,
    "bulk_operations_count": [
      .operations[] | select(.metadata.source | test("bulk"))
    ] | length,
    "operations_without_user_info": [
      .operations[] | select(.metadata.user == null or .metadata.user == "")
    ] | length,
    "weekend_operations": [
      .operations[] | select(.timestamp | strptime("%Y-%m-%dT%H:%M:%SZ") | strftime("%u") | tonumber > 5)
    ] | length,
    "after_hours_operations": [
      .operations[] | select(.timestamp | strptime("%Y-%m-%dT%H:%M:%SZ") | strftime("%H") | tonumber < 8 or (.timestamp | strptime("%Y-%m-%dT%H:%M:%SZ") | strftime("%H") | tonumber > 18))
    ] | length
  }
}')

print_success "Analysis complete"

# Generate output based on format
print_status "Generating $FORMAT report..."

case $FORMAT in
    json)
        echo "$REPORT_DATA" | jq . > "$OUTPUT_FILE"
        ;;
    csv)
        # Generate CSV format
        {
            echo "Operation ID,Timestamp,Type,Principal,Principal Type,Permission Set,Accounts,Success Rate,User,Rolled Back"
            echo "$OPERATIONS_JSON" | jq -r '.operations[] | [
                .operation_id,
                .timestamp,
                .operation_type,
                .principal_name,
                .principal_type,
                .permission_set_name,
                (.account_ids | length),
                (([.results[] | select(.success == true)] | length) * 100 / (.results | length)),
                (.metadata.user // "unknown"),
                .rolled_back
            ] | @csv'
        } > "$OUTPUT_FILE"
        ;;
    html)
        # Generate HTML format
        cat > "$OUTPUT_FILE" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>AWS Identity Center Compliance Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #f0f0f0; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; }
        .metric { display: inline-block; margin: 10px; padding: 15px; background-color: #e8f4f8; border-radius: 5px; }
        .alert { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .high-privilege { background-color: #ffebee; }
    </style>
</head>
<body>
    <div class="header">
        <h1>AWS Identity Center Compliance Report</h1>
        <p><strong>Period:</strong> $(date -d "$DAYS days ago" +%Y-%m-%d) to $(date +%Y-%m-%d)</p>
        <p><strong>Profile:</strong> ${PROFILE:-default}</p>
        <p><strong>Generated:</strong> $(date)</p>
    </div>

    <div class="section">
        <h2>Summary Statistics</h2>
        <div class="metric">
            <strong>Total Operations:</strong><br>
            $(echo "$REPORT_DATA" | jq -r '.summary_statistics.total_operations')
        </div>
        <div class="metric">
            <strong>Success Rate:</strong><br>
            $(echo "$REPORT_DATA" | jq -r '.summary_statistics.success_rate.success_percentage')%
        </div>
        <div class="metric">
            <strong>Rollback Rate:</strong><br>
            $(echo "$REPORT_DATA" | jq -r '.rollback_analysis.rollback_rate')%
        </div>
    </div>

    <div class="section">
        <h2>High Privilege Operations</h2>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>Type</th>
                <th>Principal</th>
                <th>Permission Set</th>
                <th>Accounts</th>
                <th>Rolled Back</th>
                <th>User</th>
            </tr>
EOF
        echo "$REPORT_DATA" | jq -r '.high_privilege_operations[] |
            "<tr class=\"high-privilege\"><td>" + .timestamp + "</td><td>" + .operation_type + "</td><td>" + .principal_name + "</td><td>" + .permission_set_name + "</td><td>" + (.account_count | tostring) + "</td><td>" + (.rolled_back | tostring) + "</td><td>" + (.user // "unknown") + "</td></tr>"' >> "$OUTPUT_FILE"

        cat >> "$OUTPUT_FILE" << EOF
        </table>
    </div>

    <div class="section">
        <h2>Compliance Flags</h2>
EOF

        # Add compliance flags
        HIGH_PRIV_NO_ROLLBACK=$(echo "$REPORT_DATA" | jq -r '.compliance_flags.high_privilege_without_rollback')
        WEEKEND_OPS=$(echo "$REPORT_DATA" | jq -r '.compliance_flags.weekend_operations')
        AFTER_HOURS_OPS=$(echo "$REPORT_DATA" | jq -r '.compliance_flags.after_hours_operations')

        if [ "$HIGH_PRIV_NO_ROLLBACK" -gt 0 ]; then
            echo "        <div class=\"alert\">⚠️ $HIGH_PRIV_NO_ROLLBACK high-privilege operations without rollback</div>" >> "$OUTPUT_FILE"
        fi

        if [ "$WEEKEND_OPS" -gt 0 ]; then
            echo "        <div class=\"alert\">⚠️ $WEEKEND_OPS operations performed on weekends</div>" >> "$OUTPUT_FILE"
        fi

        if [ "$AFTER_HOURS_OPS" -gt 0 ]; then
            echo "        <div class=\"alert\">⚠️ $AFTER_HOURS_OPS operations performed after hours</div>" >> "$OUTPUT_FILE"
        fi

        cat >> "$OUTPUT_FILE" << EOF
    </div>
</body>
</html>
EOF
        ;;
esac

print_success "Report generated: $OUTPUT_FILE"

# Display summary
echo ""
print_status "REPORT SUMMARY"
print_status "=============="
echo "Total Operations: $(echo "$REPORT_DATA" | jq -r '.summary_statistics.total_operations')"
echo "Success Rate: $(echo "$REPORT_DATA" | jq -r '.summary_statistics.success_rate.success_percentage')%"
echo "Rollback Rate: $(echo "$REPORT_DATA" | jq -r '.rollback_analysis.rollback_rate')%"
echo "High Privilege Operations: $(echo "$REPORT_DATA" | jq -r '.high_privilege_operations | length')"

# Show compliance flags
COMPLIANCE_FLAGS=$(echo "$REPORT_DATA" | jq -r '.compliance_flags | to_entries[] | select(.value > 0) | "\(.key): \(.value)"')
if [ -n "$COMPLIANCE_FLAGS" ]; then
    echo ""
    print_warning "Compliance Flags:"
    echo "$COMPLIANCE_FLAGS" | while read -r flag; do
        echo "  - $flag"
    done
fi

echo ""
print_status "Report saved to: $OUTPUT_FILE"
print_status "Use this report for compliance auditing and security reviews"
