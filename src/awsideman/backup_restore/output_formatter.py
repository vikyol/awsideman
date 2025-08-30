"""
Output formatter for backup diff results.

This module provides formatting capabilities for diff results in various formats
including console output with color coding and human-readable formatting,
JSON export for structured data, and CSV export for spreadsheet applications.
"""

import csv
import json
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

from .diff_models import AttributeChange, ChangeType, DiffResult, ResourceChange, ResourceDiff


class Colors:
    """ANSI color codes for console output."""

    # Basic colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Styles
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    # Reset
    RESET = "\033[0m"

    @classmethod
    def disable_colors(cls) -> None:
        """Disable all colors (useful for non-terminal output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""
        cls.WHITE = ""
        cls.BOLD = ""
        cls.UNDERLINE = ""
        cls.RESET = ""


class OutputFormatter:
    """Formats diff results into various output formats."""

    def __init__(self, use_colors: bool = True):
        """Initialize the formatter.

        Args:
            use_colors: Whether to use ANSI color codes in console output
        """
        self.use_colors = use_colors
        if not use_colors:
            Colors.disable_colors()

    def format_console(self, diff_result: DiffResult) -> str:
        """Format diff result for human-readable console output.

        Args:
            diff_result: The diff result to format

        Returns:
            Formatted console output string
        """
        if not diff_result.has_changes:
            return self._format_no_changes(diff_result)

        output_lines = []

        # Header
        output_lines.extend(self._format_header(diff_result))
        output_lines.append("")

        # Summary
        output_lines.extend(self._format_summary(diff_result))
        output_lines.append("")

        # Resource sections
        resource_diffs = [
            ("Users", diff_result.user_diff),
            ("Groups", diff_result.group_diff),
            ("Permission Sets", diff_result.permission_set_diff),
            ("Assignments", diff_result.assignment_diff),
        ]

        for section_name, resource_diff in resource_diffs:
            if resource_diff.has_changes:
                output_lines.extend(self._format_resource_section(section_name, resource_diff))
                output_lines.append("")

        # Accounts section (based on assignment changes)
        accounts_section = self._format_accounts_section(diff_result)
        if accounts_section:
            output_lines.extend(accounts_section)
            output_lines.append("")

        return "\n".join(output_lines)

    def _format_no_changes(self, diff_result: DiffResult) -> str:
        """Format output when there are no changes."""
        lines = []
        lines.append(f"{Colors.BOLD}Backup Comparison Results{Colors.RESET}")
        lines.append("=" * 50)
        lines.append(
            f"Source: {diff_result.source_backup_id} ({self._format_timestamp(diff_result.source_timestamp)})"
        )
        lines.append(
            f"Target: {diff_result.target_backup_id} ({self._format_timestamp(diff_result.target_timestamp)})"
        )
        lines.append("")
        lines.append(f"{Colors.GREEN}✓ No changes detected between backups{Colors.RESET}")
        return "\n".join(lines)

    def _format_header(self, diff_result: DiffResult) -> List[str]:
        """Format the header section."""
        lines = []
        lines.append(f"{Colors.BOLD}Backup Comparison Results{Colors.RESET}")
        lines.append("=" * 50)
        lines.append(
            f"Source: {diff_result.source_backup_id} ({self._format_timestamp(diff_result.source_timestamp)})"
        )
        lines.append(
            f"Target: {diff_result.target_backup_id} ({self._format_timestamp(diff_result.target_timestamp)})"
        )
        return lines

    def _format_summary(self, diff_result: DiffResult) -> List[str]:
        """Format the summary section."""
        lines = []
        lines.append(f"{Colors.BOLD}Summary{Colors.RESET}")
        lines.append("-" * 20)

        summary = diff_result.summary
        lines.append(f"Total Changes: {Colors.BOLD}{summary.total_changes}{Colors.RESET}")
        lines.append("")

        # Changes by action
        lines.append("Changes by Action:")
        for action, count in summary.changes_by_action.items():
            if count > 0:
                color = self._get_action_color(action)
                icon = self._get_action_icon(action)
                lines.append(f"  {color}{icon} {action.title()}: {count}{Colors.RESET}")

        lines.append("")

        # Changes by resource type
        lines.append("Changes by Resource Type:")
        for resource_type, count in summary.changes_by_type.items():
            if count > 0:
                lines.append(f"  • {resource_type.replace('_', ' ').title()}: {count}")

        return lines

    def _format_resource_section(self, section_name: str, resource_diff: ResourceDiff) -> List[str]:
        """Format a resource section (users, groups, etc.) with improved formatting."""
        lines = []
        total_changes = resource_diff.total_changes
        lines.append(f"{Colors.BOLD}{section_name} ({total_changes} changes){Colors.RESET}")
        lines.append("-" * (len(section_name) + 10))

        # Created resources - Green with + prefix
        if resource_diff.created:
            lines.append(f"{Colors.GREEN}Created ({len(resource_diff.created)}):{Colors.RESET}")
            for change in resource_diff.created:
                lines.extend(self._format_resource_change_improved(change, "created", indent="  "))
            lines.append("")

        # Deleted resources - Red with - prefix
        if resource_diff.deleted:
            lines.append(f"{Colors.RED}Deleted ({len(resource_diff.deleted)}):{Colors.RESET}")
            for change in resource_diff.deleted:
                lines.extend(self._format_resource_change_improved(change, "deleted", indent="  "))
            lines.append("")

        # Modified resources - Yellow with ~ prefix
        if resource_diff.modified:
            lines.append(f"{Colors.YELLOW}Modified ({len(resource_diff.modified)}):{Colors.RESET}")
            for change in resource_diff.modified:
                lines.extend(self._format_resource_change_improved(change, "modified", indent="  "))
            lines.append("")

        return lines

    def _format_resource_change(self, change: ResourceChange, indent: str = "") -> List[str]:
        """Format a single resource change (legacy method for tests)."""
        lines = []

        # Get appropriate prefix and color based on change type
        if change.change_type == ChangeType.CREATED:
            prefix = f"{Colors.GREEN}+{Colors.RESET}"
        elif change.change_type == ChangeType.DELETED:
            prefix = f"{Colors.RED}-{Colors.RESET}"
        else:  # modified
            prefix = f"{Colors.YELLOW}~{Colors.RESET}"

        # Display resource name or ID
        name_display = change.resource_name or change.resource_id
        lines.append(f"{indent}{prefix} {name_display}")

        # Resource ID if different from name
        if change.resource_name and change.resource_name != change.resource_id:
            lines.append(f"{indent}   ID: {change.resource_id}")

        # Attribute changes for modified resources
        if change.change_type == ChangeType.MODIFIED and change.attribute_changes:
            for attr_change in change.attribute_changes:
                lines.extend(self._format_attribute_change(attr_change, indent + "   "))

        return lines

    def _format_resource_change_improved(
        self, change: ResourceChange, change_type: str, indent: str = ""
    ) -> List[str]:
        """Format a single resource change with improved display."""
        lines = []

        # Get appropriate prefix and color
        if change_type == "created":
            prefix = f"{Colors.GREEN}+{Colors.RESET}"
        elif change_type == "deleted":
            prefix = f"{Colors.RED}-{Colors.RESET}"
        else:  # modified
            prefix = f"{Colors.YELLOW}~{Colors.RESET}"

        # Special handling for assignments
        if change.resource_type == "assignments":
            lines.extend(self._format_assignment_change_improved(change, prefix, indent))
        else:
            # Standard resource formatting
            name_display = change.resource_name or change.resource_id
            lines.append(f"{indent}{prefix} {name_display}")

            # Resource ID if different from name
            if change.resource_name and change.resource_name != change.resource_id:
                lines.append(f"{indent}   ID: {change.resource_id}")

        # Attribute changes for modified resources
        if change.change_type == ChangeType.MODIFIED and change.attribute_changes:
            for attr_change in change.attribute_changes:
                lines.extend(self._format_attribute_change(attr_change, indent + "   "))

        return lines

    def _format_assignment_change_improved(
        self, change: ResourceChange, prefix: str, indent: str = ""
    ) -> List[str]:
        """Format assignment changes with detailed information."""
        lines = []

        # Parse assignment data from resource_id or after_value
        assignment_info = self._parse_assignment_info(change)

        if assignment_info:
            principal_type = assignment_info.get("principal_type", "UNKNOWN")
            principal_id = assignment_info.get("principal_id", "unknown")
            account_id = assignment_info.get("account_id", "unknown")
            permission_set_arn = assignment_info.get("permission_set_arn", "unknown")

            # Extract permission set name from ARN if possible
            permission_set_name = self._extract_permission_set_name(permission_set_arn)

            # Format: + Principal Type:Principal ID -> Permission Set Name @ Account ID
            principal_display = f"{principal_type}:{principal_id}"
            permission_display = (
                permission_set_name or permission_set_arn.split("/")[-1]
                if "/" in permission_set_arn
                else permission_set_arn
            )

            lines.append(
                f"{indent}{prefix} {principal_display} -> {permission_display} @ {account_id}"
            )
        else:
            # Fallback to basic formatting
            name_display = change.resource_name or change.resource_id
            lines.append(f"{indent}{prefix} {name_display}")

        return lines

    def _extract_permission_set_name(self, permission_set_arn: str) -> Optional[str]:
        """Extract permission set name from ARN."""
        try:
            if permission_set_arn and "/" in permission_set_arn:
                return permission_set_arn.split("/")[-1]
        except Exception:
            pass
        return None

    def _parse_assignment_info(self, change: ResourceChange) -> Optional[Dict[str, str]]:
        """Parse assignment information from change data."""
        try:
            # Try to get info from after_value (for created) or before_value (for deleted)
            value = change.after_value or change.before_value

            if value and isinstance(value, dict):
                return {
                    "principal_type": value.get("principal_type", "UNKNOWN"),
                    "principal_id": value.get("principal_id", "unknown"),
                    "account_id": value.get("account_id", "unknown"),
                    "permission_set_arn": value.get("permission_set_arn", "unknown"),
                }

            # Try to parse from resource_id if it's in a specific format
            # Format: account_id:permission_set_arn:principal_type:principal_id
            if change.resource_id and ":" in change.resource_id:
                parts = change.resource_id.split(":")
                if len(parts) >= 4:
                    return {
                        "account_id": parts[0],
                        "permission_set_arn": parts[1],
                        "principal_type": parts[2],
                        "principal_id": parts[3],
                    }

        except Exception:
            pass

        return None

    def _format_accounts_section(self, diff_result: DiffResult) -> List[str]:
        """Format accounts section showing new/removed accounts based on assignments."""
        lines = []

        # Since DiffResult doesn't contain full backup data, we'll extract account info
        # from the assignment diffs instead
        source_accounts = set()
        target_accounts = set()

        # Extract accounts from assignment changes
        # Created assignments indicate new accounts
        for assignment in diff_result.assignment_diff.created:
            # Parse account ID from resource_id or other available fields
            account_id = self._extract_account_id_from_assignment(assignment)
            if account_id:
                target_accounts.add(account_id)

        # Deleted assignments indicate removed accounts
        for assignment in diff_result.assignment_diff.deleted:
            account_id = self._extract_account_id_from_assignment(assignment)
            if account_id:
                source_accounts.add(account_id)

        # Calculate differences
        new_accounts = target_accounts - source_accounts
        removed_accounts = source_accounts - target_accounts

        if new_accounts or removed_accounts:
            lines.append(f"{Colors.BOLD}Accounts Changes{Colors.RESET}")
            lines.append("-" * 18)

            # New accounts
            if new_accounts:
                lines.append(f"{Colors.GREEN}New Accounts ({len(new_accounts)}):{Colors.RESET}")
                for account_id in sorted(new_accounts):
                    lines.append(f"  {Colors.GREEN}+{Colors.RESET} {account_id}")
                lines.append("")

            # Removed accounts
            if removed_accounts:
                lines.append(
                    f"{Colors.RED}Removed Accounts ({len(removed_accounts)}):{Colors.RESET}"
                )
                for account_id in sorted(removed_accounts):
                    lines.append(f"  {Colors.RED}-{Colors.RESET} {account_id}")
                lines.append("")

        return lines

    def _extract_account_id_from_assignment(self, assignment: ResourceChange) -> Optional[str]:
        """Extract account ID from assignment change."""
        try:
            # Try to parse account ID from resource_id or resource_name
            if assignment.resource_id and ":" in assignment.resource_id:
                # Format might be "account_id:permission_set_arn:principal_type:principal_id"
                parts = assignment.resource_id.split(":")
                if len(parts) >= 4:
                    return parts[0]
            elif assignment.resource_name and ":" in assignment.resource_name:
                parts = assignment.resource_name.split(":")
                if len(parts) >= 4:
                    return parts[0]
        except Exception:
            pass
        return None

    def _format_attribute_change(self, attr_change: AttributeChange, indent: str = "") -> List[str]:
        """Format an attribute change."""
        lines = []
        lines.append(f"{indent}{attr_change.attribute_name}:")
        lines.append(
            f"{indent}  {Colors.RED}- {self._format_value(attr_change.before_value)}{Colors.RESET}"
        )
        lines.append(
            f"{indent}  {Colors.GREEN}+ {self._format_value(attr_change.after_value)}{Colors.RESET}"
        )
        return lines

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return "(none)"
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, (list, dict)):
            return str(value)
        else:
            return str(value)

    def _format_timestamp(self, timestamp: datetime) -> str:
        """Format a timestamp for display."""
        return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    def _get_action_color(self, action: str) -> str:
        """Get color for an action type."""
        color_map = {
            "created": Colors.GREEN,
            "deleted": Colors.RED,
            "modified": Colors.YELLOW,
        }
        return color_map.get(action, Colors.WHITE)

    def _get_action_icon(self, action: str) -> str:
        """Get icon for an action type."""
        icon_map = {
            "created": "✓",
            "deleted": "✗",
            "modified": "~",
        }
        return icon_map.get(action, "•")

    def format_json(self, diff_result: DiffResult) -> str:
        """Format diff result as structured JSON.

        Args:
            diff_result: The diff result to format

        Returns:
            JSON formatted string with complete diff details
        """
        # Convert to dictionary and format as JSON
        data = diff_result.to_dict()

        # Add metadata for JSON format
        data["format_version"] = "1.0"
        data["generated_at"] = datetime.now().isoformat()

        return json.dumps(data, indent=2, ensure_ascii=False)

    def format_csv(self, diff_result: DiffResult) -> str:
        """Format diff result as CSV for spreadsheet applications.

        The CSV format includes all changes in a flat structure with columns:
        - Resource Type
        - Change Type
        - Resource ID
        - Resource Name
        - Attribute Name (for modifications)
        - Before Value (for modifications)
        - After Value (for modifications)
        - Source Backup
        - Target Backup
        - Source Timestamp
        - Target Timestamp

        Args:
            diff_result: The diff result to format

        Returns:
            CSV formatted string
        """
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        headers = [
            "Resource Type",
            "Change Type",
            "Resource ID",
            "Resource Name",
            "Attribute Name",
            "Before Value",
            "After Value",
            "Source Backup",
            "Target Backup",
            "Source Timestamp",
            "Target Timestamp",
        ]
        writer.writerow(headers)

        # Helper function to format values for CSV
        def format_csv_value(value: Any) -> str:
            if value is None:
                return ""
            elif isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            else:
                return str(value)

        # Process all resource diffs
        resource_diffs = [
            diff_result.user_diff,
            diff_result.group_diff,
            diff_result.permission_set_diff,
            diff_result.assignment_diff,
        ]

        for resource_diff in resource_diffs:
            # Process all changes in this resource type
            all_changes = resource_diff.created + resource_diff.deleted + resource_diff.modified

            for change in all_changes:
                if change.change_type == ChangeType.MODIFIED and change.attribute_changes:
                    # For modified resources, create one row per attribute change
                    for attr_change in change.attribute_changes:
                        writer.writerow(
                            [
                                resource_diff.resource_type,
                                change.change_type.value,
                                change.resource_id,
                                change.resource_name or "",
                                attr_change.attribute_name,
                                format_csv_value(attr_change.before_value),
                                format_csv_value(attr_change.after_value),
                                diff_result.source_backup_id,
                                diff_result.target_backup_id,
                                diff_result.source_timestamp.isoformat(),
                                diff_result.target_timestamp.isoformat(),
                            ]
                        )
                else:
                    # For created/deleted resources or modified without attribute details
                    writer.writerow(
                        [
                            resource_diff.resource_type,
                            change.change_type.value,
                            change.resource_id,
                            change.resource_name or "",
                            "",  # No specific attribute
                            format_csv_value(change.before_value) if change.before_value else "",
                            format_csv_value(change.after_value) if change.after_value else "",
                            diff_result.source_backup_id,
                            diff_result.target_backup_id,
                            diff_result.source_timestamp.isoformat(),
                            diff_result.target_timestamp.isoformat(),
                        ]
                    )

        return output.getvalue()

    def format_html(self, diff_result: DiffResult) -> str:
        """Format diff result as HTML report for web-friendly viewing.

        Creates a professional-looking HTML report with:
        - Summary dashboard with statistics
        - Navigation between sections
        - Color-coded changes
        - Detailed change listings in tables
        - Responsive design

        Args:
            diff_result: The diff result to format

        Returns:
            Complete HTML document string
        """
        if not diff_result.has_changes:
            return self._format_html_no_changes(diff_result)

        html_parts = []

        # HTML document structure
        html_parts.append(self._get_html_header())
        html_parts.append(self._get_html_styles())
        html_parts.append("<body>")

        # Main container
        html_parts.append('<div class="container">')

        # Header section
        html_parts.append(self._format_html_header(diff_result))

        # Summary dashboard
        html_parts.append(self._format_html_summary(diff_result))

        # Navigation
        html_parts.append(self._format_html_navigation(diff_result))

        # Resource sections
        resource_sections = [
            ("users", "Users", diff_result.user_diff),
            ("groups", "Groups", diff_result.group_diff),
            ("permission-sets", "Permission Sets", diff_result.permission_set_diff),
            ("assignments", "Assignments", diff_result.assignment_diff),
        ]

        for section_id, section_name, resource_diff in resource_sections:
            if resource_diff.has_changes:
                html_parts.append(
                    self._format_html_resource_section(section_id, section_name, resource_diff)
                )

        # Footer
        html_parts.append(self._format_html_footer())

        # Close containers
        html_parts.append("</div>")  # container
        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def _format_html_no_changes(self, diff_result: DiffResult) -> str:
        """Format HTML output when there are no changes."""
        html_parts = []
        html_parts.append(self._get_html_header())
        html_parts.append(self._get_html_styles())
        html_parts.append("<body>")
        html_parts.append('<div class="container">')

        # Header
        html_parts.append(self._format_html_header(diff_result))

        # No changes message
        html_parts.append('<div class="no-changes">')
        html_parts.append('<div class="success-icon">✓</div>')
        html_parts.append("<h2>No Changes Detected</h2>")
        html_parts.append("<p>The backups are identical - no differences were found.</p>")
        html_parts.append("</div>")

        html_parts.append(self._format_html_footer())
        html_parts.append("</div>")
        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def _get_html_header(self) -> str:
        """Get HTML document header."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Identity Center Backup Comparison Report</title>"""

    def _get_html_styles(self) -> str:
        """Get CSS styles for the HTML report."""
        return """    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: white;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            min-height: 100vh;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }

        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.2em;
        }

        .backup-info {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 15px;
        }

        .backup-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }

        .backup-card h3 {
            color: #495057;
            margin-bottom: 5px;
        }

        .backup-card .backup-id {
            font-family: monospace;
            font-weight: bold;
            color: #007bff;
        }

        .backup-card .timestamp {
            color: #6c757d;
            font-size: 0.9em;
        }

        .summary-dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }

        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            border-top: 4px solid #007bff;
        }

        .summary-card.total {
            border-top-color: #6f42c1;
        }

        .summary-card.created {
            border-top-color: #28a745;
        }

        .summary-card.deleted {
            border-top-color: #dc3545;
        }

        .summary-card.modified {
            border-top-color: #ffc107;
        }

        .summary-card h3 {
            font-size: 2.5em;
            margin-bottom: 5px;
            font-weight: bold;
        }

        .summary-card p {
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .navigation {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 30px 0;
        }

        .navigation h3 {
            margin-bottom: 10px;
            color: #495057;
        }

        .nav-links {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }

        .nav-link {
            display: inline-block;
            padding: 8px 16px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9em;
            transition: background-color 0.2s;
        }

        .nav-link:hover {
            background: #0056b3;
        }

        .resource-section {
            margin: 40px 0;
            padding: 20px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            background: white;
        }

        .resource-section h2 {
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }

        .change-group {
            margin: 25px 0;
        }

        .change-group h3 {
            margin-bottom: 15px;
            padding: 10px 15px;
            border-radius: 4px;
            color: white;
        }

        .change-group.created h3 {
            background: #28a745;
        }

        .change-group.deleted h3 {
            background: #dc3545;
        }

        .change-group.modified h3 {
            background: #ffc107;
            color: #212529;
        }

        .changes-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: white;
        }

        .changes-table th,
        .changes-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }

        .changes-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
        }

        .changes-table tr:hover {
            background: #f8f9fa;
        }

        .resource-id {
            font-family: monospace;
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }

        .attribute-changes {
            margin-top: 10px;
        }

        .attribute-change {
            background: #f8f9fa;
            padding: 10px;
            margin: 5px 0;
            border-radius: 4px;
            border-left: 4px solid #007bff;
        }

        .attribute-name {
            font-weight: bold;
            margin-bottom: 5px;
            color: #495057;
        }

        .value-change {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-family: monospace;
            font-size: 0.9em;
        }

        .before-value {
            background: #f8d7da;
            padding: 8px;
            border-radius: 3px;
            border-left: 3px solid #dc3545;
        }

        .after-value {
            background: #d4edda;
            padding: 8px;
            border-radius: 3px;
            border-left: 3px solid #28a745;
        }

        .before-value::before {
            content: "- ";
            color: #dc3545;
            font-weight: bold;
        }

        .after-value::before {
            content: "+ ";
            color: #28a745;
            font-weight: bold;
        }

        .no-changes {
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }

        .success-icon {
            font-size: 4em;
            color: #28a745;
            margin-bottom: 20px;
        }

        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }

        @media (max-width: 768px) {
            .backup-info {
                grid-template-columns: 1fr;
            }

            .summary-dashboard {
                grid-template-columns: repeat(2, 1fr);
            }

            .nav-links {
                flex-direction: column;
            }

            .value-change {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>"""

    def _format_html_header(self, diff_result: DiffResult) -> str:
        """Format the HTML header section."""
        return f"""<div class="header">
    <h1>AWS Identity Center Backup Comparison</h1>
    <div class="backup-info">
        <div class="backup-card">
            <h3>Source Backup</h3>
            <div class="backup-id">{self._escape_html(diff_result.source_backup_id)}</div>
            <div class="timestamp">{self._format_timestamp(diff_result.source_timestamp)}</div>
        </div>
        <div class="backup-card">
            <h3>Target Backup</h3>
            <div class="backup-id">{self._escape_html(diff_result.target_backup_id)}</div>
            <div class="timestamp">{self._format_timestamp(diff_result.target_timestamp)}</div>
        </div>
    </div>
</div>"""

    def _format_html_summary(self, diff_result: DiffResult) -> str:
        """Format the HTML summary dashboard."""
        summary = diff_result.summary

        return f"""<div class="summary-dashboard">
    <div class="summary-card total">
        <h3>{summary.total_changes}</h3>
        <p>Total Changes</p>
    </div>
    <div class="summary-card created">
        <h3>{summary.changes_by_action.get('created', 0)}</h3>
        <p>Created</p>
    </div>
    <div class="summary-card deleted">
        <h3>{summary.changes_by_action.get('deleted', 0)}</h3>
        <p>Deleted</p>
    </div>
    <div class="summary-card modified">
        <h3>{summary.changes_by_action.get('modified', 0)}</h3>
        <p>Modified</p>
    </div>
</div>"""

    def _format_html_navigation(self, diff_result: DiffResult) -> str:
        """Format the HTML navigation section."""
        nav_links = []

        resource_sections = [
            ("users", "Users", diff_result.user_diff),
            ("groups", "Groups", diff_result.group_diff),
            ("permission-sets", "Permission Sets", diff_result.permission_set_diff),
            ("assignments", "Assignments", diff_result.assignment_diff),
        ]

        for section_id, section_name, resource_diff in resource_sections:
            if resource_diff.has_changes:
                nav_links.append(
                    f'<a href="#{section_id}" class="nav-link">{section_name} ({resource_diff.total_changes})</a>'
                )

        if not nav_links:
            return ""

        return f"""<div class="navigation">
    <h3>Jump to Section</h3>
    <div class="nav-links">
        {' '.join(nav_links)}
    </div>
</div>"""

    def _format_html_resource_section(
        self, section_id: str, section_name: str, resource_diff: ResourceDiff
    ) -> str:
        """Format an HTML resource section."""
        html_parts = []

        html_parts.append(f'<div id="{section_id}" class="resource-section">')
        html_parts.append(f"<h2>{section_name} ({resource_diff.total_changes} changes)</h2>")

        # Created resources
        if resource_diff.created:
            html_parts.append(
                self._format_html_change_group("created", "Created", resource_diff.created)
            )

        # Deleted resources
        if resource_diff.deleted:
            html_parts.append(
                self._format_html_change_group("deleted", "Deleted", resource_diff.deleted)
            )

        # Modified resources
        if resource_diff.modified:
            html_parts.append(
                self._format_html_change_group("modified", "Modified", resource_diff.modified)
            )

        html_parts.append("</div>")

        return "\n".join(html_parts)

    def _format_html_change_group(
        self, change_type: str, title: str, changes: List[ResourceChange]
    ) -> str:
        """Format a group of changes (created, deleted, modified)."""
        html_parts = []

        html_parts.append(f'<div class="change-group {change_type}">')
        html_parts.append(f"<h3>{title} ({len(changes)})</h3>")

        # Create table
        html_parts.append('<table class="changes-table">')
        html_parts.append("<thead>")
        html_parts.append("<tr>")
        html_parts.append("<th>Resource Name</th>")
        html_parts.append("<th>Resource ID</th>")
        if change_type == "modified":
            html_parts.append("<th>Changes</th>")
        html_parts.append("</tr>")
        html_parts.append("</thead>")
        html_parts.append("<tbody>")

        for change in changes:
            html_parts.append("<tr>")

            # Resource name
            name_display = self._escape_html(change.resource_name or change.resource_id)
            html_parts.append(f"<td>{name_display}</td>")

            # Resource ID
            if change.resource_name and change.resource_name != change.resource_id:
                html_parts.append(
                    f'<td><span class="resource-id">{self._escape_html(change.resource_id)}</span></td>'
                )
            else:
                html_parts.append("<td>-</td>")

            # Changes (for modified resources)
            if change_type == "modified":
                if change.attribute_changes:
                    changes_html = self._format_html_attribute_changes(change.attribute_changes)
                    html_parts.append(f"<td>{changes_html}</td>")
                else:
                    html_parts.append("<td>No detailed changes available</td>")

            html_parts.append("</tr>")

        html_parts.append("</tbody>")
        html_parts.append("</table>")
        html_parts.append("</div>")

        return "\n".join(html_parts)

    def _format_html_attribute_changes(self, attribute_changes: List[AttributeChange]) -> str:
        """Format attribute changes for HTML display."""
        html_parts = []

        html_parts.append('<div class="attribute-changes">')

        for attr_change in attribute_changes:
            html_parts.append('<div class="attribute-change">')
            html_parts.append(
                f'<div class="attribute-name">{self._escape_html(attr_change.attribute_name)}</div>'
            )
            html_parts.append('<div class="value-change">')
            html_parts.append(
                f'<div class="before-value">{self._escape_html(self._format_value_for_html(attr_change.before_value))}</div>'
            )
            html_parts.append(
                f'<div class="after-value">{self._escape_html(self._format_value_for_html(attr_change.after_value))}</div>'
            )
            html_parts.append("</div>")
            html_parts.append("</div>")

        html_parts.append("</div>")

        return "\n".join(html_parts)

    def _format_html_footer(self) -> str:
        """Format the HTML footer."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"""<div class="footer">
    <p>Report generated on {timestamp} by AWS Identity Manager (awsideman)</p>
</div>"""

    def _format_value_for_html(self, value: Any) -> str:
        """Format a value for HTML display."""
        if value is None:
            return "(none)"
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, list):
            return json.dumps(value, indent=2, ensure_ascii=False)
        if isinstance(value, dict):
            return json.dumps(value, indent=2, ensure_ascii=False)
        # For any other type (int, float, bool, etc.)
        return str(value)  # type: ignore[unreachable]

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not isinstance(text, str):
            text = str(text)

        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )
