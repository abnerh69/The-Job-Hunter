# Runbook

This document contains procedures for maintaining and recovering the Job Hunter EU system.

## Database Procedures

### 1. Restore Database from Backup

To restore the database from a compressed backup file:

1.  **Decompress and pipe to `psql`**:
    ```bash
    gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | psql $DATABASE_URL
    ```
    *Alternatively, if using the Docker setup:*
    ```bash
    gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | docker exec -i jobhunter-postgres psql -U jobhunter -d jobhunter
    ```

### 2. Complete Local DB Reset

If you need to completely wipe the local database and start fresh:

1.  **Stop and remove containers and volumes**:
    ```bash
    docker compose down -v
    ```
2.  **Start the services**:
    ```bash
    docker compose up -d
    ```
3.  **Apply migrations**:
    ```bash
    uv run alembic upgrade head
    ```
4.  **(Optional) Seed with sample data**:
    ```bash
    uv run jobhunter db-seed --scenario rich
    ```

### 3. Re-run Migrations from Scratch

If you need to test the migration path from zero:

1.  **Drop the `alembic_version` table and all existing tables**:
    *(Warning: This will delete all data)*
    ```bash
    psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    ```
2.  **Run migrations**:
    ```bash
    uv run alembic upgrade head
    ```

### 4. Create a Manual Backup

You can use the CLI command:
```bash
uv run jobhunter db-backup --output my_backup.sql.gz
```
Or run the script directly:
```bash
./scripts/backup_db.sh my_backup.sql.gz
```

## Troubleshooting

### "pg_dump: command not found"
Ensure you have the PostgreSQL client tools installed.
- **Ubuntu/Debian**: `sudo apt-get install postgresql-client`
- **macOS**: `brew install postgresql`

### Re-recording cassettes when an API changes

If a job source API changes its schema or you add new fields, you may need to re-record the HTTP cassettes used in integration tests.

1.  **Delete the old cassettes**:
    ```bash
    rm -rf tests/integration/sources/cassettes/*
    ```
2.  **Run tests with record mode**:
    ```bash
    uv run pytest tests/integration/sources/ --record-mode=once
    ```
    *Note: This requires an active internet connection.*

### "role 'jobhunter' does not exist"
This usually happens when trying to connect to a fresh Postgres instance that hasn't been initialized by the Docker Compose script. Ensure the environment variables match the expected user.
