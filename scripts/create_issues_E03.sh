#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E3 — Multi-source Job Ingestion
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
OPT_EPIC_E03="ecc070c5"     # E3-Ingestion

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
# 📋 DEFINITION OF DONE TEMPLATE (Python stack)
# ---------------------------------------------------------------------------
DOD_TEMPLATE='
### ✅ Definition of Done (DoD)
1. **Código limpio:** Pasa `ruff check`, `ruff format --check`, y `mypy --strict` sin warnings.
2. **Testing:** Tests unitarios y/o de integración cubren el comportamiento agregado; suite completa pasa en verde.
3. **Type hints:** Todos los miembros públicos tienen type annotations completas (parámetros, returns, atributos).
4. **Docstrings:** Toda función/clase/módulo público tiene docstring estilo Google o NumPy describiendo propósito, args, returns, raises.
5. **HTTP Cassettes (si aplica):** Tests que dependen de APIs externas usan cassettes grabados; CI corre `--block-network`.
6. **Pre-commit:** Todos los hooks pasan en local.
7. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
8. **Documentación:** Si la story añade una fuente nueva, actualiza `docs/sources.md` con: URL base, formato, rate limit, particularidades.'

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

create_label_if_missing "status:ready"       "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E03"           "1f8000" "Épica E03 — Multi-source Job Ingestion"
create_label_if_missing "type:infra"         "1d76db" "Infraestructura, setup, herramientas"
create_label_if_missing "type:feature"      "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"          "fbca04" "Tests, fixtures, cassettes"
create_label_if_missing "type:cli"           "8b4789" "Comandos CLI"
create_label_if_missing "component:sources"  "f9d0c4" "Adapters de fuentes de empleo"
create_label_if_missing "component:http"     "c2e0c6" "Cliente HTTP, retry, rate limiting"
create_label_if_missing "component:orchestrator" "fef2c0" "Orquestador, circuit breaker"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E03
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E03"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E03-S01 — BaseSource ABC + RawJob + Registry
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S01] \`BaseSource\` ABC + \`RawJob\` + Registry" \
    "## 🎯 Contexto Arquitectónico
Plugin pattern con registry. Toda fuente downstream (Arbeitnow, RemoteOK, etc.) implementará este contrato. Decisión clave: añadir una fuente nueva = crear clase + decorar con \`@register_source\`. El orquestador (S07) descubre fuentes vía registry, no via lista hardcoded.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/base.py\` con \`BaseSource(ABC)\` y método abstracto \`async fetch(since: datetime) -> AsyncIterator[RawJob]\`.
- Pydantic model \`RawJob\` (frozen) con campos normalizados: \`source_name\`, \`source_id\`, \`url\`, \`title\`, \`company\`, \`location_raw\`, \`description\`, \`posted_at\`, \`raw_payload\`.
- \`src/jobhunter/sources/registry.py\` con decorator \`@register_source\` y \`get_all_sources() -> list[BaseSource]\`.
- \`src/jobhunter/sources/url_utils.py\` con:
  - \`canonicalize_url(url)\` — lowercase host, strip query params de tracking (\`utm_*\`, \`gclid\`, \`fbclid\`, \`ref\`, \`mc_*\`), normalizar trailing slash.
  - \`compute_url_hash(url) -> str\` — sha256 sobre URL canonicalizada.

## 🧪 Criterios de Aceptación
- [ ] Tests unitarios sobre \`canonicalize_url\` cubren: trailing slash, mixed case host, query params reordenados, params de tracking, fragmentos.
- [ ] \`RawJob\` valida tipos correctamente (campos obligatorios fallan al estar ausentes).
- [ ] Registry: registrar 2 clases dummy y verificar \`get_all_sources()\` las retorna.
- [ ] mypy strict pasa.

## 📝 Decisión de diseño
\`AsyncIterator\` en lugar de \`list\`: permite streaming (procesar/persistir resultados a medida que llegan, no esperar a la respuesta completa). Importante para fuentes que paginan.

## 🔗 Dependencias
- Bloqueante: Épica E02 cerrada (necesitamos persistir).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S02 — HTTP client wrapper
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S02] HTTP client wrapper (retry, backoff, rate limit)" \
    "## 🎯 Contexto Arquitectónico
Toda fuente reusará este cliente. Centralizar manejo HTTP evita que cada adapter reimplemente retry/rate-limit (con bugs sutiles diferentes). \`tenacity\` provee primitivas robustas; rate limit por host vía semaphore.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/http.py\` con clase \`SourceHttpClient\` que envuelve \`httpx.AsyncClient\`.
- Retry con backoff exponencial (1s, 2s, 4s, jitter, max 3 reintentos) en: \`httpx.HTTPStatusError\` (status >= 500), \`httpx.TimeoutException\`, \`httpx.ConnectError\`.
- Manejo especial de **429**: respetar header \`Retry-After\` antes de reintentar.
- **No reintentar** en 4xx (excepto 429).
- Rate limiting por host configurable (req/s) usando \`asyncio.Semaphore\` o token bucket.
- User-Agent identificable: \`\"jobhunter-eu/0.3 (+https://github.com/Informatica-ASHware/Job-Hunter-EU)\"\`.
- Logging \`structlog\`: cada request con \`host\`, \`status_code\`, \`duration_ms\`, \`attempt\`.

## 🧪 Criterios de Aceptación
- [ ] \`test_retries_on_500_then_succeeds\` (3 fallos → 1 éxito = pasa).
- [ ] \`test_no_retry_on_404\` (no debe retentar; falla inmediato).
- [ ] \`test_respects_retry_after_on_429\`.
- [ ] \`test_rate_limit_throttles_concurrent_requests\` (mide tiempo, verifica throttling).
- [ ] Tests usan \`httpx.MockTransport\` (no red real).

## 🔗 Dependencias
- Bloqueante: E03-S01.
- Nuevas deps: \`httpx\`, \`tenacity\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:http,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S03 — ArbeitnowSource adapter
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S03] \`ArbeitnowSource\` adapter" \
    "## 🎯 Contexto Arquitectónico
Primera fuente productiva. Arbeitnow tiene API JSON pública limpia, ideal para validar el contrato \`BaseSource\` end-to-end.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/arbeitnow.py\` con clase \`ArbeitnowSource(BaseSource)\` decorada \`@register_source\`.
- Endpoint: \`https://www.arbeitnow.com/api/job-board-api\` (sin auth).
- Método \`_parse_job(raw: dict) -> RawJob | None\` (None si malformado, con log de warning).
- Filtra \`posted_at < since\` antes de yield.
- Maneja paginación si la API la soporta.

## 🧪 Criterios de Aceptación
- [ ] Test con cassette grabado: yields N \`RawJob\` válidos contra response real.
- [ ] Test con job malformado en respuesta: skip + log, no rompe iteración.
- [ ] Test de filtro \`since\`: ofertas viejas no se yieldean.
- [ ] Verificar manualmente con \`jobhunter ingest --source arbeitnow --limit 5 --dry-run\` cuando S08 esté listo.

## 🔗 Dependencias
- Bloqueante: E03-S02.
- Paralelizable con: S04, S05, S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S04 — RemoteOKSource adapter
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S04] \`RemoteOKSource\` adapter" \
    "## 🎯 Contexto Arquitectónico
RemoteOK cubre roles remotos globales (US-centric pero amplio). Su API JSON tiene una particularidad: el primer elemento es metadata, no un job — saltarse correctamente.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/remoteok.py\` con clase \`RemoteOKSource(BaseSource)\`.
- Endpoint: \`https://remoteok.com/api\`.
- **User-Agent obligatorio** (sin él, devuelven HTML, no JSON). Verificar.
- Saltar primer elemento de la respuesta (metadata).
- Filtro de tags configurable (default: contiene al menos uno de \`python\`, \`ai\`, \`ml\`, \`flutter\`, \`dart\`, \`senior\`, \`backend\`).
- \`default_rate_limit = 0.33\` (1 req cada 3s, conservador).
- \`posted_at\` viene en ISO8601, parsear correctamente.

## 🧪 Criterios de Aceptación
- [ ] Test con cassette grabado: yields jobs filtrados por tags.
- [ ] Test verifica que primer elemento (metadata) NO se yieldea.
- [ ] Test del filtro de tags: jobs sin tags relevantes no aparecen.

## 🔗 Dependencias
- Bloqueante: E03-S02.
- Paralelizable con: S03, S05, S06.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S05 — WeWorkRemotelySource (RSS) adapter
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S05] \`WeWorkRemotelySource\` (RSS) adapter" \
    "## 🎯 Contexto Arquitectónico
WWR es una fuente clásica de empleo remoto, distribuida vía RSS. Introduce el patrón de parsing XML (que también servirá para LinkedIn RSS en el futuro). HTML pesado en \`description\` requiere stripping antes de pasar a scoring.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/wwr.py\` con clase \`WeWorkRemotelySource(BaseSource)\`.
- Múltiples feeds configurables: \`programming\`, \`devops-sysadmin-jobs\`, \`back-end-programming\`, etc. URL pattern: \`https://weworkremotely.com/categories/{category}.rss\`.
- Parser con \`feedparser\` (nueva dep).
- Función \`_strip_html(html) -> str\` con BeautifulSoup, preserva texto, elimina tags y atributos.
- Mapeo: \`title\`, \`link\` → \`url\`, \`summary\` → \`description\` (stripped), \`pubDate\` → \`posted_at\`.
- Concatena entries de todos los feeds configurados; deduplicación por \`url\` dentro del mismo fetch (un job puede aparecer en varias categorías).

## 🧪 Criterios de Aceptación
- [ ] Cassette XML grabado para al menos 1 feed.
- [ ] Test verifica parsing correcto de fechas RFC 822.
- [ ] Test de \`_strip_html\` con HTML típico de WWR (incluye \`<br>\`, \`<p>\`, \`<a>\`).
- [ ] Si el mismo job aparece en 2 feeds, solo se yield una vez (deduplicación por URL en este fetch).

## 🔗 Dependencias
- Bloqueante: E03-S02.
- Paralelizable con: S03, S04, S06.
- Nuevas deps: \`feedparser\`, \`beautifulsoup4\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S06 — FourDayWeekSource adapter
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S06] \`FourDayWeekSource\` adapter" \
    "## 🎯 Contexto Arquitectónico
4dayweek.io agrega empresas con culturas de trabajo modernas (4-day weeks, async, remote-first). Señal de calidad cultural — empresas listadas tienden a pagar mejor y tener mejor work-life balance.

## 📐 Alcance Técnico
- \`src/jobhunter/sources/fourdayweek.py\` con clase \`FourDayWeekSource(BaseSource)\`.
- Investigar al implementar: API JSON o RSS (verificar URL base actual).
- Mapeo a \`RawJob\` con todos los campos requeridos.

## ⚠️ Plan B
Si 4dayweek.io no expone feed/API utilizable al investigar, sustituir por una de:
1. **GermanTechJobs.de** — alineado con foco DACH del proyecto.
2. **Wellfound** — vía RSS de búsquedas guardadas.
3. **LinkedIn** — vía RSS de búsquedas guardadas.

Documentar la decisión en commit message + actualizar este issue + actualizar \`docs/sources.md\`.

## 🧪 Criterios de Aceptación
- [ ] Cassette grabado.
- [ ] Test de parsing con response real.
- [ ] \`docs/sources.md\` documenta la fuente elegida (4dayweek o sustituto), URL, formato, particularidades.

## 🔗 Dependencias
- Bloqueante: E03-S02.
- Paralelizable con: S03, S04, S05.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S07 — Ingestion orchestrator + circuit breaker
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S07] Ingestion orchestrator + circuit breaker" \
    "## 🎯 Contexto Arquitectónico
El orquestador es el cerebro de E3: ejecuta todas las fuentes en paralelo, persiste deduplicado, y aísla fallos. Sin circuit breaker, una fuente caída drena el rate limit budget y satura logs en cada corrida del cron (E8). El breaker se abre tras 3 fallos seguidos y pausa 24h esa fuente específica — el resto sigue funcionando normalmente.

## 📐 Alcance Técnico

### Orquestador
- \`src/jobhunter/sources/orchestrator.py\` con \`async run_ingestion(sources, since, session) -> IngestionReport\`.
- Ejecuta fuentes en paralelo: \`asyncio.gather(*tasks, return_exceptions=True)\`.
- Persiste vía \`JobRepo.bulk_create_skipping_duplicates\`; cuenta nuevos vs duplicados por fuente.
- Si una fuente lanza excepción, se captura y se reporta — no propaga.

### Circuit breaker
- \`src/jobhunter/sources/circuit_breaker.py\` con clase \`CircuitBreaker\` (estados: closed/open/half_open).
- Configuración: \`failure_threshold = 3\`, \`pause_duration = 24h\`, \`half_open_probe_count = 1\`.
- Persistencia: nueva tabla \`source_health\` (migration Alembic) con: \`source_name\`, \`state\`, \`failure_count\`, \`last_failure_at\`, \`opened_until\`.

### Models de reporting
- Pydantic \`SourceResult\`: \`source_name\`, \`status\` (success/failed/skipped_breaker), \`new_jobs\`, \`duplicates\`, \`error: str | None\`, \`duration_ms\`.
- Pydantic \`IngestionReport\`: \`source_results\`, \`total_new\`, \`total_duplicates\`, \`total_errors\`, \`started_at\`, \`finished_at\`.

## 🧪 Criterios de Aceptación
- [ ] Test con 3 sources mockeados: una OK, una falla, una con breaker abierto → orchestrator reporta los 3 estados correctamente.
- [ ] Test que falla 3 veces consecutivas → breaker se abre → 4ta llamada se salta (no incrementa rate limit budget).
- [ ] Test que tras \`pause_duration\` el breaker pasa a \`half_open\` y deja pasar 1 request de prueba.
- [ ] Logs estructurados con resumen agregado al final.
- [ ] Migration de \`source_health\` aplicada.

## 📝 Decisión
Circuit breaker simple custom (~30 líneas), no \`aiobreaker\`. Para 4-6 fuentes, dependencia externa es overkill.

## 🔗 Dependencias
- Bloqueante: E03-S03, E03-S04, E03-S05, E03-S06.

## ⏱️ Estimación
3h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:orchestrator,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S08 — CLI: `jobhunter ingest`
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S08] CLI: \`jobhunter ingest\` y \`jobhunter sources list\`" \
    "## 🎯 Contexto Arquitectónico
Comando ergonómico para correr ingestion manual durante desarrollo y debugging. Sin esto, el inner loop pasa por el cron (E8) que aún no existe. \`--dry-run\` permite probar parsers sin contaminar la DB.

## 📐 Alcance Técnico

### \`jobhunter ingest\`
- Flags:
  - \`--source NAME\` (opcional, repetible) — solo correr fuentes específicas.
  - \`--since DATE\` (default: 7 días atrás) — filtro de fecha.
  - \`--limit N\` (default: sin límite) — cap por fuente.
  - \`--dry-run\` — fetch + parse pero no persiste a DB.
- Output: tabla con \`rich.table.Table\` mostrando por fila: source, status, new, duplicates, errors, duration.
- Footer: totales agregados.
- Exit code 1 si alguna fuente falló (útil para CI/cron alerting).

### \`jobhunter sources list\`
- Tabla con: \`name\`, \`circuit_breaker_state\`, \`last_failure_at\`, \`opened_until\` (si aplica).

## 🧪 Criterios de Aceptación
- [ ] Tests CLI con \`typer.testing.CliRunner\`:
  - [ ] \`ingest --dry-run\` no escribe a DB.
  - [ ] \`ingest --source arbeitnow\` solo corre esa fuente.
  - [ ] \`sources list\` muestra estado correcto post-ingestion.
- [ ] \`--help\` produce output legible.

## 🔗 Dependencias
- Bloqueante: E03-S07.
- Nuevas deps: \`rich\` (si no está ya).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:cli,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E03-S09 — Integration tests con HTTP cassettes
# ---------------------------------------------------------------------------
create_issue \
    "[E03-S09] Integration tests con HTTP cassettes" \
    "## 🎯 Contexto Arquitectónico
Tests reproducibles, sin red, rápidos. Cassettes capturan respuestas reales una vez y se versionan. Cuando una API cambia su schema, el test falla — exactamente la señal que queremos.

## 📐 Alcance Técnico
- \`pytest-recording\` configurado en \`pyproject.toml\`.
- Cassettes versionados en \`tests/integration/sources/cassettes/\`.
- Modo \`--record-mode=once\`: graba la primera vez, reproduce después.
- Modo CI \`--block-network\`: si un test intenta llamar a internet sin cassette, falla.
- Sanitización de cassettes (remover headers sensibles si los hay; en este caso no debería haber, todas las APIs son públicas).

### Tests end-to-end requeridos
- [ ] **Por adapter (S03–S06):** cassette → \`Source.fetch()\` → N \`RawJob\` válidos.
- [ ] **Orchestrator integration:** 4 sources con cassettes → orchestrator → repo → verifica jobs en DB.
- [ ] **Deduplicación:** correr ingest 2 veces consecutivas → segunda corrida 0 nuevos.
- [ ] **Circuit breaker:** simular 3 fallos consecutivos → 4ta llamada se salta sin tocar HTTP.
- [ ] **Aislamiento de fallos:** una fuente lanza excepción → otras 3 completan exitosamente.

## 🧪 Criterios de Aceptación
- [ ] Cassettes capturados para las 4 fuentes (limit ~5-10 jobs por cassette).
- [ ] CI corre tests integración con \`--block-network\` y pasan.
- [ ] Re-grabar cassettes documentado en \`docs/runbook.md\` (sección \"Re-grabar cassettes cuando una API cambia\").

## 🔗 Dependencias
- Bloqueante: E03-S03, E03-S04, E03-S05, E03-S06, E03-S07.
- Nueva dep: \`pytest-recording\`.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:test,component:sources,epic:E03" \
    "$OPT_EPIC_E03" \
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
echo ""
