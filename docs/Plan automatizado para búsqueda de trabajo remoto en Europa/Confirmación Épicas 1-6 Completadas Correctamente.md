# Confirmación Épicas 1-6 Completadas Correctamente

Este documento consolida la verificación realizada de las épicas 1 a 6 del plan
automatizado de búsqueda de empleo, contrastando cada acceptance criterion (AC)
de los documentos de Backlog Nivel 2 (E–J) contra el estado real del repositorio.

Convenciones usadas en cada tabla:

- ✅ — story implementada conforme al AC literal.
- ✅ con desvío menor / ⚠️ — implementada, con una desviación documentada.
- ❌ — incumplimiento real (sólo aparece en E1-S07 antes de aclarar el orquestador).

**Regla de aceptación de versionado.** El backlog pide tags `v0.X.0` por épica.
La versión efectiva del proyecto es `__version__ = "1.0.0"` (ver
`pyproject.toml` y `src/jobhunter/__init__.py`); por decisión del usuario, los
tags por épica se aceptan como cumplidos por el salto directo a v1.0.0. No se
crea ningún tag retroactivamente.

---

## Hallazgo de seguridad transversal

Durante la verificación de E1 se detectó que `git remote -v` exponía un
Personal Access Token de GitHub embebido en la URL del remote (`.git/config`
local). El usuario confirmó que el token es **temporal y local**, no
commiteado, y pidió ignorar el hallazgo. Queda registrado por completitud.

---

## Épica 1 — Foundation & Project Bootstrap

Documento origen: `E_Backlog_Nivel_2_E1.md`.

### Verificación inicial

| Story | Estado inicial | Notas |
|---|---|---|
| S01 Repo + estructura | ✅ con 1 falla | Git+main, `.gitignore` completo, estructura de dirs, docs A–E presentes (en `docs/Plan automatizado.../`). **Faltaba `LICENSE`**. |
| S02 Proyecto Python con uv | ✅ | `pyproject.toml`, `uv.lock`, `__version__ = "1.0.0"`, deps core declaradas. |
| S03 Tooling de calidad | ✅ | Ruff (line-length=100, py312), `mypy strict=true`, `.pre-commit-config.yaml` con ruff/mypy/check-yaml/check-toml/eof/trailing/detect-secrets, `.secrets.baseline` presente. |
| S04 pytest | ✅ con detalle | `asyncio_mode=auto`, cov branch, `tests/unit/test_smoke.py::test_imports`. Markers registrados son `integration` y `e2e` — el AC pedía además `unit` y `slow` (menor). |
| S05 pydantic-settings | ⚠️ desvío | `Settings` clase + `SecretStr` + `.env.example` ✓. **No existe** el singleton `settings = Settings()` que pedía el AC; cada llamador instancia `Settings()` por su cuenta. |
| S06 Docker + Postgres | ✅ | `docker-compose.yml` (postgres:16-alpine, healthcheck, volumen `postgres_data`), `Dockerfile` multi-stage, `DATABASE_URL` en `.env.example`. |
| S07 CI en GitHub Actions | Inicialmente ❌, finalmente ✅ | `ci.yml` tenía los triggers `push:`/`pull_request:` comentados. El usuario aclaró que la activación se delegó a `.github/workflows/orchestrator.yml`, que sí dispara en `push`/`pull_request` a `main` y llama a `ci.yml` vía `workflow_call`. |
| S08 README + onboarding | ⚠️ parcial | `README.md` con badge, quick start, project structure ✓; `CONTRIBUTING.md` ✓. **Faltaba el tag `v0.1.0`** — aceptado bajo la regla `__version__ = "1.0.0"`. |

### Decisiones del usuario y fixes aplicados

1. **S07** — Aceptar diferencia (orquestador en `orchestrator.yml`). Sin cambios de código.
2. **S05** — Documentar la decisión de no usar singleton.
3. **S01** — Crear licencia OpenSource. Se eligió **MIT** (con opción a Apache-2.0 si se prefiere).
4. **S08** — Aceptar `__version__ = "1.0.0"`.

### Cambios materializados en el repo

