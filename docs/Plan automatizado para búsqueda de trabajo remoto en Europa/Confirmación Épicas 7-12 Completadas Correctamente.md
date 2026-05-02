# Confirmación Épicas 7-12 Completadas Correctamente

Continuación del análisis iniciado en
`Confirmación Épicas 1-6 Completadas Correctamente.md`. Este documento
consolida la verificación de las épicas 7 a 12 contra los acceptance criteria
de los documentos K–P de Backlog Nivel 2.

Convenciones usadas en cada tabla (idénticas al documento previo):

- ✅ — story implementada conforme al AC literal.
- ✅ con desvío menor / ⚠️ — implementada, con una desviación documentada.
- ❌ — incumplimiento real.
- ➡️ — story movida a otra épica por decisión del usuario.

**Regla de aceptación de versionado** (heredada del documento previo). El
backlog pide tags `v0.X.0` por épica. La versión efectiva del proyecto es
`__version__ = "1.0.0"`; por decisión del usuario, los tags por épica se
aceptan como cumplidos por el salto directo a v1.0.0. No se crean
retroactivamente.

---

## Épica 7 — Dashboard & Application Tracker

Documento origen: `K_Backlog_Nivel_2_E7.md`.

### Verificación inicial

| Story | Estado | Evidencia |
|---|---|---|
| S01 Foundation Streamlit + auth + layout | ✅ | `dashboard/streamlit_app.py` con `st.set_page_config(layout="wide")`, login, layout. Las **5 páginas del AC** existen con la nomenclatura literal `1_📥_New_Matches.py` … `5_📊_Metrics.py` (más 3 extras: `6_🔎_Search.py`, `7_🛠_Assist.py`, `8_🏥_Status.py`). `dashboard/auth.py` con `require_auth()`, `check_password()` (compara contra `Settings.DASHBOARD_PASSWORD.get_secret_value()`), `logout()`. `dashboard/layout.py` con `render_header()`/`render_sidebar()`. `Settings.DASHBOARD_PASSWORD: SecretStr` + `DASHBOARD_SESSION_TIMEOUT_MINUTES: int = 60` literal del AC. Tema en `.streamlit/config.toml`. CLI `jobhunter dashboard`. |
| S02 New Matches | ✅ | `pages/1_📥_New_Matches.py` (241 líneas) usa `JobRepo.list_by_status` + `ApplicationRepo`; `dashboard/components.render_job_card`; integración con `ApplicationStatus`/`JobTier`. |
| S03 Pipeline kanban | ✅ | `pages/2_📋_Pipeline.py` (156 líneas) con `render_application_card` + `render_application_detail_modal`; usa `ApplicationRepo` y `ApplicationStatus`. |
| **S04 Manual Review** | ❌ inicialmente, **➡️ movida a E13-S01** | `pages/3_🔍_Manual_Review.py` tenía **12 líneas en total**: imports + `require_auth()` + `render_header()` + `render_sidebar()` + un `st.info("Placeholder: Implementation coming in next stories.")`. Ninguno de los AC se cumplía. Por decisión del usuario, la story se movió a la nueva **Épica 13: QA Humana** (story `E13-S01`) en lugar de implementarse en E7. |
| S05 Outreach | ✅ | `pages/4_💌_Outreach.py` (584 líneas) con `OutreachRepo` + `OutreachMessageRepo`; `@st.dialog` para "Añadir Nota", "Generar Mensaje", "Importar Contactos desde CSV"; botones `Mark Contacted`, `Mark Replied`, `Mark Warm`, `Add Note`; integración con `bulk_import_from_csv`; "Generate Message" ya activado vía `outreach.generator.generate_message` (se adelantó a E9). |
| S06 Metrics & Analytics | ✅ | `pages/5_📊_Metrics.py` (491 líneas); `dashboard/services/metrics.MetricsService` centraliza queries; deps `plotly>=6.7.0` + `weasyprint>=63.0` (este último para export PDF) declaradas. |
| S07 Búsqueda full-text + filtros globales | ✅ | Migración `f2fcceef4fa7_add_search_vectors.py` añade `search_vector tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', …), 'A'\|'B'\|'C'))` + índices GIN en `jobs`, `applications`, `outreach_contacts` — usa `GENERATED ALWAYS AS` literal del AC (Postgres 12+, sin triggers). `db/repos/search.SearchRepo.search()`. Search bar persistente en sidebar (`layout.py` declara `st.session_state.global_search_query` y un `text_input` con `data-testid="sidebar-search"`). Página dedicada `pages/6_🔎_Search.py` con resultados agrupados por entidad. |
| S08 Integración con E6 toolkit | ✅ | `pages/7_🛠_Assist.py` lee `st.query_params.get("job_id")` literal del AC; usa `st.status("Preparando asistencia...", expanded=True)` para los progress steps, exactamente como recomienda la nota del AC; integra `assist_application` de E6. |
| S09 Deploy + tests Playwright | ✅ | `Dockerfile.dashboard` específico. Workflow `.github/workflows/playwright.yml`. Tests E2E en `tests/e2e/dashboard/`: `test_dashboard_flows.py`, `test_assist_flow.py`, `test_search.py`, `test_pipeline_dashboard.py`, `test_new_matches.py`, `test_metrics_dashboard.py`, `test_outreach_dashboard.py`, `test_outreach_generation.py`, `test_outreach_metrics_e2e.py` — más cobertura que los 5 críticos pedidos por el AC. |

### Definition of Done de E7

- AC de las 9 stories: ✅ con S04 movida a E13 (8 implementadas + 1 diferida).
- CI con E2E: workflow `playwright.yml` separado, no bloquea PRs.
- `streamlit run` levanta dashboard: entry point existe y carga.
- Workflow E2E desde UI (login → match → assist → applied → pipeline):
  runtime, no verificable en repo.
