"""
PostgreSQL Backup Script for PJX Database
Automatically backs up the 'pjx' database and manages retention

Usage:
    python scripts/backup_postgres.py

Features:
    - Backs up 'pjx' database from Docker container
    - Saves to backups/ folder with timestamp
    - Auto-deletes backups older than 7 days
    - Simple and easy to understand

Restore Instructions:
    1. Stop all scrapers first
    2. Run: docker exec -i pjx-postgres psql -U postgres -d pjx < backups/pjx_backup_TIMESTAMP.sql
    3. Restart scrapers
"""

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
DOCKER_CONTAINER = "pjx-postgres"
DB_NAME = "pjx"
DB_USER = "postgres"
BACKUP_DIR = Path(__file__).parent.parent / "backups"
RETENTION_DAYS = 7  # Keep last 7 days of backups


def create_backup_dir():
    """Ensure backup directory exists"""
    BACKUP_DIR.mkdir(exist_ok=True)
    print(f"[INFO] Backup directory: {BACKUP_DIR}")


def check_docker_container():
    """Verify Docker container is running"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={DOCKER_CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )

        if DOCKER_CONTAINER not in result.stdout:
            print(f"[ERROR] Docker container '{DOCKER_CONTAINER}' is not running!")
            print("[INFO] Start it with: docker start pjx-postgres")
            return False

        print(f"[OK] Docker container '{DOCKER_CONTAINER}' is running")
        return True

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to check Docker: {e}")
        return False
    except FileNotFoundError:
        print("[ERROR] Docker is not installed or not in PATH")
        return False


def create_backup():
    """Create a new database backup"""
    # Generate timestamp filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"pjx_backup_{timestamp}.sql"

    print(f"\n[BACKUP] Starting backup at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[BACKUP] Database: {DB_NAME}")
    print(f"[BACKUP] Output: {backup_file}")

    try:
        # Run pg_dump inside Docker container
        command = [
            "docker", "exec",
            DOCKER_CONTAINER,
            "pg_dump",
            "-U", DB_USER,
            "-d", DB_NAME,
            "--clean",  # Include DROP statements
            "--if-exists",  # Use IF EXISTS for drops
            "--create",  # Include CREATE DATABASE
        ]

        # Execute and save output
        with open(backup_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                command,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

        # Check file was created and has content
        if backup_file.exists() and backup_file.stat().st_size > 0:
            size_mb = backup_file.stat().st_size / (1024 * 1024)
            print(f"[SUCCESS] Backup created: {backup_file.name}")
            print(f"[SUCCESS] Size: {size_mb:.2f} MB")
            return True
        else:
            print(f"[ERROR] Backup file is empty or missing")
            return False

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Backup failed: {e}")
        if e.stderr:
            print(f"[ERROR] Details: {e.stderr}")

        # Clean up failed backup file
        if backup_file.exists():
            backup_file.unlink()

        return False

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False


def cleanup_old_backups():
    """Delete backups older than RETENTION_DAYS"""
    print(f"\n[CLEANUP] Checking for backups older than {RETENTION_DAYS} days...")

    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    deleted = 0
    kept = 0

    # Find all backup files
    backup_files = sorted(BACKUP_DIR.glob("pjx_backup_*.sql"))

    for backup_file in backup_files:
        # Get file modification time
        file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)

        if file_time < cutoff_date:
            try:
                backup_file.unlink()
                print(f"[DELETED] {backup_file.name} (from {file_time.strftime('%Y-%m-%d')})")
                deleted += 1
            except Exception as e:
                print(f"[WARNING] Could not delete {backup_file.name}: {e}")
        else:
            kept += 1

    print(f"[CLEANUP] Kept {kept} recent backups, deleted {deleted} old backups")


def list_backups():
    """List all available backups"""
    print("\n[BACKUPS] Available backups:")

    backup_files = sorted(BACKUP_DIR.glob("pjx_backup_*.sql"), reverse=True)

    if not backup_files:
        print("  No backups found")
        return

    for backup_file in backup_files:
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
        age_days = (datetime.now() - file_time).days

        print(f"  - {backup_file.name:<35} {size_mb:>6.2f} MB  ({age_days} days old)")


def main():
    """Main backup routine"""
    print("="*70)
    print("PostgreSQL Backup Script - PJX Database")
    print("="*70)

    # Step 1: Create backup directory
    create_backup_dir()

    # Step 2: Check Docker container
    if not check_docker_container():
        print("\n[FAILED] Cannot proceed without running Docker container")
        return False

    # Step 3: Create backup
    success = create_backup()

    if not success:
        print("\n[FAILED] Backup was not successful")
        return False

    # Step 4: Cleanup old backups
    cleanup_old_backups()

    # Step 5: List all backups
    list_backups()

    print("\n" + "="*70)
    print("[DONE] Backup completed successfully!")
    print("="*70)

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
