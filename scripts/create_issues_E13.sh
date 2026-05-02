#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E13 — QA Humana (épica nueva, posterior a E12)
# =============================================================================
# Requisitos: gh (GitHub CLI) instalado y autenticado (`gh auth login`)
# y jq instalado.
#
# IMPORTANTE: Antes de ejecutar este script, asegúrate de que existe la opción
# "E13-QA Humana" (o similar, comenzando con "E13") en el campo Epic del
# Project del repositorio. El script intentará auto-descubrirla; si falla,
# crearla manualmente desde la UI del Project o vía API GraphQL.
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

# Epic E13 — auto-descubierto debajo
OPT_EPIC_E13=""

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + E13 specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **Logging coherente:** Toda lógica nueva usa `structlog` con campos estándar (`timestamp`, `level`, `module`, `event`, `correlation_id`).
6. **Sin regresión cross-épica:** Los tests de las épicas afectadas (E07, E09, E10, E11, E12 según corresponda al story) siguen pasando.
7. **Origen documentado:** El PR menciona explícitamente la story original de la épica de la que se rescata (ej. "Rescata E07-S04").
8. **Audit trail:** Si la story añade mutaciones críticas, generan entry en `audit_log` (cuando E13-S05 esté cerrada).
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story implica cambios visibles al usuario, actualizar `HUMAN_SETUP.md` o `docs/runbook.md` según corresponda.'

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
# 🔍 AUTO-DESCUBRIMIENTO DEL OPTION ID DE LA ÉPICA E13
# ---------------------------------------------------------------------------
echo -e "${YELLOW}Auto-descubriendo OPT_EPIC_E13 desde el Project...${NC}"
OPT_EPIC_E13=$(discover_epic_option_id "E13")

if [ -z "$OPT_EPIC_E13" ]; then
    echo -e "${RED}❌ ERROR:${NC} No se encontró opción que comience con 'E13' en el campo Epic del Project #${PROJECT_NUMBER}."
    echo ""
    echo "   Para resolverlo, crea la opción 'E13-QA Humana' (o similar) en:"
    echo "   https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}/settings/fields/${FIELD_EPIC#PVTSSF_}"
    echo ""
    echo "   Alternativa CLI (requiere obtener el field ID exacto sin prefijo):"
    echo "   gh api graphql -f query='mutation {"
    echo "     updateProjectV2Field(input: {"
    echo "       fieldId: \"${FIELD_EPIC}\""
    echo "       singleSelectOptions: [{name: \"E13-QA Humana\", color: PURPLE, description: \"Épica E13\"}]"
    echo "     }) { projectV2Field { ... on ProjectV2SingleSelectField { options { id name } } } }"
    echo "   }'"
    echo ""
    echo "   Luego re-ejecuta este script."
    exit 1
fi

echo -e "  ${GREEN}✓${NC} OPT_EPIC_E13 = $OPT_EPIC_E13"
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

# Labels nuevos para E13
create_label_if_missing "epic:E13"                   "e1bee7" "Épica E13 — QA Humana (rescate de desvíos cross-épica)"
create_label_if_missing "component:human-qa"         "8e24aa" "Flujos de revisión humana sobre decisiones IA"

# Labels existentes (idempotente: no recrea si ya existen)
create_label_if_missing "status:ready"               "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "type:feature"               "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"                  "fbca04" "Tests, fixtures, security scans"
create_label_if_missing "type:cli"                   "8b4789" "Comandos CLI"
create_label_if_missing "type:docs"                  "c5def5" "Documentación, runbooks"
create_label_if_missing "type:refactor"              "fef2c0" "Cross-cutting refactor"
create_label_if_missing "type:infra"                 "1d76db" "Infraestructura, deploy"
create_label_if_missing "component:dashboard"        "9c27b0" "Páginas y endpoints"
create_label_if_missing "component:operations"       "455a64" "Backups, runbook, DR"
create_label_if_missing "component:audit"            "ff7043" "Audit logs, compliance"
create_label_if_missing "component:security"         "b71c1c" "Secrets, rate limit, hardening"
create_label_if_missing "component:observability"    "5cb85c" "Logs, metrics, alertas"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E13
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E13 (QA Humana)"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E13-S01 — Página Manual Review (tier C) en dashboard
# ---------------------------------------------------------------------------
create_issue \
    "[E13-S01] Página Manual Review (tier C) en dashboard" \
    "${WARNING_TEXT}

