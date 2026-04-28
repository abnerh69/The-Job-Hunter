#!/bin/bash
# Backup script for Job Hunter EU database
# Usage: ./scripts/backup_db.sh [output_path]

set -e
set -o pipefail

# Default output path if not provided
DEFAULT_FILENAME="backup_$(date +%Y%m%d_%H%M%S).sql.gz"
OUTPUT_FILE=${1:-$DEFAULT_FILENAME}

# Check if pg_dump is installed
if ! command -v pg_dump &> /dev/null; then
    echo "Error: pg_dump is not installed."
    exit 1
fi

echo "--- Job Hunter EU: Database Backup ---"

# Use DATABASE_URL if available, otherwise fallback to defaults
if [ -z "$DATABASE_URL" ]; then
    echo "Warning: DATABASE_URL not set. Attempting to use local defaults (host: localhost, user: jobhunter, db: jobhunter)."
    # For local defaults, we use individual variables to avoid quoting issues with multiple flags
    DB_HOST="localhost"
    DB_USER="jobhunter"
    DB_NAME="jobhunter"

    # Execute pg_dump and compress
    echo "Exporting database to $OUTPUT_FILE..."
    pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" | gzip > "$OUTPUT_FILE"
else
    echo "Using connection string from DATABASE_URL."
    # Execute pg_dump and compress
    echo "Exporting database to $OUTPUT_FILE..."
    pg_dump "$DATABASE_URL" | gzip > "$OUTPUT_FILE"
fi

# Verify integrity
echo "Verifying backup integrity..."
if gunzip -t "$OUTPUT_FILE"; then
    echo "Integrity check passed."
else
    echo "Error: Integrity check failed for $OUTPUT_FILE"
    exit 1
fi

echo "Backup completed successfully: $(realpath "$OUTPUT_FILE")"
echo "---------------------------------------"
