# Documento Q — Backlog Nivel 2: Descomposición de E13 (QA Humana)

**Épica origen:** E13 — QA Humana (épica nueva, posterior a E12).
**Tamaño épica:** S (≤1 día, abierto a crecer si se añaden flujos de QA adicionales).
**Total stories:** 5 (la épica es contenedor para futuros flujos de QA humana).
**Estimación total:** 8–8.5 horas.

**Convenciones:** mismas que documentos E–P. ID `E13-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E13 es una **épica nueva** que agrupa las brechas de operación humana del
sistema: flujos donde el humano arbitra decisiones ambiguas de la IA
(`E13-S01`), comandos CLI ergonómicos para los workflows que por diseño
mantienen al humano-in-the-loop (`E13-S02`), gaps de observabilidad sobre
los servicios IA que el humano necesita para iterar prompts y heurísticas
(`E13-S03`), superficies de analytics avanzado que cierran el ciclo de
mejora continua (`E13-S04`), y trazabilidad de mutaciones críticas para
respuesta a incidentes y compliance lite (`E13-S05`). No introduce
funcionalidad de negocio inédita; rescata stories que en su épica original
se determinaron como diferibles (placeholder pages, botones "manual
review", subsets de CLI sin implementar, prompts inline, métricas
faltantes, páginas de dashboard ausentes, audit logs no construidos) y las
consolida bajo un objetivo común: **hacer eficiente el 5–10% de tareas que
requieren ojos y manos humanas**.

**Distinción con E11 (Metrics, Analytics & Tuning):** E11 mide el sistema en
agregado (tasas de respuesta, distribución de tiers, regresiones). E13 actúa
sobre instancias individuales que el sistema marcó para revisión o sobre
gaps de superficie (UI/CLI) que bloquean la operación humana.

### Decisiones técnicas clave

1. **Reusar la infraestructura de E7** — esta épica añade páginas nuevas al
   dashboard Streamlit; no reinventa auth/layout/theming.
2. **Sin lógica de negocio nueva** — los flujos delegan en repos y servicios
   existentes (`JobRepo`, `JobScorer`, `ApplicationRepo`).
3. **Re-score con Sonnet** como acción reservada de E13: el dashboard puede
   gatillar re-scoring (variante 7B del Documento A) por job individual,
   no en batch.
4. **Antigüedad como métrica de presión** — la UI debe empujar a decidir
   sobre items en cola de QA, no permitir que se acumulen indefinidamente.

### Tabla de stories

| ID | Título | Estimación | Depende de | Origen |
|----|---|---|---|---|
| E13-S01 | Página Manual Review (tier C) en dashboard | 1.5h | E7-S01 cerrada | Movida desde E07-S04 |
| E13-S02 | Comandos CLI faltantes de outreach (suite humana) | 2h | E9-S01–S05 cerradas | Subset diferido de E09-S06 |
| E13-S03 | Email matcher: prompt versionado + CLI `email stats` | 1h | E10-S04, E10-S08 cerradas | Subset diferido de E10-S04 + E10-S08 |
| E13-S04 | Página dashboard Analytics + workflow `monthly-report` | 1.5h | E11-S05, E11-S06 cerradas | Subset diferido de E11-S07 |
| E13-S05 | Audit log + compliance lite + `trivy` en CI | 2h | E2 cerrada | E12-S06 + detalle de E12-S08 |

### Definition of Done de la épica

```bash
# 1. UI: levantar el dashboard, navegar a "Manual Review"
streamlit run src/jobhunter/dashboard/streamlit_app.py
# → página lista jobs status='manual_review' con cards detalladas
# → botones funcionales: Promote to Queue / Re-score / Reject
# → indicador "X jobs esperan review, Y > 7 días sin decisión"

# 2. CLI: workflow completo de outreach disponible desde terminal
jobhunter outreach add --name "Sarah Smith" --linkedin-url "..." --company "N26"
jobhunter outreach candidates --limit 10 --market germany --min-score 4
jobhunter outreach draft <contact-id> --type A_inhouse --note "Vi su post sobre …"
jobhunter outreach sent <message-id>
jobhunter outreach replied <message-id>
jobhunter outreach list --status sent --last 14

# 3. Observabilidad email: prompt versionado + métricas CLI
ls prompts/email_matcher/v1.md  # archivo existe, prompt extraído del código
jobhunter email stats           # tasa de match, precision, costo IA, top dominios

# 4. Analytics avanzado: página dashboard + reporte mensual automático
streamlit run src/jobhunter/dashboard/streamlit_app.py
# → navegar a "Analytics": recommendations, A/B tests, false rejects, reports archive
gh workflow run monthly-report.yml
# → cron '0 8 1 * *' invoca analytics report y manda PDF por email

