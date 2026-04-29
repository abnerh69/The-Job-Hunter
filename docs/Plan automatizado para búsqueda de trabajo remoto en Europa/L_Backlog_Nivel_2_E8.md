# Documento L — Backlog Nivel 2: Descomposición de E8 (Scheduling & Automation)

**Épica origen:** E8 — Scheduling & Automation (Documento D).
**Tamaño épica:** S (≤1 día).
**Total stories:** 7.
**Estimación total:** 7–9 horas (un día de trabajo enfocado).

**Convenciones:** mismas que documentos E–K. ID `E08-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E8 es **el cierre del MVP P0**. Hasta aquí todo se ha invocado manualmente (`jobhunter ingest`, `score`, `notify dispatch`). E8 mete los crons que orquestan el sistema desatendido y, sobre todo, mete las **alertas operativas** — sin alertas, un workflow caído es invisible hasta que ya pasaron días sin matches.

**Decisión arquitectónica clave** (del Documento B §9): **GitHub Actions sobre Airflow** para el cron. Para 4-5 jobs/día de un sistema personal, GH Actions es gratis, sin server que mantener, y los logs son persistentes. Si en el futuro el sistema crece a DAGs complejos con dependencias, migrar a Airflow es trivial.

### Decisiones técnicas clave

1. **GitHub Actions con cron schedule** — gratis para repos personales, ~2000 min/mes free tier es muchísimo más de lo que necesitamos.
2. **Pipeline orquestado en un script Python**, no en YAML — `jobhunter pipeline run-cycle` ejecuta ingest+score+dispatch en orden con manejo de errores. YAML solo dispara y reporta.
3. **State persisted en la DB**, no en el filesystem del runner — runners son efímeros, cada job parte de cero. Circuit breakers, last-run timestamps, todo en Postgres.
4. **Alertas en Telegram cuando algo falla** — no email (volumen alto de failure alerts ahogaría inbox). Telegram con prefix "🚨" para diferenciar de matches.
5. **DB hosted en Neon free tier o Supabase** — los runners de GH Actions son efímeros, no pueden tener Postgres local persistente. Connection string en GH Secrets.
6. **Idempotencia es no-negociable** — cada workflow debe ser seguro de re-correr. Esto ya está cubierto por las épicas previas (E3 dedup_url_hash, E4 status='new', E5 notifications_sent UNIQUE), E8 lo verifica end-to-end.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E08-S01 | DB hosted setup (Neon/Supabase) + secrets | 1h | E2 cerrada | — |
| E08-S02 | `jobhunter pipeline run-cycle` orquestador | 1.5h | E3,E4,E5 cerradas | — |
| E08-S03 | Workflow: pipeline cycle (cada 8h) | 1h | S01, S02 | con S04 |
| E08-S04 | Workflow: digest semanal (domingos) | 0.5h | S01, E5-S06 | con S03 |
| E08-S05 | Workflow: follow-up checks (diario) | 1h | S01, E2 | con S03, S04 |
| E08-S06 | Sistema de alertas de fallo | 1.5h | S03–S05 | — |
| E08-S07 | Logs estructurados + observabilidad | 1.5h | S03–S05 | — |

### Camino crítico

```
E2,E3,E4,E5 ─→ S01 ─→ S02 ─→ ┬─→ S03 ─┐
                              ├─→ S04 ─┼─→ S06 ─→ S07
                              └─→ S05 ─┘
```

**Tiempo serial:** ~8h. **Con paralelización (S03/S04/S05 juntos, S06/S07 juntos):** ~6h.

### Definition of Done de la épica

```bash
# Sistema corre desatendido durante 7 días sin intervención manual
# Verificable por:
gh run list --workflow=pipeline-cycle.yml --limit=21  # ~21 ejecuciones en 7 días
# Todas verde (o fallos identificados con alerta enviada)

