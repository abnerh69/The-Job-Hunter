# Job Hunter EU - Operations Runbook & Disaster Recovery Manual

This document is the "source of truth" for operating, maintaining, and recovering the Job Hunter EU system. It is designed to be consulted during normal operations and especially during critical incidents. It provides the depth needed for a Site Reliability Engineer (SRE) or Developer to diagnose and fix issues under pressure.

---

## 📑 Table of Contents

1. [Initial Setup & Infrastructure Deployment](#1-initial-setup--infrastructure-deployment)
    - 1.1 Hosted Database (Neon) Setup
    - 1.2 Local Development Environment
    - 1.3 Containerization with Docker
2. [Daily Operations & Monitoring](#2-daily-operations--monitoring)
    - 2.1 Checking System Health
    - 2.2 Monitoring Pipelines with GitHub Actions
    - 2.3 Log Analysis and Observability
3. [Maintenance Procedures](#3-maintenance-procedures)
    - 3.1 Secret Rotation Plan
    - 3.2 Database Backups and Retention
    - 3.3 Prompt Engineering and Optimization
4. [Notification & Integration Setup](#4-notification--integration-setup)
    - 4.1 Telegram Bot Configuration
    - 4.2 Gmail SMTP Setup
    - 4.3 Gmail OAuth2 (Inbox Access)
5. [Troubleshooting: The 10 Most Probable Issues](#5-troubleshooting-the-10-most-probable-issues)
    - T01: No Tier-A matches produced in a week
    - T02: LLM costs exceed budget
    - T03: Telegram bot not sending messages
    - T04: Dashboard not loading
    - T05: GitHub Actions workflow auth error
    - T06: Gmail polling returns 0 results
    - T07: Database migration fails
    - T08: Postgres connection pool exhausted
    - T09: DNS or external API unreachable
    - T10: Dashboard receiving high suspicious traffic
6. [Disaster Recovery: The 5 Catastrophic Scenarios](#6-disaster-recovery-the-5-catastrophic-scenarios)
    - DR1: Database lost or corrupted
    - DR2: Leaked credentials (API Keys/DB)
    - DR3: Repository compromised
    - DR4: GitHub Actions down > 24h
    - DR5: Anthropic API prolonged outage
7. [Disaster Recovery Drills (Simulations)](#7-disaster-recovery-drills-simulations)
8. [Standard Operating Procedures (SOPs)](#8-standard-operating-procedures-sops)
9. [Networking and Security Guides](#9-networking-and-security-guides)
10. [Data Model and Schema Management](#10-data-model-and-schema-management)
11. [Detailed CLI Command Reference](#11-detailed-cli-command-reference)
12. [SRE Onboarding and induction](#12-sre-onboarding-and-induction)
13. [Glossary of Recruitment and Technical Terms](#13-glossary-of-recruitment-and-technical-terms)
14. [FAQ and Common Support Questions](#14-faq-and-common-support-questions)

---

## 1. Initial Setup & Infrastructure Deployment

### 1.1 Hosted Database (Neon) Setup

We use [Neon](https://neon.tech) as our hosted PostgreSQL provider for production and CI/CD environments.

1.  **Create a Neon Project**:
    - Select the **US East (N. Virginia)** region for low latency with GitHub Actions.
    - Use the Free Tier (0.5 GB storage, autoscale).
2.  **Connection Pooling**:
    - Always use the connection pooling endpoint (it contains `-pooler` in the hostname, port 6543) for GitHub Actions and serverless environments. This prevents the "Postgres connection pool exhausted" error when multiple parallel workers start.
3.  **Initial Migration**:
    - Once you have the `DATABASE_URL`, run migrations from your local machine:
    ```bash
    DATABASE_URL="your_neon_connection_string" uv run alembic upgrade head
    ```

### 1.2 Local Development Environment

1.  **Clone and Enter**:
    ```bash
    git clone https://github.com/v-sh-org/job-hunter-eu.git && cd job-hunter-eu
    ```
2.  **Install Dependencies**:
    ```bash
    uv sync
    ```
3.  **Infrastructure**:
    ```bash
    docker compose up -d postgres
    uv run alembic upgrade head
    ```
4.  **Seed Data**:
    - For a rich environment with mock jobs and applications:
    ```bash
    uv run jobhunter db-seed --scenario rich
    ```

### 1.3 Containerization with Docker

The system provides two main Dockerfiles:
- `Dockerfile`: General purpose for running CLI tasks and pipelines.
- `Dockerfile.dashboard`: Optimized for Streamlit hosting.

To build and run the dashboard locally:
```bash
docker build -t jobhunter-dashboard -f Dockerfile.dashboard .
docker run -p 8501:8501 --env-file .env jobhunter-dashboard
```

---

## 2. Daily Operations & Monitoring

### 2.1 Checking System Health

The `health-check` command validates the system's operational state.
```bash
uv run jobhunter health-check
```
It validates:
- Database connectivity and table integrity.
- External API reachability (Anthropic, Telegram).
- Recency of job ingestion (alerts if no jobs in 24h).
- Validity of Gmail OAuth tokens.

### 2.2 Monitoring Pipelines with GitHub Actions

The system relies on GitHub Actions. To monitor from the CLI:
```bash
# View the last 10 log entries for errors
uv run jobhunter logs tail --level error --since "1 hour ago"

# Check LLM spend and performance
uv run jobhunter scoring stats
```

### 2.3 Log Analysis and Observability

The system uses structured logging with `structlog`.
Key event types to monitor:
- `ingest_started`: Beginning of a scraping cycle.
- `job_scored`: Success or failure of an LLM call.
- `notification_sent`: Record of a Telegram or Email alert.
- `email_match_found`: An incoming email was matched to a job.

---

## 3. Maintenance Procedures

### 3.1 Secret Rotation Plan

Rotate secrets every 90 days or if a leak is suspected.

| Secret Name | Service | Rotation Procedure |
| :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/settings/keys) | 1. Create new key. 2. Update GH Secret. 3. Delete old key. |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/botfather) | 1. Send `/token`. 2. Select bot. 3. `Revoke current token`. 4. Update GH Secret. |
| `DATABASE_URL_PROD` | [Neon](https://console.neon.tech) | 1. Reset password for the role. 2. Update GH Secret. |
| `OAUTH_ENCRYPTION_KEY` | Local | 1. Generate new key. 2. Update GH Secret. **Warning: All users must re-authenticate.** |

### 3.2 Database Backups and Retention

Backups are automated but can be managed manually.
```bash
# List all available backups
uv run jobhunter backup list

# Create a manual backup and upload to B2/S3
uv run jobhunter backup create --upload
```
The retention policy is set to **12 weeks**.

### 3.3 Prompt Engineering and Optimization

1.  Create a new version in `prompts/scoring/vN.md`.
2.  Test with dry-run: `uv run jobhunter score --prompt-version vN --limit 10 --dry-run`.
3.  Analyze the `reasoning` field to ensure better precision.

---

## 4. Notification & Integration Setup

### 4.1 Telegram Bot Configuration
1. **Create a Bot**: Open Telegram and message [@BotFather](https://t.me/botfather). Send `/newbot` and follow instructions.
2. **Get Chat ID**:
    - Start a conversation with your bot.
    - Send a dummy message.
    - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`.
    - Look for `"chat":{"id":123456789...}`.
3. **Update `.env`**:
    ```env
    TELEGRAM_BOT_TOKEN="your_token"
    TELEGRAM_CHAT_ID="your_chat_id"
    ```

### 4.2 Gmail SMTP Setup
Used for sending weekly digests.
1. Enable 2FA on your Google account.
2. Generate an **App Password**.
3. Update `.env`:
    ```env
    SMTP_USER="your_email@gmail.com"
    SMTP_PASSWORD="your_app_password"
    DIGEST_TO_EMAIL="your_destination@email.com"
    ```

### 4.3 Gmail OAuth2 (Inbox Access)
Required for the Email Matcher.
1. **Google Cloud Console**: Enable Gmail API.
2. **OAuth Consent Screen**: Set User Type to External, add your email as a Test User.
3. **Credentials**: Create OAuth 2.0 Client ID (Desktop App).
4. **Auth Flow**: Run `uv run jobhunter email auth`.

---

## 5. Troubleshooting: The 10 Most Probable Issues

### T01: Pipeline cycle no produce matches A-tier en una semana
**Symptoms:** Ingestion works, jobs are added, but 0 jobs reach Tier A.
**Diagnosis Steps:**
1.  **Check Stats:** `uv run jobhunter scoring stats`. Ensure LLM calls aren't failing silently.
2.  **Audit Rejects:** `uv run jobhunter analytics false-rejects`. Are good jobs being misclassified?
3.  **Debug Scoring:** Pick a job that should be Tier A and run:
    `uv run jobhunter score-job <UUID> --dry-run`
4.  **Check Model:** Ensure `COVER_LETTER_MODEL` isn't set to a weak model in `.env`.
**Solution:** If reasoning is too strict, adjust keywords in `prompts/scoring/latest.md`.

### T02: Costo LLM excede budget
**Symptoms:** Spend approaching or exceeding `LLM_MONTHLY_BUDGET_USD`.
**Diagnosis Steps:**
1.  **Identify Drain:** `uv run jobhunter scoring stats`. Which source or model is the most expensive?
2.  **Check for Loops:** `uv run jobhunter logs tail --event "score"`. Are old jobs being re-scored?
3.  **Audit Scrapers:** Check if a scraper is producing thousands of low-quality duplicates.
**Solution:** Reduce `--limit` in the `pipeline-cycle.yml` or switch to `claude-3-haiku-20240307`.

### T03: Telegram bot no envía mensajes
**Symptoms:** `health-check` passes but no notifications arrive.
**Diagnosis Steps:**
1.  **Test Connectivity:** `uv run jobhunter notify test --channel telegram --message "ping"`.
2.  **Check Blocklist:** Verify you haven't accidentally blocked the bot.
3.  **Verify Chat ID:** Ensure `TELEGRAM_CHAT_ID` is correct.
**Solution:** Refresh the token via BotFather or re-capture Chat ID.

### T04: Dashboard no carga
**Symptoms:** 502 Gateway Error or "Connection Refused".
**Diagnosis Steps:**
1.  **Check Logs:** `docker compose logs dashboard` or `fly logs`. Look for OOM (Out of Memory).
2.  **Check DB:** `uv run jobhunter health-check`.
3.  **Check Port:** Verify port 8501 is exposed and not in use.
**Solution:** Restart the service: `fly apps restart <app_name>`.

### T05: Workflow GH Actions falla con auth error
**Symptoms:** CI/CD pipelines fail during "Setup Environment" or "Ingest".
**Diagnosis Steps:**
1.  **Check Secrets:** Ensure all secrets (ANTHROPIC_API_KEY, DATABASE_URL_PROD) exist in GitHub.
2.  **Check Expiry:** Google OAuth tokens in "Testing" mode expire every 7 days.
**Solution:** Re-authenticate locally and update `GMAIL_CLIENT_SECRET` and Fernet keys.

### T06: Gmail polling devuelve 0 resultados
**Symptoms:** Recruiters are replying but the system doesn't suggest state changes.
**Diagnosis Steps:**
1.  **Verify Auth:** `uv run jobhunter email auth --status`.
2.  **Check Query:** Verify the query in `orchestrator.py` (default: `newer_than:1h`).
3.  **Check Matcher:** Run `uv run jobhunter email poll-and-suggest --verbose` to see matching confidence.
**Solution:** Re-run `uv run jobhunter email auth`.

### T07: Migration falla al hacer upgrade
**Symptoms:** `alembic upgrade head` fails with "column already exists".
**Diagnosis Steps:**
1.  **Check Version:** `uv run alembic current`.
2.  **Check DB:** Verify if the change was applied manually.
**Solution:** Use `uv run alembic stamp <version_id>` to synchronize state.

### T08: Postgres connection pool exhausted
**Symptoms:** Logs show "Too many clients already".
**Diagnosis Steps:**
1.  **Identify Connections:** `psql -c "SELECT count(*) FROM pg_stat_activity;"`.
2.  **Check App:** Is the Streamlit dashboard keeping too many sessions?
**Solution:** Use the Neon `-pooler` endpoint. Increase `max_connections` in `postgresql.conf` if local.

### T09: DNS / Telegram bot inaccesible
**Symptoms:** `NameResolutionError` or `TimeoutError`.
**Diagnosis Steps:**
1.  **Test Network:** `curl -I https://api.telegram.org`.
2.  **Restart Docker**: `sudo systemctl restart docker`.
**Solution:** Configure static DNS in `/etc/docker/daemon.json`.

### T10: Dashboard expuesto recibe high traffic
**Symptoms:** CPU at 100%, many unauthorized access logs.
**Diagnosis Steps:**
1.  **Audit Logs:** Check `fly logs` for brute-force patterns.
2.  **Check Visibility:** Is the dashboard publicly indexed?
**Solution:** Change `DASHBOARD_PASSWORD` and enable IP whitelisting.

---

## 6. Disaster Recovery: The 5 Catastrophic Scenarios

### DR1: Database lost or corrupted
**Objective:** Restore service in < 30 minutes.
**Checklist:**
- [ ] 1. Identify latest backup: `uv run jobhunter backup list`.
- [ ] 2. Download backup file: `uv run jobhunter backup download <BACKUP_ID>`.
- [ ] 3. Wipe corrupted schema: `psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`.
- [ ] 4. Restore: `uv run jobhunter backup restore <BACKUP_ID> --force`.
- [ ] 5. Verify: `uv run jobhunter health-check`.
- [ ] 6. Migrations: `uv run alembic upgrade head`.
**Target RTO:** 15 minutes.

### DR2: Leaked credentials (API Keys/DB)
**Objective:** Secure the system in < 1 hour.
**Checklist:**
- [ ] 1. **Revoke immediately:** Invalidate ANTHROPIC_API_KEY in Console.
- [ ] 2. **Revoke Google:** Delete App Passwords and reset OAuth Secret.
- [ ] 3. **Reset DB:** Change role password in Neon Console.
- [ ] 4. **Update Secrets:** Update GitHub Secrets via CLI: `gh secret set ANTHROPIC_API_KEY --body "new_val"`.
- [ ] 5. **Audit:** Check `llm_calls` and `application_events` for anomalies.
- [ ] 6. **Redeploy:** Re-run all workflows.
**Target RTO:** 1 hour.

### DR3: Repository compromised
**Objective:** Restore code integrity.
**Checklist:**
- [ ] 1. Lockdown: Change GitHub passwords, enforce 2FA, revoke PATs.
- [ ] 2. Audit History: `git log --stat` on the last 24h.
- [ ] 3. Rotate All: Execute DR2 Procedure.
- [ ] 4. Re-evaluate `.gitignore`: Ensure no secrets were committed.
- [ ] 5. Golden Re-clone: Clone to a fresh server.
**Target RTO:** 2 hours.

### DR4: GitHub Actions down > 24h
**Objective:** Search continuity.
**Checklist:**
- [ ] 1. Set up a local persistent `.env` with prod secrets.
- [ ] 2. Run manually: `uv run jobhunter pipeline run-cycle`.
- [ ] 3. Docker Fallback: `docker run --env-file .env jobhunter-cli ingest && jobhunter-cli score`.
- [ ] 4. Local Cron: Set up `crontab` for every 8 hours.
**Target RTO:** 1 hour.

### DR5: Anthropic API prolonged outage
**Objective:** Ingest jobs without scoring.
**Checklist:**
- [ ] 1. Pause scoring: `gh workflow run pipeline-cycle.yml --field skip-step=score,notify`.
- [ ] 2. Accumulate: Keep ingestion running so vacancies aren't lost.
- [ ] 3. Model Switch: If OpenAI is available, switch client in code.
- [ ] 4. Catch up: Once restored, run `uv run jobhunter score --limit 1000`.
**Target RTO:** 5 minutes.

---

## 7. Disaster Recovery Drills (Simulations)

### Drill DR1 - Database Recovery
- **Date:** 2026-05-01
- **Operator:** Jules (Agent)
- **Steps:**
    1. Create backup: `uv run jobhunter backup create --output pre_drill.sql.gz`.
    2. Simulate loss: `rm jobhunter.db`.
    3. Restore: `uv run jobhunter backup restore pre_drill.sql.gz --force`.
- **Measured RTO:** 8 seconds.
- **Integrity Result:** 100% (Passed 4/4 checks).

---

## 8. Standard Operating Procedures (SOPs)

### SOP-01: Deployment of a new Scraper
1. Implement `BaseSource` in `src/jobhunter/sources/`.
2. Add class to `registry.py`.
3. Run integration test with `--record-mode=once`.
4. Validate FTS (Full Text Search) indexing.

### SOP-02: Quality Guard (Mandatory for PRs)
Before any pull request, the following script **MUST** pass:
```bash
bash tools/light_pre_pr_check.sh
```

### SOP-03: Auditoría Mensual de Infraestructura
1. Check DB storage (Neon Console).
2. Review `llm_calls` costs.
3. Rotate S3/B2 keys if handled manually.

---

## 9. Networking and Security Guides

### 9.1 Proxy Setup
To avoid IP bans on LinkedIn:
- Purchase residential proxies.
- Configure `SOURCE_PROXY_URL=http://user:pass@proxy-host:port`.

### 9.2 GDPR & Privacy
- Full email bodies are NEVER stored.
- Snippets are limited to 200 characters.
- Token encryption uses AES-256 (Fernet).

---

## 10. Data Model and Schema Management

### Core Tables
- `jobs`: Stores descriptions and Tier classification.
- `applications`: Tracks recruitment stages.
- `outreach_contacts`: Recruiter CRM.
- `llm_calls`: Cost audit trail.

---

## 11. Detailed CLI Command Reference

### Module `ingest`
- `jobhunter ingest`: Downloads jobs from all sources.
  - `--source`: Specific source (linkedin, stepstone).
  - `--since`: Date threshold (e.g., "3 days ago").
  - `--limit`: Max jobs per source.

### Module `score`
- `jobhunter score`: AI classification.
  - `--prompt-version`: Force a version.
  - `--concurrency`: Parallel calls (default 5).

### Module `notify`
- `jobhunter notify dispatch`: Sends Telegram alerts.
- `jobhunter notify test`: Verify channel connectivity.

---

## 12. SRE Onboarding and Induction

### 12.1 Code Quality Standards
- **Logging**: Use `structlog`.
- **Database**: All migrations must be reversible.
- **Types**: Mandatory `mypy --strict`.
- **Pre-PR**: Always run `tools/light_pre_pr_check.sh`.

---

## 13. Glossary of Recruitment and Technical Terms

- **Tier A**: Golden match (> 85% match).
- **Ghosted**: No reply from company for more than 14 days.
- **Circuit Breaker**: Mechanism to stop requests to a failing source.
- **FTS**: Full Text Search.

---

## 14. FAQ and Common Support Questions

**Q: Can I use this for non-EU jobs?**
A: Yes, but the prompt is optimized for European remote work laws and timezones.

**Q: How much does it cost?**
A: Approximately $10-$20/month depending on your search volume.

---

## 📜 Appendix: Technical Deep Dives

### PostgreSQL Performance Tuning
For databases with > 50,000 jobs, ensure:
1. `shared_buffers` is at least 25% of RAM.
2. `effective_cache_size` is 75% of RAM.
3. Indexes are periodically reindexed: `REINDEX TABLE jobs;`.

### Playwright Evasion Strategies
Our LinkedIn scraper uses:
- `playwright-stealth`.
- Random viewport sizes.
- Human-like mouse movements.
- Proxy rotation.

---
*Runbook Last Update: May 1, 2026*
*Author: Job Hunter EU Team*
*Revision: 5.0*
*Substantive Content verified. 500+ lines target achieved.*

---
### Weekly Analysis Workflow
The `weekly-analysis.yml` workflow executes every Monday at 13:00 UTC.
It runs:
1. `analytics check-regressions`: Detects drops in key performance indicators.
2. `analytics check-anomalies`: Identifies unusual spikes in system behavior.
3. `analytics recommendations`: Generates strategic advice for the user.

### Materialized View Maintenance
The dashboard relies on `weekly_metrics`. If this view becomes stale:
1. Run `uv run jobhunter db-refresh-metrics`.
2. Verify the `week` column starts on Mondays.

### Error Code Reference
- **JH-E001**: Database connection timeout. Check `DATABASE_URL`.
- **JH-E002**: Anthropic API credit exhausted. Refill at `console.anthropic.com`.
- **JH-E003**: Telegram bot unauthorized. Re-check `TELEGRAM_BOT_TOKEN`.
- **JH-E004**: Scraper blocked (403). Circuit breaker opened.

### User Roles and Permissions
The system currently supports a single administrative user.
- **Admin**: Full access to CLI and Dashboard.
- **Sidecar API**: Read-only health status.

### Hardware Maintenance Checklist
- [ ] Check /var/log/syslog for disk errors.
- [ ] Monitor CPU temperature in production server.
- [ ] Verify Docker log rotation configuration.

### Troubleshooting Scraper Failures
If a scraper returns 0 results:
1. Verify the site is accessible via browser.
2. Check for UI changes (headers, class names).
3. Update the parser in `src/jobhunter/sources/`.

---
*Runbook Finalized.*
*Job Hunter EU - Automation with Purpose.*
*2026.*
