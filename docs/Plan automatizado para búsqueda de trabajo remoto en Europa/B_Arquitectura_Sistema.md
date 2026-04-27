# Documento B — Arquitectura del Sistema Automatizado de Búsqueda de Empleo

**Nombre del proyecto (sugerido):** `jobhunter-eu` o `lupa` (en español: lupa de búsqueda).

**Status:** Spec arquitectónico para implementación. Diseñado para ejecutarse cada N días (cron) con notificaciones en tiempo real para matches premium. El sistema en sí mismo es un *portfolio piece* — bien documentado, open-source-able, demuestra exactamente las skills que vendes (Python, FastAPI, Docker, AI integration, scraping, dashboards).

**Time-to-MVP estimado:** 3-5 días de trabajo concentrado para versión funcional. 2 semanas para versión pulida con dashboard.

---

## 1. Objetivos y restricciones

### 1.1 Objetivos funcionales (must-have)

1. Ingestar ofertas de múltiples fuentes (APIs, RSS, scraping ligero) en pipeline programado.
2. Filtrar y scorear cada oferta con Claude API según el prompt maestro (Documento A).
3. Persistir estado completo de cada oferta y aplicación en base de datos.
4. Generar borradores de cover letters y CV-tweaks asistidos por IA para tier A/B.
5. Llevar tracker accesible (dashboard web) con estado de cada aplicación.
6. Notificar al usuario en tiempo real cuando aparezcan matches A-tier (fit_score ≥ 80).
7. Generar métricas semanales: tasa de respuesta, conversión, fuentes más productivas.

### 1.2 Objetivos no-funcionales

- **Costo bajo:** <$10 USD/mes en infraestructura + API. Idealmente $0–5.
- **Bajo mantenimiento:** corre desatendido durante una semana sin intervención.
- **Modularidad:** cada fuente de scraping y cada notificador deben ser plugins reemplazables.
- **Privacidad:** ningún dato sensible (CV, contactos) en repos públicos. Secrets en variables de entorno.
- **Idempotente:** correr dos veces no duplica registros ni envía dos notificaciones por la misma oferta.

### 1.3 No-objetivos (explícitamente fuera de scope)

- ❌ Auto-apply ciego a vacantes (counter-productivo para roles senior).
- ❌ Web scraping agresivo de LinkedIn/Indeed (riesgo de ban + violación TOS).
- ❌ Multi-usuario / SaaS — esto es para uso personal.
- ❌ Mobile app (el dashboard web responsive es suficiente).

---

## 2. Vista de alto nivel

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SCHEDULER (cron / GH Actions)                   │
│                          corre cada 8-12h                            │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│ INGEST LAYER                                                          │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────┐   │
│   │ Arbeitnow   │ │ RemoteOK    │ │ WeWorkRemote│ │ LinkedIn RSS │   │
│   │ (REST API)  │ │ (REST API)  │ │ (RSS)       │ │ (saved feeds)│   │
│   └─────────────┘ └─────────────┘ └─────────────┘ └──────────────┘   │
│                                                                       │
│   Plugin interface: BaseSource.fetch() -> List[RawJob]                │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
                    ┌────────────────┐
                    │ Dedup + Hash   │  url + title + company hash
                    └────────┬───────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ SCORING LAYER                                                         │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │  Claude Haiku 4.5 → prompt maestro → JSON estructurado       │   │
│   │  (con retry exponencial + circuit breaker)                   │   │
│   └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
                    ┌────────────────┐
                    │   PostgreSQL   │
                    │  (jobs, apps)  │
                    └────┬─────────┬─┘
                         │         │
            ┌────────────┘         └────────────┐
            ▼                                    ▼
