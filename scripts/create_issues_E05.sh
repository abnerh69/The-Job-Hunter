#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E5 — Real-time Notification System
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
OPT_EPIC_E05="737d01f6"     # E5-Notifications

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + notification specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy describiendo propósito, args, returns, raises.
5. **Idempotencia (si aplica):** Toda función que envíe una notificación verifica `notifications_sent` antes; re-correr el dispatcher 2 veces NO genera duplicados.
6. **Failure resilience:** Errores de canal (Telegram/SMTP caídos) se manejan, persisten como `success=false`, y NO propagan exceptions hacia el orquestador.
7. **Pre-commit:** Todos los hooks pasan en local.
8. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
9. **Documentación:** Si la story añade un canal nuevo o requiere setup externo (ej. token Telegram, App Password Gmail), `docs/runbook.md` documenta el procedimiento paso a paso.'

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
create_label_if_missing "epic:E05"               "f9d71c" "Épica E05 — Real-time Notification System"
create_label_if_missing "type:feature"           "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"              "fbca04" "Tests, fixtures"
create_label_if_missing "type:cli"               "8b4789" "Comandos CLI"
create_label_if_missing "component:notify"       "c2e0c6" "Notificadores, despachador, digest"
create_label_if_missing "component:templates"    "d4c5f9" "Templates Jinja2"
create_label_if_missing "component:db"           "d93f0b" "Migraciones, repos, persistencia"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E05
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E05"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E05-S01 — BaseNotifier ABC + tabla notifications_sent
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S01] \`BaseNotifier\` ABC + tabla \`notifications_sent\`" \
    "## 🎯 Contexto Arquitectónico
Plugin pattern para canales de notificación (mismo espíritu que \`BaseSource\` en E3). La tabla \`notifications_sent\` con UNIQUE constraint garantiza idempotencia a nivel DB — incluso si dos workers llaman \`send()\` simultáneamente, solo uno persiste y el sistema nunca envía duplicados.

## 📐 Alcance Técnico

### ABC + Registry
- \`src/jobhunter/notify/base.py\` con \`BaseNotifier(ABC)\`:
  - \`name: str\` (identificador único).
  - \`is_enabled() -> bool\` (lee de \`Settings\`).
  - \`async send(message: NotificationMessage) -> NotificationResult\`.
- Decorator \`@register_notifier\`.

### Pydantic models
- \`NotificationMessage\`: \`channel\`, \`subject: str | None\`, \`body_text\`, \`body_html: str | None\`, \`metadata: dict\`.
- \`NotificationResult\`: \`success: bool\`, \`provider_message_id: str | None\`, \`error: str | None\`, \`duration_ms: int\`.

### Tabla nueva: \`notifications_sent\`
- Migration Alembic.
- Columnas: \`id\` UUID PK, \`channel\` VARCHAR, \`dedup_key\` VARCHAR, \`job_id\` UUID nullable FK, \`sent_at\` TIMESTAMPTZ, \`provider_message_id\` TEXT, \`success\` BOOL, \`error\` TEXT.
- Constraint UNIQUE en \`(channel, dedup_key)\`.
- Índice en \`(job_id, channel)\`.

### Repo
- \`src/jobhunter/db/repos/notifications.py\` con \`NotificationsRepo\`:
  - \`was_sent(channel, dedup_key) -> bool\`.
  - \`record_sent(channel, dedup_key, job_id, result)\`.
  - \`failures_in_last(hours) -> int\` (para alerting futuro).

## 📝 Decisión clave
\`dedup_key\` por canal, no global. Permite múltiples notificaciones distintas para el mismo job:
- \`tier_a:{job_id}\` — alerta inicial.
- \`interview_reminder:{job_id}\` — futuro recordatorio.
- \`digest:{year}:{week}\` — digest semanal.

## 🧪 Criterios de Aceptación
- [ ] Migration aplicada; UNIQUE constraint verificado en psql.
- [ ] Test: \`record_sent\` dos veces con mismo \`(channel, dedup_key)\` → segunda raise (o devuelve ya-existente, decisión de diseño).
- [ ] Test: \`was_sent\` retorna \`True\` solo tras \`record_sent\` exitoso.
- [ ] Registry con 2 notifiers dummy funciona.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S02 — Templates Jinja2 para mensajes
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S02] Templates Jinja2 para mensajes" \
    "## 🎯 Contexto Arquitectónico
Templates versionados en repo, no hardcoded en código Python. Cambios diffables en PRs, render bonito en GitHub. Misma justificación que prompts versionados de E4.

## 📐 Alcance Técnico

### Templates iniciales en \`templates/notifications/\`
- \`tier_a_match_telegram.md\` — Telegram (MarkdownV2): título, empresa, score, salario estimado, link, top 3 match points.
- \`tier_a_match_email.html\` — versión HTML (opcional, para si en el futuro se notifica también por email).
- \`weekly_digest_email.html\` — resumen semanal con: matches A nuevos, B pendientes, follow-ups vencidos, métricas top.
- \`weekly_digest_email.txt\` — versión texto plano para multipart fallback.

### Renderizador
- \`src/jobhunter/notify/templates.py\` con \`render(template_name, context) -> str\`.
- Jinja2 environment configurado: \`autoescape=select_autoescape(['html'])\`, \`trim_blocks=True\`, \`lstrip_blocks=True\`.
- Caching del environment (no re-crear en cada call).

### Filtros custom útiles
- \`format_currency(amount, currency)\` — \"\$5,500/mes\".
- \`format_date_human(dt)\` — \"hace 2 días\".
- \`truncate_words(text, n)\` — para descripciones largas.
- \`escape_telegram_markdown(text)\` — escape de caracteres MarkdownV2 (\`_\`, \`*\`, \`[\`, etc.).

## 🧪 Criterios de Aceptación
- [ ] 4 templates iniciales creados.
- [ ] \`render()\` funciona con contexto dummy.
- [ ] Filtros custom probados unitariamente.
- [ ] Test específico: render \`tier_a_match_telegram.md\` con caracteres especiales (puntos, guiones) → output válido para MarkdownV2.

## 🔗 Dependencias
- Bloqueante: E05-S01.
- Paralelizable con: E05-S03, E05-S04.
- Nuevas deps: \`jinja2\` (probablemente ya transitiva).

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:templates,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S03 — TelegramNotifier implementación
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S03] \`TelegramNotifier\` implementación" \
    "## 🎯 Contexto Arquitectónico
Canal de notificación principal. Latencia objetivo <2 min entre que un job es scoreado tier-A y la alerta llega al teléfono. MarkdownV2 de Telegram es estricto — caracteres especiales requieren escape, lo cual es la trampa más común.

## 📐 Alcance Técnico
- \`src/jobhunter/notify/telegram.py\` con clase \`TelegramNotifier(BaseNotifier)\`.
- Usa \`python-telegram-bot\` async: \`Bot(token).send_message(chat_id, text, parse_mode='MarkdownV2')\`.
- Lee credenciales de \`Settings.telegram_bot_token\` y \`Settings.telegram_chat_id\`.
- \`is_enabled()\` devuelve \`False\` si token o chat_id vacíos (deshabilita limpiamente sin errores).
- Manejo de errores específico:
  - \`RetryAfter\` (rate limit) → respeta header \`retry_after\`, reintenta una vez.
  - \`BadRequest\` (mensaje malformado, chat_id inválido) → log + return \`success=false\`, NO raise.
  - \`NetworkError\` → return failure, no raise.
- Helper \`escape_telegram_markdown_v2(text)\` que escapa: \`_ * [ ] ( ) ~ \` > # + - = | { } . !\`.
- Trunca mensaje a 4096 chars (limit Telegram); si excede, agrega \"…\" al final.

## ⚠️ Setup externo (procedural, fuera de código)
1. \`@BotFather\` en Telegram → \`/newbot\` → guardar token.
2. Iniciar conversación con tu bot, enviar \`/start\`.
3. Visitar \`https://api.telegram.org/bot<TOKEN>/getUpdates\` → extraer \`chat.id\`.
4. Poner ambos en \`.env\`.

Documentar en \`docs/runbook.md\` sección \"Configurar Telegram bot\".

## 🧪 Criterios de Aceptación
- [ ] Test con \`python-telegram-bot\` mockeado: send exitoso → \`success=true\`.
- [ ] Test: \`RetryAfter\` → reintenta una vez exitosamente.
- [ ] Test: \`BadRequest\` → \`success=false\`, NO raise.
- [ ] Test: \`is_enabled()\` con creds vacías → \`False\`.
- [ ] Test del escape: \`escape_telegram_markdown_v2(\"Salary: \$5,500. Apply!\")\` produce string válido para MarkdownV2.
- [ ] Test manual: \`jobhunter notify test --channel telegram --message \"Hello from setup\"\` llega al chat real.

## 🔗 Dependencias
- Bloqueante: E05-S01.
- Paralelizable con: E05-S02, E05-S04.
- Nuevas deps: \`python-telegram-bot[asyncio]\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S04 — EmailNotifier (SMTP) implementación
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S04] \`EmailNotifier\` (SMTP) implementación" \
    "## 🎯 Contexto Arquitectónico
Canal secundario para el digest semanal. Gmail SMTP es suficiente para volumen actual (~1 digest/semana + ocasionales). Si en el futuro deliverability se vuelve problema, migrar a SendGrid/Resend es trivial (mismo \`BaseNotifier\` interface).

## 📐 Alcance Técnico
- \`src/jobhunter/notify/email.py\` con clase \`EmailNotifier(BaseNotifier)\`.
- Usa \`aiosmtplib\` para envío async (no bloquea event loop).
- Soporta multipart MIME (text + HTML); fallback a text si cliente no renderiza HTML.
- Lee de \`Settings\`: \`smtp_host\`, \`smtp_port\`, \`smtp_user\`, \`smtp_password\`, \`digest_to_email\`.
- \`is_enabled() = False\` si credenciales vacías.
- Manejo de errores: \`SMTPException\`, \`SMTPAuthenticationError\` → log + \`success=false\`, no raise.
- Connection pooling no necesario (envío esporádico).

## ⚠️ Setup externo
Si usas Gmail con 2FA habilitado (deberías), requiere **App Password**:
1. https://myaccount.google.com/apppasswords
2. Generar app password para \"Job-Hunter-EU\".
3. Usar ese password en \`SMTP_PASSWORD\`, no el de la cuenta.

Documentar en \`docs/runbook.md\` sección \"Configurar Gmail SMTP\".

## 🧪 Criterios de Aceptación
- [ ] Test con \`aiosmtplib\` mockeado: send multipart → \`success=true\`.
- [ ] Test: \`SMTPAuthenticationError\` → \`success=false\`, NO raise.
- [ ] Test: \`is_enabled()\` con creds vacías → \`False\`.
- [ ] Test multipart: contenido HTML y text presentes en mensaje generado.
- [ ] Test manual: \`jobhunter notify test --channel email --subject \"Test\" --message \"Hello\"\` llega al inbox.

## 🔗 Dependencias
- Bloqueante: E05-S01.
- Paralelizable con: E05-S02, E05-S03.
- Nuevas deps: \`aiosmtplib\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S05 — Despachador de notificaciones tier-A
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S05] Despachador de notificaciones tier-A" \
    "## 🎯 Contexto Arquitectónico
El despachador es lo que el cron de E8 invocará tras cada batch de scoring. Toma jobs tier-A no notificados, renderiza el template, envía vía Telegram, persiste el resultado. Idempotencia garantizada por la tabla \`notifications_sent\` (de S01).

## 📐 Alcance Técnico
- \`src/jobhunter/notify/dispatcher.py\` con \`async dispatch_tier_a_notifications(session) -> DispatchReport\`.
- Query: jobs \`tier='A'\` que NO están en \`notifications_sent\` con \`(channel='telegram', dedup_key='tier_a:{job_id}')\`.
- Por cada job:
  1. Renderizar template \`tier_a_match_telegram.md\` con \`job\` + \`job.score_data\`.
  2. Llamar \`TelegramNotifier.send(message)\`.
  3. Persistir en \`notifications_sent\` con resultado (incluso si falló).
- Si \`TelegramNotifier.is_enabled() == False\`, log warning y return early sin error.

### \`DispatchReport\` (Pydantic)
- \`total_pending\`, \`success_count\`, \`failure_count\`, \`errors: list[str]\`, \`duration_ms\`.

## 📝 Decisión: política de retry
MVP marca fallos como \`success=false\` y NO reintenta automáticamente. Razón: evitar infinite retry loops si Telegram banea el bot o si hay un mensaje sistemáticamente malformado. Si en operación esto se vuelve molesto, agregar job de \"retry failed notifications older than X\" en E11 (analytics/ops).

## 📝 Decisión: lag objetivo
<2 min entre \`Job.scored_at\` y notificación enviada. El cron de E8 corriendo ingest+score+dispatch en secuencia hará posible este SLA.

## 🧪 Criterios de Aceptación
- [ ] Test: 3 jobs tier-A nuevos → 3 sends → 3 records en \`notifications_sent\`.
- [ ] Test idempotencia: re-correr → 0 sends.
- [ ] Test aislamiento: 1 falla, otros 2 completan; \`DispatchReport\` cuenta correctamente.
- [ ] Test: notifier deshabilitado → return early con \`total_pending\` correcto pero 0 sends.

## 🔗 Dependencias
- Bloqueante: E05-S02, E05-S03.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S06 — Email digest semanal
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S06] Email digest semanal" \
    "## 🎯 Contexto Arquitectónico
Email resumen los domingos con estado del pipeline. Visibilidad agregada sin abrir el dashboard cada día. Contraste útil con las notificaciones tiempo-real de tier-A: una vista granular y otra panorámica.

## 📐 Alcance Técnico
- \`src/jobhunter/notify/digest.py\` con \`async send_weekly_digest(session, week_ending: date | None = None) -> NotificationResult\`.

### Contexto computado
- **Nuevos esta semana:** N jobs ingestados, N tier A, N tier B, N tier C.
- **Aplicaciones:** N enviadas esta semana, X tasa de respuesta agregada (últimas 4 semanas).
- **Pendientes:** N follow-ups vencidos, N tier A no aplicados (en \`queued\`), N tier C en \`manual_review\` esperando decisión.
- **Top 5 tier A no aplicados:** lista con título, empresa, score, link.
- **Métricas mensuales** (de \`weekly_metrics\` materializada de E2): apps/semana, conversión a entrevista.

### Renderizado
- Renderiza ambos templates: \`weekly_digest_email.html\` + \`weekly_digest_email.txt\`.
- Envía via \`EmailNotifier\` con multipart.

### Idempotencia
- \`dedup_key = f\"digest:{iso_year}:{iso_week}\"\`.
- Re-correr el mismo lunes no envía duplicado.

### Edge case: pipeline vacío
Si NO hay actividad esta semana (0 jobs nuevos, 0 aplicaciones), aún envía el email con tono honesto: \"Pipeline silencioso esta semana, posibles causas: …\". Útil para detectar pipeline roto antes que silencio confunda.

## 🧪 Criterios de Aceptación
- [ ] Test con DB seeded: contexto computado correctamente (counts coherentes).
- [ ] Test con DB vacía: digest se envía con mensaje apropiado.
- [ ] Test idempotencia: re-correr no envía duplicado.
- [ ] Test que verifica que ambos formatos (HTML + text) se generan y van al MIME message.

## 🔗 Dependencias
- Bloqueante: E05-S04.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E05-S07 — CLI + tests de integración
# ---------------------------------------------------------------------------
create_issue \
    "[E05-S07] CLI \`jobhunter notify\` + tests de integración" \
    "## 🎯 Contexto Arquitectónico
Cierre de la épica. Comandos CLI para operación manual, testing del pipeline completo, y documentación de setup. \`notify status\` es particularmente útil — cuando algo falla en operación, responde rápido \"¿el canal está enabled? ¿última notificación exitosa?\".

## 📐 Alcance Técnico

### Subgroup CLI \`jobhunter notify\`
- \`notify dispatch\` — invoca \`dispatch_tier_a_notifications\`. Output con tabla rich (jobs procesados, status, errores).
- \`notify digest [--send] [--week-ending DATE]\` — si \`--send\` envía, si no solo imprime preview a stdout.
- \`notify test --channel CHANNEL [--message MSG] [--subject SUBJ]\` — envía mensaje arbitrario al canal especificado (debug).
- \`notify status\` — muestra:
  - Canales registrados y estado (\`enabled\` / \`disabled\` con razón).
  - Últimas 10 notificaciones enviadas (canal, dedup_key, success, sent_at).
  - Fallos en últimas 24h (count + breakdown por canal).

### Tests de integración end-to-end (notifiers mockeados)
- Dispatch tier-A: 3 jobs → 3 sends → 3 records en \`notifications_sent\`.
- Re-dispatch: 0 sends (idempotencia verificada).
- Digest dispatch: 1 send con dedup_key correcto.
- \`notify status\` muestra info coherente tras dispatch.

### Documentación
- \`docs/runbook.md\` actualizado con secciones:
  - \"Configurar Telegram bot\" (paso a paso, con captura de comandos).
  - \"Configurar Gmail SMTP con App Password\".
  - \"Diagnosticar notificaciones que no llegan\" (checklist).

## 🧪 Criterios de Aceptación
- [ ] Tests CLI con \`typer.testing.CliRunner\` para cada comando.
- [ ] Tests integración pasan en CI sin red real.
- [ ] \`notify test\` real-test ejecutado y documentado: notificación recibida en Telegram.
- [ ] \`notify test\` real-test ejecutado: email recibido.
- [ ] Runbook documenta los 3 procedimientos.

## 🔗 Dependencias
- Bloqueante: E05-S05, E05-S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:notify,epic:E05" \
    "$OPT_EPIC_E05" \
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
echo "   3. ⚠️  ANTES DE IMPLEMENTAR S03: crear bot de Telegram con @BotFather y obtener chat_id."
echo "   4. ⚠️  ANTES DE IMPLEMENTAR S04: generar Gmail App Password si tu cuenta tiene 2FA."
echo ""
