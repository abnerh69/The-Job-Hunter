#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E14 — Onboarding Automation & Profile Generation
# =============================================================================
# Requisitos: gh (GitHub CLI) instalado y autenticado (`gh auth login`)
# y jq instalado.
#
# IMPORTANTE: Antes de ejecutar este script, asegúrate de que existe la opción
# "E14-Onboarding" (o similar, comenzando con "E14") en el campo Epic del
# Project del repositorio. El script intentará auto-descubrirla; si falla,
# crearla manualmente desde la UI del Project o vía API GraphQL.
#
# CONTEXTO: E14 es una épica nueva (no estaba en el plan original) que
# automatiza la creación del perfil del candidato y sus variantes de CV a
# partir de un master resume subido por el usuario. Cambia arquitectura:
# perfil pasa de archivos a entidades de primera clase en BD. Ver
# `docs/adr/ADR-008-profile-in-db.md` para el rationale.
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
# Priority (heredados de scripts previos)
OPT_PRIORITY_P0="6f783caf"  # P0-MVP Critical
OPT_PRIORITY_P1="72f5e96b"  # P1-MVP Desirable
OPT_PRIORITY_P2="4a355e1b"  # P2-Post-MVP

# Epic E14 — auto-descubierto debajo
OPT_EPIC_E14=""

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + E14 specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **Logging coherente:** Toda lógica nueva usa `structlog` con campos estándar (`timestamp`, `level`, `module`, `event`, `correlation_id`, `entity_id` cuando aplica).
6. **Multi-profile-aware:** Cualquier código que lea perfil debe soportar múltiples perfiles activos (no asumir 1).
7. **Migration safety:** Si la story añade tabla o columna, la migration tiene `downgrade()` funcional probado (upgrade → downgrade → upgrade → idempotente).
8. **Sin regresión cross-épica:** Tests de E04, E06, E09 (que consumen el perfil) siguen pasando con la nueva lógica de DB.
9. **Audit trail:** Mutaciones del perfil (INSERT/UPDATE/DELETE en `candidate_profiles` o `cv_variants`) generan entry en `audit_log` (cuando E13-S05 esté cerrada).
10. **Pre-commit:** Todos los hooks pasan en local.
11. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
12. **Documentación:** Si la story toca el flujo de onboarding o la estructura del perfil, actualizar `HUMAN_SETUP.md` y/o `docs/data_model.md`.'

# ---------------------------------------------------------------------------
# 🛠️ FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

