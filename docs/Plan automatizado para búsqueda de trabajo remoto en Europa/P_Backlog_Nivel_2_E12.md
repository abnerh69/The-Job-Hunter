# Documento P — Backlog Nivel 2: Descomposición de E12 (Observability, Security & Operations)

**Épica origen:** E12 — Observability, Security & Operations (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 14–17 horas (3 sesiones de medio día).

**Convenciones:** mismas que documentos E–O. ID `E12-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E12 es la **épica cross-cutting** del backlog. Su trabajo no es entregar funcionalidad nueva al usuario sino **endurecer** lo ya construido. Cuando algo se rompe en producción, esta épica determina si lo descubres en 1 hora o en 3 días. Si tus credenciales se filtran, determina si el blast radius es contenido o catastrófico. Si necesitas auditar qué pasó hace 2 meses, determina si tienes los datos.

**Principio operativo crítico:** la mayor parte de E12 son **revisiones cross-épica + automatización defensiva**, no construcción de features nuevas. Mucho del trabajo aquí es ir épica por épica verificando que cumplen estándares mínimos de logging, secret hygiene, y backup.

**Distinción clave con E11:** E11 es analytics del *negocio* (¿cuántos matches? ¿qué tasa de respuesta?). E12 es analytics del *sistema* (¿está corriendo? ¿hay leaks? ¿tenemos backups recuperables?). Ambas son P2 en el L1, pero E12 es la que evita catástrofes; E11 es la que optimiza performance.

### Decisiones técnicas clave

1. **Logging estructurado coherente cross-épica** — verificación + fixes; `structlog` configurado uniformemente, formato JSON en producción, pretty local. Mucho ya existe (E8-S07) pero E12 audita y completa.
2. **Secrets hygiene end-to-end** — `detect-secrets` baseline + pre-commit hook obligatorio, scan de history reciente, plan de rotación documentado.
3. **Backups con verificación de restauración** — no basta con `pg_dump`; un backup que nunca se restauró NO es backup. Workflow semanal que ejerce el restore.
4. **Health endpoint operacional** — `/health` y `/readiness` endpoints expuestos, consumibles por el dashboard y futuros monitores externos.
5. **Runbook completo** — el documento que tu yo del futuro va a leer cuando algo se rompa a las 11pm. Incluye 5 incidentes más probables con steps específicos.
6. **Rate limiting y abuse prevention** — el dashboard expuesto puede ser blanco de scans automatizados. Login rate-limit + IP-based blocking básico.
7. **Compliance lite** — no estamos sujetos a GDPR formalmente porque es uso personal, pero seguir buenas prácticas (data minimization, derecho a borrado) prepara el terreno si en futuro se abre a otros usuarios.
8. **Disaster recovery plan documentado** — escenarios concretos: "DB borrada", "GH Actions caído 1 semana", "credencial Anthropic filtrada". Con steps de recuperación.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E12-S01 | Logging estructurado: audit + completion | 2h | E1–E11 | con S02, S03 |
| E12-S02 | Secrets hygiene + pre-commit + history scan | 1.5h | E1 cerrada | con S01, S03 |
| E12-S03 | Backup automatizado + restore drill | 2h | E2 cerrada | con S01, S02 |
| E12-S04 | Health endpoints + status page | 2h | E7 cerrada | — |
| E12-S05 | Rate limiting + abuse prevention dashboard | 1.5h | S04 | con S06 |
| E12-S06 | Audit logs + compliance lite | 2h | E2 cerrada | con S05 |
| E12-S07 | Runbook completo + disaster recovery | 1.5h | S01–S06 | — |
| E12-S08 | Penetration test ligero + fix-all + cierre | 1.5h | S01–S07 | — |

### Camino crítico

```
E1–E11 ─→ ┬─→ S01 ─┐
          ├─→ S02 ─┤
          └─→ S03 ─┴─→ S04 ─→ ┬─→ S05 ─┐
                              └─→ S06 ─┴─→ S07 ─→ S08
```

**Tiempo serial:** ~14h. **Con paralelización (S01+S02+S03 juntos, S05+S06 juntos):** ~10h.

### Definition of Done de la épica

```bash
# Logging coherente cross-épica
jobhunter logs tail --since "1 day ago" --module E04
# → output JSON estructurado, parseable, con todos los campos esperados

# Secrets hygiene
detect-secrets scan --baseline .secrets.baseline
# → 0 nuevos secretos detectados; pre-commit instalado

# Backup + restore drill funciona end-to-end
gh workflow run backup-restore-drill.yml
# → backup creado, DB restaurada en sandbox, validación de integridad pasa

# Health endpoint
curl https://jobhunter.fly.dev/health
# → {"status": "healthy", "db": "ok", "last_pipeline_run": "2h ago", ...}

# Status page accesible públicamente (sanitizada)
open https://jobhunter.fly.dev/status

# Runbook completo
cat docs/runbook.md | wc -l
# → ≥500 líneas, cubre 10+ procedimientos comunes y 5 incidentes específicos

# Disaster recovery testeado
# Escenario: simular DB perdida → restore desde backup → sistema operacional en <30 min
```

---

## E12-S01 — Logging estructurado: audit + completion

**Como** dueño del sistema, **quiero** verificar que todos los módulos cross-épica producen logs estructurados con los mismos campos, **para que** búsquedas y filtros funcionen consistentemente y debugging sea posible 6 meses después.

### Acceptance Criteria

- [ ] Auditoría de cada módulo verificando uso de `structlog`:
  - `sources/`, `scoring/`, `application/`, `notify/`, `outreach/`, `email/`, `analytics/`, `pipeline/`, `db/`, `dashboard/`.
  - Identificar módulos que aún usan `logging` standard library directamente y refactorizar.
- [ ] Lista de campos estándar que TODOS los logs estructurados deben incluir cuando aplica:
  - `timestamp` (ISO8601, UTC).
  - `level` (DEBUG/INFO/WARNING/ERROR/CRITICAL).
  - `module` (ej. `jobhunter.scoring.scorer`).
  - `event` (verbo descriptivo, ej. `"job_scored"`, `"email_matched"`).
  - `correlation_id` (UUID que persiste a través de un workflow run completo, propagado por context vars).
  - `entity_id` cuando aplica (ej. `job_id`, `application_id`, `email_message_id`).
- [ ] `src/jobhunter/log_config.py`:
  - `configure_logging(format='json'|'pretty', level='INFO')` único punto de entrada.
  - Procesador `add_correlation_id` usando `contextvars`.
  - Filtros: redactar campos sensibles (`password`, `token`, `api_key`) con `****`.
- [ ] Helper `with_correlation_id(workflow_name)` context manager que setea correlation_id al inicio de cada workflow.
- [ ] Tests unitarios: log estructurado tiene los campos esperados; redacción funciona.
- [ ] Cada workflow YAML usa `LOG_FORMAT=json` y `JOBHUNTER_CORRELATION_ID=$GITHUB_RUN_ID`.
- [ ] CLI `jobhunter logs tail [--since X] [--module Y] [--correlation-id Z]` mejora capacidades existentes (de E8-S07) con filtros.

### Tasks

- [ ] Audit cross-épica: rutina manual recorriendo cada módulo.
- [ ] Refactor de cualquier módulo no estándar.
- [ ] Crear `log_config.py` con configure_logging.
- [ ] Implementar correlation_id propagation con contextvars.
- [ ] Filtros de redacción de secretos.
- [ ] Update workflows YAML.
- [ ] Mejorar CLI `logs tail` con filtros adicionales.
- [ ] Tests.

### Estimación: 2h

### Paralelizable con

S02, S03.

### Notas

- **Correlation ID es la magia.** Permite trazar un workflow run completo a través de todos los módulos: ingest llamó scoring que llamó notify, todo unido por un mismo correlation_id. Sin esto, debug es arqueología.
- **Redacción de secretos en logs.** Aunque structlog no debería loggear `password` ni `api_key` directamente, errores stack traces a veces los incluyen. Filtro defensivo previene leaks.
- **Cuidado con `repr()` y `f-string`.** Si un logger evalúa `f"Token: {token}"` con `level=DEBUG`, el secreto va al log incluso si está como `SecretStr` en Python. Usar siempre `logger.debug("token used", token=token)` y dejar que structlog lo redacte.

---

## E12-S02 — Secrets hygiene + pre-commit + history scan

**Como** dueño del sistema, **quiero** garantía de que no hay secretos commiteados en el repo (pasado, presente, futuro), **para que** si el repo se hace público o se filtra, no haya credenciales expuestas.

### Acceptance Criteria

- [ ] `detect-secrets` configurado:
  - Pre-commit hook obligatorio (en `.pre-commit-config.yaml`).
  - `.secrets.baseline` versionado con falsos positivos auditados.
- [ ] Scan de history reciente del repo:
  - `gh secret-scanning alerts list` revisado para alertas de GitHub.
  - `git log --all -p | detect-secrets scan --string` audita historia.
  - Si se encuentran secretos en commits pasados, **plan documentado** de rotación (NO rebase de history salvo casos extremos — para repo privado de uso personal, rotar la credencial es suficiente).
- [ ] Verificación de `.gitignore` cobertura:
  - `.env`, `.env.local`, `.env.*` (excepto `.env.example`).
  - `.local/` (CV reales, S6 datos personales).
  - `*.db`, `pgdata/`, `backups/`.
  - `secrets.json`, `credentials.json`.
  - `.streamlit/secrets.toml`.
- [ ] Plan de rotación de credenciales documentado en `docs/runbook.md`:
  - Anthropic API key.
  - Telegram bot token.
  - Gmail OAuth tokens.
  - SMTP password.
  - Postgres connection string.
  - Dashboard password.
  - OAuth encryption key (la más sensible — rotarla invalida TODOS los tokens OAuth, requiere re-auth).
- [ ] Workflow `.github/workflows/secrets-scan.yml`:
  - Schedule: weekly + on every push to main.
  - Ejecuta `detect-secrets scan` y compara con baseline.
  - Si nuevos secretos detectados, alerta Telegram + falla CI.
- [ ] Tests del workflow funcionan.

### Tasks

- [ ] Instalar y configurar `detect-secrets` en pre-commit.
- [ ] Generar baseline inicial con `detect-secrets scan > .secrets.baseline` y revisar manualmente.
- [ ] Scan de history del repo.
- [ ] Audit y completar `.gitignore`.
- [ ] Documentar plan de rotación.
- [ ] Workflow YAML.

### Estimación: 1.5h

### Paralelizable con

S01, S03.

### Notas

- **`detect-secrets` no es perfecto.** Detecta patrones (entropía alta, formatos típicos), pero un secreto custom puede pasar. Usar como defense in depth, no única defensa.
- **Plan de rotación es valioso aunque nunca lo uses.** El día que la credencial se filtre (humano error o leak en log), tener el procedimiento listo ahorra 30 min de pánico.
- **OAuth encryption key:** la más sensible. Si se filtra, atacante puede descifrar tokens OAuth Gmail. Rotar implica re-correr `jobhunter email auth`. Documentar paso a paso.

---

## E12-S03 — Backup automatizado + restore drill

**Como** dueño del sistema, **quiero** backups verificados con restore drill semanal, **para que** un día que pierda la DB pueda recuperar en <30 min con confianza.

### Acceptance Criteria

- [ ] Workflow `.github/workflows/backup-and-drill.yml`:
  - Schedule: domingos 04:00 UTC (después del digest semanal pero antes de Monday morning).
  - Steps:
    1. Conectar a DB hosted.
    2. Ejecutar `pg_dump` (script de E2-S09 mejorado).
    3. Comprimir con `gzip`.
    4. Upload a almacenamiento externo (Backblaze B2 free tier 10GB, o S3-compatible).
    5. **Restore drill:** descargar backup recién creado, restaurar a una DB Postgres ephemeral en el runner, validar integridad con queries.
    6. Si drill falla, alerta Telegram CRÍTICA.
- [ ] Settings nuevas:
  - `backup_storage_provider: Literal['b2', 's3', 'local']`.
  - `backup_storage_bucket: str`.
  - `backup_access_key: SecretStr`.
  - `backup_secret_key: SecretStr`.
  - `backup_retention_weeks: int = 12` (3 meses).
- [ ] Validaciones de integridad post-restore:
  - Tablas críticas existen (`jobs`, `applications`, `outreach_contacts`, etc.).
  - Row counts dentro de rango razonable (alerta si bajada drástica).
  - Migration version en `alembic_version` table coincide con la app actual.
  - Sample query en cada tabla crítica retorna datos.
- [ ] CLI `jobhunter backup create [--upload]` para backup manual.
- [ ] CLI `jobhunter backup restore <backup_id>` para restore manual (con confirmación interactiva — destructivo).
- [ ] CLI `jobhunter backup list` para ver backups disponibles.
- [ ] Lifecycle policy: backups >12 semanas se borran automáticamente.

### Tasks

- [ ] Cuenta Backblaze B2 (o S3 alternativo) creada, bucket configurado.
- [ ] Settings + secrets para storage.
- [ ] Workflow YAML completo.
- [ ] CLI commands.
- [ ] Lifecycle policy (puede ser bucket-level o script en workflow).
- [ ] Tests de validación post-restore.

### Estimación: 2h

### Paralelizable con

S01, S02.

### Notas

- **Backblaze B2 vs S3:** B2 free tier es 10GB storage + 1GB/día download. Un backup nuestro es ~50MB; 12 backups = 600MB. Holgado. S3 es overkill para esto.
- **Restore drill es lo que diferencia "tener backups" de "tener backups que funcionan".** Muchas empresas descubren que sus backups no son restaurables el día que necesitan restaurarlos. Drill semanal cierra ese loop.
- **Storage provider abstrasion:** si en el futuro Backblaze tiene problemas, swap a otro provider es config change, no code rewrite.

---

## E12-S04 — Health endpoints + status page

**Como** dueño del sistema, **quiero** endpoints HTTP que reportan estado del sistema y una status page pública (con datos sanitizados), **para que** monitores externos puedan integrarse y yo pueda verificar salud desde cualquier lugar.

### Acceptance Criteria

- [ ] Endpoint `/health` en el dashboard (Streamlit native page o ruta custom):
  - Response JSON con:
    ```json
    {
      "status": "healthy" | "degraded" | "unhealthy",
      "checks": {
        "db": {"status": "ok", "latency_ms": 12},
        "anthropic_api": {"status": "ok", "last_call_at": "..."},
        "telegram": {"status": "ok"},
        "gmail": {"status": "ok" | "warning" | "error"}
      },
      "metrics": {
        "last_pipeline_run_at": "2h ago",
        "active_circuit_breakers": [],
        "monthly_cost_usd": 5.40,
        "budget_pct_used": 21.6
      }
    }
    ```
  - Status code: 200 si healthy, 503 si unhealthy.
- [ ] Endpoint `/readiness`:
  - Response JSON con: ¿DB conectable? ¿Migrations al día? ¿Secrets cargados? ¿Servicios externos accesibles?
- [ ] Página pública `/status` (sin auth):
  - Muestra datos públicamente safe: uptime últimas 24h, last successful pipeline run (relative), totales de jobs (sin detalles), número de matches A-tier en última semana.
  - **NO muestra:** datos personales, contenido de jobs, costo USD, contraseñas, tokens, paths internos.
  - Pintada con CSS minimalista, sin auth requerida.
- [ ] Streamlit dashboard página `/status` (autenticada) muestra info expandida.
- [ ] Tests: cada check tiene unit test; integration tests verifican respuesta válida.

### Tasks

- [ ] Implementar `/health` y `/readiness` (Streamlit `st.sidebar` no permite endpoints custom — considerar FastAPI sidecar o Streamlit experimental APIs).
- [ ] Lógica de checks individuales encapsulada en `src/jobhunter/health/checks.py`.
- [ ] Página `/status` pública.
- [ ] Tests.

### Estimación: 2h

### Notas

- **Streamlit no es app server tradicional.** Para `/health` HTTP estándar, posible enfoque: pequeño FastAPI sidecar que sirve los endpoints + Streamlit principal. Alternativa: Streamlit con query param routing (limitado).
- **Status page pública vale.** Si en algún momento quieres mostrar el sistema a otros (entrevista, demo, blog post), `/status` sin auth con datos no-sensibles es directamente compartible.
- **Sanitization es crítica.** Status page accidentalmente leak de pieces de info personal sería embarazoso. Define conservador y revísalo.

---

## E12-S05 — Rate limiting + abuse prevention dashboard

**Como** dueño del sistema, **quiero** rate limiting en login y endpoints sensibles del dashboard, **para que** scans automatizados o intentos de brute-force no comprometan el sistema.

### Acceptance Criteria

- [ ] Rate limiting en login del dashboard:
  - Max 5 intentos fallidos en 15 min por IP → bloquear IP por 1h.
  - Max 3 intentos fallidos en 1 hora → CAPTCHA o bloqueo más largo.
  - Implementar con `slowapi` (si FastAPI sidecar) o Streamlit session-level + tabla `failed_login_attempts`.
- [ ] Tabla nueva `failed_login_attempts`:
  - `id`, `ip_address`, `attempted_at`, `user_agent`, `outcome` (success | failure).
  - Índice `(ip_address, attempted_at)`.
  - TTL automático (datos >30 días borrados con cron).
- [ ] Tabla `blocked_ips`:
  - `ip_address`, `blocked_at`, `unblock_at`, `reason`.
- [ ] Logs de seguridad estructurados con tag `security_event`:
  - Cada intento de login (success/failure).
  - Cada bloqueo de IP.
  - Cada acceso a endpoint sensible.
- [ ] Alerta Telegram si:
  - >10 intentos fallidos de login en 1 hora desde IPs distintas (posible scan).
  - Login exitoso desde IP nueva (no vista en últimos 30 días).
- [ ] CSP (Content Security Policy) headers configurados en dashboard.
- [ ] HTTPS forzado (redirect HTTP → HTTPS) — si deploy externo.

### Tasks

- [ ] Migrations.
- [ ] Lógica de rate limiting.
- [ ] Logs de seguridad.
- [ ] Alertas.
- [ ] CSP headers.
- [ ] Tests.

### Estimación: 1.5h

### Paralelizable con

S06.

### Notas

- **Para sistema de un solo usuario, esto puede parecer paranoia.** Pero el dashboard expuesto a internet es blanco constante de scans automatizados. El primer botnet que escanee tu dominio probará passwords comunes — sin rate limit, eventualmente acierta.
- **CSP headers** previenen XSS. Streamlit usa muchos inline scripts; configurar CSP requiere allowlist específica para Streamlit. Empezar con `report-only` mode antes de hacer enforcing.
- **Login desde IP nueva = warning legitimo** si trabajas desde casa siempre. Si viajas, suprimir alerta temporalmente desde CLI.

---

## E12-S06 — Audit logs + compliance lite

**Como** dueño del sistema, **quiero** audit logs completos de operaciones sensibles (mutaciones, accesos a datos, cambios de config), **para que** pueda responder "qué pasó y cuándo" si hay un incidente.

### Acceptance Criteria

- [ ] Tabla nueva `audit_log`:
  - `id` UUID PK.
  - `event_type` VARCHAR (`login`, `logout`, `data_access`, `data_mutation`, `config_change`, `secret_rotated`, `backup_created`, `restore_executed`, `bulk_delete`).
  - `actor` VARCHAR (`user`, `system`, `cron:workflow_name`, etc.).
  - `target_entity` VARCHAR NULLABLE (ej. `Job`, `Application`).
  - `target_id` UUID NULLABLE.
  - `action` VARCHAR — verbo descriptivo.
  - `metadata` JSONB — contexto adicional.
  - `ip_address` VARCHAR NULLABLE.
  - `created_at` TIMESTAMPTZ.
- [ ] Decorator `@audit_logged(event_type, action)` para mutaciones críticas.
- [ ] Aplicar audit logging en:
  - Login/logout dashboard.
  - Bulk delete operations (manual desde dashboard o CLI).
  - Cambios de prompt versions.
  - Backups y restores.
  - Rotación de secretos (cuando la herramienta CLI exista).
  - Acceso a OAuth tokens (descrifrado).
- [ ] CLI `jobhunter audit query [--since X] [--actor Y] [--event Z]` para consultar.
- [ ] Página dashboard "Audit Log" (admin-only) con filtros.
- [ ] **Compliance lite:**
  - Comando `jobhunter compliance export-data` que exporta TODA la data personal (jobs aplicados, contactos outreach, emails procesados) en JSON. Útil para "right to access" preparation.
  - Comando `jobhunter compliance delete-all --confirm-twice` que borra todos los datos personales de la DB. Útil para "right to erasure" preparation.
- [ ] Tests.

### Tasks

- [ ] Migration `audit_log`.
- [ ] Decorator + aplicación cross-épica.
- [ ] CLI commands.
- [ ] Página dashboard.
- [ ] Tests.

### Estimación: 2h

### Paralelizable con

S05.

### Notas

- **Audit logs growth:** crecen con uso. Plan: rotación a archivo cold storage tras 6 meses (opcional, para futuro).
- **Compliance lite no es compliance.** Si en futuro abres a otros usuarios, requiere assessment GDPR/CCPA real. Esta story prepara el terreno mínimo.
- **`delete-all --confirm-twice`** es destructivo. Pide confirmación textual ("Type 'DELETE-ALL' to confirm") + segunda confirmación explícita. Audit log persiste el evento incluso después de delete.

---

## E12-S07 — Runbook completo + disaster recovery

**Como** dueño del sistema (o mi yo del futuro a las 11pm cuando algo se rompe), **quiero** un runbook denso con procedimientos específicos para incidentes comunes, **para que** la respuesta sea seguir steps documentados, no improvisación bajo estrés.

### Acceptance Criteria

- [ ] `docs/runbook.md` reorganizado por secciones:
  - **1. Setup inicial** (consolidación de procedimientos esparcidos en runbooks de épicas previas).
  - **2. Operación diaria** (cómo ver estado, cómo interpretar alertas).
  - **3. Mantenimiento** (rotación de secretos, actualización de prompts, cleanup de DB).
  - **4. Troubleshooting** — los 10 problemas más probables con steps.
  - **5. Disaster recovery** — los 5 incidentes catastróficos.
- [ ] **Sección Troubleshooting cubre al menos:**
  - "Pipeline cycle no produce matches A-tier en una semana" → diagnóstico paso a paso.
  - "Costo LLM excede budget" → cómo identificar runaway, rollback.
  - "Telegram bot no envía mensajes" → checks de token, chat_id, conectividad.
  - "Dashboard no carga" → checks, restart, logs.
  - "Workflow GH Actions falla con auth error" → secret rotation, re-config.
  - "Gmail polling devuelve 0 resultados" → token refresh, scope check.
  - "Migration falla al hacer upgrade" → diagnosis, downgrade plan.
  - "Postgres connection pool exhausted" → diagnosis.
  - "DNS / Telegram bot inaccesible" → fallback plan.
  - "Dashboard expuesto recibe high traffic" → temporary lockdown.
- [ ] **Sección Disaster Recovery cubre:**
  - **DR1: DB perdida o corrupta.** Steps: identificar último backup → download → restore → verificar integridad → re-correr migrations si necesario → resume operations. Target: <30 min.
  - **DR2: Credenciales filtradas (Anthropic, Telegram, etc.).** Steps: revocar inmediatamente → generar nuevas → actualizar GH Secrets → re-deploy → audit logs para detectar si hubo abuso. Target: <1 hora.
  - **DR3: Repo comprometido.** Steps: fork lockdown → audit history → rotar TODOS los secretos como precaución → re-evaluar `.gitignore` → notificar a Anthropic si Anthropic key estaba comprometida.
  - **DR4: GH Actions caído >24h.** Steps: ejecutar workflows manualmente desde local → docker run con secretos locales → fallback temporal.
  - **DR5: Anthropic API caída prolongada.** Steps: pause workflows que dependen de scoring → switch a modo "ingest only" → resume cuando vuelva.
- [ ] Cada disaster scenario tiene **checklist específico** (no narrativa) y **comando exacto** cuando aplica.
- [ ] **Drill ejecutado:** al menos DR1 (DB recovery) ejecutado manualmente y documentado el tiempo real que tomó.
- [ ] Runbook revisable: `mkdocs` o servir como página estática.

### Tasks

- [ ] Reorganizar runbook existente.
- [ ] Escribir cada procedimiento de troubleshooting (research o experiment para verificar steps).
- [ ] Escribir cada DR scenario.
- [ ] Ejecutar DR1 drill, medir tiempo, ajustar.
- [ ] (Opcional) Configurar mkdocs para serving.

### Estimación: 1.5h

### Notas

- **Runbook que no se ejerce decae.** Drill DR1 cada trimestre asegura que steps siguen siendo válidos.
- **Specificity wins.** "Restart the service" no ayuda a las 11pm. "Run `gh workflow run pipeline-cycle.yml --field skip-step=ingest`" sí.
- **Runbook como portfolio piece.** Un runbook denso y bien estructurado en un repo público es señal de senioridad.

---

## E12-S08 — Penetration test ligero + fix-all + cierre

**Como** dueño del sistema, **quiero** un sweep final de seguridad antes de declarar el sistema completo, **para que** issues conocidos no acaben en bugs descubiertos por terceros.

### Acceptance Criteria

- [ ] **Penetration test ligero** (no necesita ser profesional, autoejecutado):
  - Ejecutar `bandit -r src/` para vulnerabilidades comunes en código Python.
  - Ejecutar `safety check` o `pip-audit` para CVEs en dependencias.
  - Ejecutar `trivy fs .` para escaneo más amplio.
  - Manual checks:
    - SQL injection en queries (verificar uso uniforme de SQLAlchemy parametrized queries, no string concatenation).
    - XSS en dashboard (Streamlit auto-escapes pero verificar custom HTML rendering).
    - CSRF en mutations (Streamlit no expone forms tradicionales pero verificar).
    - Path traversal en file operations (CV variant loader, etc.).
    - Insecure deserialization (uso de `pickle`, `yaml.load` sin SafeLoader).
- [ ] Lista de findings priorizada:
  - **Critical:** fix antes del cierre.
  - **High:** fix antes del cierre.
  - **Medium:** create issue, fix en próxima iteración.
  - **Low:** documentar como tech debt.
- [ ] Fix de todos críticos y altos.
- [ ] **Verificación final cross-épica:**
  - Todas las 12 épicas tienen tag `vN.0` correspondiente.
  - CI verde en `main`.
  - 7 días consecutivos de operación con tasa de éxito ≥95% en workflows.
  - Tests con coverage global ≥75%.
  - `docs/` completo: arquitectura, data model, runbook, prompt design, ADRs (Architectural Decision Records).
- [ ] **Tag final del proyecto:** `v1.0.0`.
- [ ] **README.md actualizado** con badges de status, captura del dashboard, link al status page público.

### Tasks

- [ ] Ejecutar `bandit`, `pip-audit`, `trivy`.
- [ ] Manual checks en lista.
- [ ] Triage de findings.
- [ ] Fix de críticos/altos.
- [ ] Verificación cross-épica.
- [ ] Tag `v1.0.0`.
- [ ] README final.

### Estimación: 1.5h

### Notas

- **`bandit`/`pip-audit` son obligatorios para cualquier proyecto Python público.** Configurar en CI también para que cada PR los ejecute.
- **`v1.0.0` es psicológicamente significativo.** Marca el cierre de la fase de construcción. A partir de aquí, cualquier change es maintenance/feature, no construcción inicial.

---

## Definition of Ready para... ¿qué sigue?

E12 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con coverage ≥75% global.
- [ ] DR1 drill ejecutado exitosamente.
- [ ] Runbook denso publicado (`docs/runbook.md`).
- [ ] `bandit`, `pip-audit`, `trivy` integrados en CI sin findings críticos.
- [ ] **Sistema operacional estable durante 14 días sin incidentes mayores.**
- [ ] Tag `v1.0.0` creado.

🎉 **PROYECTO COMPLETO.** 

A partir de aquí: **maintenance, A/B testing de prompts (E11), iteración basada en métricas reales, y eventual handoff** (si alguna vez se decide abrir a otros usuarios o hacer open source).

---

## Anexo: Lo que NO está en E12

Hay temas adyacentes a observability/security que **NO** están en esta épica intencionalmente:

1. **Hosted observability (Datadog, Sentry, New Relic).** Para sistema de un solo usuario, GitHub artifacts + structured logs + alertas Telegram son suficientes. Si crece a multi-tenant, sí.

2. **Tracing distribuido (OpenTelemetry).** Sistema es mostly monolithic; no hay 5 microservicios que correlacionar.

3. **WAF (Web Application Firewall) tipo Cloudflare.** Si el dashboard se expone públicamente con tráfico real, sí. Para uso personal con tailscale o IP allowlist, no.

4. **SOC 2 / ISO 27001 compliance.** Para uso personal no aplica. Si en futuro se ofrece como SaaS, requeriría.

5. **Bug bounty program.** Mismo razonamiento — no aplica para sistema personal.

**Si rinde:** la decisión consciente es scope mínimo viable. E12 lo cubre.

---

## Anexo: ¿Cuándo NO ejecutar E12?

Mismo principio que E11: si el sistema solo va a operar 1-2 meses (búsqueda corta, oferta rápida), E12 puede saltarse parcialmente:

- **Mantener:** S02 (secrets hygiene) y S03 (backups). Esos previenen catástrofes.
- **Posponer:** S04 (status page), S05 (rate limiting), S06 (compliance), S08 (pen test).

**Decision rule:**
- Sistema personal, uso <2 meses: solo S02 + S03 + runbook básico de S07.
- Sistema personal, uso >2 meses: épica completa.
- Sistema con plan de hacer público o multi-usuario: épica completa + considerar adicionales fuera de scope.

---

## Anexo: ADRs (Architectural Decision Records)

A lo largo del proyecto hemos tomado ~50+ decisiones arquitectónicas explícitas (recogidas en los anexos de cada documento). Como cierre del proyecto, vale formalizarlas en `docs/adr/`:

- `ADR-001-streamlit-over-fastapi-vue.md`
- `ADR-002-postgres-over-sqlite.md`
- `ADR-003-gh-actions-over-airflow.md`
- `ADR-004-haiku-for-scoring-opus-for-cover-letters.md`
- `ADR-005-no-auto-apply-no-auto-send.md`
- `ADR-006-prompt-versioning-in-git.md`
- `ADR-007-privacy-first-email-storage.md`
- `ADR-008-heuristic-over-llm-for-recommendations.md`
- ...

Estos son **portfolio piece extraordinario**. Cualquier reviewer técnico va a apreciar el rigor de tener decisiones arquitectónicas documentadas como ADRs.

**Esto puede ser una story-mini de cierre opcional.** No la añado formal a E12 porque es trabajo de redacción, no de código. Pero recomendado.

---

**Fin Documento P. Fin del backlog Nivel 2 del proyecto Job-Hunter-EU.**
