#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E10 — Response Detection (Gmail Integration)
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
OPT_EPIC_E10="2e03fdca"     # E10-Gmail

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + Gmail/OAuth specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; APIs externas (Gmail, OAuth, Telegram) mockeadas en CI.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy.
5. **Privacy first:** Emails procesados se almacenan SOLO con metadata + snippet (200 chars) + body_hash. NUNCA contenido completo.
6. **Auth scope mínimo:** OAuth scope estrictamente `gmail.readonly` + `gmail.modify` (solo labels). NO `gmail.send`, NO `gmail.compose`.
7. **No auto-changes para casos críticos:** El sistema NUNCA aplica auto-cambio de estado para `rejected` u `offer` sin confirmación humana, sin importar confidence.
8. **Idempotencia:** Re-procesar el mismo email (mismo `gmail_message_id`) NUNCA crea duplicados ni dispara dobles transiciones.
9. **Cifrado at rest:** Tokens OAuth almacenados cifrados con Fernet; clave en `Settings.oauth_encryption_key`.
10. **Pre-commit:** Todos los hooks pasan en local.
11. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
12. **Documentación:** Si la story añade un setup externo (Google Cloud project, OAuth consent), `docs/runbook.md` documenta procedimiento paso a paso.'

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

create_label_if_missing "status:ready"           "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E10"               "ea4335" "Épica E10 — Response Detection (Gmail)"
create_label_if_missing "type:feature"           "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"              "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"               "8b4789" "Comandos CLI"
create_label_if_missing "type:infra"             "1d76db" "Infraestructura, workflows, OAuth"
create_label_if_missing "component:email"        "fbbc04" "Gmail client, matcher, suggester"
create_label_if_missing "component:auth"         "ff5722" "OAuth, tokens, cifrado"
create_label_if_missing "component:db"           "d93f0b" "Migraciones, repos, persistencia"
create_label_if_missing "component:notify"       "c2e0c6" "Telegram interactividad, callbacks"
create_label_if_missing "component:llm"          "5319e7" "LLM matcher, prompts"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E10
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E10"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E10-S01 — OAuth2 Gmail setup + token storage
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S01] OAuth2 Gmail setup + token storage cifrado" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Autenticación Gmail vía OAuth2 con scope mínimo. El sistema lee inbox sin almacenar password ni requerir re-auth en cada polling. Tokens cifrados at rest con Fernet — si la DB se filtra sin la clave de cifrado, los tokens son inutilizables.

## 📐 Alcance Técnico

### Setup externo (Google Cloud Console)
1. Proyecto creado (o reutilizar existente).
2. Gmail API habilitada.
3. OAuth consent screen \"External\" pero limitado a tu Google account (Testing mode hasta 100 users sin verification).
4. OAuth Client ID tipo \"Desktop app\".

