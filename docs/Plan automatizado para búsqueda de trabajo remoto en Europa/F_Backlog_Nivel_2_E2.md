# Documento F — Backlog Nivel 2: Descomposición de E2 (Data Persistence Layer)

**Épica origen:** E2 — Data Persistence Layer (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 9.
**Estimación total:** 13–16 horas (2-3 sesiones de medio día).

**Convenciones:** mismas que Documento E. ID `E02-S##`, formato user story + AC + tasks, estimaciones en horas reales.

---

## Resumen ejecutivo

E2 entrega el contrato de datos del sistema. Toda lectura/escritura pasa por aquí; ninguna épica downstream (E3 ingestion, E4 scoring, E7 dashboard, etc.) toca SQL directamente — usan los repositorios. Esto desacopla y permite que E2 evolucione (índices, particionamiento, etc.) sin romper consumidores.

Decisión arquitectónica clave: **Repository pattern en lugar de queries inline.** Marginalmente más boilerplate al inicio, paga dividendos masivos cuando hay 6+ módulos consumiendo la DB.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E02-S01 | SQLAlchemy + Alembic Foundation | 1.5h | E1 cerrada | — |
| E02-S02 | Modelo `jobs` + migration | 2h | S01 | — |
| E02-S03 | Modelos `applications` + `application_events` | 2h | S02 | — |
| E02-S04 | Modelo `outreach_contacts` | 1h | S01 | con S02, S03 |
| E02-S05 | Vista materializada `weekly_metrics` | 1h | S03 | — |
| E02-S06 | Repository base + `JobRepo` | 1.5h | S02 | con S07 |
| E02-S07 | `ApplicationRepo` + `OutreachRepo` | 2h | S03, S04 | con S06 |
| E02-S08 | Fixtures + seeders + tests integración | 2h | S06, S07 | — |
| E02-S09 | Backup script + documentación ER | 1.5h | todas | — |

### Camino crítico

```
E1 ─→ S01 ─→ S02 ─→ S03 ─→ S05 ─┐
              │      │           │
              ↓      ↓           │
              S04   S06 ─┐       │
                    S07 ─┴─→ S08 ─→ S09
```

**Tiempo serial:** ~14h. **Con paralelización (S04 mientras S02-S03, S06 con S07):** ~11h.

### Definition of Done de la épica (recordatorio)

```bash
alembic upgrade head           # corre limpio en DB vacía
alembic upgrade head           # idempotente, no falla al repetir
pytest tests/integration/db/   # todos los repos verde
python -m jobhunter.cli db-backup  # genera backup verificable
```

---

## E02-S01 — SQLAlchemy + Alembic Foundation

**Como** dueño del sistema, **quiero** SQLAlchemy 2.x configurado con sesiones async-ready y Alembic listo para generar migraciones, **para que** todas las stories siguientes solo agreguen modelos sin tocar infraestructura.

### Acceptance Criteria

- [ ] `src/jobhunter/db/session.py` expone `engine`, `SessionLocal`, y context manager `get_session()`.
- [ ] `src/jobhunter/db/base.py` define `Base = DeclarativeBase` (estilo SQLAlchemy 2.x).
- [ ] `alembic init` ejecutado, `alembic.ini` apunta a `DATABASE_URL` desde `Settings`.
- [ ] `alembic/env.py` configurado para autogeneración (importa `Base.metadata`).
- [ ] `alembic upgrade head` corre exitosamente sobre DB vacía (sin migraciones todavía).
- [ ] Comando smoke: `python -c "from jobhunter.db.session import get_session; ..."` funciona.

### Tasks

- [ ] Crear `src/jobhunter/db/__init__.py`
- [ ] Crear `src/jobhunter/db/base.py`:
  ```python
  from sqlalchemy.orm import DeclarativeBase
  
  class Base(DeclarativeBase):
      pass
  ```
- [ ] Crear `src/jobhunter/db/session.py` con `create_engine`, `sessionmaker`, y `get_session()` como contextmanager
- [ ] `uv run alembic init alembic`
- [ ] Editar `alembic.ini`: `sqlalchemy.url` se setea desde `env.py`, no aquí
- [ ] Editar `alembic/env.py`: importar `Settings` y `Base.metadata`, configurar `target_metadata`
- [ ] Verificar `alembic upgrade head` sobre DB local vacía
- [ ] Test smoke en `tests/integration/db/test_connection.py` que verifica que se puede abrir/cerrar sesión

### Estimación: 1.5h

### Notas

- **Async vs sync.** Para v1 usa SQLAlchemy sync — es suficiente y más fácil de debuggear. Si en el futuro el dashboard necesita async, se migra (SQLAlchemy 2.x soporta ambos coexistiendo).
- Pin de versión: `sqlalchemy>=2.0.30,<3.0`.

---

## E02-S02 — Modelo `jobs` + primera migración

**Como** dueño del sistema, **quiero** la tabla `jobs` modelada con todos los campos de scoring y la lógica de deduplicación, **para que** la ingestion (E3) y scoring (E4) tengan dónde escribir.

### Acceptance Criteria

- [ ] Clase `Job` en `src/jobhunter/db/models.py` con todos los campos de §4.1 del Documento B.
- [ ] Tipos correctos: UUID PK con default, `JSONB` para `raw_payload` y `score_data`, `TIMESTAMPTZ` para fechas.
- [ ] Constraint UNIQUE sobre `url_hash`.
- [ ] Índices en `status`, `tier`, `scraped_at DESC`, `company`.
- [ ] Enum (Python) para `status` y `tier` con validación.
- [ ] Migración Alembic generada y aplicada.
- [ ] Migración tiene `downgrade()` funcional (probado: upgrade → downgrade → upgrade).

### Tasks

- [ ] Definir enums en `src/jobhunter/db/enums.py`:
  ```python
  from enum import StrEnum
  
  class JobStatus(StrEnum):
      NEW = "new"
      SCORED = "scored"
      QUEUED = "queued"
      APPLIED = "applied"
      MANUAL_REVIEW = "manual_review"
      REJECTED = "rejected"
      ARCHIVED = "archived"
  
  class JobTier(StrEnum):
      A = "A"
      B = "B"
      C = "C"
      REJECT = "REJECT"
  ```
- [ ] Crear `src/jobhunter/db/models.py` con clase `Job` usando SQLAlchemy 2.x style (`Mapped[]`)
- [ ] Importar `Job` en `alembic/env.py` (vía `from jobhunter.db.models import *`)
- [ ] `uv run alembic revision --autogenerate -m "create jobs table"`
- [ ] Revisar la migración generada (Alembic a veces inventa cosas raras con JSONB)
- [ ] `uv run alembic upgrade head`
- [ ] Verificar en psql: `\d jobs` muestra columnas e índices correctos
- [ ] Probar downgrade: `alembic downgrade -1` y `alembic upgrade head` ciclo limpio

### Estimación: 2h

### Notas

- **`scored_at`, `score_model`, `score_version`, `fit_score`, `tier`, `score_data`** se inicializan como `nullable=True` — se poblarán cuando E4 (scoring) escriba. Pero conceptualmente forman parte de `jobs` (no de tabla separada) porque hay 1:1 con la oferta.
- `score_data: JSONB` debe usar `mutable_json_type` o cuidar de hacer copy-on-write — el bug clásico de SQLAlchemy: mutar un dict in-place no marca la sesión como dirty.

---

## E02-S03 — Modelos `applications` + `application_events`

**Como** dueño del sistema, **quiero** las tablas para trackear aplicaciones enviadas y su historial de estados, **para que** E6 (toolkit) y E7 (dashboard) puedan registrar y visualizar el pipeline.

### Acceptance Criteria

- [ ] Clase `Application` con FK a `jobs(id)`, todos los campos de §4.1 del Documento B.
- [ ] Clase `ApplicationEvent` con FK a `applications(id)`, audit log básico.
- [ ] Enum `ApplicationStatus` (applied, screening, interview_1, interview_n, offer, rejected, ghosted, withdrawn).
- [ ] Índice parcial en `applications.next_action_due` que excluye estados terminales (per Doc B §4.1).
- [ ] Relación bidireccional `Job.applications` y `Application.job` configurada.
- [ ] Relación `Application.events` con cascade delete.
- [ ] Migración generada, aplicada, downgrade funcional.

### Tasks

- [ ] Añadir enum `ApplicationStatus` y `ApplicationEventType` en `db/enums.py`
- [ ] Añadir `Application` a `db/models.py` con `relationship()` hacia `Job`
- [ ] Añadir `ApplicationEvent` con relationship hacia `Application` (cascade="all, delete-orphan")
- [ ] Definir índice parcial en migración manualmente (Alembic no autogenera índices parciales perfectamente):
  ```python
  op.create_index(
      'idx_apps_next_action_due',
      'applications',
      ['next_action_due'],
      postgresql_where=text("status NOT IN ('rejected', 'ghosted', 'withdrawn', 'offer')")
  )
  ```
- [ ] Generar migración, revisar, aplicar
- [ ] Test smoke: crear `Job` → crear `Application` referenciándola → crear `ApplicationEvent` → verificar relaciones

### Estimación: 2h

### Notas

- **Audit log via trigger vs aplicación.** Tentación: usar triggers Postgres para auto-poblar `application_events` en cada UPDATE. Recomendación: **no** — código de aplicación más explícito, más fácil de debuggear, y SQLAlchemy events lo cubre bien si se quiere automatizar después.

---

## E02-S04 — Modelo `outreach_contacts`

**Como** dueño del sistema, **quiero** la tabla para reclutadores y contactos de outreach, **para que** E9 (outreach module) tenga dónde persistir contactos y trackear cadencia.

### Acceptance Criteria

- [ ] Clase `OutreachContact` con todos los campos de §4.1 del Documento B.
- [ ] Enums para `market` (germany, eu_wide, uk, netherlands, etc.) y `status` (new, contacted, replied, ghosted, warm).
- [ ] Índice en `(status, last_contacted_at)` para queries de "necesitan follow-up".
- [ ] Migración aplicada y reversible.

### Tasks

- [ ] Añadir enums `OutreachMarket` y `OutreachStatus` en `db/enums.py`
- [ ] Añadir `OutreachContact` a `db/models.py`
- [ ] Generar migración, aplicar
- [ ] Test smoke de creación

### Estimación: 1h

### Paralelizable con

S02, S03 (no dependencia entre estas tablas).

---

## E02-S05 — Vista materializada `weekly_metrics`

**Como** dueño del sistema, **quiero** una vista materializada con métricas semanales pre-agregadas, **para que** el dashboard (E7) y el digest semanal (E5) consulten datos rápido sin agregaciones costosas en cada request.

### Acceptance Criteria

- [ ] Vista materializada `weekly_metrics` creada vía migration (definida en SQL crudo, Alembic no la autogenera).
- [ ] Query `SELECT * FROM weekly_metrics` devuelve estructura de §4.1 del Documento B.
- [ ] Comando CLI `jobhunter refresh-metrics` que ejecuta `REFRESH MATERIALIZED VIEW weekly_metrics`.
- [ ] Función Python wrapper `refresh_weekly_metrics(session)` para uso programático.

### Tasks

- [ ] Generar migration vacía: `alembic revision -m "create weekly_metrics view"`
- [ ] Editar la migración manualmente con SQL del Documento B §4.1
- [ ] En `downgrade()`: `DROP MATERIALIZED VIEW weekly_metrics`
- [ ] Aplicar migración
- [ ] Crear `src/jobhunter/db/maintenance.py` con función `refresh_weekly_metrics()`
- [ ] Añadir comando CLI `db-refresh-metrics` (wrapper sobre la función)
- [ ] Test que pobla datos dummy → refresh → query → verifica resultados

### Estimación: 1h

### Notas

- **Refresh frecuencia.** En operación, llamar tras cualquier cambio en `applications` es ineficiente. Mejor: `REFRESH` vía cron diario (E8) o on-demand cuando el dashboard lo pida. Para esta story, solo crear la infraestructura.
- Si Postgres < 12 o si necesitamos refresh sin lock, usar `REFRESH MATERIALIZED VIEW CONCURRENTLY` (requiere índice unique en la vista).

---

## E02-S06 — Repository base + `JobRepo`

**Como** dueño del sistema, **quiero** un patrón Repository implementado para `Job`, **para que** E3 (ingestion) y E4 (scoring) accedan a la DB con métodos tipados y no SQL crudo.

### Acceptance Criteria

- [ ] Clase abstracta `BaseRepo[T]` genérica con `get`, `list`, `create`, `update`, `delete`.
- [ ] `JobRepo(BaseRepo[Job])` con métodos específicos: `find_by_url_hash`, `list_by_status`, `list_by_tier`, `mark_status`, `bulk_create_skipping_duplicates`.
- [ ] Métodos retornan tipos correctos (no `Any`); mypy strict pasa.
- [ ] Tests unitarios cubren cada método con DB de testing (transactional fixtures).

### Tasks

- [ ] Crear `src/jobhunter/db/repos/__init__.py`
- [ ] Crear `src/jobhunter/db/repos/base.py` con `BaseRepo[T]` genérico
- [ ] Crear `src/jobhunter/db/repos/jobs.py` con `JobRepo`
- [ ] Implementar método `bulk_create_skipping_duplicates` usando `INSERT ... ON CONFLICT (url_hash) DO NOTHING RETURNING id` (Postgres-specific)
- [ ] Tests en `tests/integration/db/test_jobs_repo.py`:
  - [ ] `test_find_by_url_hash_returns_none_when_missing`
  - [ ] `test_create_and_retrieve_roundtrip`
  - [ ] `test_bulk_create_dedupes_by_url_hash`
  - [ ] `test_list_by_status_filter`
  - [ ] `test_mark_status_updates_field`

### Estimación: 1.5h

### Notas

- **Generic base repo.** Hay debate religioso sobre si vale la pena. Para este proyecto sí: 3 entidades principales con CRUD muy similar. Si fueran 30, peor — abstrae demasiado.
- **Transactional test fixtures.** Cada test corre en transacción que rolea atrás al final; nada se persiste entre tests. Implementar con fixture `db_session` en `conftest.py`.

---

## E02-S07 — `ApplicationRepo` + `OutreachRepo`

**Como** dueño del sistema, **quiero** repositorios para applications y outreach contacts, **para que** E6 (toolkit), E7 (dashboard), E9 (outreach) tengan APIs limpias.

### Acceptance Criteria

- [ ] `ApplicationRepo(BaseRepo[Application])` con métodos: `create_for_job`, `transition_status` (escribe `ApplicationEvent` automáticamente), `list_pending_followups`, `list_ghosted_candidates`.
- [ ] `OutreachRepo(BaseRepo[OutreachContact])` con métodos: `find_by_linkedin_url`, `list_due_for_followup`, `mark_contacted`, `bulk_import_from_csv`.
- [ ] Tests unitarios cubren cada método.

### Tasks

- [ ] Crear `src/jobhunter/db/repos/applications.py`
- [ ] Implementar `transition_status` que en una transacción: actualiza `Application.status` + crea `ApplicationEvent` con `event_type='status_change'`
- [ ] Implementar `list_pending_followups` (query con `status='applied'` AND última actualización entre 7-10 días atrás)
- [ ] Implementar `list_ghosted_candidates` (`status='applied'` AND última actualización > 21 días)
- [ ] Crear `src/jobhunter/db/repos/outreach.py`
- [ ] Tests en `tests/integration/db/test_applications_repo.py` y `test_outreach_repo.py`

### Estimación: 2h

### Paralelizable con

S06.

### Notas

- **`transition_status` atomicidad.** Crítico que la actualización de estado y el insert de evento sean en la misma transacción. Si falla uno, falla ambos.

---

## E02-S08 — Fixtures, seeders y tests de integración

**Como** dueño del sistema, **quiero** fixtures realistas y un seeder para poblar DB local con datos demo, **para que** desarrollo y testing del dashboard (E7) tengan data sin esperar al pipeline real.

### Acceptance Criteria

- [ ] `tests/conftest.py` define fixtures pytest: `db_session` (transactional), `sample_job`, `sample_application`, `sample_outreach_contact`.
- [ ] Comando CLI `jobhunter db-seed [--scenario rich|minimal]` puebla DB local con datos demo.
- [ ] Scenario `rich`: 50 jobs (mix de tiers), 15 applications (mix de estados), 20 outreach contacts.
- [ ] Scenario `minimal`: 5 jobs, 2 applications, 3 contacts.
- [ ] Suite de tests de integración corre verde en CI con Postgres del runner.

### Tasks

- [ ] Crear `tests/fixtures/sample_jobs.json` con 50 ofertas realistas (puedes generar con Claude pidiendo "50 ofertas de trabajo realistas con campos X, Y, Z en JSON")
- [ ] Crear `src/jobhunter/db/seed.py` con función `seed_database(scenario: str)`
- [ ] Añadir comando CLI `db-seed` (typer)
- [ ] Crear fixtures pytest reutilizables en `tests/conftest.py`
- [ ] Mover tests integración existentes a usar las fixtures comunes
- [ ] Verificar `pytest tests/integration/` corre verde
- [ ] Actualizar `.github/workflows/ci.yml` para correr tests de integración (ya tiene Postgres del job de S07 de E1)

### Estimación: 2h

### Notas

- **Fixtures vs factory pattern.** Para volumen pequeño, fixtures JSON son fine. Si en el futuro necesitas data más variada, considera `factory_boy`.

---

## E02-S09 — Backup script y documentación ER

**Como** dueño del sistema, **quiero** un script de backup confiable y documentación visual del modelo de datos, **para que** pueda recuperar de pérdida de DB y futuros yo (o cualquier reviewer) entiendan el esquema rápido.

### Acceptance Criteria

- [ ] Script `scripts/backup_db.sh` ejecuta `pg_dump` con timestamp en nombre, comprime, valida integridad.
- [ ] Comando CLI `jobhunter db-backup [--output PATH]` envuelve el script.
- [ ] `docs/data_model.md` con: descripción de cada tabla, diagrama ER (mermaid), explicación de decisiones (por qué JSONB, por qué índices parciales, etc.).
- [ ] Diagrama ER renderiza en GitHub (mermaid en markdown).
- [ ] Documentado el procedimiento de restauración en `docs/runbook.md` (sección "Restaurar DB desde backup").

### Tasks

- [ ] Crear `scripts/backup_db.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  OUTPUT="${1:-./backups}/jobhunter_${TIMESTAMP}.sql.gz"
  mkdir -p "$(dirname "$OUTPUT")"
  pg_dump "$DATABASE_URL" | gzip > "$OUTPUT"
  gunzip -t "$OUTPUT"  # verifica integridad
  echo "Backup OK: $OUTPUT"
  ```
- [ ] Añadir comando CLI `db-backup` (typer wrapper)
- [ ] Crear `docs/data_model.md` con secciones:
  - [ ] Diagrama ER (mermaid)
  - [ ] Decisiones de diseño
  - [ ] Convenciones (UUIDs, timestamps en UTC, JSONB para campos flexibles)
  - [ ] Cómo añadir una nueva tabla (workflow Alembic)
- [ ] Crear `docs/runbook.md` con secciones iniciales:
  - [ ] Restaurar DB desde backup
  - [ ] Reset completo de DB local
  - [ ] Re-correr migraciones desde cero
- [ ] Test manual: backup → drop DB → restore → verify data intacta

### Estimación: 1.5h

### Notas

- **Mermaid ER en GitHub.** Sintaxis `erDiagram` renderiza nativamente en GitHub markdown — no necesitas herramientas externas.
- **Backup almacenamiento.** Por ahora local. Más adelante (en E12) se decidirá si replicar a S3/Backblaze.

---

## Definition of Ready para E3

E2 cerrada cuando:

- [ ] Las 9 stories tienen AC ✅.
- [ ] CI verde con tests de integración corriendo.
- [ ] Backup probado end-to-end (drop → restore → verify).
- [ ] `docs/data_model.md` con diagrama ER actualizado.
- [ ] Tag `v0.2.0` creado.

A partir de aquí, **E3 (Multi-source Job Ingestion)** se puede empezar — los repos de `Job` están listos para que los scrapers escriban.

---

**Fin Documento F.**
