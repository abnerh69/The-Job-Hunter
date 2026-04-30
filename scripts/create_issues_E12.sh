#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E12 — Observability, Security & Operations
# =============================================================================
# Requisitos: gh (GitHub CLI) instalado y autenticado (`gh auth login`)
# y jq instalado.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# ⚙️ CONFIGURACIÓN DEL REPOSITORIO Y PROYECTO
# ---------------------------------------------------------------------------
OWNER="Informatica-ASHware"
REPO="Job-Hunter-EU"
FULL_REPO="${OWNER}/${REPO}"
PROJECT_NUMBER="2"
PROJECT_ID="PVT_kwDOEBSEkc4BV46-"

# ---------------------------------------------------------------------------
# 🗂️ IDs DE LOS CAMPOS DEL PROYECTO
# ---------------------------------------------------------------------------
FIELD_EPIC="PVTSSF_lADOEBSEkc4BV46-zhRRYn4"
FIELD_PRIORITY="PVTSSF_lADOEBSEkc4BV46-zhRRYpk"

# ---------------------------------------------------------------------------
# 🎯 OPTION IDs — Single-select fields
# ---------------------------------------------------------------------------
# Epic
OPT_EPIC_E12="37c62c87"     # E12-Observability

# Priority
OPT_PRIORITY_P0="6f783caf"  # P0-MVP Critical
OPT_PRIORITY_P1="72f5e96b"  # P1-MVP Desirable
OPT_PRIORITY_P2="4a355e1b"  # P2-Post-MVP

# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SUCCESS_COUNT=0
FAIL_COUNT=0

# Definir el bloque de texto (El prompt ligero)
# Usamos un identificador único al principio para evitar duplicados en el futuro.
WARNING_TEXT=$(cat << 'EOF'
> [!WARNING]
> **REGLA CRÍTICA DE CALIDAD PARA PULL REQUESTS**
>
> Como agente, TIENES PROHIBIDO crear un Pull Request (PR) o dar por finalizada una tarea de código sin antes validar la calidad del código localmente.
>
> ANTES de interactuar con GitHub para crear un PR, DEBES:
>
> 1. Ejecutar el script de validación ligera en la terminal:
>    `bash tools/light_pre_pr_check.sh`
> 2. Analizar el resultado:
>    - Este script valida Linter (Ruff), Formato (Ruff format) y Tipos estáticos (Mypy).
> 3. SI EL SCRIPT FALLA (exit code != 0):
>    - Detente. NO crees el PR.
>    - Lee el error en la terminal (problemas de tipado, variables no usadas, mal formato, etc.).
>    - Corrige el código y vuelve al paso 1.
> 4. SI EL SCRIPT ES EXITOSO (exit code == 0):
>    - Tienes luz verde para hacer el commit final, pushear los cambios y crear el Pull Request.
>
> Esta regla es estricta. Todo el código subido debe cumplir con las convenciones del proyecto validadas por las herramientas de CI incluidas en el script.

---

EOF
)

# ---------------------------------------------------------------------------
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + observability/security specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **Logging coherente:** Toda lógica nueva usa `structlog` (no `logging` standard library directo) con campos estándar (`timestamp`, `level`, `module`, `event`, `correlation_id`).
6. **Secrets hygiene:** Pre-commit con `detect-secrets` pasa; ninguna credencial commiteada al repo.
7. **Audit trail:** Operaciones sensibles (mutaciones, accesos a datos críticos, cambios de config) generan entry en `audit_log`.
8. **Disaster recovery awareness:** Si la story añade un componente crítico (DB tabla, servicio externo), se actualiza `docs/runbook.md` con procedimiento de recovery.
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** `docs/runbook.md` actualizado para procedimientos manuales; `docs/adr/` actualizado si la story implica decisión arquitectónica nueva.'

# ---------------------------------------------------------------------------
# 🛠️ FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

