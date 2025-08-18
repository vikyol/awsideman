# Automation Scripts

Key automation examples for backup and restore operations.

## Shell Scripts

### 1. Daily Backup Script

**File: `daily-backup.sh`**
```bash
#!/bin/bash

# Daily backup automation
BACKUP_TYPE="full"
BACKUP_DESCRIPTION="Daily backup - $(date +%Y-%m-%d)"
LOG_FILE="/var/log/awsideman/daily-backup.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Starting daily backup process"

# Create backup
BACKUP_ID=$(awsideman backup create \
    --type "$BACKUP_TYPE" \
    --description "$BACKUP_DESCRIPTION" \
    --format json | jq -r '.backup_id')

log "Backup created: $BACKUP_ID"

# Validate backup
awsideman backup validate "$BACKUP_ID"
log "Backup validation completed"

# Clean up old backups
awsideman backup delete --older-than 30d
log "Daily backup process completed"
```

### 2. Disaster Recovery Script

**File: `disaster-recovery.sh`**
```bash
#!/bin/bash

# Disaster recovery script
BACKUP_ID="$1"
STRATEGY="${2:-overwrite}"

if [ -z "$BACKUP_ID" ]; then
    echo "Usage: $0 <backup-id> [strategy]"
    exit 1
fi

echo "Starting disaster recovery for backup: $BACKUP_ID"

# Validate backup
awsideman backup validate "$BACKUP_ID"

# Preview restore
awsideman restore preview "$BACKUP_ID" --strategy "$STRATEGY"

# Execute restore
awsideman restore restore "$BACKUP_ID" --strategy "$STRATEGY"

echo "Disaster recovery completed"
```

## Python Scripts

### 1. Backup Health Check

**File: `backup-health-check.py`**
```python
#!/usr/bin/env python3
"""Backup system health checker."""

import subprocess
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(command):
    """Run awsideman command."""
    try:
        result = subprocess.run(
            command + ['--format', 'json'],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except Exception as e:
        logger.error(f"Command failed: {e}")
        return {}

def check_backup_health():
    """Check backup system health."""
    logger.info("Checking backup system health...")

    # Check performance status
    status = run_command(['awsideman', 'backup', 'performance', 'status'])
    if not status:
        logger.error("Backup system unavailable")
        return False

    # Check recent backups
    backups = run_command(['awsideman', 'backup', 'list', '--recent', '--limit', '5'])
    if not backups:
        logger.error("No recent backups found")
        return False

    # Check for failed backups
    failed = [b for b in backups.get('backups', []) if b.get('status') == 'failed']
    if failed:
        logger.warning(f"Found {len(failed)} failed backups")

    logger.info("Health check completed")
    return True

if __name__ == '__main__':
    success = check_backup_health()
    exit(0 if success else 1)
```

### 2. Backup Migration

**File: `backup-migration.py`**
```python
#!/usr/bin/env python3
"""Backup migration tool."""

import argparse
import subprocess
import json

def migrate_backup(backup_id, source_profile, target_profile):
    """Migrate backup between environments."""
    print(f"Migrating backup {backup_id}")

    # Export from source
    export_cmd = [
        'awsideman', 'backup', 'export',
        backup_id, '--format', 'json',
        '--output', f"/tmp/migration_{backup_id}.json"
    ]

    subprocess.run(export_cmd + ['--profile', source_profile], check=True)

    # Import to target
    import_cmd = [
        'awsideman', 'backup', 'import',
        f"/tmp/migration_{backup_id}.json"
    ]

    result = subprocess.run(import_cmd + ['--profile', target_profile],
                           capture_output=True, text=True, check=True)

    print("Migration completed successfully")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('backup_id')
    parser.add_argument('--source-profile', required=True)
    parser.add_argument('--target-profile', required=True)

    args = parser.parse_args()
    migrate_backup(args.backup_id, args.source_profile, args.target_profile)
```

## CI/CD Examples

### 1. GitHub Actions

**File: `.github/workflows/backup-testing.yml`**
```yaml
name: Backup Testing

on:
  push:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * *'

jobs:
  backup-testing:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install poetry
        poetry install

    - name: Configure AWS
      uses: aws-actions/configure-aws-credentials@v2
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1

    - name: Run tests
      run: |
        poetry run pytest tests/unit/backup_restore/ -v
        poetry run pytest tests/performance/ -v
```

### 2. GitLab CI

**File: `.gitlab-ci.yml`**
```yaml
stages:
  - test
  - deploy

backup-testing:
  stage: test
  image: python:3.11
  script:
    - pip install poetry
    - poetry install
    - poetry run pytest tests/unit/backup_restore/ -v
  artifacts:
    paths:
      - test-results.xml
    expire_in: 1 week

backup-deployment:
  stage: deploy
  image: python:3.11
  script:
    - pip install poetry
    - poetry install
    - poetry run python scripts/deploy-backup-system.py
  only:
    - main
  when: manual
```

## Cron Jobs

### System Cron

**File: `/etc/cron.d/awsideman-backup`**
```bash
# Daily backup at 2 AM
0 2 * * * awsideman /usr/local/bin/awsideman backup create --type full

# Weekly incremental on Sunday at 3 AM
0 3 * * 0 awsideman /usr/local/bin/awsideman backup create --type incremental --since 7d

# Daily health check at 6 AM
0 6 * * * awsideman /usr/local/bin/awsideman backup performance status

# Monthly cleanup on 15th at 1 AM
0 1 15 * * awsideman /usr/local/bin/awsideman backup delete --older-than 90d
```

### User Cron

**Add to crontab: `crontab -e`**
```bash
# Check backup status every hour during business hours
0 9-17 * * 1-5 /usr/local/bin/awsideman backup status

# Weekly validation
0 8 * * 1 /usr/local/bin/awsideman backup list --recent | xargs -I {} /usr/local/bin/awsideman backup validate {}

# Daily health check
0 10 * * * /usr/local/bin/python3 /home/user/scripts/backup-health-check.py
```

## Systemd Services

### Backup Service

**File: `/etc/systemd/system/awsideman-backup.service`**
```ini
[Unit]
Description=AWS Identity Center Backup Service
After=network.target

[Service]
Type=simple
User=awsideman
Environment=AWS_PROFILE=backup-admin
ExecStart=/usr/local/bin/awsideman backup schedule start
Restart=always

[Install]
WantedBy=multi-user.target
```

### Backup Timer

**File: `/etc/systemd/system/awsideman-backup.timer`**
```ini
[Unit]
Description=Run Backup Service
Requires=awsideman-backup.service

[Timer]
Unit=awsideman-backup.service
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Usage Examples

### Run Daily Backup
```bash
# Make executable
chmod +x daily-backup.sh

# Run manually
./daily-backup.sh

# Add to cron
echo "0 2 * * * /path/to/daily-backup.sh" | crontab -
```

### Run Health Check
```bash
# Run health check
python3 backup-health-check.py

# Add to cron for monitoring
echo "0 6 * * * /usr/bin/python3 /path/to/backup-health-check.py" | crontab -
```

### Migrate Backup
```bash
# Migrate between profiles
python3 backup-migration.py backup-123 \
    --source-profile dev \
    --target-profile prod
```

## Next Steps

1. **[Configuration Templates](configuration-templates.md)** - Ready-to-use configs
2. **[Enterprise Examples](enterprise-examples.md)** - Complex workflows
3. **[Troubleshooting](../troubleshooting.md)** - Solve problems
4. **[CLI Reference](../cli-reference.md)** - Command reference
