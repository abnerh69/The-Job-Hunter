#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues y Project Sync
# Épica: E2 — Data Persistence Layer
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
OPT_EPIC_E02="d6c1cc08"     # E2-Persistence

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
5. **Migrations (si aplica):** `alembic upgrade head` y `alembic downgrade -1` ejecutan sin errores; migración revisada manualmente.
6. **Pre-commit:** Todos los hooks pasan en local.
7. **Revisión:** PR creado, descripción referencia este issue, CI/CD en verde antes de merge.
8. **Documentación:** Si la story modifica el modelo de datos, `docs/data_model.md` se actualiza en el mismo PR.'

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

create_label_if_missing "status:ready"      "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "epic:E02"          "5319e7" "Épica E02 — Data Persistence Layer"
create_label_if_missing "type:infra"        "1d76db" "Infraestructura, setup, herramientas"
create_label_if_missing "type:feature"      "0e8a16" "Funcionalidad nueva"
create_label_if_missing "type:test"         "fbca04" "Tests, fixtures, seeders"
create_label_if_missing "type:docs"         "c5def5" "Documentación"
create_label_if_missing "component:db"      "d93f0b" "Base de datos, modelos, migraciones"
create_label_if_missing "component:repos"   "e99695" "Repositorios (data access layer)"
create_label_if_missing "component:devops"  "bfdadc" "Scripts ops, backups"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN — CREACIÓN DE BACKLOG PARA LA ÉPICA E02
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU — Épica E02"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# E02-S01 — SQLAlchemy + Alembic Foundation
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S01] SQLAlchemy + Alembic Foundation" \
    "## 🎯 Contexto Arquitectónico
