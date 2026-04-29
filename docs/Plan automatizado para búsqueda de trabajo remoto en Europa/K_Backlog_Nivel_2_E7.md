# Documento K — Backlog Nivel 2: Descomposición de E7 (Dashboard & Application Tracker)

**Épica origen:** E7 — Dashboard & Application Tracker (Documento D).
**Tamaño épica:** L (4-6 días).
**Total stories:** 9.
**Estimación total:** 17–21 horas (3-4 sesiones de medio día).

**Convenciones:** mismas que documentos E–J. ID `E07-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E7 es la **interfaz humana del sistema**. Hasta aquí todo es CLI + Telegram. El dashboard expone visualmente lo que el sistema sabe, permite mover aplicaciones por estados sin SQL manual, y consolida métricas. **Sin él, escalar la operación diaria es doloroso** — revisar 15 matches A en terminal funciona, pero 50+ requiere vista panorámica.

**Decisión arquitectónica clave** (del Documento B §9): empezar con **Streamlit**, no Flutter Web. Streamlit te da el dashboard funcional en un día; Flutter Web tomaría una semana para algo equivalente. Streamlit es trade-off explícito: rápido de construir, limitado en customización fina. Si el sistema rinde y quieres convertir el dashboard en portfolio piece de Flutter, queda como story P2 en E11.

### Decisiones técnicas clave

1. **Streamlit como framework principal** — multipágina, autenticación simple, deploy trivial.
2. **Read-only por default, write-explicit** — toda mutación requiere botón + confirmación. Previene cambios accidentales.
3. **Auth simple (un solo usuario)** — password en `Settings`, no OAuth. El sistema es personal.
4. **Acceso directo a repos de E2** — el dashboard NO duplica lógica. Si una métrica existe, vive en `LLMCallRepo` o `ApplicationRepo`, el dashboard la consume.
5. **Caching agresivo con `@st.cache_data`** — Streamlit re-renderiza en cada interacción; sin cache, queries pesadas matan latencia.
6. **Mobile-responsive aceptable** — uso desde teléfono mientras tomo café. Streamlit no es perfecto en mobile pero es usable.
7. **Local-first, deploy opcional** — corre en `localhost:8501`. Deploy a Fly.io/Railway es separado (story opcional al final).

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E07-S01 | Foundation Streamlit + auth + layout | 2h | E2 cerrada | — |
| E07-S02 | Página: New Matches (tier A/B sin aplicar) | 2.5h | S01 | con S03, S04 |
| E07-S03 | Página: Pipeline (kanban de aplicaciones) | 3h | S01 | con S02, S04 |
| E07-S04 | Página: Manual Review (tier C) | 1.5h | S01 | con S02, S03 |
| E07-S05 | Página: Outreach (contactos reclutadores) | 1.5h | S01 | con S02–S04 |
| E07-S06 | Página: Metrics & Analytics | 2h | S03 | con S05 |
| E07-S07 | Búsqueda full-text + filtros globales | 2h | S02–S05 | — |
| E07-S08 | Integración con E6 toolkit (assist desde UI) | 1.5h | S02 | con S07 |
| E07-S09 | Deploy opcional + tests Playwright | 2h | S08 | — |

### Camino crítico

```
E2 ─→ S01 ─→ ┬─→ S02 ─┐
             ├─→ S03 ─┤
             ├─→ S04 ─┼─→ S07 ─→ S08 ─→ S09
             └─→ S05 ─┘
                S03 ─→ S06
```

**Tiempo serial:** ~18h. **Con paralelización (S02+S03+S04+S05 en paralelo):** ~12h.

### Definition of Done de la épica

```bash
# Levantar el dashboard
streamlit run src/jobhunter/dashboard/streamlit_app.py
# → Login screen, password de .env
# → Vistas: New Matches, Pipeline, Manual Review, Outreach, Metrics

# Workflow: revisar matches del día desde el teléfono en café (mobile)
# → 5 nuevos tier A → marco 2 como "skip", lanzo assist en 1, dejo 2 para más tarde

