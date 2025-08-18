# CLI Reference

Complete reference for all backup and restore CLI commands.

## Backup Commands

### `backup create`

Create a new backup of AWS Identity Center resources.

```bash
awsideman backup create [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--type` | `full\|incremental` | `full` | Backup type |
| `--resource-types` | `list` | `all` | Specific resource types to backup |
| `--since` | `date` | - | Date for incremental backup (YYYY-MM-DD) |
| `--description` | `string` | - | Human-readable description |
| `--encryption-enabled` | `bool` | `true` | Enable encryption |
| `--compression-enabled` | `bool` | `true` | Enable compression |
| `--parallel-workers` | `int` | `8` | Number of parallel workers |
| `--dry-run` | `flag` | `false` | Preview without execution |
| `--verbose` | `flag` | `false` | Detailed output |

#### Resource Types

- `users` - User accounts and profiles
- `groups` - Group definitions and memberships
- `permission-sets` - Permission set configurations
- `assignments` - Account assignments and mappings
- `all` - All resource types (default)

#### Examples

```bash
# Full backup of all resources
awsideman backup create --type full

# Incremental backup since specific date
awsideman backup create --type incremental --since 2024-01-01

# Backup specific resources only
awsideman backup create \
    --type full \
    --resource-types users,groups \
    --description "User and group backup"

# Dry run to preview
awsideman backup create --type full --dry-run
```

### `backup list`

List existing backups with filtering options.

```bash
awsideman backup list [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--backup-id` | `string` | - | Filter by specific backup ID |
| `--type` | `full\|incremental` | - | Filter by backup type |
| `--since` | `date` | - | Show backups since date |
| `--until` | `date` | - | Show backups until date |
| `--status` | `completed\|failed\|running` | - | Filter by backup status |
| `--format` | `table\|json\|yaml` | `table` | Output format |
| `--limit` | `int` | `50` | Maximum number of results |

#### Examples

```bash
# List all backups
awsideman backup list

# List recent backups
awsideman backup list --since 2024-01-01

# List failed backups
awsideman backup list --status failed

# JSON output
awsideman backup list --format json --limit 10
```

### `backup validate`

Validate backup integrity and consistency.

```bash
awsideman backup validate <BACKUP_ID> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--checksum` | `flag` | `true` | Verify checksums |
| `--structure` | `flag` | `true` | Validate data structure |
| `--relationships` | `flag` | `true` | Check entity relationships |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# Full validation
awsideman backup validate backup-20241201-143022-abc123

# Structure only
awsideman backup validate backup-20241201-143022-abc123 --checksum false

