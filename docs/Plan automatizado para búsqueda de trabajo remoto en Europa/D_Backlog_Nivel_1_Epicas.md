# Documento D — Backlog Nivel 1: Épicas

**Proyecto:** `jobhunter-eu` (sistema automatizado de búsqueda de empleo).
**Base:** Documento B — Arquitectura del Sistema Automatizado.
**Nivel:** L1 (solo épicas). El nivel L2 (user stories y tasks) se deriva de aquí en una iteración posterior.

**Convenciones del backlog:**
- **ID:** `E##` (épica). Estable, no cambia.
- **Tamaño (T-shirt):** S = ≤1 día, M = 2-3 días, L = 4-6 días, XL = >1 semana.
- **Prioridad:** P0 (MVP crítico) · P1 (MVP deseable) · P2 (Post-MVP).
- **Sprint sugerido:** mapeo al roadmap del Documento B (S0–S4).

---

## Resumen ejecutivo

12 épicas organizadas en 3 olas. La **Ola 1 (E1–E5)** define el MVP funcional: ingestar ofertas, scorearlas con IA, persistirlas, y notificar matches de alta calidad. La **Ola 2 (E6–E8)** añade la capa de productividad (asistencia para aplicar, dashboard, automatización). La **Ola 3 (E9–E12)** cierra el ciclo con outreach, detección de respuestas, métricas y operaciones.

**MVP cut (P0):** E1, E2, E3, E4, E5, E8 → sistema corre desatendido y notifica matches A-tier. ~6-8 días de trabajo.

**Producto completo:** todas las épicas. ~3-4 semanas de trabajo a tiempo parcial.

---

## Tabla resumen

| ID | Épica | Tamaño | Prioridad | Sprint | Depende de |
|----|---|---|---|---|---|
| E1 | Foundation & Project Bootstrap | S | P0 | S0 | — |
| E2 | Data Persistence Layer | M | P0 | S0–S1 | E1 |
| E3 | Multi-source Job Ingestion | L | P0 | S1 | E1, E2 |
| E4 | AI Scoring Engine | M | P0 | S1 | E1, E2 |
| E5 | Real-time Notification System | S | P0 | S2 | E2, E4 |
| E6 | AI-Assisted Application Toolkit | M | P1 | S2 | E2, E4 |
| E7 | Dashboard & Application Tracker | L | P1 | S2–S3 | E2 |
| E8 | Scheduling & Automation | S | P0 | S3 | E3, E4 |
| E9 | Recruiter Outreach Module | M | P2 | S4 | E2, E6 |
| E10 | Response Detection (Gmail) | M | P2 | S4 | E2, E6 |
| E11 | Metrics, Analytics & Tuning | M | P2 | S4 | E2, E7 |
| E12 | Observability, Security & Ops | M | P1 | cross | todas |

---

## Diagrama de dependencias

```
                    ┌─────┐
                    │ E1  │  Foundation
                    └──┬──┘
                       │
                    ┌──▼──┐
                    │ E2  │  Persistence
                    └──┬──┘
            ┌──────────┼──────────┐
            ▼          ▼          ▼
         ┌─────┐    ┌─────┐    ┌─────┐
         │ E3  │    │ E4  │    │ E7  │  Ingest · Scoring · Dashboard
         └──┬──┘    └──┬──┘    └─────┘
            │          │
            └────┬─────┘
                 ▼
              ┌─────┐
              │ E5  │  Notification
              └──┬──┘
                 │
              ┌──▼──┐
              │ E8  │  Scheduling  ← MVP cut completa aquí
              └─────┘
                 │
       ┌─────────┼─────────┬─────────┐
       ▼         ▼         ▼         ▼
    ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐
    │ E6  │  │ E9  │  │ E10 │  │ E11 │  Toolkit · Outreach · Gmail · Métricas
    └─────┘  └─────┘  └─────┘  └─────┘

    ┌─────┐
    │ E12 │  Observability — cross-cutting, atraviesa todas
    └─────┘
```

---

## E1 — Foundation & Project Bootstrap

**Outcome:** Proyecto inicializado con estructura, dependencias, herramientas de desarrollo y configuración base. Cualquier desarrollador (yo mismo dentro de 6 meses) puede clonar y correr en <10 minutos.