create_issue() {
    local title="$1"
    local body="$2"
    local labels="$3"
    local opt_epic="$4"
    local opt_priority="$5"

    echo -e "${BLUE}Creando issue:${NC} $title"

    local issue_url
    if issue_url=$(gh issue create \
        --repo "$FULL_REPO" \
        --title "$title" \
        --body "$body" \
        --label "$labels" 2>/dev/null); then

        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo -e "  ${GREEN}✓${NC} Issue creado: $issue_url"

        local item_id
        if item_id=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$issue_url" --format json -q '.id' 2>/dev/null); then
            echo -e "  ${GREEN}✓${NC} Añadido al Proyecto."

            if [ -n "$opt_epic" ]; then
                gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$FIELD_EPIC" --single-select-option-id "$opt_epic" >/dev/null
            fi
            if [ -n "$opt_priority" ]; then
                gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$FIELD_PRIORITY" --single-select-option-id "$opt_priority" >/dev/null
            fi
            echo -e "  ${GREEN}✓${NC} Metadatos (Epic, Priority) asignados."
        else
            echo -e "  ${YELLOW}⚠${NC} Issue creado pero no se pudo añadir al proyecto."
        fi
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo -e "  ${RED}✗${NC} Error creando el issue: $title"
    fi

    sleep 1.5
}

# ---------------------------------------------------------------------------
# 🔖 VERIFICACIÓN DE LABELS NECESARIOS
# ---------------------------------------------------------------------------

echo -e "${YELLOW}Verificando/creando labels necesarios...${NC}"

create_label_if_missing() {
    local label="$1"
    local color="$2"
    local description="$3"
    if ! gh label list --repo "$FULL_REPO" --json name -q '.[].name' | grep -q "^${label}$"; then
        gh label create "$label" --repo "$FULL_REPO" --color "$color" --description "$description" 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} Label creado: $label"
    fi
}

create_label_if_missing "status:ready"               "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E12"                   "37474f" "Épica E12 — Observability, Security & Operations"
create_label_if_missing "type:feature"               "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"                  "fbca04" "Tests, fixtures, security scans"
create_label_if_missing "type:cli"                   "8b4789" "Comandos CLI"
create_label_if_missing "type:infra"                 "1d76db" "Infraestructura, deploy"
create_label_if_missing "type:docs"                  "c5def5" "Documentación, runbooks"
create_label_if_missing "type:refactor"              "fef2c0" "Cross-cutting refactor"
create_label_if_missing "component:observability"    "5cb85c" "Logs, metrics, alertas"
create_label_if_missing "component:security"         "b71c1c" "Secrets, rate limit, hardening"
create_label_if_missing "component:operations"       "455a64" "Backups, runbook, DR"
create_label_if_missing "component:audit"            "ff7043" "Audit logs, compliance"
create_label_if_missing "component:dashboard"        "9c27b0" "Páginas y endpoints"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E12
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E12"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E12-S01 — Logging estructurado: audit + completion
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S01] Logging estructurado: audit + completion cross-épica" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Auditoría cross-épica de uso de \`structlog\` y completion de campos estándar en todos los logs. Sin coherencia, búsquedas y filtros no funcionan consistentemente y debugging 6 meses después es imposible. **Correlation ID es la magia:** permite trazar un workflow run completo a través de todos los módulos.

## 📐 Alcance Técnico