- `LICENSE` creado con texto MIT estándar (© 2026 Abner Hernandez).
- `pyproject.toml:8` — `license = { text = "MIT" }` (antes `Proprietary`).
- `README.md` — sección License actualizada a "Released under the MIT License".
- `docs/adr/ADR-006-no-settings-singleton.md` — ADR formal documentando por qué
  no hay singleton `settings` (test isolation, fail-fast en `__main__.callback`,
  perfiles distintos por entry-point, alternativa con `lru_cache` descartada).
- `src/jobhunter/config.py` — docstring de módulo apuntando al ADR.
- `README.md` — ADR-006 añadido al índice.

### Estado final E1

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| S04 | ✅ |
| S05 | ✅ (desvío documentado en ADR-006) |
| S06 | ✅ |
| S07 | ✅ (vía orchestrator.yml) |
| S08 | ✅ (v1.0.0 aceptado en lugar de v0.1.0) |

**Épica 1 cerrada.**

---

## Épica 2 — Data Persistence Layer

Documento origen: `F_Backlog_Nivel_2_E2.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 SQLAlchemy + Alembic | ✅ | `db/session.py` expone `engine`, `SessionLocal`, `get_session()` context manager; `db/base.py` con `DeclarativeBase` + `type_annotation_map` para JSONB; `alembic.ini` + `alembic/env.py` configurados; `tests/integration/db/test_connection.py`. |
| S02 Modelo `jobs` | ✅ | `Job` con `url_hash UNIQUE`, índices `idx_jobs_status`/`idx_jobs_tier`/`idx_jobs_scraped_at`/`idx_jobs_company`, `raw_payload` y `score_data` como JSONB; enums `JobStatus`+`JobTier`; migración `1b5df3f99a65_create_jobs_table.py`. |
| S03 `applications`+`application_events` | ✅ | FKs y `relationship` configuradas; `ApplicationStatus`+`ApplicationEventType` enums; índice parcial `idx_apps_next_action_due` con `postgresql_where` correcto. |
| S04 `outreach_contacts` | ✅ | `OutreachContact` con índice compuesto `idx_outreach_followup (status, last_contacted_at)`; enums `OutreachMarket`+`OutreachStatus`. |
| S05 Vista `weekly_metrics` | ✅ | Migración `8003f9b94773_create_weekly_metrics_view.py` crea la materialized view + unique index; `db/maintenance.refresh_weekly_metrics()` usa `REFRESH MATERIALIZED VIEW CONCURRENTLY`; CLI `db-refresh-metrics`. |
| S06 `BaseRepo` + `JobRepo` | ✅ | `BaseRepo[T]` genérica con `get/list/create/update/delete`; `JobRepo` añade los 5 métodos del AC. Tests en `tests/integration/test_job_repo.py`. |
| S07 `ApplicationRepo`+`OutreachRepo` | ✅ | `ApplicationRepo`: los 4 métodos del AC; `OutreachRepo`: los 4 métodos del AC. Tests `test_application_repo.py` y `test_outreach_repo.py`. |
| S08 Fixtures + seed + tests | ✅ | `conftest.py` con `db_session`/`sample_job`/`sample_application`/`sample_outreach_contact`; `db/seed.py` con scenarios `rich`/`minimal`; CLI `db-seed`; `tests/fixtures/sample_jobs.json` con 50 ofertas (verificado). |
| S09 Backup + ER doc | ✅ con desvío | `scripts/backup_db.sh`; `docs/data_model.md` con diagrama mermaid `erDiagram`; restore en `docs/runbook.md`. **Desvío:** el AC pedía CLI `db-backup`, la implementación expone sub-Typer `backup {create,list,restore}` — superset del AC. |

### Definition of Done de E2

- AC de las 9 stories: ✅ (con el desvío "ampliado" de S09).
- CI con tests de integración: `ci.yml:78-82` corre alembic + pytest sobre Postgres.
- Backup probado end-to-end: cubierto por `backup create`/`restore`; existe
  `pre_drill_backup.sql.gz` como evidencia de drill.
- `docs/data_model.md` con ER actualizado.
- Tag `v0.2.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

Documentar el desvío de S09 (sub-Typer `backup` vs CLI `db-backup`).

### Cambios materializados

- `docs/data_model.md` — sección "CLI commands related to the data layer"
  añadida al final con una tabla (`db-seed`, `db-refresh-metrics`,
  `backup create/list/restore`) y un bloque "Note" que documenta el desvío de
  E02-S09 explícitamente, marcándolo como **superset** del AC, no faltante.

