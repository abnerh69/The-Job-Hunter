#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E11 — Metrics, Analytics & Continuous Tuning
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
OPT_EPIC_E11="4d8dcded"     # E11-Analytics

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + analytics specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **DRY:** Toda query de métrica vive en `src/jobhunter/analytics/`. NO duplicada en dashboard, digest, o CLI consumers.
6. **No auto-tuning:** El sistema sugiere cambios al prompt/template/filtros pero NUNCA los aplica sin aprobación humana.
7. **Reproducibilidad:** Recommendations heurísticas son determinísticas (mismo input siempre produce mismo output).
8. **A/B asignment determinístico:** `select_variant(test, entity_id)` produce siempre la misma variant para el mismo entity (no flapping).
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story añade prompt analítico, se versiona en `prompts/analytics_*/vN.md`.'

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

create_label_if_missing "status:ready"            "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E11"                "00838f" "Épica E11 — Metrics, Analytics & Tuning"
create_label_if_missing "type:feature"            "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"               "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"                "8b4789" "Comandos CLI"
create_label_if_missing "type:infra"              "1d76db" "Infraestructura, workflows"
create_label_if_missing "component:analytics"     "00838f" "Servicios de métricas, A/B testing"
create_label_if_missing "component:dashboard"     "9c27b0" "Páginas y componentes Streamlit"
create_label_if_missing "component:reports"       "fdd835" "Reportes mensuales, PDFs"
create_label_if_missing "component:llm"           "5319e7" "LLM client, prompts narrativos"
create_label_if_missing "component:db"            "d93f0b" "Migraciones, repos, persistencia"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E11
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E11"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E11-S01 — Servicio de métricas consolidadas
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S01] Servicio de métricas consolidadas" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Hasta E10, queries de métricas pueden estar duplicadas en \`dashboard/services/metrics.py\`, \`notify/digest.py\`, \`outreach/stats\`. E11-S01 consolida en \`src/jobhunter/analytics/\` — DRY brutal, single source of truth. Otras stories de E11 dependen de esta consolidación.

## 📐 Alcance Técnico