- Mobile-responsive: runtime.
- Tag `v0.7.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fixes aplicados

S04 (Manual Review): el usuario eligió la **opción 3** del análisis original
(mover a una nueva épica) y solicitó crear la **Épica 13: QA Humana** como
contenedor para flujos de revisión humana de decisiones ambiguas de la IA.

### Cambios materializados en el repo

- **`docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md`**
  — nuevo documento de Backlog Nivel 2 para la Épica 13. Estructura:
    - Resumen ejecutivo que define E13 como contenedora de flujos de QA
      humana, con distinción explícita frente a E11 (E11 mide en agregado;
      E13 actúa sobre instancias individuales).
    - Decisiones técnicas clave: reusa la infraestructura de E7, sin lógica
      de negocio nueva, re-score con Sonnet on-demand, antigüedad como
      métrica de presión.
    - `E13-S01 — Página Manual Review (tier C)`: rescate literal de
      E07-S04, con bloque inicial que documenta el origen y por qué se
      movió. Conserva los AC originales (jobs `manual_review`, cards
      detalladas, botones `Promote to Queue` / `Re-score` / `Reject`,
      filtro por antigüedad, indicador "X jobs esperan review, Y > 7 días
      sin decisión"). Tasks ampliadas con detalles concretos
      (`JobRepo.mark_status`, `st.dialog` para captura de razón, test E2E
      mínimo).
    - Definition of Ready para futuras stories: la épica nace con 1 story
      pero queda abierta a `E13-S02+` cuando aparezcan más flujos de QA
      humana (follow-ups vencidos, tier B con red flags inesperados,
      outreach `replied` sin contenido).
- **`src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py`** — placeholder
  reemplazado: el `st.info("Placeholder: Implementation coming in next
  stories.")` original cambia a un `st.warning` que apunta explícitamente
  a la Épica 13, story `E13-S01`, y a la ruta del nuevo documento.

### Estado final E7

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| **S04** | **➡️ movida a E13-S01** |
| S05 | ✅ |
| S06 | ✅ |
| S07 | ✅ |
| S08 | ✅ |
| S09 | ✅ |

**Épica 7 cerrada en su scope reducido.**

---

## Épica 8 — Scheduling & Automation

Documento origen: `L_Backlog_Nivel_2_E8.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 DB hosted + secrets | ✅ | Composite action `.github/actions/setup-env/action.yml` parametrizada con `database_url`, `anthropic_api_key`, `telegram_bot_token`, `telegram_chat_id`, `smtp_user`, `smtp_password`, `digest_to_email`, `dashboard_password`. Workflow dummy `.github/workflows/test-connection.yml` (`workflow_dispatch`) para verificar conexión a la DB hosted. Runbook documenta `DR2: Secretos Filtrados` (rotación). |
| S02 `pipeline run-cycle` orquestador | ✅ | `pipeline.run_cycle()` async; `RunCycleReport` + `RunCycleStatus` enum con los 3 valores literales del AC (`SUCCESS`/`PARTIAL_FAILURE`/`TOTAL_FAILURE`); CLI `pipeline run-cycle` con `--skip-step` (repetible), `--since`, `--limit`, `--source`. Logging JSON via `LOG_FORMAT=json` que el workflow inyecta. **Diferencia estructural menor:** vive en `src/jobhunter/pipeline.py` (módulo único) en vez de `src/jobhunter/pipeline/run_cycle.py` (subpaquete) que sugería el AC; funcionalmente idéntico. |
| S03 Workflow pipeline cycle (cada 8h) | ✅ | `.github/workflows/pipeline-cycle.yml` con `cron: '0 */8 * * *'` literal; `workflow_dispatch` con inputs `limit` + `source`; `timeout-minutes: 30`; `concurrency: { group: pipeline-cycle, cancel-in-progress: false }` literal del AC; usa la composite action `setup-env`; redirige stdout a `pipeline-${{ github.run_id }}.jsonl`; sube artifact con `retention-days: 30`; Action Summary con tabla markdown que extrae métricas via `jq`; `Alert on Failure` step llamando a la composite action de S06. |
| S04 Workflow digest semanal | ✅ | `.github/workflows/weekly-digest.yml` con `cron: '0 17 * * 0'` literal del AC (domingos 17 UTC = 12:00 COT); `workflow_dispatch`; `timeout-minutes: 5`. Invoca `notify digest --send` (de E5-S06). |
| S05 Workflow follow-up checks | ✅ | `.github/workflows/followup-checks.yml` con `cron: '0 14 * * *'` literal (diario 14 UTC = 09:00 COT); `workflow_dispatch`. CLI `pipeline check-followups` invoca `pipeline.run_followup_checks(session)` que devuelve `FollowupReport`; lógica auto-marca ghosted (>21 días) y refresca `weekly_metrics` materialized view. |
| S06 Alertas de fallo | ✅ | Composite action `.github/actions/alert-on-failure/action.yml` con `curl` directo a Telegram (sin Python — exactamente como recomendaba el AC); incluye link al run + preview de 10 líneas del log. Aplicada como último step (`if: failure()`) en `pipeline-cycle.yml`. CLI `health-check` (`@app.command("health-check")`) verifica última corrida pipeline-cycle, followup-checks, circuit breakers, costo LLM mensual. `.github/workflows/health-check.yml` con `cron: '0 */4 * * *'` literal. **Anti-spam** vía `dedup_key = f"health_check:{alert_type}:{date_hour}"` literal del AC, persistido en tabla `notifications_sent` (reuso de E5-S01). |
| S07 Logs estructurados + observabilidad | ✅ | `Settings.LOG_FORMAT: Literal["json", "pretty"] = "pretty"` literal del AC; los workflows setean `LOG_FORMAT: json`; artifact upload con `retention-days: 30`; CLI `logs tail`; Action Summary visible en GitHub UI con tabla markdown (status, duration, ingested/scored/notified, cost). `JOBHUNTER_CORRELATION_ID = ${{ github.run_id }}` para correlación cross-step. |

### Definition of Done de E8

- AC de las 7 stories: ✅ (sin desvíos relevantes; sólo la diferencia
  estructural menor en S02).
- Composite actions reusadas (`setup-env`, `alert-on-failure`).
- Anti-spam de health alerts: implementado y testeado vía `dedup_key`.
- Sistema corre desatendido 7 días con tasa de éxito ≥95%: runtime, no
  verificable en repo.
- Fallo simulado disparó alerta Telegram: runtime, no verificable en repo.
- Digest semanal recibido: runtime.
- DB hosted en producción con backup verificado: runtime; el script
  `scripts/backup_db.sh` y el workflow `backup-and-drill.yml` están listos.
- `docs/runbook.md` documenta workflows + investigación de fallos (§DR2,
  §SOP-02, §42).
- Tag `v0.8.0`: aceptado bajo la regla `__version__ = "1.0.0"`.

**Épica 8 cerrada limpia. Sin desvíos que documentar.**

---

## Épica 9 — Recruiter Outreach Module

Documento origen: `M_Backlog_Nivel_2_E9.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 Tabla `outreach_messages` + repo | ✅ | Migración `d04e23d53872_add_outreach_messages_table.py` con todas las columnas del AC: `template_type`, `template_version`, `body_edited_by_user` (default false), `research_notes`, `cost_usd`, `status`, `parent_message_id` (self-FK), índice parcial `idx_outreach_messages_status_sent` con `postgresql_where='status IN ('sent','draft')'`. `OutreachMessageRepo` con los 6 métodos del AC: `create_draft`, `mark_sent`, `mark_replied`, `mark_ghosted`, `list_by_contact`, `list_pending_followups` (más extras `mark_discarded`, `update_body`, `list_due_for_followup`, `list_ghosted_messages`). |
| S02 Templates versionados | ✅ | `prompts/outreach/v1/` con los **4 templates literales del AC**: `A_inhouse.md`, `B_boutique.md`, `C_senior.md`, `D_followup.md`. `prompts/outreach/forbidden_phrases.txt`. `outreach/templates.py` con `OutreachTemplate` (Pydantic), `load_outreach_template(template_type, version="latest")`, `render_outreach_template()`. |
| S03 Generador IA (Sonnet) | ✅ | `outreach/generator.generate_message()` async + `MessageGenerationResult` + `OutreachGenerationError`. `Settings.OUTREACH_MODEL: str = "claude-sonnet-4-6"` literal del AC. Persiste como `OutreachMessage` con `status='draft'`. |
| S04 LinkedIn CSV importer + scoring | ✅ | `outreach/linkedin_csv.LinkedInCSVParser`. CLI `outreach import` con `--from`, `--mapping`, `--enrich-with-ai` (los 3 flags del AC). `outreach/scoring.calculate_heuristic_score` con `recruiter_keywords = ["tech recruiter", "talent acquisition", "engineering recruiter"]` literal del AC; `infer_market` con regla `"GmbH"→DE, "Ltd"→UK` literal; `outreach/dach_companies.py` con la lista hardcoded (N26, Trade Republic, Personio, Aleph Alpha, DeepL, etc.). |
| S05 Cadencia + follow-ups | ✅ | CLI `outreach check-cadence` invoca `pipeline.run_outreach_cadence_checks(session)` que: marca como `ghosted` mensajes con `sent_at > 21 días` (`list_ghosted_messages` usa `timedelta(days=21)` literal); identifica due-for-followup en ventana 7-10 días (`list_due_for_followup` con `days_threshold=7`). **Política de 2 toques** enforced a nivel DB en `OutreachMessageRepo.create_draft` (raise `ValueError` si el contacto ya tiene ≥2 mensajes en `SENT`/`GHOSTED` sin reply) — implementación más estricta que el AC literal. Integrado en `pipeline.run_followup_checks` (workflow `followup-checks.yml` de E8-S05). |
| **S06 Suite CLI** | ⚠️ inicialmente, **➡️ subset movido a E13-S02** | El AC pide **8 comandos**; sólo **3 están implementados** en CLI: `outreach import` (S04), `outreach stats` (S08), `outreach check-cadence` (S05). **Faltan 6:** `outreach add`, `outreach candidates`, `outreach draft <contact-id>`, `outreach sent <message-id>`, `outreach replied <message-id>`, `outreach list`. El dashboard E7-S05/E9-S07 cubre el workflow visual; los 6 comandos faltantes se difirieron a la nueva story `E13-S02` por decisión del usuario. |
| S07 Activación en dashboard | ✅ | `pages/4_💌_Outreach.py` (584 líneas) tiene `@st.dialog("Generar Mensaje")` con form: radio `template_type` (A/B/C/D), textarea `research_notes` con **validación ≥20 chars** literal del AC, radio `language` (en/es), botón "Generar"; spinner "Generando mensaje con Claude Sonnet..." durante generación; integrado con `outreach.generator.generate_message`. Botones `Mark Contacted`, `Mark Replied`, `Mark Warm`, `Add Note` en cada fila. |
| S08 Métricas + tests | ✅ | CLI `outreach stats --since "4 weeks ago"` (default ventana de 4 semanas, alineado con AC). Sección equivalente en dashboard de Metrics (`MetricsService` centraliza). Tests integración cubren creación, importación, cadencia. Tests E2E Playwright: `test_outreach_generation.py`, `test_outreach_dashboard.py`, `test_outreach_metrics_e2e.py`. |

### Definition of Done de E9

- AC de las 8 stories: ✅ con S06 parcial (3 de 8 comandos CLI; los 6
  restantes movidos a `E13-S02`).
- CI con tests integración: ✅.
- Workflow E2E desde dashboard: cubierto vía la dialog "Generar Mensaje" +
  tests Playwright.
- 5 mensajes reales enviados manualmente: runtime, no verificable.
- Métricas iniciales capturadas: runtime.
- Tag `v0.9.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

S06 (6 comandos CLI faltantes): el usuario eligió la **opción 3** del
análisis original (mover el subset a otra épica), pero específicamente
como **`E13-S02`** (no como mini-épica nueva). La épica E13 (creada durante
la verificación de E7) se amplió ligeramente para acomodar este tipo de
brecha además de los flujos de QA humana sobre decisiones ambiguas.

### Cambios materializados en el repo

- **`docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md`**
  — actualizado para incluir `E13-S02`. Cambios:
    - Header: `Total stories: 1 → 2`; `Estimación: 1.5–2h → 3.5–4h`.
    - Resumen ejecutivo ampliado para reconocer el segundo tipo de brecha
      humana (CLI ergonómico para flujos human-in-the-loop por diseño),
      manteniendo coherencia con el alcance original.
    - Tabla de stories con fila nueva para `E13-S02 — Comandos CLI
      faltantes de outreach (suite humana) | 2h | E9-S01–S05 cerradas |
      Subset diferido de E09-S06`.
    - Definition of Done ampliada con sección "2. CLI" mostrando el
      workflow completo (`add` → `candidates` → `draft` → `sent` →
      `replied` → `list`).
    - Story `E13-S02` completa con bloque "Origen" documentando el rescate
      desde E09-S06, AC desglosado por cada uno de los 6 comandos
      (preservando detalles literales del AC original: ordenamiento
      `quality_score DESC, last_contacted_at ASC NULLS FIRST`, default
      `--copy=False`, validación `--note ≥20 chars`, propagación de la
      política de 2 toques como exit 1), tasks de implementación,
      estimación 2h, notas (reuso máximo, `--copy` opcional, alternativa
      `pbcopy`).
    - Definition of Ready actualizada para reflejar las dos stories
      iniciales y abrir la puerta a `E13-S03+`.

### Estado final E9

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| S04 | ✅ |
| S05 | ✅ |
| **S06** | **⚠️ parcial (3 de 8 implementados; los 6 restantes ➡️ E13-S02)** |
| S07 | ✅ |
| S08 | ✅ |

**Épica 9 cerrada con desvío parcial documentado.**

---

## Épica 10 — Response Detection (Gmail)

Documento origen: `N_Backlog_Nivel_2_E10.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 OAuth2 Gmail + token storage | ✅ | Settings con `GMAIL_CLIENT_ID`/`GMAIL_CLIENT_SECRET` (SecretStr), `GMAIL_REDIRECT_URI: str = "http://localhost:8765/oauth/callback"` literal del AC, `OAUTH_ENCRYPTION_KEY: SecretStr`. Migración `2b3696072a71_add_oauth_tokens_table.py` con `provider`, `account_email`, `access_token`, `refresh_token`, `expires_at`, `scopes`, `idx_oauth_provider_email UNIQUE (provider, account_email)`. `crypto.py` con `encrypt`/`decrypt` usando `Fernet` literal del AC. `OAuthTokenRepo` con `get_token(provider, account_email)` + heredados de `BaseRepo`. CLI `email auth`. |
| S02 Tabla `email_messages` + repo | ✅ | Migración `99ead058acfc_add_email_messages_table.py` con todas las columnas del AC: `gmail_message_id` UNIQUE, `gmail_thread_id`, `from_domain`, `snippet` (200), `body_hash` (64), `match_status` (default `unmatched`), `matched_application_id`/`matched_outreach_message_id` (FKs nullables), `match_confidence` (Float), `suggested_status_change` (JSONB), constraint XOR `"(matched_application_id IS NULL) OR (matched_outreach_message_id IS NULL)"` literal. Índices `idx_email_from_domain`, `idx_email_match_status`, `idx_email_received_at` (DESC). `EmailMessageRepo` con los 6 métodos del AC. |
| S03 Gmail API client wrapper | ✅ | `email/gmail_client.GmailClient` con los 4 métodos del AC; `_execute_with_retry` para refresh automático del access token; `_parse_message` para multipart/base64 de Gmail. Deps `google-api-python-client`, `google-auth`, `google-auth-oauthlib` declaradas. |
| **S04 Email matcher (heurística + IA)** | ⚠️ inicialmente, **➡️ subset movido a E13-S03** | `email/matcher.match_email` async + `MatchResult`; las **3 heurísticas del AC** presentes: domain match (confidence 0.9), `SUBJECT_KEYWORDS` (confidence 0.95), `MARKETING_MARKERS` + `UNSUBSCRIBE_MARKER`; **escalación a IA si `confidence < 0.8`** literal del AC; keywords de transición (interview, offer, congratulations). Tests `test_matcher.py`. **Desvío menor:** el AC pide `prompts/email_matcher/v1.md` versionado; ese archivo no existe — el prompt vive inline en el código. Movido a `E13-S03`. |
| S05 Sugeridor de cambios de estado | ✅ | `email/suggester.suggest_state_changes(session)` async + `StateSuggestion` (Pydantic) + `SuggestionStatus` (StrEnum); helper `_requires_confirmation(suggestion, match_status)` literal del AC + `_is_positive_transition(current, suggested)` para la política conservadora "auto-apply solo en transiciones positivas". |
| S06 Telegram inline buttons | ✅ | `TelegramNotifier` extendido con `send_with_buttons(message, buttons)`; modelo `Button(BaseModel)` con `callback_data: str`; uso de `InlineKeyboardButton` + `InlineKeyboardMarkup`. CLI `telegram process-callbacks` (sub-Typer `telegram`). |
| S07 Workflow `email-poll` | ✅ | `.github/workflows/email-poll.yml` con `cron: '*/30 * * * *'` literal; `timeout-minutes: 5`; `concurrency: { group: email-poll, cancel-in-progress: false }` literal. CLI `email poll-and-suggest`. Orquestador `email/orchestrator.run_email_poll_and_suggest(session)`. |
| **S08 Métricas + tests** | ⚠️ inicialmente, **➡️ subset movido a E13-S03** | Tests presentes en `tests/unit/email/`: `test_gmail_client.py`, `test_matcher.py`, `test_orchestrator.py`, `test_suggester.py`. **Desvío:** el AC pide CLI `jobhunter email stats` con tasa de match, precision, costo IA, top dominios. Sub-Typer `email` sólo tiene `auth` y `poll-and-suggest`; `email stats` no existe (las métricas equivalentes viven en dashboard E7-S06). Movido a `E13-S03`. |

### Definition of Done de E10

- AC de las 8 stories: ✅ con dos desvíos menores (S04 prompt no extraído,
  S08 CLI `email stats` faltante), ambos consolidados en `E13-S03`.
- CI con tests integración: ✅ unit tests cubren matcher/suggester/
  orchestrator/gmail_client.
- OAuth flow probado E2E: runtime, no verificable.
- Workflow `email-poll` corre 24h: runtime.
- Precision ≥80% en muestra real: runtime.
- Tag `v0.10.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

S04 (prompt no versionado) y S08 (CLI `email stats` faltante): el usuario
eligió la **opción 3** del análisis (mover los desvíos a E13), siguiendo el
patrón establecido en E13-S01 y E13-S02. Ambos desvíos se consolidan en una
sola story `E13-S03 — Email matcher: prompt versionado + CLI email stats`
porque comparten origen (módulo `email/`) y pueden implementarse en el
mismo PR.

### Cambios materializados en el repo

- **`docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md`**
  — actualizado para incluir `E13-S03`. Cambios:
    - Header: `Total stories: 2 → 3`; `Estimación: 3.5–4h → 4.5–5h`.
    - Resumen ejecutivo ampliado para reconocer el tercer tipo de brecha
      (gaps de observabilidad sobre servicios IA: prompts inline,
      métricas faltantes).
    - Tabla de stories con fila nueva para `E13-S03 — Email matcher:
      prompt versionado + CLI 'email stats' | 1h | E10-S04, E10-S08
      cerradas | Subset diferido de E10-S04 + E10-S08`.
    - Definition of Done ampliada con sección "3. Observabilidad email"
      mostrando `ls prompts/email_matcher/v1.md` y `jobhunter email stats`.
    - Story `E13-S03` completa con:
      - Bloque "Origen" documentando los dos desvíos rescatados
        (E10-S04 prompt inline, E10-S08 CLI faltante) y la justificación
        de consolidarlos en una sola story.
      - **Parte A (prompt versionado):** AC para crear
        `prompts/email_matcher/v1.md` con estructura estándar `## SYSTEM`
        + `## USER_TEMPLATE` + `## REQUIREMENTS`, refactor del matcher
        para consumir el loader (con `lru_cache`), persistencia de
        `prompt_version` en `email_messages` para trazabilidad, y test
        de regresión que verifica `MatchResult` idéntico antes/después
        del refactor.
      - **Parte B (CLI email stats):** AC con las 5 secciones del AC
        original (total emails, tasa de match, precision estimada,
        costo IA, top dominios), flag `--since "N weeks ago"` (default
        4 semanas), exit code 1 opcional con `--strict` si precision
        cae bajo target.
      - Tasks de implementación, estimación 1h, notas
        (no introduce deps nuevas, test de regresión crítico).
    - Definition of Ready actualizada para reflejar las tres stories
      iniciales y abrir la puerta a `E13-S04+`.

### Estado final E10

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| **S04** | **✅ con desvío ➡️ E13-S03 (parte A: prompt versionado)** |
| S05 | ✅ |
| S06 | ✅ |
| S07 | ✅ |
| **S08** | **✅ con desvío ➡️ E13-S03 (parte B: CLI `email stats`)** |

**Épica 10 cerrada con desvíos menores documentados.**

---

## Épica 11 — Metrics, Analytics & Continuous Tuning

Documento origen: `O_Backlog_Nivel_2_E11.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 Servicio de métricas consolidadas | ✅ | `src/jobhunter/analytics/` con los **6 submódulos del AC**: `pipeline_metrics.py`, `quality_metrics.py`, `cost_metrics.py`, `outreach_metrics.py`, `email_metrics.py`, `prompt_metrics.py`. Funciones puras + Pydantic models. Tests unit por cada submódulo. |
| S02 A/B testing infrastructure | ✅ | Migración `cb5c9f0689f4_create_ab_tests_table.py` con todas las columnas del AC (`name UNIQUE`, `description`, `metric_target`, `variants` JSONB, `started_at`, `status` default `active`, `conclusion`). `analytics/ab_testing.py` con `select_variant(session, test_name, entity_id)` determinístico, `calculate_z_test`, `_normal_cdf` para significancia, `get_ab_test_results` → `ABTestResults`/`VariantResult`. CLI con los 3 subcomandos del AC (`ab-test create`, `ab-test results`, `ab-test conclude`). |
| S03 Detector de regresiones + alertas | ✅ | `analytics/regression_detector.check_metrics(session)` con las **6 métricas del AC** (`tier_a_rate`, `application_rate`, `response_rate`, `outreach_response_rate`, `email_matcher_precision`, `pipeline_success_rate`); compara última semana vs promedio de las 4 anteriores. CLIs `analytics check-regressions` + `analytics check-anomalies`. `get_inferred_context()` enriquece la alerta con commits/cambios recientes. |
| S04 False rejects + missed opportunities | ✅ | Migración `73fe5268d2b9_add_manually_promoted_columns_to_jobs.py` añade `manually_promoted_at` + `manually_promoted_reason` a `jobs` literal del AC. CLIs `analytics false-rejects`, `analytics missed-opportunities`, `analytics rescore-suspicious` (los 3 del AC). Tests `test_false_rejects.py`. |
| S05 Reportes mensuales (Sonnet) | ✅ | `analytics/report_generator.py` con `collect_metrics_for_period`, `calculate_comparison`, `format_report_as_html`, `convert_html_to_pdf` (vía `weasyprint` literal del AC). `prompts/analytics_report/v1.md` versionado. CLI `analytics report --month YYYY-MM --output md\|html\|pdf`. Reportes archivados en `reports/`. |
| S06 Recomendaciones automáticas | ✅ | `analytics/recommendations.py` con `Recommendation` (Pydantic) + enums `Effort` y `Priority`. Implementa **las 6 reglas heurísticas literales del AC**: `_check_template_zero_response`, `_check_source_dry_spell`, `_check_prompt_regression`, `_check_manual_review_bottleneck`, `_check_budget_warning`, `_check_circuit_breaker_stuck`. Función pública `get_recommendations(session)`. CLI `analytics recommendations`. |
| **S07 Export PDF + UI dashboard analytics** | ⚠️ inicialmente, **➡️ movido a E13-S04** | El AC pide página `pages/8_📈_Analytics.py` con 4 secciones (Recommendations, A/B tests activos, False rejects review, Reports archive) y workflow `monthly-report.yml` con `cron: '0 8 1 * *'`. **Ambas piezas ausentes:** la página `8_` que existe es `8_🏥_Status.py` (System Health, parte de E12); no hay `pages/8_📈_Analytics.py` ni `pages/9_📈_Analytics.py`. El workflow `monthly-report.yml` no existe. **PDF export sí está** (vía `weasyprint` en `report_generator.convert_html_to_pdf`). Movido a `E13-S04`. |
| S08 Tests + workflow semanal | ✅ | `.github/workflows/weekly-analysis.yml` con `cron: '0 13 * * 1'` literal del AC (lunes 13:00 UTC = 08:00 COT); ejecuta los 3 comandos (`check-regressions --markdown`, `check-anomalies --markdown`, `recommendations --markdown`) volcando a `$GITHUB_STEP_SUMMARY`; integra `alert-on-failure`. Tests integración cross-épica: `test_pipeline_sim.py`, `test_ab_testing_e2e.py`, `test_report_e2e.py`, `test_false_rejects.py`. |

### Definition of Done de E11

- AC de las 8 stories: ✅ excepto S07 (página dashboard analytics + workflow
  mensual ausentes), ambos consolidados en `E13-S04`.
- CI con tests integración cross-épica: ✅.
- Workflow `weekly-analysis.yml`: presente y completo.
- Reporte mensual: el código para generarlo existe; falta el cron mensual y
  la superficie UI (movidos a E13).
- A/B test creado y conducido: runtime.
- Sección Analytics del dashboard: ❌ ausente, movida a E13-S04.
- Tag `v0.11.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

S07 (página Analytics + workflow mensual): el usuario eligió la **opción 3**
del análisis (mover a E13), siguiendo el patrón establecido en E13-S01,
E13-S02 y E13-S03. Se consolida en una sola story `E13-S04 — Página
dashboard Analytics + workflow monthly-report` porque las dos piezas son
superficies de presentación del mismo ciclo de mejora continua y comparten
contexto de implementación (`analytics/report_generator`, `EmailNotifier`).

### Cambios materializados en el repo

- **`docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md`**
  — actualizado para incluir `E13-S04`. Cambios:
    - Header: `Total stories: 3 → 4`; `Estimación: 4.5–5h → 6–6.5h`.
    - Resumen ejecutivo ampliado para reconocer el cuarto tipo de brecha
      (superficies de analytics avanzado que cierran el ciclo de mejora
      continua).
    - Tabla de stories con fila nueva para `E13-S04 — Página dashboard
      Analytics + workflow monthly-report | 1.5h | E11-S05, E11-S06
      cerradas | Subset diferido de E11-S07`.
    - Definition of Done ampliada con sección "4. Analytics avanzado"
      mostrando `streamlit run` con la página Analytics y `gh workflow
      run monthly-report.yml`.
    - Story `E13-S04` completa con:
      - Bloque "Origen" documentando los dos componentes ausentes (página
        Streamlit con 4 secciones + workflow cron mensual) y la nota
        explícita de que toda la lógica subyacente existe — sólo falta
        superficie de presentación.
      - **Parte A (página Analytics):** AC para crear
        `pages/9_📈_Analytics.py` (slot `8_` ocupado por Status), las 4
        secciones literales del AC (Recommendations con quickbuttons
        Snooze/Acted/Ignore, A/B tests activos con detalle vía
        `get_ab_test_results`, False rejects review con botón Promote,
        Reports archive con `st.download_button`), botones "Generate
        report" on-demand y "Export to PDF", test E2E Playwright.
      - **Parte B (workflow monthly-report):** AC para crear
        `.github/workflows/monthly-report.yml` con `cron: '0 8 1 * *'`
        literal, `workflow_dispatch` con input `month` opcional, steps
        análogos a `weekly-digest.yml`, envío de email con PDF adjunto
        (extender `EmailNotifier` si no soporta attachments), `Alert on
        Failure`, CLI `analytics report --send-email` para testing.
      - Tasks de implementación, estimación 1.5h, notas (slot `9_` para
        evitar conflicto con `8_🏥_Status.py`, Analytics page como
        portfolio piece, posible extensión de `EmailNotifier` con
        `MIMEApplication`).
    - Definition of Ready actualizada para reflejar las cuatro stories
      iniciales y abrir la puerta a `E13-S05+`.

### Estado final E11

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| S04 | ✅ |
| S05 | ✅ |
| S06 | ✅ |
| **S07** | **⚠️ ➡️ E13-S04 (página Analytics + workflow `monthly-report`)** |
| S08 | ✅ |

**Épica 11 cerrada con desvío documentado.**

---

## Épica 12 — Observability, Security & Operations

Documento origen: `P_Backlog_Nivel_2_E12.md`.

### Verificación

| Story | Estado | Evidencia |
|---|---|---|
| S01 Logging estructurado | ✅ | `src/jobhunter/log_config.py` con `configure_logging`, `_CORRELATION_ID` (`contextvars.ContextVar`), procesador `add_correlation_id`, `redact_sensitive_info`. Workflows YAML usan `LOG_FORMAT=json` + `JOBHUNTER_CORRELATION_ID=$GITHUB_RUN_ID`. CLI `logs tail` (de E8-S07). |
| S02 Secrets hygiene | ✅ | `.secrets.baseline` versionado; `.pre-commit-config.yaml` con `detect-secrets`. `.github/workflows/secrets-scan.yml` presente. `.gitignore` cubre `.env`, `.local/`, etc. Plan de rotación documentado en `docs/runbook.md` (§DR2). |
| S03 Backup + restore drill | ✅ | `.github/workflows/backup-and-drill.yml` presente. CLI `backup create`, `backup list`, `backup restore`. Settings `BACKUP_STORAGE_PROVIDER`, `BACKUP_RETENTION_WEEKS: int = 12` literal del AC. `db/backup.py` con `create_compressed_backup`, `restore_from_compressed_backup`, `BackupStorage`, `validate_db_integrity`, `run_backup_cleanup`. Deps `boto3`. Existen `pre_drill_backup.sql.gz` y `test_backup.sql.gz` como evidencia. |
| S04 Health endpoints + status page | ✅ | **FastAPI sidecar** en `src/jobhunter/api/main.py` con `/health`, `/readiness`, `/status` (HTMLResponse pública). `health.py` con `HealthReport`, `ComponentStatus`, `SystemMetrics`, `get_health_report`. Página dashboard `pages/8_🏥_Status.py` (autenticada). CLI `api run`. Resuelve el "Streamlit no permite endpoints custom" del AC vía sidecar separado. |
| S05 Rate limiting + abuse prevention | ✅ | Migración `72ef8867ac56_add_security_tracking_tables.py` con tablas `failed_login_attempts` y `blocked_ips`. Modelos en `db/models.py`. `db/repos/security.SecurityRepo`. Página `8_🏥_Status.py` integra estas señales. |
| **S06 Audit logs + compliance lite** | ❌ inicialmente, **➡️ movido a E13-S05** | **Falta toda la infraestructura:** no existe modelo `AuditLog`, ninguna migración, ningún `@audit_logged`, ningún CLI `audit query` ni `compliance export-data` ni `compliance delete-all`. La única "auditoría" presente es el tracking básico de S05 (`failed_login_attempts`/`blocked_ips`), que es para abuse prevention, no audit trail completo. Movido a `E13-S05`. |
| S07 Runbook + disaster recovery | ✅ | `docs/runbook.md` denso con 53 secciones. Cubre setup, operación, mantenimiento, troubleshooting, DR. **DR1–DR5** documentados (§DR2 "Secretos Filtrados", §29 "Estrategia de Backup Multicapa", §SOP-02 "Respuesta a Alerta de Salud", §42 "Configuración Telegram", §46 "Restauración Parcial de Datos"). Drill ejecutado: `pre_drill_backup.sql.gz` evidencia DR1. |
| **S08 Pen test + cierre** | ⚠️ desvío menor, **detalle ➡️ E13-S05** | `ci.yml` ejecuta `bandit -r src/ -ll` ✓ y `pip-audit` ✓. **Falta `trivy fs .`** del AC (consolidado en `E13-S05` parte C). Manual checks (SQL injection, XSS, etc.) no son verificables desde repo — el uso uniforme de SQLAlchemy parametrized queries y la naturaleza auto-escape de Streamlit cubren los riesgos principales. ADRs: 7 ADRs en `docs/adr/` (los del backlog original más los 2 creados durante esta verificación, ADR-006 y ADR-007). **Tag `v1.0.0`** efectivo via `__version__ = "1.0.0"` y badge del README. |

### Definition of Done de E12

- AC de las 8 stories: ✅ excepto S06 (audit logs + compliance lite) y un
  detalle menor en S08 (`trivy`), ambos consolidados en `E13-S05`.
- CI con coverage ≥75% global: badge del README declara 75%.
- DR1 drill ejecutado: `pre_drill_backup.sql.gz` lo evidencia.
- Runbook denso: 53 secciones en `docs/runbook.md`.
- `bandit`, `pip-audit` integrados en CI: ✅ (`trivy` queda en E13-S05).
- Sistema operacional 14 días sin incidentes: runtime, no verificable.
- Tag `v1.0.0`: aceptado bajo la regla `__version__`.

### Decisión del usuario y fix aplicado

S06 (audit log + compliance lite) y el detalle de S08 (`trivy`): el
usuario eligió la **opción 3** del análisis (mover a E13), siguiendo el
patrón establecido en E13-S01 a E13-S04. Ambos desvíos se consolidan en
una sola story `E13-S05 — Audit log + compliance lite + trivy en CI`
porque comparten temática (security surface) y pueden implementarse en el
mismo PR.

### Cambios materializados en el repo

- **`docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md`**
  — actualizado para incluir `E13-S05`. Cambios:
    - Header: `Total stories: 4 → 5`; `Estimación: 6–6.5h → 8–8.5h`.
    - Resumen ejecutivo ampliado para reconocer el quinto tipo de brecha
      (trazabilidad de mutaciones críticas para incident response y
      compliance lite).
    - Tabla de stories con fila nueva para `E13-S05 — Audit log +
      compliance lite + trivy en CI | 2h | E2 cerrada | E12-S06 +
      detalle de E12-S08`.
    - Definition of Done ampliada con sección "5. Audit + compliance +
      trivy" mostrando `jobhunter audit query`, `compliance
      export-data`, `compliance delete-all --confirm-twice`, `trivy fs .`.
    - Story `E13-S05` completa con:
      - Bloque "Origen" documentando los dos rescates (E12-S06 desvío
        real + E12-S08 detalle menor) y la justificación de
        consolidarlos por afinidad de security surface.
      - **Parte A (audit log):** AC para migración con las 9 columnas
        literales del AC original (event_type enum, actor, target_entity/
        target_id, action, metadata JSONB, ip_address), modelo +
        `AuditLogRepo`, decorator `@audit_logged`, aplicación en
        mutaciones críticas literales (login/logout, bulk deletes,
        backups/restores, OAuth token access, secret rotation), CLI
        `audit query` con filtros, sub-tab en página dashboard.
      - **Parte B (compliance lite):** AC para CLI `compliance
        export-data` (export JSON con tokens redactados) y `compliance
        delete-all --confirm-twice` (doble confirmación textual + audit
        log antes del delete + orden correcto respetando FKs +
        preservación de `audit_log`/`alembic_version`/security ops).
      - **Parte C (trivy en CI):** AC para step nuevo en `ci.yml` con
        `aquasecurity/trivy-action`, `severity: CRITICAL,HIGH`,
        `exit-code: 1`, `.trivyignore` inicial vacío, nota en runbook.
      - Tasks de implementación, estimación 2h, notas (decorator vs
        llamada explícita, `delete-all` nuclear con doble confirmación,
        trivy ruidoso si no se filtra severidad, audit log no es GDPR
        compliance).
    - Definition of Ready actualizada para reflejar las cinco stories
      iniciales y abrir la puerta a `E13-S06+`.

### Estado final E12

| Story | Estado |
|---|---|
| S01 | ✅ |
| S02 | ✅ |
| S03 | ✅ |
| S04 | ✅ |
| S05 | ✅ |
| **S06** | **➡️ E13-S05 (parte A: audit log + parte B: compliance lite)** |
| S07 | ✅ |
| **S08** | **✅ con detalle ➡️ E13-S05 (parte C: `trivy` en CI)** |

**Épica 12 cerrada con desvíos documentados.**

---

## Resumen consolidado (parcial)

| Épica | Stories | Estado | Desvíos documentados | Artefactos creados/modificados |
|---|---|---|---|---|
| E7 Dashboard | 9 | ✅ con S04 movida | S04 ➡️ E13-S01 | `Q_Backlog_Nivel2_E13.md` (nuevo), `pages/3_🔍_Manual_Review.py` (notificación de traslado) |
| E8 Scheduling | 7 | ✅ | — (diferencia estructural menor en S02, no requiere doc) | — |
| E9 Outreach | 8 | ✅ con S06 parcial | S06 ➡️ E13-S02 (subset de 6 comandos CLI) | `Q_Backlog_Nivel2_E13.md` (ampliado con `E13-S02`) |
| E10 Response Detection | 8 | ✅ con S04+S08 menores | S04 + S08 ➡️ E13-S03 (prompt versionado + CLI `email stats`) | `Q_Backlog_Nivel2_E13.md` (ampliado con `E13-S03`) |
| E11 Analytics | 8 | ✅ con S07 movida | S07 ➡️ E13-S04 (página dashboard Analytics + workflow `monthly-report`) | `Q_Backlog_Nivel2_E13.md` (ampliado con `E13-S04`) |
| E12 Observability | 8 | ✅ con S06 movida + detalle S08 movido | S06 + detalle S08 ➡️ E13-S05 (audit log + compliance lite + `trivy`) | `Q_Backlog_Nivel2_E13.md` (ampliado con `E13-S05`) |

### Nuevas épicas surgidas durante la verificación

- **Épica 13: QA Humana** (`Q_Backlog_Nivel2_E13.md`) — contenedora de
  brechas de operación humana del sistema. Inicialmente contenedora de
  flujos donde el humano arbitra decisiones ambiguas de la IA, ampliada
  iterativamente durante la verificación para incluir gaps de superficie
  operativa (CLI/UI), gaps de observabilidad sobre servicios IA,
  superficies de analytics avanzado, y trazabilidad de mutaciones
  críticas. Stories actuales (5 en total, ~8h estimadas):
    - `E13-S01` — Página Manual Review (tier C) en dashboard, rescatada de
      E07-S04.
    - `E13-S02` — Comandos CLI faltantes de outreach (suite humana),
      rescatada del subset diferido de E09-S06 (6 de 8 comandos: `add`,
      `candidates`, `draft`, `sent`, `replied`, `list`).
    - `E13-S03` — Email matcher: prompt versionado + CLI `email stats`,
      rescatada de los dos desvíos menores de E10 (S04 prompt inline,
      S08 CLI faltante).
    - `E13-S04` — Página dashboard Analytics + workflow `monthly-report`,
      rescatada de E11-S07 (UI de recommendations/A-B-tests/false-rejects/
      reports archive + cron mensual `'0 8 1 * *'`).
    - `E13-S05` — Audit log + compliance lite + `trivy` en CI, rescatada
      de E12-S06 (audit log table + decorator + CLI `audit query` +
      `compliance export-data`/`delete-all`) y del detalle menor de
      E12-S08 (scanner `trivy` faltante en CI).

  Abierta a más stories (`E13-S06+`) cuando aparezcan flujos similares.

### Reglas de aceptación transversales aplicadas

(Mismas que en el documento de Épicas 1-6.)

1. **Tags `v0.X.0` por épica:** se aceptan como cumplidos por el salto directo
   a `__version__ = "1.0.0"`. No se crean retroactivamente.
2. **PAT en `.git/config`:** ignorado por instrucción del usuario (token
   temporal y local, no commiteado).
3. **Métricas runtime** (jobs reales en DB, latencia, tiempos de operación,
   etc.): no verificables desde el repo; se asumen cubiertas por las pruebas
   manuales fuera de scope de esta verificación.

---

**Documento finalizado. Última actualización: 2026-05-01 (verificación de
Épicas 7 a 12 completadas).** Junto con
`Confirmación Épicas 1-6 Completadas Correctamente.md`, cubre las **12
épicas del backlog Nivel 1 (Documento D)** verificadas contra el estado
del repositorio. Los desvíos detectados durante la verificación se
consolidaron en la nueva **Épica 13 — QA Humana**
(`Q_Backlog_Nivel2_E13.md`), con 5 stories iniciales (~8h estimadas) que
agrupan placeholders de UI, comandos CLI faltantes, prompts inline, gaps
de observabilidad y audit log/compliance pendientes.