## 🎯 Origen
Esta story se movió desde **E07-S04** durante la verificación de la Épica 7 (ver \`docs/Plan automatizado.../K_Backlog_Nivel_2_E7.md\`). En su épica original quedó como placeholder de 12 líneas (\`pages/3_🔍_Manual_Review.py\` con \`st.info(\"Placeholder: Implementation coming in next stories.\")\`). Por decisión del usuario se difirió a esta épica nueva en lugar de implementarse en E7.

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** revisar jobs tier C ambiguos (\`status='manual_review'\`), **para que** decida promover a queue o descartar sin perder oportunidades borderline.

## 📐 Alcance Técnico

### Página Streamlit
- La página \`src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py\` lista jobs \`status='manual_review'\`.
- Cards más detalladas que las de **New Matches** (más contexto necesario para decidir):
  - JD completa (collapsible).
  - \`score_data\` completo en formato leíble (yellow_flags resaltados).
  - Razón principal de \"manual_review\" (de \`score_data.recommendation.reason_short\`).

### Acciones por job
- **Promote to Queue** — transiciona a \`status='queued'\` (entra al flujo normal de aplicación).
- **Re-score** — re-ejecuta scoring con prompt actual + Sonnet 4.6 (variante 7B del Documento A).
- **Reject** — transiciona a \`status='rejected'\` con razón.

### UX
- Filtro por antigüedad (jobs viejos en review acumulan polvo).
- Indicador top: \"X jobs esperan review, Y > 7 días sin decisión\".

## 🛠️ Tasks

- Reemplazar el placeholder de \`src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py\` por la implementación real, similar en estructura a \`pages/1_📥_New_Matches.py\` pero con cards más densos.
- Componente reutilizable \`render_manual_review_card(job)\` en \`dashboard/components.py\` (o ampliar el existente \`render_job_card\` con un modo \`compact=False\`).
- Botón **Re-score** invoca \`JobScorer\` con override de modelo (Sonnet 4.6); mostrar diff entre el score original y el re-score si difieren > 10 puntos.
- Botón **Promote to Queue** llama a \`JobRepo.mark_status(job.id, JobStatus.QUEUED)\`.
- Botón **Reject** llama a \`JobRepo.mark_status(job.id, JobStatus.REJECTED)\` con captura de razón en un \`st.dialog\`.
- Indicador top calculado a partir de \`Job.scored_at\` (días desde el scoring inicial, no \`scraped_at\`).
- Test E2E mínimo en \`tests/e2e/dashboard/\` (\`test_manual_review.py\`): navegar a la página, ver al menos 1 card, click en \"Promote to Queue\", verificar que el job desaparece de la lista.

## 📝 Notas

- **Re-score con Sonnet** es directo del Documento A variante 7B. Si el nuevo score difiere significativamente, sirve como señal de que el caso es genuinamente ambiguo y vale empujar a \`queued\` con un disclaimer en notas.
- **Antigüedad como métrica:** jobs en \`manual_review\` > 7 días son señal de procrastinación. La UI debe empujar a decidir (color rojo en el indicador, ordenar más antiguos primero por defecto).
- **Coste del Re-score on-demand:** Sonnet a ~\$0.003 por job, despreciable para uso individual desde dashboard.

## 🧪 Criterios de Aceptación
- [ ] La página \`pages/3_🔍_Manual_Review.py\` lista jobs \`status='manual_review'\`.
- [ ] Cards muestran JD collapsible, \`score_data\` completo con yellow_flags resaltados, razón de manual_review.
- [ ] Botón **Promote to Queue** funciona end-to-end (DB actualizada).
- [ ] Botón **Re-score** ejecuta scoring con Sonnet y muestra diff si > 10 puntos.
- [ ] Botón **Reject** captura razón en dialog y persiste.
- [ ] Filtro por antigüedad operativo.
- [ ] Indicador \"X jobs esperan review, Y > 7 días\" funcional.
- [ ] Test E2E Playwright pasa.
- [ ] La notificación \`st.warning\` en la página actual (apuntando a E13) se elimina al implementar.

## 🔗 Dependencias
- Bloqueante: Épica E07 cerrada (foundation Streamlit + auth).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:human-qa,epic:E13" \
    "$OPT_EPIC_E13" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E13-S02 — Comandos CLI faltantes de outreach (suite humana)
# ---------------------------------------------------------------------------
create_issue \
    "[E13-S02] Comandos CLI faltantes de outreach (suite humana)" \
    "${WARNING_TEXT}

## 🎯 Origen
Esta story rescata el subset de **E09-S06** que quedó sin implementar durante la verificación de la Épica 9 (ver \`docs/Plan automatizado.../M_Backlog_Nivel_2_E9.md\`). De los 8 comandos CLI que pedía el AC original sólo se implementaron 3 (\`outreach import\`, \`outreach stats\`, \`outreach check-cadence\`); los 6 restantes se difirieron a esta épica por decisión del usuario.

El workflow completo está disponible desde el dashboard (E7-S05 + E9-S07), por lo que esta story no bloquea operación. Su valor es **paridad CLI ↔ UI** y soporte para automatización ad-hoc desde scripts/cron del usuario.

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** los 6 comandos CLI faltantes de \`jobhunter outreach\`, **para que** el workflow completo (añadir contacto → priorizar → generar draft → marcar enviado/respondido → consultar historial) viva también en terminal sin depender del dashboard.

## 📐 Alcance Técnico

Los 6 comandos siguen las mismas convenciones que el resto de la suite (\`typer\` + \`rich\` para output, exit code 0 ok / 1 error, secrets vía \`Settings\`). Cada uno mapea a métodos ya existentes en \`OutreachRepo\` o \`OutreachMessageRepo\` — esta story es plumbing, no lógica nueva.

### \`outreach add\`
- Flags: \`--name\` (required), \`--linkedin-url\`, \`--company\`, \`--role\`, \`--market\` (enum \`OutreachMarket\`), \`--notes\`.
- Detecta duplicado por \`linkedin_url\` (vía \`OutreachRepo.find_by_linkedin_url\`) y aborta con exit 1 si existe.
- Aplica scoring heurístico de E09-S04 al insertar (\`outreach.scoring.calculate_heuristic_score\`).
- Output: tabla rich con el contacto creado + \`id\` para uso posterior.

### \`outreach candidates\`
- Flags: \`--limit N\` (default 10), \`--market germany|eu_wide|uk|...\`, \`--min-score N\` (default sin filtro).
- Ordenamiento literal del AC original: **\`quality_score DESC\`, \`last_contacted_at ASC NULLS FIRST\`** (prioriza alto-score nunca-contactado).
- Output: tabla rich con \`id\`, \`name\`, \`company\`, \`role\`, \`quality_score\`, \`status\`, \`last_contacted_at\` (humano: \"hace 5 días\" o \"—\").

### \`outreach draft <contact-id>\`
- Argumento posicional: \`contact_id\` (UUID del contacto).
- Flags: \`--type A_inhouse|B_boutique|C_senior|D_followup\` (required), \`--note TEXT\` (required, ≥20 chars — misma validación que el dashboard E9-S07), \`--language en|es\` (default \`en\`), \`--copy\` (opcional, copia al portapapeles vía \`pyperclip\` o equivalente).
- **Default: NO copia al clipboard** (literal del AC original — evita pegar accidentalmente).
- Invoca \`outreach.generator.generate_message\`; persiste el resultado como \`OutreachMessage\` con \`status='draft'\`; muestra el body con \`rich.markdown.Markdown\`.
- Footer del output: \`id\` del mensaje + comando sugerido para marcar enviado (\`jobhunter outreach sent <message-id>\`).
- Si la política de 2 toques (E9-S05) bloquea la creación (\`OutreachMessageRepo.create_draft\` raise \`ValueError\`), el comando termina con exit 1 y mensaje explicativo.

### \`outreach sent <message-id>\`
- Argumento posicional: \`message_id\` (UUID).
- Flag opcional: \`--at TIMESTAMP\` (ISO 8601, default: ahora).
- Invoca \`OutreachMessageRepo.mark_sent\`; transiciona el contacto a \`OutreachStatus.CONTACTED\` automáticamente.

### \`outreach replied <message-id>\`
- Argumento posicional: \`message_id\` (UUID).
- Flag opcional: \`--at TIMESTAMP\`.
- Invoca \`OutreachMessageRepo.mark_replied\`; transiciona el contacto a \`OutreachStatus.REPLIED\`.

### \`outreach list\`
- Flags: \`--status draft|sent|replied|ghosted|discarded\` (multi-select posible, repetible), \`--contact-id UUID\`, \`--last N\` (días, default 14).
- Output: tabla rich con \`id\`, \`contact_name\`, \`template_type\`, \`status\`, \`created_at\`, \`sent_at\`, \`replied_at\`.
- Soporta combinación: \`--status sent --last 7\` muestra mensajes enviados los últimos 7 días sin reply.

## 🛠️ Tasks

- Implementar los 6 comandos en \`src/jobhunter/__main__.py\` (sub-Typer \`outreach_app\`, mismo patrón que los 3 ya existentes).
- Helper \`_format_contact_row(contact)\` y \`_format_message_row(msg)\` en algún módulo compartido (p. ej. \`cli/formatters.py\`) — evita duplicar formatting entre \`candidates\`, \`list\`, y la tabla del dashboard.
- Verificar que \`Settings.OUTREACH_MODEL\` se respeta cuando \`draft\` invoca al generator.
- Tests CLI con \`typer.testing.CliRunner\` para cada comando: golden path + 1 caso de error (duplicado en \`add\`, política de 2 toques en \`draft\`, message_id inexistente en \`sent\`/\`replied\`).
- Smoke test E2E (no Playwright, sólo CLI): correr la secuencia del ejemplo del AC con DB seeded y verificar que cada paso funciona.
- Actualizar README o \`docs/runbook.md\` si es necesario para incluir el workflow CLI completo (era el ejemplo de la sección \"Definition of Done\" del Documento M).

## 📝 Notas

- **Por qué se difirió.** Durante la verificación de E9 se detectó que de los 8 comandos CLI del AC sólo 3 estaban implementados. El dashboard (E9-S07) cubre el workflow visual, así que el sistema es operativo end-to-end. El usuario eligió diferir vs. bloquear el cierre de E9.
- **Reuso máximo.** Cada comando es un wrapper thin sobre métodos que ya existen y están testeados. La complejidad real está en formatting + validación de inputs, no en lógica nueva.
- **\`--copy\` requiere dependencia opcional.** Si añadirla pesa demasiado, documentar el patrón \"pipe a \`pbcopy\`/\`xclip\`\" en lugar de añadir dep: \`jobhunter outreach draft <id> --type A_inhouse --note \"...\" | pbcopy\`.
- **Test E2E mínimo.** Si el smoke test resulta más caro que su valor (por requerir DB real + mocks de Anthropic), reducirlo a tests unitarios por comando con \`CliRunner\`.

## 🧪 Criterios de Aceptación
- [ ] Los 6 comandos CLI presentes en \`outreach_app\` y funcionales.
- [ ] \`outreach add\` detecta duplicados por linkedin_url.
- [ ] \`outreach candidates\` ordena por \`quality_score DESC, last_contacted_at ASC NULLS FIRST\`.
- [ ] \`outreach draft\` valida \`--note ≥20 chars\` y propaga la política de 2 toques como exit 1.
- [ ] \`outreach sent\` transiciona el contacto a \`CONTACTED\` automáticamente.
- [ ] \`outreach replied\` transiciona el contacto a \`REPLIED\`.
- [ ] \`outreach list\` con filtros combinables.
- [ ] Tests CLI por cada comando (golden path + caso de error).
- [ ] Smoke test E2E del workflow completo pasa.

## 🔗 Dependencias
- Bloqueante: Épicas E09-S01 a E09-S05 cerradas (DB, repos, generator, scoring, cadence).

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:human-qa,epic:E13" \
    "$OPT_EPIC_E13" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E13-S03 — Email matcher: prompt versionado + CLI `email stats`
# ---------------------------------------------------------------------------
create_issue \
    "[E13-S03] Email matcher: prompt versionado + CLI email stats" \
    "${WARNING_TEXT}

## 🎯 Origen
Esta story rescata dos desvíos menores detectados durante la verificación de la Épica 10 (ver \`docs/Plan automatizado.../N_Backlog_Nivel_2_E10.md\`):

1. **De E10-S04:** el AC pedía \`prompts/email_matcher/v1.md\` versionado; ese archivo no existe — el prompt vive inline en el código de \`src/jobhunter/email/matcher.py\`. Inconsistente con el resto del sistema (E4 scoring, E6 cover letter / ATS / CV tweaks, E9 outreach) donde los prompts son \`.md\` versionados.
2. **De E10-S08:** el AC pedía CLI \`jobhunter email stats\` (tasa de match, precision, costo IA, top dominios). El sub-Typer \`email\` sólo expone \`auth\` y \`poll-and-suggest\`; las métricas equivalentes existen en el dashboard (\`MetricsService\` + página de Metrics) pero no en CLI.

Ambos son superficie operativa, no lógica de negocio nueva. Por decisión del usuario se difirieron a esta story consolidada.

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** el prompt del email matcher versionado en disco y un comando CLI con métricas de detección, **para que** iterar sobre el prompt sea diffable en PRs (igual que el resto del sistema) y la observabilidad del módulo \`email/\` no dependa exclusivamente del dashboard.

## 📐 Alcance Técnico — Parte A: Prompt versionado (rescate de E10-S04)

### Estructura
- Crear directorio \`prompts/email_matcher/\` (paralelo a \`prompts/scoring/\`, \`prompts/cover_letter/\`, \`prompts/ats_keywords/\`, \`prompts/cv_tweaks/\`, \`prompts/outreach/\`).
- Crear archivo \`prompts/email_matcher/v1.md\` con la estructura estándar del proyecto (\`## SYSTEM\` + \`## USER_TEMPLATE\` + \`## REQUIREMENTS\`), conteniendo el texto del prompt actualmente embebido en \`src/jobhunter/email/matcher.py\` (la rama de escalación a IA cuando \`confidence < 0.8\`).

### Refactor del matcher
- Reemplazar la string literal del prompt en \`matcher.py\` por una llamada a un loader (\`load_prompt_template(\"email_matcher\", \"v1\")\` o similar, reutilizando el patrón de \`scoring/prompt.py\` / \`outreach/templates.py\`).
- El loader cachea la lectura (\`functools.lru_cache\`) para no leer disco en cada email procesado.
- Persistir \`prompt_version\` en \`email_messages.match_reasoning\` (o un campo específico si se prefiere) cuando la match status es \`ai_matched\`, para que cada match quede trazable a la versión del prompt que lo generó.

### Tests
- Tests unit: el matcher produce el mismo \`MatchResult\` antes y después del refactor con la misma respuesta mockeada del LLM (regresión).

## 📐 Alcance Técnico — Parte B: CLI \`email stats\` (rescate de E10-S08)

### Comando
- \`jobhunter email stats\` con flag \`--since \"N weeks ago\"\` (default 4 semanas, alineado con \`outreach stats\`).
- Output (tabla rich) con las **5 secciones del AC original**:
  - Total emails procesados en la ventana.
  - **Tasa de match:** \`% auto_matched\`, \`% ai_matched\`, \`% unmatched\`, \`% ignored_marketing\`.
  - **Precision estimada:** \`count(user_confirmed) / (count(user_confirmed) + count(user_rejected))\` sobre los matches que el usuario revisó. Target ≥85%.
  - **Costo IA acumulado** del módulo email (filtrar \`LLMCallRepo\` por \`purpose='email_matcher'\` o el purpose que use el matcher).
  - **Top dominios** (\`from_domain\`) generadores de emails — útil para detectar marketing senders no clasificados.
- Exit code 1 si la precision cae por debajo del target (señal opcional para alerting en cron). Decidir en implementación si se activa por default o requiere flag \`--strict\`.

### Tests
- Tests CLI con \`typer.testing.CliRunner\` + DB seeded con \`email_messages\` variados (3 confirmados, 1 rechazado, 2 unmatched).

## 🛠️ Tasks

- Crear \`prompts/email_matcher/v1.md\` extrayendo el prompt actual del código (cuidar que el formato \`{placeholders}\` siga vigente).
- Implementar (o reutilizar) loader de prompts en \`email/matcher.py\`.
- Refactor del matcher para consumir el prompt cargado, no la string literal.
- Implementar \`email_stats\` en \`__main__.py\` (sub-Typer \`email_app\`).
- Helper \`_compute_email_stats(session, since)\` en \`email/orchestrator.py\` o \`email/stats.py\` (testeable aisladamente).
- Tests unit + CLI (los descritos en los AC).
- Verificar que el dashboard E7-S06 (Metrics page) sigue funcionando — si comparte el helper, mejor; si no, no romperlo.

## 📝 Notas

- **Por qué se difirió.** Durante la verificación de E10 se detectaron como desvíos menores: el sistema funciona (matcher escala correctamente, las métricas existen en dashboard). Pero la inconsistencia con el resto del proyecto (prompts versionados, CLI \`*-stats\` por módulo) justificaba un cierre limpio. El usuario eligió diferir a E13 vs. bloquear E10.
- **No introduce dependencia nueva.** El loader de prompts ya existe patrón-wise; sólo hay que aplicarlo a \`email_matcher\`.
- **Test de regresión es crítico.** Si el refactor del prompt cambia el comportamiento del matcher (p. ej. por un \`\\n\` distinto), las heurísticas del módulo se desestabilizan. El test debe usar fixtures reales de email + respuesta mockeada del LLM y verificar que \`MatchResult\` es idéntico.

## 🧪 Criterios de Aceptación
- [ ] Archivo \`prompts/email_matcher/v1.md\` existe con estructura SYSTEM/USER_TEMPLATE/REQUIREMENTS.
- [ ] \`matcher.py\` carga el prompt desde el archivo, no usa string literal.
- [ ] Test de regresión: mismo \`MatchResult\` antes y después del refactor con respuesta mockeada idéntica.
- [ ] CLI \`email stats\` implementado con las 5 secciones del AC.
- [ ] CLI \`email stats --since\` funcional.
- [ ] Tests CLI cubren caso con DB seeded.
- [ ] Dashboard E7 Metrics sigue funcionando sin regresión.

## 🔗 Dependencias
- Bloqueante: Épicas E10-S04 (matcher) y E10-S08 (tests + métricas) cerradas.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:refactor,type:cli,component:human-qa,component:observability,epic:E13" \
    "$OPT_EPIC_E13" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E13-S04 — Página dashboard Analytics + workflow `monthly-report`
# ---------------------------------------------------------------------------
create_issue \
    "[E13-S04] Página dashboard Analytics + workflow monthly-report" \
    "${WARNING_TEXT}

## 🎯 Origen
Esta story rescata el desvío detectado durante la verificación de la Épica 11 (ver \`docs/Plan automatizado.../O_Backlog_Nivel_2_E11.md\`). El AC de E11-S07 pedía dos piezas que no se implementaron:

1. **Página dashboard \`pages/8_📈_Analytics.py\`** con 4 secciones (Recommendations con quickbuttons Snooze/Acted/Ignore, A/B tests activos, False rejects review, Reports archive). El slot \`8_\` ya está ocupado por \`8_🏥_Status.py\` (System Health, parte de E12); esta story debe colocar la página en \`9_📈_Analytics.py\` o renombrar el orden.
2. **Workflow \`.github/workflows/monthly-report.yml\`** con \`cron: '0 8 1 * *'\` (día 1 de cada mes 08:00 UTC = 03:00 COT) que invoque \`analytics report\` y mande el PDF por email automáticamente.

Toda la lógica subyacente existe — \`analytics/recommendations.py\` produce las recomendaciones, \`analytics/report_generator.py\` genera el PDF vía \`weasyprint\`, \`analytics/ab_testing.py\` expone resultados, \`analytics false-rejects\` lista los promovidos manualmente. Falta sólo la **superficie de presentación** (UI dashboard + cron mensual).

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** la página de analytics avanzado en el dashboard y el envío mensual automático del reporte, **para que** el ciclo de mejora continua de E11 cierre sin pasos manuales: las recomendaciones se ven al inicio de la semana en UI, y el reporte mensual narrativo llega por email el día 1 sin tener que invocarlo.

## 📐 Alcance Técnico — Parte A: Página dashboard Analytics

### Página
- Crear \`src/jobhunter/dashboard/pages/9_📈_Analytics.py\` (slot \`8_\` está ocupado por \`8_🏥_Status.py\` de E12, evitar conflicto).
- La página requiere \`require_auth()\` y renderiza header + sidebar como las demás (\`render_header()\`, \`render_sidebar()\`).

### Sección 1 — Recommendations
Lista paginada de \`analytics.recommendations.get_recommendations(session)\` con priority badges (P1/P2/P3 con colores rojo/amarillo/gris) y, por cada item, los 3 quickbuttons literales del AC:
- **Snooze** — marca como vista, oculta por 7 días (persistir estado en \`notifications_sent\` con \`dedup_key=f\"reco_snooze:{recommendation_hash}\"\` o tabla nueva \`recommendation_state\` si conviene).
- **Acted on** — marca como resuelta, no aparece más.
- **Ignore** — descarta permanentemente.

### Sección 2 — A/B tests activos
Tabla con \`name\`, \`variants\`, \`sample_size_per_variant\`, \`current_significance\`, \`started_at\`. Click en una fila navega a detalle con la salida de \`get_ab_test_results(session, name)\`. Si el test está concluido o tiene significancia ≥0.95, muestra botón \"End test\" que invoca el repo de A/B con \`--winner\`.

### Sección 3 — False rejects review
Lista paginada de jobs con \`tier='REJECT'\` y \`manually_promoted_at IS NOT NULL\` (datos de E11-S04). Cada fila con preview del job (título, empresa, snippet de description) + botón \"Promote\" que ejecuta la promoción manual (\`JobRepo.mark_status\` a \`QUEUED\` + insertar \`application_event\`).

### Sección 4 — Reports archive
Lista de archivos en \`reports/\` (filtrar por \`*.pdf\` y \`*.md\`) ordenada por fecha descendente. Cada entrada con preview del primer párrafo (markdown) + botón \"Download\" que sirve el archivo via \`st.download_button\`.

### Botones de acción rápida
- **Botón \"Generate report\"** en la cabecera de la página, dispara \`analytics.report_generator\` para el mes actual on-demand con un \`st.spinner\` mientras se ejecuta (~30-60s con Sonnet).
- **Botón \"Export to PDF\"** en cualquier sub-vista convierte la vista actual a PDF descargable usando \`weasyprint\`.

### Test
Test E2E mínimo en \`tests/e2e/dashboard/test_analytics_page.py\`: navegar, ver al menos 1 recommendation, click en \"Snooze\", verificar que desaparece.

## 📐 Alcance Técnico — Parte B: Workflow \`monthly-report\`

### Workflow YAML
Crear \`.github/workflows/monthly-report.yml\`:
- \`cron: '0 8 1 * *'\` literal del AC.
- \`workflow_dispatch\` con input opcional \`month: str\` para regenerar un mes pasado.
- Steps idénticos en estructura a \`weekly-digest.yml\` (checkout, setup uv, sync, composite action \`setup-env\` con secrets de SMTP + Anthropic, \`uv run jobhunter analytics report --month \$MONTH --output pdf\`).
- Después de generar el PDF, step que envía email vía \`EmailNotifier\` de E5 con el PDF adjunto (extender \`EmailNotifier\` si no soporta attachments — actualmente parece solo body multipart text/HTML).
- Timeout: 10 minutos.
- \`concurrency: { group: monthly-report, cancel-in-progress: false }\`.
- \`Alert on Failure\` step usando la composite action de E8-S06.

### CLI auxiliar
\`analytics report --send-email\` opcional para invocar manualmente el flujo de generar+enviar (útil para testing del workflow).

### Documentación
Documentar en \`docs/runbook.md\` cómo regenerar un reporte de un mes específico vía \`workflow_dispatch\`.

## 🛠️ Tasks

- Crear página Streamlit con las 4 secciones (estimado: 60-70% del esfuerzo total de la story).
- Componente reutilizable \`render_recommendation_card(reco)\` que encapsula priority badge + quickbuttons.
- Persistencia de estado de recommendations (snooze/acted/ignore) — decidir entre extender \`notifications_sent\` o crear tabla nueva \`recommendation_state\` (recomendado: tabla nueva para no contaminar \`notifications_sent\` con semántica distinta).
- Migration Alembic si se opta por tabla nueva.
- Workflow YAML \`monthly-report.yml\`.
- Extender \`EmailNotifier\` (E5-S04) si no soporta attachments.
- Test E2E Playwright + smoke test del workflow vía \`workflow_dispatch\`.

## 📝 Notas

- **Por qué se difirió.** Durante la verificación de E11 se detectó que la lógica subyacente (recommendations, report generation, A/B testing, false rejects) está completa y testeada, pero la superficie de presentación (página dashboard + cron mensual) no se construyó. El sistema funciona end-to-end vía CLI; lo que falta es la ergonomía visual.
- **Slot \`8_\` ocupado.** La página \`8_🏥_Status.py\` (Health) probablemente pertenece a E12. Esta story usa el slot \`9_\` para evitar conflicto y no romper el orden alfabético de Streamlit.
- **\`EmailNotifier\` con attachments.** Si actualmente no soporta, es ~30 líneas extender \`aiosmtplib\` con \`MIMEApplication\` para el PDF. Tarea menor, pero hay que verificarla antes de la implementación.
- **Analytics page = portfolio piece.** Esta página es la cara visible del ciclo de mejora continua del sistema. Mostrarla en una entrevista (especialmente para roles AI/ML/data) es una historia poderosa: \"el sistema se observa a sí mismo y sugiere qué cambiar\".

## 🧪 Criterios de Aceptación
- [ ] Página \`pages/9_📈_Analytics.py\` existe con las 4 secciones.
- [ ] Recommendations con quickbuttons Snooze/Acted/Ignore funcionales.
- [ ] A/B tests activos con detalle accesible.
- [ ] False rejects con botón Promote operativo.
- [ ] Reports archive con preview y download.
- [ ] Botón \"Generate report\" on-demand funcional.
- [ ] Botón \"Export to PDF\" funcional.
- [ ] Workflow \`monthly-report.yml\` válido con \`cron: '0 8 1 * *'\`.
- [ ] \`EmailNotifier\` soporta attachments (PDF).
- [ ] Workflow \`workflow_dispatch\` ejecuta exitosamente y envía email.
- [ ] Test E2E Playwright pasa.

## 🔗 Dependencias
- Bloqueante: Épicas E11-S05 (report_generator) y E11-S06 (recommendations) cerradas.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:human-qa,component:operations,epic:E13" \
    "$OPT_EPIC_E13" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E13-S05 — Audit log + compliance lite + `trivy` en CI
# ---------------------------------------------------------------------------
create_issue \
    "[E13-S05] Audit log + compliance lite + trivy en CI" \
    "${WARNING_TEXT}

## 🎯 Origen
Esta story rescata el desvío real detectado durante la verificación de la Épica 12 (ver \`docs/Plan automatizado.../P_Backlog_Nivel_2_E12.md\`):

1. **De E12-S06 (desvío real):** no existe modelo \`AuditLog\`, ninguna migración de tabla \`audit_log\`, ningún decorator \`@audit_logged\`, ningún CLI \`audit query\` ni \`compliance export-data\` ni \`compliance delete-all\`. El AC pedía trazabilidad explícita de mutaciones críticas (login/logout, bulk deletes, cambios de prompt versions, backups/restores, rotación de secretos, acceso a OAuth tokens) — ninguna está. La única \"auditoría\" presente es el tracking básico de E12-S05 (\`failed_login_attempts\`/\`blocked_ips\`), que es para abuse prevention, no audit trail completo.
2. **De E12-S08 (detalle menor):** \`bandit\` y \`pip-audit\` corren en CI pero **falta \`trivy fs .\`** que el AC pedía como tercer scanner. Se consolida en esta misma story por afinidad temática (security surface).

Por decisión del usuario se difirieron a esta story consolidada en lugar de bloquear el cierre de E12.

## 🎯 Contexto Arquitectónico
**Como** dueño del sistema, **quiero** trazabilidad completa de operaciones sensibles + utilidades de export/erasure de datos personales + scanner adicional \`trivy\` en CI, **para que** pueda responder \"qué pasó y cuándo\" ante incidentes, prepare el terreno mínimo de compliance, y la superficie de seguridad esté completa.

## 📐 Alcance Técnico — Parte A: Audit log (rescate de E12-S06)

### Migration Alembic
Crear tabla \`audit_log\` con las columnas literales del AC original:
- \`id\` UUID PK.
- \`event_type\` VARCHAR (enum: \`login\`, \`logout\`, \`data_access\`, \`data_mutation\`, \`config_change\`, \`secret_rotated\`, \`backup_created\`, \`restore_executed\`, \`bulk_delete\`).
- \`actor\` VARCHAR (\`user\`, \`system\`, \`cron:workflow_name\`, etc.).
- \`target_entity\` VARCHAR NULLABLE (ej. \`Job\`, \`Application\`, \`OutreachContact\`).
- \`target_id\` UUID NULLABLE.
- \`action\` VARCHAR — verbo descriptivo.
- \`metadata\` JSONB — contexto adicional.
- \`ip_address\` VARCHAR NULLABLE.
- \`created_at\` TIMESTAMPTZ default now().

Índices: \`(event_type, created_at DESC)\`, \`(actor, created_at DESC)\`, \`(target_entity, target_id)\`.

### Modelo + repo
Modelo SQLAlchemy \`AuditLog\` en \`db/models.py\` + \`AuditLogRepo\` en \`db/repos/audit_log.py\` con \`record(event_type, actor, ...)\` y \`query(filters, since, limit)\`.

### Decorator
\`@audit_logged(event_type, action)\` en \`src/jobhunter/audit/decorator.py\` (o módulo similar) que captura automáticamente el evento al ejecutar la función decorada.

### Aplicar el decorator (o llamada explícita al repo)
En las **mutaciones críticas literales del AC**:
- Login/logout dashboard (\`dashboard/auth.py\`).
- Bulk deletes (cualquier endpoint que borre múltiples entidades).
- Cambios de prompt versions (sería un evento futuro, dejar el hook listo).
- Backups y restores (\`db/backup.py\`).
- Rotación de secretos (cuando exista la herramienta CLI).
- Acceso a OAuth tokens (descrifrado en \`email/gmail_client._get_service\`).

### CLI
\`jobhunter audit query [--since X] [--actor Y] [--event Z] [--limit N]\` con output tabla rich.

### Página dashboard
\"Audit Log\" — agregar como sección a \`8_🏥_Status.py\` o como sub-tab en la nueva \`9_📈_Analytics.py\` (E13-S04). Decisión: sub-tab en Analytics para no saturar Status.

### Tests
Tests unit: cada \`event_type\` puede registrarse y consultarse; decorator captura args correctamente.

## 📐 Alcance Técnico — Parte B: Compliance lite (rescate de E12-S06)

### CLI export
\`jobhunter compliance export-data [--output PATH]\` que exporta toda la data personal del usuario en JSON: jobs aplicados (con scores y cover letters), \`outreach_contacts\` y \`outreach_messages\`, \`email_messages\`, \`audit_log\`, \`oauth_tokens\` (con tokens redactados). Útil para \"right to access\" preparation.

### CLI delete
\`jobhunter compliance delete-all --confirm-twice\` que borra TODA la data personal:
- Pide confirmación textual: \"Type 'DELETE-ALL' to confirm\".
- Pide segunda confirmación explícita.
- Persiste el evento en \`audit_log\` ANTES del delete (para que la auditoría sobreviva al borrado).
- Borra en orden correcto respetando FKs: \`email_messages\`, \`outreach_messages\`, \`application_events\`, \`applications\`, \`outreach_contacts\`, \`oauth_tokens\`, \`notifications_sent\`, \`jobs\`.
- NO borra: \`audit_log\` (queda como única evidencia), \`alembic_version\`, \`failed_login_attempts\`/\`blocked_ips\` (security ops).

## 📐 Alcance Técnico — Parte C: \`trivy\` en CI (rescate de E12-S08)

### Step nuevo
En \`.github/workflows/ci.yml\` después de \`pip-audit\`:
\`\`\`yaml
- name: Filesystem vulnerability scan with trivy
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: fs
    scan-ref: .
    severity: CRITICAL,HIGH
    exit-code: '1'
\`\`\`

### Manejo de findings
- Si trivy reporta findings nuevos no triadeados, CI falla y se genera un issue (manual o vía workflow_dispatch).
- Documentar en \`docs/runbook.md\` cómo investigar findings de trivy y cómo añadir \`.trivyignore\` para falsos positivos.

## 🛠️ Tasks

- **Parte A:** migration \`audit_log\` + modelo + repo + decorator + aplicación cross-épica + CLI \`audit query\` + tests.
- **Parte B:** CLI \`compliance export-data\` + CLI \`compliance delete-all --confirm-twice\` con doble confirmación.
- **Parte C:** step \`trivy\` en \`ci.yml\` + \`.trivyignore\` inicial vacío + nota en runbook.
- Sub-tab \"Audit Log\" en página Analytics (depende de E13-S04 cerrada; si no, añadir directamente en \`8_🏥_Status.py\` como sección).
- Test E2E: registrar manual login → ver evento en \`audit query\`.
- Test E2E destructivo: ejecutar \`compliance delete-all --confirm-twice\` con DB seeded mínima → verificar que \`audit_log\` y \`alembic_version\` sobreviven.

## 📝 Notas

- **Por qué se difirió.** Audit log es trabajo defensivo significativo (~2h) cuya falta no impide operación. El sistema funciona sin él; pero ante un incidente real (credencial filtrada, mutación accidental), no hay forma de reconstruir \"qué pasó\". El usuario eligió diferir vs. bloquear E12.
- **\`@audit_logged\` como decorator vs llamada explícita.** El decorator ahorra boilerplate pero acopla el módulo a \`audit/\`. Para mutaciones muy puntuales (5-10 callsites), llamada explícita es más explícita. Decidir caso a caso.
- **\`compliance delete-all\` es nuclear.** Doble confirmación + audit log antes del delete + tests específicos del flujo. NUNCA disponible desde dashboard (sólo CLI con flags), para evitar accidentes.
- **\`trivy\` puede ser ruidoso.** Su DB de vulnerabilidades crece a diario. Setear \`severity: CRITICAL,HIGH\` evita el ruido de LOW/MEDIUM. El \`.trivyignore\` es para excepciones documentadas, no para silenciar findings legítimos.
- **\`audit_log\` no es GDPR compliance.** Es \"compliance lite\" — preparación mínima. Si en el futuro se abre el sistema a otros usuarios, requiere assessment formal.

## 🧪 Criterios de Aceptación
- [ ] Tabla \`audit_log\` creada vía migration con todas las columnas del AC.
- [ ] Modelo + repo funcionales.
- [ ] Decorator \`@audit_logged\` aplicado en login/logout, backups, restores, OAuth token access.
- [ ] CLI \`audit query\` con filtros operativo.
- [ ] CLI \`compliance export-data\` produce JSON con tokens redactados.
- [ ] CLI \`compliance delete-all --confirm-twice\` requiere doble confirmación + persiste audit antes del delete + preserva \`audit_log\`/\`alembic_version\`.
- [ ] Step \`trivy\` añadido a \`ci.yml\` con severity CRITICAL,HIGH.
- [ ] \`.trivyignore\` inicial vacío + nota en runbook.
- [ ] Tests E2E cubren registro de evento y delete destructivo controlado.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada (DB infra).
- Recomendado: E13-S04 cerrada (sub-tab en página Analytics).

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,type:infra,component:audit,component:security,component:human-qa,epic:E13" \
    "$OPT_EPIC_E13" \
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
echo " 🎉 BACKLOG L2 CREADO PARA LA ÉPICA E13 — QA HUMANA (5 stories, ~8h)."
echo ""
echo " Próximos pasos:"
echo "   1. Verifica los issues en: https://github.com/${FULL_REPO}/issues?q=is%3Aissue+label%3Aepic%3AE13"
echo "   2. Verifica el proyecto en: https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo "   3. ⚠️  E13-S01 → E13-S04 son rescates de stories diferidas durante"
echo "       la verificación de E07, E09, E10, E11. Cada PR debe referenciar"
echo "       explícitamente el origen (E07-S04, E09-S06, etc.)."
echo "   4. ⚠️  E13-S05 (audit + compliance + trivy) bloquea cierre de seguridad"
echo "       avanzada del proyecto."
echo "   5. Antes de empezar E13-S04, considera completar E13-S05 primero si"
echo "       quieres que el sub-tab Audit Log viva en la página Analytics."
echo ""
echo " Total stories E13: 5  |  Estimación: ~8h"
echo ""