┌────────────────────────┐         ┌────────────────────────────────┐
│ NOTIFY (tier A only)   │         │ DASHBOARD (FastAPI + Streamlit │
│   Telegram bot         │         │ o Flutter Web)                  │
│   + email digest weekly│         │   - lista filtable             │
└────────────────────────┘         │   - kanban de aplicaciones     │
                                   │   - métricas                    │
                                   └────────────────────────────────┘
                             ▲
                             │
                    ┌────────┴───────────────────────────┐
                    │ APPLICATION ASSIST (on-demand)     │
                    │   - cover letter generator         │
                    │     (Claude Opus 4.7)              │
                    │   - CV variant selector            │
                    │   - response tracker (Gmail watch) │
                    └────────────────────────────────────┘
```

---

## 3. Stack técnico

| Componente | Tecnología | Justificación |
|---|---|---|
| Lenguaje principal | Python 3.12+ | Tu stack core; pleno control |
| Web framework | FastAPI | Lo conoces, async-first, ideal para APIs internas |
| ORM / DB layer | SQLAlchemy 2.x + Alembic | Tipado, migraciones automáticas |
| Database | PostgreSQL 16 | JSONB para campos flexibles, búsqueda full-text |
| Scraping HTTP | `httpx` (async) | Más rápido que requests para múltiples fuentes |
| Scraping JS-heavy | Playwright (headless) | Solo para fuentes que lo requieran |
| LLM client | `anthropic` Python SDK | Oficial, soporta streaming |
| Scheduling | GitHub Actions (cron) | Gratis para repos personales, sin server propio |
| Alternativa scheduling | Apache Airflow | Si prefieres más control y ya lo conoces |
| Dashboard | Streamlit | MVP en horas; alternativa: Flutter Web (luce tu skill) |
| Notificaciones | python-telegram-bot + smtplib (Gmail SMTP) | Telegram para tiempo real, email para digest |
| Secrets management | `.env` + python-dotenv local; GitHub Secrets en Actions | Simple, sin AWS Secrets Manager |
| Containerization | Docker + docker-compose | Para correr local consistente |
| Hosting (si necesario) | Fly.io / Railway free tier | Solo si necesitas dashboard 24/7 |
| Testing | pytest + pytest-asyncio | Standard |
| Linting | ruff + black + mypy | Standard moderno |

---

## 4. Modelo de datos

### 4.1 Tablas principales

```sql
-- Ofertas crudas ingeridas
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(50) NOT NULL,          -- 'arbeitnow', 'remoteok', etc.
    source_id       VARCHAR(255),                  -- ID de la fuente, si aplica
    url             TEXT NOT NULL,
    url_hash        VARCHAR(64) UNIQUE NOT NULL,   -- sha256 para dedup
    
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location_raw    TEXT,
    description     TEXT NOT NULL,
    posted_at       TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    raw_payload     JSONB,                          -- todo lo que la fuente dio
    
    -- Scoring (poblado por SCORING LAYER)
    scored_at       TIMESTAMPTZ,
    score_model     VARCHAR(50),                    -- 'claude-haiku-4-5-20251001'
    score_version   VARCHAR(20),                    -- versión del prompt maestro
    fit_score       INT,
    tier            VARCHAR(10),                    -- 'A', 'B', 'C', 'REJECT'
    score_data      JSONB,                          -- el JSON completo del prompt
    
    status          VARCHAR(30) DEFAULT 'new',
                    -- new | scored | queued | applied | manual_review | rejected | archived
    
    INDEX idx_jobs_status (status),
    INDEX idx_jobs_tier (tier),
    INDEX idx_jobs_scraped_at (scraped_at DESC),
    INDEX idx_jobs_company (company)
);