# 5. Audit + compliance + trivy
jobhunter audit query --since "7 days ago" --event login
# → trazabilidad de logins, mutaciones críticas, accesos a OAuth tokens
jobhunter compliance export-data --output exports/personal_data.json
jobhunter compliance delete-all --confirm-twice
trivy fs .  # scan completo de vulnerabilidades en deps + filesystem
```

---

## E13-S01 — Página Manual Review (tier C)

> **Origen:** esta story se movió desde **E07-S04** durante la verificación de
> la Épica 7 (ver `docs/Plan automatizado.../K_Backlog_Nivel_2_E7.md`). En su
> épica original quedó como placeholder de 12 líneas
> (`pages/3_🔍_Manual_Review.py` con `st.info("Placeholder: Implementation
> coming in next stories.")`). Por decisión del usuario se difirió a esta
> épica nueva en lugar de implementarse en E7.

**Como** dueño del sistema, **quiero** revisar jobs tier C ambiguos
(`status='manual_review'`), **para que** decida promover a queue o descartar
sin perder oportunidades borderline.

### Acceptance Criteria

- [ ] La página `src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py` lista
  jobs `status='manual_review'`.
- [ ] Cards más detalladas que las de **New Matches** (más contexto necesario
  para decidir):
  - JD completa (collapsible).
  - `score_data` completo en formato leíble (yellow_flags resaltados).
  - Razón principal de "manual_review" (de
    `score_data.recommendation.reason_short`).
- [ ] Acciones por job:
  - [ ] **Promote to Queue** — transiciona a `status='queued'` (entra al flujo
    normal de aplicación).
  - [ ] **Re-score** — re-ejecuta scoring con prompt actual + Sonnet 4.6
    (variante 7B del Documento A).
  - [ ] **Reject** — transiciona a `status='rejected'` con razón.
- [ ] Filtro: por antigüedad (jobs viejos en review acumulan polvo).
- [ ] Indicador: "X jobs esperan review, Y > 7 días sin decisión".

### Tasks

- [ ] Reemplazar el placeholder de
  `src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py` por la implementación
  real, similar en estructura a `pages/1_📥_New_Matches.py` pero con cards
  más densos.
- [ ] Componente reutilizable `render_manual_review_card(job)` en
  `dashboard/components.py` (o ampliar el existente `render_job_card` con un
  modo `compact=False`).
- [ ] Botón **Re-score** invoca `JobScorer` con override de modelo
  (Sonnet 4.6); mostrar diff entre el score original y el re-score si
  difieren > 10 puntos.
- [ ] Botón **Promote to Queue** llama a `JobRepo.mark_status(job.id,
  JobStatus.QUEUED)`.
- [ ] Botón **Reject** llama a `JobRepo.mark_status(job.id,
  JobStatus.REJECTED)` con captura de razón en un `st.dialog`.
- [ ] Indicador top calculado a partir de `Job.scored_at` (días desde el
  scoring inicial, no `scraped_at`).
- [ ] Test E2E mínimo en `tests/e2e/dashboard/` (`test_manual_review.py`):
  navegar a la página, ver al menos 1 card, click en "Promote to Queue",
  verificar que el job desaparece de la lista.

### Estimación: 1.5h

### Notas

- **Re-score con Sonnet** es directo del Documento A variante 7B. Si el nuevo
  score difiere significativamente, sirve como señal de que el caso es
  genuinamente ambiguo y vale empujar a `queued` con un disclaimer en notas.
- **Antigüedad como métrica:** jobs en `manual_review` > 7 días son señal de
  procrastinación. La UI debe empujar a decidir (color rojo en el indicador,
  ordenar más antiguos primero por defecto).
- **Coste del Re-score on-demand:** Sonnet a ~$0.003 por job, despreciable
  para uso individual desde dashboard.

---

## E13-S02 — Comandos CLI faltantes de outreach (suite humana)

> **Origen:** esta story rescata el subset de **E09-S06** que quedó sin
> implementar durante la verificación de la Épica 9 (ver
> `docs/Plan automatizado.../M_Backlog_Nivel_2_E9.md`). De los 8 comandos CLI
> que pedía el AC original sólo se implementaron 3 (`outreach import`,
> `outreach stats`, `outreach check-cadence`); los 6 restantes se difirieron
> a esta épica por decisión del usuario.
>
> El workflow completo está disponible desde el dashboard (E7-S05 + E9-S07),
> por lo que esta story no bloquea operación. Su valor es **paridad CLI ↔
> UI** y soporte para automatización ad-hoc desde scripts/cron del usuario.

**Como** dueño del sistema, **quiero** los 6 comandos CLI faltantes de
`jobhunter outreach`, **para que** el workflow completo (añadir contacto →
priorizar → generar draft → marcar enviado/respondido → consultar historial)
viva también en terminal sin depender del dashboard.

### Acceptance Criteria

Los 6 comandos siguen las mismas convenciones que el resto de la suite
(`typer` + `rich` para output, exit code 0 ok / 1 error, secrets vía
`Settings`). Cada uno mapea a métodos ya existentes en `OutreachRepo` o
`OutreachMessageRepo` — esta story es plumbing, no lógica nueva.

#### `outreach add`
- [ ] Flags: `--name` (required), `--linkedin-url`, `--company`, `--role`,
  `--market` (enum `OutreachMarket`), `--notes`.
- [ ] Detecta duplicado por `linkedin_url` (vía
  `OutreachRepo.find_by_linkedin_url`) y aborta con exit 1 si existe.
- [ ] Aplica scoring heurístico de E09-S04 al insertar
  (`outreach.scoring.calculate_heuristic_score`).
- [ ] Output: tabla rich con el contacto creado + `id` para uso posterior.

#### `outreach candidates`
- [ ] Flags: `--limit N` (default 10), `--market germany|eu_wide|uk|...`,
  `--min-score N` (default sin filtro).
- [ ] Ordenamiento literal del AC original: **`quality_score DESC`,
  `last_contacted_at ASC NULLS FIRST`** (prioriza alto-score
  nunca-contactado).
- [ ] Output: tabla rich con `id`, `name`, `company`, `role`, `quality_score`,
  `status`, `last_contacted_at` (humano: "hace 5 días" o "—").

#### `outreach draft <contact-id>`
- [ ] Argumento posicional: `contact_id` (UUID del contacto).
- [ ] Flags: `--type A_inhouse|B_boutique|C_senior|D_followup` (required),
  `--note TEXT` (required, ≥20 chars — misma validación que el dashboard
  E9-S07), `--language en|es` (default `en`), `--copy` (opcional, copia al
  portapapeles vía `pyperclip` o equivalente).
- [ ] **Default: NO copia al clipboard** (literal del AC original — evita
  pegar accidentalmente).
- [ ] Invoca `outreach.generator.generate_message`; persiste el resultado
  como `OutreachMessage` con `status='draft'`; muestra el body con
  `rich.markdown.Markdown`.
- [ ] Footer del output: `id` del mensaje + comando sugerido para marcar
  enviado (`jobhunter outreach sent <message-id>`).
- [ ] Si la política de 2 toques (E9-S05) bloquea la creación
  (`OutreachMessageRepo.create_draft` raise `ValueError`), el comando
  termina con exit 1 y mensaje explicativo.

#### `outreach sent <message-id>`
- [ ] Argumento posicional: `message_id` (UUID).
- [ ] Flag opcional: `--at TIMESTAMP` (ISO 8601, default: ahora).
- [ ] Invoca `OutreachMessageRepo.mark_sent`; transiciona el contacto a
  `OutreachStatus.CONTACTED` automáticamente.

#### `outreach replied <message-id>`
- [ ] Argumento posicional: `message_id` (UUID).
- [ ] Flag opcional: `--at TIMESTAMP`.
- [ ] Invoca `OutreachMessageRepo.mark_replied`; transiciona el contacto a
  `OutreachStatus.REPLIED`.

#### `outreach list`
- [ ] Flags: `--status draft|sent|replied|ghosted|discarded` (multi-select
  posible, repetible), `--contact-id UUID`, `--last N` (días, default 14).
- [ ] Output: tabla rich con `id`, `contact_name`, `template_type`, `status`,
  `created_at`, `sent_at`, `replied_at`.
- [ ] Soporta combinación: `--status sent --last 7` muestra mensajes enviados
  los últimos 7 días sin reply.

### Tasks

- [ ] Implementar los 6 comandos en `src/jobhunter/__main__.py` (sub-Typer
  `outreach_app`, mismo patrón que los 3 ya existentes).
- [ ] Helper `_format_contact_row(contact)` y `_format_message_row(msg)` en
  algún módulo compartido (p. ej. `cli/formatters.py`) — evita duplicar
  formatting entre `candidates`, `list`, y la tabla del dashboard.
- [ ] Verificar que `Settings.OUTREACH_MODEL` se respeta cuando `draft`
  invoca al generator.
- [ ] Tests CLI con `typer.testing.CliRunner` para cada comando: golden
  path + 1 caso de error (duplicado en `add`, política de 2 toques en
  `draft`, message_id inexistente en `sent`/`replied`).
- [ ] Smoke test E2E (no Playwright, sólo CLI): correr la secuencia del
  ejemplo del AC con DB seeded y verificar que cada paso funciona.
- [ ] Actualizar README o `docs/runbook.md` si es necesario para incluir
  el workflow CLI completo (era el ejemplo de la sección "Definition of
  Done" del Documento M).

### Estimación: 2h

### Notas

- **Por qué se difirió.** Durante la verificación de E9 se detectó que de
  los 8 comandos CLI del AC sólo 3 estaban implementados. El dashboard
  (E9-S07) cubre el workflow visual, así que el sistema es operativo
  end-to-end. El usuario eligió diferir vs. bloquear el cierre de E9.
- **Reuso máximo.** Cada comando es un wrapper thin sobre métodos que ya
  existen y están testeados. La complejidad real está en formatting +
  validación de inputs, no en lógica nueva.
- **`--copy` requiere dependencia opcional.** Si añadirla pesa demasiado,
  documentar el patrón "pipe a `pbcopy`/`xclip`" en lugar de añadir dep:
  `jobhunter outreach draft <id> --type A_inhouse --note "..." | pbcopy`.
- **Test E2E mínimo.** Si el smoke test resulta más caro que su valor (por
  requerir DB real + mocks de Anthropic), reducirlo a tests unitarios por
  comando con `CliRunner`.

---

## E13-S03 — Email matcher: prompt versionado + CLI `email stats`

> **Origen:** esta story rescata dos desvíos menores detectados durante la
> verificación de la Épica 10 (ver
> `docs/Plan automatizado.../N_Backlog_Nivel_2_E10.md`):
>
> 1. **De E10-S04:** el AC pedía `prompts/email_matcher/v1.md` versionado;
>    ese archivo no existe — el prompt vive inline en el código de
>    `src/jobhunter/email/matcher.py`. Inconsistente con el resto del
>    sistema (E4 scoring, E6 cover letter / ATS / CV tweaks, E9 outreach)
>    donde los prompts son `.md` versionados.
> 2. **De E10-S08:** el AC pedía CLI `jobhunter email stats` (tasa de match,
>    precision, costo IA, top dominios). El sub-Typer `email` sólo expone
>    `auth` y `poll-and-suggest`; las métricas equivalentes existen en el
>    dashboard (`MetricsService` + página de Metrics) pero no en CLI.
>
> Ambos son superficie operativa, no lógica de negocio nueva. Por decisión
> del usuario se difirieron a esta story consolidada.

**Como** dueño del sistema, **quiero** el prompt del email matcher
versionado en disco y un comando CLI con métricas de detección, **para que**
iterar sobre el prompt sea diffable en PRs (igual que el resto del sistema)
y la observabilidad del módulo `email/` no dependa exclusivamente del
dashboard.

### Acceptance Criteria

#### Parte A — Prompt versionado (rescate de E10-S04)

- [ ] Crear directorio `prompts/email_matcher/` (paralelo a
  `prompts/scoring/`, `prompts/cover_letter/`, `prompts/ats_keywords/`,
  `prompts/cv_tweaks/`, `prompts/outreach/`).
- [ ] Crear archivo `prompts/email_matcher/v1.md` con la estructura estándar
  del proyecto (`## SYSTEM` + `## USER_TEMPLATE` + `## REQUIREMENTS`),
  conteniendo el texto del prompt actualmente embebido en
  `src/jobhunter/email/matcher.py` (la rama de escalación a IA cuando
  `confidence < 0.8`).
- [ ] Reemplazar la string literal del prompt en `matcher.py` por una
  llamada a un loader (`load_prompt_template("email_matcher", "v1")` o
  similar, reutilizando el patrón de `scoring/prompt.py` /
  `outreach/templates.py`).
- [ ] El loader cachea la lectura (`functools.lru_cache`) para no leer disco
  en cada email procesado.
- [ ] Persistir `prompt_version` en `email_messages.match_reasoning` (o un
  campo específico si se prefiere) cuando la match status es `ai_matched`,
  para que cada match quede trazable a la versión del prompt que lo
  generó.
- [ ] Tests unit: el matcher produce el mismo `MatchResult` antes y después
  del refactor con la misma respuesta mockeada del LLM (regresión).

#### Parte B — CLI `email stats` (rescate de E10-S08)

- [ ] Comando `jobhunter email stats` con flag `--since "N weeks ago"`
  (default 4 semanas, alineado con `outreach stats`).
- [ ] Output (tabla rich) con las **5 secciones del AC original**:
  - Total emails procesados en la ventana.
  - **Tasa de match:** `% auto_matched`, `% ai_matched`, `% unmatched`,
    `% ignored_marketing`.
  - **Precision estimada:** `count(user_confirmed) / (count(user_confirmed)
    + count(user_rejected))` sobre los matches que el usuario revisó.
    Target ≥85%.
  - **Costo IA acumulado** del módulo email (filtrar `LLMCallRepo` por
    `purpose='email_matcher'` o el purpose que use el matcher).
  - **Top dominios** (`from_domain`) generadores de emails — útil para
    detectar marketing senders no clasificados.
- [ ] Exit code 1 si la precision cae por debajo del target (señal opcional
  para alerting en cron). Decidir en implementación si se activa por
  default o requiere flag `--strict`.
- [ ] Tests CLI con `typer.testing.CliRunner` + DB seeded con `email_messages`
  variados (3 confirmados, 1 rechazado, 2 unmatched).

### Tasks

- [ ] Crear `prompts/email_matcher/v1.md` extrayendo el prompt actual del
  código (cuidar que el formato `{placeholders}` siga vigente).
- [ ] Implementar (o reutilizar) loader de prompts en `email/matcher.py`.
- [ ] Refactor del matcher para consumir el prompt cargado, no la string
  literal.
- [ ] Implementar `email_stats` en `__main__.py` (sub-Typer `email_app`).
- [ ] Helper `_compute_email_stats(session, since)` en
  `email/orchestrator.py` o `email/stats.py` (testeable aisladamente).
- [ ] Tests unit + CLI (los descritos en los AC).
- [ ] Verificar que el dashboard E7-S06 (Metrics page) sigue funcionando —
  si comparte el helper, mejor; si no, no romperlo.

### Estimación: 1h

### Notas

- **Por qué se difirió.** Durante la verificación de E10 se detectaron como
  desvíos menores: el sistema funciona (matcher escala correctamente, las
  métricas existen en dashboard). Pero la inconsistencia con el resto del
  proyecto (prompts versionados, CLI `*-stats` por módulo) justificaba un
  cierre limpio. El usuario eligió diferir a E13 vs. bloquear E10.
- **No introduce dependencia nueva.** El loader de prompts ya existe
  patrón-wise; sólo hay que aplicarlo a `email_matcher`.
- **Test de regresión es crítico.** Si el refactor del prompt cambia el
  comportamiento del matcher (p. ej. por un `\n` distinto), las heurísticas
  del módulo se desestabilizan. El test debe usar fixtures reales de email
  + respuesta mockeada del LLM y verificar que `MatchResult` es idéntico.

---

## E13-S04 — Página dashboard Analytics + workflow `monthly-report`

> **Origen:** esta story rescata el desvío detectado durante la verificación
> de la Épica 11 (ver `docs/Plan automatizado.../O_Backlog_Nivel_2_E11.md`).
> El AC de E11-S07 pedía dos piezas que no se implementaron:
>
> 1. **Página dashboard `pages/8_📈_Analytics.py`** con 4 secciones
>    (Recommendations con quickbuttons Snooze/Acted/Ignore, A/B tests
>    activos, False rejects review, Reports archive). El slot `8_` ya está
>    ocupado por `8_🏥_Status.py` (System Health, parte de E12); esta story
>    debe colocar la página en `9_📈_Analytics.py` o renombrar el orden.
> 2. **Workflow `.github/workflows/monthly-report.yml`** con
>    `cron: '0 8 1 * *'` (día 1 de cada mes 08:00 UTC = 03:00 COT) que
>    invoque `analytics report` y mande el PDF por email automáticamente.
>
> Toda la lógica subyacente existe — `analytics/recommendations.py` produce
> las recomendaciones, `analytics/report_generator.py` genera el PDF vía
> `weasyprint`, `analytics/ab_testing.py` expone resultados, `analytics
> false-rejects` lista los promovidos manualmente. Falta sólo la **superficie
> de presentación** (UI dashboard + cron mensual).

**Como** dueño del sistema, **quiero** la página de analytics avanzado en
el dashboard y el envío mensual automático del reporte, **para que** el
ciclo de mejora continua de E11 cierre sin pasos manuales: las
recomendaciones se ven al inicio de la semana en UI, y el reporte mensual
narrativo llega por email el día 1 sin tener que invocarlo.

### Acceptance Criteria

#### Parte A — Página dashboard Analytics

- [ ] Crear `src/jobhunter/dashboard/pages/9_📈_Analytics.py` (slot `8_`
  está ocupado por `8_🏥_Status.py` de E12, evitar conflicto).
- [ ] La página requiere `require_auth()` y renderiza header + sidebar
  como las demás (`render_header()`, `render_sidebar()`).
- [ ] **Sección 1 — Recommendations:** lista paginada de
  `analytics.recommendations.get_recommendations(session)` con priority
  badges (P1/P2/P3 con colores rojo/amarillo/gris) y, por cada item, los
  3 quickbuttons literales del AC:
  - **Snooze** — marca como vista, oculta por 7 días (persistir estado en
    `notifications_sent` con `dedup_key=f"reco_snooze:{recommendation_hash}"`
    o tabla nueva `recommendation_state` si conviene).
  - **Acted on** — marca como resuelta, no aparece más.
  - **Ignore** — descarta permanentemente.
- [ ] **Sección 2 — A/B tests activos:** tabla con `name`, `variants`,
  `sample_size_per_variant`, `current_significance`, `started_at`. Click
  en una fila navega a detalle con la salida de
  `get_ab_test_results(session, name)`. Si el test está concluido o tiene
  significancia ≥0.95, muestra botón "End test" que invoca el repo de A/B
  con `--winner`.
- [ ] **Sección 3 — False rejects review:** lista paginada de jobs con
  `tier='REJECT'` y `manually_promoted_at IS NOT NULL` (datos de
  E11-S04). Cada fila con preview del job (título, empresa, snippet de
  description) + botón "Promote" que ejecuta la promoción manual
  (`JobRepo.mark_status` a `QUEUED` + insertar `application_event`).
- [ ] **Sección 4 — Reports archive:** lista de archivos en `reports/`
  (filtrar por `*.pdf` y `*.md`) ordenada por fecha descendente. Cada
  entrada con preview del primer párrafo (markdown) + botón "Download" que
  sirve el archivo via `st.download_button`.
- [ ] **Botón "Generate report"** en la cabecera de la página, dispara
  `analytics.report_generator` para el mes actual on-demand con un
  `st.spinner` mientras se ejecuta (~30-60s con Sonnet).
- [ ] **Botón "Export to PDF"** en cualquier sub-vista convierte la vista
  actual a PDF descargable usando `weasyprint`.
- [ ] Test E2E mínimo en `tests/e2e/dashboard/test_analytics_page.py`:
  navegar, ver al menos 1 recommendation, click en "Snooze", verificar
  que desaparece.

#### Parte B — Workflow `monthly-report`

- [ ] Crear `.github/workflows/monthly-report.yml`:
  - `cron: '0 8 1 * *'` literal del AC.
  - `workflow_dispatch` con input opcional `month: str` para regenerar
    un mes pasado.
  - Steps idénticos en estructura a `weekly-digest.yml` (checkout, setup
    uv, sync, composite action `setup-env` con secrets de SMTP +
    Anthropic, `uv run jobhunter analytics report --month $MONTH
    --output pdf`).
  - Después de generar el PDF, step que envía email vía `EmailNotifier`
    de E5 con el PDF adjunto (extender `EmailNotifier` si no soporta
    attachments — actualmente parece solo body multipart text/HTML).
  - Timeout: 10 minutos.
  - `concurrency: { group: monthly-report, cancel-in-progress: false }`.
  - `Alert on Failure` step usando la composite action de E8-S06.
- [ ] CLI `analytics report --send-email` opcional para invocar
  manualmente el flujo de generar+enviar (útil para testing del workflow).
- [ ] Documentar en `docs/runbook.md` cómo regenerar un reporte de un mes
  específico vía `workflow_dispatch`.

### Tasks

- [ ] Crear página Streamlit con las 4 secciones (estimado: 60-70% del
  esfuerzo total de la story).
- [ ] Componente reutilizable `render_recommendation_card(reco)` que
  encapsula priority badge + quickbuttons.
- [ ] Persistencia de estado de recommendations (snooze/acted/ignore) —
  decidir entre extender `notifications_sent` o crear tabla nueva
  `recommendation_state` (recomendado: tabla nueva para no contaminar
  `notifications_sent` con semántica distinta).
- [ ] Migration Alembic si se opta por tabla nueva.
- [ ] Workflow YAML `monthly-report.yml`.
- [ ] Extender `EmailNotifier` (E5-S04) si no soporta attachments.
- [ ] Test E2E Playwright + smoke test del workflow vía
  `workflow_dispatch`.

### Estimación: 1.5h

### Notas

- **Por qué se difirió.** Durante la verificación de E11 se detectó que la
  lógica subyacente (recommendations, report generation, A/B testing,
  false rejects) está completa y testeada, pero la superficie de
  presentación (página dashboard + cron mensual) no se construyó. El
  sistema funciona end-to-end vía CLI; lo que falta es la ergonomía
  visual.
- **Slot `8_` ocupado.** La página `8_🏥_Status.py` (Health) probablemente
  pertenece a E12. Esta story usa el slot `9_` para evitar conflicto y no
  romper el orden alfabético de Streamlit.
- **`EmailNotifier` con attachments.** Si actualmente no soporta, es ~30
  líneas extender `aiosmtplib` con `MIMEApplication` para el PDF. Tarea
  menor, pero hay que verificarla antes de la implementación.
- **Analytics page = portfolio piece.** Esta página es la cara visible
  del ciclo de mejora continua del sistema. Mostrarla en una entrevista
  (especialmente para roles AI/ML/data) es una historia poderosa: "el
  sistema se observa a sí mismo y sugiere qué cambiar".

---

## E13-S05 — Audit log + compliance lite + `trivy` en CI

> **Origen:** esta story rescata el desvío real detectado durante la
> verificación de la Épica 12 (ver
> `docs/Plan automatizado.../P_Backlog_Nivel_2_E12.md`):
>
> 1. **De E12-S06 (desvío real):** no existe modelo `AuditLog`, ninguna
>    migración de tabla `audit_log`, ningún decorator `@audit_logged`,
>    ningún CLI `audit query` ni `compliance export-data` ni `compliance
>    delete-all`. El AC pedía trazabilidad explícita de mutaciones
>    críticas (login/logout, bulk deletes, cambios de prompt versions,
>    backups/restores, rotación de secretos, acceso a OAuth tokens) —
>    ninguna está. La única "auditoría" presente es el tracking básico de
>    E12-S05 (`failed_login_attempts`/`blocked_ips`), que es para abuse
>    prevention, no audit trail completo.
> 2. **De E12-S08 (detalle menor):** `bandit` y `pip-audit` corren en CI
>    pero **falta `trivy fs .`** que el AC pedía como tercer scanner. Se
>    consolida en esta misma story por afinidad temática (security
>    surface).
>
> Por decisión del usuario se difirieron a esta story consolidada en
> lugar de bloquear el cierre de E12.

**Como** dueño del sistema, **quiero** trazabilidad completa de operaciones
sensibles + utilidades de export/erasure de datos personales + scanner
adicional `trivy` en CI, **para que** pueda responder "qué pasó y cuándo"
ante incidentes, prepare el terreno mínimo de compliance, y la superficie
de seguridad esté completa.

### Acceptance Criteria

#### Parte A — Audit log (rescate de E12-S06)

- [ ] Migration Alembic crea tabla `audit_log` con las columnas literales
  del AC original:
  - `id` UUID PK.
  - `event_type` VARCHAR (enum: `login`, `logout`, `data_access`,
    `data_mutation`, `config_change`, `secret_rotated`, `backup_created`,
    `restore_executed`, `bulk_delete`).
  - `actor` VARCHAR (`user`, `system`, `cron:workflow_name`, etc.).
  - `target_entity` VARCHAR NULLABLE (ej. `Job`, `Application`,
    `OutreachContact`).
  - `target_id` UUID NULLABLE.
  - `action` VARCHAR — verbo descriptivo.
  - `metadata` JSONB — contexto adicional.
  - `ip_address` VARCHAR NULLABLE.
  - `created_at` TIMESTAMPTZ default now().
- [ ] Índices: `(event_type, created_at DESC)`, `(actor, created_at DESC)`,
  `(target_entity, target_id)`.
- [ ] Modelo SQLAlchemy `AuditLog` en `db/models.py` + `AuditLogRepo` en
  `db/repos/audit_log.py` con `record(event_type, actor, ...)` y
  `query(filters, since, limit)`.
- [ ] **Decorator** `@audit_logged(event_type, action)` en
  `src/jobhunter/audit/decorator.py` (o módulo similar) que captura
  automáticamente el evento al ejecutar la función decorada.
- [ ] Aplicar el decorator (o llamada explícita al repo) en las
  **mutaciones críticas literales del AC**:
  - Login/logout dashboard (`dashboard/auth.py`).
  - Bulk deletes (cualquier endpoint que borre múltiples entidades).
  - Cambios de prompt versions (sería un evento futuro, dejar el hook
    listo).
  - Backups y restores (`db/backup.py`).
  - Rotación de secretos (cuando exista la herramienta CLI).
  - Acceso a OAuth tokens (descrifrado en `email/gmail_client._get_service`).
- [ ] CLI `jobhunter audit query [--since X] [--actor Y] [--event Z]
  [--limit N]` con output tabla rich.
- [ ] Página dashboard "Audit Log" — agregar como sección a `8_🏥_Status.py`
  o como sub-tab en la nueva `9_📈_Analytics.py` (E13-S04). Decisión:
  sub-tab en Analytics para no saturar Status.
- [ ] Tests unit: cada `event_type` puede registrarse y consultarse;
  decorator captura args correctamente.

#### Parte B — Compliance lite (rescate de E12-S06)

- [ ] CLI `jobhunter compliance export-data [--output PATH]` que exporta
  toda la data personal del usuario en JSON: jobs aplicados (con scores y
  cover letters), `outreach_contacts` y `outreach_messages`,
  `email_messages`, `audit_log`, `oauth_tokens` (con tokens redactados).
  Útil para "right to access" preparation.
- [ ] CLI `jobhunter compliance delete-all --confirm-twice` que borra
  TODA la data personal:
  - Pide confirmación textual: "Type 'DELETE-ALL' to confirm".
  - Pide segunda confirmación explícita.
  - Persiste el evento en `audit_log` ANTES del delete (para que la
    auditoría sobreviva al borrado).
  - Borra en orden correcto respetando FKs: `email_messages`,
    `outreach_messages`, `application_events`, `applications`,
    `outreach_contacts`, `oauth_tokens`, `notifications_sent`, `jobs`.
  - NO borra: `audit_log` (queda como única evidencia), `alembic_version`,
    `failed_login_attempts`/`blocked_ips` (security ops).

#### Parte C — `trivy` en CI (rescate de E12-S08)

- [ ] Step nuevo en `.github/workflows/ci.yml` después de `pip-audit`:
  ```yaml
  - name: Filesystem vulnerability scan with trivy
    uses: aquasecurity/trivy-action@master
    with:
      scan-type: fs
      scan-ref: .
      severity: CRITICAL,HIGH
      exit-code: '1'
  ```
- [ ] Si trivy reporta findings nuevos no triadeados, CI falla y se
  genera un issue (manual o vía workflow_dispatch).
- [ ] Documentar en `docs/runbook.md` cómo investigar findings de trivy
  y cómo añadir `.trivyignore` para falsos positivos.

### Tasks

- [ ] **Parte A:** migration `audit_log` + modelo + repo + decorator +
  aplicación cross-épica + CLI `audit query` + tests.
- [ ] **Parte B:** CLI `compliance export-data` + CLI `compliance
  delete-all --confirm-twice` con doble confirmación.
- [ ] **Parte C:** step `trivy` en `ci.yml` + `.trivyignore` inicial
  vacío + nota en runbook.
- [ ] Sub-tab "Audit Log" en página Analytics (depende de E13-S04 cerrada;
  si no, añadir directamente en `8_🏥_Status.py` como sección).
- [ ] Test E2E: registrar manual login → ver evento en `audit query`.
- [ ] Test E2E destructivo: ejecutar `compliance delete-all
  --confirm-twice` con DB seeded mínima → verificar que `audit_log` y
  `alembic_version` sobreviven.

### Estimación: 2h

### Notas

- **Por qué se difirió.** Audit log es trabajo defensivo significativo
  (~2h) cuya falta no impide operación. El sistema funciona sin él; pero
  ante un incidente real (credencial filtrada, mutación accidental), no
  hay forma de reconstruir "qué pasó". El usuario eligió diferir vs.
  bloquear E12.
- **`@audit_logged` como decorator vs llamada explícita.** El decorator
  ahorra boilerplate pero acopla el módulo a `audit/`. Para mutaciones
  muy puntuales (5-10 callsites), llamada explícita es más explícita.
  Decidir caso a caso.
- **`compliance delete-all` es nuclear.** Doble confirmación + audit
  log antes del delete + tests específicos del flujo. NUNCA disponible
  desde dashboard (sólo CLI con flags), para evitar accidentes.
- **`trivy` puede ser ruidoso.** Su DB de vulnerabilidades crece a diario.
  Setear `severity: CRITICAL,HIGH` evita el ruido de LOW/MEDIUM. El
  `.trivyignore` es para excepciones documentadas, no para silenciar
  findings legítimos.
- **`audit_log` no es GDPR compliance.** Es "compliance lite" —
  preparación mínima. Si en el futuro se abre el sistema a otros
  usuarios, requiere assessment formal.

---

## Definition of Ready para futuras stories de E13

Esta épica nace con cinco stories (`S01` rescatada de E07-S04, `S02`
rescatada de E09-S06, `S03` rescatada de E10-S04 + E10-S08, `S04`
rescatada de E11-S07, `S05` rescatada de E12-S06 + detalle de E12-S08).
Si en operación aparecen más flujos donde el humano arbitra decisiones de
baja confianza (p. ej. "applications con `next_action_due` vencido y sin
respuesta", "tier B con red flags inesperados", "outreach contacts
marcados como `replied` sin contenido") o más brechas de superficie
operativa (CLI/UI/prompts no versionados/cron faltantes/audit gaps), se
descomponen como `E13-S06`, `E13-S07`, etc., siguiendo las convenciones
del backlog.

---

**Fin Documento Q.**
