#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E6 — AI-Assisted Application Toolkit
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
OPT_EPIC_E06="291fb010"     # E6-Toolkit

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + assistant specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy describiendo propósito, args, returns, raises.
5. **LLM fixtures (si aplica):** Tests que invocan al LLM usan fixtures grabadas; nunca consumen API real en CI.
6. **Costos observables:** Cada llamada LLM se registra en `llm_calls` con `purpose` correcto (cover_letter / ats_keywords / cv_tweaks).
7. **Cero auto-apply:** El sistema NUNCA envía aplicaciones automáticamente a portales. El comando `apply` solo registra que YO ya apliqué manualmente.
8. **Datos personales fuera del repo:** CVs reales en `.local/cv_variants/` (gitignored); solo templates placeholder commiteados.
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story añade un nuevo prompt o template, se versiona en `prompts/` o `templates/` con nomenclatura `vN.md`.'

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

create_label_if_missing "status:ready"             "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E06"                 "a4d9bb" "Épica E06 — AI-Assisted Application Toolkit"
create_label_if_missing "type:feature"             "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"                "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"                 "8b4789" "Comandos CLI"
create_label_if_missing "component:application"    "f6c026" "Toolkit de aplicación, assistant"
create_label_if_missing "component:cv"             "ddd6f3" "CV variants, parser, selector"
create_label_if_missing "component:llm"            "5319e7" "LLM client, prompts, costos"
create_label_if_missing "component:prompts"        "fef2c0" "Prompts versionados"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E06
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E06"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E06-S01 — CV variants: estructura + cargador
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S01] CV variants: estructura + cargador" \
    "## 🎯 Contexto Arquitectónico
