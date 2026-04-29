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

## Notification Setup

### Configure Telegram bot

To enable Telegram notifications:

1.  **Create a Bot**: Open Telegram and message [@BotFather](https://t.me/botfather). Send `/newbot` and follow instructions to get your **Bot Token**.
2.  **Get your Chat ID**:
    - Start a conversation with your new bot (click the link in BotFather's message and press **Start**).
    - Send a dummy message to the bot.
    - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser.
    - Look for `"chat":{"id":123456789...}`. That number is your **Chat ID**.
3.  **Update `.env`**:
    ```env
    TELEGRAM_BOT_TOKEN="your_token_here"
    TELEGRAM_CHAT_ID="your_chat_id_here"
    ```
4.  **Test the setup**:
    ```bash
    uv run jobhunter notify test --channel telegram --message "Hello from Job Hunter!"
    ```

### Configure Gmail SMTP

To enable email notifications using Gmail:

1.  **Enable 2FA**: Ensure your Google account has 2-Step Verification enabled.
2.  **Generate App Password**:
    - Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
    - App name: "Job-Hunter-EU".
    - Copy the generated 16-character password.
3.  **Update `.env`**:
    ```env
    SMTP_USER="your_email@gmail.com"
    SMTP_PASSWORD="your_app_password_without_spaces"
    DIGEST_TO_EMAIL="where_to_receive_the_digest@email.com"
    ```
4.  **Test the setup**:
    ```bash
    uv run jobhunter notify test --channel email --subject "Test Email" --message "Hello from Job Hunter!"
    ```

### Diagnosticar notificaciones que no llegan

Si esperas notificaciones y no se están recibiendo:

1.  **Verificar estado del canal**:
    ```bash
    uv run jobhunter notify status
    ```
    Revisa si el canal aparece como `ENABLED`. Si está `DISABLED`, comprueba que las variables de entorno en `.env` coinciden con los nombres esperados.

2.  **Revisar intentos recientes**:
    El mismo comando `notify status` muestra los últimos 10 intentos. Busca errores específicos en la columna de status.

3.  **Comprobar fallos en 24h**:
    Si hay una cuenta de fallos alta, es probable que haya un problema de red o de credenciales (ej. App Password de Google revocado).

4.  **Verificar políticas de idempotencia**:
    - **Tier-A**: Solo se envía una notificación por `job_id`. Si ya se intentó (con éxito o fallo), no se reintenta automáticamente para evitar spam.
    - **Digest**: Solo se envía uno por semana ISO.
    Puedes consultar la tabla `notifications_sent` para ver qué llaves de deduplicación ya existen.

5.  **Probar manualmente**:
    Usa el comando `notify test` para descartar problemas de configuración del canal independientemente de la lógica de negocio.