-- Aplicaciones enviadas
CREATE TABLE applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID NOT NULL REFERENCES jobs(id),
    
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    application_method  VARCHAR(50),                -- 'web_form', 'email', 'linkedin', 'referral'
    cv_variant          VARCHAR(50),                -- 'ai_python', 'flutter', 'fullstack'
    
    cover_letter_text   TEXT,
    cover_letter_model  VARCHAR(50),                -- modelo Claude usado
    
    contact_name        TEXT,
    contact_email       TEXT,
    contact_linkedin    TEXT,
    
    status              VARCHAR(30) DEFAULT 'applied',
                        -- applied | screening | interview_1 | interview_n | offer | rejected | ghosted | withdrawn
    status_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    next_action         TEXT,
    next_action_due     DATE,
    
    salary_offered_min  INT,
    salary_offered_max  INT,
    salary_currency     VARCHAR(10),
    contract_type       VARCHAR(20),                -- 'B2B', 'EOR', 'employee'
    
    notes               TEXT,
    
    INDEX idx_apps_status (status),
    INDEX idx_apps_next_action_due (next_action_due) WHERE status NOT IN ('rejected', 'ghosted', 'withdrawn', 'offer')
);

-- Historial de cambios de estado (audit log)
CREATE TABLE application_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES applications(id),
    event_type      VARCHAR(50) NOT NULL,           -- 'status_change', 'follow_up_sent', 'interview_scheduled'
    event_data      JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    INDEX idx_events_app (application_id, occurred_at DESC)
);

-- Outreach a reclutadores (relacionado con Documento C)
CREATE TABLE outreach_contacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    company             TEXT,
    role                TEXT,                       -- 'Tech Recruiter', 'CTO', etc.
    linkedin_url        TEXT,
    email               TEXT,
    
    market              VARCHAR(50),                -- 'germany', 'eu_wide', 'uk', 'netherlands'
    specialty_stack     VARCHAR(100),               -- 'python_ai', 'flutter', 'fullstack'
    quality_score       INT,                        -- 1-5, manual o IA-asistido
    
    first_contacted_at  TIMESTAMPTZ,
    last_contacted_at   TIMESTAMPTZ,
    contact_count       INT DEFAULT 0,
    
    status              VARCHAR(30) DEFAULT 'new',  -- new | contacted | replied | ghosted | warm
    notes               TEXT
);

-- Métricas pre-agregadas (opcional, para dashboard rápido)
CREATE MATERIALIZED VIEW weekly_metrics AS
SELECT
    date_trunc('week', applied_at) AS week,
    COUNT(*) AS apps_sent,
    COUNT(*) FILTER (WHERE status != 'applied') AS apps_with_response,
    COUNT(*) FILTER (WHERE status IN ('interview_1', 'interview_n', 'offer')) AS interviews,
    COUNT(*) FILTER (WHERE status = 'offer') AS offers,
    AVG(salary_offered_max) FILTER (WHERE status = 'offer') AS avg_offer_max
FROM applications
GROUP BY 1
ORDER BY 1 DESC;
```

### 4.2 Estados y transiciones

```
JOB lifecycle:
new → scored → {queued | manual_review | rejected | archived}
queued → applied (se crea registro en applications)

APPLICATION lifecycle:
applied → screening → interview_1 → interview_n → {offer | rejected}
                  ↘ rejected
                  ↘ ghosted (auto después de 21 días sin respuesta)
                  ↘ withdrawn (manual)
