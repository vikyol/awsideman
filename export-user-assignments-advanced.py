#!/usr/bin/env python3
"""
Advanced script to export user assignments and convert to bulk revoke format.

This script can handle both CSV and JSON exports from 'awsideman assignment list'
and convert them to the format expected by 'awsideman bulk revoke'.
"""

import csv
import json
import sys
from pathlib import Path


def convert_csv_assignments(input_file: str, output_file: str) -> bool:
    """Convert CSV assignment list export to bulk revoke format."""

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        return False

    assignments = []
    with open(input_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assignment = {
                "principal_name": row["principal_name"],
                "permission_set_name": row["permission_set_name"],
                "account_name": row["account_name"],
                "principal_type": row["principal_type"],
            }
            assignments.append(assignment)

    # Write bulk revoke format CSV
    with open(output_file, "w", newline="") as f:
        fieldnames = ["principal_name", "permission_set_name", "account_name", "principal_type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(assignments)

    print(f"Converted {len(assignments)} assignments from CSV to bulk revoke format")
    return True


def convert_json_assignments(input_file: str, output_file: str) -> bool:
    """Convert JSON assignment list export to bulk revoke format."""

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        return False

    with open(input_path, "r") as f:
        data = json.load(f)

    # Extract assignments from JSON structure
    assignments = []
    if isinstance(data, list):
        # Direct list of assignments
        assignment_list = data
    elif isinstance(data, dict) and "assignments" in data:
        # Nested structure with assignments key
        assignment_list = data["assignments"]
    else:
        print("Error: Unexpected JSON structure")
        return False

    for assignment in assignment_list:
        converted = {
            "principal_name": assignment.get("principal_name", ""),
            "permission_set_name": assignment.get("permission_set_name", ""),
            "account_name": assignment.get("account_name", ""),
            "principal_type": assignment.get("principal_type", "USER"),
        }
        assignments.append(converted)

    # Write bulk revoke format CSV
    with open(output_file, "w", newline="") as f:
        fieldnames = ["principal_name", "permission_set_name", "account_name", "principal_type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(assignments)

    print(f"Converted {len(assignments)} assignments from JSON to bulk revoke format")
    return True


def create_json_format(input_file: str, output_file: str) -> bool:
    """Convert assignment list export to bulk revoke JSON format."""

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        return False

    assignments = []

    # Determine input format and read data
    if input_path.suffix.lower() == ".json":
        with open(input_path, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            assignment_list = data
        elif isinstance(data, dict) and "assignments" in data:
            assignment_list = data["assignments"]
        else:
            print("Error: Unexpected JSON structure")
            return False

        for assignment in assignment_list:
            converted = {
                "principal_name": assignment.get("principal_name", ""),
                "permission_set_name": assignment.get("permission_set_name", ""),
                "account_name": assignment.get("account_name", ""),
                "principal_type": assignment.get("principal_type", "USER"),
            }
            assignments.append(converted)

    elif input_path.suffix.lower() == ".csv":
        with open(input_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                assignment = {
                    "principal_name": row["principal_name"],
                    "permission_set_name": row["permission_set_name"],
                    "account_name": row["account_name"],
                    "principal_type": row["principal_type"],
                }
                assignments.append(assignment)

    else:
        print("Error: Unsupported file format. Use .csv or .json files.")
        return False

    # Write bulk revoke format JSON
    output_data = {"assignments": assignments}
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Converted {len(assignments)} assignments to bulk revoke JSON format")
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python export-user-assignments-advanced.py <input-file> <output-file> [format]")
        print("")
        print("Examples:")
        print("  # Convert CSV to CSV")
        print(
            "  python export-user-assignments-advanced.py user-assignments-raw.csv user-assignments-for-revoke.csv"
        )
        print("")
        print("  # Convert JSON to CSV")
        print(
            "  python export-user-assignments-advanced.py user-assignments.json user-assignments-for-revoke.csv"
        )
        print("")
        print("  # Convert to JSON format")
        print(
            "  python export-user-assignments-advanced.py user-assignments-raw.csv user-assignments-for-revoke.json json"
        )
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    output_format = sys.argv[3] if len(sys.argv) > 3 else "csv"

    input_path = Path(input_file)

    # Determine conversion method based on input and output formats
    if output_format.lower() == "json":
        success = create_json_format(input_file, output_file)
    elif input_path.suffix.lower() == ".json":
        success = convert_json_assignments(input_file, output_file)
    else:
        success = convert_csv_assignments(input_file, output_file)

    if success:
        print("\nConversion completed successfully!")
        print(f"Output file: {output_file}")
        print("\nNext steps:")
        print(f"1. Review the converted file: {output_file}")
        print(f"2. Test with dry run: poetry run awsideman bulk revoke {output_file} --dry-run")
        print(f"3. Execute revoke: poetry run awsideman bulk revoke {output_file} --force")


if __name__ == "__main__":
    main()