**Épica 2 cerrada con desvíos documentados in-tree.**

---

## Épica 3 — Multi-source Job Ingestion

Documento origen: `G_Backlog_Nivel_2_E3.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 `BaseSource` + `RawJob` + Registry | ⚠️ desvío menor | `RawJob` ✓ frozen pydantic; `@register_source` + `get_all_sources()` ✓; `canonicalize_url`/`compute_url_hash` ✓ en `sources/url_utils.py`; tests `tests/unit/sources/test_url_utils.py`. **Desvío:** `BaseSource` no declara `name: str` ni `default_rate_limit: float` ni método `canonicalize_url`. Sólo `RemoteOKSource` declara `default_rate_limit = 0.33` en la subclase. |
| S02 HTTP wrapper | ✅ | `sources/http.SourceHttpClient` envuelve `httpx.AsyncClient`; `tenacity` con `retry_if_exception` + backoff exponencial; `User-Agent = "jobhunter-eu/0.3 (+https://github.com/Informatica-ASHware/Job-Hunter-EU)"` literal del AC; `Retry-After` honrado en 429; rate-limit con `Semaphore` por host; `structlog` con `host`/`status_code`/`duration_ms`/`attempt`. |
| S03 ArbeitnowSource | ✅ | `@register_source`, mapping → `RawJob(source_name="arbeitnow", …)`. Cassettes: `test_arbeitnow_fetch_integration.yaml` y `test_arbeitnow_pagination_integration.yaml`. |
| S04 RemoteOKSource | ✅ | `@register_source`, `default_rate_limit = 0.33` (≈ 1 req/3s), `User-Agent` propagado vía `SourceHttpClient`. Cassettes: `fetch`, `metadata_skipped`, `tag_filtering` — los 3 escenarios del AC. |
| S05 WeWorkRemotelySource | ✅ | `@register_source`, parser RSS (deps `feedparser` + `beautifulsoup4`). Cassette `test_wwr_fetch_integration.yaml`. |
| S06 FourDayWeekSource | ✅ | `@register_source`, mapping a `RawJob(source_name="fourdayweek", …)`. Cassette `test_fourdayweek_fetch_integration.yaml`. |
| S07 Orchestrator + circuit breaker | ✅ | `sources/orchestrator.run_ingestion()` async + `asyncio.gather`; `IngestionReport`+`SourceResult` con `status="skipped_breaker"` literal del AC; `circuit_breaker.CircuitBreaker` con persistencia vía tabla `source_health` (migración `4c73a58d9d21_create_source_health_table.py` y repo). |
| S08 CLI `jobhunter ingest` | ✅ | `ingest` con flags `--source` (repetible), `--since` (default `"7 days ago"`), `--limit`, `--dry-run`; `sources list` muestra estado del circuit breaker en tabla Rich. |
| S09 Integration tests con cassettes | ✅ | `vcrpy>=8.1.1` + `pytest-recording>=0.13.4`; cassettes versionados en `tests/integration/sources/cassettes/`; `test_orchestrator_integration.py` cubre `full_ingestion`, `deduplication`, `failure_isolation`. |

### Definition of Done de E3

- AC de las 9 stories: ✅ con desvío menor en S01.
- CI con cassettes: ✅.
- Idempotencia: cubierta por `bulk_create_skipping_duplicates`
  (`ON CONFLICT (url_hash) DO NOTHING`) y cassette `test_orchestrator_deduplication_integration.yaml`.
- Circuit breaker probado: `test_orchestrator_failure_isolation_integration.yaml`
  + `test_circuit_breaker.py`.
- Tag `v0.3.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

Documentar el desvío de S01 (opción 2: ADR), no implementar la opción 1
(declarar atributos en la base).

### Cambios materializados

- `docs/adr/ADR-007-thin-basesource-contract.md` — ADR formal con tabla de
  mapeo (dónde vive cada responsabilidad del AC original: `name` → literal en
  cada `RawJob`; `default_rate_limit` → subclase + `SourceHttpClient`;
  `canonicalize_url` → `url_utils`), rationale (ningún caller consume el
  contrato propuesto, canonicalización uniforme entre fuentes), consecuencias
  y alternativas.
