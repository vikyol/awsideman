# Export User Assignments for Bulk Revoke

This workflow shows how to export all user assignments and prepare them for bulk revoke operations.

## Step 1: Export User Assignments

Export all user assignments to CSV format:

```bash
# Export all user assignments (direct assignments only)
poetry run awsideman assignment list --principal-type USER --format csv --output user-assignments-raw.csv --no-interactive
```

This command will:
- Filter for USER principal type only (excludes group assignments)
- Export to CSV format
- Save to `user-assignments-raw.csv`
- Disable interactive pagination for automation

## Step 2: Convert to Bulk Revoke Format

The exported CSV has different column names than what bulk revoke expects. Convert it:

```bash
# Convert the exported CSV to bulk revoke format
python convert-assignments-for-revoke.py user-assignments-raw.csv user-assignments-for-revoke.csv
```

This will create a CSV with the correct format for bulk revoke:
- `principal_name`
- `permission_set_name`
- `account_name`
- `principal_type`

## Step 3: Review and Test

Before revoking, review the assignments:

```bash
# Preview what will be revoked (dry run)
poetry run awsideman bulk revoke user-assignments-for-revoke.csv --dry-run
```

## Step 4: Execute Bulk Revoke

If the preview looks correct, execute the revoke:

```bash
# Revoke all user assignments
poetry run awsideman bulk revoke user-assignments-for-revoke.csv --force
```

## Alternative: Direct JSON Export

You can also export directly to JSON format and convert:

```bash
# Export to JSON
poetry run awsideman assignment list --principal-type USER --format json --output user-assignments.json --no-interactive

# Then manually convert the JSON structure to match bulk revoke format
```

## Example Output Files

### Raw Export (assignment list format):
```csv
permission_set_name,principal_name,principal_type,account_id,account_name
ReadOnlyAccess,john.doe,USER,123456789012,Production
PowerUserAccess,jane.smith,USER,987654321098,Development
```

### Converted Format (bulk revoke format):
```csv
principal_name,permission_set_name,account_name,principal_type
john.doe,ReadOnlyAccess,Production,USER
jane.smith,PowerUserAccess,Development,USER
```

## Notes

- This workflow only exports **direct user assignments**, not assignments inherited through groups
- Use `--dry-run` first to preview changes before executing
- The `--force` flag skips confirmation prompts for automation
- Consider backing up your assignments before bulk revoke operations