Los CVs son insumo crítico para cover letters (S03) y CV tweaks (S05). Se almacenan en archivos markdown estructurados (no JSON/YAML) porque un CV es texto narrativo + estructura — el LLM lee mejor el formato natural. Datos personales reales viven en \`.local/cv_variants/\` gitignored; el repo solo contiene templates placeholder.

## 📐 Alcance Técnico

### Estructura de archivos
- \`cv_variants/ai_python.template.md\`, \`flutter.template.md\`, \`fullstack.template.md\` — templates con placeholders (\`[YOUR_NAME]\`, etc.) commiteados.
- \`.local/cv_variants/ai_python.md\`, etc. — versiones reales con datos personales, **gitignored**.
- Estructura de archivo con headers semánticos parseables:
  \`\`\`markdown
  ## SUMMARY
  …
  ## STACK
  - primary: …
  - secondary: …
  ## EXPERIENCE
  ### [Role] | [Company] | [Dates]
  - [bullet 1]
  ## SKILLS
  - …
  \`\`\`

### Cargador
- \`src/jobhunter/application/cv.py\` con:
  - Pydantic \`CVVariant\`: \`name\`, \`path\`, \`summary\`, \`stack_primary: list[str]\`, \`stack_secondary: list[str]\`, \`experience: list[Experience]\`, \`skills: list[str]\`, \`raw_markdown: str\`.
  - Pydantic \`Experience\`: \`role\`, \`company\`, \`dates\`, \`bullets: list[str]\`.
  - \`load_cv(variant_name) -> CVVariant\` parsea el markdown.
  - \`list_available_variants() -> list[str]\`.
- Settings: \`cv_variants_dir: Path = Path(\".local/cv_variants\")\` con fallback a \`cv_variants/\` para CI.

## ⚠️ Seguridad de datos personales
- \`.local/\` debe estar en \`.gitignore\` (verificar).
- Templates placeholder en repo NUNCA contienen datos reales.

## 🧪 Criterios de Aceptación
- [ ] 3 templates placeholder commiteados.
- [ ] \`.local/\` añadido a \`.gitignore\`.
- [ ] Test: \`load_cv(\"ai_python\")\` parsea correctamente todos los campos.
- [ ] Test: archivo malformado raise error claro.
- [ ] Test: fallback a \`cv_variants/\` si \`.local/\` vacío.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.
- Paralelizable con: E06-S02.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:cv,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S02 — Selector de variante de CV (heurística)
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S02] Selector de variante de CV (heurística)" \
    "## 🎯 Contexto Arquitectónico
Dado un \`Job\` con \`score_data\`, recomienda la variante de CV óptima. Heurística determinística (no LLM) porque es elección entre 3 opciones con info estructurada — más rápido, gratis y predecible que invocar un modelo.

## 📐 Alcance Técnico
- \`src/jobhunter/application/variant_selector.py\` con \`recommend_cv_variant(job: Job) -> VariantRecommendation\`.
- \`VariantRecommendation\` (Pydantic): \`variant_name: str\`, \`confidence: float [0-1]\`, \`reasoning: str\`.

### Lógica heurística (sobre \`job.score_data\`)
- Si \`is_ai_ml_role=true\` o stack incluye \`python\`+\`ai/llm/ml\` → \`ai_python\`.
- Si \`is_flutter_role=true\` o stack incluye \`flutter\`+\`dart\` → \`flutter\`.
- Si \`is_full_stack=true\` o no hay match claro → \`fullstack\`.
- \`confidence\` calculada según claridad del match (1.0 = unambiguous).

### Fallback
Si \`score_data\` no tiene info estructurada (caso edge), keyword matching sobre \`job.title\` + \`job.description\`.

## 📝 Decisión: \`confidence\` en el output
Permite al consumidor saber cuándo el sistema está adivinando. Si \`confidence < 0.5\`, el CLI muestra \"Variant uncertain — review before applying\".

## 🧪 Criterios de Aceptación
- [ ] Test: 5 casos típicos cubiertos (claro AI, claro Flutter, claro fullstack, ambiguo, score_data faltante).
- [ ] \`confidence\` ≥ 0.8 en casos claros.
- [ ] \`confidence\` ≤ 0.5 en caso ambiguo.

## 🔗 Dependencias
- Bloqueante: E06-S01.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S03 — Generador de cover letters (Opus)
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S03] Generador de cover letters (Opus)" \
    "## 🎯 Contexto Arquitectónico
La cover letter es el output más visible del sistema — lo que el reclutador lee. Justifica usar el modelo más caro (\`claude-opus-4-7\`). Costo: ~\$0.05/letter × 30/mes = \$1.50/mes. Valor: diferencia entre tasa de respuesta 5% (genérica) vs 12% (específica al producto/empresa).

## 📐 Alcance Técnico
- \`src/jobhunter/application/cover_letter.py\` con \`async generate_cover_letter(job, cv_variant, llm_client) -> CoverLetterResult\`.
- \`CoverLetterResult\` (Pydantic): \`text\`, \`model\`, \`prompt_version\`, \`cost_usd\`, \`word_count\`.
- Modelo default: \`claude-opus-4-7\`. Configurable vía \`Settings.cover_letter_model\`.
- Prompt versionado en \`prompts/cover_letter/v1.md\` (estructura: \`## SYSTEM\` + \`## USER_TEMPLATE\`).

### Contexto inyectado en el prompt
- JD completa (truncada a 6000 chars).
- CV variant relevante (markdown completo).
- \`cover_letter_angle\` del \`score_data\` (campo \`recommendation.cover_letter_angle\`).
- Candidate profile (mismo bloque YAML del Documento A).

### Validaciones del output (post-procesamiento)
- 250-450 palabras (cover letters efectivas).
- No incluye placeholders sin rellenar (\`[Company]\`, \`[Role]\`, etc.).
- No contiene frases prohibidas (lista en \`prompts/cover_letter/forbidden_phrases.txt\`):
  - \"I am writing to express interest in\"
  - \"I am writing to apply for\"
  - \"amazing experience\"
  - \"passionate about\"
  - (lista vivirá versionada)
- Si validation falla → un retry con prompt reforzado.

### Persistencia
- Si \`Application\` ya existe para el job → persistir en \`applications.cover_letter_text\`.
- Si no existe → cachear in-memory (será persistido cuando \`apply\` se invoque).

## ⚠️ Acción previa
Iterar el prompt v1 contra 3-5 jobs reales antes de cerrar la story. Vale 30 min de prompt design.

## 🧪 Criterios de Aceptación
- [ ] \`prompts/cover_letter/v1.md\` versionado.
- [ ] \`prompts/cover_letter/forbidden_phrases.txt\` versionado.
- [ ] Test con LLM mockeado: generación exitosa.
- [ ] Test: validation falla → retry con prompt reforzado.
- [ ] Test: cover letter persistida en \`applications.cover_letter_text\` cuando \`Application\` existe.
- [ ] Costo registrado en \`llm_calls\` con \`purpose='cover_letter'\`.
- [ ] 3 fixtures reales capturados para regression tests.

## 🔗 Dependencias
- Bloqueante: Épica E04 cerrada, E06-S01.

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S04 — Extractor de keywords ATS
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S04] Extractor de keywords ATS" \
    "## 🎯 Contexto Arquitectónico
Muchas empresas medianas-grandes filtran CVs con ATS antes de que un humano los vea. Si la JD dice \"experience with Kubernetes\" y tu CV solo dice \"container orchestration\", el ATS te filtra. Este extractor te muestra qué términos literales incluir en CV/cover letter.

## 📐 Alcance Técnico
- \`src/jobhunter/application/ats_keywords.py\` con \`async extract_ats_keywords(job, llm_client) -> ATSKeywordsResult\`.
- Modelo: \`claude-haiku-4-5-20251001\` (rápido y barato; este caso no requiere razonamiento profundo). ~\$0.001 por extracción.
- Prompt versionado en \`prompts/ats_keywords/v1.md\`.

### Pydantic models
- \`ATSKeywordsResult\`: \`must_have: list[Keyword]\`, \`nice_to_have: list[Keyword]\`, \`model\`, \`cost_usd\`.
- \`Keyword\`: \`term\`, \`category\` (technical/soft/certification/tool/methodology), \`weight: int [1-10]\`, \`present_in_cv: bool\`.

### Post-procesamiento
- Tras obtener keywords, comparar contra \`cv_variant.raw_markdown\` (case-insensitive substring) y poblar \`present_in_cv\`.
- Soporte de sinónimos básicos: \`Python\` ↔ \`Python 3\` ↔ \`Py3\`. Hardcodear \`KEYWORD_SYNONYMS = {…}\` para v1; embedding-based en E11 si crece.

### Output ordenado
Por \`weight\` descendente — los más importantes primero.

## 🧪 Criterios de Aceptación
- [ ] \`prompts/ats_keywords/v1.md\` versionado.
- [ ] Test con LLM mockeado: extracción exitosa.
- [ ] Test \`_check_presence_in_cv\`: case-insensitive funciona.
- [ ] Test sinónimos: \`Python 3\` en CV matches keyword \`Python\`.
- [ ] Costo registrado en \`llm_calls\` con \`purpose='ats_keywords'\`.

## 🔗 Dependencias
- Bloqueante: Épica E04 cerrada.
- Paralelizable con: E06-S03.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S05 — Sugeridor de tweaks de CV
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S05] Sugeridor de tweaks de CV" \
    "## 🎯 Contexto Arquitectónico
Sugerencias accionables de qué reordenar/destacar en el CV para esta JD específica. Maximiza match-score percibido sin reescribir el CV cada vez. Modelo Sonnet (no Opus) — calidad suficiente para refinamiento, mejor costo.

## 📐 Alcance Técnico
- \`src/jobhunter/application/cv_tweaks.py\` con \`async suggest_cv_tweaks(job, cv_variant, ats_keywords, llm_client) -> CVTweaksResult\`.
- Modelo: \`claude-sonnet-4-6\` (~\$0.02 por sugerencia).
- Prompt versionado en \`prompts/cv_tweaks/v1.md\`.

### Pydantic models
- \`CVTweaksResult\`: \`tweaks: list[Tweak]\`, \`model\`, \`cost_usd\`.
- \`Tweak\`: \`type\` (\`reorder_bullet\` / \`add_keyword\` / \`rewrite_bullet\` / \`add_section\` / \`remove\`), \`target\` (sección o bullet específico), \`original: str | None\`, \`suggested: str | None\`, \`rationale: str\`.

### Disciplina del límite
- **Máximo 5 tweaks por sugerencia.** Sin esto, el LLM tiende a generar 15 sugerencias menores que ahogan las 2-3 importantes.
- Tweaks ordenados por impacto estimado (1 = highest).
- Prompt enfatiza: \"5 tweaks máximo, ordenados por impacto, omite cosméticos\".

## 🧪 Criterios de Aceptación
- [ ] \`prompts/cv_tweaks/v1.md\` versionado.
- [ ] Test: max 5 tweaks en output (validation post-LLM).
- [ ] Test: tweaks ordenados por impacto.
- [ ] Costo registrado en \`llm_calls\` con \`purpose='cv_tweaks'\`.

## 🔗 Dependencias
- Bloqueante: E06-S03, E06-S04.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S06 — Orquestador assist_application(job_id)
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S06] Orquestador \`assist_application(job_id)\`" \
    "## 🎯 Contexto Arquitectónico
Una sola función que orquesta selector + cover letter + ATS keywords + CV tweaks en paralelo. Latencia objetivo <30s. Devuelve \`ApplicationPackage\` listo para que el CLI (S07) lo presente.

## 📐 Alcance Técnico
- \`src/jobhunter/application/assistant.py\` con \`async assist_application(session, job_id, llm_client) -> ApplicationPackage\`.

### Pydantic \`ApplicationPackage\`
- \`job_id\`, \`cv_variant: VariantRecommendation\`, \`cover_letter: CoverLetterResult\`, \`ats_keywords: ATSKeywordsResult\`, \`cv_tweaks: CVTweaksResult\`, \`total_cost_usd: float\`, \`total_duration_ms: int\`, \`estimated_apply_time_min: int\`.

### Orquestación con \`asyncio.gather\`
1. Selector de variante (síncrono, rápido).
2. **En paralelo:** cover letter generation + ATS keywords extraction.
3. CV tweaks suggestion (depende del paso 2).

### Validación previa
Si \`job.tier not in {'A', 'B'}\` → raise \`JobNotAssistableError\`. No malgastar llamadas API en jobs descartados.

### Persistencia / cache
- Si \`Application\` existe: \`cover_letter\` se persiste.
- Si no: cache in-memory por job_id, expira tras 1h o tras \`apply\`.

### \`estimated_apply_time_min\`
Heurística: baseline 8 min, +1 min por cada \`cv_tweak\`, -2 min si todas las ATS keywords ya están en el CV.

## 🧪 Criterios de Aceptación
- [ ] Test integración con sub-componentes mockeados: \`ApplicationPackage\` completo.
- [ ] Test: \`job.tier='REJECT'\` → \`JobNotAssistableError\`.
- [ ] Test paralelización: tiempo total < tiempo serial (verificar con mocks de latencia).
- [ ] Cache funciona: 2 calls al mismo \`job_id\` dentro de 1h → segunda usa cache.

## 🔗 Dependencias
- Bloqueante: E06-S02, E06-S03, E06-S04, E06-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S07 — CLI: assist + apply + letter
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S07] CLI: \`jobhunter assist\` + \`apply\` + \`letter\`" \
    "## 🎯 Contexto Arquitectónico
Workflow ergonómico para operación diaria. Telegram alert → terminal → assist → ajustar → aplicar manualmente → registrar. Sin estos comandos, todo el toolkit es código sin interfaz.

## 📐 Alcance Técnico

### \`jobhunter assist <job_id>\`
Flags:
- \`--output-dir DIR\` (default: stdout) — escribir paquete a archivos en directorio.
- \`--no-letter\` — solo variante + tweaks + keywords (no genera cover letter, ahorra costo).
- \`--cv-variant NAME\` — overridear selector de variante.

Output: tabla rich con resumen + bloques formateados (Markdown rendering) con cover letter, tweaks, keywords.

### \`jobhunter letter <job_id>\`
Solo cover letter. Más rápido cuando ya tienes variante decidida.
Flags:
- \`--output FILE\` (default: stdout).
- \`--cv-variant NAME\`.

### \`jobhunter apply <job_id>\`
Registra aplicación enviada manualmente.
Flags:
- \`--method METHOD\` (web/email/linkedin/referral, **required**).
- \`--cv-variant NAME\` (**required**).
- \`--contact-name NAME\`, \`--contact-email EMAIL\` (opcionales).
- \`--notes TEXT\` (opcional).

Acción:
- Crea \`Application\` con \`status='applied'\`.
- Transición de \`Job\` a \`status='applied'\`.
- Si hay cover letter en cache (de \`assist\` previo), la persiste automáticamente.

## ⚠️ Cero auto-apply
\`apply\` SOLO registra que YO ya envié manualmente. No invoca Playwright, no toca portales. Esto es decisión arquitectónica explícita (ver Documento J §10).

## 🧪 Criterios de Aceptación
- [ ] Tests CLI con \`typer.testing.CliRunner\` para los 3 comandos.
- [ ] \`assist --no-letter\` no llama a Opus (verificar via \`llm_calls\`).
- [ ] \`apply\` requiere \`--method\` y \`--cv-variant\` (falla sin ellos).
- [ ] Test E2E: \`assist\` cachea cover letter → \`apply\` la persiste.

## 🔗 Dependencias
- Bloqueante: E06-S06.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E06-S08 — Tests con fixtures + tracker de aplicaciones
# ---------------------------------------------------------------------------
create_issue \
    "[E06-S08] Tests con fixtures + tracker de aplicaciones" \
    "## 🎯 Contexto Arquitectónico
Tests end-to-end con fixtures reales. Verificación crítica de que el ciclo \"tier-A → assist → apply → tracker actualizado\" es robusto. Capturar fixtures gasta ~\$0.20 una vez; ahorro infinito en CI.

## 📐 Alcance Técnico

### Fixtures requeridas en \`tests/fixtures/application_assistant/\`
- \`cover_letter_response_python_ai.txt\` (output real del Opus para job python AI).
- \`cover_letter_response_flutter.txt\`.
- \`ats_keywords_response.json\`.
- \`cv_tweaks_response.json\`.

### MockLLMClient extendido
- Reusar el de E04-S08, extender para devolver fixtures de cover letters / keywords / tweaks según pattern del job + purpose.

### Tests end-to-end requeridos
- [ ] \`assist_application\` con job tier-A → \`ApplicationPackage\` completo y válido.
- [ ] \`assist_application\` con job tier=REJECT → \`JobNotAssistableError\`.
- [ ] \`apply\` crea \`Application\` con todos los campos correctos.
- [ ] Cover letter cacheada de \`assist\` previo se persiste en \`apply\`.
- [ ] Tests del selector de variante: 5 casos típicos cubiertos.

### Coverage
≥ 75% en módulo \`application/\`.

## 🧪 Criterios de Aceptación
- [ ] 4 fixtures capturados, sanitizados, commiteados.
- [ ] \`MockLLMClient\` extendido funciona para los 3 purposes nuevos.
- [ ] Tests end-to-end pasan en CI sin red real.
- [ ] Coverage ≥ 75% en \`application/\`.

## 🔗 Dependencias
- Bloqueante: E06-S06, E06-S07.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:test,component:application,epic:E06" \
    "$OPT_EPIC_E06" \
    "$OPT_PRIORITY_P1"

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
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S01: añadir '.local/' a .gitignore."
echo "   4. ⚠️  ANTES DE IMPLEMENTAR S03: iterar prompts/cover_letter/v1.md"
echo "       contra 3-5 jobs reales hasta que el output suene en tu voz."
echo ""