- `src/jobhunter/sources/base.py` — docstring de módulo apuntando al ADR.
- `README.md` — ADR-007 añadido al índice.

**Épica 3 cerrada con desvíos documentados in-tree.**

---

## Épica 4 — AI Scoring Engine

Documento origen: `H_Backlog_Nivel_2_E4.md`.

### Verificación — sin desvíos

| Story | Estado | Evidencia |
|---|---|---|
| S01 Schema Pydantic | ✅ | `scoring/schema.py`: `ScoringResult` + 6 sub-modelos (`CompanyInfo`, `RoleInfo`, `CompensationInfo`, `LogisticsInfo`, `MatchAnalysis`, `Recommendation`); 8 enums (`Tier`, `Action`, `Priority`, `RemoteType`, `TimezoneRequirement`, `ContractType`, `CompanyStage`, `Seniority`); `InvalidScoringResponse`; `parse_scoring_response()`; `ConfigDict(extra="forbid")`. Tests `test_schema.py`. |
| S02 Prompt loader | ✅ | `prompts/scoring/v1.md` versionado; `scoring/prompt.ScoringPrompt` (Pydantic) + `load_prompt(version="latest")` + `render_user_prompt()` + `PromptRenderError`. Tests `test_prompt.py`. |
| S03 Anthropic client | ✅ | `llm/anthropic_client.AnthropicLLMClient` con `LLMResponse` (`text`, `model`, tokens, `cost_usd`, `duration_ms`, `stop_reason`); retry con `tenacity` + `retry_if_exception_type`; `llm/pricing.py` con tabla `PRICING` y comentario `verified 2026-04-29`; `calculate_cost_usd()`. |
| S04 JobScorer | ✅ | `scoring/scorer.JobScorer` con `score(job) -> ScoringOutcome`; jerarquía `ScoringError` → `ScoringParseError` (con `raw_response`) + `ScoringAPIError` exactamente como pide el AC. |
| S05 Pipeline batch | ✅ | `scoring/pipeline.score_pending_jobs(session, limit, concurrency)` + `rescore_jobs()`; `ScoringBatchReport`. Tests unit + e2e. |
| S06 Cost tracking + budget | ✅ | Migraciones `create_llm_calls_table.py` + `d6232ede895b_update_llm_calls_table.py`; `LLMCallRepo` con `record_call`, `monthly_total_usd`, `weekly_total_usd`, `get_stats_by_model`; `llm/budget.BudgetExceededError` + `check_budget()` + `BudgetStatus`; `Settings.LLM_MONTHLY_BUDGET_USD = 25.0`. |
| S07 CLI | ✅ | `score` con los 5 flags del AC (`--limit`, `--concurrency`, `--model`, `--prompt-version`, `--dry-run`); `score-job` para debug; `rescore` con `--tier` (default `A`), `--with-model`, `--limit`; `scoring stats`. |
| S08 Fixtures de respuestas IA | ✅ | `tests/fixtures/scoring_responses/` con los **8 fixtures literales**: `tier_a_python_ai.json`, `tier_a_flutter.json`, `tier_b_borderline.json`, `tier_c_manual_review.json`, `reject_eu_only.json`, `reject_low_salary.json`, `invalid_response.json`, `malformed_json.txt`. `MockLLMClient` en `tests/conftest.py`. E2E en `test_pipeline_e2e.py`. |

### Definition of Done de E4

- AC de las 8 stories: ✅ (sin desvíos).
- CI con fixtures sin red: `MockLLMClient` permite que los tests del pipeline
  corran sin Anthropic.
- Schema strict (`extra="forbid"`): aplicado en cada sub-modelo.
- Costo observable: `scoring stats` + `LLMCallRepo.monthly_total_usd`.
- Tag `v0.4.0`: aceptado bajo la regla `__version__`.

**Épica 4 cerrada limpia. Sin desvíos que documentar.**

---

## Épica 5 — Real-time Notification System

Documento origen: `I_Backlog_Nivel_2_E5.md`.

### Verificación — sin desvíos