**Alcance:**
- Estructura de directorios según §5 del Documento B.
- Gestor de dependencias (`pyproject.toml` con `uv` o `poetry`).
- Configuración de entorno (`pydantic-settings` + `.env.example`).
- Toolchain de desarrollo: ruff, black, mypy, pytest configurados.
- `Dockerfile` + `docker-compose.yml` para Postgres local.
- README inicial con instrucciones de setup.

**Definition of Done:**
- `git clone && cp .env.example .env && docker-compose up && uv sync` deja el entorno corriendo.
- `pytest` ejecuta (aunque no haya tests reales todavía).
- CI básico en GitHub Actions corre lint + typecheck en PR.

**Tamaño:** S · **Prioridad:** P0 · **Sprint:** S0

**Métrica de éxito:** Tiempo de onboarding < 10 min en máquina limpia.

---

## E2 — Data Persistence Layer

**Outcome:** Modelo de datos completo, versionado y migrable. Toda escritura/lectura del sistema pasa por este layer. Sirve como contrato estable para todas las épicas downstream.

**Alcance:**
- Modelos SQLAlchemy 2.x para `jobs`, `applications`, `application_events`, `outreach_contacts` (per §4.1 del Doc B).
- Migrations con Alembic, versionadas en repo.
- Repository pattern: clases `JobRepo`, `ApplicationRepo`, etc. encapsulan queries comunes.
- Vistas materializadas para métricas pre-agregadas.
- Seeders/fixtures para datos de prueba.
- Backup script (`pg_dump`).

**Definition of Done:**
- Migrations corren idempotentes (`alembic upgrade head` dos veces no rompe).
- Tests unitarios cubren los repositorios (CRUD básico de cada entidad).
- Documentación corta (`docs/data_model.md`) con diagrama ER.

**Tamaño:** M · **Prioridad:** P0 · **Sprint:** S0–S1

**Métrica de éxito:** Cero `ALTER TABLE` manuales una vez en producción; toda evolución vía migration.

---

## E3 — Multi-source Job Ingestion

**Outcome:** Pipeline ingiere ofertas desde múltiples fuentes externas, deduplica, y las persiste como `status='new'` listas para scoring. Plugin-based: añadir una fuente nueva no requiere tocar el resto.

**Alcance:**
- ABC `BaseSource` con interfaz `async fetch(since: datetime) -> List[RawJob]`.
- Implementación de fuentes prioritarias para MVP: Arbeitnow, RemoteOK, WeWorkRemotely (RSS), JOIN.com.
- Implementación de fuentes secundarias (post-MVP): GermanTechJobs, LinkedIn vía RSS de búsquedas guardadas, 4dayweek.io.
- Deduplicación robusta vía `url_hash` (sha256 de URL canónica).
- Manejo de rate limits y backoff exponencial.
- Circuit breaker por fuente (3 fallos → pausa 24h).
- CLI: `jobhunter ingest [--source X] [--since DATE]`.

**Definition of Done:**
- ≥4 fuentes funcionales para MVP, retornando ofertas reales.
- Una fuente que falla no detiene las demás.
- Test de integración: mock de respuesta de cada fuente → registros correctos en DB.
- 0 duplicados al re-correr ingest dos veces seguidas.

**Tamaño:** L · **Prioridad:** P0 · **Sprint:** S1

**Métrica de éxito:** ≥100 ofertas únicas/semana ingeridas tras estabilización.

---

## E4 — AI Scoring Engine

**Outcome:** Toda oferta nueva se scorea con el prompt maestro (Documento A) en ≤30s, devolviendo JSON validado y persistido. El tier asignado dispara el flujo correcto downstream.

**Alcance:**
- Wrapper sobre el SDK `anthropic` con retry, timeout, y manejo de errores estructurado.
- Carga del prompt maestro versionado desde el repo (Documento A como fuente de verdad).
- Validación de schema del JSON de respuesta (Pydantic).
- Pipeline `score_pending_jobs()` que toma jobs en `status='new'` y los procesa en batch.
- Lógica de transición de estado: tier A/B → `queued`, tier C → `manual_review`, REJECT → `rejected`.
- Soporte para re-scoring (variante 7A del Doc A) con segundo modelo cuando convenga.
- CLI: `jobhunter score [--limit N] [--rescore-tier-a]`.

