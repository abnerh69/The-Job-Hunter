#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E7 — Dashboard & Application Tracker
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
OPT_EPIC_E07="2a7579cd"     # E7-Dashboard

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack + Streamlit specifics)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios cubren la lógica de servicios; tests E2E con Playwright cubren flujos críticos.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas.
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google/NumPy.
5. **Streamlit best practices:** Uso de `@st.cache_data` en queries pesadas; `st.session_state` para estado de UI; sin re-queries innecesarias en cada interacción.
6. **Read-only by default:** Toda mutación a la DB requiere botón explícito + confirmación. Sin auto-saves implícitos.
7. **Mobile-aware:** La página funciona razonablemente en viewport <500px (test manual).
8. **Performance:** Página carga en <2s con DB seeded `rich`; queries cacheadas con TTL apropiado.
9. **Pre-commit:** Todos los hooks pasan en local.
10. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
11. **Documentación:** Si la story añade una página nueva, screenshot incluido en el PR para revisión visual.'

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
create_label_if_missing "epic:E07"                   "00bfa5" "Épica E07 — Dashboard & Application Tracker"
create_label_if_missing "type:feature"               "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"                  "fbca04" "Tests, fixtures, E2E"
create_label_if_missing "type:infra"                 "1d76db" "Infraestructura, deploy"
create_label_if_missing "component:dashboard"        "9c27b0" "Páginas y componentes Streamlit"
create_label_if_missing "component:auth"             "ff5722" "Autenticación, sesión"
create_label_if_missing "component:db"               "d93f0b" "Migraciones, repos, queries"
create_label_if_missing "component:metrics"          "00838f" "Métricas, analytics, charts"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E07
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E07"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E07-S01 — Foundation Streamlit + auth + layout
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S01] Foundation Streamlit + auth + layout" \
    "## 🎯 Contexto Arquitectónico
Base del dashboard. Las 8 stories siguientes solo añaden contenido sobre esta plumbing. Decisión arquitectónica: **Streamlit, no FastAPI+Vue/React** (ver Anexo Documento K). Trade-off explícito: rápido de construir (1 día), limitado en customización fina; suficiente para un usuario único.

## 📐 Alcance Técnico

