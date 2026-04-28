#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E4 — AI Scoring Engine
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
OPT_EPIC_E04="1855a020"     # E4-Scoring

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + LLM specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy describiendo propósito, args, returns, raises.
5. **LLM fixtures (si aplica):** Tests que invocan al LLM usan fixtures grabadas en `tests/fixtures/scoring_responses/`; nunca consumen API real en CI.
6. **Costos:** Cada llamada al LLM se registra en tabla `llm_calls` con tokens y costo USD calculado.
7. **Pre-commit:** Todos los hooks pasan en local.
8. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
9. **Documentación:** Si la story modifica el prompt maestro, se crea nueva versión en `prompts/scoring/vN.md`; si modifica el schema de respuesta, `docs/scoring.md` se actualiza.'

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

create_label_if_missing "status:ready"          "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E04"              "b60205" "Épica E04 — AI Scoring Engine"
create_label_if_missing "type:feature"         "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"             "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"              "8b4789" "Comandos CLI"
create_label_if_missing "component:scoring"     "ff7a00" "Motor de scoring, prompts, scorer"
create_label_if_missing "component:llm"         "5319e7" "Cliente LLM, pricing, budget"
create_label_if_missing "component:db"          "d93f0b" "Migraciones, repos, persistencia"
create_label_if_missing "component:prompts"     "fef2c0" "Prompts versionados"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E04
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E04"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E04-S01 — Esquema Pydantic para respuesta del scoring
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S01] Esquema Pydantic para respuesta del scoring" \
    "## 🎯 Contexto Arquitectónico