discover_epic_option_id() {
    local epic_prefix="$1"
    gh api graphql -f query="
    query {
        node(id: \"$FIELD_EPIC\") {
            ... on ProjectV2SingleSelectField {
                options { id name }
            }
        }
    }" --jq ".data.node.options[] | select(.name | startswith(\"$epic_prefix\")) | .id" 2>/dev/null
}

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
# 🔍 AUTO-DESCUBRIMIENTO DEL OPTION ID DE LA ÉPICA E14
# ---------------------------------------------------------------------------
echo -e "${YELLOW}Auto-descubriendo OPT_EPIC_E14 desde el Project...${NC}"
OPT_EPIC_E14=$(discover_epic_option_id "E14")

if [ -z "$OPT_EPIC_E14" ]; then
    echo -e "${RED}❌ ERROR:${NC} No se encontró opción que comience con 'E14' en el campo Epic del Project #${PROJECT_NUMBER}."
    echo ""
    echo "   Para resolverlo, crea la opción 'E14-Onboarding' (o similar) en:"
    echo "   https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}/settings/fields/${FIELD_EPIC#PVTSSF_}"
    echo ""
    echo "   Alternativa CLI (requiere obtener el field ID exacto sin prefijo):"
    echo "   gh api graphql -f query='mutation {"
    echo "     updateProjectV2Field(input: {"
    echo "       fieldId: \"${FIELD_EPIC}\""
    echo "       singleSelectOptions: [{name: \"E14-Onboarding\", color: TEAL, description: \"Épica E14\"}]"
    echo "     }) { projectV2Field { ... on ProjectV2SingleSelectField { options { id name } } } }"
    echo "   }'"
    echo ""
    echo "   Luego re-ejecuta este script."
    exit 1
fi

echo -e "  ${GREEN}✓${NC} OPT_EPIC_E14 = $OPT_EPIC_E14"
echo ""

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

# Labels nuevos para E14
create_label_if_missing "epic:E14"                   "b2dfdb" "Épica E14 — Onboarding Automation & Profile Generation"
create_label_if_missing "component:onboarding"       "00897b" "Wizard, resume parsing, profile/cv generation"
create_label_if_missing "component:profile"          "558b2f" "Candidate profile + CV variants (BD entities)"
create_label_if_missing "component:llm"              "d81b60" "Llamadas LLM (Opus, Sonnet, Haiku) y prompts"
create_label_if_missing "component:db"               "0277bd" "Schema, migrations, repos"

# Labels existentes (idempotente)
create_label_if_missing "status:ready"               "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "type:feature"               "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"                  "fbca04" "Tests, fixtures, security scans"
create_label_if_missing "type:cli"                   "8b4789" "Comandos CLI"
create_label_if_missing "type:docs"                  "c5def5" "Documentación, runbooks"
create_label_if_missing "type:refactor"              "fef2c0" "Cross-cutting refactor"
create_label_if_missing "type:infra"                 "1d76db" "Infraestructura, deploy"
create_label_if_missing "component:dashboard"        "9c27b0" "Páginas y endpoints"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E14
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E14 (Onboarding)"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E14-S01 — Schema BD: candidate_profiles + history + cv_variants
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S01] Schema BD: candidate_profiles + history + cv_variants + experiencias" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** persistir el perfil del candidato y sus variants de CV en Postgres con schema híbrido y versionado, **para que** el yaml + markdowns dejen de ser fuente de verdad y la información del usuario sea entidad de primera clase en la BD.

Esta story implementa el cambio arquitectónico documentado en \`docs/adr/ADR-008-profile-in-db.md\`. El **schema híbrido (Eje A3)** elegido por el usuario combina columnas para campos queryables, \`TEXT[]\` para listas, y \`JSONB\` para mapas/configs flexibles.

## 📐 Alcance Técnico

### Migration Alembic — 4 tablas

\`\`\`sql
CREATE TABLE candidate_profiles (
    id UUID PK DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,           -- \"Python AI Senior\", \"Flutter Mobile\"
    is_active BOOLEAN DEFAULT TRUE,
    seniority VARCHAR(50),
    years_experience INT,
    country VARCHAR(50),
    work_authorization TEXT,
    timezone_home VARCHAR(50),            -- \"UTC-5\"
    overlap_max_hours_cet INT,
    preferred_overlap_cet INT,
    primary_stack TEXT[],
    secondary_stack TEXT[],
    domains TEXT[],
    languages JSONB,                      -- {\"english\": \"fluent\", ...}
    compensation JSONB,                   -- {floor_usd_month, target_usd_month, ...}
    contract_preferences TEXT[],
    hard_blockers TEXT[],
    soft_negatives TEXT[],
    positive_signals TEXT[],
    payment_methods_ok TEXT[],
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE candidate_profile_history (
    id UUID PK,
    profile_id UUID FK REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    snapshot JSONB NOT NULL,              -- copia completa pre-cambio
    changed_at TIMESTAMPTZ DEFAULT now(),
    changed_by VARCHAR(100),              -- \"user\", \"wizard\", \"cli\"
    change_reason TEXT
);

CREATE TABLE cv_variants (
    id UUID PK DEFAULT gen_random_uuid(),
    profile_id UUID FK REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,            -- \"ai_python_engineer\", user-defined
    display_name VARCHAR(100),            -- \"AI Python Engineer\" human-friendly
    target_role_keywords TEXT[],          -- [\"python\", \"ml engineer\", \"ai\"]
    target_stack TEXT[],
    target_seniority VARCHAR(50),
    summary TEXT,
    skills TEXT[],
    raw_markdown TEXT,                    -- regenerable, útil para diff/export
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(profile_id, name)
);

CREATE TABLE cv_variant_experiences (
    id UUID PK,
    cv_variant_id UUID FK REFERENCES cv_variants(id) ON DELETE CASCADE,
    role VARCHAR(200),
    company VARCHAR(200),
    start_date DATE,
    end_date DATE,                        -- NULL = current
    bullets TEXT[],
    sort_order INT
);
\`\`\`

### Índices
- \`(is_active)\` parcial sobre \`candidate_profiles\`.
- \`(profile_id)\` sobre \`cv_variants\`.
- \`(cv_variant_id, sort_order)\` sobre \`cv_variant_experiences\`.
- \`(profile_id, changed_at DESC)\` sobre history.

### Trigger SQL
BEFORE UPDATE en \`candidate_profiles\` que copia el row pre-cambio a \`candidate_profile_history\` automáticamente (con \`change_reason = NEW.notes\` o NULL). Trigger en SQL es preferible a hacerlo en Python: garantiza que cualquier UPDATE — incluso uno hecho directamente con \`psql\` — quede trazado. Para \`INSERT\` no aplica (la versión inicial vive en el row mismo).

### Modelos SQLAlchemy
En \`db/models.py\`: \`CandidateProfile\`, \`CandidateProfileHistory\`, \`CVVariant\`, \`CVVariantExperience\`. Relationships configuradas (cascade delete, back_populates).

### Repos
En \`db/repos/\`:
- \`CandidateProfileRepo\` con \`list_active\`, \`get_active_by_id\`, \`create\`, \`update_with_history\`, \`deactivate\`, \`list_history\`.
- \`CVVariantRepo\` con \`list_by_profile\`, \`get_by_name\`, \`create_with_experiences\`, \`update_markdown\`.

### Tests
Tests integración: CRUD básico, trigger de history dispara, cascade delete funciona, multi-profile activos coexisten sin conflicto.

## 🛠️ Tasks

- Migration Alembic con las 4 tablas + índices + trigger.
- Modelos SQLAlchemy.
- Repos con tipos correctos para mypy strict.
- Tests integración (\`tests/integration/test_candidate_profile_repo.py\`).

## 📝 Notas

- **Trigger de history en SQL es preferible a hacerlo en Python**: garantiza que cualquier UPDATE — incluso uno hecho directamente con \`psql\` — quede trazado. Para \`INSERT\` no aplica.
- **\`is_active\` permite múltiples TRUE simultáneos.** El usuario decide cuántos perfiles tiene corriendo a la vez. La UI advierte si activa más de 3 por costo.
- **Decisión Eje A3 (híbrido)** documentada en ADR-008. Considerada pero descartada A1 (JSONB blob, queries feas) y A2 (normalización completa, joins en cada lectura).
- **Decisión Eje E1 (sin cifrado MVP):** disk encryption EBS + auth dashboard cubren PII. Si el sistema se abre a multi-usuario, añadir cifrado de campos PII vía \`crypto.py\`.

## 🧪 Criterios de Aceptación
- [ ] Migration Alembic crea las 4 tablas con todas las columnas listadas.
- [ ] Migration tiene \`downgrade()\` funcional probado (cycle upgrade → downgrade → upgrade).
- [ ] Trigger BEFORE UPDATE captura snapshot a history (verificable con UPDATE de prueba).
- [ ] Cascade delete funciona: borrar perfil borra sus variants y experiencias.
- [ ] Multi-profile: 3 rows con \`is_active=true\` coexisten sin conflicto.
- [ ] Modelos SQLAlchemy con relationships y type hints.
- [ ] Repos con todos los métodos listados.
- [ ] Tests integración cubren CRUD + trigger + cascade.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada (DB infra).

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:db,component:profile,component:onboarding,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S02 — ResumeIngestor (PDF/MD/DOCX → ResumeData)
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S02] ResumeIngestor: parser de CV con LLM (PDF/MD/DOCX → ResumeData)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** un servicio que tome un archivo de CV (PDF, Markdown o DOCX) y devuelva los datos estructurados, **para que** los generadores downstream tengan input estructurado en lugar de texto crudo.

Este es el primer eslabón del pipeline de onboarding: convertir un CV humano-leíble en \`ResumeData\` Pydantic que S03/S04/S05 consumen.

## 📐 Alcance Técnico

### Módulo
\`src/jobhunter/onboarding/resume_ingestor.py\` con:
\`\`\`python
async def ingest_resume(file_bytes: bytes, mime_type: str) -> ResumeData:
\`\`\`

### MIME types soportados
- \`application/pdf\`
- \`text/markdown\`
- \`text/plain\`
- \`application/vnd.openxmlformats-officedocument.wordprocessingml.document\` (DOCX)

### Extracción de texto
- PDF: \`pypdfium2\` (más rápido y simple que pymupdf, suficiente para CVs típicos).
- DOCX: \`python-docx\`.
- MD/TXT: lectura directa.

### Parser LLM
\`claude-opus-4-7\`: recibe el texto extraído + prompt versionado en \`prompts/onboarding/resume_parser/v1.md\`, devuelve JSON parseable a \`ResumeData\`.

### Pydantic model
\`\`\`python
class ResumeData(BaseModel):
    name: str
    email: str | None
    phone: str | None
    location_raw: str | None
    summary: str | None
    experiences: list[ParsedExperience]   # role, company, dates, bullets
    educations: list[ParsedEducation]
    skills: list[str]
    languages: list[str]
    detected_seniority: str | None        # \"junior\" / \"mid\" / \"senior\" / \"staff\"
    detected_years_experience: int | None
    detected_primary_stack: list[str]     # las 5-7 más mencionadas
    raw_text: str                         # para debug
\`\`\`

### Validación post-LLM
Si \`experiences\` está vacío o \`name\` falta, raise \`ResumeIngestionError\` con \`raw_text\` y \`raw_response\` para debug.

### Cost tracking
Costo registrado en \`llm_calls\` con \`purpose='resume_parsing'\`.

### Tests
Fixtures de CVs reales sanitizados (PDF de un perfil ficticio + MD + DOCX equivalentes en \`tests/fixtures/resumes/\`).

## 🛠️ Tasks

- Añadir deps: \`pypdfium2\`, \`python-docx\`.
- Crear \`src/jobhunter/onboarding/__init__.py\` y \`resume_ingestor.py\`.
- Prompt en \`prompts/onboarding/resume_parser/v1.md\`.
- Pydantic models.
- Tests con 3 fixtures (PDF, MD, DOCX).

## 📝 Notas

- **Por qué Opus aquí.** Resume parsing tolera ruido y formatos raros. Opus produce mejor extracción que Sonnet en CVs con tablas, columnas, fuentes raras. Costo: ~\$0.10 por CV one-shot, justificado.
- **Sanitización de fixtures.** Los CVs de ejemplo deben tener nombres y empresas ficticias (no datos reales del usuario). Generar con prompt: \"Crea un CV ficticio realista de un Python senior con 8 años de experiencia\".

## 🧪 Criterios de Aceptación
- [ ] Deps \`pypdfium2\` y \`python-docx\` añadidas y bloqueadas.
- [ ] \`ingest_resume()\` async con los 4 MIME types soportados.
- [ ] Prompt versionado en \`prompts/onboarding/resume_parser/v1.md\`.
- [ ] \`ResumeData\` Pydantic con todos los campos listados.
- [ ] Validación post-LLM raise \`ResumeIngestionError\` ante input degenerado.
- [ ] Costo persistido en \`llm_calls\` con \`purpose='resume_parsing'\`.
- [ ] Tests con 3 fixtures (PDF, MD, DOCX) pasan.

## 🔗 Dependencias
- Bloqueante: Épica E04 cerrada (LLM client + tracking).
- Paralelizable con: E14-S03.

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:onboarding,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S03 — ProfileGenerator (ResumeData → INSERT en candidate_profiles)
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S03] ProfileGenerator: ResumeData + inputs → candidate_profiles" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** transformar la \`ResumeData\` extraída + inputs interactivos del usuario en una row de \`candidate_profiles\` persistida en BD, **para que** el wizard tenga un commit atómico al final.

## 📐 Alcance Técnico

### Módulo
\`src/jobhunter/onboarding/profile_generator.py\` con:
\`\`\`python
async def generate_profile(
    resume_data: ResumeData,
    user_inputs: ProfileUserInputs,    # contexto que la IA no puede inferir
    session: Session,
    llm_client: AnthropicLLMClient,
) -> CandidateProfile:                  # row recién insertada
\`\`\`

### Pydantic ProfileUserInputs
\`country\`, \`work_authorization\`, \`timezone_home\`, \`overlap_max_hours_cet\`, \`contract_preferences\`, \`hard_blockers\`, \`payment_methods_ok\`, \`profile_name\` (lo que el usuario decide llamarlo, ej. \"Python AI Senior\").

### Inferencia LLM (Sonnet) para los campos derivables
- \`seniority\`, \`years_experience\` (validar contra \`detected_*\` del ResumeData).
- \`primary_stack\` (5-7 tecnologías), \`secondary_stack\`, \`domains\` (3-5 áreas).
- \`positive_signals\`, \`soft_negatives\` (sugerencias iniciales que el usuario puede ajustar después).

### Prompt versionado
\`prompts/onboarding/profile_generator/v1.md\`.

### Languages
Se rellenan a partir de \`ResumeData.languages\` con defaults razonables (\"native\" si es el idioma del país declarado, \"fluent\" si no se especifica nivel).

### Compensation
\`compensation\` queda **NULL** en este paso — lo pobla \`SalaryProposer\` (S05) en un paso aparte.

### Persistencia
\`INSERT\` en \`candidate_profiles\` vía \`CandidateProfileRepo.create(profile_data)\`. NO se inserta \`compensation\`.

### Return value
Devuelve la entidad recién creada (con \`id\` poblado).

### Tests
Tests con \`ResumeData\` fixture + \`MockLLMClient\` que devuelve respuesta Sonnet pre-grabada.

## 🛠️ Tasks

- Implementar \`generate_profile\`.
- Pydantic \`ProfileUserInputs\`.
- Prompt versionado.
- Tests integración (DB seeded + mock LLM).

## 📝 Notas

- **Multi-profile habilita esto:** el usuario puede correr \`generate_profile\` N veces (vía wizard \"Add another profile\"). Cada llamada inserta una row distinta.
- **Validación cruzada del LLM con ResumeData:** si el LLM dice \`years_experience=3\` pero \`ResumeData.detected_years_experience=15\`, warn al usuario en el wizard. Probable confusión por formato del CV.

## 🧪 Criterios de Aceptación
- [ ] \`generate_profile()\` async implementado.
- [ ] \`ProfileUserInputs\` Pydantic con todos los campos del AC.
- [ ] Prompt versionado en \`prompts/onboarding/profile_generator/v1.md\`.
- [ ] Inferencia LLM produce \`seniority\`, \`primary_stack\`, \`domains\`, etc.
- [ ] Validación cruzada LLM vs ResumeData con warning si discrepa.
- [ ] \`compensation\` queda NULL (no se inserta en este paso).
- [ ] Persistencia atómica vía repo.
- [ ] Tests integración con \`MockLLMClient\` pasan.

## 🔗 Dependencias
- Bloqueante: E14-S01 (schema BD), E14-S02 (ResumeData).
- Paralelizable con: E14-S02.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:onboarding,component:profile,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S04 — CVVariantGenerator (variants user-defined)
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S04] CVVariantGenerator: variants user-defined" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** generar N variants de CV con nombres y focos arbitrarios elegidos por el usuario, **para que** el sistema soporte cualquier combinación de carreras (no sólo \`ai_python\` / \`flutter\` / \`fullstack\`) y la \`variant_selector\` tenga material rico para elegir.

**Decisión clave del usuario** documentada en ADR-008 y E14 doc R: las variants ya **NO están hardcoded**. Un usuario puede tener variants llamadas \`python_backend\`, \`translator_es\`, \`ai_agent_consultant\`, lo que sea. Esta story implementa el generador; S06 implementa el selector que las consume.

## 📐 Alcance Técnico

### Módulo
\`src/jobhunter/onboarding/cv_variant_generator.py\` con:
\`\`\`python
async def generate_variant(
    profile: CandidateProfile,
    resume_data: ResumeData,
    variant_spec: VariantSpec,         # name + foco que el usuario quiere
    session: Session,
    llm_client: AnthropicLLMClient,
) -> CVVariant:                         # row insertada con experiencias
\`\`\`

### Pydantic VariantSpec
\`\`\`python
class VariantSpec(BaseModel):
    name: str                            # \"ai_python_engineer\", lowercase + underscore
    display_name: str                    # \"AI Python Engineer\", human-friendly
    target_role_keywords: list[str]      # [\"python\", \"ml engineer\", \"ai engineer\"]
    target_stack: list[str]              # [\"Python\", \"PyTorch\", \"FastAPI\"]
    target_seniority: str | None
    angle_description: str               # \"Foco en backend AI con LLMs en producción\"
\`\`\`

### Generación LLM (Sonnet)
Toma:
- \`ResumeData\` completa (todas las experiencias).
- \`VariantSpec\` (qué quiere destacar).
- \`profile\` (compensation, etc., para coherencia).

### Output del LLM
- \`summary\` reescrito con foco en \`angle_description\`.
- \`skills\` priorizados (los relevantes para la variant primero).
- \`experiences\` con bullets reescritos/reordenados — sólo se mantienen bullets relevantes; los irrelevantes se omiten para mantener el CV enfocado.

### Prompt versionado
\`prompts/onboarding/cv_variant_generator/v1.md\`.

### Persistencia atómica
En una transacción, \`INSERT\` en \`cv_variants\` + N \`INSERT\` en \`cv_variant_experiences\`. Si falla cualquiera, rollback.

### Markdown rendering
\`raw_markdown\` se renderiza desde los datos estructurados (helper \`cv_variant_to_markdown(variant) -> str\`) y se persiste para que el usuario pueda exportar / diffear.

### Tests
Generar 3 variants distintas a partir de la misma \`ResumeData\` con \`VariantSpec\` distintas → verificar que los \`summary\` y \`skills\` priorizados son distintos.

## 🛠️ Tasks

- Implementar \`generate_variant\`.
- Pydantic \`VariantSpec\`.
- Helper \`cv_variant_to_markdown\`.
- Prompt versionado.
- Tests con fixtures.

## 📝 Notas

- **El usuario controla cuántas variants.** El wizard sugiere defaults basados en \`ResumeData.detected_primary_stack\` (ej. si detecta Python+AI y Flutter, sugiere 2 variants). Pero el usuario puede pedir 1, 5, o 10.
- **Costo:** ~\$0.02 por variant. 5 variants = \$0.10. Aceptable.
- **\`raw_markdown\` regenerable:** si el LLM cambia o el prompt evoluciona, re-generar todas las variants es un comando (\`profile rebuild-variants <profile_id>\`).

## 🧪 Criterios de Aceptación
- [ ] \`generate_variant()\` async implementado.
- [ ] \`VariantSpec\` Pydantic con todos los campos del AC.
- [ ] Generación LLM produce summary + skills priorizados + experiences reordenados/filtrados.
- [ ] Persistencia atómica (rollback ante fallo parcial).
- [ ] Helper \`cv_variant_to_markdown\` funcional.
- [ ] Prompt versionado.
- [ ] Test: 3 variants distintas a partir de misma ResumeData producen output distinto.

## 🔗 Dependencias
- Bloqueante: E14-S01 (schema), E14-S02 (ResumeData).
- Paralelizable con: E14-S05, E14-S06.

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:onboarding,component:profile,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S05 — SalaryProposer
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S05] SalaryProposer: rango salarial con rationale" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** que el sistema proponga un rango salarial (floor / target / stretch) basado en mi experiencia, ubicación y preferencias contractuales, **para que** no tenga que hacer research manual de mercado y la propuesta tenga rationale explicable.

## 📐 Alcance Técnico

### Módulo
\`src/jobhunter/onboarding/salary_proposer.py\` con:
\`\`\`python
async def propose_salary(
    profile: CandidateProfile,         # ya creado por S03
    resume_data: ResumeData,
    llm_client: AnthropicLLMClient,
    market_data_source: SalaryDataSource | None = None,
) -> SalaryProposal:
\`\`\`

### Pydantic SalaryProposal
\`\`\`python
class SalaryProposal(BaseModel):
    currency: Literal[\"USD\", \"EUR\"]
    period: Literal[\"month\", \"year\"]
    floor: int
    target: int
    stretch: int
    rationale: str                      # narrativa del LLM
    data_sources: list[str]             # [\"llm_baseline_2026\", ...]
    confidence: float                   # 0-1
\`\`\`

### Estrategia de v1 (LLM con baseline 2026)
Prompt versionado en \`prompts/onboarding/salary_proposer/v1.md\` que incluye una tabla de baselines por (stack, seniority, region, contract_type). El LLM ajusta basándose en \`years_experience\`, \`primary_stack\`, \`country\`, \`contract_preferences\`.

### Hook para Estrategia v2 (datos reales — story futura)
Parámetro opcional \`market_data_source\` que, si se pasa, consulta \`JobRepo\` por jobs ingestados con compensation extraído + match heurístico contra el perfil. Devuelve mediano + p25/p75. Esto se implementa cuando haya 500+ jobs reales en BD; por ahora el hook queda definido pero no conectado.

### Persistencia
El resultado se persiste en \`candidate_profiles.compensation\` vía \`CandidateProfileRepo.update_compensation(profile_id, proposal)\`.

### UX
El usuario puede aceptar o ajustar antes del save final (el wizard presenta los 3 valores como editables).

### Tests
Tests con \`MockLLMClient\`.

## 🛠️ Tasks

- Implementar \`propose_salary\`.
- Prompt con tabla baseline 2026 (revisar al menos cada 6 meses).
- Pydantic models.
- Tests.

## 📝 Notas

- **Baselines envejecen.** Marcar el prompt con \`# verified YYYY-MM-DD\` (igual que \`pricing.py\` de E4-S03). Workflow semestral de revisión recomendable.
- **Hook v2 = futuro story.** Cuando haya 500+ jobs ingestados, abrir \`E14-S12 — SalaryProposer con datos reales\`. La interfaz \`SalaryDataSource\` ya está prevista para minimizar refactor.

## 🧪 Criterios de Aceptación
- [ ] \`propose_salary()\` async implementado.
- [ ] Prompt versionado con baseline 2026 marcado con \`# verified YYYY-MM-DD\`.
- [ ] \`SalaryProposal\` Pydantic con currency/period/floor/target/stretch/rationale/data_sources/confidence.
- [ ] Interfaz \`SalaryDataSource\` definida (aunque no implementada aún).
- [ ] Persistencia en \`candidate_profiles.compensation\` vía repo.
- [ ] Tests con \`MockLLMClient\` cubren caso típico (LATAM Python senior B2B) y caso edge (idioma alemán + EU).

## 🔗 Dependencias
- Bloqueante: E14-S02 (ResumeData), E14-S01 (perfil ya existe en BD para update_compensation).
- Paralelizable con: E14-S04, E14-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:onboarding,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S06 — Refactor variant_selector para variants arbitrarias
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S06] Refactor variant_selector para variants arbitrarias" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** que el \`variant_selector\` funcione con N variants user-defined, **para que** el cambio de variants hardcoded a user-defined no rompa el assistant E6.

Hoy el selector tiene heurística \`if name == \"ai_python\"\` hardcoded para 3 variants fijas. Tras E14, las variants son user-defined con metadata explícito (\`target_role_keywords\`, \`target_stack\`); el selector debe consumir esa metadata.

## 📐 Alcance Técnico

### Firma nueva
\`src/jobhunter/application/variant_selector.recommend_cv_variant\` se reescribe:
\`\`\`python
def recommend_cv_variant(
    job: Job,
    available_variants: Sequence[CVVariant],   # cargadas de DB
    llm_client: AnthropicLLMClient | None = None,
) -> VariantRecommendation:
\`\`\`

### Lógica nueva en 2 pasos

**Paso 1 — Heurística (gratis, rápida):**
Para cada \`variant\` en \`available_variants\`, calcular score = count(matches entre \`variant.target_role_keywords\` ∪ \`variant.target_stack\` y \`job.title\` ∪ \`job.description.lower()\`). El de mayor score gana con \`confidence = score / max_possible_score\`.

**Paso 2 — Fallback LLM (si confidence < 0.4 o todas las variants empatan):**
Prompt corto con \`job.title + job.description.snippet + summaries de cada variant\`, Sonnet devuelve \`{\"variant_name\": \"...\", \"confidence\": 0.X, \"reasoning\": \"...\"}\`.

### Casos especiales
- Si \`len(available_variants) == 1\`: devuelve esa variant con \`confidence = 1.0\` sin llamar al LLM.
- Si \`len(available_variants) == 0\`: raise \`NoCVVariantsAvailableError\` (debe gating en el caller).

### VariantRecommendation
Mantener Pydantic con \`variant_name\`, \`variant_id\`, \`confidence\`, \`reasoning\`.

### Backward-compat
Los callers existentes (\`assistant.py\`, página Streamlit de Assist) siguen funcionando, sólo cambia que ahora reciben el \`variant_id\` para resolver contra DB en vez de archivo.

### Tests
Scenarios:
- 1 variant disponible → devuelve esa.
- 3 variants, una matchea claramente → heurística sin LLM.
- 3 variants, todas matchean débilmente → escala a LLM.
- 0 variants → raise.

## 🛠️ Tasks

- Reescribir \`recommend_cv_variant\`.
- Helper \`_keyword_match_score(variant, job) -> float\`.
- Helper \`_llm_disambiguate(job, variants) -> VariantRecommendation\`.
- Crear \`NoCVVariantsAvailableError\` en \`application/__init__.py\`.
- Tests unitarios cubriendo los 4 scenarios.

## 📝 Notas

- **El refactor preserva la heurística > LLM** (decisión original de E6-S02 ratificada en ADR-007 conceptualmente). LLM sólo escala cuando la heurística es ambigua.
- **\`target_role_keywords\` y \`target_stack\` se llenan en S04** con sugerencias del LLM. El usuario puede ajustarlas en el wizard step 6 — eso afina el selector.

## 🧪 Criterios de Aceptación
- [ ] Nueva firma de \`recommend_cv_variant\` recibe \`Sequence[CVVariant]\`.
- [ ] Heurística scoring por keyword match implementada.
- [ ] Fallback LLM cuando heurística confidence < 0.4 o empate.
- [ ] Caso \`len == 1\` → devuelve directo sin LLM.
- [ ] Caso \`len == 0\` → raise \`NoCVVariantsAvailableError\`.
- [ ] \`VariantRecommendation\` incluye \`variant_id\` (no sólo name).
- [ ] Tests unitarios cubren los 4 scenarios.

## 🔗 Dependencias
- Bloqueante: E14-S01 (modelo CVVariant en BD).
- Paralelizable con: E14-S04 (los 2 pueden avanzar en paralelo).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:refactor,component:profile,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S07 — Refactor cross-épica: consumers leen perfil de DB
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S07] Refactor cross-épica: scoring/outreach/application leen perfil de DB" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** que TODOS los consumidores del perfil (scoring, outreach, application/) lean de la BD en vez de yaml/markdown, **para que** la BD sea fuente única de verdad y la deuda técnica del perfil duplicado se resuelva.

**Esta es la story de mayor riesgo de regresión** de E14. El test suite completo (>200 tests) debe pasar al final. Ver ADR-008 para el rationale completo.

## 📐 Alcance Técnico — Scoring (E4)

### Prompt
\`prompts/scoring/v1.md\` se edita para reemplazar el bloque \`candidate_profile:\` hardcoded por el placeholder \`{candidate_profile_yaml}\` (mismo patrón que \`prompts/outreach/v1/\`).

### Scorer
\`scoring/scorer.JobScorer.score(job)\` recibe \`profile_id: UUID\` o consulta \`CandidateProfileRepo.list_active()\`.

### Multi-profile
\`score(job)\` itera sobre cada perfil activo, persiste el resultado por perfil. Schema Job extendido (ver tarea abajo): tabla nueva \`job_profile_scores\`.

## 📐 Alcance Técnico — Outreach (E9)

- \`outreach/generator.generate_message\`: en vez de \`Path(\"prompts/candidate_profile.yaml\").read_text()\`, hace \`CandidateProfileRepo.get_active_by_id(profile_id).to_yaml_string()\`.
- \`outreach/scoring.calculate_heuristic_score\`: recibe \`candidate_profile: CandidateProfile\` (modelo SQLAlchemy) en vez de \`dict\`.
- \`__main__.py:2195\` (importer) usa el repo en lugar de yaml directo.

## 📐 Alcance Técnico — Application (E6)

- \`application/cv.load_cv(variant_name, ...)\` se reescribe para leer de \`cv_variants\` table vía \`CVVariantRepo.get_by_name(profile_id, name)\`.
- \`application/cv.list_available_variants(profile_id)\` lista de DB.
- \`application/assistant.assist_application\` recibe \`profile_id\` (lo obtiene del session_state del dashboard o del CLI).
- \`application/cover_letter\`, \`cv_tweaks\`, \`ats_keywords\`: reciben \`cv_variant: CVVariant\` (modelo SQLAlchemy) en vez de leer archivo.

## 📐 Alcance Técnico — Schema extension para multi-profile scoring

Decidir entre:
- Opción 1: \`Job.scores_by_profile JSONB\` (\`{profile_id: {fit_score, tier, score_data}}\`).
- Opción 2: nueva tabla \`job_profile_scores (job_id, profile_id, fit_score, tier, score_data, scored_at, scored_with_prompt_version)\`.

**Recomendación: Opción 2** — queryable, indexable, audit-friendly.

Migration adicional para la tabla nueva.

## 📐 Alcance Técnico — Tests de regresión

Los tests de E4, E6, E9 siguen pasando con la nueva lógica (puede requerir actualizar fixtures para que el \`db_session\` inserte un perfil mínimo antes de cada test).

## 🛠️ Tasks

- Editar \`prompts/scoring/v1.md\` con placeholder.
- Migration tabla \`job_profile_scores\`.
- Refactor \`JobScorer.score\` para iterar perfiles activos.
- Refactor \`outreach/generator.py\` y \`outreach/scoring.py\`.
- Refactor \`application/cv.py\`, \`assistant.py\`, \`cover_letter.py\`, \`cv_tweaks.py\`, \`ats_keywords.py\`.
- Helper \`CandidateProfile.to_yaml_string()\` (para inyectar como string en prompts que lo esperan en formato yaml).
- Update fixtures en \`tests/conftest.py\`: \`sample_candidate_profile\` insertado por default.
- Run full test suite, fix regresiones.

## 📝 Notas

- **Esta es la story de mayor riesgo de regresión** de E14. El test suite completo (>200 tests) debe pasar al final. Considerar feature flag para rollback si CI rojo.
- **Multi-profile scoring 3x el costo LLM si hay 3 perfiles activos.** El scorer puede paralelizar las 3 llamadas (\`asyncio.gather\`) para mantener latencia. Documentar en runbook.

## 🧪 Criterios de Aceptación
- [ ] \`prompts/scoring/v1.md\` con placeholder \`{candidate_profile_yaml}\`.
- [ ] Tabla \`job_profile_scores\` creada vía migration con downgrade probado.
- [ ] \`JobScorer.score(job)\` itera sobre perfiles activos y persiste por perfil.
- [ ] \`outreach/generator.py\` y \`outreach/scoring.py\` leen de DB.
- [ ] \`application/cv.py\` y consumers leen de DB.
- [ ] Helper \`CandidateProfile.to_yaml_string()\` implementado.
- [ ] Fixture \`sample_candidate_profile\` añadido a \`conftest.py\`.
- [ ] **Full test suite verde** (cero regresiones en E4/E6/E9 y demás épicas).

## 🔗 Dependencias
- Bloqueante: E14-S01 (schema), E14-S06 (variant_selector refactorizado para BD).

## ⏱️ Estimación
3h
${DOD_TEMPLATE}" \
    "status:ready,type:refactor,component:profile,component:db,component:llm,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S08 — Wizard dashboard pages/0_🎯_Onboarding.py
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S08] Wizard dashboard: pages/0_🎯_Onboarding.py (7 pasos + edit mode)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** un wizard web de varios pasos para crear/editar mi perfil, **para que** el bootstrap inicial sea sin terminal y la experiencia primer-uso sea fluida.

**Decisión Eje C (soft gating):** sin perfil activo, el dashboard muestra banner persistente \"Configura tu perfil para empezar\" pero NO bloquea navegación.

## 📐 Alcance Técnico

### Página
\`src/jobhunter/dashboard/pages/0_🎯_Onboarding.py\` (slot \`0_\` → primero alfabéticamente, llamado \"Onboarding\").

### Soft gating
\`dashboard/auth.require_auth\` extendido o nuevo helper \`check_profile_setup()\` que, si \`CandidateProfileRepo.list_active()\` retorna vacío, muestra banner persistente en TODAS las páginas:

\`\`\`
ℹ️ Configura tu perfil para empezar a recibir matches → [Empezar wizard]
\`\`\`

Click → navigate a \`pages/0_🎯_Onboarding.py\`. Las demás páginas siguen accesibles (no bloqueo).

### Wizard de 7 pasos con progreso visible (step indicator)

**1. Upload resume** (drag-drop o file picker, PDF/MD/DOCX). Botón \"Saltar y rellenar manual\" lleva al step 2 con \`ResumeData\` vacío.

**2. Review extracción**: bloques editables con \`name\`, experiences (timeline), \`skills\`, \`educations\`, \`languages\`. Usuario corrige cualquier mala extracción. Indicador de \`detected_seniority\` / \`detected_years_experience\` / \`detected_primary_stack\`.

**3. Contexto personal** (form): \`country\`, \`work_authorization\`, \`timezone_home\`, \`overlap_max_hours_cet\`, \`contract_preferences\` (multi-select), \`payment_methods_ok\` (multi-select), \`hard_blockers\` (textarea, una por línea).

**4. Career angle** (form):
- \`profile.name\` (texto libre, ej. \"Python AI Senior\").
- Confirmar \`primary_stack\`/\`secondary_stack\`/\`domains\` sugeridos por el LLM (editables).
- \`positive_signals\` y \`soft_negatives\` editables.

**5. Salary proposal**: muestra \`SalaryProposer\` resultado con \`rationale\` desplegable. Tres campos editables (floor/target/stretch). Toggle USD/EUR + month/year.

**6. Variants**: form repetible.
- \"¿Cuántas variants quieres?\" → defaults 1, máximo 10.
- Para cada variant: \`name\`, \`display_name\`, \`target_role_keywords\` (chips), \`target_stack\` (chips), \`angle_description\`.
- Botón \"Generar\" por variant → llama \`CVVariantGenerator\` y muestra preview del markdown (editable).

**7. Confirm and save**: resumen completo. Botón \"Activar perfil\" ejecuta la transacción atómica (perfil + N variants).

### Edit mode
Si ya hay perfil activo, la página detecta \`?profile_id=X\` query param o usa el activo por default. Pre-llena los pasos con datos actuales. Permite saltar entre pasos no-secuencialmente via tabs/anchors.

### State management
\`st.session_state\` con clave \`onboarding_state: OnboardingState\` (Pydantic) que persiste entre re-renders. Reset explícito al completar.

### Multi-profile UX
**Botón \"Add another profile\"** en dashboard si ya hay perfil → abre wizard en modo \"nuevo perfil\" (limpia state).

### Coste visible
Costo total visible al final (suma de las llamadas LLM del wizard).

### Tests
Tests E2E Playwright: completar el flow con un PDF fixture (\`tests/e2e/dashboard/test_onboarding_wizard.py\`).

## 🛠️ Tasks

- Página Streamlit con state machine.
- Componente \`render_resume_review_form(resume_data)\` editable.
- Componente \`render_variant_form(variant_spec, profile)\` con preview.
- Soft gating helper en \`dashboard/auth.py\` o \`layout.py\`.
- Test E2E.

## 📝 Notas

- **Wizard como UX principal.** El CLI (S09) es alternativo. La mayoría de usuarios van a usar la web.
- **Edit mode es lo que hace al wizard sostenible.** Sin él, el usuario necesita SQL para cambiar el floor salarial. Con él, la onboarding page es también el \"settings page\" del perfil.

## 🧪 Criterios de Aceptación
- [ ] Página \`pages/0_🎯_Onboarding.py\` existe con los 7 pasos secuenciales.
- [ ] Soft gating: banner persistente en todas las páginas si no hay perfil; sin bloqueo de navegación.
- [ ] Step 1: upload PDF/MD/DOCX funcional + opción \"saltar manual\".
- [ ] Step 2: bloques editables para ResumeData.
- [ ] Step 3: form de contexto personal completo.
- [ ] Step 4: career angle (profile name + stacks + signals editables).
- [ ] Step 5: salary proposal editable con rationale desplegable.
- [ ] Step 6: variants user-defined (cantidad y nombres arbitrarios).
- [ ] Step 7: confirmación + transacción atómica perfil+variants.
- [ ] Edit mode pre-llena con datos actuales y permite navegación no-secuencial.
- [ ] Botón \"Add another profile\" desde dashboard funciona.
- [ ] Costo total visible al finalizar.
- [ ] Test E2E Playwright pasa.

## 🔗 Dependencias
- Bloqueante: E14-S03 (ProfileGenerator), E14-S04 (CVVariantGenerator), E14-S05 (SalaryProposer).

## ⏱️ Estimación
4h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:onboarding,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S09 — CLI profile bootstrap
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S09] CLI profile bootstrap: alternativo para power users" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** un comando CLI equivalente al wizard para automatización (scripts, re-bootstrapping desde cron, headless deploys), **para que** el sistema no dependa exclusivamente del navegador.

## 📐 Alcance Técnico

### Comando principal
\`jobhunter profile bootstrap --resume PATH [--interactive] [--profile-name NAME]\`.

### Sin \`--interactive\`
Corre el pipeline end-to-end y crea un perfil con \`compensation\` propuesto, variants generadas con defaults sugeridos por IA, **TODO** markers en campos que necesitan input humano (ej. \`hard_blockers: [TODO_ADD_BLOCKERS]\`). El usuario edita después en dashboard o vía SQL.

### Con \`--interactive\`
Prompts en terminal para los campos que la IA no puede inferir (los del step 3 del wizard).

### Output
Tabla rich con resumen del perfil creado + ID + costo total + comando para verificar (\`profile show <id>\`).

### CLI auxiliares
- \`profile list\` — lista perfiles con \`id\`, \`name\`, \`is_active\`, \`count(variants)\`, \`created_at\`.
- \`profile show <id>\` — muestra el perfil completo (yaml-like) en stdout.
- \`profile activate <id>\` / \`profile deactivate <id>\`.
- \`profile delete <id> --confirm\` — soft delete (marca inactivo + audit log) o hard delete (ON DELETE CASCADE).
- \`profile variants list <profile_id>\`.
- \`profile rebuild-variants <profile_id>\` — re-genera todas las variants del perfil con el prompt actual (útil tras prompt iteration).

### Tests
Tests CLI con \`typer.testing.CliRunner\`.

## 🛠️ Tasks

- Implementar comandos en \`__main__.py\` (sub-Typer \`profile_app\`).
- Tests CLI.

## 📝 Notas

- **Reuso máximo:** los comandos llaman directamente a las funciones de S02–S05. El CLI es UI alternativa, no lógica nueva.
- **\`--interactive\` con \`typer.prompt\`** para los campos sin IA-inferencia.

## 🧪 Criterios de Aceptación
- [ ] \`profile bootstrap --resume X\` ejecuta pipeline completo end-to-end.
- [ ] Modo \`--interactive\` pregunta en terminal los campos no-inferibles.
- [ ] Modo no-interactivo deja TODO markers para campos no-inferibles.
- [ ] Sub-Typer \`profile\` con: \`bootstrap\`, \`list\`, \`show\`, \`activate\`, \`deactivate\`, \`delete\`, \`variants list\`, \`rebuild-variants\`.
- [ ] Output rich con resumen + costo + comando next-step.
- [ ] Tests CLI con \`CliRunner\` cubren cada comando (golden path + 1 caso de error).

## 🔗 Dependencias
- Bloqueante: E14-S02 (ResumeIngestor), E14-S03 (ProfileGenerator), E14-S04 (CVVariantGenerator), E14-S05 (SalaryProposer).
- Paralelizable con: E14-S08.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:onboarding,component:profile,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S10 — Migration legacy yaml + markdowns → BD
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S10] Migration legacy: yaml + markdowns → BD" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** que un usuario con \`prompts/candidate_profile.yaml\` y \`.local/cv_variants/*.md\` existentes pueda correr \`alembic upgrade head\` y tener su data ya en BD, **para que** el upgrade de E14 sea no-disruptivo.

**Decisión Eje D1 (migración one-shot + archive):** los archivos originales se preservan en \`prompts/_legacy/{timestamp}/\` (no se borran).

## 📐 Alcance Técnico

### Migration Alembic post-S01 (idempotente)

- Si existe \`prompts/candidate_profile.yaml\`, parsearlo e insertar como nuevo \`candidate_profile\` (\`name=\"Legacy Profile\"\`, \`is_active=true\`). Mapea campos yaml → columnas BD según convención de Eje A3.
- Si existen \`.local/cv_variants/*.md\`, parsear cada uno (usando el parser \`_parse_cv_markdown\` actual de \`application/cv.py\`) e insertar como \`cv_variants\` asociadas al perfil legacy. \`target_role_keywords\` y \`target_stack\` se infieren del nombre del archivo (ej. \`ai_python.md\` → keywords \`[\"python\", \"ai\", \"ml\"]\`).
- Si NO existe ninguno (deploy fresh), no-op.

### Archivado post-migración exitosa

El script archiva los originales:
- \`prompts/candidate_profile.yaml\` → \`prompts/_legacy/{timestamp}/candidate_profile.yaml\`.
- \`.local/cv_variants/*.md\` → \`.local/cv_variants/_legacy/{timestamp}/\`.
- **NO los borra** — el usuario puede consultar/restaurar.

### Output
Migration imprime resumen: \"Imported 1 legacy profile + N CV variants. Originals archived in prompts/_legacy/{timestamp}/.\"

### Tests
Ejecutar migration con yaml mock + markdowns mock → verificar rows insertados.

## 🛠️ Tasks

- Migration Alembic.
- Helpers de parsing (reuso del parser actual).
- Lógica de archive.
- Tests integración con fixtures yaml/md.

## 📝 Notas

- **Para el caso particular del autor**, esta migration es \"gratis\" (no tiene yaml de su perfil definitivo desplegado). Pero existe por higiene: si el proyecto se forkea o si en el futuro se despliega una versión local primero, la migration evita pérdida de data.
- **El archivo en \`_legacy/\` queda gitignored** (igual que \`.local/\`) excepto si el yaml original estaba commiteado. Si estaba commiteado, se mueve dentro del repo y se commitea el move.

## 🧪 Criterios de Aceptación
- [ ] Migration es idempotente (ejecutar 2 veces no duplica).
- [ ] Si yaml existe, se importa con \`name=\"Legacy Profile\"\` activo.
- [ ] Si markdowns existen, cada uno se importa como \`cv_variant\` asociada.
- [ ] \`target_role_keywords\` y \`target_stack\` inferidos del filename (ai_python → [\"python\",\"ai\",\"ml\"]).
- [ ] Originales archivados en \`prompts/_legacy/{timestamp}/\` y \`.local/cv_variants/_legacy/{timestamp}/\`.
- [ ] Resumen impreso por la migration con conteos.
- [ ] Si ninguno existe (deploy fresh), no-op silencioso.
- [ ] Tests con fixtures yaml/md pasan.

## 🔗 Dependencias
- Bloqueante: E14-S07 (refactor cross-épica) cerrada — para que los consumers ya estén apuntando a BD cuando la migration importe.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:db,component:profile,epic:E14" \
    "$OPT_EPIC_E14" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E14-S11 — Tests E2E + actualización de docs
# ---------------------------------------------------------------------------
create_issue \
    "[E14-S11] Tests E2E + Playwright wizard + actualización de docs (HUMAN_SETUP, CLAUDE, ARCHITECTURE)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** test E2E del wizard + CLI bootstrap + documentación actualizada en HUMAN_SETUP/CLAUDE/ARCHITECTURE, **para que** E14 quede cerrada con regression coverage y la documentación refleje la nueva realidad (perfil en BD, no en yaml).

## 📐 Alcance Técnico

### Test E2E Playwright
\`tests/e2e/dashboard/test_onboarding_wizard.py\`:
- Login → ver banner soft-gating → click \"Empezar wizard\".
- Upload de PDF fixture (sanitizado).
- Avanzar por los 7 pasos rellenando los inputs.
- Verificar que al final hay 1 row en \`candidate_profiles\` + N rows en \`cv_variants\`.
- Banner soft-gating desaparece.

### Test E2E del CLI bootstrap
\`tests/integration/test_profile_bootstrap_cli.py\`:
- Run \`profile bootstrap --resume tests/fixtures/resumes/sample_python.pdf\`.
- Verificar mismas inserciones en BD.

### Test cross-épica
Después de bootstrap, ejecutar \`score-job <id>\` contra un job ya ingestado → verificar que el scoring usa el perfil de BD (no falla por yaml ausente).

### Documentación
- Actualizar \`HUMAN_SETUP.md\` §2 completa: reemplazar la sección \"Editar yaml\" por \"Ejecutar wizard\". Mantener nota sobre alternativa CLI.
- Actualizar \`CLAUDE.md\` sección \"Architecture\": añadir \`onboarding/\` como módulo; mencionar que perfil vive en BD.
- Actualizar \`docs/ARCHITECTURE.md\` con \`candidate_profiles\` como entidad de dominio.
- Actualizar \`docs/data_model.md\` con las 4 tablas nuevas + diagrama mermaid actualizado.
- Actualizar \`README.md\` con captura del wizard si es posible.

> Nota: \`docs/adr/ADR-008-profile-in-db.md\` ya fue creado durante la planificación de E14 (no requiere creación, sólo verificar que sigue alineado tras la implementación).

## 🛠️ Tasks

- Implementar tests E2E.
- Implementar test integración CLI.
- Update docs.
- Verificar ADR-008 sigue alineado tras implementación.

## 📝 Notas

- **El test cross-épica es crítico.** Sin él, S07 podría dejar regresiones silenciosas en E4/E6/E9 que sólo se manifiestan en producción.

## 🧪 Criterios de Aceptación
- [ ] \`tests/e2e/dashboard/test_onboarding_wizard.py\` cubre el flow completo del wizard.
- [ ] \`tests/integration/test_profile_bootstrap_cli.py\` cubre el flow del CLI.
- [ ] Test cross-épica: \`score-job <id>\` post-bootstrap funciona sin yaml.
- [ ] \`HUMAN_SETUP.md\` §2 reescrita apuntando al wizard.
- [ ] \`CLAUDE.md\` sección Architecture incluye \`onboarding/\`.
- [ ] \`docs/ARCHITECTURE.md\` menciona \`candidate_profiles\` como entidad.
- [ ] \`docs/data_model.md\` con 4 tablas nuevas + diagrama mermaid actualizado.
- [ ] ADR-008 verificado contra implementación final (alineado, no requiere update mayor).

## 🔗 Dependencias
- Bloqueante: E14-S08 (wizard) y E14-S09 (CLI).

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:docs,component:onboarding,component:dashboard,epic:E14" \
    "$OPT_EPIC_E14" \
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
echo " 🎉 BACKLOG L2 CREADO PARA LA ÉPICA E14 — ONBOARDING (11 stories, ~23h)."
echo ""
echo " Próximos pasos:"
echo "   1. Verifica los issues en: https://github.com/${FULL_REPO}/issues?q=is%3Aissue+label%3Aepic%3AE14"
echo "   2. Verifica el proyecto en: https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo "   3. ⚠️  E14-S07 (refactor cross-épica) es la story de mayor riesgo de regresión."
echo "       Considera feature flag para rollback si CI rojo."
echo "   4. ⚠️  E14-S10 (migration legacy) corre vacía si no hay yaml previo —"
echo "       importante para futuros forks/clones."
echo "   5. ⚠️  Las decisiones del usuario están documentadas en ADR-008 y en"
echo "       'R_Backlog_Nivel_2_E14.md' bajo 'Decisiones técnicas clave'."
echo "   6. Costo runtime de multi-profile: ~3x baseline si hay 3 perfiles activos."
echo "       Documentar en runbook tras S07."
echo ""
echo " Total stories E14: 11  |  Estimación: ~23-25h"
echo " Costo bootstrap one-shot LLM: ~\$0.20"
echo ""