### Estructura multipágina
- \`src/jobhunter/dashboard/streamlit_app.py\` como entry point.
- \`src/jobhunter/dashboard/pages/\`:
  - \`1_📥_New_Matches.py\`
  - \`2_📋_Pipeline.py\`
  - \`3_🔍_Manual_Review.py\`
  - \`4_💌_Outreach.py\`
  - \`5_📊_Metrics.py\`
- (Numeración con emoji controla el orden alfabético de Streamlit.)

### Autenticación simple
- Settings nuevas: \`dashboard_password: SecretStr\`, \`dashboard_session_timeout_minutes: int = 60\`.
- Login screen con form, password almacenado en \`st.session_state\` tras éxito.
- Helper \`require_auth()\` invocado al inicio de cada página.

### Layout
- \`render_header()\`: título, versión del sistema, link de logout.
- \`render_sidebar()\`: estado del sistema (última ingestion, matches A pendientes, fallos recientes), refresh button.
- Theme custom en \`.streamlit/config.toml\`: paleta de colores, dark mode.

### CLI
- Comando \`jobhunter dashboard\` que ejecuta \`streamlit run src/jobhunter/dashboard/streamlit_app.py\`.

## 📝 Decisión: Auth simple
Un solo usuario (yo). Password en env var es suficiente. OAuth/Auth0 sería overkill. Si futuro multi-usuario, migrar a \`streamlit-authenticator\` es trivial.

## 🧪 Criterios de Aceptación
- [ ] \`streamlit run src/jobhunter/dashboard/streamlit_app.py\` levanta dashboard en <3s.
- [ ] Login screen funcional; password incorrecto muestra error claro.
- [ ] Cada página placeholder verifica auth (intentar acceder sin login redirige a login).
- [ ] Sidebar muestra estado del sistema actualizado.
- [ ] Theme custom aplicado consistentemente.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada.
- Nuevas deps: \`streamlit>=1.30\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:auth,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S02 — Página: New Matches
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S02] Página: New Matches (tier A/B sin aplicar)" \
    "## 🎯 Contexto Arquitectónico
La página más usada en operación diaria. Lista jobs \`status='queued'\` ordenados por score. Workflow target: revisar 5-15 matches, decidir cuáles aplicar, lanzar assist en los elegidos.

## 📐 Alcance Técnico

### Query y filtros
- Página \`pages/1_📥_New_Matches.py\` muestra jobs \`status='queued'\` ordenados por \`fit_score DESC\`.
- Filtros laterales:
  - Tier (A, B, ambas).
  - Source (multi-select).
  - Min score (slider 50-100).
  - Stack predominante (chips: Python, Flutter, AI/ML, Backend).
  - Salario mínimo USD/mes.

### Cards visuales por job
- Header: emoji tier + título + empresa.
- Score y rango salarial estimado.
- Top 3 match points (de \`score_data.match_analysis.key_match_points\`).
- Top red/yellow flags si los hay.
- Footer: source, scraped_at relative (\"hace 2h\"), botones de acción.

### Acciones por job
- **Assist** (verde) — link a página de E07-S08 (\`?job_id=X\`).
- **Skip** (gris) — transiciona a \`status='archived'\` con confirmación.
- **Mark Applied** (azul) — modal con form (method, cv_variant, notes).
- **View JD** (link externo) — abre URL original.

### UX
- Paginación: 20 jobs por página.
- Refresh manual + auto-refresh cada 5 min (toggle, pausado durante modal abierto).
- Métrica top: \"X jobs nuevos hoy, Y A-tier pendientes\".

### Caching
- \`@st.cache_data(ttl=60)\` en queries pesadas.

## 🧪 Criterios de Aceptación
- [ ] Filtros funcionan combinables (multi-filtro = AND).
- [ ] \"Skip\" requiere confirmación antes de archivar.
- [ ] \"Mark Applied\" crea \`Application\` y transiciona job correctamente.
- [ ] Auto-refresh NO interrumpe modal abierto.
- [ ] Test E2E: filtrar por tier A → 5 cards renderizan → click Skip en 1 → desaparece.

## 🔗 Dependencias
- Bloqueante: E07-S01.
- Paralelizable con: E07-S03, E07-S04, E07-S05.

## ⏱️ Estimación
2.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S03 — Página: Pipeline (kanban)
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S03] Página: Pipeline (kanban de aplicaciones)" \
    "## 🎯 Contexto Arquitectónico
Tablero kanban con todas las aplicaciones organizadas por estado. Vista del embudo completo. El audit log de \`application_events\` (de E2) brilla aquí: cada cambio de estado, cada nota — todo trazable en el modal de detalle.

## 📐 Alcance Técnico

### Layout kanban
- Página \`pages/2_📋_Pipeline.py\` con columnas por \`ApplicationStatus\`:
  \`applied\` → \`screening\` → \`interview_1\` → \`interview_n\` → \`offer\` / \`rejected\` / \`ghosted\`.
- Implementado con \`st.columns\`.

### Cards compactos por aplicación
- Empresa + título.
- Tiempo en estado actual (\"hace 5 días\").
- Indicador visual si \`next_action_due\` es hoy o pasó (badge rojo).
- Click abre modal de detalle.

### Modal de detalle
- Job info completa (título, empresa, link, stack).
- Cover letter aplicada (read-only).
- Tabs:
  - **Notes** — textarea editable, save explícito.
  - **Events history** — timeline de \`application_events\` (de E2).
  - **Contact info** — name, email, linkedin.
- Botones de transición: \"Move to Screening\", \"Move to Interview 1\", etc.
- Form para \`next_action\` y \`next_action_due\`.

### Filtros
- Por método (web/email/linkedin/referral).
- Por mes de aplicación.
- Mostrar/ocultar estados terminales (rejected, ghosted, withdrawn).

### Indicador top
- Total apps activas, edad media en pipeline, próximas 3 acciones más urgentes.

### Drag & drop
- Si \`streamlit-sortables\` u otro componente community soporta, integrar.
- Si no, fallback: botones \"Move to next\" en cada card.

## 📝 Decisión
Drag & drop en Streamlit es frágil (componentes community rompen con releases). Empezar con botones; si rinde, considerar drag&drop en E11.

## 🧪 Criterios de Aceptación
- [ ] Las 7 columnas renderizan correctamente.
- [ ] Modal de detalle abre con click en card.
- [ ] Transición de estado invoca \`ApplicationRepo.transition_status\` (atómico, crea event).
- [ ] Timeline de eventos se actualiza tras transición.
- [ ] Test E2E: crear app → mover a screening → verificar event creado.

## 🔗 Dependencias
- Bloqueante: E07-S01.
- Paralelizable con: E07-S02, E07-S04, E07-S05.

## ⏱️ Estimación
3h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S04 — Página: Manual Review
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S04] Página: Manual Review (tier C)" \
    "## 🎯 Contexto Arquitectónico
Jobs tier C (\`manual_review\`) requieren juicio humano. Sin esta página acumulan polvo y se pierden oportunidades borderline. La UI debería empujar a decidir.

## 📐 Alcance Técnico

### Página
- \`pages/3_🔍_Manual_Review.py\` lista jobs \`status='manual_review'\`.

### Cards más detalladas que New Matches
- JD completa (collapsible).
- \`score_data\` completo formato leíble (yellow_flags resaltados).
- Razón principal de \"manual_review\" (de \`score_data.recommendation.reason_short\`).

### Acciones por job
- **Promote to Queue** — transiciona a \`status='queued'\` (entra al flujo de aplicación).
- **Re-score** — re-ejecuta scoring con prompt actual + Sonnet 4.6 (variante 7A del Documento A).
  - Mostrar diff entre score original y nuevo si difieren > 10 puntos.
- **Reject** — transiciona a \`status='rejected'\` con razón opcional.

### Filtros e indicadores
- Filtro: por antigüedad (jobs viejos en review acumulan polvo).
- Indicador top: \"X jobs esperan review, Y > 7 días sin decisión\".

## 🧪 Criterios de Aceptación
- [ ] Tres acciones funcionan correctamente y persisten.
- [ ] Re-score con Sonnet muestra diff visual claro.
- [ ] Indicador de \"> 7 días sin decisión\" calcula correctamente.

## 🔗 Dependencias
- Bloqueante: E07-S01.
- Paralelizable con: E07-S02, E07-S03, E07-S05.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S05 — Página: Outreach
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S05] Página: Outreach (contactos reclutadores)" \
    "## 🎯 Contexto Arquitectónico
Visualización + acciones manuales sobre \`outreach_contacts\`. Esta página prepara el terreno para E9 (módulo de outreach con generación IA). Cuando E9 cierre, el botón \"Generate Message\" se activa.

## 📐 Alcance Técnico

### Tabla
- \`pages/4_💌_Outreach.py\` con tabla de \`outreach_contacts\`.
- \`st.data_editor\` para edición inline de \`notes\` y \`quality_score\` (sin abrir modal por cada uno).

### Filtros
- Status (new/contacted/replied/ghosted/warm).
- Market (germany/eu_wide/uk/etc.).
- Specialty stack (chips).
- Due for follow-up (boolean).

### Acciones bulk
- **Importar CSV** (usa \`OutreachRepo.bulk_import_from_csv\`) — modal con preview de primeras 5 filas + confirmación.
- **Exportar selección a CSV**.

### Acciones por contacto
- **Mark Contacted** — incrementa contador, actualiza \`last_contacted_at\`, transiciona a \`contacted\`.
- **Mark Replied** → status \`replied\`.
- **Mark Warm** → status \`warm\` (lead caliente, prioridad alta).
- **Add Note** — modal con textarea.
- **Generate Message** — placeholder por ahora: botón presente pero deshabilitado, tooltip \"Available in E9\".
- **Open LinkedIn** — abre URL externa.

### Indicador top
Contactos por status, follow-ups pendientes hoy.

## 🧪 Criterios de Aceptación
- [ ] Importar CSV con preview funciona.
- [ ] Edición inline de \`notes\` persiste.
- [ ] Acciones de status transicionan correctamente.
- [ ] \"Generate Message\" deshabilitado con tooltip apropiado.

## 🔗 Dependencias
- Bloqueante: E07-S01.
- Paralelizable con: E07-S02, E07-S03, E07-S04.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S06 — Página: Metrics & Analytics
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S06] Página: Metrics & Analytics" \
    "## 🎯 Contexto Arquitectónico
Vista panorámica del pipeline. Detecta problemas (caída de tasa de respuesta, fuente rota) sin abrir SQL. La materialized view \`weekly_metrics\` (de E2-S05) alimenta tendencias temporales.

## 📐 Alcance Técnico

### Página \`pages/5_📊_Metrics.py\` con secciones
1. **Funnel:** ingest → scored → queued → applied → screening → interview → offer. Conversión entre etapas.
2. **Por fuente:** jobs ingestados, % tier A, jobs aplicados, response rate por fuente.
3. **Tendencias temporales:** últimas 8 semanas. Gráfica de apps/semana, response rate.
4. **Costos LLM:** total mes, breakdown por purpose (scoring/cover_letter/etc.), tendencia diaria. (Usa \`llm_calls\` de E4-S06.)
5. **Distribución de tiers:** pie chart o bar chart.
6. **Salud del sistema:** estado de circuit breakers (de E3-S07), última ingestion exitosa por fuente.

### Charts
- \`plotly.express\` (más rápido de prototipar que altair).
- Streamlit native support.

### Date range selector global
Aplica a todas las métricas. Default: últimas 4 semanas.

### Caching agresivo
\`@st.cache_data(ttl=300)\` en queries de funnel y tendencias.

### Servicios centralizados
\`dashboard/services/metrics.py\` con todas las queries — evita duplicar código en otras páginas.

### Export PDF
Stub por ahora (P2 en E11).

## 🧪 Criterios de Aceptación
- [ ] Las 6 secciones renderizan con DB seeded \`rich\`.
- [ ] Date range selector actualiza todas las secciones consistentemente.
- [ ] Performance: página completa carga en <2s.
- [ ] Estado de circuit breakers refleja realidad (test forzando un breaker abierto).

## 🔗 Dependencias
- Bloqueante: E07-S03.
- Paralelizable con: E07-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:metrics,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S07 — Búsqueda full-text
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S07] Búsqueda full-text + filtros globales" \
    "## 🎯 Contexto Arquitectónico
Búsqueda global resuelve \"¿cuándo apliqué a esa empresa con Python AI?\" en 5 segundos. Postgres tsvector + GIN index >> LIKE para 1000+ jobs (100x más rápido + soporta stemming).

## 📐 Alcance Técnico

### Migration
- Agregar columna \`search_vector tsvector\` a \`jobs\`, \`applications\`, \`outreach_contacts\`.
- Usar \`GENERATED ALWAYS AS (...)\` (Postgres 12+) para auto-poblar — evita triggers manuales.
- GIN index en cada \`search_vector\`.

### Search bar
- Persistente en sidebar (visible en todas las páginas).
- Query persiste entre páginas hasta borrar explícitamente.

### Búsqueda
- Full-text contra:
  - \`Job.title\`, \`Job.company\`, \`Job.description\`.
  - \`Application.notes\`.
  - \`OutreachContact.name\`, \`OutreachContact.company\`.
- \`SearchRepo.search(query, limit=20) -> SearchResults\`.
- Resultados agrupados por entidad (jobs / applications / contacts), ordenados por relevancia (\`ts_rank\`).

### Página de resultados
- \`pages/6_🔎_Search.py\` con resultados expandidos.
- Click en resultado lleva a la página correspondiente con foco en el item (query param \`?focus=ID\`).

## 📝 Decisión técnica
\`GENERATED ALWAYS AS\` over triggers — más declarativo, menos código que mantener.

## 🧪 Criterios de Aceptación
- [ ] Migration aplicada; índices GIN creados.
- [ ] Búsqueda \"Python AI Berlin\" devuelve resultados relevantes en <100ms.
- [ ] Stemming funciona: \"running\" matches \"run\".
- [ ] Click en resultado navega correctamente con foco.

## 🔗 Dependencias
- Bloqueante: E07-S02, E07-S03, E07-S04, E07-S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,component:db,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S08 — Integración con E6 toolkit (assist desde UI)
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S08] Integración con E6 toolkit (assist desde UI)" \
    "## 🎯 Contexto Arquitectónico
Cierra el workflow completo en una sola UI: descubrir → assist → aplicar → registrar. Sin terminal. Streaming progress hace los ~30s de generación tolerables visualmente.

## 📐 Alcance Técnico

### Página
- \`pages/7_🛠_Assist.py\` recibe \`?job_id=X\` query param.
- Botón \"Assist\" en cards de New Matches (S02) navega a esta página.

### Streaming progress
- Spinner durante generación (~30s) con progress steps usando \`st.status()\`:
  1. \"Selecting CV variant…\"
  2. \"Generating cover letter (Opus)…\"
  3. \"Extracting ATS keywords…\"
  4. \"Suggesting CV tweaks…\"
- Cada paso aparece a medida que completa.

### Output renderizado
- **Cover letter:** textarea editable + botón \"Copy\" + \"Save edits\".
- **CV Tweaks:** lista checkable.
- **ATS Keywords:** chips con indicador presente/ausente en CV.
- **Variante recomendada** con confidence.

### Persistencia de ediciones
Si el usuario edita la cover letter en la UI, los cambios persisten en \`applications.cover_letter_text\` cuando hace \"Save\" o \"Mark Applied\". **Las ediciones humanas son señal valiosa** para futura calibración del prompt.

### Acción final
- Botón \"Mark Applied\" al final con form (método, notes).
- Costo total de la corrida visible (transparencia).

## 🧪 Criterios de Aceptación
- [ ] Streaming progress funciona (cada paso aparece secuencialmente).
- [ ] Edición de cover letter persiste tras \"Save\".
- [ ] \"Mark Applied\" crea \`Application\` con cover letter editada (no la original).
- [ ] Test E2E: navegar de New Matches → Assist → editar → Mark Applied → verificar en Pipeline.

## 🔗 Dependencias
- Bloqueante: E07-S02, Épica E06 cerrada.
- Paralelizable con: E07-S07.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
    "$OPT_PRIORITY_P1"

# ---------------------------------------------------------------------------
# E07-S09 — Deploy opcional + tests Playwright
# ---------------------------------------------------------------------------
create_issue \
    "[E07-S09] Deploy opcional + tests Playwright" \
    "## 🎯 Contexto Arquitectónico
Cierre de la épica con dos componentes:
1. **Tests E2E Playwright** (P1) para que el dashboard no se rompa silenciosamente.
2. **Deploy opcional** (P2) para acceder desde fuera de casa (alternativa: tailscale).

## 📐 Alcance Técnico

### Tests Playwright (P1)
- Dependencia: \`pytest-playwright\`.
- Tests E2E en \`tests/e2e/dashboard/\`:
  - Login con credenciales correctas → dashboard.
  - Login con password incorrecto → error.
  - Navegación entre páginas funciona.
  - Búsqueda devuelve resultados.
  - Smoke test del flujo \"Mark Applied\" desde New Matches.
- Selectores con \`data-testid\` (no class names volátiles).
- Workflow CI separado (más lento, no bloquea PRs default).

### Deploy a Fly.io (P2)
- \`Dockerfile.dashboard\` específico (puede heredar del principal).
- HTTPS via proxy (Fly.io lo provee automáticamente).
- Variables de entorno seguras (incluido \`dashboard_password\`).
- Documentar en \`docs/runbook.md\` sección \"Deploy dashboard a Fly.io\".

## 📝 Notas
- **Deploy es opcional.** Local-first sigue siendo válido; \`tailscale\` es mejor que exponer a internet.
- **Playwright en Streamlit es delicado** (websockets dinámicos). Empezar con 5 tests críticos, no 50 frágiles.

## 🧪 Criterios de Aceptación
- [ ] 5 tests E2E pasan en CI workflow separado.
- [ ] (P2) \`Dockerfile.dashboard\` builda correctamente.
- [ ] (P2) Deploy a Fly.io documentado y reproducido.

## 🔗 Dependencias
- Bloqueante: E07-S08.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:test,type:infra,component:dashboard,epic:E07" \
    "$OPT_EPIC_E07" \
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
echo "   3. ⚠️  Antes de empezar S07: verificar Postgres 12+ para soporte de"
echo "       'GENERATED ALWAYS AS' columns con tsvector."
echo ""