Toda escritura/lectura del sistema pasará por SQLAlchemy 2.x. Antes de modelar entidades, necesitamos infraestructura: motor de DB, sesiones, y Alembic listo para autogenerar migraciones a partir de \`Base.metadata\`. Esta story no entrega lógica de negocio — entrega el contrato base sobre el que las stories siguientes solo agregan modelos.

## 📐 Alcance Técnico
- \`src/jobhunter/db/session.py\` con \`engine\`, \`SessionLocal\`, context manager \`get_session()\`.
- \`src/jobhunter/db/base.py\` con \`Base = DeclarativeBase\` (estilo SQLAlchemy 2.x).
- \`alembic init\` ejecutado; \`alembic.ini\` y \`alembic/env.py\` configurados para tomar \`DATABASE_URL\` desde \`Settings\` y autogeneración basada en \`Base.metadata\`.
- Decisión: SQLAlchemy **sync** para v1 (más fácil de debuggear; async se puede agregar luego sin migración traumática).
- Pin de versión: \`sqlalchemy>=2.0.30,<3.0\`.

## 🧪 Criterios de Aceptación
- [ ] \`alembic upgrade head\` corre sobre DB vacía sin errores (aunque no haya modelos aún).
- [ ] \`from jobhunter.db.session import get_session\` permite abrir/cerrar sesión correctamente.
- [ ] Test smoke en \`tests/integration/db/test_connection.py\` verifica conexión.
- [ ] mypy strict pasa sobre el módulo \`db/\`.

## 🔗 Dependencias
- Bloqueante: Épica E01 cerrada (Foundation).

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S02 — Modelo `jobs` + primera migración
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S02] Modelo \`jobs\` + primera migración" \
    "## 🎯 Contexto Arquitectónico
La tabla \`jobs\` es la entidad central del sistema. Recibe ofertas de E3 (ingestion), las enriquece con scoring de E4, y alimenta tanto el pipeline de aplicación (E6) como el dashboard (E7). El campo \`url_hash\` con UNIQUE constraint es el mecanismo de deduplicación que garantiza idempotencia del pipeline.

## 📐 Alcance Técnico
- Clase \`Job\` en \`src/jobhunter/db/models.py\` con todos los campos de §4.1 del Documento B.
- Tipos: UUID PK con \`gen_random_uuid()\`, \`JSONB\` para \`raw_payload\` y \`score_data\`, \`TIMESTAMPTZ\` para fechas.
- Constraint UNIQUE sobre \`url_hash\` (sha256 de URL canónica).
- Índices: \`status\`, \`tier\`, \`scraped_at DESC\`, \`company\`.
- Enums Python en \`src/jobhunter/db/enums.py\`: \`JobStatus\`, \`JobTier\`.
- Migración Alembic generada vía \`--autogenerate\` y revisada manualmente (Alembic a veces inventa cosas raras con JSONB).

## ⚠️ Trampa conocida
\`score_data: JSONB\` requiere cuidado: mutar un dict in-place no marca la sesión como dirty en SQLAlchemy. Usar \`MutableDict.as_mutable(JSONB)\` o asignar siempre un dict nuevo.

## 🧪 Criterios de Aceptación
- [ ] Migración aplicada sobre DB local; \`\\d jobs\` en psql muestra columnas e índices correctos.
- [ ] Ciclo \`upgrade → downgrade -1 → upgrade\` ejecuta limpio.
- [ ] \`Session().add(Job(...))\` + commit + query funciona.
- [ ] Tests smoke de creación y unique constraint.

## 🔗 Dependencias
- Bloqueante: E02-S01.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S03 — Modelos `applications` + `application_events`
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S03] Modelos \`applications\` + \`application_events\`" \
    "## 🎯 Contexto Arquitectónico
Una vez que un \`Job\` pasa scoring y entra en estado \`queued\`, se crea un \`Application\` cuando se envía la candidatura. \`ApplicationEvent\` es el audit log que captura cada transición de estado — fundamental para análisis post-mortem (¿por qué este proceso se atascó? ¿cuánto tardó cada etapa?).

## 📐 Alcance Técnico
- \`Application\` con FK a \`jobs(id)\`, todos los campos de §4.1 del Documento B.
- \`ApplicationEvent\` con FK a \`applications(id)\`, \`event_type\` (enum), \`event_data: JSONB\`.
- Enum \`ApplicationStatus\`: applied, screening, interview_1, interview_n, offer, rejected, ghosted, withdrawn.
- Índice **parcial** en \`applications.next_action_due\` que excluye estados terminales (mejora performance de queries de follow-up).
- Relaciones SQLAlchemy bidireccionales: \`Job.applications\` ↔ \`Application.job\`; \`Application.events\` con \`cascade='all, delete-orphan'\`.

## 📝 Decisión de diseño
Audit log vía código de aplicación (no triggers Postgres). Más explícito, más fácil de debuggear, y SQLAlchemy events lo automatiza si después hace falta.

## 🧪 Criterios de Aceptación
- [ ] Migración aplicada; índice parcial verificado en \`\\di+\` de psql.
- [ ] Creación: \`Job\` → \`Application\` → \`ApplicationEvent\` funciona end-to-end.
- [ ] Cascade delete: borrar \`Application\` borra sus \`ApplicationEvent\`.
- [ ] Ciclo upgrade/downgrade limpio.

## 🔗 Dependencias
- Bloqueante: E02-S02.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S04 — Modelo `outreach_contacts`
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S04] Modelo \`outreach_contacts\`" \
    "## 🎯 Contexto Arquitectónico
Soporta la operación de outreach proactivo descrita en el Documento C (Playbook). Almacena reclutadores, contactos en empresas target, y trackea cadencia (cuándo se contactó, cuándo hacer follow-up, en qué status está). Independiente del flujo \`jobs\` → \`applications\`.

## 📐 Alcance Técnico
- \`OutreachContact\` con todos los campos de §4.1 del Documento B.
- Enums: \`OutreachMarket\` (germany, eu_wide, uk, netherlands, other), \`OutreachStatus\` (new, contacted, replied, ghosted, warm).
- Índice compuesto \`(status, last_contacted_at)\` para queries eficientes de \"contactos pendientes de follow-up\".
- UNIQUE constraint en \`linkedin_url\` cuando no es NULL (evitar contactar dos veces por error).

## 🧪 Criterios de Aceptación
- [ ] Migración aplicada limpiamente.
- [ ] Test smoke de creación + retrieval.
- [ ] Verificar unique constraint condicional en \`linkedin_url\` (NULL permitido múltiple, no-NULL único).

## 🔗 Dependencias
- Bloqueante: E02-S01.
- Paralelizable con: E02-S02, E02-S03.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S05 — Vista materializada `weekly_metrics`
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S05] Vista materializada \`weekly_metrics\`" \
    "## 🎯 Contexto Arquitectónico
El dashboard (E7) y el digest semanal (E5) necesitan métricas agregadas (apps/semana, tasa de respuesta, conversión a entrevista). Calcular en cada request es ineficiente; una vista materializada con \`REFRESH\` periódico balanco rapidez de query con frescura aceptable (refresh diario es suficiente).

## 📐 Alcance Técnico
- Vista materializada \`weekly_metrics\` definida en SQL crudo (Alembic no la autogenera) dentro de migration custom.
- Schema según §4.1 del Documento B: \`week\`, \`apps_sent\`, \`apps_with_response\`, \`interviews\`, \`offers\`, \`avg_offer_max\`.
- Función Python \`refresh_weekly_metrics(session)\` en \`src/jobhunter/db/maintenance.py\`.
- Comando CLI \`jobhunter db-refresh-metrics\` (typer wrapper).
- Migration \`downgrade()\` debe hacer \`DROP MATERIALIZED VIEW\`.

## 📝 Decisión
Para v1, refresh on-demand (CLI o cron en E8). Si se necesita refresh sin lock, usar \`REFRESH MATERIALIZED VIEW CONCURRENTLY\` (requiere índice unique en la vista).

## 🧪 Criterios de Aceptación
- [ ] Migración up/down funciona limpiamente.
- [ ] Tras seed de datos dummy + refresh, query devuelve filas esperadas.
- [ ] CLI \`jobhunter db-refresh-metrics\` ejecuta sin errores.

## 🔗 Dependencias
- Bloqueante: E02-S03.

## ⏱️ Estimación
1h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S06 — Repository base + JobRepo
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S06] Repository base + \`JobRepo\`" \
    "## 🎯 Contexto Arquitectónico
Repository pattern centraliza queries en clases tipadas, en lugar de SQLAlchemy ORM disperso por todo el código. Beneficios: tipado fuerte, queries reutilizables, fácil de mockear en tests, y permite cambiar implementación de DB sin tocar consumidores.

## 📐 Alcance Técnico
- \`BaseRepo[T]\` genérico en \`src/jobhunter/db/repos/base.py\` con \`get(id)\`, \`list(filters)\`, \`create(obj)\`, \`update(id, **fields)\`, \`delete(id)\`.
- \`JobRepo(BaseRepo[Job])\` con métodos específicos:
  - \`find_by_url_hash(hash) -> Job | None\`
  - \`list_by_status(status, limit=100) -> list[Job]\`
  - \`list_by_tier(tier, limit=100) -> list[Job]\`
  - \`mark_status(job_id, new_status) -> None\`
  - \`bulk_create_skipping_duplicates(jobs: list[Job]) -> list[UUID]\` (returns IDs of inserted, not skipped)
- \`bulk_create_skipping_duplicates\` debe usar \`INSERT ... ON CONFLICT (url_hash) DO NOTHING RETURNING id\` (Postgres-specific, performant).
- Tipos correctos en todos los métodos; mypy strict pasa.

## 🧪 Criterios de Aceptación
- [ ] \`test_find_by_url_hash_returns_none_when_missing\`
- [ ] \`test_create_and_retrieve_roundtrip\`
- [ ] \`test_bulk_create_dedupes_by_url_hash\` — insertar 5 jobs, 2 con mismo url_hash, verificar que solo 4 se persisten
- [ ] \`test_list_by_status_filter\` — filtros funcionan correctamente
- [ ] \`test_mark_status_updates_field_and_timestamp\`
- [ ] Fixture \`db_session\` transactional implementada en \`tests/conftest.py\` (rollback al final de cada test).

## 🔗 Dependencias
- Bloqueante: E02-S02.
- Paralelizable con: E02-S07.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:repos,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S07 — ApplicationRepo + OutreachRepo
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S07] \`ApplicationRepo\` + \`OutreachRepo\`" \
    "## 🎯 Contexto Arquitectónico
Repos restantes para completar el data access layer. \`ApplicationRepo.transition_status\` encapsula la atomicidad crítica (cambio de estado + audit event en una transacción). Sin esto, el riesgo es estados huérfanos sin evento correspondiente.

## 📐 Alcance Técnico

### \`ApplicationRepo(BaseRepo[Application])\`
- \`create_for_job(job_id, **kwargs) -> Application\`
- \`transition_status(app_id, new_status, note=None) -> ApplicationEvent\` — atómico: actualiza \`Application.status\` + crea \`ApplicationEvent\` con \`event_type='status_change'\`. Una sola transacción.
- \`list_pending_followups(today) -> list[Application]\` — \`status='applied'\` AND \`updated_at\` entre 7 y 10 días atrás.
- \`list_ghosted_candidates(today) -> list[Application]\` — \`status='applied'\` AND \`updated_at\` > 21 días.

### \`OutreachRepo(BaseRepo[OutreachContact])\`
- \`find_by_linkedin_url(url) -> OutreachContact | None\`
- \`list_due_for_followup(today) -> list[OutreachContact]\`
- \`mark_contacted(contact_id) -> None\` — incrementa contador, actualiza timestamp.
- \`bulk_import_from_csv(path) -> tuple[int, int]\` — devuelve (importados, duplicados omitidos).

## ⚠️ Atomicidad
\`transition_status\` debe ser todo-o-nada. Test específico que simula fallo a mitad y verifica que ambos cambios se rolean.

## 🧪 Criterios de Aceptación
- [ ] Tests para cada método público de ambos repos.
- [ ] Test específico de atomicidad de \`transition_status\`.
- [ ] Test de \`bulk_import_from_csv\` con CSV malformado (caso de error manejado).
- [ ] mypy strict pasa.

## 🔗 Dependencias
- Bloqueante: E02-S03, E02-S04.
- Paralelizable con: E02-S06.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:feature,component:repos,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S08 — Fixtures + seeders + tests integración
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S08] Fixtures, seeders y tests de integración" \
    "## 🎯 Contexto Arquitectónico
Sin data realista, el dashboard (E7) y desarrollo de épicas posteriores se hace ciego. Un seeder con dos escenarios (rich/minimal) acelera el inner loop de desarrollo. Fixtures pytest reutilizables eliminan duplicación entre tests.

## 📐 Alcance Técnico
- \`tests/fixtures/sample_jobs.json\` con ~50 ofertas realistas (mix de tiers A/B/C/REJECT, varias fuentes, variedad de stack).
- \`src/jobhunter/db/seed.py\` con función \`seed_database(scenario: Literal['rich', 'minimal'])\`.
  - **rich**: 50 jobs, 15 applications (varios estados), 20 outreach contacts.
  - **minimal**: 5 jobs, 2 applications, 3 contacts.
- Comando CLI \`jobhunter db-seed --scenario rich|minimal\`.
- Fixtures pytest en \`tests/conftest.py\`:
  - \`db_session\` (transactional, rollback al final)
  - \`sample_job\`, \`sample_application\`, \`sample_outreach_contact\` (basadas en fixtures JSON)
- Tests integración existentes (de S06, S07) refactorizados para usar las fixtures comunes.
- CI: \`.github/workflows/ci.yml\` corre tests integración contra Postgres del runner (ya disponible desde E01-S07).

## 💡 Tip
Las 50 ofertas realistas se pueden generar con Claude: prompt tipo \"genera 50 ofertas de trabajo realistas en JSON con campos title, company, location, description, source\".

## 🧪 Criterios de Aceptación
- [ ] \`jobhunter db-seed --scenario rich\` puebla DB en <5s, sin errores.
- [ ] \`pytest tests/integration/db/\` corre verde, todos los repos cubiertos.
- [ ] Fixtures no comparten estado entre tests (cada test ve DB con solo sus datos).
- [ ] CI verde con tests integración.

## 🔗 Dependencias
- Bloqueante: E02-S06, E02-S07.

## ⏱️ Estimación
2h
${DOD_TEMPLATE}" \
    "status:ready,type:test,component:db,epic:E02" \
    "$OPT_EPIC_E02" \
    "$OPT_PRIORITY_P0"

# ---------------------------------------------------------------------------
# E02-S09 — Backup + documentación ER
# ---------------------------------------------------------------------------
create_issue \
    "[E02-S09] Backup script y documentación ER" \
    "## 🎯 Contexto Arquitectónico
Cierre de la épica: garantizar recuperabilidad (backup probado end-to-end) y comprensibilidad del modelo (documentación visual ER). Sin esto, en 6 meses ni yo mismo recordaré por qué tal índice parcial existe.

## 📐 Alcance Técnico

### Backup
- \`scripts/backup_db.sh\` con \`pg_dump | gzip\` + verificación de integridad (\`gunzip -t\`).
- Comando CLI \`jobhunter db-backup [--output PATH]\`.
- Procedimiento de restauración documentado en \`docs/runbook.md\`.
- Test manual ejecutado: backup → drop DB → restore → verificar datos intactos.

### Documentación ER
- \`docs/data_model.md\` con secciones:
  - **Diagrama ER** en mermaid (renderiza nativamente en GitHub).
  - **Por tabla:** propósito, relaciones, campos clave.
  - **Decisiones de diseño:** por qué JSONB, por qué índices parciales, por qué UUIDs vs serials, convenciones de timestamps en UTC.
  - **Cómo añadir una tabla nueva:** workflow Alembic paso a paso.

### Runbook
- \`docs/runbook.md\` con secciones iniciales:
  - Restaurar DB desde backup.
  - Reset completo de DB local (\`docker-compose down -v && up && alembic upgrade head\`).
  - Re-correr migraciones desde cero.

## 🧪 Criterios de Aceptación
- [ ] Diagrama ER en mermaid renderiza correctamente en GitHub (verificar visualmente en preview del PR).
- [ ] Test manual de backup→restore documentado y ejecutado, con captura de comandos.
- [ ] \`runbook.md\` cubre los 3 procedimientos listados.

## 🔗 Dependencias
- Bloqueante: todas las stories anteriores de E02.

## ⏱️ Estimación
1.5h
${DOD_TEMPLATE}" \
    "status:ready,type:docs,component:devops,epic:E02" \
    "$OPT_EPIC_E02" \
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