### Estructura nueva
\`src/jobhunter/analytics/\` con submódulos por dominio:
- \`pipeline_metrics.py\` — funnel de descubrimiento → aplicación → entrevista → oferta.
- \`quality_metrics.py\` — tier distribution, fit_score por fuente, false rejects.
- \`cost_metrics.py\` — LLM usage, cost per outcome (cost per tier-A, cost per application).
- \`outreach_metrics.py\` — response rate por template/market/score.
- \`email_metrics.py\` — precision/recall del matcher (de E10).
- \`prompt_metrics.py\` — performance por prompt_version (foundation para A/B testing).

### Patrón
- Cada submódulo expone funciones puras: \`get_funnel(session, date_range) -> FunnelResult\`, etc.
- Pydantic models para todos los resultados (testeables, serializables a JSON).

### Refactor (deuda técnica saneada)
- Migrar queries del dashboard E7-S06 a \`analytics/\`.
- Migrar queries del digest E5-S06 a \`analytics/\`.
- Migrar \`outreach stats\` (E9-S08) a \`analytics/outreach_metrics.py\`.

### Caching coordinado
- \`@lru_cache\` para queries deterministas.
- \`@st.cache_data\` en Streamlit consumers.
- Default in-memory; Redis opcional si rinde.

## 📝 Reusar lo que ya existe
Aprovechar la materialized view \`weekly_metrics\` (de E2-S05) y \`llm_calls\` (de E4-S06). Sumar lógica nueva solo donde no existe.

## 🧪 Criterios de Aceptación
- [ ] 6 submódulos creados con funciones documentadas.
- [ ] Pydantic result models para cada función.
- [ ] Dashboard E7 sigue funcionando tras migración.
- [ ] Digest E5 sigue funcionando tras migración.
- [ ] Tests unitarios cubren cada función con DB seeded \`rich\`.

## 🔗 Dependencias
- Bloqueante: Épicas E04, E05, E06, E07, E08, E09, E10 cerradas (las consumen).

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S02 — A/B testing infrastructure
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S02] A/B testing infrastructure (feature flags)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Infraestructura ligera de A/B testing para prompts y templates. Comparar versiones empíricamente en lugar de adivinar. Determinístico por hash(entity_id) — el mismo job siempre va a la misma variant (no flaps).

## 📐 Alcance Técnico

### Tabla nueva: \`ab_tests\`
- \`id\` UUID PK.
- \`name\` VARCHAR UNIQUE — ej. \"scoring_v2_test\".
- \`description\` TEXT.
- \`metric_target\` VARCHAR — ej. \"tier_a_precision\", \"outreach_response_rate\".
- \`variants\` JSONB — ej. \`{\"v1\": 0.5, \"v2\": 0.5}\`.
- \`started_at\` TIMESTAMPTZ.
- \`ended_at\` TIMESTAMPTZ NULLABLE.
- \`status\` VARCHAR (enum: \`active\`, \`concluded\`, \`aborted\`).
- \`conclusion\` TEXT NULLABLE.

### CLI commands
- \`jobhunter analytics ab-test create --name X --variants v1=0.5,v2=0.5 --metric M\`.
- \`jobhunter analytics ab-test results <NAME>\` — tabla con sample size, metric value, confidence interval, statistical significance vs control.
- \`jobhunter analytics ab-test conclude <NAME> --winner v2 --conclusion \"...\"\`.

### Selector determinístico
\`src/jobhunter/analytics/ab_testing.py\` con \`select_variant(test_name, entity_id) -> str\`:
- Hash determinístico: \`hash(entity_id + test_name) % 100\` → bucket.
- Mismo entity siempre cae en mismo bucket (no flapping).
- Si no hay test activo para \`test_name\`, devuelve \"default\".

### Integración
- E4 scorer y E9 outreach generator consultan \`select_variant(\"scoring_prompt\", job.id)\` antes de cargar el prompt.
- \`Job.score_version\` y \`OutreachMessage.template_version\` ya existen — solo consumir el assignment.

### Significancia estadística
Z-test para proporciones (suficiente para nuestro caso).

### Sample size mínimo
30 por variant (rule of thumb estadístico). CLI advierte si < 30 al pedir results, rechaza concluir winner.

## 🧪 Criterios de Aceptación
- [ ] Migration aplicada.
- [ ] Test assignment determinístico: mismo \`entity_id\` siempre devuelve misma variant.
- [ ] Test variants distribution: 1000 entities con 50/50 → ~500 en cada variant (margen ±5%).
- [ ] Test significance calculation con sample size pequeño y grande.
- [ ] CLI rechaza \`conclude\` si sample size < 30 por variant.

## 🔗 Dependencias
- Bloqueante: Épica E04 cerrada.
- Paralelizable con: E11-S01.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,component:db,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S03 — Detector de regresiones + alertas
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S03] Detector de regresiones + alertas" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Detección automática de drops significativos en métricas clave. Sin esto, un cambio que rompe sutilmente el sistema (ej. nueva versión de prompt que baja precision) sería invisible durante semanas.

## 📐 Alcance Técnico

### Comando \`jobhunter analytics check-regressions\`
1. Compara métricas de **última semana** vs **promedio de las 4 semanas anteriores**.
2. Métricas monitoreadas:
   - Tier A rate (% de jobs ingestados que terminan tier A).
   - Application rate (% de tier A que se aplican).
   - Response rate (% de aplicaciones con cualquier respuesta).
   - Outreach response rate.
   - Email matcher precision.
   - Pipeline cycle success rate.
3. Threshold: drop > 30% relativo, o drop > 5 puntos porcentuales absolutos (lo que sea mayor).
4. Output structured con: métrica, valor anterior, valor actual, % drop, contexto inferido.

### Comando \`jobhunter analytics check-anomalies\`
Complementario para detectar anomalías upward. Subida brusca también puede indicar bug (ej. precision súbitamente al 100% probablemente bug en cálculo).

### Alertas Telegram
Si regresión detectada:
- Métrica afectada y magnitud.
- Contexto inferido (commits recientes, prompts cambiados, configs).
- Link al dashboard.
- Sugerencia: \"Considera correr \`analytics report\` para análisis completo\".

### Anti-flapping
Si la misma regresión ya alertó en últimos 3 días, no re-alerta (a menos que empeoró 20%+). Usa \`notifications_sent\` con dedup_key.

## 📝 Threshold conservador
30% drop relativo es significativo; 10% puede ser ruido normal en sample size pequeño. Si el sistema rinde y tiene más data, ajustar a 20% en futuro.

## 🧪 Criterios de Aceptación
- [ ] Tests con DB seeded simulando drops de cada métrica.
- [ ] Alertas Telegram disparan correctamente.
- [ ] Anti-flapping verificado: 2 alertas iguales en 3 días → solo 1 enviada.
- [ ] Anomaly detection upward funciona.

## 🔗 Dependencias
- Bloqueante: E11-S01.
- Paralelizable con: E11-S04.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S04 — Análisis de false rejects + missed opportunities
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S04] Análisis de \"false rejects\" y \"missed opportunities\"" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Identificar jobs que el sistema marcó REJECT pero que en retrospectiva eran válidos. Calibrar el prompt y no perder oportunidades silenciosamente. \"Manualmente promovido\" desde dashboard es la señal más clara de false reject — feedback ground truth del usuario.

## 📐 Alcance Técnico

### Migration
Añadir columnas a \`jobs\` (o usar \`application_events\` extendido):
- \`manually_promoted_at\` TIMESTAMPTZ NULLABLE.
- \`manually_promoted_reason\` TEXT NULLABLE.

### CLI: \`jobhunter analytics false-rejects [--limit N]\`
- Query: jobs \`tier='REJECT'\` en últimos 60 días donde el usuario los promovió manualmente.
- Output: lista con título, empresa, razón original de REJECT, razón de promoción manual.

### CLI: \`jobhunter analytics missed-opportunities\`
- Heurística: jobs \`tier='REJECT'\` donde el \`red_flag\` que los marcó es ahora menos común en la población.
- Ejemplo: \"EU permit required\" puede ser sobre-restrictivo si el sistema rinde con LATAM-friendly companies.
- Output: lista de candidatos a re-score con prompt actualizado.

### CLI: \`jobhunter analytics rescore-suspicious [--limit N --confirm]\`
- Toma top-N de \`missed-opportunities\`.
- Re-scorea con prompt actual (puede ser una versión nueva).
- Si re-score difiere significativamente (REJECT → A/B), reporta y permite promover.

### Integración
- Sección en dashboard E7 (Analytics page futura).
- Aparece en reporte mensual (S05).

## 📝 Sobre \`missed-opportunities\`
Es exploratoria, no certeza. El usuario decide si promover. Sirve más como \"lista de cosas a revisar\" que como \"deuda\".

## 🧪 Criterios de Aceptación
- [ ] Migration aplicada.
- [ ] Tests con DB seeded simulando false rejects.
- [ ] \`false-rejects\` lista correctamente.
- [ ] \`rescore-suspicious\` re-scorea y reporta diferencias.

## 🔗 Dependencias
- Bloqueante: E11-S01.
- Paralelizable con: E11-S03.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,component:db,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S05 — Generador de reportes mensuales (Sonnet)
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S05] Generador de reportes mensuales (Sonnet)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Reporte mensual narrativo generado por LLM con insights, recomendaciones, y anomalías. Visión cualitativa además de las métricas crudas. **Portfolio piece poderoso:** mostrar el reporte auto-generado del sistema mismo en entrevistas (especialmente roles AI/ML) es una historia única.

## 📐 Alcance Técnico

### CLI: \`jobhunter analytics report --month YYYY-MM [--output md|html|pdf]\`

### Pipeline de generación
1. Recolectar todas las métricas del mes desde S01.
2. Comparar contra mes anterior y trimestre anterior.
3. Identificar top 3 cambios significativos.
4. Pasar todo a Sonnet con prompt analítico que produce:
   - **Resumen ejecutivo** (1 párrafo).
   - **Highlights** (3-5 logros, métricas concretas).
   - **Lowlights** (3-5 problemas o regresiones).
   - **Anomalías** observadas.
   - **Recomendaciones priorizadas** (top 5).
   - **Predicciones** para próximo mes basadas en tendencia.

### Prompt versionado
\`prompts/analytics_report/v1.md\` cuidadosamente diseñado.

### Modelo
\`claude-sonnet-4-6\`. Calidad alta, costo bajo (~\$0.10 por reporte).

### Output formats
- \`md\` (default).
- \`html\` con CSS embebido (email-friendly).
- \`pdf\` usando \`weasyprint\` (MD → HTML → PDF).

### Defaults
- Si \`--month\` no se especifica: mes anterior completo.
- Reportes guardados en \`reports/YYYY-MM-monthly.{md,pdf}\`.

## ⚠️ Prompt design crítico
El reporte debe ser HONESTO sobre los lowlights. **Anti-pattern:** LLMs tienden a sugar-coat. El prompt debe explícitamente pedir \"ser brutal sobre lo que no funcionó\".

## 🧪 Criterios de Aceptación
- [ ] \`prompts/analytics_report/v1.md\` versionado.
- [ ] Test con LLM mockeado: reporte completo generado con estructura esperada.
- [ ] Conversión PDF funciona con \`weasyprint\`.
- [ ] Costo registrado en \`llm_calls\` con \`purpose='analytics_report'\`.

## 🔗 Dependencias
- Bloqueante: E11-S01.
- Nuevas deps: \`weasyprint\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,component:llm,component:reports,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S06 — Recomendaciones automáticas accionables
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S06] Recomendaciones automáticas accionables" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Comando que produce recomendaciones específicas y accionables sobre qué cambiar para mejorar resultados. Operación data-driven, no intuición. **Heurística determinística > LLM aquí** — reproducibilidad, debugability, gratis.

## 📐 Alcance Técnico

### CLI: \`jobhunter analytics recommendations\`
Lista de recomendaciones con:
- **Acción específica.**
- **Razón data-driven.**
- **Impacto estimado.**
- **Esfuerzo estimado:** Low / Medium / High.
- **Prioridad:** P1 / P2 / P3.

### Reglas heurísticas implementadas
- Tasa de respuesta de un template = 0% en últimas 4 semanas con ≥10 sends → recomienda pausar.
- Fuente sin producir A-tier en 14 días → recomienda revisar filtros o circuit breaker.
- Prompt v actual con precision <80% en últimas 4 semanas (vs prev de 90%+) → recomienda rollback.
- > 30% de jobs en \`manual_review\` sin decisión > 7 días → recomienda revisar threshold de tier C.
- Costo LLM mensual >80% del budget → recomienda revisión de uso.
- Circuit breaker de fuente abierto >24h sin recuperación → recomienda investigar manualmente.

### Estructura
- Cada regla como función separada testeable: \`_check_template_zero_response()\`, \`_check_source_dry_spell()\`, etc.
- Engine en \`src/jobhunter/analytics/recommendations.py\`.
- Output: tabla rich + JSON exportable.
- Sección en dashboard E7 (página Analytics dedicada).

## 📝 Decisión: heurística > LLM
- **Reproducibilidad:** mismo input siempre da misma output.
- **Debugability:** rastreable a regla específica.
- **Costo:** gratis vs ~\$0.50/corrida.
- **Calidad para este caso:** reglas son específicas y conocibles a priori.

## ⚠️ Cero auto-tuning
El sistema NO aplica recomendaciones automáticamente. Pausar un template = decisión humana.

## 🧪 Criterios de Aceptación
- [ ] Cada regla heurística testeada aisladamente.
- [ ] Tests con DB seeded simulando cada escenario que dispara recomendación.
- [ ] CLI output legible con tabla rich.
- [ ] Sección dashboard renderiza correctamente.

## 🔗 Dependencias
- Bloqueante: E11-S03, E11-S04.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:analytics,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S07 — Export PDF + UI dashboard analytics page
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S07] Export PDF + UI dashboard analytics page" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Página dedicada en dashboard para analytics avanzado y export PDF. Archivado de reportes mensuales + consumo visual de recommendations, A/B tests, y false rejects.

## 📐 Alcance Técnico

### Página nueva: \`pages/8_📈_Analytics.py\`
4 secciones:
- **Recommendations:** lista (de S06) con priority badges, quickbutton actions \"Snooze\", \"Acted on\", \"Ignore\".
- **A/B tests activos:** tabla con name, variants, sample size, current significance — link a \"End test\" si concluida.
- **False rejects review:** lista paginada con preview del job + botón \"Promote\" (ejecuta promoción manual).
- **Reports archive:** lista de reportes mensuales con preview + botón download.

### Botones
- **Generate report** genera reporte del mes actual on-demand (con spinner).
- **Export to PDF** en cualquier vista convierte a PDF descargable (usando \`weasyprint\`).

### Workflow automatizado
\`.github/workflows/monthly-report.yml\`:
- Schedule cron: \`'0 8 1 * *'\` (día 1 de cada mes 08:00 UTC = 03:00 COT).
- Genera reporte del mes anterior.
- Envía email con PDF adjunto.

### Snooze functionality
- \"Snooze\": marca como vista, oculta por X días.
- Útil para recommendations recurrentes que ya estás trabajando.

## 🧪 Criterios de Aceptación
- [ ] Página Streamlit con 4 secciones funcionales.
- [ ] Generate report on-demand funciona.
- [ ] Export PDF funciona.
- [ ] Workflow \`monthly-report.yml\` corre exitosamente al menos una vez.
- [ ] Tests E2E (Playwright) de la página.

## 🔗 Dependencias
- Bloqueante: E11-S05, E11-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:reports,epic:E11" \
    "$OPT_EPIC_E11" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E11-S08 — Tests + workflow semanal de análisis
# ---------------------------------------------------------------------------
create_issue \
    "[E11-S08] Tests + workflow semanal de análisis" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Workflow automatizado de análisis semanal y tests cross-épica del módulo analytics. Detección de regresiones y recomendaciones corren sin intervención manual.

## 📐 Alcance Técnico

### \`.github/workflows/weekly-analysis.yml\`
- Schedule cron: \`'0 13 * * 1'\` (lunes 13:00 UTC = 08:00 COT — info al empezar la semana).
- Trigger manual.
- Steps:
  1. \`uv run jobhunter analytics check-regressions\`.
  2. \`uv run jobhunter analytics check-anomalies\`.
  3. \`uv run jobhunter analytics recommendations\` → output a Action Summary.
  4. Si hay regresiones críticas, alerta Telegram.

### Tests integración cross-épica
- **Pipeline completo simulado:** seed DB con datos representativos de 3 meses → run analytics → verificar métricas, regresiones detectadas, recomendaciones coherentes.
- **A/B testing E2E:** crear test → assignar 100 jobs → simular outcomes → conclude → verificar significance.
- **Reporte mensual E2E:** generar reporte completo → verificar estructura, contenido, sin errores LLM.

### Coverage
\`analytics/\` ≥ 80%.

### Performance
Workflow \`weekly-analysis\` debe completar en <3 min.

## 📝 Decisión de horario
Lunes 08:00 COT — recomendaciones y regresiones aterrizan al inicio de la semana de trabajo, no en domingo cuando estás en café.

## 🧪 Criterios de Aceptación
- [ ] Workflow YAML válido + manual trigger exitoso.
- [ ] Action Summary muestra results con tablas markdown.
- [ ] Tests integración pasan en CI.
- [ ] Coverage \`analytics/\` ≥ 80%.
- [ ] Performance <3 min verificada.

## 🔗 Dependencias
- Bloqueante: E11-S03, E11-S05, E11-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:infra,component:analytics,epic:E11" \
    "$OPT_EPIC_E11" \
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
echo " Próximos pasos:"
echo "   1. Verifica los issues en: https://github.com/${FULL_REPO}/issues"
echo "   2. Verifica el proyecto en: https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo "   3. ⚠️  Decision rule: si vas a operar el sistema >3 meses, E11 vale la pena."
echo "       Si <3 meses (ej. ya tienes oferta), considera saltarla."
echo "   4. ⚠️  S05 prompt design crítico: el reporte debe ser HONESTO sobre lowlights."
echo "       LLMs tienden a sugar-coat. El prompt debe pedir 'ser brutal'."
echo "   5. ⚠️  No auto-tuning: el sistema sugiere, NUNCA aplica cambios automáticamente."
echo ""