# Desktop: arrastrar aplicaciones por kanban (interview_1 → interview_n)
```

---

## E07-S01 — Foundation Streamlit + auth + layout

**Como** dueño del sistema, **quiero** la base del dashboard con autenticación simple, navegación multipágina, y layout consistente, **para que** las páginas siguientes solo añadan contenido sin reinventar plumbing.

### Acceptance Criteria

- [ ] `src/jobhunter/dashboard/streamlit_app.py` como entry point.
- [ ] Estructura multipágina con `pages/` (Streamlit native multipage):
  - `pages/1_📥_New_Matches.py`
  - `pages/2_📋_Pipeline.py`
  - `pages/3_🔍_Manual_Review.py`
  - `pages/4_💌_Outreach.py`
  - `pages/5_📊_Metrics.py`
- [ ] Autenticación simple: password en `Settings.dashboard_password: SecretStr`. Login screen con formulario, password almacenado en `st.session_state` tras éxito.
- [ ] Layout helper `render_header()` con: logo/título, indicador de versión del sistema, link de logout.
- [ ] Sidebar con: estado del sistema (última ingestion, matches A pendientes, fallos recientes), refresh button.
- [ ] Theme custom: paleta de colores consistente, dark/light mode respeta sistema.
- [ ] Settings nuevas: `dashboard_password: SecretStr`, `dashboard_session_timeout_minutes: int = 60`.
- [ ] `streamlit run` levanta el dashboard en <3s.

### Tasks

- [ ] Añadir dependencia `streamlit>=1.30`.
- [ ] Crear estructura `src/jobhunter/dashboard/`.
- [ ] Implementar `streamlit_app.py` con login flow.
- [ ] Crear módulo `dashboard/components/auth.py` con `require_auth()` decorator/helper.
- [ ] Crear módulo `dashboard/components/layout.py` con `render_header`, `render_sidebar`.
- [ ] Configurar tema en `.streamlit/config.toml` (colores acordes a la marca).
- [ ] Página placeholder en cada `pages/*.py` que solo verifica auth.
- [ ] Comando CLI `jobhunter dashboard` que ejecuta `streamlit run` (wrapper conveniente).

### Estimación: 2h

### Notas

- **Auth simple deliberada.** Un solo usuario (yo). Password en env var es suficiente. OAuth/Auth0 sería overkill y añadiría 4h de scope. Si en el futuro hay multi-usuario, migrar a `streamlit-authenticator` es trivial.
- **`st.session_state`** sobrevive recargas de página dentro de la misma sesión, no entre cierres del navegador. Aceptable.
- **Numeración de páginas con emoji:** Streamlit ordena alfabéticamente; `1_📥_...`, `2_📋_...` controla orden + emoji da identidad visual.

---

## E07-S02 — Página: New Matches (tier A/B sin aplicar)

**Como** dueño del sistema, **quiero** ver todos los matches tier A y B aún no aplicados, ordenados por score, **para que** pueda decidir rápidamente cuáles aplicar hoy.

### Acceptance Criteria

- [ ] Página `pages/1_📥_New_Matches.py` muestra jobs `status='queued'` ordenados por `fit_score DESC`.
- [ ] Filtros laterales:
  - [ ] Tier (A, B, ambas).
  - [ ] Source (multi-select).
  - [ ] Min score (slider 50-100).
  - [ ] Stack predominante (chips: Python, Flutter, AI/ML, Backend).
  - [ ] Salario mínimo USD/mes.
- [ ] Cards visuales por job con:
  - Header: emoji tier + título + empresa.
  - Score y rango salarial estimado.
  - Top 3 match points (de `score_data.match_analysis.key_match_points`).
  - Top red/yellow flags si los hay.
  - Footer: source, scraped_at relative ("hace 2h"), botones de acción.
- [ ] Acciones por job (botones):
  - [ ] **Assist** (verde) — dispara E6 toolkit (link a página detalle, ver S08).
  - [ ] **Skip** (gris) — transiciona job a `status='archived'` con confirmación.
  - [ ] **Mark Applied** (azul) — abre modal con form de `apply` (method, cv_variant, notes).
  - [ ] **View JD** (link externo) — abre URL original.
- [ ] Paginación: 20 jobs por página.
- [ ] Refresh manual + auto-refresh cada 5 min (toggle).
- [ ] Métrica top: "X jobs nuevos hoy, Y A-tier pendientes".

### Tasks

- [ ] Implementar página con `JobRepo.list_by_status('queued', tier=...)`.
- [ ] Componente `render_job_card(job)` reutilizable en `dashboard/components/cards.py`.
- [ ] Modal de "Mark Applied" con `st.dialog` (Streamlit ≥1.30).
- [ ] Cache con `@st.cache_data(ttl=60)` en queries pesadas.
- [ ] Integración con `ApplicationRepo.create_for_job` para "Mark Applied".

### Estimación: 2.5h

### Paralelizable con

S03, S04, S05.

### Notas

- **Densidad visual.** 20 jobs por página con cards completas es ~3-4 scrolls. Si abruma, agregar vista compacta (toggle).
- **Auto-refresh peligroso.** Si el usuario está en medio de un modal y la página se refresca, se pierde el estado. Solución: pausar auto-refresh mientras modal abierto.

---

## E07-S03 — Página: Pipeline (kanban de aplicaciones)

**Como** dueño del sistema, **quiero** un tablero kanban con todas mis aplicaciones organizadas por estado, **para que** vea el embudo completo y mueva aplicaciones rápido.

### Acceptance Criteria

- [ ] Página `pages/2_📋_Pipeline.py` con vista kanban: columnas por `ApplicationStatus`.
- [ ] Columnas: `applied` → `screening` → `interview_1` → `interview_n` → `offer` / `rejected` / `ghosted`.
- [ ] Cards compactos por aplicación:
  - Empresa + título.
  - Tiempo en estado actual ("hace 5 días").
  - Indicador visual si `next_action_due` es hoy o pasó.
  - Click abre modal de detalle.
- [ ] Modal de detalle con:
  - Job info completa (título, empresa, link, stack).
  - Cover letter aplicada.
  - Tabs: Notes, Events history (de `application_events`), Contact info.
  - Botones de transición de estado (siguiente paso).
  - Form para añadir nota / actualizar `next_action_due` / actualizar contact info.
- [ ] Filtros laterales:
  - [ ] Por método (web/email/linkedin/referral).
  - [ ] Por mes de aplicación.
  - [ ] Mostrar/ocultar estados terminales (rejected, ghosted, withdrawn).
- [ ] Indicador top: total apps activas, edad media en pipeline, próximas acciones (3 más urgentes).
- [ ] **Drag & drop entre columnas:** opcional; si Streamlit no lo soporta nativamente, botones "Move to next" en cada card.

### Tasks

- [ ] Implementar layout kanban con `st.columns`.
- [ ] Componente `render_application_card(app)`.
- [ ] Modal de detalle con `st.dialog`.
- [ ] Botones de transición invocan `ApplicationRepo.transition_status`.
- [ ] Componente `render_event_timeline(events)` para tab Events.
- [ ] Investigar drag-and-drop: si `streamlit-sortables` u otro componente community soporta, integrar; si no, fallback a botones.

### Estimación: 3h

### Paralelizable con

S02, S04, S05.

### Notas

- **Drag & drop en Streamlit es frágil.** Componentes community existen pero rompen con cada release. Recomendación: empezar con botones; si rinde, considerar drag&drop en E11.
- **`render_event_timeline`** es donde brilla el audit log de E2. Cada cambio de estado, cada nota, cada follow-up — todo trazable.

---

## E07-S04 — Página: Manual Review (tier C)

**Como** dueño del sistema, **quiero** revisar jobs tier C ambiguos (`manual_review`), **para que** decida promover a queue o descartar sin perder oportunidades borderline.

### Acceptance Criteria

- [ ] Página `pages/3_🔍_Manual_Review.py` lista jobs `status='manual_review'`.
- [ ] Cards más detalladas que New Matches (más contexto necesario para decidir):
  - JD completa (collapsible).
  - `score_data` completo en formato leíble (yellow_flags resaltados).
  - Razón principal de "manual_review" (de `score_data.recommendation.reason_short`).
- [ ] Acciones por job:
  - [ ] **Promote to Queue** — transiciona a `status='queued'` (entra al flujo normal de aplicación).
  - [ ] **Re-score** — re-ejecuta scoring con prompt actual + Sonnet 4.6 (variante 7B del Doc A).
  - [ ] **Reject** — transiciona a `status='rejected'` con razón.
- [ ] Filtro: por antigüedad (jobs viejos en review acumulan polvo).
- [ ] Indicador: "X jobs esperan review, Y > 7 días sin decisión".

### Tasks

- [ ] Implementar página similar a S02 pero con cards más densos.
- [ ] Botón "Re-score" invoca `JobScorer` con override de modelo.
- [ ] Mostrar diff entre score original y re-score si difieren > 10 puntos.

### Estimación: 1.5h

### Paralelizable con

S02, S03, S05.

### Notas

- **Re-score con Sonnet** es directo del Doc A variante 7A. Si el nuevo score difiere significativamente, sirve como señal de que el caso es genuinamente ambiguo.
- **Antigüedad como métrica:** jobs en `manual_review` > 7 días son señal de procrastinación. La UI debería empujar a decidir.

---

## E07-S05 — Página: Outreach (contactos reclutadores)

**Como** dueño del sistema, **quiero** gestionar mis contactos de outreach (reclutadores, CTOs target), **para que** ejecute la operación del Documento C desde la UI.

### Acceptance Criteria

- [ ] Página `pages/4_💌_Outreach.py` con tabla de `outreach_contacts`.
- [ ] Filtros:
  - [ ] Status (new/contacted/replied/ghosted/warm).
  - [ ] Market (germany/eu_wide/uk/etc.).
  - [ ] Specialty stack (chips).
  - [ ] Due for follow-up (boolean).
- [ ] Acciones bulk:
  - [ ] Importar CSV (usa `OutreachRepo.bulk_import_from_csv`).
  - [ ] Exportar selección a CSV.
- [ ] Acciones por contacto:
  - [ ] **Mark Contacted** — incrementa contador, actualiza `last_contacted_at`, transiciona a `contacted`.
  - [ ] **Mark Replied** → status `replied`.
  - [ ] **Mark Warm** → status `warm` (lead caliente, prioridad alta).
  - [ ] **Add Note** — modal con textarea.
  - [ ] **Generate Message** — placeholder: "Coming in E9". Por ahora solo abre LinkedIn URL.
- [ ] Indicador top: contactos por status, follow-ups pendientes hoy.

### Tasks

- [ ] Implementar página con tabla editable (`st.data_editor` o tabla custom).
- [ ] Modal de import CSV con preview de primeras 5 filas + confirmación.
- [ ] Acciones bulk con checkboxes.
- [ ] Stub de "Generate Message" (botón presente pero deshabilitado, tooltip "Available in E9").

### Estimación: 1.5h

### Paralelizable con

S02, S03, S04.

### Notas

- **E9 (Outreach Module) traerá la generación de mensajes IA.** Esta página prepara el terreno: visualización + acciones manuales. Cuando E9 cierre, "Generate Message" se activa.
- **`st.data_editor`** permite edición inline de tabla. Útil para ajustar `notes` o `quality_score` sin abrir modal por cada uno.

---

## E07-S06 — Página: Metrics & Analytics

**Como** dueño del sistema, **quiero** ver métricas agregadas del pipeline en una vista, **para que** detecte problemas (caída de tasa de respuesta, fuente rota) sin abrir SQL.

### Acceptance Criteria

- [ ] Página `pages/5_📊_Metrics.py` con secciones:
  - [ ] **Funnel:** ingest → scored → queued → applied → screening → interview → offer. Conversión entre etapas.
  - [ ] **Por fuente:** jobs ingestados, % tier A, jobs aplicados, response rate por fuente.
  - [ ] **Tendencias temporales:** últimas 8 semanas, gráfica de apps/semana, response rate.
  - [ ] **Costos LLM:** total mes, breakdown por purpose (scoring/cover_letter/etc.), tendencia diaria.
  - [ ] **Distribución de tiers:** pie chart o bar chart.
  - [ ] **Salud del sistema:** estado de circuit breakers (de E3-S07), última ingestion exitosa por fuente.
- [ ] Charts con `plotly` o `altair` (Streamlit native support para ambos).
- [ ] Date range selector global aplica a todas las métricas.
- [ ] Export a PDF: botón que genera reporte mensual con `weasyprint` o similar.

### Tasks

- [ ] Implementar página con secciones colapsables.
- [ ] Queries de métricas centralizadas en `dashboard/services/metrics.py` (caché agresivo).
- [ ] Charts con `plotly.express` (más rápido de prototypar que altair).
- [ ] Stub de export PDF (story P2 si rinde).

### Estimación: 2h

### Paralelizable con

S05.

### Notas

- **Caché agresivo crítico aquí.** Las queries de funnel y tendencias son pesadas; sin `@st.cache_data(ttl=300)` cada interacción re-ejecuta y mata UX.
- **`weekly_metrics` materializada de E2-S05** alimenta las tendencias temporales — refresh diario es suficiente.

---

## E07-S07 — Búsqueda full-text + filtros globales

**Como** dueño del sistema, **quiero** una búsqueda global que encuentre jobs y aplicaciones por keyword, **para que** "¿cuándo apliqué a esa empresa con Python AI?" se resuelva en 5 segundos.

### Acceptance Criteria

- [ ] Search bar persistente en sidebar (visible en todas las páginas).
- [ ] Búsqueda full-text contra: `Job.title`, `Job.company`, `Job.description`, `Application.notes`, `OutreachContact.name`, `OutreachContact.company`.
- [ ] Implementación: Postgres `tsvector` + `GIN` index (migration nueva), no LIKE queries.
- [ ] Resultados agrupados por entidad (jobs / applications / contacts), ordenados por relevancia.
- [ ] Click en resultado lleva a la página correspondiente con foco en el item.
- [ ] Búsqueda persistente: el query se mantiene entre páginas hasta que se borra explícitamente.

### Tasks

- [ ] Migration: agregar `tsvector` columna + `GIN` index a `jobs`, `applications`, `outreach_contacts`.
- [ ] Trigger Postgres para auto-poblar `tsvector` en INSERT/UPDATE (o computed column).
- [ ] `SearchRepo` con método `search(query: str, limit: int) -> SearchResults`.
- [ ] Componente `render_search_bar()` en sidebar.
- [ ] Página `pages/6_🔎_Search.py` para resultados expandidos.

### Estimación: 2h

### Notas

- **Postgres tsvector >> LIKE.** Para 1000+ jobs, full-text search nativo es 100x más rápido que `LIKE '%query%'` y soporta stemming (encuentra "running" cuando buscas "run").
- **Triggers vs computed columns:** Postgres 12+ soporta `GENERATED ALWAYS AS (...)` para tsvector. Usa eso, evita triggers manuales.

---

## E07-S08 — Integración con E6 toolkit (assist desde UI)

**Como** dueño del sistema, **quiero** lanzar el toolkit de E6 desde el dashboard sin volver a terminal, **para que** el workflow completo (descubrir → assist → aplicar → registrar) viva en una sola UI.

### Acceptance Criteria

- [ ] Página `pages/7_🛠_Assist.py` que recibe `?job_id=X` query param.
- [ ] Botón "Assist" en cards de New Matches (S02) navega a esta página.
- [ ] Spinner durante generación (~30s) con progress steps:
  1. "Selecting CV variant..."
  2. "Generating cover letter (Opus)..."
  3. "Extracting ATS keywords..."
  4. "Suggesting CV tweaks..."
- [ ] Output:
  - Cover letter: textarea editable + botón "Copy" + "Save edits".
  - CV Tweaks: lista checkable.
  - ATS Keywords: chips con indicador presente/ausente en CV.
  - Variante recomendada con confidence.
- [ ] Botón "Mark Applied" al final con form (método, notes).
- [ ] Costo total de la corrida visible.

### Tasks

- [ ] Página implementada con `assist_application` de E6-S06.
- [ ] Streaming UI: cada paso aparece a medida que completa.
- [ ] Edición de cover letter persiste en `applications.cover_letter_text` cuando se guarda.

### Estimación: 1.5h

### Paralelizable con

S07.

### Notas

- **Streaming progress.** Streamlit no tiene streaming nativo para tareas async largas; usar `st.status()` con context manager actualiza el UI a medida que cada paso completa.
- **Edición + persistencia:** si el usuario edita la cover letter en la UI, esos cambios deben persistir cuando hace "Save" o "Mark Applied". Las ediciones humanas son señal valiosa para futura calibración del prompt.

---

## E07-S09 — Deploy opcional + tests Playwright

**Como** dueño del sistema, **quiero** opcionalmente exponer el dashboard a internet de forma segura y tener smoke tests E2E, **para que** pueda accederlo desde cualquier lugar y la UI no se rompa silenciosamente con cada cambio.

### Acceptance Criteria

- [ ] **Deploy opcional** (P2): Dockerfile específico para dashboard + instrucciones para Fly.io free tier.
- [ ] HTTPS via proxy (Fly.io lo provee automáticamente).
- [ ] Variables de entorno seguras (incluido `dashboard_password`).
- [ ] **Tests Playwright E2E** (P1):
  - Login con credenciales correctas → dashboard.
  - Login con password incorrecto → error.
  - Navegación entre páginas funciona.
  - Búsqueda devuelve resultados.
  - Smoke test del flujo "Mark Applied" desde New Matches.
- [ ] CI corre tests Playwright contra dashboard local levantado en GitHub Actions.

### Tasks

- [ ] Crear `Dockerfile.dashboard` (puede heredar de `Dockerfile` principal).
- [ ] Documentar deploy en `docs/runbook.md` sección "Deploy dashboard a Fly.io".
- [ ] Añadir dependencia `pytest-playwright`.
- [ ] Tests E2E en `tests/e2e/dashboard/`.
- [ ] Workflow CI separado para E2E (más lento, no bloquea PRs).

### Estimación: 2h

### Notas

- **Deploy es opcional.** Local-first sigue siendo válido. El dashboard corre en `localhost:8501` y para uso desde fuera de casa, basta `tailscale` (mejor que exponer a internet).
- **Playwright en Streamlit es delicado.** Streamlit usa websockets dinámicos; los selectores deben ser robustos (data-testid). Empezar con 5 tests críticos, no 50 frágiles.

---

## Definition of Ready para E8

E7 cerrada cuando:

- [ ] Las 9 stories tienen AC ✅.
- [ ] CI verde con tests E2E (al menos los smoke).
- [ ] `streamlit run` levanta dashboard sin errores.
- [ ] Workflow probado E2E desde UI: login → ver match → assist → mark applied → ver en pipeline.
- [ ] Mobile-responsive aceptable (test desde teléfono real).
- [ ] Tag `v0.7.0` creado.

A partir de aquí, **E8 (Scheduling & Automation)** es el cierre del MVP P0 — automatiza el cron y manda el sistema a producción.

---

## Anexo: ¿Por qué Streamlit y no FastAPI + Vue/React?

Tentación: construir API + frontend separados, "más profesional". Razones para resistirla:

1. **Tiempo:** Streamlit te da el dashboard funcional en 1 día. API + frontend = 1 semana mínimo.
2. **Audiencia:** un solo usuario (yo). Multi-tenancy y autenticación robusta no aplican.
3. **Flexibilidad:** Streamlit deja construir prácticamente cualquier UI con Python. Para 95% de casos es suficiente.
4. **Iteración:** cambiar una página es editar Python y guardar. Sin pipeline build.
5. **Limitación honesta:** Streamlit no es para apps web públicas con miles de usuarios. Pero tampoco es nuestro caso.

**Si en el futuro** el dashboard se vuelve portfolio piece y quieres mostrar Flutter chops, queda como story potencial: reescribir frontend en Flutter Web consumiendo API REST (que ya casi tienes con los repos de E2). Eso es ~1 semana de trabajo, justifica solo si rinde el resto del sistema.

---

**Fin Documento K.**