**Definition of Done:**
- Procesa 50 ofertas reales sin errores no manejados.
- Si la API falla, los jobs quedan en `status='new'` para retry — no se pierde nada.
- Costo medido por job ≤ $0.005 USD con Haiku.
- Tests con respuestas mockeadas de la API cubren happy path + 3 casos de error.

**Tamaño:** M · **Prioridad:** P0 · **Sprint:** S1

**Métrica de éxito:** ≥95% de ofertas se scorean exitosamente al primer intento.

---

## E5 — Real-time Notification System

**Outcome:** Cada match tier-A genera notificación a Telegram en <60s. Resumen semanal vía email los domingos. Notificaciones son útiles, no spam.

**Alcance:**
- Bot de Telegram con `python-telegram-bot`: mensaje por match A-tier con link, score, salario estimado, y un quick-action `/assist <job_id>`.
- Email digest semanal (cron domingo 18:00 COT) con resumen: nuevas A-tier, B-tier pendientes, follow-ups vencidos.
- Sistema de templates de notificación.
- Deduplicación: nunca dos notificaciones por la misma oferta.
- CLI manual: `jobhunter notify --job-id X` para testing.

**Definition of Done:**
- Telegram bot operativo, recibo notificaciones reales.
- Email digest se entrega correctamente y formato es legible en mobile.
- Notificaciones se pueden silenciar (config flag) para fines de semana o vacaciones.

**Tamaño:** S · **Prioridad:** P0 · **Sprint:** S2

**Métrica de éxito:** Lag promedio entre match A-tier scoreado y notificación recibida < 2 minutos.

---

## E6 — AI-Assisted Application Toolkit

**Outcome:** Para cualquier oferta tier A/B, el sistema produce en <30s un paquete listo para revisar y enviar: cover letter draft, recomendación de variante de CV, lista de tweaks sugeridos, y keywords para ATS.

**Alcance:**
- Generador de cover letter con Claude Opus 4.7, alimentado por: JD, variante de CV, `cover_letter_angle` del scoring.
- Tres variantes de CV mantenidas en el repo (`cv_variants/ai_python.md`, `flutter.md`, `fullstack.md`).
- Selector automático de variante basado en el `score_data`.
- Extractor de keywords ATS de la JD.
- Sugeridor de tweaks: qué bullets reordenar, qué keywords incluir.
- CLI: `jobhunter assist <job_id>` que devuelve el paquete completo en JSON o markdown.
- Comando para registrar la aplicación enviada: `jobhunter applied <job_id> --method web --cv-variant ai_python`.

**Definition of Done:**
- Cover letter generada es coherente, específica al JD, y respeta tu voz (no genérica IA).
- Sistema persiste la cover letter generada en `applications.cover_letter_text`.
- Workflow probado end-to-end con 5 ofertas reales.

**Tamaño:** M · **Prioridad:** P1 · **Sprint:** S2

**Métrica de éxito:** Tiempo medio de oferta-tier-A a aplicación enviada ≤ 10 min.

---

## E7 — Dashboard & Application Tracker

**Outcome:** UI web con visión completa del pipeline. Permite revisar matches, mover aplicaciones por estados, ver métricas, y registrar notas — todo sin tocar la base de datos directamente.

**Alcance:**
- Dashboard Streamlit (versión MVP) con páginas:
  - **New Matches:** tier A/B sin aplicar, ordenadas por score.
  - **Pipeline:** kanban de aplicaciones por estado (applied → screening → interview → offer/rejected).
  - **Manual Review:** tier C esperando decisión.
  - **Outreach:** contactos de reclutadores y su estado (relacionado con E9).
  - **Metrics:** dashboard de métricas semanales.
- Filtros: por fuente, por tier, por fecha, por stack.
- Acciones in-place: mover de estado, añadir nota, marcar follow-up.
- Búsqueda full-text sobre JDs.
- (Stretch) Versión Flutter Web del dashboard como portfolio piece.