### Settings nuevas
- \`gmail_client_id: SecretStr\`.
- \`gmail_client_secret: SecretStr\`.
- \`gmail_redirect_uri: str = \"http://localhost:8765/oauth/callback\"\`.
- \`oauth_encryption_key: SecretStr\` — clave Fernet generada con \`Fernet.generate_key()\`.

### CLI: \`jobhunter email auth\`
1. Imprime URL de OAuth.
2. Abre browser automáticamente (\`webbrowser.open()\`).
3. Levanta servidor HTTP local efímero en port 8765 para callback.
4. Captura el \`code\`, intercambia por \`access_token\` + \`refresh_token\`.
5. Persiste tokens cifrados en DB.
6. Cierra servidor, imprime \"Auth successful\".

### Tabla nueva: \`oauth_tokens\`
- \`id\` UUID PK.
- \`provider\` VARCHAR (\"gmail\", futuro: \"linkedin\", etc.).
- \`account_email\` VARCHAR.
- \`access_token\` TEXT (cifrado Fernet).
- \`refresh_token\` TEXT (cifrado).
- \`expires_at\` TIMESTAMPTZ.
- \`scopes\` ARRAY[VARCHAR].
- UNIQUE \`(provider, account_email)\`.

### Helper crypto
\`src/jobhunter/crypto.py\` con \`encrypt(plaintext, key)\` / \`decrypt(ciphertext, key)\` usando \`cryptography.fernet\`.

### Comando de revocación
\`jobhunter email auth --revoke\` para revocar tokens (importante para security).

## ⚠️ Scope mínimo crítico
Estrictamente \`gmail.readonly\` + \`gmail.modify\` (solo para etiquetas). NUNCA \`gmail.send\` ni \`gmail.compose\`. Si Google revisa el OAuth consent (porque pasaste 100 usuarios), querrás defender un scope mínimo.

## 🧪 Criterios de Aceptación
- [ ] Migration \`oauth_tokens\` aplicada.
- [ ] CLI flow OAuth completo funciona (probado manual).
- [ ] Tokens cifrados verificables (campo en DB no es plaintext).
- [ ] Refresh automático cuando \`access_token\` expira.
- [ ] \`--revoke\` funciona y revoca remoto en Google.
- [ ] Runbook documenta setup paso a paso de Google Cloud.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:auth,component:db,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S02 — Tabla email_messages + repo
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S02] Tabla \`email_messages\` + repo" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Persistencia de cada email procesado con su match decision. Permite debug de false positives/negatives, métricas de detección, y idempotencia (re-procesar el mismo email no crea duplicados ni dispara doble transición de estado).

## 📐 Alcance Técnico

### Migration: \`add_email_messages_table\`
- \`id\` UUID PK.
- \`gmail_message_id\` VARCHAR UNIQUE — id de Gmail.
- \`gmail_thread_id\` VARCHAR — agrupar respuestas en threads.
- \`received_at\` TIMESTAMPTZ.
- \`from_email\` VARCHAR.
- \`from_domain\` VARCHAR — extraído (ej. \`recruiter@n26.com\` → \`n26.com\`).
- \`subject\` TEXT.
- \`snippet\` TEXT — primeros 200 chars del body (suficiente para contexto en sugerencias).
- \`body_hash\` VARCHAR(64) — sha256 del body completo (para detectar duplicados sin almacenar contenido).
- \`match_status\` VARCHAR (enum: \`unmatched\`, \`auto_matched\`, \`ai_matched\`, \`user_confirmed\`, \`user_rejected\`, \`ignored_marketing\`).
- \`matched_application_id\` UUID NULLABLE FK → \`applications(id)\`.
- \`matched_outreach_message_id\` UUID NULLABLE FK → \`outreach_messages(id)\`.
- \`match_confidence\` FLOAT (0-1).
- \`match_reasoning\` TEXT — heurística que disparó el match.
- \`suggested_status_change\` JSONB — ej. \`{\"from\": \"applied\", \"to\": \"screening\"}\`.
- \`processed_at\` TIMESTAMPTZ.

### Constraint
Solo uno de \`matched_application_id\` o \`matched_outreach_message_id\` puede ser NOT NULL (CHECK constraint en SQL).

### Índices
- \`(from_domain)\`.
- \`(match_status)\`.
- \`(received_at DESC)\`.

### \`EmailMessageRepo\`
- \`record(gmail_msg, ...) -> EmailMessage\`.
- \`find_by_gmail_id(id) -> EmailMessage | None\` (idempotencia).
- \`list_unmatched(limit) -> list[EmailMessage]\`.
- \`update_match(message_id, app_id|outreach_id, confidence, reasoning, suggestion)\`.
- \`mark_user_confirmed(message_id) / mark_user_rejected(message_id)\`.

## 📝 Decisión: privacidad first
\`body_hash\`, NO \`body\` completo. Razones:
1. Reducir blast radius si DB se compromete.
2. GDPR-compliant by design.
3. Snippet (200 chars) + hash es suficiente para >90% de casos.

Excepción controlada: si matcher escala a IA con más contexto, se hace fetch fresh from Gmail API (audit en Google), no se cachea local.

## 🧪 Criterios de Aceptación
- [ ] Migration up/down ejecuta limpiamente.
- [ ] CHECK constraint verificado: insertar con AMBOS FKs falla.
- [ ] Test idempotencia: insertar mismo \`gmail_message_id\` 2x raise unique violation.
- [ ] Tests CRUD del repo.

## 🔗 Dependencias
- Bloqueante: E10-S01.
- Paralelizable con: E10-S03.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:email,component:db,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S03 — Gmail API client wrapper
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S03] Gmail API client wrapper" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Wrapper sobre Gmail API con manejo de tokens, refresh automático, y rate limit. Servicios downstream (matcher, suggester) lo usan sin pensar en OAuth plumbing.

## 📐 Alcance Técnico

### Clase \`GmailClient\`
- \`src/jobhunter/email/gmail_client.py\`.
- Constructor recibe \`OAuthTokenRepo\`; carga tokens desde DB y los descifra.

### Métodos
- \`async list_messages(query: str, max_results: int = 50) -> list[GmailMessage]\` — usa Gmail search syntax (ej. \`\"newer_than:1d\"\`, \`\"from:no-reply\"\`, \`\"newer_than:1h -from:me\"\`).
- \`async get_message(message_id: str) -> GmailMessageDetail\` — incluye body parseado (HTML+text).
- \`async add_label(message_id: str, label_name: str)\` — crea label si no existe.
- \`async remove_label(message_id: str, label_name: str)\`.
- \`async list_labels() -> list[Label]\`.

### Refresh automático
Detectar 401 → refresh \`access_token\` con \`refresh_token\` → retry una vez.

### Rate limit
Respetar quota Gmail (~250 quota units/sec; un \`get_message\` cuesta 5 units). Conservador: 1 req/200ms con \`asyncio.Semaphore\`.

### Pydantic models
- \`GmailMessage\`: \`id\`, \`thread_id\`, \`received_at\`, \`from_email\`, \`to_email\`, \`subject\`, \`snippet\`, \`labels\`.
- \`GmailMessageDetail\` extiende con \`body_text\`, \`body_html\`.

### Helper crítico
\`_parse_message(raw)\` — extrae body de payload multipart de Gmail. **Body de Gmail es nightmare-encoded** (multipart, base64, charset variable, HTML+text alternativas). Dedicar tiempo a este helper.

## 🧪 Criterios de Aceptación
- [ ] Tests con \`google-api-python-client\` mockeado.
- [ ] Test refresh: 401 → refresh → retry exitoso.
- [ ] Test parser de body multipart con fixture real (sanitizada).
- [ ] Rate limit verificable (test mide tiempo entre requests).

## 🔗 Dependencias
- Bloqueante: E10-S01.
- Paralelizable con: E10-S02.
- Nuevas deps: \`google-api-python-client\`, \`google-auth\`, \`google-auth-oauthlib\`, \`google-auth-httplib2\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:email,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S04 — Email matcher (heurística + IA)
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S04] Email matcher (heurística + IA)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Servicio que recibe un email y propone match contra \`application\` o \`outreach_message\`. Estrategia escalonada: heurística primero (gratis, ~70% precision), IA solo si ambiguo. Ahorra ~70% de las llamadas LLM.

## 📐 Alcance Técnico

### Función principal
\`src/jobhunter/email/matcher.py\` con \`async match_email(email, session, llm_client) -> MatchResult\`.

### Estrategia escalonada
1. **Heurística 1 — Domain match:** extrae \`from_domain\`, busca \`applications\` con \`Job.company\` similar al dominio o \`contact_email\` con mismo dominio en \`outreach_contacts\`. Match único → confidence 0.9.
2. **Heurística 2 — Subject keyword match:** subject contiene \"re: [job title]\", \"your application\", \"interview\", \"next steps\" + match heurística 1 → confidence 0.95.
3. **Heurística 3 — Marketing detector:** \`from\` contiene \"noreply\", \"no-reply\", \"newsletter\", o \`unsubscribe\` en body → marcar como \`ignored_marketing\`. NO procesar.
4. **Escalación a IA (si confidence <0.8):** invocar Haiku con prompt corto que recibe \`(subject + snippet, candidate jobs/contacts list)\` y devuelve match + sugerencia de status change.

### \`MatchResult\` (Pydantic)
\`match_status\`, \`application_id | None\`, \`outreach_message_id | None\`, \`confidence\`, \`reasoning\`, \`suggested_change: dict | None\`.

### Inferencia de \`suggested_change\`
Heurística sobre keywords:
- \"interview\" / \"schedule a call\" → \`applied → screening\` o \`screening → interview_1\`.
- \"rejected\" / \"moved forward with\" / \"regret to inform\" → \`* → rejected\`.
- \"offer\" / \"compensation package\" → \`* → offer\`.
- Outreach: respuesta directa → \`outreach_message.status = replied\`.

### Marketing detector crítico
Un solo email de marketing de N26 (donde aplicaste) confundido con respuesta destruiría el tracker. Lista de \"marketing markers\" hardcoded + lista learnable de senders frecuentes (ver story S08 para learning).

### Persistencia
Resultado se persiste en \`email_messages\` table.

## 🧪 Criterios de Aceptación
- [ ] Test 5 casos: interview invite, rejection, marketing email, ambiguous outreach reply, unknown email.
- [ ] Test escalación a IA: heurística confidence 0.6 → IA llamada.
- [ ] Test marketing: email con \`unsubscribe\` → \`ignored_marketing\`, sin llamada IA.
- [ ] Coverage del módulo ≥ 80%.

## 🔗 Dependencias
- Bloqueante: E10-S02, E10-S03.

## ⏱️ Estimación
3h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:email,component:llm,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S05 — Sugeridor de cambios de estado
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S05] Sugeridor de cambios de estado" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Toma resultados del matcher y produce sugerencias accionables. Threshold dinámico según confidence — política conservadora: \"auto-apply\" SOLO para transiciones positivas (applied→screening, screening→interview), NUNCA para rejected u offer (siempre confirmación humana, sin importar confidence).

## 📐 Alcance Técnico

### Función principal
\`src/jobhunter/email/suggester.py\` con \`async suggest_state_changes(session) -> list[StateSuggestion]\`.
Procesa emails recientes con \`match_status='auto_matched' | 'ai_matched'\` y \`confidence >= 0.7\`.

### \`StateSuggestion\` (Pydantic)
\`email_id\`, \`application_id | outreach_message_id\`, \`current_state\`, \`suggested_state\`, \`confidence\`, \`email_snippet\`, \`reasoning\`.

### Threshold dinámico
- \`confidence ≥ 0.9\` y heurística clara y transición positiva → notificación informativa \"auto-applied\" (no requiere confirmación, pero log auditable).
- \`confidence 0.7-0.9\` → notificación con botones de confirmación.
- \`confidence < 0.7\` → silent, deja como \`unmatched\` para review manual en dashboard.

### Política conservadora
**SIEMPRE requiere confirmación humana, sin importar confidence:**
- Transición a \`rejected\`.
- Transición a \`offer\`.

Razones:
- Error en \`rejected\`: pierde una oportunidad real (no recuperas un proceso marcado rechazado por error).
- Error en \`offer\`: false-celebration, decepción posterior.

### Persistencia
Sugerencias en \`email_messages.suggested_status_change\`.

## 🧪 Criterios de Aceptación
- [ ] Test 3 paths threshold: auto-apply, requires-confirm, silent.
- [ ] Test política: \`rejected\` con confidence 0.95 → requires-confirm (no auto).
- [ ] Test \`offer\` siempre confirma.
- [ ] Helper \`_requires_confirmation(suggestion) -> bool\` testeado aisladamente.

## 🔗 Dependencias
- Bloqueante: E10-S04.
- Paralelizable con: E10-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:email,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S06 — Telegram bot inline buttons
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S06] Telegram bot inline buttons (interactividad)" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Notificaciones de sugerencias con botones inline (Aprobar/Rechazar/Más contexto). Confirmar cambios = un tap, sin abrir dashboard. Decisión: polling > webhook (webhook requiere servidor público con HTTPS; el workflow \`email-poll\` ya corre cada 30 min y procesa callbacks pendientes).

## 📐 Alcance Técnico

### Extender \`TelegramNotifier\` (de E5-S03)
- Nuevo método \`async send_with_buttons(message, buttons: list[Button]) -> str\` (devuelve \`message_id\` para tracking).

### Formato del mensaje
\`\`\`
📧 Posible respuesta detectada

Email de: sarah@n26.com
\"Hi Abner, we'd love to schedule a 30-min...\"

Sugerencia: Job#1234 (N26 Senior Python)
applied → screening
Confidence: 87%

[✅ Aprobar]  [❌ Rechazar]  [📄 Más contexto]
\`\`\`

### Botones inline
Telegram \`InlineKeyboardMarkup\` con \`callback_data\`: \`approve:{suggestion_id}\`, \`reject:{suggestion_id}\`, \`context:{suggestion_id}\`.

### Procesamiento de callbacks (modo polling)
- \`process_callback_updates(updates)\` que procesa callbacks pendientes via \`Bot.get_updates()\`.
- Comando \`jobhunter telegram process-callbacks\` standalone.
- Integración: workflow \`email-poll\` (S07) tras enviar sugerencias también consume callbacks.

### Acciones por callback
- \`approve\`: ejecuta el cambio de estado, persiste \`match_status='user_confirmed'\`, edita el mensaje Telegram a \"✅ Aplicado: applied → screening\".
- \`reject\`: marca \`match_status='user_rejected'\`, edita mensaje a \"❌ Rechazado\".
- \`context\`: envía mensaje secundario con detalle expandido (snippet expandido, link a dashboard).

### Idempotencia
Un callback procesado dos veces NO aplica el cambio dos veces (verifica \`match_status\` antes de actuar).

## 📝 Decisión: polling sobre webhook
Webhook requiere servidor público con HTTPS. Polling es viable: el workflow \`email-poll\` corre cada 30 min y consume callbacks. Latencia hasta 30 min para procesar respuesta humana — aceptable.

## 🧪 Criterios de Aceptación
- [ ] Test: \`send_with_buttons\` envía mensaje con botones correctos.
- [ ] Test idempotencia: \`approve\` callback procesado dos veces solo aplica una.
- [ ] Test edición de mensaje original tras callback.
- [ ] Test manual: simular callback approve → estado cambia + mensaje editado.

## 🔗 Dependencias
- Bloqueante: Épica E05 cerrada, E10-S05.
- Paralelizable con: E10-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,component:email,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S07 — Workflow email-poll cada 30 min
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S07] Workflow \`email-poll\` cada 30 min" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Workflow que dispara polling Gmail + matching + sugerencias cada 30 min. Las respuestas se detectan en near-real-time sin intervención manual.

## 📐 Alcance Técnico

### \`.github/workflows/email-poll.yml\`
- Schedule cron: \`'*/30 * * * *'\` (cada 30 min).
- Trigger manual.
- Steps:
  1. Checkout, setup uv, sync.
  2. Composite action \`setup-env\` (de E8-S01) extendida con env vars Gmail.
  3. \`uv run jobhunter email poll-and-suggest\`.
- Timeout: 5 min.
- Concurrency: \`email-poll\`, \`cancel-in-progress: false\`.

### Comando CLI: \`jobhunter email poll-and-suggest\`
1. Llama \`GmailClient.list_messages(query=\"newer_than:1h -from:me\")\`.
2. Para cada email no procesado (verificar \`email_messages.gmail_message_id\`):
   - Procesa con \`EmailMatcher\`.
   - Si match con confidence suficiente, ejecuta \`suggester\` y envía Telegram con botones (S06).
3. Procesa callbacks Telegram pendientes.

### Anti-spam
Si \"tormenta\" de emails (>5 sugerencias en 1 hora), agrupar en una sola notificación con summary.

### Alertas en caso de fallo
Composite action \`alert-on-failure\` (de E8-S06).

### Logs estructurados upload
Consistente con E8-S07 (LOG_FORMAT=json + artifacts).

## ⚠️ Costo de runner
- 48 corridas/día × ~1 min = ~1500 min/mes.
- Sumado a workflows E8 (~900 min/mes), total ~2400 min/mes vs free tier 2000 min/mes.
- **Posible overflow.** Mitigaciones:
  - Reducir a cada 60 min (24/día → 720 min/mes).
  - Aceptar billing GH Actions: \$0.008/min después de free tier ≈ \$3/mes peor caso.

## 🧪 Criterios de Aceptación
- [ ] Workflow YAML válido.
- [ ] Manual trigger ejecuta exitosamente.
- [ ] Primer cron-triggered run sea exitoso.
- [ ] Alertas \`alert-on-failure\` integradas.
- [ ] Logs upload como artifact.

## 🔗 Dependencias
- Bloqueante: E10-S05, E10-S06, Épica E08 cerrada.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:email,epic:E10" \
    "$OPT_EPIC_E10" \
    "$OPT_PRIORITY_P2"

# ---------------------------------------------------------------------------
# E10-S08 — Métricas de detección + tests end-to-end
# ---------------------------------------------------------------------------
create_issue \
    "[E10-S08] Métricas de detección + tests end-to-end" \
    "${WARNING_TEXT}

## 🎯 Contexto Arquitectónico
Métricas de precision/recall del matcher permiten iterar las heurísticas. Precision is gold here — si <85%, el usuario aprende a desconfiar del sistema y deja de aprobar/rechazar, perdiendo todo el valor.

## 📐 Alcance Técnico

### Comando \`jobhunter email stats\`
Muestra:
- Total emails procesados (último mes).
- **Tasa de match:** % auto-matched, % ai-matched, % unmatched.
- **Precision (estimada):** % de auto-matched que el usuario confirmó (vs rechazó). **Target ≥85%.**
- **Recall (estimada):** % de aplicaciones con cambio de estado manual reciente vs vía email (proxy de \"missed responses\").
- **Costo IA:** total mes de calls de matcher con escalación.
- **Top dominios** generadores de emails (para identificar marketing senders no detectados — actualizar lista hardcoded).

### Sección dashboard
Equivalente añadida al dashboard E7 Metrics page.

### Tests integración end-to-end
- [ ] Email con interview invite → matcher detecta → suggester crea sugerencia → Telegram envía con botones → simular \"approve\" callback → verificar \`Application.status='screening'\`.
- [ ] Email de marketing → matcher marca \`ignored_marketing\` → NO sugerencia.
- [ ] Email ambiguo → matcher escala a IA → sugiere con confidence 0.75 → requiere confirmación humana.
- [ ] Idempotencia: re-procesar mismo email no crea duplicados.

### Coverage
\`email/\` ≥ 80%.

## 📝 Sobre recall
Imposible de medir 100%. No podemos saber qué emails NO detectó como respuesta válida. Proxy: si una \`Application\` cambia de estado manualmente desde dashboard sin email asociado, posiblemente fue una respuesta missed — flag para revisión.

## 🧪 Criterios de Aceptación
- [ ] \`email stats\` muestra valores coherentes con datos seeded.
- [ ] Sección dashboard renderiza.
- [ ] Tests E2E pasan en CI.
- [ ] Coverage \`email/\` ≥ 80%.

## 🔗 Dependencias
- Bloqueante: E10-S07.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:feature,component:email,component:dashboard,epic:E10" \
    "$OPT_EPIC_E10" \
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
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S01: crear proyecto en Google Cloud Console,"
echo "       habilitar Gmail API, generar OAuth Client ID (Desktop type)."
echo "   4. ⚠️  Política CRÍTICA: rejected/offer SIEMPRE requieren confirmación humana,"
echo "       sin importar confidence. NO la saltes."
echo "   5. ⚠️  Privacy first: NUNCA almacenar contenido completo de emails."
echo "       Solo metadata + snippet (200 chars) + body_hash."
echo ""
