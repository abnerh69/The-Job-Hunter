# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Job Hunter EU — Python 3.12 system that scrapes EU job boards, LLM-scores listings (Anthropic), tracks applications, and surfaces them via a Streamlit dashboard, a Typer CLI, and a FastAPI sidecar. Backed by PostgreSQL + Alembic.

## Toolchain

- Dependency / venv manager: `uv` (NOT pip). Always use `uv run <cmd>` so the project venv and `PYTHONPATH=src` resolve correctly.
- Build backend: `uv_build` (see `pyproject.toml`). `requirements.txt` is intentionally empty — dependencies live in `pyproject.toml` / `uv.lock`.
- Python is pinned via `.python-version` (3.12).

## Common commands

Setup (once):
```bash
cp .env.example .env          # then fill in ANTHROPIC_API_KEY + DASHBOARD_PASSWORD (required)
docker compose up -d          # starts Postgres on :5432
uv sync --all-groups          # installs runtime + dev deps
uv run alembic upgrade head   # apply migrations
uv run pre-commit install
```

Quality gates (must all pass — mypy is `strict`):
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest                              # full suite
uv run pytest --ignore=tests/e2e           # what CI runs
uv run pytest tests/unit/scoring -v        # one directory
uv run pytest tests/unit/scoring/test_scorer.py::test_name   # one test
uv run pytest -m integration               # only integration
```

E2E (Streamlit + Playwright) tests need browsers installed:
```bash
uv run playwright install chromium
uv run pytest tests/e2e
```
`run_tests_with_env.py` is a convenience wrapper that injects dummy `ANTHROPIC_API_KEY` / `DASHBOARD_PASSWORD` and runs the full suite with coverage — useful when a shell `.env` isn't loaded.

DB migrations:
```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "msg"
```
`alembic.ini` sets `prepend_sys_path = ./src`, so models import as `jobhunter.db.models` from migration scripts.

Run the app:
```bash
uv run python -m jobhunter --help                      # Typer CLI root
uv run python -m jobhunter pipeline run-cycle          # ingest → score → dispatch
uv run python -m jobhunter dashboard                   # launches Streamlit
uv run streamlit run src/jobhunter/dashboard/streamlit_app.py   # direct
uv run python -m jobhunter api run                     # FastAPI sidecar
```

Two Docker images: `Dockerfile` runs the CLI (`python -m jobhunter`); `Dockerfile.dashboard` runs the Streamlit UI on :8080 and additionally bundles `prompts/` and `cv_variants/`.

## Architecture

The package is `src/jobhunter/` (src layout — `PYTHONPATH=src` is required for tests/CI). Modules are organized by domain, not by layer:

- `sources/` — async scrapers (`arbeitnow`, `remoteok`, `wwr`, `fourdayweek`). New sources subclass `BaseSource` (yields `RawJob`) and self-register via the `@register_source` decorator in `sources/registry.py`. `orchestrator.run_ingestion()` iterates the registry and writes through `db/repos/job.py`. Resilience helpers live in `circuit_breaker.py` and `http.py`.
- `scoring/` — LLM-driven tiering. `scorer.JobScorer` builds prompts from `prompts/scoring/`, calls the LLM client, and validates against `schema.py`. Batch entry points are `scoring.pipeline.score_pending_jobs` and `rescore_jobs`.
- `llm/` — `AnthropicLLMClient` wraps the Anthropic SDK. Every call is recorded via `db/repos/llm_calls.py` with model, purpose (`LLMPurpose` enum), tokens, and `cost_usd` from `llm.pricing`. **All LLM calls flow through this client** so cost telemetry and the `LLM_MONTHLY_BUDGET_USD` cap stay accurate. Tests substitute `MockLLMClient` (defined in `tests/conftest.py`), which also records calls when given a session.
- `application/` — post-match user-facing flows: `assistant.assist_application`, `cover_letter`, `cv_tweaks`, `ats_keywords`, `variant_selector`. CV variants are loaded from `CV_VARIANTS_DIR`.
- `outreach/` — proactive contact cadence and message tracking against `OutreachContact` / `OutreachMessage`.
- `notify/` — pluggable notifier registry (`__init__.get_notifier_cls`, `get_all_notifiers`) for Telegram + email. `dispatcher.dispatch_tier_a_notifications` is the production fan-out; `digest.py` produces the weekly summary; `health_check.py` raises source-health alerts.
- `email/` — Gmail OAuth (`auth`) + inbox poller that correlates recruiter replies to applications. OAuth tokens are encrypted via `crypto.py` using `OAUTH_ENCRYPTION_KEY`.
- `analytics/` — regression detection, anomaly scans, false-reject / missed-opportunity reports backing the `analytics ...` CLI subcommands.
- `db/` — SQLAlchemy 2.0 declarative models in `models.py`, repos under `db/repos/`, Alembic migrations in `alembic/versions/`. A `weekly_metrics` PostgreSQL materialized view is created/refreshed by `db/maintenance.refresh_weekly_metrics`; `tests/conftest.py` recreates it for the test session.
- `dashboard/` — Streamlit multi-page app (`streamlit_app.py` + numbered files in `pages/`). Auth is enforced by `auth.require_auth` against `DASHBOARD_PASSWORD`.
- `api/` — small FastAPI sidecar (`api/main.py`).
- `pipeline.py` — top-level orchestrator (`run_cycle`, `run_followup_checks`) used by the CLI and the GitHub Actions schedules.
- `config.py` — `Settings` (pydantic-settings) is the single config surface. `__main__.callback` validates it on every CLI invocation, so missing required vars fail fast. Use `safe_dict()` when logging.

CLI structure (`src/jobhunter/__main__.py`): one root Typer `app` plus sub-Typers (`sources`, `scoring`, `notify`, `pipeline`, `outreach`, `analytics`, `ab-test`, `telegram`, `email`, `logs`, `api`, `backup`). When adding a command, attach it to the matching sub-Typer and keep the orchestration thin — push logic into the corresponding domain module.

## Conventions

- Prefer editing existing modules; the domain split above is load-bearing.
- New job sources: implement `BaseSource`, decorate with `@register_source`, then it's automatically picked up by `get_all_sources()` / the orchestrator. No central wiring file.
- Anything that calls Anthropic should go through `AnthropicLLMClient.complete(..., purpose=LLMPurpose.X, session=...)` so the call is logged and costed.
- Conventional Commits are required (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, …); branches off `main` (`feature/*`, `bugfix/*`, `hotfix/*`). See `CONTRIBUTING.md`.
- Pre-commit runs ruff (fix + format), `mypy --strict` with the bundled type-stub deps, and `detect-secrets` against `.secrets.baseline`. CI additionally runs `bandit -r src/ -ll` and `pip-audit`.
- Test markers: `integration`, `e2e` (registered in `pyproject.toml`); `asyncio_mode = "auto"`.
- Integration tests need a live Postgres (the docker-compose one is fine) — `tests/conftest.py` drops/creates the schema and the `weekly_metrics` materialized view per session.

## Reference docs in-repo

- `docs/ARCHITECTURE.md` — short module map (in Spanish).
- `docs/runbook.md` — long-form operations / DR runbook (Spanish).
- `docs/adr/ADR-00{1..5}-*.md` — architectural decisions (Streamlit, Postgres, GH Actions orchestration, centralized crypto, human-in-the-loop).
- `docs/data_model.md`, `docs/sources.md` — data model and source catalog.