```

---

## 5. Estructura de directorios

```
jobhunter-eu/
├── README.md
├── pyproject.toml                  # poetry o uv
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .github/
│   └── workflows/
│       ├── ingest.yml              # cron: cada 8h
│       ├── score.yml               # cron: cada 8h, después de ingest
│       ├── digest.yml              # cron: domingos 18:00 COT
│       └── ci.yml                  # tests on PR
│
├── alembic/                        # migrations
│
├── src/jobhunter/
│   ├── __init__.py
│   ├── config.py                   # pydantic-settings
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   │
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseSource ABC
│   │   ├── arbeitnow.py
│   │   ├── remoteok.py
│   │   ├── wwr.py                  # WeWorkRemotely
│   │   ├── linkedin_rss.py
│   │   ├── honeypot.py
│   │   └── arbeitnow.py
│   │
│   ├── scoring/
│   │   ├── prompt.py               # carga el Documento A
│   │   ├── client.py               # wrapper sobre anthropic SDK
│   │   └── pipeline.py             # orquesta: fetch unscored → score → save
│   │
│   ├── application/
│   │   ├── cover_letter.py         # generación con Claude Opus 4.7
│   │   ├── cv_variants/
│   │   │   ├── ai_python.md
│   │   │   ├── flutter.md
│   │   │   └── fullstack.md
│   │   └── tracker.py              # CRUD de applications
│   │
│   ├── notify/
│   │   ├── telegram.py
│   │   ├── email_digest.py
│   │   └── templates/
│   │
│   ├── dashboard/
│   │   ├── streamlit_app.py        # punto de entrada del dashboard
│   │   └── pages/
│   │       ├── 1_New_Matches.py
│   │       ├── 2_Pipeline.py
│   │       ├── 3_Metrics.py
│   │       └── 4_Outreach.py
│   │
│   ├── outreach/
│   │   ├── recruiter_finder.py     # ver Documento C
│   │   └── message_gen.py
│   │
│   └── cli.py                      # typer/click: comandos manuales
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── sample_jobs.json
│
└── docs/
    ├── A_prompt_maestro.md         # symlink al Documento A
    ├── B_arquitectura.md           # este documento
    └── C_outreach_playbook.md
```

---

## 6. Flujos clave

### 6.1 Flujo de ingestion + scoring (corre vía cron cada 8-12h)

```python
# pseudocódigo
async def ingest_and_score():
    sources = [ArbeitnowSource(), RemoteOKSource(), WWRSource(), ...]
    
    for src in sources:
        try:
            raw_jobs = await src.fetch(since=last_run_timestamp)
            for raw in raw_jobs:
                if not job_exists(url_hash=hash(raw.url)):
                    save_job(raw, status="new")
        except Exception as e:
            log_error(src, e)
            continue
    
    # Scoring batch
    new_jobs = get_jobs(status="new", limit=100)
    for job in new_jobs:
        try:
            result = await score_job(job)              # Claude Haiku
            save_score(job, result)
            
            if result["tier"] == "A":
                notify_telegram(job, result)
                set_status(job, "queued")
            elif result["tier"] == "B":
                set_status(job, "queued")
            elif result["tier"] == "C":
                set_status(job, "manual_review")
            else:
                set_status(job, "rejected")
        except Exception as e:
            log_error(job, e)
            continue
```

### 6.2 Flujo de aplicación (semi-manual, asistido por IA)

```python
def assist_application(job_id):
    job = get_job(job_id)
    score = job.score_data
    
    # 1. Sugerir variante de CV
    cv_variant = recommend_cv_variant(score)        # 'ai_python' | 'flutter' | 'fullstack'
    
    # 2. Generar cover letter con Opus 4.7
    cover_letter = generate_cover_letter(
        job_description=job.description,
        cv_variant_path=f"cv_variants/{cv_variant}.md",
        angle=score["recommendation"]["cover_letter_angle"],
        candidate_profile=CANDIDATE_PROFILE
    )
    
    # 3. Sugerir tweaks al CV (qué bullets reordenar/destacar)
    cv_tweaks = suggest_cv_tweaks(job, cv_variant)
    
    # 4. Detectar si es ATS conocido y predecir keywords
    ats_keywords = extract_ats_keywords(job.description)
    
    # 5. Devolver paquete listo para revisión humana
    return {
        "cv_variant": cv_variant,
        "cover_letter_draft": cover_letter,
        "cv_tweaks": cv_tweaks,
        "ats_keywords": ats_keywords,
        "estimated_time_to_apply": "5-8 min"
    }

# Tras aplicar manualmente:
def mark_applied(job_id, **kwargs):
    create_application(job_id=job_id, **kwargs)
    set_status(job_id, "applied")
    schedule_followup_check(job_id, days=7)