# Comportamiento esperado tras 7 días:
# - 100+ jobs ingestados
# - 50+ jobs scoreados
# - X notificaciones tier-A enviadas a Telegram
# - 1 digest semanal recibido en email
# - Si hubo fallos, recibí alerta en Telegram en <1 hora
```

---

## E08-S01 — DB hosted setup + secrets

**Como** dueño del sistema, **quiero** la base de datos accesible desde GitHub Actions con credenciales seguras, **para que** los workflows puedan operar contra una DB persistente sin depender de mi máquina local.

### Acceptance Criteria

- [ ] Provider seleccionado: **Neon** (recomendado) o **Supabase**, ambos free tier.
- [ ] Proyecto creado en el provider con region cercana (US East para Colombia ≈ baja latencia).
- [ ] Connection string capturado.
- [ ] Schema migrado: `alembic upgrade head` corrido contra la DB hosted desde local.
- [ ] Secrets configurados en GitHub:
  - `DATABASE_URL_PROD` (connection string completa).
  - `ANTHROPIC_API_KEY` (production key).
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
  - `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO_EMAIL`.
  - `DASHBOARD_PASSWORD`.
- [ ] `.github/actions/setup-env/action.yml` (composite action) que setea env vars desde secrets — DRY entre los 3+ workflows.
- [ ] Documentado en `docs/runbook.md`:
  - Setup de Neon/Supabase paso a paso.
  - Cómo rotar secrets si se filtran.
  - Cómo migrar de provider si rinde.
- [ ] Test manual: workflow dummy que conecta a la DB hosted desde GH Actions y ejecuta `SELECT 1`.

### Tasks

- [ ] Crear cuenta en Neon (https://neon.tech) si no se tiene.
- [ ] Crear proyecto, capturar `DATABASE_URL`.
- [ ] Correr `alembic upgrade head` apuntando a la DB hosted.
- [ ] Configurar GH Secrets vía CLI: `gh secret set DATABASE_URL_PROD --body "..."`.
- [ ] Crear composite action `setup-env` en `.github/actions/setup-env/action.yml`.
- [ ] Workflow dummy `.github/workflows/test-connection.yml` para verificar.
- [ ] Documentar en runbook.

### Estimación: 1h

### Notas

- **Neon vs Supabase:** Neon free tier es 0.5 GB storage + autoscale; Supabase free tier es 500MB + más features. Para este proyecto (1000 jobs/mes ≈ 100MB), ambos sobran. Neon tiene menos features = menos cosas que romperse. **Recomendación: Neon.**
- **Connection pooling:** Neon ofrece pooler endpoint (`-pooler` en URL). Útil para workflows efímeros que abren/cierran conexiones rápido.
- **Backup:** ambos providers hacen backups automáticos free tier. Aún así, mantener `scripts/backup_db.sh` (de E2-S09) corriendo semanalmente.

---

## E08-S02 — `jobhunter pipeline run-cycle` orquestador

**Como** dueño del sistema, **quiero** un comando único que ejecute ingest → score → dispatch en secuencia con manejo de errores, **para que** los workflows YAML solo lo invoquen y la lógica viva en código testeable.

### Acceptance Criteria

- [ ] Comando CLI `jobhunter pipeline run-cycle` que ejecuta:
  1. `ingest` (de E3-S08) para todas las fuentes.
  2. `score` (de E4-S07) para jobs nuevos.
  3. `notify dispatch` (de E5-S07) para tier-A no notificados.
- [ ] Cada paso captura su `Report` (IngestionReport, ScoringBatchReport, DispatchReport).
- [ ] Si un paso falla, los siguientes se ejecutan igual (excepto si la falla es DB-related). Resilience > "fail-fast" en operación desatendida.
- [ ] `RunCycleReport` (Pydantic) consolida los 3 reports + `started_at`, `finished_at`, `total_duration_ms`, `overall_status` (success/partial_failure/total_failure).
- [ ] Output a stdout: tabla rich con resumen + JSON al final (machine-readable para que GH Actions lo capture).
- [ ] Exit code:
  - `0` si todo OK o partial failure (workflow marca como ⚠️ pero verde).
  - `1` solo si total failure (DB caída, etc.) — workflow falla en rojo.
- [ ] Flag `--skip-step STEP` para debug (ingest/score/notify).
- [ ] Tests con sub-componentes mockeados.

### Tasks

- [ ] Crear `src/jobhunter/pipeline/__init__.py` y `src/jobhunter/pipeline/run_cycle.py`.
- [ ] Implementar `async run_cycle() -> RunCycleReport`.
- [ ] CLI command en `cli.py`: `jobhunter pipeline run-cycle`.
- [ ] Output dual: human (rich) + machine (JSON al stderr o último bloque stdout).
- [ ] Tests con mocks.

### Estimación: 1.5h

### Notas

- **Por qué orquestador en Python, no en YAML.** YAML está OK para definir steps, pero la lógica de "si ingest falló pero scoring tiene jobs nuevos del último cycle, igual scoréalos" es código de aplicación. Mantener orquestación en Python permite testear sin GH Actions.
- **Output JSON al final** es para que el workflow capture la métrica y la pinte en el summary. Útil para detectar tendencias de un vistazo.

---

## E08-S03 — Workflow: pipeline cycle (cada 8h)

**Como** dueño del sistema, **quiero** un workflow que dispare el ciclo completo cada 8 horas, **para que** el sistema descubra y notifique matches en near-real-time.

### Acceptance Criteria

- [ ] `.github/workflows/pipeline-cycle.yml` con:
  - Schedule cron: `'0 */8 * * *'` (cada 8h: 00:00, 08:00, 16:00 UTC = 19:00, 03:00, 11:00 COT).
  - Trigger manual (`workflow_dispatch`) con inputs opcionales (`limit`, `source`).
  - Job único `run-cycle` con steps:
    1. Checkout.
    2. Setup uv + Python.
    3. `uv sync --frozen`.
    4. Composite action `setup-env` (de S01).
    5. `uv run jobhunter pipeline run-cycle`.
    6. Si falla, post a Telegram (de S06).
  - Timeout: 30 minutos.
  - `concurrency: pipeline-cycle` con `cancel-in-progress: false` (si un run anterior tarda, esperar; no cancelar).
- [ ] Workflow corre exitosamente tras commit a main.
- [ ] Logs persisten en Actions tab por 90 días (default GH).
- [ ] Métrica visible: tiempo medio de ejecución del cycle.

### Tasks

- [ ] Crear el workflow YAML.
- [ ] Probar con `workflow_dispatch` manual antes de esperar al cron.
- [ ] Verificar que el primer cron-triggered run sea exitoso.
- [ ] Documentar en runbook: cómo ver logs, cómo disparar manualmente.

### Estimación: 1h

### Paralelizable con

S04, S05.

### Notas

- **Schedule UTC:** GitHub Actions usa UTC. `*/8` significa cada 8h pero el runner puede tardar 5-15 min en arrancar el cron (no hay SLA). Aceptable para nuestro caso.
- **`cancel-in-progress: false`** — si un run de las 16:00 sigue corriendo cuando llega el de las 00:00, ambos completan en serie. Evita race conditions sobre la misma DB.
- **3 corridas por día** = ~9000 minutes/mes peor caso (run de 30 min × 3 × 30 días). Free tier es 2000 min/mes. **Pero** un cycle típico debe tomar 5-10 min, no 30. Si rinde, ~900 min/mes.

---

## E08-S04 — Workflow: digest semanal (domingos)

**Como** dueño del sistema, **quiero** el digest semanal disparado automáticamente los domingos al mediodía, **para que** reciba el resumen sin pensar.

### Acceptance Criteria

- [ ] `.github/workflows/weekly-digest.yml` con:
  - Schedule cron: `'0 17 * * 0'` (domingos 17:00 UTC = 12:00 COT).
  - Trigger manual.
  - Steps idénticos a S03 pero ejecutando `uv run jobhunter notify digest --send`.
  - Timeout: 5 minutos.
- [ ] Digest llega al inbox los domingos.

### Tasks

- [ ] Crear workflow YAML.
- [ ] Probar manualmente.
- [ ] Verificar primer envío automático.

### Estimación: 0.5h

### Paralelizable con

S03, S05.

### Notas

- **Domingo 12:00 COT** elegido para que esté listo cuando reviso el café del domingo. Si prefieres otro horario, ajustar cron.

---

## E08-S05 — Workflow: follow-up checks (diario)

**Como** dueño del sistema, **quiero** un workflow diario que detecte aplicaciones que requieren follow-up o que están ghosted, **para que** el sistema empuje a actuar antes de que se pierdan oportunidades.

### Acceptance Criteria

- [ ] `.github/workflows/followup-checks.yml` con:
  - Schedule cron: `'0 14 * * *'` (diario 14:00 UTC = 09:00 COT).
  - Trigger manual.
  - Steps ejecutan `uv run jobhunter pipeline check-followups`.
- [ ] Comando CLI nuevo `jobhunter pipeline check-followups` que:
  1. Ejecuta `ApplicationRepo.list_pending_followups(today)` (de E2-S07).
  2. Ejecuta `ApplicationRepo.list_ghosted_candidates(today)` y los marca como ghosted automáticamente (status='ghosted', evento creado).
  3. Si hay follow-ups pendientes, manda notificación Telegram con lista compacta.
- [ ] Refresh de `weekly_metrics` materialized view tras checks (rápido, hace que dashboard tenga data fresca para la mañana).
- [ ] Tests del comando con DB seeded.

### Tasks

- [ ] Implementar `check-followups` en `pipeline/run_cycle.py` (función separada).
- [ ] CLI command.
- [ ] Workflow YAML.
- [ ] Tests.

### Estimación: 1h

### Paralelizable con

S03, S04.

### Notas

- **Auto-marcar ghosted en lugar de solo notificar.** Decisión: si han pasado 21 días sin respuesta, es realista llamar al spade un spade. Mantener en `applied` indefinidamente distorsiona métricas. Usuario puede revertir manualmente desde dashboard si fue prematuro.
- **Telegram notification con lista compacta:** "💡 3 follow-ups pendientes hoy: [ACME Corp, BetaTech, Gamma Inc]. Ver dashboard."

---

## E08-S06 — Sistema de alertas de fallo

**Como** dueño del sistema, **quiero** alertas inmediatas en Telegram cuando un workflow falla, **para que** un sistema caído no sea invisible durante días.

### Acceptance Criteria

- [ ] Composite action `.github/actions/alert-on-failure/action.yml` que:
  - Detecta si steps anteriores fallaron (`if: failure()`).
  - Llama a la API de Telegram directamente con `curl` (no requiere Python; más simple en YAML).
  - Mensaje incluye: nombre del workflow, link al run, primeras líneas del error log.
- [ ] Aplicado en los 3 workflows (S03, S04, S05) como último step.
- [ ] Comando CLI `jobhunter health-check` que verifica:
  - Última corrida exitosa de pipeline-cycle (alerta si > 16h).
  - Última corrida exitosa de followup-checks (alerta si > 36h).
  - Estado de circuit breakers (alerta si 2+ fuentes abiertas).
  - Costo LLM mensual (alerta si > 80% del budget).
  - Cualquier alerta dispara mensaje Telegram.
- [ ] `.github/workflows/health-check.yml` que ejecuta `health-check` cada 4 horas.
- [ ] Anti-spam: si la misma alerta ya se envió en las últimas 6 horas, no re-enviar (usa tabla `notifications_sent` con `dedup_key='health_check:{alert_type}:{date_hour}'`).

### Tasks

- [ ] Crear composite action `alert-on-failure`.
- [ ] Aplicarla en los 3 workflows existentes.
- [ ] Implementar `jobhunter health-check`.
- [ ] Workflow `health-check.yml`.
- [ ] Lógica anti-spam.
- [ ] Test manual: forzar un fallo en cycle (ej. credencial DB inválida) → verificar que llegó alerta.

### Estimación: 1.5h

### Notas

- **`curl` directo a Telegram desde YAML** es más simple que invocar Python para esto. Menos cosas que pueden fallar (si Python falla, ¿cómo enviarías la alerta?).
- **Dual-track de alertas:** las de `alert-on-failure` cubren "el workflow no completó". Las de `health-check` cubren "completó pero el resultado es preocupante" (ej. circuit breaker abierto, budget al 90%). Complementarias.
- **Anti-spam crítico.** Sin él, una DB caída a las 03:00 envía alerta cada 8h hasta que se resuelva = 6+ alertas en 24h, ruido.

---

## E08-S07 — Logs estructurados + observabilidad

**Como** dueño del sistema, **quiero** logs estructurados (JSON) capturados como artifacts en cada workflow run, **para que** debug post-mortem sea posible sin necesidad de hosted log service.

### Acceptance Criteria

- [ ] `structlog` configurado consistentemente en todo el sistema (verificación cross-épica).
- [ ] Logs en JSON cuando `LOG_FORMAT=json` env var está set; pretty-print cuando no (default local: pretty).
- [ ] Workflows configuran `LOG_FORMAT=json` y redirigen stdout a `pipeline-{run_id}.jsonl`.
- [ ] Step "Upload logs" en cada workflow sube el archivo como artifact (retención 30 días).
- [ ] CLI command `jobhunter logs tail [--since DATE]` que descarga últimos artifacts y muestra logs filtrables.
- [ ] Métricas clave exportadas como JSON Summary en Action Summary:
  - Pipeline cycle: jobs ingestados, scoreados, notificados, costo LLM, duración.
  - Health check: status (green/yellow/red), alertas activas.
- [ ] Action Summary visible en GitHub UI tras cada run (con tablas markdown).

### Tasks

- [ ] Verificar `structlog` configurado uniformemente en todos los módulos.
- [ ] Settings: `log_format: Literal['json', 'pretty'] = 'pretty'`.
- [ ] Configurar workflows con `LOG_FORMAT=json` + redirect stdout.
- [ ] Step `actions/upload-artifact@v4` con archivo de logs.
- [ ] Implementar `jobhunter logs tail` (descarga último artifact via `gh run download`).
- [ ] Action Summary con `$GITHUB_STEP_SUMMARY`.
- [ ] Documentar en runbook: cómo descargar logs, cómo investigar un fallo.

### Estimación: 1.5h

### Notas

- **No usar hosted logging (Datadog, Sentry, etc.)** — overkill para sistema personal. GitHub artifacts + CLI download es suficiente.
- **Action Summary** es la pantalla que ves al hacer click en un run. Markdown render: tablas, links, métricas. Hace los runs auto-explicativos.

---

## Definition of Ready para E9

E8 cerrada cuando:

- [ ] Las 7 stories tienen AC ✅.
- [ ] Sistema corre desatendido durante 7 días con tasa de éxito ≥95%.
- [ ] Al menos 1 fallo simulado ha disparado alerta Telegram correctamente.
- [ ] Digest semanal recibido al menos una vez.
- [ ] DB hosted en producción con backup verificado.
- [ ] `docs/runbook.md` documenta los 3 workflows + cómo investigar fallos.
- [ ] Tag `v0.8.0` creado.
- [ ] **MVP P0 oficialmente cerrado.** 🎉

A partir de aquí: épicas P2 (E9 Outreach, E10 Gmail, E11 Analytics, E12 Observability avanzada) son optativas. Si tras 4 semanas operando el MVP la búsqueda da fruto, quizás nunca se construyan — y está bien.

---

## Anexo: ¿Por qué no Airflow?

Tentación: usar Airflow, "más profesional", herramienta que conoces (CV menciona Airflow). Razones para resistirla:

1. **Operación:** Airflow requiere webserver + scheduler + DB de metadata. Hosting = $20-30/mes mínimo en Fly.io o tu VPS. GH Actions = $0.
2. **Escala:** Airflow brilla con 50+ DAGs y dependencias complejas. Tenemos 3 workflows lineales.
3. **Observabilidad:** Airflow UI es buena, pero GH Actions tiene UI nativa, logs persistentes, alertas integradas.
4. **Migración futura:** si el sistema crece a múltiples usuarios, multi-tenant, DAGs complejos — migrar a Airflow es ~2 días de trabajo. Mantener Airflow desde día 1 = 2 días + carga operativa permanente.

**Excepción legítima:** si ya tienes una instancia de Airflow corriendo para otros proyectos, integrar es marginal. Pero standalone Airflow para esto = sobre-ingeniería.

---

## Anexo: ¿Por qué no Render/Railway/Fly.io para correr el sistema completo?

Otra tentación: deployar el sistema como contenedor permanente (FastAPI server + worker) en lugar de cron jobs. Razones para resistirla en MVP:

1. **Estado idle:** el sistema está esperando 99% del tiempo. Pagar por compute idle es desperdicio.
2. **Costo:** Fly.io free tier es generoso pero limitado; Railway gratis se acabó. Cron en GH Actions = gratis con margen.
3. **Restart cleanliness:** runners efímeros nunca acumulan estado raro. Un servidor de larga duración eventualmente tiene memory leaks, conexiones huérfanas, etc.
4. **Logs:** Action runs son logs persistentes naturales. Servidores requieren stack de logging adicional.

**Excepción:** el dashboard (E7) sí puede ir a Fly.io porque debe estar accesible 24/7. Pero los workflows del sistema son cron por naturaleza.

---

**Fin Documento L.**