**Definition of Done:**
- Todos los flujos diarios se pueden hacer desde el dashboard sin SQL manual.
- Mobile-responsive aceptable (uso desde teléfono mientras tomo café).
- Persistencia de filtros entre sesiones.

**Tamaño:** L · **Prioridad:** P1 · **Sprint:** S2–S3

**Métrica de éxito:** Tiempo de revisión diaria del pipeline (matches + follow-ups) < 10 min.

---

## E8 — Scheduling & Automation

**Outcome:** El sistema corre desatendido. Cron schedules ejecutan ingest, scoring, follow-up checks y digests sin intervención humana. Yo solo intervengo para revisar matches y aplicar.

**Alcance:**
- GitHub Actions workflows:
  - `ingest.yml` — cada 8h, corre `ingest` + `score`.
  - `score.yml` — separado por si se quiere correr solo scoring.
  - `digest.yml` — domingos 18:00 COT.
  - `followup_check.yml` — diario 09:00 COT, marca ghosted y sugiere follow-ups.
  - `ci.yml` — tests + lint en PR.
- GitHub Secrets para credenciales (Anthropic API key, Telegram token, DB connection string, etc.).
- Logs de ejecución persistidos (artifacts en GH Actions o tabla `system_runs` en DB).
- Alerta a Telegram si un workflow falla 2 veces seguidas.
- (Alternativa) Airflow DAG para los mismos jobs, si en el futuro se prefiere control local.

**Definition of Done:**
- 7 días consecutivos de operación sin intervención manual.
- Logs accesibles para debug post-mortem.

**Tamaño:** S · **Prioridad:** P0 · **Sprint:** S3

**Métrica de éxito:** Disponibilidad efectiva ≥ 95% (jobs corren cuando deben).

---

## E9 — Recruiter Outreach Module

**Outcome:** Soporte para la operación de outreach descrita en el Documento C. Sistema gestiona contactos, genera mensajes asistidos por IA, trackea cadencia y respuestas.

**Alcance:**
- CRUD de `outreach_contacts` desde dashboard (E7) y CLI.
- Generador de mensajes con Claude Sonnet 4.6: `jobhunter outreach draft --contact-id X --type A_inhouse --note "..."`.
- Templates A, B, C, D versionados en el repo (Documento C §3).
- Tracker de cadencia: qué contactos esperan follow-up, cuáles marcar ghosted.
- Métricas de outreach: tasa de respuesta por template, por mercado, por tipo de reclutador.
- Importación bulk de contactos desde CSV (post-LinkedIn search export).

**Definition of Done:**
- Workflow completo probado: importar 5 contactos → generar mensajes → enviar manualmente → registrar respuestas → ver métricas.
- Mensajes generados pasan el "smell test" — no parecen plantilla obvia.

**Tamaño:** M · **Prioridad:** P2 · **Sprint:** S4

**Métrica de éxito:** Tiempo medio para generar y enviar un mensaje de outreach ≤ 4 min (vs ~10 min sin asistencia).

---

## E10 — Response Detection (Gmail Integration)

**Outcome:** Cuando una empresa o reclutador responde a una aplicación o outreach, el sistema lo detecta automáticamente y propone update de estado. Cero respuestas se pierden.

**Alcance:**
- Integración Gmail API con OAuth (scope `gmail.readonly` + `gmail.modify` para etiquetas).
- Watcher (polling cada 30 min, o push notifications de Gmail) que escanea inbox.
- Matching heurístico (+IA opcional): asociar email entrante con `application` o `outreach_contact` por dominio, asunto, contacto.
- Sugerencia automática de cambio de estado: "Email de @company.com sugiere mover Job#123 a 'screening'?"
- Etiquetado automático en Gmail (`jobhunter/applied`, `jobhunter/interview`, etc.).
- Notificación Telegram cuando hay respuesta detectada.

**Definition of Done:**
- Detecta correctamente ≥90% de las respuestas a aplicaciones registradas.
- 0 falsos positivos críticos (ej. no marcar como "rejected" un email que no es rechazo).

**Tamaño:** M · **Prioridad:** P2 · **Sprint:** S4

**Métrica de éxito:** Reducción del 80% en tiempo de actualización manual de estados.

---

