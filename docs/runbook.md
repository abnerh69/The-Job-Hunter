# Runbook

This document contains procedures for maintaining and recovering the Job Hunter EU system.

## Database Procedures

### 0. Hosted Database (Neon) Setup

We use [Neon](https://neon.tech) as our hosted PostgreSQL provider for production and CI/CD environments.

1.  **Create a Neon Project**:
    - Select the **US East (N. Virginia)** region for low latency.
    - Use the Free Tier (0.5 GB storage, autoscale).
2.  **Connection Pooling**:
    - Always use the connection pooling endpoint (it contains `-pooler` in the hostname) for GitHub Actions and serverless environments.
3.  **Initial Migration**:
    - Once you have the `DATABASE_URL`, run migrations from your local machine:
    ```bash
    DATABASE_URL="your_neon_connection_string" uv run alembic upgrade head
    ```

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

## Secrets Management

The system relies on several GitHub Secrets for CI/CD and production workflows.

### Required Secrets

| Secret Name | Description |
| :--- | :--- |
| `DATABASE_URL_PROD` | Full PostgreSQL connection string (with pooler). |
| `ANTHROPIC_API_KEY` | API Key for Claude (Scoring, Cover Letters). |
| `DASHBOARD_PASSWORD` | Password for Streamlit dashboard access. |
| `TELEGRAM_BOT_TOKEN` | (Optional) Token for Telegram notifications. |
| `TELEGRAM_CHAT_ID` | (Optional) Chat ID for Telegram notifications. |
| `SMTP_USER` | (Optional) Gmail/SMTP user for digests. |
| `SMTP_PASSWORD` | (Optional) App password for SMTP. |
| `DIGEST_TO_EMAIL` | (Optional) Recipient email for weekly digest. |

### Emergency Procedures

**If a secret is leaked:**
1.  **Revoke**: Revoke the API key or password at the provider (e.g., Anthropic Console, Google Account).
2.  **Rotate**: Generate a new value.
3.  **Update GH Secrets**: Use the `gh` CLI or Web UI to update the secret.
    ```bash
    gh secret set LEAKED_SECRET_NAME --body "new_value"
    ```
4.  **Redeploy**: Re-run any active workflows or redeploy the dashboard.

**Migrating Database Provider:**
1.  **Backup**: Create a full dump using `pg_dump`.
2.  **New Provider**: Setup the new DB and apply migrations (`alembic upgrade head`).
3.  **Restore**: Import the dump.
4.  **Update Secret**: Update `DATABASE_URL_PROD` in GitHub Secrets.

## Workflow & Automation

### Pipeline Cycle

The `Pipeline Cycle` workflow runs every 8 hours (`00:00`, `08:00`, `16:00` UTC). It orchestrates the full cycle: ingestion, scoring, and notification dispatch.

**Manual Execution:**
- Go to the **Actions** tab in GitHub.
- Select **Pipeline Cycle**.
- Click **Run workflow**.
- (Optional) Provide a `limit` or specific `source` names (comma-separated).

**Monitoring & Investigation:**
1.  **Status**: Check the workflow run list. A green checkmark means success (or partial failure that didn't crash the system).
2.  **Logs**: Each run uploads a `pipeline-logs-{id}.jsonl` artifact. Download it to see structured logs of all steps.
3.  **Alerts**: If a workflow fails, an alert is sent to the configured Telegram channel with a link to the failed run.

## Dashboard Deployment

### Deploy dashboard a Fly.io

Para desplegar el dashboard en Fly.io siguiendo un enfoque productivo:

1.  **Instalar Fly CLI**: Sigue las instrucciones en [fly.io/docs/hands-on/install-cli/](https://fly.io/docs/hands-on/install-cli/).
2.  **Login**: `fly auth login`.
3.  **Launch**: Ejecuta `fly launch` en la raíz del proyecto.
    - Selecciona el `Dockerfile.dashboard` cuando se te pregunte.
    - No configurar base de datos Postgres de Fly si ya usas una externa.
4.  **Configurar Secretos**:
    ```bash
    fly secrets set DASHBOARD_PASSWORD="tu_password_seguro" \
                   DATABASE_URL="tu_url_de_base_de_datos" \
                   ANTHROPIC_API_KEY="tu_api_key"
    ```
5.  **Desplegar**: `fly deploy --dockerfile Dockerfile.dashboard`.
6.  **Acceso**: El dashboard estará disponible en `https://<tu-app-name>.fly.dev`. Fly.io gestiona el HTTPS automáticamente.

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