```

### 6.3 Flujo de follow-up

```python
def check_pending_followups():
    """Corre diariamente. Identifica aplicaciones que necesitan acción."""
    
    # Auto-marca como ghosted: 21+ días sin cambio de estado
    apps_ghosted = get_applications(
        status="applied",
        last_change_before=date.today() - timedelta(days=21)
    )
    for app in apps_ghosted:
        update_status(app, "ghosted")
    
    # Sugiere follow-up: 7 días sin respuesta
    apps_to_followup = get_applications(
        status="applied",
        last_change_between=(date.today() - timedelta(days=10), date.today() - timedelta(days=7))
    )
    for app in apps_to_followup:
        notify_telegram(f"💡 Follow-up sugerido: {app.job.company}")
```

---

## 7. Manejo de costos y rate limits

### 7.1 Estimación de costos mensuales

| Concepto | Volumen est. | Costo unit. | Total/mes |
|---|---|---|---|
| Claude Haiku 4.5 (scoring) | ~800 ofertas/mes | ~$0.002 | ~$1.60 |
| Claude Opus 4.7 (cover letters) | ~30/mes | ~$0.10 | ~$3.00 |
| Claude Sonnet 4.6 (re-scoring tier A) | ~50/mes | ~$0.015 | ~$0.75 |
| PostgreSQL (Neon free tier o local) | 1 GB | $0 | $0 |
| GitHub Actions (cron) | <2000 min/mes | $0 (free tier) | $0 |
| Hosting dashboard (Fly.io free) | 1 instancia | $0 | $0 |
| **Total estimado** | | | **~$5–8 USD/mes** |

Consulta `https://docs.claude.com` para precios actualizados de la API.

### 7.2 Rate limits a respetar

- **Claude API:** Tier 1 default es suficiente. No hace falta paralelizar más de 5 requests/segundo.
- **Arbeitnow / RemoteOK:** APIs públicas, sin rate limit oficial pero respeta `User-Agent` claro y máximo 1 request cada 2-3 segundos.
- **LinkedIn:** **Nunca** scrapeo programático — solo RSS de búsquedas guardadas o consumo manual.
- **Honeypot:** No requiere scraping (las empresas te contactan). Solo perfil bien optimizado.

### 7.3 Resilencia

- **Retry con exponential backoff** en todas las llamadas externas (HTTP, Claude API).
- **Circuit breaker** por fuente: si una fuente falla 3 veces seguidas, pausarla 24h.
- **Idempotencia:** `url_hash` único garantiza no duplicar.
- **Logs estructurados** (JSON) — `structlog`.
- **Alertas** en Telegram cuando una fuente lleva 24h sin entregar nada (señal de scraping roto).

---

## 8. Roadmap de implementación

### Sprint 0 — Setup (medio día)
- [ ] Crear repo, estructura inicial, `.env.example`, Docker compose con Postgres local.
- [ ] Configurar Anthropic API key, Telegram bot.
- [ ] Migrations iniciales con Alembic.

### Sprint 1 — Pipeline mínimo viable (1-2 días)
- [ ] Implementar `BaseSource` + Arbeitnow + RemoteOK (los más fáciles, APIs limpias).
- [ ] Implementar `ScoringPipeline` con Documento A.
- [ ] CLI: `jobhunter ingest`, `jobhunter score`, `jobhunter list-tier-a`.
- [ ] Test end-to-end: 50 ofertas reales pasan por el pipeline correctamente.

### Sprint 2 — Notificación + Dashboard básico (1 día)
- [ ] Telegram bot funcional para alertas tier A.
- [ ] Streamlit dashboard básico: lista filtrable, kanban de aplicaciones.
- [ ] Comando `jobhunter assist <job_id>` que genera cover letter y tweaks.

### Sprint 3 — Cron + más fuentes (1 día)
- [ ] GitHub Actions con cron cada 8h.
- [ ] Añadir WeWorkRemotely RSS, JOIN.com, GermanTechJobs.
- [ ] Email digest semanal.

### Sprint 4 — Refinamiento (continuo)
- [ ] Integrar Gmail API para detectar respuestas automáticamente (→ actualizar status).
- [ ] Métricas más ricas en dashboard.
- [ ] Outreach module (ver Documento C).
- [ ] Re-prompt tuning basado en data real.