## E11 — Metrics, Analytics & Continuous Tuning

**Outcome:** Visibilidad completa sobre la salud del pipeline. Decisiones de qué fuentes priorizar, qué prompts ajustar, qué templates funcionan, basadas en data, no intuición.

**Alcance:**
- Dashboard de métricas dentro de E7:
  - Aplicaciones/semana, tasa de respuesta, tasa entrevista, tasa oferta.
  - Productividad por fuente (apps generadas, response rate por fuente).
  - Distribución de salarios ofrecidos.
  - Tiempos: lag de descubrimiento, lag de aplicación, ciclo total.
- Reportes mensuales auto-generados en markdown.
- A/B testing infrastructure: poder etiquetar prompts/templates y comparar performance.
- Análisis de "false rejects" (ofertas marcadas REJECT que en retrospectiva eran válidas).
- Recomendaciones automáticas: "Tu tasa de respuesta cayó 30% esta semana — ¿revisar CV?".

**Definition of Done:**
- Reporte mensual generado al día 1 de cada mes con narrativa coherente.
- Al menos 1 mejora del prompt maestro o templates respaldada por data.

**Tamaño:** M · **Prioridad:** P2 · **Sprint:** S4

**Métrica de éxito:** Mejora medible de tasa de respuesta tras 8 semanas operativas (baseline → +20%).

---

## E12 — Observability, Security & Operations

**Outcome:** Sistema operable en producción personal con confianza. Cuando algo se rompe, lo sé rápido y puedo debuggear. Datos sensibles protegidos. Cero secretos commiteados.

**Alcance:** *(cross-cutting, evoluciona en paralelo a otras épicas)*
- Logging estructurado con `structlog` en todos los componentes.
- Alertas Telegram para: workflow fallido, fuente de scraping rota >24h, costo Claude excedido.
- Health check endpoint del dashboard.
- `.gitignore` riguroso, secrets exclusivamente en `.env` local + GH Secrets.
- Pre-commit hook con `detect-secrets` o similar.
- Backup automático semanal de DB (pg_dump → ubicación segura).
- Plan de recuperación documentado: cómo restaurar desde backup, cómo rotar credenciales si se filtran.
- Repositorio mantenido en privado mientras tenga datos personales.
- Documentación operativa: `docs/runbook.md` con troubleshooting común.

**Definition of Done:**
- Auditoría manual: 0 secretos en historial de Git.
- Simulacro de "DB perdida": backup permite restaurar en <30 min.
- Runbook cubre los 5 incidentes más probables.

**Tamaño:** M · **Prioridad:** P1 · **Sprint:** continuo

**Métrica de éxito:** MTTD (mean time to detect) de fallos < 1 hora; MTTR < 24 horas.

---

## Cut MVP (P0) — qué entrega valor mínimo

```
E1 → E2 → E3 → E4 → E5 → E8
```

Con estas 6 épicas, el sistema:
- Ingiere ofertas de ≥4 fuentes cada 8h.
- Las scorea con IA y filtra.
- Notifica matches A-tier a Telegram en <2 min.
- Corre desatendido vía GitHub Actions.

**Tiempo estimado:** 6-8 días de trabajo concentrado.
**Output operativo:** ya puedes empezar a aplicar manualmente a buenos matches mientras construyes el resto.

---

## Notas para próxima iteración (Nivel 2)

Cuando se descomponga este backlog a stories:

1. **Empezar por E1.** Sin foundation no hay nada.
2. **E2 antes que E3/E4.** El modelo de datos es el contrato — definirlo bien evita refactor masivo después.
3. **E3 y E4 se pueden paralelizar** una vez E2 está estable (un día cada uno, distinto contexto mental).
4. **E12 (observabilidad) no se deja para el final.** Cada épica debe contribuir su parte de logging/alertas mientras se construye, no después.
5. **Las épicas P2 (E9–E11) son legítimamente opcionales.** Si después de 4 semanas operando el MVP la búsqueda ya dio fruto, quizás nunca se construyan — y está bien.

**Convención sugerida para naming de stories en L2:** `E03-S01: Implementar BaseSource ABC`, `E03-S02: Adaptador Arbeitnow`, etc.

---

**Fin Documento D.**
