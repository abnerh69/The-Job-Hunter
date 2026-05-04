import os
import subprocess
import gzip
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
import structlog
from botocore.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from jobhunter.config import Settings

logger = structlog.get_logger(__name__)


def create_compressed_backup(db_url: str, output_path: Path) -> Path:
    """
    Creates a compressed backup of the database.
    Supports SQLite and Postgres.
    """
    logger.info(
        "Creating database backup", db_url=db_url.split("@")[-1] if "@" in db_url else db_url
    )

    if db_url.startswith("sqlite"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        if not db_path.exists():
            raise FileNotFoundError(f"SQLite database not found at {db_path}")

        with open(db_path, "rb") as f_in:
            with gzip.open(output_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        # Postgres
        try:
            with open(output_path, "wb") as f_out:
                # We pipe pg_dump to gzip for maximum efficiency
                dump_proc = subprocess.Popen(
                    ["pg_dump", db_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                gzip_proc = subprocess.Popen(
                    ["gzip", "-c"], stdin=dump_proc.stdout, stdout=f_out, stderr=subprocess.PIPE
                )

                # Allow dump_proc to receive a SIGPIPE if gzip_proc exits.
                if dump_proc.stdout:
                    dump_proc.stdout.close()

                _, dump_stderr = dump_proc.communicate()
                _, gzip_stderr = gzip_proc.communicate()

                if dump_proc.returncode != 0:
                    raise RuntimeError(f"pg_dump failed: {dump_stderr.decode()}")
                if gzip_proc.returncode != 0:
                    raise RuntimeError(f"gzip failed: {gzip_stderr.decode()}")

        except Exception as e:
            if output_path.exists():
                output_path.unlink()
            raise e

    logger.info(
        "Backup created successfully", path=str(output_path), size_bytes=output_path.stat().st_size
    )
    return output_path


def restore_from_compressed_backup(backup_path: Path, db_url: str) -> None:
    """
    Restores the database from a compressed backup.
    WARNING: This is a destructive operation.
    """
    logger.info(
        "Restoring database from backup",
        backup_path=str(backup_path),
        db_url=db_url.split("@")[-1] if "@" in db_url else db_url,
    )

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found at {backup_path}")

    if db_url.startswith("sqlite"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        # For SQLite, we just overwrite the file
        with gzip.open(backup_path, "rb") as f_in:
            with open(db_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        # Postgres
        try:
            # We use gunzip -c | psql
            gunzip_proc = subprocess.Popen(
                ["gunzip", "-c", str(backup_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            psql_proc = subprocess.Popen(
                ["psql", db_url],
                stdin=gunzip_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if gunzip_proc.stdout:
                gunzip_proc.stdout.close()

            _, gunzip_stderr = gunzip_proc.communicate()
            psql_stdout, psql_stderr = psql_proc.communicate()

            if gunzip_proc.returncode != 0:
                raise RuntimeError(f"gunzip failed: {gunzip_stderr.decode()}")
            if psql_proc.returncode != 0:
                # Note: psql might return non-zero for some warnings, but usually it's an error
                raise RuntimeError(f"psql restore failed: {psql_stderr.decode()}")

        except Exception as e:
            raise e

    logger.info("Restore completed successfully")


class BackupStorage:
    """
    Handles backup storage (Local, S3, or B2).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.BACKUP_STORAGE_PROVIDER
        self.bucket = settings.BACKUP_STORAGE_BUCKET
        self.local_dir = Path("backups")
        self.local_dir.mkdir(exist_ok=True)

        if self.provider in ("s3", "b2"):
            if not self.bucket:
                raise ValueError(f"BACKUP_STORAGE_BUCKET must be set for {self.provider}")

            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.BACKUP_ACCESS_KEY.get_secret_value()
                if settings.BACKUP_ACCESS_KEY
                else None,
                aws_secret_access_key=settings.BACKUP_SECRET_KEY.get_secret_value()
                if settings.BACKUP_SECRET_KEY
                else None,
                config=Config(signature_version="s3v4"),
                endpoint_url=settings.BACKUP_ENDPOINT_URL or os.environ.get("BACKUP_ENDPOINT_URL"),
            )

    def upload(self, local_path: Path) -> str:
        """Uploads a backup to the configured storage."""
        filename = local_path.name
        if self.provider == "local":
            target_path = self.local_dir / filename
            if local_path != target_path:
                shutil.copy2(local_path, target_path)
            return str(target_path)
        else:
            if not self.bucket:
                raise ValueError("BACKUP_STORAGE_BUCKET not set")
            logger.info(
                "Uploading backup to remote storage",
                provider=self.provider,
                bucket=self.bucket,
                filename=filename,
            )
            self.s3_client.upload_file(str(local_path), self.bucket, filename)
            return f"{self.provider}://{self.bucket}/{filename}"

    def download(self, filename: str, target_dir: Path) -> Path:
        """Downloads a backup from the configured storage."""
        target_path = target_dir / filename
        if self.provider == "local":
            source_path = self.local_dir / filename
            if not source_path.exists():
                raise FileNotFoundError(f"Local backup not found: {source_path}")
            shutil.copy2(source_path, target_path)
        else:
            if not self.bucket:
                raise ValueError("BACKUP_STORAGE_BUCKET not set")
            logger.info(
                "Downloading backup from remote storage",
                provider=self.provider,
                bucket=self.bucket,
                filename=filename,
            )
            self.s3_client.download_file(self.bucket, filename, str(target_path))
        return target_path

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists available backups."""
        backups: List[Dict[str, Any]] = []
        if self.provider == "local":
            for f in self.local_dir.glob("*.sql.gz"):
                stats = f.stat()
                backups.append(
                    {
                        "id": f.name,
                        "size": stats.st_size,
                        "created_at": datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
                    }
                )
        else:
            if not self.bucket:
                raise ValueError("BACKUP_STORAGE_BUCKET not set")
            response = self.s3_client.list_objects_v2(Bucket=self.bucket)
            if "Contents" in response:
                for obj in response["Contents"]:
                    if obj["Key"] and obj["Key"].endswith(".sql.gz"):
                        backups.append(
                            {
                                "id": obj["Key"],
                                "size": obj.get("Size", 0),
                                "created_at": obj.get("LastModified", datetime.now(timezone.utc)),
                            }
                        )

        # Sort by date descending
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def delete(self, filename: str) -> None:
        """Deletes a backup from storage."""
        if self.provider == "local":
            path = self.local_dir / filename
            if path.exists():
                path.unlink()
        else:
            if not self.bucket:
                raise ValueError("BACKUP_STORAGE_BUCKET not set")
            logger.info(
                "Deleting backup from remote storage",
                provider=self.provider,
                bucket=self.bucket,
                filename=filename,
            )
            self.s3_client.delete_object(Bucket=self.bucket, Key=filename)


def validate_db_integrity(
    session: Session, expected_migration_version: Optional[str] = None
) -> Dict[str, bool]:
    """
    Validates the integrity of the database by checking for
    the existence of critical tables, minimum data counts,
    and migration version.
    """
    logger.info("Validating database integrity")

    critical_tables = ["jobs", "applications", "outreach_contacts", "alembic_version"]
    results = {}

    for table in critical_tables:
        try:
            # Check if table exists and has a reasonable count (or at least doesn't crash)
            # Table names are validated against critical_tables whitelist above
            query = text(f"SELECT COUNT(*) FROM {table}")  # nosec B608
            count = session.execute(query).scalar()

            # Simple heuristic: at least jobs and alembic_version should have data
            if table in ("jobs", "alembic_version") and count == 0:
                logger.warning(f"Integrity check WARNING: Table {table} is empty")
                # We don't mark it as False yet because a fresh DB might be okay,
                # but for a production restore, it might be an issue.

            results[table] = True
            logger.info(f"Integrity check: Table {table} exists", row_count=count)
        except Exception as e:
            logger.error(f"Integrity check FAILED: Table {table} error", error=str(e))
            results[table] = False

    # Check migration version
    if expected_migration_version:
        try:
            query = text("SELECT version_num FROM alembic_version")
            current_version = session.execute(query).scalar()
            if current_version == expected_migration_version:
                results["migration_version"] = True
                logger.info("Integrity check: Migration version matches", version=current_version)
            else:
                results["migration_version"] = False
                logger.error(
                    "Integrity check FAILED: Migration version mismatch",
                    expected=expected_migration_version,
                    current=current_version,
                )
        except Exception as e:
            logger.error("Integrity check FAILED: Could not check migration version", error=str(e))
            results["migration_version"] = False

    return results


def run_backup_cleanup(storage: BackupStorage, retention_weeks: int) -> int:
    """
    Deletes backups older than retention_weeks.
    """
    logger.info("Running backup cleanup", retention_weeks=retention_weeks)

    all_backups = storage.list_backups()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=retention_weeks)

    deleted_count = 0
    for b in all_backups:
        if b["created_at"] < cutoff:
            logger.info(
                "Cleanup: Deleting old backup", backup_id=b["id"], age=now - b["created_at"]
            )
            storage.delete(b["id"])
            deleted_count += 1

    logger.info("Backup cleanup finished", deleted_count=deleted_count)
    return deleted_count