### Stretch goals (si rinde)
- Dashboard reescrito en Flutter Web (queda como portfolio piece extra).
- Integración con Notion como UI alternativa.
- Multi-perfil: si en el futuro quieres ayudar a otros con el mismo sistema.

---

## 9. Decisiones arquitectónicas notables

**¿Por qué GitHub Actions y no Airflow self-hosted?**
GH Actions es gratis, sin server que mantener, y para ~5 jobs cron/día sobra. Si en el futuro necesitas DAGs complejos con muchas dependencias, migrar a Airflow es trivial (ya conoces ambos según tu CV).

**¿Por qué Streamlit y no Flutter Web para el dashboard?**
Streamlit te da el dashboard funcional en 4 horas. Flutter Web te tomaría 2-3 días para algo equivalente. Recomendación: empieza con Streamlit, y cuando el sistema sea estable, *opcionalmente* reemplaza el dashboard con Flutter Web — ese mismo trabajo se vuelve evidencia adicional para tu CV de Flutter.

**¿Por qué no usar un LLM open-source local?**
Coste-beneficio. La calidad de scoring y cover letters de Claude vs Llama/Mistral local es suficientemente superior para justificar los $5-8/mes, especialmente cuando el output afecta directamente tu pipeline de oportunidades.

**¿Por qué no auto-apply?**
Para roles senior $7k+/mes en EU, la calidad del touch importa. Auto-apply ciego destruye conversión (data: <1% response rate vs ~12% con cover letter cuidada). El sistema te ahorra el 90% del trabajo (descubrimiento, scoring, draft) pero conserva el 10% que más impacto tiene (la firma humana).

**¿Cómo manejar cambios de status sin abrir el dashboard cada vez?**
Bot de Telegram con comandos: `/status <job_id> screening`, `/note <job_id> "Llamada el viernes"`. Esto convierte el seguimiento en algo natural durante el día.

---

## 10. Métricas de éxito del sistema

A las 8 semanas de operación, deberíamos ver:

| Métrica | Target |
|---|---|
| Ofertas ingeridas/semana | 100–200 |
| Ofertas tier A/semana | 5–15 |
| Tasa de aplicación (A+B aplicados / A+B encontrados) | ≥ 70% |
| Tasa de respuesta (cualquier respuesta / aplicaciones) | ≥ 10% |
| Conversión a entrevista | ≥ 20% de respuestas |
| Tiempo desde ingest a aplicación (mediana) | < 48h |
| Costo total | < $10/mes |

Si la **tasa de respuesta < 5%** después de 30 aplicaciones tier A: problema de CV o targeting (no del sistema).
Si **0 ofertas tier A en una semana**: problema de fuentes o filtros muy estrictos.

---

## 11. Seguridad y privacidad

- API keys, tokens y CV en `.env` local + GitHub Secrets para Actions.
- Repo **privado** mientras tenga datos personales. Si se publica como portfolio, scrub con BFG Repo-Cleaner.
- Database backups semanales (`pg_dump` → ubicación segura).
- No commitear `.env`, `*.db`, `cv_variants/*` con datos personales reales (usar `.gitignore`).
- Si se añade integración Gmail: usar OAuth con scope mínimo (`gmail.readonly`).

---

## 12. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Scraping de una fuente se rompe | Alta | Bajo | Plugin per source; alerta automática; el resto sigue |
| Claude API caída | Baja | Medio | Retry + queue local; reintentar al recuperar |
| LinkedIn detecta scraping y banea | Media | Medio | NO scrapeo programático; solo RSS y manual |
| Ofertas spam pasan el filtro | Media | Bajo | Few-shot examples + revisión semanal de filtros |
| Costo Claude se dispara | Baja | Bajo | Budget alert en Anthropic console; default a Haiku |
| Pierdes follow-ups por bug | Media | Alto | Tests sobre `check_pending_followups`; redundancia con calendario manual |

---

**Fin Documento B.**
