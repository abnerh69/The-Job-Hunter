#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E8 — Scheduling & Automation
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
OPT_EPIC_E08="7a9c7ae7"     # E8-Automation

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

# ---------------------------------------------------------------------------
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + automation specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren la lógica del orquestador y comandos CLI; mocks usados para sub-componentes.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google/NumPy.
5. **Idempotencia:** Cualquier workflow es seguro de re-correr múltiples veces sin generar duplicados ni efectos secundarios indebidos.
6. **Resilience:** Errores en un paso no detienen el pipeline completo (excepto fallos DB-related). Cada paso captura y reporta su estado.
7. **Logs estructurados:** Workflows producen output JSON con `LOG_FORMAT=json`; capturados como artifacts.
8. **Secrets seguros:** Credenciales NUNCA en código ni en logs; solo en GH Secrets, accedidos vía composite action `setup-env`.
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story añade/modifica un workflow, `docs/runbook.md` documenta cómo investigar fallos y cómo disparar manualmente.'

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
create_label_if_missing "epic:E08"                   "1f6feb" "Épica E08 — Scheduling & Automation"
create_label_if_missing "type:feature"               "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:infra"                 "1d76db" "Infraestructura, deploy, hosting"
create_label_if_missing "type:cli"                   "8b4789" "Comandos CLI"
create_label_if_missing "type:test"                  "fbca04" "Tests, fixtures"
create_label_if_missing "component:pipeline"         "ff9800" "Orquestador, run-cycle"
create_label_if_missing "component:workflows"        "6f42c1" "GitHub Actions workflows"
create_label_if_missing "component:observability"    "5cb85c" "Logs, metrics, alertas"
create_label_if_missing "component:secrets"          "b71c1c" "Credenciales, GH Secrets"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E08
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E08"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E08-S01 — DB hosted setup + secrets
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S01] DB hosted setup (Neon/Supabase) + secrets" \
    "## 🎯 Contexto Arquitectónico
Los runners de GH Actions son efímeros — no pueden tener Postgres local persistente. Necesitamos DB hosted con free tier suficiente. **Recomendación: Neon** (autoscale, region US East, menos features = menos cosas que romperse). Connection string + todas las credenciales del sistema en GH Secrets, accedidos vía composite action para DRY.

## 📐 Alcance Técnico