La IA puede devolver JSON malformado, con campos extra, o con valores fuera de rango. Un schema Pydantic strict atrapa esto **antes** de que contamine la DB. Sin este filtro, un bug en el prompt podría poblar \`Job.score_data\` con basura silenciosamente.

## 📐 Alcance Técnico
- \`src/jobhunter/scoring/schema.py\` con clase \`ScoringResult(BaseModel)\` que refleja exactamente el schema del Documento A §3.
- Sub-modelos: \`CompanyInfo\`, \`RoleInfo\`, \`CompensationInfo\`, \`LogisticsInfo\`, \`MatchAnalysis\`, \`Recommendation\`.
- Enums: \`Tier\` (A/B/C/REJECT), \`Action\`, \`Priority\`, \`RemoteType\`, \`TimezoneRequirement\`, \`ContractType\`, \`CompanyStage\`, \`Seniority\`.
- Validators custom:
  - \`fit_score\` ∈ [0, 100].
  - Si \`tier=REJECT\`, debe haber al menos 1 \`red_flag\`.
  - Si \`tier='A'\`, no puede haber \`red_flags\`.
- \`InvalidScoringResponse\` para casos donde la IA decide que la oferta es spam: \`{valid: false, reason: str}\`.
- Función \`parse_scoring_response(raw_text: str) -> ScoringResult | InvalidScoringResponse\`:
  - Tolera markdown fences (\`\`\`json … \`\`\`) — los strippea con regex antes de parsear.
  - Raise \`ValidationError\` si JSON inválido o no cumple schema.
- \`model_config = ConfigDict(extra='forbid')\` — strict mode para detectar drift del prompt.

## 🧪 Criterios de Aceptación
- [ ] Test: respuesta válida típica → \`ScoringResult\` poblado correctamente.
- [ ] Test: respuesta REJECT con red_flags → válido.
- [ ] Test: \`tier='A'\` con red_flags → \`ValidationError\`.
- [ ] Test: respuesta con markdown fences → parsea OK.
- [ ] Test: JSON malformado → \`ValidationError\`.
- [ ] Test: campo extra inesperado → \`ValidationError\` (extra='forbid').
- [ ] Test: \`{valid: false, reason: ...}\` → devuelve \`InvalidScoringResponse\`.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada (necesitamos persistir).

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:scoring,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S02 — Cargador de prompt versionado
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S02] Cargador de prompt versionado" \
    "## 🎯 Contexto Arquitectónico
El prompt maestro vive en archivos \`.md\` versionados (\`prompts/scoring/v1.md\`, \`v2.md\`, …) commiteados al repo. Cada cambio queda en git history, es diffable en PRs, y cada \`Job\` persiste qué versión lo scoreó (\`Job.score_version\`) — habilita análisis de regresión cuando se itere el prompt.

## 📐 Alcance Técnico
- Crear \`prompts/scoring/v1.md\` con el contenido del Documento A. Estructura:
  \`\`\`
  ## SYSTEM
  …
  ## USER_TEMPLATE
  …
  \`\`\`
  El loader parsea por estos headers.
- \`src/jobhunter/scoring/prompt.py\`:
  - \`load_prompt(version: str = 'latest') -> ScoringPrompt\` — \`'latest'\` resuelve a la versión semánticamente mayor.
  - \`render_user_prompt(template, job) -> str\` — sustituye \`{title}\`, \`{company}\`, \`{description}\`, etc. usando \`str.format_map()\`.
  - Raise \`PromptRenderError\` si placeholder no encontrado en el job.
- \`ScoringPrompt\` (Pydantic): \`version\`, \`system_prompt\`, \`user_template\`, \`loaded_from\`.

## 📝 Decisión
\`str.format_map\` es suficiente; no hace falta Jinja2. Mantiene cero dependencias adicionales.

## 🧪 Criterios de Aceptación
- [ ] Test: \`load_prompt('v1')\` carga correctamente.
- [ ] Test: \`load_prompt('latest')\` resuelve a la versión más alta.
- [ ] Test: \`render_user_prompt\` sustituye todos los placeholders.
- [ ] Test: placeholder no encontrado → \`PromptRenderError\`.
- [ ] Test: \`load_prompt('v999')\` → error claro de archivo no encontrado.

## 🔗 Dependencias
- Bloqueante: E04-S01.
- Paralelizable con: E04-S03.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:prompts,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S03 — Anthropic API client wrapper
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S03] Anthropic API client wrapper" \
    "## 🎯 Contexto Arquitectónico
Wrapper centralizado sobre el SDK \`anthropic\` con retry, timeout, manejo de errores y captura de tokens/costo. Servirá tanto al scorer (S04) como al generador de cover letters (E6) y al de outreach (E9). Centralizar evita duplicar lógica de retry/pricing en cada consumidor.

## 📐 Alcance Técnico
- \`src/jobhunter/llm/__init__.py\` y \`src/jobhunter/llm/anthropic_client.py\` con clase \`AnthropicLLMClient\`.
- Método \`async complete(system: str, user: str, model: str, max_tokens: int = 1500) -> LLMResponse\`.
- \`LLMResponse\` (Pydantic): \`text\`, \`model\`, \`input_tokens\`, \`output_tokens\`, \`cost_usd\`, \`duration_ms\`, \`stop_reason\`.
- Retry con \`tenacity\`: exponential backoff (1s, 2s, 4s, jitter, max 3) en \`RateLimitError\`, \`APIConnectionError\`, \`InternalServerError\`.
- **No retry** en \`BadRequestError\`, \`AuthenticationError\` (fallar rápido).
- Timeout configurable (default 60s).
- \`src/jobhunter/llm/pricing.py\`:
  \`\`\`python
  # USD per million tokens, verified YYYY-MM-DD
  PRICING = {
      \"claude-haiku-4-5-20251001\": {\"input\": 1.0, \"output\": 5.0},
      \"claude-sonnet-4-6\": {\"input\": 3.0, \"output\": 15.0},
      \"claude-opus-4-7\": {\"input\": 15.0, \"output\": 75.0},
  }
  def calculate_cost_usd(model, input_tokens, output_tokens) -> float: ...
  \`\`\`
- Logging \`structlog\` por cada llamada: \`model\`, \`input_tokens\`, \`output_tokens\`, \`cost_usd\`, \`duration_ms\`, \`attempt\`.

## ⚠️ Acción previa
Verificar pricing actual en https://docs.claude.com/en/docs/about-claude/pricing antes de hardcodear. Cambia ocasionalmente.

## 🧪 Criterios de Aceptación
- [ ] Test: respuesta exitosa devuelve \`LLMResponse\` con todos los campos.
- [ ] Test: \`RateLimitError\` → retry exitoso.
- [ ] Test: \`AuthenticationError\` → no retry, falla inmediato.
- [ ] Test: cálculo de costo correcto para los 3 modelos.
- [ ] mypy strict pasa.
- [ ] Tests usan \`anthropic\` SDK mockeado (no consumen API real).

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.
- Paralelizable con: E04-S02.
- Nuevas deps: \`anthropic\` (probablemente ya en pyproject), \`tenacity\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:llm,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S04 — Scorer principal: JobScorer.score(job)
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S04] Scorer principal: \`JobScorer.score(job)\`" \
    "## 🎯 Contexto Arquitectónico
Unidad atómica del scoring: toma un \`Job\`, lo manda al modelo con el prompt maestro, valida la respuesta, y devuelve un \`ScoringOutcome\` listo para que el pipeline (S05) lo persista. Encapsula la lógica de retry de parsing (modelos pequeños como Haiku ocasionalmente meten texto antes/después del JSON; un retry con prompt reforzado salva ~80% de estos casos).

## 📐 Alcance Técnico
- \`src/jobhunter/scoring/scorer.py\` con clase \`JobScorer\`.
- Constructor: \`JobScorer(llm_client, prompt_version='latest', model='claude-haiku-4-5-20251001')\`.
- Método \`async score(job: Job) -> ScoringOutcome\`.
- \`ScoringOutcome\` (Pydantic): \`result: ScoringResult | InvalidScoringResponse\`, \`model\`, \`prompt_version\`, \`cost_usd\`, \`duration_ms\`, \`raw_response: str\`.
- Trunca \`job.description\` a max 8000 chars antes de pasar al prompt (~2000 tokens, deja espacio para resto del context).
- Si parsing falla en primer intento, **un retry** con instrucción reforzada (\"Respond with valid JSON only, no preamble or postamble\"); si falla de nuevo, raise \`ScoringParseError\` incluyendo \`raw_response\` para debug.
- Excepciones custom en \`src/jobhunter/scoring/errors.py\`: \`ScoringError\` (base), \`ScoringParseError\`, \`ScoringAPIError\`.
- \`_truncate_description(text, max_chars=8000)\` corta inteligente (en boundary de palabra/párrafo, no a media palabra).

## 🧪 Criterios de Aceptación
- [ ] Test: scoring exitoso → \`ScoringOutcome\` válido.
- [ ] Test: primer intento devuelve JSON malformado, retry exitoso → \`ScoringOutcome\` válido.
- [ ] Test: dos intentos fallan → \`ScoringParseError\` con \`raw_response\` accesible.
- [ ] Test: respuesta \`{valid: false}\` → \`ScoringOutcome\` con \`InvalidScoringResponse\`.
- [ ] Test: descripción de 20000 chars se trunca correctamente.

## 🔗 Dependencias
- Bloqueante: E04-S01, E04-S02, E04-S03.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:scoring,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S05 — Pipeline batch + transición de estados
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S05] Pipeline batch + transición de estados" \
    "## 🎯 Contexto Arquitectónico
El pipeline es lo que el cron de E8 invocará. Toma jobs en \`status='new'\`, los scoree en paralelo controlado, y hace las transiciones de estado correctas según tier. **Idempotencia es crítica:** filtrar por \`status='new'\` garantiza que re-correr no re-procesa lo ya scoreado. Aislamiento de fallos: si un job falla, no detiene el batch.

## 📐 Alcance Técnico
- \`src/jobhunter/scoring/pipeline.py\` con \`async score_pending_jobs(session, limit=100, concurrency=5) -> ScoringBatchReport\`.
- Selecciona jobs \`status='new'\` ordenados por \`scraped_at ASC\` (FIFO).
- Procesa en paralelo con \`asyncio.Semaphore(concurrency)\` (default 5 — respeta rate limits Anthropic Tier 1).

### Lógica de transición de estado
| Resultado | Persistencia | \`status\` final |
|---|---|---|
| Tier A | score_data + score_model + score_version | \`queued\` |
| Tier B | mismo | \`queued\` |
| Tier C | mismo | \`manual_review\` |
| Tier REJECT | mismo | \`rejected\` |
| Respuesta \`valid=false\` | razón en \`score_data\` | \`archived\` |
| Error API/parsing | **NO modifica el job** | sigue en \`new\` (retry próxima corrida) |

### Re-scoring (variante 7A del Documento A)
- Función separada \`async rescore_jobs(filter, with_model)\`.
- Permite re-scorear tier A actuales con Sonnet para segunda opinión.

### Reporte
- \`ScoringBatchReport\` (Pydantic): \`total_processed\`, \`success_count\`, \`failed_count\`, \`tier_distribution: dict[Tier, int]\`, \`total_cost_usd\`, \`duration_seconds\`.

## 🧪 Criterios de Aceptación
- [ ] Test: batch de 10 jobs mockeados, mix de tiers → todos persistidos correctamente.
- [ ] Test: 1 job falla con \`ScoringAPIError\`, otros 9 ok → batch completa, job fallido sigue en \`status='new'\`.
- [ ] Test idempotencia: correr 2 veces consecutivas → segunda corrida 0 procesados.
- [ ] Test: \`rescore_jobs(filter={'tier': 'A'}, with_model='claude-sonnet-4-6')\` re-procesa correctamente.

## 🔗 Dependencias
- Bloqueante: E04-S04.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:scoring,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S06 — Tracking de costos + alertas de budget
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S06] Tracking de costos + alertas de budget" \
    "## 🎯 Contexto Arquitectónico
Observabilidad sobre costos LLM y failsafe ante bugs (ej. loop infinito de retry que generaría \$200 sin avisar). Tabla \`llm_calls\` separada (no extensión de \`jobs\`) porque también capturará cover letters (E6), outreach (E9), futuros usos — permite analytics cross-purpose.

## 📐 Alcance Técnico

### Tabla nueva: \`llm_calls\`
- Migration Alembic.
- Columnas: \`id\`, \`called_at\`, \`model\`, \`purpose\` (scoring/cover_letter/outreach), \`input_tokens\`, \`output_tokens\`, \`cost_usd\`, \`duration_ms\`, \`success: bool\`, \`job_id: UUID | null\` (FK opcional).

### Repo
- \`src/jobhunter/db/repos/llm_calls.py\` con \`LLMCallRepo\`:
  - \`record_call(...)\` — registra cualquier llamada (incluso fallidas con \`success=false\`).
  - \`monthly_total_usd(year, month) -> float\`.
  - \`weekly_total_usd(date) -> float\`.

### Integración
- \`AnthropicLLMClient\` (S03) inyecta \`LLMCallRepo\`; cada \`complete()\` registra automáticamente.

### Budget
- Nueva config en \`Settings\`: \`llm_monthly_budget_usd: float = 25.0\`.
- \`src/jobhunter/llm/budget.py\` con:
  - \`check_budget(session) -> BudgetStatus\` (\`current_month_spend\`, \`budget\`, \`pct_used\`, \`is_exceeded\`, \`is_warning\` si >80%).
  - Excepción \`BudgetExceededError\`.
- \`JobScorer.score()\` (de S04) consulta \`check_budget()\` antes de cada llamada y raise \`BudgetExceededError\` si excede.

### CLI
- \`jobhunter scoring stats\` con tabla: total mes, total semana, breakdown por modelo, tasa de éxito.

## 🧪 Criterios de Aceptación
- [ ] Migration de \`llm_calls\` aplicada.
- [ ] Test: \`record_call\` persiste correctamente.
- [ ] Test: \`monthly_total_usd\` agrega correctamente.
- [ ] Test: budget excedido → \`BudgetExceededError\` antes de llamar API.
- [ ] Comando \`scoring stats\` muestra valores coherentes.

## 🔗 Dependencias
- Bloqueante: E04-S03.
- Paralelizable con: E04-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:llm,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S07 — CLI: jobhunter score + comandos auxiliares
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S07] CLI: \`jobhunter score\` + comandos auxiliares" \
    "## 🎯 Contexto Arquitectónico
Comandos para operación manual del scoring: dev/debug, re-scoring tras cambios de prompt, scoring puntual de un job problemático.

## 📐 Alcance Técnico

### \`jobhunter score\`
Procesa batch de jobs en \`status='new'\`. Flags:
- \`--limit N\` (default: 100).
- \`--concurrency N\` (default: 5).
- \`--model NAME\` (default: from settings).
- \`--prompt-version VER\` (default: 'latest').
- \`--dry-run\` — no persiste.

### \`jobhunter score-job <JOB_ID>\`
Score puntual de un job específico. Imprime \`raw_response\` completa para debug. No persiste por defecto; flag \`--persist\` lo activa.

### \`jobhunter rescore\`
Re-procesa jobs ya scoreados. Flags:
- \`--tier A\` — filtra por tier actual.
- \`--with-model NAME\` — modelo a usar (variante 7A: re-scorear tier A con Sonnet).
- \`--limit N\`.

### \`jobhunter scoring stats\`
(De S06) — tabla con costos y métricas.

### Output
- \`rich.table.Table\` para resúmenes.
- \`rich.progress.Progress\` durante batch.
- Exit code 1 si tasa de éxito < 90% (señal para alerting en cron).

## 🧪 Criterios de Aceptación
- [ ] Tests CLI con \`typer.testing.CliRunner\` para cada comando.
- [ ] Test: \`--dry-run\` no escribe a DB.
- [ ] Test: exit code 1 si fallos > 10%.
- [ ] \`--help\` produce output legible para cada comando.

## 🔗 Dependencias
- Bloqueante: E04-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:scoring,epic:E04" \
    "$OPT_EPIC_E04" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E04-S08 — Tests con fixtures de respuestas IA
# ---------------------------------------------------------------------------
create_issue \
    "[E04-S08] Tests con fixtures de respuestas IA" \
    "## 🎯 Contexto Arquitectónico
Tests que validan el flujo end-to-end del scoring sin consumir la API real. Capturar 8 fixtures variados gasta ~\$0.02 una sola vez; después CI corre gratis y reproducible. Sin esto, cada PR costaría dinero en API y dependería de red.

## 📐 Alcance Técnico

### Fixtures requeridas en \`tests/fixtures/scoring_responses/\`
- \`tier_a_python_ai.json\` — Senior Python/AI, salario alto, B2B-friendly.
- \`tier_a_flutter.json\` — Flutter senior, remote global.
- \`tier_b_borderline.json\` — match decente pero no ideal.
- \`tier_c_manual_review.json\` — caso ambiguo, salario al límite.
- \`reject_eu_only.json\` — REJECT por requerir EU work permit.
- \`reject_low_salary.json\` — REJECT por salario debajo de floor.
- \`invalid_response.json\` — \`{valid: false, reason: ...}\`.
- \`malformed_json.txt\` — JSON roto (para test de retry de parsing).

### MockLLMClient
- En \`tests/conftest.py\`: clase que devuelve respuesta de fixture según pattern del job input.
- Ej: si \`job.title.lower()\` contiene \"python\" + \"ai\" → \`tier_a_python_ai.json\`.

### Tests end-to-end requeridos
- [ ] Pipeline completo: 20 jobs mockeados con mix variado → distribución de tiers correcta en DB.
- [ ] Estado correcto post-scoring: tier A → \`queued\`, REJECT → \`rejected\`, etc.
- [ ] \`BudgetExceededError\` cuando se excede budget configurado.
- [ ] Test de \`score_data\` persistido es válido contra el schema Pydantic (round-trip).

## 📝 Notas
**Fixtures ≠ snapshots.** Los fixtures son inputs estables. Si el prompt cambia y produce respuestas distintas, los fixtures siguen siendo válidos históricamente — los tests del pipeline siguen pasando porque solo verifican que el flujo procesa correctamente cualquier respuesta válida.

Validar que el prompt actual produce el tier *esperado* para X job es otro test (más caro, opcional, no en este story).

## 🧪 Criterios de Aceptación
- [ ] 8 fixtures capturados, sanitizados, commiteados.
- [ ] \`MockLLMClient\` implementado en \`conftest.py\`.
- [ ] Tests end-to-end pasan en CI sin red real.
- [ ] Coverage ≥ 80% en módulo \`scoring/\`.

## 🔗 Dependencias
- Bloqueante: E04-S04, E04-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:test,component:scoring,epic:E04" \
    "$OPT_EPIC_E04" \
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
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S03: verifica el pricing actual de Claude API en"
echo "      https://docs.claude.com/en/docs/about-claude/pricing"
echo ""
