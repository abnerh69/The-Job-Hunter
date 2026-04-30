#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E9 — Recruiter Outreach Module
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
OPT_EPIC_E09="46ad1f6d"     # E9-Outreach

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + outreach specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **LLM fixtures (si aplica):** Tests que invocan al LLM usan fixtures grabadas; nunca consumen API real en CI.
6. **Costos observables:** Cada llamada LLM se registra en `llm_calls` con `purpose="outreach_message"`.
7. **Cero auto-send:** El sistema NUNCA envía mensajes automáticamente a LinkedIn/Xing/email. Solo genera drafts; el usuario hace copy-paste manual y marca como sent.
8. **Política 2 toques:** El sistema fuerza máximo 2 mensajes por contacto sin respuesta. Después se descarta o marca warm manualmente.
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story añade un nuevo template, se versiona en `prompts/outreach/vN/` con el nombre del template.'

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
create_label_if_missing "epic:E09"                "e91e63" "Épica E09 — Recruiter Outreach Module"
create_label_if_missing "type:feature"            "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"               "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"                "8b4789" "Comandos CLI"
create_label_if_missing "component:outreach"      "ff80ab" "Módulo outreach, mensajes, cadencia"
create_label_if_missing "component:db"            "d93f0b" "Migraciones, repos, persistencia"
create_label_if_missing "component:llm"           "5319e7" "LLM client, prompts, costos"
create_label_if_missing "component:dashboard"     "9c27b0" "Páginas y componentes Streamlit"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E09
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E09"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E09-S01 — Tabla outreach_messages + repo extension
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S01] Tabla \`outreach_messages\` + repo extension" \
    "## 🎯 Contexto Arquitectónico
Cada mensaje de outreach (draft, sent, replied, follow-up) requiere persistencia para audit trail y métricas de efectividad por template/contacto. \`OutreachContact\` (ya existe de E2-S04) se relaciona 1:N con \`OutreachMessage\` — un contacto puede recibir múltiples mensajes a lo largo del tiempo (mensaje inicial + follow-up).

## 📐 Alcance Técnico

### Migration Alembic: \`add_outreach_messages_table\`
- \`id\` UUID PK.
- \`contact_id\` UUID FK → \`outreach_contacts(id)\`, ON DELETE CASCADE.
- \`template_type\` VARCHAR (enum: \`A_inhouse\`, \`B_boutique\`, \`C_senior\`, \`D_followup\`, \`custom\`).
- \`template_version\` VARCHAR (ej. \"v1\") — versión que generó este mensaje.
- \`subject\` TEXT NULLABLE.
- \`body\` TEXT NOT NULL.
- \`body_edited_by_user\` BOOL — true si el usuario modificó el draft generado por IA.
- \`research_notes\` TEXT NULLABLE — la frase específica que el usuario aportó al generar.
- \`model_used\` VARCHAR.
- \`cost_usd\` NUMERIC.
- \`status\` VARCHAR (enum: \`draft\`, \`sent\`, \`replied\`, \`ghosted\`, \`discarded\`).
- \`created_at\`, \`sent_at\`, \`replied_at\` TIMESTAMPTZ.
- \`parent_message_id\` UUID NULLABLE FK self — para tracking de threads de follow-up.

### Índices
- \`(contact_id, created_at DESC)\` — historial por contacto.
- \`(status, sent_at)\` parcial sobre estados activos.

### Repo
- \`OutreachMessageRepo\` en \`db/repos/outreach_messages.py\` con:
  - \`create_draft(contact_id, template_type, body, ...)\`.
  - \`mark_sent(message_id, sent_at=None)\` — actualiza status, persiste timestamp, transiciona contact a \`contacted\`.
  - \`mark_replied(message_id, replied_at=None)\` — transiciona contact a \`replied\`.
  - \`mark_ghosted(message_id)\` — automático tras 21 días sin reply.
  - \`list_by_contact(contact_id) -> list[OutreachMessage]\`.
  - \`list_pending_followups(today, days_threshold=7) -> list[OutreachMessage]\`.

## 📝 Decisión clave
**\`body_edited_by_user\`** es señal valiosa: si 80% de los mensajes generados se editan significativamente, el prompt necesita iteración.

## 🧪 Criterios de Aceptación
- [ ] Migration up/down ejecuta limpiamente.
- [ ] Tests CRUD básico de \`OutreachMessageRepo\`.
- [ ] Test cascade delete: borrar contact borra sus mensajes.
- [ ] Test transiciones de estado (\`mark_sent\` actualiza contact también).
- [ ] Test \`list_pending_followups\` con datos seeded variando antigüedades.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:outreach,component:db,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S02 — Templates de mensajes versionados
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S02] Templates de mensajes versionados" \
    "## 🎯 Contexto Arquitectónico
Los 4 templates del Documento C como prompts versionados en repo. Ajustar tono o estructura es diffable en PRs y cada mensaje persiste qué versión lo generó. Habilita A/B testing entre versiones.

## 📐 Alcance Técnico

### Estructura de archivos
- \`prompts/outreach/v1/\`:
  - \`A_inhouse.md\` — reclutador in-house en empresa target.
  - \`B_boutique.md\` — reclutador de agencia boutique.
  - \`C_senior.md\` — outreach senior-to-senior (CTO, VP Eng).
  - \`D_followup.md\` — follow-up a un mensaje anterior sin respuesta.
- \`prompts/outreach/forbidden_phrases.txt\` — lista versionada (mismo concepto que cover letters E6).

### Estructura de cada template
\`\`\`markdown
## SYSTEM
Eres un asistente que ayuda a Abner a redactar mensajes profesionales…

## USER_TEMPLATE
Genera un mensaje de outreach tipo {template_type} para:
CONTACT: {contact_name} ({contact_role}) en {contact_company}
RESEARCH_NOTES: {research_notes}
CANDIDATE_PROFILE: {candidate_profile_yaml}
TARGET_TONE: directo, no genérico, 4-6 frases máximo

## REQUIREMENTS
- Idioma: {target_language} (en|es)
- Longitud: 80-150 palabras
- Frases prohibidas: ver forbidden_phrases.txt
- DEBE incluir referencia específica de research_notes
\`\`\`

### Loader
- \`src/jobhunter/outreach/templates.py\` con \`load_template(template_type, version='latest') -> OutreachTemplate\`.
- \`OutreachTemplate\` (Pydantic): \`template_type\`, \`version\`, \`system_prompt\`, \`user_template\`, \`requirements\`.
- \`'latest'\` resuelve a versión semánticamente mayor.

## 🧪 Criterios de Aceptación
- [ ] 4 templates iniciales basados en Documento C §3.
- [ ] \`forbidden_phrases.txt\` con frases comunes a evitar.
- [ ] Test: cargar cada template, render con context dummy.
- [ ] Test: \`'latest'\` resuelve correctamente.

## 🔗 Dependencias
- Bloqueante: E09-S01.
- Paralelizable con: E09-S03.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:outreach,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S03 — Generador IA de mensajes (Sonnet)
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S03] Generador IA de mensajes (Sonnet)" \
    "## 🎯 Contexto Arquitectónico
Genera borradores específicos al contacto y contexto. Sonnet (no Opus) — calidad suficiente para mensajes de 80-150 palabras, mejor costo (~\$0.015/mensaje). \`research_notes\` es la salsa secreta: sin esto, el mensaje será genérico.

## 📐 Alcance Técnico

### Función principal
- \`src/jobhunter/outreach/generator.py\` con \`async generate_message(contact, template_type, research_notes, llm_client) -> MessageGenerationResult\`.
- Modelo: \`claude-sonnet-4-6\` (configurable vía \`Settings.outreach_model\`).

### \`MessageGenerationResult\` (Pydantic)
\`body: str\`, \`subject: str | None\`, \`template_version: str\`, \`model: str\`, \`cost_usd: float\`, \`word_count: int\`.

### Contexto inyectado
- Datos del contacto (\`name\`, \`role\`, \`company\`, \`market\`, \`notes\`).
- \`research_notes\` aportadas por el usuario.
- Candidate profile YAML (mismo del Documento A).
- Si \`template_type='D_followup'\`, también el \`parent_message.body\` para contexto.

### Validaciones post-LLM
- 80-150 palabras (mensajes de outreach efectivos son cortos).
- No contiene frases prohibidas.
- Incluye referencia textual a \`research_notes\` (verificación heurística: substring match).
- Si validation falla → un retry con prompt reforzado, después raise \`OutreachGenerationError\`.

### Validación previa
- Rechaza si \`research_notes\` está vacío o <20 chars.

### Persistencia
- Resultado se persiste como \`OutreachMessage\` con \`status='draft'\`.
- Costo registrado en \`llm_calls\` con \`purpose='outreach_message'\`.

## ⚠️ Acción previa
Iterar el prompt v1 contra 3 contactos imaginarios y verificar tono. ~30 min de prompt design ahorra horas de re-edición posterior.

## 🧪 Criterios de Aceptación
- [ ] Test con LLM mockeado: generación exitosa.
- [ ] Test: validation falla → retry exitoso.
- [ ] Test: validation falla 2 veces → \`OutreachGenerationError\`.
- [ ] Test: \`research_notes\` muy corto → raise antes de llamar API.
- [ ] Test: 3 fixtures reales capturados para regression tests.

## 🔗 Dependencias
- Bloqueante: Épica E04 cerrada (LLM client + budget).
- Paralelizable con: E09-S02.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:outreach,component:llm,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S04 — LinkedIn CSV importer + contact scoring
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S04] LinkedIn CSV importer + contact scoring" \
    "## 🎯 Contexto Arquitectónico
Importa contactos desde LinkedIn export con scoring automático de relevancia. De un batch de 500 conexiones, identifica las 30 que vale la pena contactar primero.

## 📐 Alcance Técnico

### CLI command
\`jobhunter outreach import --from PATH\`
- Acepta CSV de LinkedIn export (formato: First Name, Last Name, URL, Email, Company, Position, Connected On).
- Acepta CSV genérico con mapping flag \`--mapping FILE\`.
- Detecta duplicados por LinkedIn URL (de E2-S07 \`find_by_linkedin_url\`).
- Output: tabla con \`imported\`, \`skipped (duplicate)\`, \`failed (validation)\`.

### Scoring heurístico (\`quality_score: int [1-5]\`)
- +2 si position contiene \"Tech Recruiter\", \"Talent Acquisition\", \"Engineering Recruiter\".
- +2 si position contiene \"CTO\", \"VP Engineering\", \"Head of Engineering\".
- +1 si company es de las \"AI-friendly DACH\" (lista del Documento C §2.2 hardcoded en \`outreach/dach_companies.py\`).
- +1 si specialty_stack matches CV stack primario.
- Cap a 5.

### Inferencia automática
- \`market\` inferido de company location (best effort: \"GmbH\"→DE, \"Ltd\"→UK, etc.).
- \`specialty_stack\` inferido de position keywords.

### Modo \`--enrich-with-ai\` (opcional, costo asumido)
Para cada contacto, invoca Haiku con prompt corto que evalúa relevancia leyendo position+company. Útil cuando la heurística no es suficiente. Costo ~\$0.001/contacto.

### Helper \`outreach/linkedin_csv.py\`
- Parser robusto a variaciones de formato (LinkedIn cambia columnas).
- Validation: filas sin URL ni nombre se descartan con log.

## 📝 Limitación de scope
LinkedIn export está limitado a tus conexiones, no busca en LinkedIn público. Para contactar reclutadores que NO son conexiones, el flujo es manual: LinkedIn search → copy info → \`jobhunter outreach add\`.

## 🧪 Criterios de Aceptación
- [ ] Test con CSV fixture: 10 filas → scoring esperado.
- [ ] Test deduplicación por URL.
- [ ] Test \`--enrich-with-ai\` opcional con LLM mockeado.
- [ ] Test con CSV malformado (filas sin URL).

## 🔗 Dependencias
- Bloqueante: E2-S07 (\`OutreachRepo\`).
- Paralelizable con: E09-S03.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:outreach,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S05 — Cadencia y follow-ups automatizados
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S05] Cadencia y follow-ups automatizados" \
    "## 🎯 Contexto Arquitectónico
Detección automática de mensajes que necesitan follow-up y mensajes ghosted. El sistema empuja a actuar en la ventana correcta (7-10 días) sin spam. **Política estricta: máximo 2 toques por contacto** (Doc C §3.4 — \"Nunca tres mensajes sin respuesta\").

## 📐 Alcance Técnico

### Comando CLI
\`jobhunter outreach check-cadence\`:
- Identifica mensajes \`status='sent'\` con \`sent_at\` entre 7-10 días atrás → marca contacto como \"due for followup\" en notificación.
- Identifica mensajes \`status='sent'\` con \`sent_at\` > 21 días → automáticamente marca \`status='ghosted'\`, transiciona contact a \`ghosted\`.
- Refresh de estadísticas relevantes.

### Notificación Telegram
Lista compacta cuando hay follow-ups due:
\`\`\`
💌 3 contactos esperan follow-up:
  - Sarah at N26
  - Mark at Trade Republic
  - Anna at HelloFresh
Comando: jobhunter outreach draft --contact-id X --type D_followup
\`\`\`

### Política de 2 toques (CRÍTICO)
Si contacto ya tiene 2 mensajes con \`template_type IN ('A','B','C','D_followup')\`, NO se sugiere otro follow-up. El sistema **fuerza a desistir**. Después del 2do toque, el contacto se marca \`ghosted\` o \`warm\` (decisión manual desde dashboard).

### Integración con E8
Extender el comando ya existente \`jobhunter pipeline check-followups\` (de E8-S05) para incluir cadencia de outreach. Mismo workflow diario.

### Anti-spam
Solo notificar si hay ≥1 follow-up pendiente; no enviar mensaje vacío \"0 pendientes hoy\".

## 🧪 Criterios de Aceptación
- [ ] Test: mensaje sent hace 8 días → detectado como due.
- [ ] Test: mensaje sent hace 22 días → marcado ghosted automáticamente.
- [ ] Test: contacto con 2 mensajes ya enviados → NO se sugiere 3er.
- [ ] Test anti-spam: 0 follow-ups pendientes → no se envía notificación.
- [ ] Integración con \`check-followups\` de E8 verificada.

## 🔗 Dependencias
- Bloqueante: E09-S01, Épica E05 cerrada (notifiers).

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:outreach,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S06 — CLI: jobhunter outreach (suite completa)
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S06] CLI: \`jobhunter outreach\` (suite completa)" \
    "## 🎯 Contexto Arquitectónico
Suite completa de comandos para el workflow diario de outreach: identificar candidatos → generar draft → editar → enviar manual → registrar.

## 📐 Alcance Técnico

### Comandos en subgroup \`jobhunter outreach\`

#### \`outreach add\`
Añade contacto manualmente.
- Flags: \`--name\`, \`--linkedin-url\`, \`--company\`, \`--role\`, \`--market\`, \`--notes\`.

#### \`outreach import\` (de S04)
Importa CSV de LinkedIn.

#### \`outreach candidates\`
Lista contactos prioritarios.
- Flags: \`--limit N\` (default 10), \`--market germany\`, \`--min-score 4\`.
- Output: tabla rich con name, company, role, score, status, last_contacted.
- Ordenamiento: \`quality_score DESC\`, \`last_contacted_at ASC NULLS FIRST\`.

#### \`outreach draft <contact-id>\`
Genera draft de mensaje.
- Flags: \`--type A_inhouse|B_boutique|C_senior|D_followup\` (required), \`--note TEXT\` (research_notes, required), \`--language en|es\` (default en).
- Output: tabla con datos del contacto + mensaje en bloque markdown rendering + comando para marcar enviado.
- Default: NO copia al clipboard (evita persisting accidental). Flag \`--copy\` opcional.

#### \`outreach sent <message-id>\`
Marca mensaje como enviado.
- Flag opcional \`--at TIMESTAMP\`.

#### \`outreach replied <message-id>\`
Marca como respondido.

#### \`outreach list\`
Lista mensajes con filtros.
- Flags: \`--status\`, \`--contact-id\`, \`--last N\` (días).

#### \`outreach stats\`
(De S08) — métricas.

## ⚠️ Cero auto-send
**No hay \`outreach send\`.** Decisión arquitectónica explícita: el sistema no envía. Razones:
1. LinkedIn TOS prohíbe automation no autorizada.
2. Riesgo de ban permanente con una sola cuenta.
3. \"Mark as Sent\" tras review humano garantiza filtro de calidad.

## 🧪 Criterios de Aceptación
- [ ] Tests CLI con \`typer.testing.CliRunner\` para cada comando.
- [ ] \`outreach draft\` rechaza si \`--note\` muy corto.
- [ ] Output rich formatted correctamente.
- [ ] Tests E2E: add → draft → sent → replied → list.

## 🔗 Dependencias
- Bloqueante: E09-S03, E09-S04, E09-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:outreach,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S07 — Activación en dashboard (E7 outreach page)
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S07] Activación en dashboard (E7 outreach page)" \
    "## 🎯 Contexto Arquitectónico
El botón \"Generate Message\" de la página Outreach del dashboard (E7-S05) estaba deshabilitado con tooltip \"Available in E9\". Esta story lo activa, cerrando el workflow completo en una sola UI.

## 📐 Alcance Técnico

### Activación del botón
- Página \`pages/4_💌_Outreach.py\` (de E7-S05) ahora tiene botón \"Generate Message\" funcional.
- Click abre modal con form:
  - Template type (radio: A/B/C/D_followup).
  - Research notes (textarea, required, ≥20 chars).
  - Language (radio: en/es).
  - Botón \"Generate\".

### Generación
- Spinner durante generación (~3-5s con Sonnet).
- Output renderizado:
  - Mensaje en textarea editable.
  - Botón \"Copy\" (con notificación de éxito).
  - Botón \"Mark as Sent\" (asume copy-paste manual hecho).
  - Botón \"Discard\" (status='discarded').
  - Si el usuario edita el mensaje antes de \"Mark Sent\", \`body_edited_by_user=true\` se persiste.

### Vista expandida por contacto
- Nueva columna en tabla de outreach: \"Last Message\" — link al mensaje más reciente con status badge.
- Vista expandible por contacto: timeline de todos los mensajes (drafts/sent/replied), similar a \`application_events\` timeline de E7-S03.

### Persistencia de ediciones
Las ediciones del usuario son señal valiosa para iterar el prompt. Si el usuario reescribe completamente el draft de la IA, es signal de que el prompt necesita trabajo.

## 🧪 Criterios de Aceptación
- [ ] Botón funcional, modal abre correctamente.
- [ ] Validation de research_notes (≥20 chars).
- [ ] \"Mark as Sent\" persiste con body editado (no original).
- [ ] Timeline por contacto renderiza correctamente.
- [ ] Test E2E (Playwright) del flujo completo: add contact → generate → edit → mark sent → ver en timeline.

## 🔗 Dependencias
- Bloqueante: E09-S03, E09-S06, E07-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:outreach,epic:E09" \
    "$OPT_EPIC_E09" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E09-S08 — Métricas de outreach + tests
# ---------------------------------------------------------------------------
create_issue \
    "[E09-S08] Métricas de outreach + tests end-to-end" \
    "## 🎯 Contexto Arquitectónico
Métricas de efectividad permiten iterar la estrategia con data. Tasa de respuesta como métrica central: 10-20% sano (Doc C §7); <5% indica problema de templates, perfiles target, o personalización.

## 📐 Alcance Técnico

### Comando \`jobhunter outreach stats\`
Muestra:
- Total mensajes enviados (último mes, últimas 8 semanas).
- **Tasa de respuesta global** y desagregada por:
  - \`template_type\` (A_inhouse, B_boutique, etc.).
  - \`market\` (germany, eu_wide, uk).
  - \`quality_score\` del contacto (1-2, 3-4, 5).
- Top 5 contactos warmest (status='warm' o \`replied_at\` reciente).
- Mensajes pendientes follow-up vs ghosted vs activos.
- **Tiempo medio a respuesta** (cuando hay reply).

### Sección en dashboard
Equivalente añadida al dashboard de E7-S06 (Metrics page).

### Tests integración end-to-end
- [ ] Importar 5 contactos → generar 3 mensajes → marcar 2 sent + 1 replied → verificar stats coherentes.
- [ ] Cadencia: mensaje sent hace 8 días → check-cadence detecta como \"due followup\".
- [ ] Cadencia: mensaje sent hace 22 días → check-cadence marca como ghosted.

### Coverage
≥ 75% en módulo \`outreach/\`.

## 📝 Sobre A/B testing
A/B testing entre versiones de templates (ej. v1 vs v2 de A_inhouse) prepara base aquí pero el A/B real entra en E11 (Analytics). Esta story solo asegura que las queries discriminan por \`template_version\`.

## 🧪 Criterios de Aceptación
- [ ] \`outreach stats\` muestra valores coherentes con datos seeded.
- [ ] Sección dashboard renderiza correctamente.
- [ ] Tests E2E pasan en CI.
- [ ] Coverage \`outreach/\` ≥ 75%.

## 🔗 Dependencias
- Bloqueante: E09-S05, E09-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:feature,component:outreach,component:dashboard,epic:E09" \
    "$OPT_EPIC_E09" \
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
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S03: iterar prompts/outreach/v1/*.md contra"
echo "       3 contactos imaginarios hasta que el output suene en tu voz."
echo "   4. ⚠️  Política de 2 toques (S05) es ley: no la saltes."
echo "   5. ⚠️  Sistema NUNCA envía mensajes automáticamente. Solo drafts."
echo ""