### Provider
- Neon (https://neon.tech) free tier: 0.5 GB storage, autoscale.
- Region: US East (baja latencia desde Colombia).
- Connection pooling endpoint (\`-pooler\` en URL) para workflows efímeros.
- Schema migrado: \`alembic upgrade head\` corrido contra DB hosted desde local.

### GH Secrets requeridos
- \`DATABASE_URL_PROD\` (connection string completa con \`-pooler\`).
- \`ANTHROPIC_API_KEY\`.
- \`TELEGRAM_BOT_TOKEN\`, \`TELEGRAM_CHAT_ID\`.
- \`SMTP_USER\`, \`SMTP_PASSWORD\`, \`DIGEST_TO_EMAIL\`.
- \`DASHBOARD_PASSWORD\`.

### Composite action: \`setup-env\`
- \`.github/actions/setup-env/action.yml\`.
- Reutilizable en todos los workflows. Sin esto, cada YAML duplicaría 20 líneas de configuración de env vars.

### Workflow de prueba
- \`.github/workflows/test-connection.yml\` (manual trigger): ejecuta \`SELECT 1\` contra DB hosted desde GH Actions.

### Documentación en runbook
- Setup de Neon paso a paso.
- Cómo rotar secrets si se filtran (procedimiento de emergencia).
- Cómo migrar de provider si rinde.

## 🧪 Criterios de Aceptación
- [ ] Cuenta Neon creada, proyecto activo.
- [ ] \`alembic upgrade head\` ejecutado contra DB hosted exitosamente.
- [ ] Todos los secrets configurados con \`gh secret set\`.
- [ ] Composite action \`setup-env\` funciona.
- [ ] \`test-connection.yml\` workflow corre verde.
- [ ] Runbook actualizado.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:secrets,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S02 — pipeline run-cycle orquestador
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S02] \`jobhunter pipeline run-cycle\` orquestador" \
    "## 🎯 Contexto Arquitectónico
Comando único que ejecuta ingest → score → dispatch en secuencia. Los workflows YAML solo lo invocan; la lógica vive en código testeable. Decisión: orquestación en Python, no en YAML, porque \"si ingest falló pero scoring tiene jobs nuevos del último cycle, igual scoréalos\" es lógica de aplicación que YAML no puede expresar limpiamente.

## 📐 Alcance Técnico

### Comando CLI
- \`jobhunter pipeline run-cycle\` ejecuta:
  1. \`ingest\` (de E3-S08) para todas las fuentes.
  2. \`score\` (de E4-S07) para jobs nuevos.
  3. \`notify dispatch\` (de E5-S07) para tier-A no notificados.

### Manejo de errores
- Cada paso captura su \`Report\` (IngestionReport, ScoringBatchReport, DispatchReport).
- Si un paso falla, los siguientes se ejecutan igual (excepto si la falla es DB-related).
- **Resilience > fail-fast** en operación desatendida.

### \`RunCycleReport\` (Pydantic)
Consolida los 3 reports + \`started_at\`, \`finished_at\`, \`total_duration_ms\`, \`overall_status\` (success/partial_failure/total_failure).

### Output dual
- Human: tabla rich con resumen.
- Machine: JSON al final (último bloque stdout o stderr) — para que GH Actions capture la métrica y la pinte en summary.

### Exit code
- \`0\` si todo OK o partial failure (workflow marca como ⚠️ pero verde).
- \`1\` solo si total failure (DB caída, etc.) — workflow falla en rojo.

### Flag \`--skip-step STEP\`
Para debug (ingest/score/notify).

## 🧪 Criterios de Aceptación
- [ ] Test: cycle exitoso → \`overall_status='success'\`, exit code 0.
- [ ] Test: ingest falla pero score+dispatch ok → \`overall_status='partial_failure'\`, exit code 0.
- [ ] Test: DB caída → exit code 1.
- [ ] Test: \`--skip-step ingest\` no ejecuta ingest.
- [ ] Output JSON parseable.

## 🔗 Dependencias
- Bloqueante: Épicas E03, E04, E05 cerradas.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,type:cli,component:pipeline,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S03 — Workflow: pipeline cycle (cada 8h)
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S03] Workflow: pipeline cycle (cada 8h)" \
    "## 🎯 Contexto Arquitectónico
Workflow principal. Dispara el ciclo completo cada 8h (00:00, 08:00, 16:00 UTC = 19:00, 03:00, 11:00 COT). Es el corazón de la operación desatendida — sin esto, todo el sistema requiere intervención manual.

## 📐 Alcance Técnico

### \`.github/workflows/pipeline-cycle.yml\`
- Schedule cron: \`'0 */8 * * *'\` (cada 8h en UTC).
- Trigger manual (\`workflow_dispatch\`) con inputs opcionales (\`limit\`, \`source\`).
- Job único \`run-cycle\` con steps:
  1. Checkout.
  2. Setup uv + Python 3.12.
  3. \`uv sync --frozen\`.
  4. Composite action \`setup-env\` (de S01).
  5. \`uv run jobhunter pipeline run-cycle\`.
  6. Si falla, post a Telegram (composite action de S06).
- Timeout: 30 minutos.
- \`concurrency: pipeline-cycle\` con \`cancel-in-progress: false\` (si un run anterior tarda, esperar; no cancelar).

## 📝 Decisiones
- **\`cancel-in-progress: false\`** evita race conditions sobre la misma DB. Si las 16:00 sigue corriendo cuando llega 00:00, completan en serie.
- **3 corridas/día** = ~9000 min/mes peor caso (timeout 30 min × 3 × 30). Free tier es 2000 min/mes. Pero cycle típico debería ser 5-10 min, no 30. Si rinde, ~900 min/mes. Aceptable.
- **GH Actions cron NO tiene SLA**: runner puede tardar 5-15 min en arrancar tras el horario programado. Aceptable para nuestro caso.

## 🧪 Criterios de Aceptación
- [ ] Workflow YAML válido (\`gh workflow run\` no falla en parsing).
- [ ] \`workflow_dispatch\` manual ejecuta exitosamente.
- [ ] Primer cron-triggered run sea exitoso.
- [ ] Logs persisten en Actions tab.
- [ ] Tiempo medio de ejecución < 15 min.

## 🔗 Dependencias
- Bloqueante: E08-S01, E08-S02.
- Paralelizable con: E08-S04, E08-S05.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:workflows,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S04 — Workflow: digest semanal
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S04] Workflow: digest semanal (domingos)" \
    "## 🎯 Contexto Arquitectónico
Digest semanal disparado automáticamente los domingos al mediodía COT. Sin pensar; llega al inbox cuando reviso el café del domingo.

## 📐 Alcance Técnico

### \`.github/workflows/weekly-digest.yml\`
- Schedule cron: \`'0 17 * * 0'\` (domingos 17:00 UTC = 12:00 COT).
- Trigger manual.
- Steps idénticos a S03 pero ejecutando \`uv run jobhunter notify digest --send\`.
- Timeout: 5 minutos.

## 🧪 Criterios de Aceptación
- [ ] Workflow YAML válido.
- [ ] Manual trigger envía digest correctamente.
- [ ] Primer envío automático verificado al siguiente domingo.

## 🔗 Dependencias
- Bloqueante: E08-S01, E05-S06 (digest implementado).
- Paralelizable con: E08-S03, E08-S05.

## ⏱️ Estimación
0.5h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:workflows,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S05 — Workflow: follow-up checks (diario)
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S05] Workflow: follow-up checks (diario)" \
    "## 🎯 Contexto Arquitectónico
Workflow diario que detecta aplicaciones requiriendo follow-up o que están ghosted. Sin esto, el sistema acumula data muerta y no empuja a actuar antes de perder oportunidades.

## 📐 Alcance Técnico

### Comando CLI nuevo: \`jobhunter pipeline check-followups\`
1. Ejecuta \`ApplicationRepo.list_pending_followups(today)\` (de E2-S07).
2. Ejecuta \`ApplicationRepo.list_ghosted_candidates(today)\` y los marca como ghosted automáticamente (status='ghosted', evento creado en \`application_events\`).
3. Si hay follow-ups pendientes, manda notificación Telegram con lista compacta: \"💡 3 follow-ups pendientes hoy: [ACME Corp, BetaTech, Gamma Inc]. Ver dashboard.\"
4. Refresh de \`weekly_metrics\` materialized view (rápido, hace que dashboard tenga data fresca).

### \`.github/workflows/followup-checks.yml\`
- Schedule cron: \`'0 14 * * *'\` (diario 14:00 UTC = 09:00 COT).
- Trigger manual.
- Steps ejecutan \`uv run jobhunter pipeline check-followups\`.

## 📝 Decisión: auto-marcar ghosted
Si han pasado 21 días sin respuesta, mantener en \`applied\` indefinidamente distorsiona métricas. Auto-marcar ghosted es realista. Usuario puede revertir manualmente desde dashboard si fue prematuro.

## 🧪 Criterios de Aceptación
- [ ] Test del comando con DB seeded: pending followups detectados, ghosted candidates marcados.
- [ ] Notificación Telegram solo cuando hay follow-ups pendientes (no spam diario si lista vacía).
- [ ] Workflow YAML válido + manual trigger exitoso.

## 🔗 Dependencias
- Bloqueante: E08-S01, Épica E02 (Application repos).
- Paralelizable con: E08-S03, E08-S04.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:workflows,component:pipeline,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S06 — Sistema de alertas de fallo
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S06] Sistema de alertas de fallo" \
    "## 🎯 Contexto Arquitectónico
Alertas inmediatas en Telegram cuando un workflow falla. **Sin alertas, un sistema caído es invisible durante días.** Dual-track: \`alert-on-failure\` cubre \"el workflow no completó\"; \`health-check\` cubre \"completó pero el resultado es preocupante\" (circuit breaker abierto, budget al 90%, etc.).

## 📐 Alcance Técnico

### Composite action \`alert-on-failure\`
- \`.github/actions/alert-on-failure/action.yml\`.
- Detecta si steps anteriores fallaron (\`if: failure()\`).
- Llama a la API de Telegram directamente con \`curl\` (no requiere Python; más simple en YAML).
- Mensaje incluye: nombre del workflow, link al run, primeras líneas del error log.
- Aplicado en los 3 workflows (S03, S04, S05) como último step.

### Comando CLI: \`jobhunter health-check\`
Verifica:
- Última corrida exitosa de pipeline-cycle (alerta si > 16h).
- Última corrida exitosa de followup-checks (alerta si > 36h).
- Estado de circuit breakers (alerta si 2+ fuentes abiertas).
- Costo LLM mensual (alerta si > 80% del budget).
- Cualquier alerta dispara mensaje Telegram con prefix \"🚨\".

### \`.github/workflows/health-check.yml\`
- Schedule cron: cada 4 horas.
- Ejecuta \`uv run jobhunter health-check\`.

### Anti-spam crítico
Si la misma alerta ya se envió en las últimas 6 horas, no re-enviar. Implementación: usa tabla \`notifications_sent\` con \`dedup_key='health_check:{alert_type}:{date_hour}'\` agrupando por bloques de 6h.

## ⚠️ Por qué \`curl\` directo y no Python
Más simple en YAML; menos cosas que pueden fallar. Si Python falla por algún motivo, **¿cómo enviarías la alerta?** El \`curl\` directo es failsafe.

## 🧪 Criterios de Aceptación
- [ ] Composite action funciona en los 3 workflows.
- [ ] \`health-check\` detecta condiciones correctamente.
- [ ] Anti-spam: 2 alertas iguales en 6h → solo 1 enviada.
- [ ] Test manual: forzar fallo en cycle (credencial DB inválida) → alerta llega.

## 🔗 Dependencias
- Bloqueante: E08-S03, E08-S04, E08-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:observability,component:workflows,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E08-S07 — Logs estructurados + observabilidad
# ---------------------------------------------------------------------------
create_issue \
    "[E08-S07] Logs estructurados + observabilidad" \
    "## 🎯 Contexto Arquitectónico
Sin logs estructurados capturados como artifacts, debug post-mortem es imposible. Action Summary con métricas en cada run hace los workflows auto-explicativos. Decisión: GitHub artifacts + CLI download es suficiente; no usar hosted logging (Datadog, Sentry) para sistema personal.

## 📐 Alcance Técnico

### Configuración structlog
- Verificar \`structlog\` configurado uniformemente cross-épica.
- Settings: \`log_format: Literal['json', 'pretty'] = 'pretty'\`.
- Logs en JSON cuando \`LOG_FORMAT=json\`; pretty-print por default (local).

### Workflows
- Configuran \`LOG_FORMAT=json\` y redirigen stdout a \`pipeline-{run_id}.jsonl\`.
- Step \`actions/upload-artifact@v4\` con archivo de logs (retención 30 días).

### CLI: \`jobhunter logs tail [--since DATE]\`
- Descarga últimos artifacts via \`gh run download\`.
- Muestra logs filtrables (por nivel, por timestamp, por evento).

### Action Summary
Métricas clave exportadas como markdown en \`\$GITHUB_STEP_SUMMARY\`:
- **Pipeline cycle:** jobs ingestados, scoreados, notificados, costo LLM, duración.
- **Health check:** status (green/yellow/red), alertas activas.
- Visible en GitHub UI tras cada run.

### Documentación en runbook
- Cómo descargar logs.
- Cómo investigar un fallo paso a paso.
- Cómo correlacionar artifacts con runs.

## 🧪 Criterios de Aceptación
- [ ] Workflows producen \`pipeline-{run_id}.jsonl\` capturable.
- [ ] \`gh run download <RUN_ID>\` recupera artifacts.
- [ ] \`jobhunter logs tail\` muestra logs filtrables del último run.
- [ ] Action Summary visible con tabla markdown legible.
- [ ] Runbook documenta los 3 procedimientos.

## 🔗 Dependencias
- Bloqueante: E08-S03, E08-S04, E08-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:observability,epic:E08" \
    "$OPT_EPIC_E08" \
    "$OPT_PRIORITY_P0"

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
echo " Próximos pasos:"
echo "   1. Verifica los issues en: https://github.com/${FULL_REPO}/issues"
echo "   2. Verifica el proyecto en: https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S01: crear cuenta en Neon (https://neon.tech)"
echo "       y tener la connection string lista."
echo "   4. ⚠️  Tras cerrar S03+S06: dejar el sistema correr 7 días desatendido"
echo "       como verificación final del MVP P0."
echo ""
echo " 🎉 Cerrar E08 = MVP P0 oficialmente cerrado."
echo ""