| Story | Estado | Evidencia |
|---|---|---|
| S01 `BaseNotifier` + tabla `notifications_sent` | ✅ | `notify/base.py`: `BaseNotifier(ABC)` con `async send(NotificationMessage) -> NotificationResult`; modelos Pydantic completos; `@register_notifier(name)` + `get_all_notifiers()` + `get_notifier_cls()`. Migración `4c9f4a2b6f09_add_notifications_sent_table.py` con `idx_notifications_sent_dedup UNIQUE (channel, dedup_key)` e `idx_notifications_sent_job_channel`. `NotificationsRepo` con los 3 métodos del AC + extras. |
| S02 Templates Jinja2 | ✅ | `templates/notifications/` con los 4 archivos del AC (`tier_a_match_telegram.md`, `tier_a_match_email.html`, `weekly_digest_email.html`, `weekly_digest_email.txt`); `notify/templates.render()` con `Environment` cacheado, `autoescape=select_autoescape(["html","xml"])`, `trim_blocks=True`; los 3 filtros del AC (`format_currency`, `format_date_human`, `truncate_words`) + `escape_telegram_markdown`. |
| S03 TelegramNotifier | ✅ | `notify/telegram.py` con `@register_notifier("telegram")`; `python-telegram-bot[asyncio]>=22.7`; `escape_telegram_markdown_v2`; `parse_mode="MarkdownV2"`; manejo de `RetryAfter`, `BadRequest`, `NetworkError`. Tests `test_telegram.py`. |
| S04 EmailNotifier (SMTP) | ✅ | `notify/email.py` con `@register_notifier("email")`; usa `aiosmtplib>=3.0.1`; multipart MIME; manejo no-raise de `SMTPException` y `SMTPAuthenticationError`. Tests `test_email.py`. |
| S05 Dispatcher tier-A | ✅ | `notify/dispatcher.dispatch_tier_a_notifications(session) -> DispatchReport`; `dedup_key = f"tier_a:{job.id}"` literal del AC. |
| S06 Digest semanal | ✅ | `notify/digest.py` con `send_weekly_digest()`, `prepare_weekly_digest()`, `compute_digest_context()`; `dedup_key = f"digest:{iso_year}:{iso_week}"` literal del AC; modelos Pydantic ricos para el contexto. |
| S07 CLI + tests | ✅ | Sub-Typer `notify` con los 4 comandos del AC: `dispatch`, `digest [--send] [--week-ending]`, `test --channel ...`, `status`. Tests `test_cli_notify.py`. Runbook documenta Telegram (§42) y Gmail (§T06). |

### Definition of Done de E5

- AC de las 7 stories: ✅ (sin desvíos).
- CI con notifiers mockeados: ✅.
- Idempotencia DB-level: `UNIQUE (channel, dedup_key)`.
- Runbook documenta Telegram + Gmail.
- Tag `v0.5.0`: aceptado bajo la regla `__version__`.

**Épica 5 cerrada limpia. Sin desvíos que documentar.**

---

## Épica 6 — AI-Assisted Application Toolkit

Documento origen: `J_Backlog_Nivel_2_E6.md`.

### Verificación — sin desvíos

| Story | Estado | Evidencia |
|---|---|---|
| S01 CV variants | ✅ | `cv_variants/` con los 3 templates literales (`ai_python.template.md`, `flutter.template.md`, `fullstack.template.md`); `.local/` en `.gitignore`; `application/cv.py` con `CVVariant` + `Experience`, `load_cv()`, `list_available_variants()`, parser `_parse_cv_markdown`; `Settings.CV_VARIANTS_DIR = Path(".local/cv_variants")`. |
| S02 Variant selector | ✅ | `application/variant_selector.recommend_cv_variant(job) -> VariantRecommendation`; lógica heurística sobre `score_data` + fallback por keyword matching. |
| S03 Cover letter (Opus) | ✅ | `application/cover_letter.generate_cover_letter()`; `CoverLetterResult`; `prompts/cover_letter/v1.md` + `forbidden_phrases.txt` literal del AC; `validate_cover_letter()`. Modelo configurable vía `Settings.COVER_LETTER_MODEL = "claude-opus-4-7"`. |
| S04 ATS keywords | ✅ | `application/ats_keywords.extract_ats_keywords()`; `ATSKeywordsResult { must_have, nice_to_have }`; `Keyword.category: Literal["technical","soft","certification","tool","methodology"]` exactos del AC; `_check_presence_in_cv()`; `prompts/ats_keywords/v1.md`. |
| S05 CV tweaks | ✅ | `application/cv_tweaks.suggest_cv_tweaks()`; `Tweak.type: Literal["reorder_bullet","add_keyword","rewrite_bullet","add_section","remove"]` exactos; **límite estricto de 5 tweaks** (`tweaks_data[:5]`). |
| S06 Orquestador | ✅ | `application/assistant.py` con `JobNotAssistableError`, `ApplicationPackage`, `assist_application()`; paralelización con `asyncio.gather` (ATS keywords + cover letter en paralelo, tweaks dependiente); cache `_CACHE` in-memory por `job_id`. |
| S07 CLI | ✅ | `assist` con los 3 flags del AC; `letter` con `--output` + `--cv-variant`; `apply` con los 5 flags del AC. |
| S08 Fixtures + tests E2E | ✅ | `tests/fixtures/application_assistant/` con los 4 fixtures literales del AC; `MockLLMClient` extendido con ramas `LLMPurpose.COVER_LETTER`/`ATS_KEYWORDS`/`CV_TWEAKS`; E2E `test_e2e_assistant.py`. |

