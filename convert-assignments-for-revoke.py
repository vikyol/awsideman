#!/usr/bin/env python3
"""
Convert assignment list CSV export to bulk revoke format.

This script converts the CSV output from 'awsideman assignment list'
to the format expected by 'awsideman bulk revoke'.
"""

import csv
import sys
from pathlib import Path


def convert_assignments_csv(input_file: str, output_file: str):
    """Convert assignment list CSV to bulk revoke format."""

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        return False

    # Read the assignment list CSV
    assignments = []
    with open(input_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert to bulk revoke format
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

    print(f"Converted {len(assignments)} assignments to bulk revoke format")
    print(f"Output saved to: {output_file}")
    return True


def main():
    if len(sys.argv) != 3:
        print("Usage: python convert-assignments-for-revoke.py <input-csv> <output-csv>")
        print(
            "Example: python convert-assignments-for-revoke.py user-assignments-raw.csv user-assignments-for-revoke.csv"
        )
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    if convert_assignments_csv(input_file, output_file):
        print("\nNext steps:")
        print(f"1. Review the converted file: {output_file}")
        print(f"2. Run bulk revoke: poetry run awsideman bulk revoke {output_file} --dry-run")
        print(f"3. If satisfied, run: poetry run awsideman bulk revoke {output_file}")


if __name__ == "__main__":
    main()