### Auditoría cross-épica
Verificar uso de \`structlog\` en cada módulo:
- \`sources/\`, \`scoring/\`, \`application/\`, \`notify/\`, \`outreach/\`, \`email/\`, \`analytics/\`, \`pipeline/\`, \`db/\`, \`dashboard/\`.
- Identificar módulos que aún usan \`logging\` standard library directamente y refactorizar.

### Campos estándar obligatorios
Todos los logs estructurados deben incluir cuando aplica:
- \`timestamp\` (ISO8601, UTC).
- \`level\` (DEBUG/INFO/WARNING/ERROR/CRITICAL).
- \`module\` (ej. \`jobhunter.scoring.scorer\`).
- \`event\` (verbo descriptivo, ej. \`\"job_scored\"\`, \`\"email_matched\"\`).
- \`correlation_id\` (UUID que persiste a través de un workflow run completo).
- \`entity_id\` cuando aplica (ej. \`job_id\`, \`application_id\`, \`email_message_id\`).

### Configuración centralizada
\`src/jobhunter/log_config.py\`:
- \`configure_logging(format='json'|'pretty', level='INFO')\` único punto de entrada.
- Procesador \`add_correlation_id\` usando \`contextvars\`.
- Filtros: redactar campos sensibles (\`password\`, \`token\`, \`api_key\`) con \`****\`.

### Helper de correlation
\`with_correlation_id(workflow_name)\` context manager que setea correlation_id al inicio de cada workflow.

### Update workflows
Cada workflow YAML usa \`LOG_FORMAT=json\` y \`JOBHUNTER_CORRELATION_ID=\$GITHUB_RUN_ID\`.

### CLI mejorado
\`jobhunter logs tail [--since X] [--module Y] [--correlation-id Z]\` mejora capacidades existentes (de E8-S07) con filtros adicionales.

## ⚠️ Trampa común
\`f\"Token: {token}\"\` con \`level=DEBUG\` mete el secreto al log incluso si \`token\` es \`SecretStr\`. Usar siempre \`logger.debug(\"token used\", token=token)\` y dejar que structlog lo redacte.

## 🧪 Criterios de Aceptación
- [ ] Audit completado: lista de módulos auditados con status.
- [ ] Refactor de cualquier módulo no estándar.
- [ ] Test: log estructurado tiene los campos esperados.
- [ ] Test: redacción funciona (\`token\` aparece como \`****\` en output).
- [ ] Test: correlation_id se propaga correctamente a través de async calls.
- [ ] CLI \`logs tail\` con filtros nuevos funciona.

## 🔗 Dependencias
- Bloqueante: Épicas E01–E11 cerradas (audita el trabajo previo).
- Paralelizable con: E12-S02, E12-S03.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:refactor,component:observability,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S02 — Secrets hygiene + pre-commit + history scan
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S02] Secrets hygiene + pre-commit + history scan" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Garantía de que no hay secretos commiteados en el repo (pasado, presente, futuro). Si el repo se hace público o se filtra, no debería haber credenciales expuestas. **Plan de rotación documentado** es valioso aunque nunca se use — el día que la credencial se filtre, tener el procedimiento listo ahorra 30 min de pánico.

## 📐 Alcance Técnico

### \`detect-secrets\` configurado
- Pre-commit hook obligatorio (en \`.pre-commit-config.yaml\`).
- \`.secrets.baseline\` versionado con falsos positivos auditados.

### Scan de history
- \`gh secret-scanning alerts list\` revisado.
- \`git log --all -p | detect-secrets scan --string\` audita historia.
- Si se encuentran secretos en commits pasados, **plan documentado** de rotación (NO rebase de history para repo personal — rotar la credencial es suficiente).

### Verificación de \`.gitignore\`
- \`.env\`, \`.env.local\`, \`.env.*\` (excepto \`.env.example\`).
- \`.local/\` (CV reales, datos personales).
- \`*.db\`, \`pgdata/\`, \`backups/\`.
- \`secrets.json\`, \`credentials.json\`.
- \`.streamlit/secrets.toml\`.

### Plan de rotación documentado
En \`docs/runbook.md\`:
- Anthropic API key.
- Telegram bot token.
- Gmail OAuth tokens.
- SMTP password.
- Postgres connection string.
- Dashboard password.
- **OAuth encryption key** (la más sensible — rotarla invalida TODOS los tokens OAuth, requiere re-auth).

### Workflow automatizado
\`.github/workflows/secrets-scan.yml\`:
- Schedule: weekly + on every push to main.
- Ejecuta \`detect-secrets scan\` y compara con baseline.
- Si nuevos secretos detectados, alerta Telegram + falla CI.

## 🧪 Criterios de Aceptación
- [ ] Pre-commit con \`detect-secrets\` instalado y funcional.
- [ ] Baseline auditado (cero falsos positivos persistentes sin justificación).
- [ ] History scan ejecutado, findings (si existen) atendidos.
- [ ] Plan de rotación documentado con steps específicos.
- [ ] Workflow corre exitosamente.

## 🔗 Dependencias
- Bloqueante: Épica E01 cerrada.
- Paralelizable con: E12-S01, E12-S03.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:security,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S03 — Backup automatizado + restore drill
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S03] Backup automatizado + restore drill semanal" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Backups verificados con restore drill semanal. **Un backup que nunca se restauró NO es backup.** Muchas empresas descubren que sus backups no son restaurables el día que necesitan restaurarlos. Drill semanal cierra ese loop.

## 📐 Alcance Técnico

### Workflow: \`.github/workflows/backup-and-drill.yml\`
- Schedule: domingos 04:00 UTC (después del digest semanal pero antes de Monday morning).
- Steps:
  1. Conectar a DB hosted.
  2. Ejecutar \`pg_dump\` (script de E2-S09 mejorado).
  3. Comprimir con \`gzip\`.
  4. Upload a almacenamiento externo (Backblaze B2 free tier 10GB, o S3-compatible).
  5. **Restore drill:** descargar backup recién creado, restaurar a Postgres ephemeral en runner, validar integridad con queries.
  6. Si drill falla, alerta Telegram CRÍTICA.

### Settings nuevas
- \`backup_storage_provider: Literal['b2', 's3', 'local']\`.
- \`backup_storage_bucket: str\`.
- \`backup_access_key: SecretStr\`.
- \`backup_secret_key: SecretStr\`.
- \`backup_retention_weeks: int = 12\` (3 meses).

### Validaciones de integridad post-restore
- Tablas críticas existen (\`jobs\`, \`applications\`, \`outreach_contacts\`, etc.).
- Row counts dentro de rango razonable (alerta si bajada drástica).
- Migration version en \`alembic_version\` table coincide con app actual.
- Sample query en cada tabla crítica retorna datos.

### CLI commands
- \`jobhunter backup create [--upload]\`.
- \`jobhunter backup restore <backup_id>\` con confirmación interactiva.
- \`jobhunter backup list\`.

### Lifecycle
Backups >12 semanas se borran automáticamente.

## 📝 Decisión: Backblaze B2 vs S3
B2 free tier es 10GB storage + 1GB/día download. Un backup nuestro es ~50MB; 12 backups = 600MB. Holgado.

## 🧪 Criterios de Aceptación
- [ ] Cuenta Backblaze B2 (o equivalente) configurada.
- [ ] Workflow YAML válido + manual trigger exitoso.
- [ ] Drill ejecuta restore completo y validation passes.
- [ ] Si drill falla intencionalmente (test), alerta Telegram dispara.
- [ ] CLI \`backup restore\` con confirmación interactiva.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.
- Paralelizable con: E12-S01, E12-S02.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:operations,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S04 — Health endpoints + status page
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S04] Health endpoints + status page" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Endpoints HTTP que reportan estado del sistema y status page pública (con datos sanitizados). Monitores externos pueden integrarse y verificación de salud desde cualquier lugar es posible.

## 📐 Alcance Técnico

### Endpoint \`/health\`
Response JSON con:
\`\`\`json
{
  \"status\": \"healthy\" | \"degraded\" | \"unhealthy\",
  \"checks\": {
    \"db\": {\"status\": \"ok\", \"latency_ms\": 12},
    \"anthropic_api\": {\"status\": \"ok\", \"last_call_at\": \"...\"},
    \"telegram\": {\"status\": \"ok\"},
    \"gmail\": {\"status\": \"ok\" | \"warning\" | \"error\"}
  },
  \"metrics\": {
    \"last_pipeline_run_at\": \"2h ago\",
    \"active_circuit_breakers\": [],
    \"monthly_cost_usd\": 5.40,
    \"budget_pct_used\": 21.6
  }
}
\`\`\`
Status code: 200 si healthy, 503 si unhealthy.

### Endpoint \`/readiness\`
JSON: ¿DB conectable? ¿Migrations al día? ¿Secrets cargados? ¿Servicios externos accesibles?

### Página pública \`/status\` (sin auth)
- Datos públicamente safe: uptime últimas 24h, last successful pipeline run (relative), totales de jobs (sin detalles), número de matches A-tier en última semana.
- **NO muestra:** datos personales, contenido de jobs, costo USD, contraseñas, tokens, paths internos.

### Página dashboard \`/status\` (autenticada)
Muestra info expandida.

### Implementación
Streamlit no es app server tradicional. Para \`/health\` HTTP estándar, posibles enfoques:
- Pequeño FastAPI sidecar que sirve los endpoints + Streamlit principal.
- Streamlit con query param routing (limitado).

## 📝 Sanitization crítica
Status page leak accidental sería embarazoso. Define conservador y revísalo.

## 🧪 Criterios de Aceptación
- [ ] \`/health\` responde JSON con todos los checks.
- [ ] \`/readiness\` responde correctamente.
- [ ] Página pública \`/status\` no leak ninguna info sensible.
- [ ] Tests unitarios por cada check.
- [ ] Status code 503 si algún check crítico falla.

## 🔗 Dependencias
- Bloqueante: Épica E07 cerrada (dashboard).

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:observability,component:dashboard,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S05 — Rate limiting + abuse prevention
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S05] Rate limiting + abuse prevention dashboard" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Rate limiting en login y endpoints sensibles del dashboard. Para sistema de un solo usuario puede parecer paranoia, pero el dashboard expuesto a internet es blanco constante de scans automatizados. El primer botnet que escanee tu dominio probará passwords comunes — sin rate limit, eventualmente acierta.

## 📐 Alcance Técnico

### Rate limiting en login
- Max 5 intentos fallidos en 15 min por IP → bloquear IP por 1h.
- Max 3 intentos fallidos en 1 hora → CAPTCHA o bloqueo más largo.
- Implementar con \`slowapi\` (si FastAPI sidecar) o Streamlit session-level + tabla.

### Tabla nueva: \`failed_login_attempts\`
- \`id\`, \`ip_address\`, \`attempted_at\`, \`user_agent\`, \`outcome\` (success | failure).
- Índice \`(ip_address, attempted_at)\`.
- TTL automático (datos >30 días borrados con cron).

### Tabla nueva: \`blocked_ips\`
- \`ip_address\`, \`blocked_at\`, \`unblock_at\`, \`reason\`.

### Logs de seguridad
Tag \`security_event\` para:
- Cada intento de login (success/failure).
- Cada bloqueo de IP.
- Cada acceso a endpoint sensible.

### Alertas Telegram
- >10 intentos fallidos de login en 1 hora desde IPs distintas (posible scan).
- Login exitoso desde IP nueva (no vista en últimos 30 días).

### Hardening adicional
- CSP (Content Security Policy) headers configurados.
- HTTPS forzado (redirect HTTP → HTTPS) si deploy externo.

## 📝 CSP en Streamlit
Streamlit usa muchos inline scripts; configurar CSP requiere allowlist específica. Empezar con \`report-only\` mode antes de hacer enforcing.

## 🧪 Criterios de Aceptación
- [ ] Migrations aplicadas.
- [ ] Test: 6 intentos fallidos en 15 min → IP bloqueada.
- [ ] Test: bloqueo expira tras 1h.
- [ ] Logs de \`security_event\` capturados.
- [ ] Alertas Telegram disparan correctamente.

## 🔗 Dependencias
- Bloqueante: E12-S04.
- Paralelizable con: E12-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:security,component:dashboard,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S06 — Audit logs + compliance lite
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S06] Audit logs + compliance lite" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Audit logs completos de operaciones sensibles (mutaciones, accesos a datos, cambios de config). Permite responder \"qué pasó y cuándo\" si hay un incidente. Compliance lite prepara terreno mínimo si en futuro se abre a otros usuarios.

## 📐 Alcance Técnico

### Tabla nueva: \`audit_log\`
- \`id\` UUID PK.
- \`event_type\` VARCHAR (\`login\`, \`logout\`, \`data_access\`, \`data_mutation\`, \`config_change\`, \`secret_rotated\`, \`backup_created\`, \`restore_executed\`, \`bulk_delete\`).
- \`actor\` VARCHAR (\`user\`, \`system\`, \`cron:workflow_name\`, etc.).
- \`target_entity\` VARCHAR NULLABLE (ej. \`Job\`, \`Application\`).
- \`target_id\` UUID NULLABLE.
- \`action\` VARCHAR — verbo descriptivo.
- \`metadata\` JSONB — contexto adicional.
- \`ip_address\` VARCHAR NULLABLE.
- \`created_at\` TIMESTAMPTZ.

### Decorator
\`@audit_logged(event_type, action)\` para mutaciones críticas.

### Aplicar audit logging en
- Login/logout dashboard.
- Bulk delete operations.
- Cambios de prompt versions.
- Backups y restores.
- Rotación de secretos.
- Acceso a OAuth tokens (descrifrado).

### CLI
- \`jobhunter audit query [--since X] [--actor Y] [--event Z]\`.

### Página dashboard \"Audit Log\"
Admin-only con filtros.

### Compliance lite
- \`jobhunter compliance export-data\` — exporta TODA la data personal (jobs aplicados, contactos outreach, emails procesados) en JSON. Útil para \"right to access\" preparation.
- \`jobhunter compliance delete-all --confirm-twice\` — borra todos los datos personales. Útil para \"right to erasure\" preparation.
  - Pide confirmación textual (\"Type 'DELETE-ALL' to confirm\") + segunda confirmación explícita.
  - Audit log persiste el evento incluso después de delete.

## 🧪 Criterios de Aceptación
- [ ] Migration aplicada.
- [ ] Decorator funciona en mutaciones de prueba.
- [ ] Test: login genera audit entry.
- [ ] Test: \`compliance export-data\` produce JSON válido completo.
- [ ] Test: \`compliance delete-all\` requiere doble confirmación.
- [ ] Página dashboard renderiza con filtros.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.
- Paralelizable con: E12-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:audit,component:db,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S07 — Runbook completo + disaster recovery
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S07] Runbook completo + disaster recovery" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Runbook denso con procedimientos específicos para incidentes comunes. **El documento que tu yo del futuro va a leer cuando algo se rompa a las 11pm.** \"Restart the service\" no ayuda. \"Run \`gh workflow run pipeline-cycle.yml --field skip-step=ingest\`\" sí.

## 📐 Alcance Técnico

### \`docs/runbook.md\` reorganizado
Secciones:
1. **Setup inicial** (consolidación de procedimientos esparcidos).
2. **Operación diaria** (cómo ver estado, cómo interpretar alertas).
3. **Mantenimiento** (rotación de secretos, actualización de prompts, cleanup de DB).
4. **Troubleshooting** — los 10 problemas más probables con steps.
5. **Disaster recovery** — los 5 incidentes catastróficos.

### Sección Troubleshooting (10 procedimientos)
- \"Pipeline cycle no produce matches A-tier en una semana\".
- \"Costo LLM excede budget\".
- \"Telegram bot no envía mensajes\".
- \"Dashboard no carga\".
- \"Workflow GH Actions falla con auth error\".
- \"Gmail polling devuelve 0 resultados\".
- \"Migration falla al hacer upgrade\".
- \"Postgres connection pool exhausted\".
- \"DNS / Telegram bot inaccesible\".
- \"Dashboard expuesto recibe high traffic\".

### Sección Disaster Recovery (5 escenarios)
- **DR1: DB perdida o corrupta.** Steps: identificar último backup → download → restore → verificar integridad → re-correr migrations → resume operations. **Target: <30 min.**
- **DR2: Credenciales filtradas.** Steps: revocar inmediatamente → generar nuevas → actualizar GH Secrets → re-deploy → audit logs para detectar abuso. **Target: <1 hora.**
- **DR3: Repo comprometido.** Steps: lockdown → audit history → rotar TODOS los secretos → re-evaluar \`.gitignore\` → notificar a Anthropic si key comprometida.
- **DR4: GH Actions caído >24h.** Steps: ejecutar workflows manualmente desde local → docker run con secretos → fallback temporal.
- **DR5: Anthropic API caída prolongada.** Steps: pause workflows → switch a modo \"ingest only\" → resume cuando vuelva.

### Drill ejecutado
**DR1 ejecutado manualmente** con tiempo medido y documentado.

## 📝 Specificity wins
Cada disaster scenario tiene **checklist específico** (no narrativa) y **comando exacto** cuando aplica.

### Hosting opcional
\`mkdocs\` o serving como página estática.

## 🧪 Criterios de Aceptación
- [ ] Runbook reorganizado y completo.
- [ ] 10 troubleshooting procedures escritos con steps específicos.
- [ ] 5 DR scenarios documentados.
- [ ] DR1 drill ejecutado, tiempo registrado.
- [ ] Runbook ≥500 líneas, comprehensivo.

## 🔗 Dependencias
- Bloqueante: E12-S01, E12-S02, E12-S03, E12-S04, E12-S05, E12-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:docs,component:operations,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E12-S08 — Penetration test ligero + cierre del proyecto
# ---------------------------------------------------------------------------
create_issue \
    "[E12-S08] Penetration test ligero + fix-all + cierre del proyecto v1.0.0" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Sweep final de seguridad antes de declarar el sistema completo. Issues conocidos no deben acabar en bugs descubiertos por terceros. **Tag \`v1.0.0\`** marca el cierre psicológico de la fase de construcción — a partir de aquí, cualquier cambio es maintenance/feature.

## 📐 Alcance Técnico

### Penetration test ligero (auto-ejecutado)
- \`bandit -r src/\` — vulnerabilidades comunes en código Python.
- \`safety check\` o \`pip-audit\` — CVEs en dependencias.
- \`trivy fs .\` — escaneo más amplio.

### Manual checks
- **SQL injection:** verificar uso uniforme de SQLAlchemy parametrized queries, no string concatenation.
- **XSS** en dashboard (Streamlit auto-escapes pero verificar custom HTML rendering).
- **CSRF en mutations** (Streamlit no expone forms tradicionales pero verificar).
- **Path traversal** en file operations (CV variant loader, etc.).
- **Insecure deserialization** (uso de \`pickle\`, \`yaml.load\` sin SafeLoader).

### Triage de findings
- **Critical:** fix antes del cierre.
- **High:** fix antes del cierre.
- **Medium:** create issue, fix en próxima iteración.
- **Low:** documentar como tech debt.

### Fix de todos críticos y altos.

### Verificación final cross-épica
- Todas las 12 épicas tienen tag \`vN.0\` correspondiente.
- CI verde en \`main\`.
- 7 días consecutivos de operación con tasa de éxito ≥95% en workflows.
- Tests con coverage global ≥75%.
- \`docs/\` completo: arquitectura, data model, runbook, prompt design, ADRs.

### Tag final
**\`v1.0.0\`** del proyecto.

### README final
- Badges de status.
- Captura del dashboard.
- Link al status page público (de S04).
- Sección 'Architectural Decisions' linkeando ADRs.

### CI integration
\`bandit\` y \`pip-audit\` configurados en CI para que cada PR los ejecute.

## 📝 ADRs (opcional pero recomendado)
A lo largo del proyecto se han tomado ~50+ decisiones arquitectónicas explícitas (en anexos de cada documento L2). Formalizar en \`docs/adr/\` es **portfolio piece extraordinario**:
- \`ADR-001-streamlit-over-fastapi-vue.md\`.
- \`ADR-002-postgres-over-sqlite.md\`.
- \`ADR-003-gh-actions-over-airflow.md\`.
- \`ADR-005-no-auto-apply-no-auto-send.md\`.
- ... etc.

## 🧪 Criterios de Aceptación
- [ ] \`bandit\`, \`pip-audit\`, \`trivy\` ejecutados, findings triaged.
- [ ] 0 findings Critical/High sin atender.
- [ ] Manual checks completados.
- [ ] Tests con coverage ≥75% global.
- [ ] 7 días de operación estable confirmados.
- [ ] Tag \`v1.0.0\` creado.
- [ ] README final con badges + screenshots.
- [ ] **Sistema operacional estable durante 14 días sin incidentes mayores.**

## 🎉 Cierre
**Tag \`v1.0.0\` = PROYECTO COMPLETO.** A partir de aquí: maintenance, A/B testing de prompts (E11), iteración basada en métricas reales.

## 🔗 Dependencias
- Bloqueante: TODAS las stories anteriores (E12-S01 a E12-S07) y todas las épicas previas (E1-E11).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:docs,component:security,component:operations,epic:E12" \
    "$OPT_EPIC_E12" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# 📊 RESUMEN FINAL
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo -e " ${GREEN}PROCESO COMPLETADO${NC}"
echo -e " Issues creados exitosamente: ${GREEN}${SUCCESS_COUNT}${NC}"
echo -e " Issues fallidos:             ${RED}${FAIL_COUNT}${NC}"
echo "============================================================"
echo ""
echo " 🎉 BACKLOG L2 COMPLETO PARA TODAS LAS 12 ÉPICAS DEL PROYECTO."
echo ""
echo " Próximos pasos:"
echo "   1. Verifica los issues en: https://github.com/${FULL_REPO}/issues"
echo "   2. Verifica el proyecto en: https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo "   3. ⚠️  Decision rule de E12: si vas a operar el sistema >2 meses, épica completa."
echo "       Si <2 meses, mantener S02 + S03 + runbook básico de S07; saltar el resto."
echo "   4. ⚠️  S03 restore drill: muchas empresas descubren que sus backups no son"
echo "       restaurables el día que necesitan restaurarlos. NO lo saltes."
echo "   5. ⚠️  S07 runbook denso: tu yo del futuro a las 11pm te lo agradecerá."
echo "   6. ⚠️  S08: tag 'v1.0.0' marca cierre psicológico de la fase de construcción."
echo ""
echo " Proyecto completo: 12 épicas × 8 stories promedio ≈ 96 issues."
echo " Estimación total: ~135 horas de trabajo concentrado."
echo ""