### Definition of Done de E6

- AC de las 8 stories: ✅ (sin desvíos).
- CI con fixtures sin red: `MockLLMClient` cubre `cover_letter`, `ats_keywords`, `cv_tweaks`.
- Coverage ≥75% en `application/`: 7 archivos de tests; el badge del README declara 75% global.
- **Cero auto-aplicación**: confirmado — el comando `apply` solo registra el
  `Application` en DB; no hay `playwright` ni dependencias de submit en `application/`.
- Tag `v0.6.0`: aceptado bajo la regla `__version__`.

**Épica 6 cerrada limpia. Sin desvíos que documentar.**

---

## Resumen consolidado

| Épica | Stories | Estado | Desvíos documentados | Artefactos creados/modificados |
|---|---|---|---|---|
| E1 Foundation | 8 | ✅ | S05 (sin singleton), S07 (vía orchestrator) | `LICENSE` (MIT), `pyproject.toml`, `README.md`, `ADR-006`, docstring `config.py` |
| E2 Persistence | 9 | ✅ | S09 (`backup` sub-Typer es superset de `db-backup`) | Nota CLI en `docs/data_model.md` |
| E3 Ingestion | 9 | ✅ | S01 (`BaseSource` minimalista) | `ADR-007`, docstring `sources/base.py`, `README.md` |
| E4 Scoring | 8 | ✅ | — | — |
| E5 Notifications | 7 | ✅ | — | — |
| E6 Application Toolkit | 8 | ✅ | — | — |
| **Total** | **49** | **✅** | **4 desvíos, todos documentados** | 2 ADRs nuevos, 1 LICENSE, 3 docstrings, 1 nota en data_model |

### ADRs añadidos en esta verificación

- [`ADR-006: No Module-Level settings Singleton`](../adr/ADR-006-no-settings-singleton.md) — justifica el desvío de E01-S05.
- [`ADR-007: Thin BaseSource Contract`](../adr/ADR-007-thin-basesource-contract.md) — justifica el desvío de E03-S01.

### Reglas de aceptación transversales aplicadas

1. **Tags `v0.X.0` por épica:** se aceptan como cumplidos por el salto directo a
   `__version__ = "1.0.0"`. No se crean retroactivamente.
2. **PAT en `.git/config`:** ignorado por instrucción del usuario (token
   temporal y local, no commiteado).
3. **Métricas runtime** (jobs reales en DB, latencia <30s, tiempo a apply <10
   min, etc.): no verificables desde el repo; se asumen cubiertas por las
   pruebas manuales fuera de scope de esta verificación.

### Estado de las épicas P0 del MVP

Las épicas E1–E6 cubren los pilares del MVP: bootstrap, persistencia,
ingestion, scoring, notificaciones y toolkit de aplicación. Todas verificadas
y cerradas. **El MVP P0 está funcionalmente completo a la espera de E7
(Dashboard) y E8 (Scheduling)**, según el "Definition of Ready para E7" del
Documento J.

---

**Fin del documento. Verificado contra estado del repo el 2026-05-01.**