# JSON output
awsideman backup validate backup-20241201-143022-abc123 --format json
```

### `backup delete`

Delete backups with confirmation.

```bash
awsideman backup delete [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--backup-id` | `string` | - | Specific backup to delete |
| `--older-than` | `duration` | - | Delete backups older than (e.g., 30d, 6m, 1y) |
| `--type` | `full\|incremental` | - | Delete backups of specific type |
| `--dry-run` | `flag` | `false` | Preview deletions without execution |
| `--force` | `flag` | `false` | Skip confirmation prompts |

#### Examples

```bash
# Delete specific backup
awsideman backup delete --backup-id backup-20241201-143022-abc123

# Delete old backups
awsideman backup delete --older-than 90d

# Preview deletions
awsideman backup delete --older-than 30d --dry-run

# Force delete without confirmation
awsideman backup delete --backup-id backup-20241201-143022-abc123 --force
```

### `backup status`

Show detailed status of backup operations.

```bash
awsideman backup status [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--backup-id` | `string` | - | Specific backup ID |
| `--operation-id` | `string` | - | Specific operation ID |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# Show all active operations
awsideman backup status

# Show specific backup status
awsideman backup status --backup-id backup-20241201-143022-abc123

# Show operation details
awsideman backup status --operation-id op-123456
```

## Restore Commands

### `restore restore`

Restore a backup to AWS Identity Center.

```bash
awsideman restore restore <BACKUP_ID> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--strategy` | `overwrite\|skip\|merge\|prompt` | `prompt` | Conflict resolution strategy |
| `--resource-types` | `list` | `all` | Specific resource types to restore |
| `--dry-run` | `flag` | `false` | Preview without execution |
| `--validate-only` | `flag` | `false` | Only validate compatibility |
| `--parallel-workers` | `int` | `8` | Number of parallel workers |
| `--verbose` | `flag` | `false` | Detailed output |

#### Conflict Resolution Strategies

- `overwrite` - Replace existing resources
- `skip` - Skip conflicting resources
- `merge` - Merge with existing resources
- `prompt` - Ask user for each conflict (default)

#### Examples

```bash
# Restore with overwrite strategy
awsideman backup restore backup-20241201-143022-abc123 --strategy overwrite

# Restore specific resources
awsideman backup restore backup-20241201-143022-abc123 \
    --resource-types users,groups \
    --strategy merge

# Dry run to preview
awsideman backup restore backup-20241201-143022-abc123 --dry-run
```

### `restore preview`

Preview restore operations without execution.

```bash
awsideman restore preview <BACKUP_ID> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--strategy` | `overwrite\|skip\|merge` | `overwrite` | Conflict resolution strategy |
| `--resource-types` | `list` | `all` | Specific resource types |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# Preview with overwrite strategy
awsideman restore preview backup-20241201-143022-abc123

# Preview specific resources
awsideman restore preview backup-20241201-143022-abc123 \
    --resource-types users,groups \
    --strategy merge

# JSON output
awsideman restore preview backup-20241201-143022-abc123 --format json
```

### `restore validate`

Validate restore compatibility and requirements.

```bash
awsideman restore validate <BACKUP_ID> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--check-permissions` | `flag` | `true` | Verify required permissions |
| `--check-resources` | `flag` | `true` | Check resource availability |
| `--check-limits` | `flag` | `true` | Verify service limits |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# Full validation
awsideman restore validate backup-20241201-143022-abc123

# Permission check only
awsideman restore validate backup-20241201-143022-abc123 \
    --check-resources false \
    --check-limits false
```

## Schedule Commands

### `backup schedule create`

Create automated backup schedules.

```bash
awsideman backup schedule create [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--name` | `string` | **required** | Schedule name |
| `--cron` | `string` | **required** | Cron expression |
| `--type` | `full\|incremental` | `full` | Backup type |
| `--description` | `string` | - | Human-readable description |
| `--resource-types` | `list` | `all` | Resource types to backup |
| `--enabled` | `bool` | `true` | Enable schedule immediately |

#### Cron Expression Format

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday = 0)
│ │ │ │ │
* * * * *
```

#### Examples

```bash
# Daily backup at 2 AM
awsideman backup schedule create \
    --name "daily-backup" \
    --cron "0 2 * * *" \
    --type full

# Weekly incremental on Sunday at 3 AM
awsideman backup schedule create \
    --name "weekly-incremental" \
    --cron "0 3 * * 0" \
    --type incremental \
    --description "Weekly incremental backup"
```

### `backup schedule list`

List all backup schedules.

```bash
awsideman backup schedule list [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--name` | `string` | - | Filter by schedule name |
| `--enabled` | `bool` | - | Filter by enabled status |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# List all schedules
awsideman backup schedule list

# List enabled schedules only
awsideman backup schedule list --enabled true

# JSON output
awsideman backup schedule list --format json
```

### `backup schedule update`

Update existing backup schedules.

```bash
awsideman backup schedule update <SCHEDULE_NAME> [OPTIONS]
```

#### Options

| Option | Type | Description |
|--------|------|-------------|
| `--cron` | `string` | New cron expression |
| `--type` | `full\|incremental` | New backup type |
| `--description` | `string` | New description |
| `--resource-types` | `list` | New resource types |
| `--enabled` | `bool` | Enable/disable schedule |

#### Examples

```bash
# Update cron expression
awsideman backup schedule update daily-backup --cron "0 3 * * *"

# Change backup type
awsideman backup schedule update weekly-backup --type full

# Disable schedule
awsideman backup schedule update daily-backup --enabled false
```

### `backup schedule delete`

Delete backup schedules.

```bash
awsideman backup schedule delete <SCHEDULE_NAME> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--force` | `flag` | `false` | Skip confirmation |

#### Examples

```bash
# Delete with confirmation
awsideman backup schedule delete daily-backup

# Force delete
awsideman backup schedule delete weekly-backup --force
```

### `backup schedule run`

Manually execute a scheduled backup.

```bash
awsideman backup schedule run <SCHEDULE_NAME> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | `flag` | `false` | Preview without execution |

#### Examples

```bash
# Run schedule immediately
awsideman backup schedule run daily-backup

# Preview execution
awsideman backup schedule run weekly-backup --dry-run
```

### `backup schedule status`

Show schedule status and history.

```bash
awsideman backup schedule status <SCHEDULE_NAME> [OPTIONS]
```

#### Examples

```bash
# Show schedule details
awsideman backup schedule status daily-backup

# Show execution history
awsideman backup schedule status weekly-backup
```

## Performance Commands

### `backup performance enable`

Enable performance optimizations.

```bash
awsideman backup performance enable [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--compression` | `flag` | `true` | Enable compression |
| `--deduplication` | `flag` | `true` | Enable deduplication |
| `--parallel-processing` | `flag` | `true` | Enable parallel processing |
| `--resource-monitoring` | `flag` | `true` | Enable resource monitoring |
| `--max-workers` | `int` | `8` | Maximum parallel workers |
| `--compression-algorithm` | `lz4\|gzip\|zlib` | `lz4` | Compression algorithm |

#### Examples

```bash
# Enable all optimizations
awsideman backup performance enable

# Custom configuration
awsideman backup performance enable \
    --max-workers 16 \
    --compression-algorithm gzip \
    --no-resource-monitoring
```

### `backup performance disable`

Disable performance optimizations.

```bash
awsideman backup performance disable [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--compression` | `flag` | `false` | Disable compression |
| `--deduplication` | `flag` | `false` | Disable deduplication |
| `--parallel-processing` | `flag` | `false` | Disable parallel processing |
| `--resource-monitoring` | `flag` | `false` | Disable resource monitoring |

#### Examples

```bash
# Disable all optimizations
awsideman backup performance disable

# Disable specific features
awsideman backup performance disable --no-compression --no-deduplication
```

### `backup performance status`

Show performance optimization status.

```bash
awsideman backup performance status [OPTIONS]
```

#### Examples

```bash
# Show current status
awsideman backup performance status
```

### `backup performance stats`

Show performance statistics.

```bash
awsideman backup performance stats [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--since` | `date` | `7d` | Show stats since date |
| `--format` | `table\|json` | `table` | Output format |

#### Examples

```bash
# Show recent stats
awsideman backup performance stats

# Show stats since specific date
awsideman backup performance stats --since 2024-01-01

# JSON output
awsideman backup performance stats --format json
```

### `backup performance benchmark`

Run performance benchmarks.

```bash
awsideman backup performance benchmark [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--iterations` | `int` | `3` | Number of benchmark iterations |
| `--data-size` | `small\|medium\|large` | `medium` | Test data size |

#### Examples

```bash
# Run standard benchmark
awsideman backup performance benchmark

# Custom benchmark
awsideman backup performance benchmark \
    --iterations 5 \
    --data-size large
```

### `backup performance clear`

Clear performance optimization caches.

```bash
awsideman backup performance clear [OPTIONS]
```

#### Examples

```bash
# Clear all caches
awsideman backup performance clear
```

## Export/Import Commands

### `backup export`

Export backup data in various formats.

```bash
awsideman backup export <BACKUP_ID> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `json\|yaml\|csv` | `json` | Export format |
| `--output` | `string` | - | Output file path |
| `--resource-types` | `list` | `all` | Specific resource types |
| `--include-metadata` | `flag` | `true` | Include backup metadata |

#### Examples

```bash
# Export to JSON
awsideman backup export backup-20241201-143022-abc123 --format json

# Export specific resources to file
awsideman backup export backup-20241201-143022-abc123 \
    --format yaml \
    --output users-groups.yaml \
    --resource-types users,groups
```

### `backup import`

Import backup data from external sources.

```bash
awsideman backup import <SOURCE> [OPTIONS]
```

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `auto\|json\|yaml\|csv` | `auto` | Import format |
| `--validate-only` | `flag` | `false` | Only validate import data |
| `--dry-run` | `flag` | `false` | Preview import without execution |

#### Examples

```bash
# Import from JSON file
awsideman backup import backup-data.json

# Import with validation
awsideman backup import users.yaml --validate-only

# Preview import
awsideman backup import backup-data.json --dry-run
```

## Global Options

All commands support these global options:

| Option | Type | Description |
|--------|------|-------------|
| `--config` | `string` | Configuration file path |
| `--profile` | `string` | AWS profile name |
| `--region` | `string` | AWS region |
| `--verbose` | `flag` | Detailed output |
| `--quiet` | `flag` | Minimal output |
| `--version` | `flag` | Show version and exit |
| `--help` | `flag` | Show help and exit |

## Output Formats

### Table Format (Default)
Human-readable tabular output with colors and symbols.

### JSON Format
Machine-readable JSON output for scripting and automation.

### YAML Format
Human-readable YAML output for configuration files.

## Examples

### Complete Backup Workflow

```bash
# 1. Create backup
awsideman backup create --type full --description "Daily backup"

# 2. List backups
awsideman backup list --recent

# 3. Validate backup
awsideman backup validate backup-20241201-143022-abc123

# 4. Preview restore
awsideman restore preview backup-20241201-143022-abc123

# 5. Execute restore (if needed)
awsideman restore restore backup-20241201-143022-abc123 --strategy overwrite
```

### Automated Backup Setup

```bash
# 1. Create daily schedule
awsideman backup schedule create \
    --name "daily-backup" \
    --cron "0 2 * * *" \
    --type full

# 2. Create weekly schedule
awsideman backup schedule create \
    --name "weekly-incremental" \
    --cron "0 3 * * 0" \
    --type incremental

# 3. List schedules
awsideman backup schedule list

# 4. Test schedule
awsideman backup schedule run daily-backup --dry-run
```

### Performance Optimization

```bash
# 1. Enable optimizations
awsideman backup performance enable \
    --max-workers 16 \
    --compression-algorithm lz4

# 2. Check status
awsideman backup performance status

# 3. Run benchmark
awsideman backup performance benchmark

# 4. Monitor performance
awsideman backup performance stats
```
