# Documento R — Backlog Nivel 2: Descomposición de E14 (Onboarding Automation & Profile Generation)

**Épica origen:** E14 — Onboarding Automation & Profile Generation (épica
nueva, posterior a E12 y E13).
**Tamaño épica:** L (4-6 días).
**Total stories:** 11.
**Estimación total:** 23–25 horas (4-5 sesiones de medio día).

**Convenciones:** mismas que documentos E–Q. ID `E14-S##`, formato user
story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E14 es una **épica nueva** que cubre una funcionalidad no contemplada en
el plan original: **el sistema debe ser capaz de configurarse a sí mismo
a partir del CV maestro del usuario**. Hasta hoy, el operador debe rellenar
manualmente `prompts/candidate_profile.yaml` y crear los archivos en
`.local/cv_variants/*.md` siguiendo plantillas. Esto es exactamente el
trabajo manual que el sistema dice automatizar.

E14 introduce un flujo de onboarding web (`pages/0_🎯_Onboarding.py`) y
CLI alternativo (`profile bootstrap`) donde el usuario sube su CV en PDF/
MD/DOCX, la IA extrae datos estructurados, y un wizard de varios pasos
guía la creación del perfil + variants + rango salarial — todo persistido
en la **base de datos**, no en archivos.

**Cambio arquitectónico mayor:** el perfil del candidato y sus variantes
de CV pasan de **archivos en disco a entidades de primera clase en BD**.
Esto resuelve la deuda técnica heredada (perfil duplicado entre
`prompts/scoring/v1.md` y `prompts/candidate_profile.yaml`), habilita
audit trail vía `audit_log` (E13-S05), versionado histórico, y multi-
profile sin re-inventar la rueda.

### Decisiones técnicas clave (consolidadas con el usuario)

1. **Schema híbrido (Eje A3):** campos queryables como columnas Postgres,
   listas como `TEXT[]` nativos, mapas/configs flexibles como `JSONB`.
   Tabla de history para versionado.
2. **Multi-profile desde día 1 (Eje B2):** la tabla `candidate_profiles`
   permite múltiples rows con `is_active=true`. El scorer scorea cada job
   contra cada perfil activo y persiste el resultado por perfil. Costo
   runtime escala linealmente con `count(perfiles activos)`. UI advierte
   si hay más de 3 activos por costo.
3. **Soft gating (Eje C):** sin perfil activo, el dashboard muestra banner
   persistente "Configura tu perfil para empezar" pero NO bloquea
   navegación. Permite explorar el sistema antes de invertir 15 min en
   el wizard.
4. **Migración one-shot + archive (Eje D1):** el primer `alembic upgrade
   head` post-E14 detecta `prompts/candidate_profile.yaml` y `.local/
   cv_variants/*.md` existentes, los carga a BD, mueve los originales a
   `prompts/_legacy/{timestamp}/`. Si no existen (deploy nuevo), no-op.
5. **Sin cifrado de PII en BD (Eje E1):** disk encryption EBS (`DEPLOY_AWS`
   §7) + auth dashboard cubren. Si el sistema se abre a multi-usuario en
   futuro, añadir cifrado de campos PII (~2h, cambio local a `crypto.py`).
6. **Variants user-defined (no hardcoded):** la cantidad y nombres de los
   CV variants los define el usuario. `ai_python`, `flutter`, `fullstack`
   son sólo defaults sugeridos en el wizard. Un usuario puede tener
   `python_backend`, `translator_es`, `ai_agent_consultant`, etc. El
   `variant_selector` se refactoriza de "if/else hardcoded" a "match por
   metadata + fallback LLM".
7. **Resume parsing con Opus, generación con Sonnet:** Opus para extraer
   estructura desde PDF desordenado (~$0.10 one-shot); Sonnet para generar
   variants + perfil + salary (~$0.06 total). Total bootstrap: ~$0.20 por
   ejecución completa.
8. **Wizard reutilizable como edit screen:** la misma página
   `0_🎯_Onboarding.py` sirve como "first-run" y como "editar perfil
   existente". Pre-llena los pasos con datos actuales si ya hay perfil,
   permite saltar pasos no-secuencialmente.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E14-S01 | Schema BD: `candidate_profiles` + history + `cv_variants` + experiencias | 2.5h | E2 cerrada | — |
| E14-S02 | `ResumeIngestor` (PDF/MD/DOCX → texto + LLM Opus → `ResumeData`) | 2.5h | E4 cerrada | con S03 |
| E14-S03 | `ProfileGenerator` (`ResumeData` + inputs → INSERT en `candidate_profiles`) | 2h | S01, S02 | con S02 |
| E14-S04 | `CVVariantGenerator` (LLM Sonnet × N → INSERT en `cv_variants`) | 2.5h | S01, S02 | con S05 |
| E14-S05 | `SalaryProposer` (LLM con baseline 2026 + hooks para datos reales) | 1.5h | S02 | con S04 |
| E14-S06 | Refactor `variant_selector` para variants arbitrarias (heurística + LLM fallback) | 1.5h | S01 | con S04 |
| E14-S07 | Refactor cross-épica: scoring prompt, outreach, application/ leen perfil de DB | 3h | S01, S06 | — |
| E14-S08 | Wizard dashboard `pages/0_🎯_Onboarding.py` (7 pasos, edit mode, soft gating) | 4h | S03, S04, S05 | — |
| E14-S09 | CLI `profile bootstrap --resume X [--interactive]` (alternativo para power users) | 1.5h | S02–S05 | con S08 |
| E14-S10 | Migration one-shot: yaml + markdowns existentes → BD; archivar legacy | 1h | S07 | — |
| E14-S11 | Tests E2E + Playwright del wizard + actualización docs (HUMAN_SETUP, CLAUDE, ARCHITECTURE) | 2h | S08, S09 | — |

### Camino crítico

```
E2,E4 ─→ S01 ─→ ┬─→ S02 ─→ ┬─→ S03 ─┐
                │          │         │
                │          ├─→ S04 ──┼─→ S08 ─┐
                │          ├─→ S05 ──┘        ├─→ S11
                │          │                  │
                └──→ S06 ──┴─→ S07 ───────────┴─→ S09
                                              │
                                              S10
```

**Tiempo serial:** ~24h. **Con paralelización (S02+S03 juntos, S04+S05+S06
juntos):** ~16h.

### Definition of Done de la épica

```bash
# 1. Bootstrap web (UX principal)
streamlit run src/jobhunter/dashboard/streamlit_app.py
# → Sin perfil activo: banner "Configura tu perfil"
# → Click → wizard de 7 pasos: upload resume → revisar → contexto →
#   career angle → salary → variants → confirm save
# → Perfil + variants insertados en BD; banner desaparece

# 2. Bootstrap CLI (alternativo)
uv run python -m jobhunter profile bootstrap --resume ./CV_Master.pdf --interactive
# → Mismo resultado, terminal-based para power users

# 3. Multi-profile
uv run python -m jobhunter profile list
# → Lista perfiles activos con id, name, primary_stack, active variants

uv run python -m jobhunter profile activate <profile_id>  # múltiples activos OK

# 4. Variants user-defined
uv run python -m jobhunter profile variants list <profile_id>
# → ai_python_engineer, translator_es, ai_agent_consultant, ...

# 5. Edit mode
# Dashboard → Onboarding page con perfil existente: pre-lleno, editable,
# salta entre pasos no-secuencialmente

# 6. Audit
uv run python -m jobhunter audit query --event profile_change --since "30 days ago"
# (depende de E13-S05 cerrada)

# 7. Migración legacy (si hay yaml previo)
ls prompts/_legacy/   # contiene snapshot del yaml + markdowns
psql -c "SELECT name, primary_stack FROM candidate_profiles"
```

---

## E14-S01 — Schema BD: `candidate_profiles` + history + `cv_variants`

**Como** dueño del sistema, **quiero** persistir el perfil del candidato y
sus variants de CV en Postgres con schema híbrido y versionado, **para que**
el yaml + markdowns dejen de ser fuente de verdad y la información del
usuario sea entidad de primera clase en la BD.

### Acceptance Criteria

- [ ] Migration Alembic crea las 4 tablas siguientes:

  ```sql
  CREATE TABLE candidate_profiles (
      id UUID PK DEFAULT gen_random_uuid(),
      name VARCHAR(100) NOT NULL,           -- "Python AI Senior", "Flutter Mobile"
      is_active BOOLEAN DEFAULT TRUE,
      seniority VARCHAR(50),
      years_experience INT,
      country VARCHAR(50),
      work_authorization TEXT,
      timezone_home VARCHAR(50),            -- "UTC-5"
      overlap_max_hours_cet INT,
      preferred_overlap_cet INT,
      primary_stack TEXT[],
      secondary_stack TEXT[],
      domains TEXT[],
      languages JSONB,                      -- {"english": "fluent", ...}
      compensation JSONB,                   -- {floor_usd_month, target_usd_month, ...}
      contract_preferences TEXT[],
      hard_blockers TEXT[],
      soft_negatives TEXT[],
      positive_signals TEXT[],
      payment_methods_ok TEXT[],
      notes TEXT,
      created_at TIMESTAMPTZ DEFAULT now(),
      updated_at TIMESTAMPTZ DEFAULT now()
  );

  CREATE TABLE candidate_profile_history (
      id UUID PK,
      profile_id UUID FK REFERENCES candidate_profiles(id) ON DELETE CASCADE,
      snapshot JSONB NOT NULL,              -- copia completa pre-cambio
      changed_at TIMESTAMPTZ DEFAULT now(),
      changed_by VARCHAR(100),              -- "user", "wizard", "cli"
      change_reason TEXT
  );

  CREATE TABLE cv_variants (
      id UUID PK DEFAULT gen_random_uuid(),
      profile_id UUID FK REFERENCES candidate_profiles(id) ON DELETE CASCADE,
      name VARCHAR(50) NOT NULL,            -- "ai_python_engineer", user-defined
      display_name VARCHAR(100),            -- "AI Python Engineer" human-friendly
      target_role_keywords TEXT[],          -- ["python", "ml engineer", "ai"]
      target_stack TEXT[],
      target_seniority VARCHAR(50),
      summary TEXT,
      skills TEXT[],
      raw_markdown TEXT,                    -- regenerable, útil para diff/export
      created_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ,
      UNIQUE(profile_id, name)
  );

  CREATE TABLE cv_variant_experiences (
      id UUID PK,
      cv_variant_id UUID FK REFERENCES cv_variants(id) ON DELETE CASCADE,
      role VARCHAR(200),
      company VARCHAR(200),
      start_date DATE,
      end_date DATE,                        -- NULL = current
      bullets TEXT[],
      sort_order INT
  );
  ```

- [ ] Índices: `(is_active)` parcial sobre `candidate_profiles`,
  `(profile_id)` sobre `cv_variants`, `(cv_variant_id, sort_order)` sobre
  `cv_variant_experiences`, `(profile_id, changed_at DESC)` sobre history.
- [ ] Trigger BEFORE UPDATE en `candidate_profiles` que copia el row
  pre-cambio a `candidate_profile_history` automáticamente (con
  `change_reason = NEW.notes` o NULL).
- [ ] Modelos SQLAlchemy correspondientes en `db/models.py`:
  `CandidateProfile`, `CandidateProfileHistory`, `CVVariant`,
  `CVVariantExperience`. Relationships configuradas (cascade delete,
  back_populates).
- [ ] Repos en `db/repos/`:
  - `CandidateProfileRepo` con `list_active`, `get_active_by_id`,
    `create`, `update_with_history`, `deactivate`, `list_history`.
  - `CVVariantRepo` con `list_by_profile`, `get_by_name`,
    `create_with_experiences`, `update_markdown`.
- [ ] Tests integración: CRUD básico, trigger de history dispara, cascade
  delete funciona, multi-profile activos coexisten sin conflicto.

### Tasks

- [ ] Migration Alembic con las 4 tablas + índices + trigger.
- [ ] Modelos SQLAlchemy.
- [ ] Repos con tipos correctos para mypy strict.
- [ ] Tests integración (`tests/integration/test_candidate_profile_repo.py`).

### Estimación: 2.5h

### Notas

- **Trigger de history en SQL es preferible a hacerlo en Python**: garantiza
  que cualquier UPDATE — incluso uno hecho directamente con `psql` — quede
  trazado. Para `INSERT` no aplica (la versión inicial vive en el row
  mismo).
- **`is_active` permite múltiples TRUE simultáneos.** El usuario decide
  cuántos perfiles tiene corriendo a la vez. La UI advierte si activa más
  de 3 por costo.

---

## E14-S02 — `ResumeIngestor`: parser de CV con LLM

**Como** dueño del sistema, **quiero** un servicio que tome un archivo de
CV (PDF, Markdown o DOCX) y devuelva los datos estructurados, **para que**
los generadores downstream tengan input estructurado en lugar de texto
crudo.

### Acceptance Criteria

- [ ] `src/jobhunter/onboarding/resume_ingestor.py` con:
  - `async ingest_resume(file_bytes: bytes, mime_type: str) -> ResumeData`.
- [ ] Soporta MIME types: `application/pdf`, `text/markdown`, `text/plain`,
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (DOCX).
- [ ] **Extracción de texto**:
  - PDF: `pypdfium2` (más rápido y simple que pymupdf, suficiente para CVs típicos).
  - DOCX: `python-docx`.
  - MD/TXT: lectura directa.
- [ ] **Parser LLM** (`claude-opus-4-7`): recibe el texto extraído + prompt
  versionado en `prompts/onboarding/resume_parser/v1.md`, devuelve JSON
  parseable a `ResumeData`.
- [ ] `ResumeData` (Pydantic):
  ```python
  class ResumeData(BaseModel):
      name: str
      email: str | None
      phone: str | None
      location_raw: str | None
      summary: str | None
      experiences: list[ParsedExperience]   # role, company, dates, bullets
      educations: list[ParsedEducation]
      skills: list[str]
      languages: list[str]
      detected_seniority: str | None        # "junior" / "mid" / "senior" / "staff"
      detected_years_experience: int | None
      detected_primary_stack: list[str]     # las 5-7 más mencionadas
      raw_text: str                         # para debug
  ```
- [ ] Validación post-LLM: si `experiences` está vacío o `name` falta, raise
  `ResumeIngestionError` con `raw_text` y `raw_response` para debug.
- [ ] Costo registrado en `llm_calls` con `purpose='resume_parsing'`.
- [ ] Tests con fixtures de CVs reales sanitizados (PDF de un perfil ficticio
  + MD + DOCX equivalentes en `tests/fixtures/resumes/`).

### Tasks

- [ ] Añadir deps: `pypdfium2`, `python-docx`.
- [ ] Crear `src/jobhunter/onboarding/__init__.py` y `resume_ingestor.py`.
- [ ] Prompt en `prompts/onboarding/resume_parser/v1.md`.
- [ ] Pydantic models.
- [ ] Tests con 3 fixtures (PDF, MD, DOCX).

### Estimación: 2.5h

### Notas

- **Por qué Opus aquí.** Resume parsing tolera ruido y formatos raros. Opus
  produce mejor extracción que Sonnet en CVs con tablas, columnas, fuentes
  raras. Costo: ~$0.10 por CV one-shot, justificado.
- **Sanitización de fixtures.** Los CVs de ejemplo deben tener nombres y
  empresas ficticias (no datos reales del usuario). Generar con prompt:
  "Crea un CV ficticio realista de un Python senior con 8 años de
  experiencia".

---

## E14-S03 — `ProfileGenerator`: `ResumeData` → `candidate_profiles`

**Como** dueño del sistema, **quiero** transformar la `ResumeData` extraída
+ inputs interactivos del usuario en una row de `candidate_profiles`
persistida en BD, **para que** el wizard tenga un commit atómico al final.

### Acceptance Criteria

- [ ] `src/jobhunter/onboarding/profile_generator.py` con:
  ```python
  async def generate_profile(
      resume_data: ResumeData,
      user_inputs: ProfileUserInputs,    # contexto que la IA no puede inferir
      session: Session,
      llm_client: AnthropicLLMClient,
  ) -> CandidateProfile:                  # row recién insertada
  ```
- [ ] `ProfileUserInputs` (Pydantic): `country`, `work_authorization`,
  `timezone_home`, `overlap_max_hours_cet`, `contract_preferences`,
  `hard_blockers`, `payment_methods_ok`, `profile_name` (lo que el usuario
  decide llamarlo, ej. "Python AI Senior").
- [ ] Inferencia LLM (Sonnet) para los campos derivables:
  - `seniority`, `years_experience` (validar contra `detected_*` del
    ResumeData).
  - `primary_stack` (5-7 tecnologías), `secondary_stack`,
    `domains` (3-5 áreas).
  - `positive_signals`, `soft_negatives` (sugerencias iniciales que el
    usuario puede ajustar después).
- [ ] Prompt versionado en `prompts/onboarding/profile_generator/v1.md`.
- [ ] **Languages** se rellenan a partir de `ResumeData.languages` con
  defaults razonables ("native" si es el idioma del país declarado, "fluent"
  si no se especifica nivel).
- [ ] **`compensation` queda NULL** en este paso — lo pobla `SalaryProposer`
  (S05) en un paso aparte.
- [ ] Persistencia: `INSERT` en `candidate_profiles` vía `CandidateProfileRepo
  .create(profile_data)`. NO se inserta `compensation`.
- [ ] Devuelve la entidad recién creada (con `id` poblado).
- [ ] Tests con `ResumeData` fixture + `MockLLMClient` que devuelve respuesta
  Sonnet pre-grabada.

### Tasks

- [ ] Implementar `generate_profile`.
- [ ] Pydantic `ProfileUserInputs`.
- [ ] Prompt versionado.
- [ ] Tests integración (DB seeded + mock LLM).

### Estimación: 2h

### Notas

- **Multi-profile habilita esto:** el usuario puede correr `generate_profile`
  N veces (vía wizard "Add another profile"). Cada llamada inserta una row
  distinta.
- **Validación cruzada del LLM con ResumeData:** si el LLM dice
  `years_experience=3` pero `ResumeData.detected_years_experience=15`,
  warn al usuario en el wizard. Probable confusión por formato del CV.

---

## E14-S04 — `CVVariantGenerator`: variants user-defined

**Como** dueño del sistema, **quiero** generar N variants de CV con
nombres y focos arbitrarios elegidos por el usuario, **para que** el sistema
soporte cualquier combinación de carreras (no sólo `ai_python` /
`flutter` / `fullstack`) y la `variant_selector` tenga material rico para
elegir.

### Acceptance Criteria

- [ ] `src/jobhunter/onboarding/cv_variant_generator.py` con:
  ```python
  async def generate_variant(
      profile: CandidateProfile,
      resume_data: ResumeData,
      variant_spec: VariantSpec,         # name + foco que el usuario quiere
      session: Session,
      llm_client: AnthropicLLMClient,
  ) -> CVVariant:                         # row insertada con experiencias
  ```
- [ ] `VariantSpec` (Pydantic):
  ```python
  class VariantSpec(BaseModel):
      name: str                            # "ai_python_engineer", lowercase + underscore
      display_name: str                    # "AI Python Engineer", human-friendly
      target_role_keywords: list[str]      # ["python", "ml engineer", "ai engineer"]
      target_stack: list[str]              # ["Python", "PyTorch", "FastAPI"]
      target_seniority: str | None
      angle_description: str               # "Foco en backend AI con LLMs en producción"
  ```
- [ ] Generación LLM (Sonnet) que toma:
  - `ResumeData` completa (todas las experiencias).
  - `VariantSpec` (qué quiere destacar).
  - `profile` (compensation, etc., para coherencia).
- [ ] **Output del LLM:**
  - `summary` reescrito con foco en `angle_description`.
  - `skills` priorizados (los relevantes para la variant primero).
  - `experiences` con bullets reescritos/reordenados — sólo se mantienen
    bullets relevantes; los irrelevantes se omiten para mantener el CV
    enfocado.
- [ ] Prompt versionado en `prompts/onboarding/cv_variant_generator/v1.md`.
- [ ] Persistencia atómica: en una transacción, `INSERT` en `cv_variants` +
  N `INSERT` en `cv_variant_experiences`. Si falla cualquiera, rollback.
- [ ] `raw_markdown` se renderiza desde los datos estructurados (helper
  `cv_variant_to_markdown(variant) -> str`) y se persiste para que el
  usuario pueda exportar / diffear.
- [ ] Tests: generar 3 variants distintas a partir de la misma
  `ResumeData` con `VariantSpec` distintas → verificar que los `summary`
  y `skills` priorizados son distintos.

### Tasks

- [ ] Implementar `generate_variant`.
- [ ] Pydantic `VariantSpec`.
- [ ] Helper `cv_variant_to_markdown`.
- [ ] Prompt versionado.
- [ ] Tests con fixtures.

### Estimación: 2.5h

### Notas

- **El usuario controla cuántas variants.** El wizard sugiere defaults
  basados en `ResumeData.detected_primary_stack` (ej. si detecta Python+AI
  y Flutter, sugiere 2 variants). Pero el usuario puede pedir 1, 5, o 10.
- **Costo:** ~$0.02 por variant. 5 variants = $0.10. Aceptable.
- **`raw_markdown` regenerable:** si el LLM cambia o el prompt evoluciona,
  re-generar todas las variants es un comando (`profile rebuild-variants
  <profile_id>`).

---

## E14-S05 — `SalaryProposer`: rango salarial con rationale

**Como** dueño del sistema, **quiero** que el sistema proponga un rango
salarial (floor / target / stretch) basado en mi experiencia, ubicación y
preferencias contractuales, **para que** no tenga que hacer research
manual de mercado y la propuesta tenga rationale explicable.

### Acceptance Criteria

- [ ] `src/jobhunter/onboarding/salary_proposer.py` con:
  ```python
  async def propose_salary(
      profile: CandidateProfile,         # ya creado por S03
      resume_data: ResumeData,
      llm_client: AnthropicLLMClient,
      market_data_source: SalaryDataSource | None = None,
  ) -> SalaryProposal:
  ```
- [ ] `SalaryProposal` (Pydantic):
  ```python
  class SalaryProposal(BaseModel):
      currency: Literal["USD", "EUR"]
      period: Literal["month", "year"]
      floor: int
      target: int
      stretch: int
      rationale: str                      # narrativa del LLM
      data_sources: list[str]             # ["llm_baseline_2026", ...]
      confidence: float                   # 0-1
  ```
- [ ] **Estrategia de v1 (LLM con baseline 2026):** prompt versionado en
  `prompts/onboarding/salary_proposer/v1.md` que incluye una tabla de
  baselines por (stack, seniority, region, contract_type). El LLM ajusta
  basándose en `years_experience`, `primary_stack`, `country`,
  `contract_preferences`.
- [ ] **Hook para Estrategia v2 (datos reales):** parámetro opcional
  `market_data_source` que, si se pasa, consulta `JobRepo` por jobs
  ingestados con compensation extraído + match heurístico contra el
  perfil. Devuelve mediano + p25/p75. Esto se implementa cuando haya
  500+ jobs reales en BD; por ahora el hook queda definido pero no
  conectado.
- [ ] El resultado se persiste en `candidate_profiles.compensation` vía
  `CandidateProfileRepo.update_compensation(profile_id, proposal)`.
- [ ] El usuario puede aceptar o ajustar antes del save final (el wizard
  presenta los 3 valores como editables).
- [ ] Tests con `MockLLMClient`.

### Tasks

- [ ] Implementar `propose_salary`.
- [ ] Prompt con tabla baseline 2026 (revisar al menos cada 6 meses).
- [ ] Pydantic models.
- [ ] Tests.

### Estimación: 1.5h

### Notas

- **Baselines envejecen.** Marcar el prompt con
  `# verified YYYY-MM-DD` (igual que `pricing.py` de E4-S03). Workflow
  semestral de revisión recomendable.
- **Hook v2 = futuro story.** Cuando haya 500+ jobs ingestados, abrir
  `E14-S12 — SalaryProposer con datos reales`. La interfaz
  `SalaryDataSource` ya está prevista para minimizar refactor.

---

## E14-S06 — Refactor `variant_selector` para variants arbitrarias

**Como** dueño del sistema, **quiero** que el `variant_selector` funcione
con N variants user-defined, **para que** el cambio de variants
hardcoded a user-defined no rompa el assistant E6.

### Acceptance Criteria

- [ ] `src/jobhunter/application/variant_selector.recommend_cv_variant` se
  reescribe con esta firma:
  ```python
  def recommend_cv_variant(
      job: Job,
      available_variants: Sequence[CVVariant],   # cargadas de DB
      llm_client: AnthropicLLMClient | None = None,
  ) -> VariantRecommendation:
  ```
- [ ] **Lógica nueva en 2 pasos:**
  1. **Heurística (gratis, rápida):** para cada `variant` en
     `available_variants`, calcular score = count(matches entre
     `variant.target_role_keywords` ∪ `variant.target_stack` y
     `job.title` ∪ `job.description.lower()`). El de mayor score gana
     con `confidence = score / max_possible_score`.
  2. **Fallback LLM (si confidence < 0.4 o todas las variants empatan):**
     prompt corto con `job.title + job.description.snippet + summaries
     de cada variant`, Sonnet devuelve `{"variant_name": "...",
     "confidence": 0.X, "reasoning": "..."}`.
- [ ] Si `len(available_variants) == 1`: devuelve esa variant con
  `confidence = 1.0` sin llamar al LLM.
- [ ] Si `len(available_variants) == 0`: raise
  `NoCVVariantsAvailableError` (debe gating en el caller).
- [ ] Mantener `VariantRecommendation` con `variant_name`, `variant_id`,
  `confidence`, `reasoning`.
- [ ] **Backward-compat:** los callers existentes (`assistant.py`, página
  Streamlit de Assist) siguen funcionando, sólo cambia que ahora reciben
  el `variant_id` para resolver contra DB en vez de archivo.
- [ ] Tests con scenarios:
  - 1 variant disponible → devuelve esa.
  - 3 variants, una matchea claramente → heurística sin LLM.
  - 3 variants, todas matchean débilmente → escala a LLM.
  - 0 variants → raise.

### Tasks

- [ ] Reescribir `recommend_cv_variant`.
- [ ] Helper `_keyword_match_score(variant, job) -> float`.
- [ ] Helper `_llm_disambiguate(job, variants) -> VariantRecommendation`.
- [ ] Crear `NoCVVariantsAvailableError` en `application/__init__.py`.
- [ ] Tests unitarios cubriendo los 4 scenarios.

### Estimación: 1.5h

### Notas

- **El refactor preserva la heurística > LLM** (decisión original de E6-S02
  ratificada en ADR-007 conceptualmente). LLM sólo escala cuando la
  heurística es ambigua.
- **`target_role_keywords` y `target_stack` se llenan en S04** con sugerencias
  del LLM. El usuario puede ajustarlas en el wizard step 6 — eso afina el
  selector.

---

## E14-S07 — Refactor cross-épica: consumers leen perfil de DB

**Como** dueño del sistema, **quiero** que TODOS los consumidores del perfil
(scoring, outreach, application/) lean de la BD en vez de yaml/markdown,
**para que** la BD sea fuente única de verdad y la deuda técnica del
perfil duplicado se resuelva.

### Acceptance Criteria

- [ ] **Scoring (E4):**
  - `prompts/scoring/v1.md` se edita para reemplazar el bloque
    `candidate_profile:` hardcoded por el placeholder
    `{candidate_profile_yaml}` (mismo patrón que `prompts/outreach/v1/`).
  - `scoring/scorer.JobScorer.score(job)` recibe `profile_id: UUID` o
    consulta `CandidateProfileRepo.list_active()`.
  - **Multi-profile:** `score(job)` itera sobre cada perfil activo,
    persiste el resultado por perfil. Schema Job extendido (ver tarea
    abajo): `Job.scores_by_profile: JSONB` o nueva tabla
    `job_profile_scores`.
- [ ] **Outreach (E9):**
  - `outreach/generator.generate_message`: en vez de
    `Path("prompts/candidate_profile.yaml").read_text()`, hace
    `CandidateProfileRepo.get_active_by_id(profile_id).to_yaml_string()`.
  - `outreach/scoring.calculate_heuristic_score`: recibe
    `candidate_profile: CandidateProfile` (modelo SQLAlchemy) en vez de
    `dict`.
  - `__main__.py:2195` (importer) usa el repo en lugar de yaml directo.
- [ ] **Application (E6):**
  - `application/cv.load_cv(variant_name, ...)` se reescribe para leer de
    `cv_variants` table vía `CVVariantRepo.get_by_name(profile_id, name)`.
  - `application/cv.list_available_variants(profile_id)` lista de DB.
  - `application/assistant.assist_application` recibe `profile_id` (lo
    obtiene del session_state del dashboard o del CLI).
  - `application/cover_letter`, `cv_tweaks`, `ats_keywords`: reciben
    `cv_variant: CVVariant` (modelo SQLAlchemy) en vez de leer archivo.
- [ ] **Schema extension para multi-profile scoring:** decidir entre:
  - Opción 1: `Job.scores_by_profile JSONB` (`{profile_id: {fit_score,
    tier, score_data}}`).
  - Opción 2: nueva tabla `job_profile_scores (job_id, profile_id,
    fit_score, tier, score_data, scored_at, scored_with_prompt_version)`.
  - **Recomendación: Opción 2** — queryable, indexable, audit-friendly.
- [ ] Migration adicional para la tabla nueva.
- [ ] **Tests de regresión:** los tests de E4, E6, E9 siguen pasando con la
  nueva lógica (puede requerir actualizar fixtures para que el `db_session`
  inserte un perfil mínimo antes de cada test).

### Tasks

- [ ] Editar `prompts/scoring/v1.md` con placeholder.
- [ ] Migration tabla `job_profile_scores`.
- [ ] Refactor `JobScorer.score` para iterar perfiles activos.
- [ ] Refactor `outreach/generator.py` y `outreach/scoring.py`.
- [ ] Refactor `application/cv.py`, `assistant.py`, `cover_letter.py`,
  `cv_tweaks.py`, `ats_keywords.py`.
- [ ] Helper `CandidateProfile.to_yaml_string()` (para inyectar como string
  en prompts que lo esperan en formato yaml).
- [ ] Update fixtures en `tests/conftest.py`: `sample_candidate_profile`
  insertado por default.
- [ ] Run full test suite, fix regresiones.

### Estimación: 3h

### Notas

- **Esta es la story de mayor riesgo de regresión** de E14. El test suite
  completo (>200 tests) debe pasar al final. Considerar feature flag para
  rollback si CI rojo.
- **Multi-profile scoring 3x el costo LLM si hay 3 perfiles activos.** El
  scorer puede paralelizar las 3 llamadas (`asyncio.gather`) para mantener
  latencia. Documentar en runbook.

---

## E14-S08 — Wizard dashboard `pages/0_🎯_Onboarding.py`

**Como** dueño del sistema, **quiero** un wizard web de varios pasos para
crear/editar mi perfil, **para que** el bootstrap inicial sea sin terminal
y la experiencia primer-uso sea fluida.

### Acceptance Criteria

- [ ] Página `src/jobhunter/dashboard/pages/0_🎯_Onboarding.py` (slot `0_`
  → primero alfabéticamente, llamado "Onboarding").
- [ ] **Soft gating:** `dashboard/auth.require_auth` extendido o nuevo
  helper `check_profile_setup()` que, si `CandidateProfileRepo.list_active()`
  retorna vacío, muestra banner persistente en TODAS las páginas:
  ```
  ℹ️ Configura tu perfil para empezar a recibir matches → [Empezar wizard]
  ```
  Click → navigate a `pages/0_🎯_Onboarding.py`. Las demás páginas siguen
  accesibles (no bloqueo).
- [ ] **Wizard de 7 pasos** con progreso visible (step indicator):
  1. **Upload resume** (drag-drop o file picker, PDF/MD/DOCX). Botón
     "Saltar y rellenar manual" lleva al step 2 con `ResumeData` vacío.
  2. **Review extracción**: bloques editables con `name`, experiences
     (timeline), `skills`, `educations`, `languages`. Usuario corrige
     cualquier mala extracción. Indicador de `detected_seniority` /
     `detected_years_experience` / `detected_primary_stack`.
  3. **Contexto personal** (form): `country`, `work_authorization`,
     `timezone_home`, `overlap_max_hours_cet`, `contract_preferences`
     (multi-select), `payment_methods_ok` (multi-select), `hard_blockers`
     (textarea, una por línea).
  4. **Career angle** (form):
     - `profile.name` (texto libre, ej. "Python AI Senior").
     - Confirmar `primary_stack`/`secondary_stack`/`domains` sugeridos por
       el LLM (editables).
     - `positive_signals` y `soft_negatives` editables.
  5. **Salary proposal**: muestra `SalaryProposer` resultado con
     `rationale` desplegable. Tres campos editables (floor/target/stretch).
     Toggle USD/EUR + month/year.
  6. **Variants**: form repetible.
     - "¿Cuántas variants quieres?" → defaults 1, máximo 10.
     - Para cada variant: `name`, `display_name`, `target_role_keywords`
       (chips), `target_stack` (chips), `angle_description`.
     - Botón "Generar" por variant → llama `CVVariantGenerator` y muestra
       preview del markdown (editable).
  7. **Confirm and save**: resumen completo. Botón "Activar perfil"
     ejecuta la transacción atómica (perfil + N variants).
- [ ] **Edit mode**: si ya hay perfil activo, la página detecta
  `?profile_id=X` query param o usa el activo por default. Pre-llena los
  pasos con datos actuales. Permite saltar entre pasos no-secuencialmente
  via tabs/anchors.
- [ ] **State management**: `st.session_state` con clave
  `onboarding_state: OnboardingState` (Pydantic) que persiste entre
  re-renders. Reset explícito al completar.
- [ ] **Botón "Add another profile"** en dashboard si ya hay perfil →
  abre wizard en modo "nuevo perfil" (limpia state).
- [ ] Costo total visible al final (suma de las llamadas LLM del wizard).
- [ ] Tests E2E Playwright: completar el flow con un PDF fixture
  (`tests/e2e/dashboard/test_onboarding_wizard.py`).

### Tasks

- [ ] Página Streamlit con state machine.
- [ ] Componente `render_resume_review_form(resume_data)` editable.
- [ ] Componente `render_variant_form(variant_spec, profile)` con preview.
- [ ] Soft gating helper en `dashboard/auth.py` o `layout.py`.
- [ ] Test E2E.

### Estimación: 4h

### Notas

- **Wizard como UX principal.** El CLI (S09) es alternativo. La mayoría de
  usuarios van a usar la web.
- **Edit mode es lo que hace al wizard sostenible.** Sin él, el usuario
  necesita SQL para cambiar el floor salarial. Con él, la onboarding page
  es también el "settings page" del perfil.

---

## E14-S09 — CLI `profile bootstrap` (alternativo)

**Como** dueño del sistema, **quiero** un comando CLI equivalente al wizard
para automatización (scripts, re-bootstrapping desde cron, headless
deploys), **para que** el sistema no dependa exclusivamente del navegador.

### Acceptance Criteria

- [ ] CLI `jobhunter profile bootstrap --resume PATH [--interactive]
  [--profile-name NAME]`.
- [ ] Sin `--interactive`: corre el pipeline end-to-end y crea un perfil con
  `compensation` propuesto, variants generadas con defaults sugeridos por
  IA, **TODO** markers en campos que necesitan input humano (ej.
  `hard_blockers: [TODO_ADD_BLOCKERS]`). El usuario edita después en
  dashboard o vía SQL.
- [ ] Con `--interactive`: prompts en terminal para los campos que la IA no
  puede inferir (los del step 3 del wizard).
- [ ] Output rich: tabla con resumen del perfil creado + ID + costo total
  + comando para verificar (`profile show <id>`).
- [ ] CLI auxiliares:
  - `profile list` — lista perfiles con `id`, `name`, `is_active`,
    `count(variants)`, `created_at`.
  - `profile show <id>` — muestra el perfil completo (yaml-like) en stdout.
  - `profile activate <id>` / `profile deactivate <id>`.
  - `profile delete <id> --confirm` — soft delete (marca inactivo + audit
    log) o hard delete (ON DELETE CASCADE).
  - `profile variants list <profile_id>`.
  - `profile rebuild-variants <profile_id>` — re-genera todas las variants
    del perfil con el prompt actual (útil tras prompt iteration).
- [ ] Tests CLI con `typer.testing.CliRunner`.

### Tasks

- [ ] Implementar comandos en `__main__.py` (sub-Typer `profile_app`).
- [ ] Tests CLI.

### Estimación: 1.5h

### Notas

- **Reuso máximo:** los comandos llaman directamente a las funciones de
  S02–S05. El CLI es UI alternativa, no lógica nueva.
- **`--interactive` con `typer.prompt`** para los campos sin IA-inferencia.

---

## E14-S10 — Migración legacy: yaml + markdowns → BD

**Como** dueño del sistema, **quiero** que un usuario con `prompts/
candidate_profile.yaml` y `.local/cv_variants/*.md` existentes pueda
correr `alembic upgrade head` y tener su data ya en BD, **para que** el
upgrade de E14 sea no-disruptivo.

### Acceptance Criteria

- [ ] Migration Alembic post-S01 (idempotente):
  - Si existe `prompts/candidate_profile.yaml`, parsearlo e insertar como
    nuevo `candidate_profile` (`name="Legacy Profile"`, `is_active=true`).
    Mapea campos yaml → columnas BD según convención de Eje A3.
  - Si existen `.local/cv_variants/*.md`, parsear cada uno (usando el
    parser `_parse_cv_markdown` actual de `application/cv.py`) e insertar
    como `cv_variants` asociadas al perfil legacy. `target_role_keywords`
    y `target_stack` se infieren del nombre del archivo (ej. `ai_python.md`
    → keywords `["python", "ai", "ml"]`).
  - Si NO existe ninguno (deploy fresh), no-op.
- [ ] Después de la migración exitosa, el script archiva los originales:
  - `prompts/candidate_profile.yaml` → `prompts/_legacy/{timestamp}/
    candidate_profile.yaml`.
  - `.local/cv_variants/*.md` → `.local/cv_variants/_legacy/{timestamp}/`.
  - **NO los borra** — el usuario puede consultar/restaurar.
- [ ] Migration imprime resumen: "Imported 1 legacy profile + N CV variants.
  Originals archived in prompts/_legacy/{timestamp}/."
- [ ] Tests: ejecutar migration con yaml mock + markdowns mock → verificar
  rows insertados.

### Tasks

- [ ] Migration Alembic.
- [ ] Helpers de parsing (reuso del parser actual).
- [ ] Lógica de archive.
- [ ] Tests integración con fixtures yaml/md.

### Estimación: 1h

### Notas

- **Para tu caso particular**, esta migration es "gratis" (no tienes yaml
  de tu perfil definitivo desplegado). Pero existe por higiene: si el
  proyecto se forkea o si en el futuro despliegas una versión local
  primero, la migration evita pérdida de data.
- **El archivo en `_legacy/` queda gitignored** (igual que `.local/`)
  excepto si el yaml original estaba commiteado. Si estaba commiteado, se
  mueve dentro del repo y se commitea el move.

---

## E14-S11 — Tests E2E + actualización de docs

**Como** dueño del sistema, **quiero** test E2E del wizard + CLI bootstrap
+ documentación actualizada en HUMAN_SETUP/CLAUDE/ARCHITECTURE, **para
que** E14 quede cerrada con regression coverage y la documentación refleje
la nueva realidad (perfil en BD, no en yaml).

### Acceptance Criteria

- [ ] **Test E2E Playwright** `tests/e2e/dashboard/test_onboarding_wizard.py`:
  - Login → ver banner soft-gating → click "Empezar wizard".
  - Upload de PDF fixture (sanitizado).
  - Avanzar por los 7 pasos rellenando los inputs.
  - Verificar que al final hay 1 row en `candidate_profiles` + N rows en
    `cv_variants`.
  - Banner soft-gating desaparece.
- [ ] **Test E2E del CLI bootstrap** `tests/integration/test_profile_bootstrap_cli.py`:
  - Run `profile bootstrap --resume tests/fixtures/resumes/sample_python.pdf`.
  - Verificar mismas inserciones en BD.
- [ ] **Test cross-épica:** después de bootstrap, ejecutar `score-job <id>`
  contra un job ya ingestado → verificar que el scoring usa el perfil de BD
  (no falla por yaml ausente).
- [ ] **Documentación:**
  - Actualizar `HUMAN_SETUP.md` §2 completa: reemplazar la sección "Editar
    yaml" por "Ejecutar wizard". Mantener nota sobre alternativa CLI.
  - Actualizar `CLAUDE.md` sección "Architecture": añadir
    `onboarding/` como módulo; mencionar que perfil vive en BD.
  - Actualizar `docs/ARCHITECTURE.md` con `candidate_profiles` como
    entidad de dominio.
  - Actualizar `docs/data_model.md` con las 4 tablas nuevas + diagrama
    mermaid actualizado.
  - Crear `ADR-008 — Profile and CV variants live in DB, not files` con
    rationale (resuelve duplicación, habilita audit, multi-profile,
    edit en vivo).
  - Actualizar `README.md` con captura del wizard si es posible.

### Tasks

- [ ] Implementar tests E2E.
- [ ] Implementar test integración CLI.
- [ ] Update docs.
- [ ] Crear ADR-008.

### Estimación: 2h

### Notas

- **El test cross-épica es crítico.** Sin él, S07 podría dejar regresiones
  silenciosas en E4/E6/E9 que sólo se manifiestan en producción.

---

## Definition of Ready para E15+ (si surge)

E14 cerrada cuando:

- [ ] Las 11 stories tienen AC ✅.
- [ ] CI verde con tests E2E del wizard.
- [ ] Bootstrap real ejecutado con un CV personal: perfil + variants
  insertados, scoring contra el perfil funciona.
- [ ] Multi-profile probado: crear 2 perfiles activos, scorear 1 job →
  resultados separados por perfil en `job_profile_scores`.
- [ ] Edit mode probado: re-correr wizard sobre perfil existente actualiza
  sin duplicar.
- [ ] Migration legacy probada (con yaml/md de juguete).
- [ ] `HUMAN_SETUP.md` §2 reescrita; `ADR-008` creado.
- [ ] Tag `v1.1.0` (primer increment funcional post-MVP).

A partir de aquí, mejoras candidatas (no son E15 todavía, pero candidatas
si rinde el uso):

- **`E14-S12 — SalaryProposer con datos reales`** (cuando hayan 500+ jobs
  ingestados, conectar el hook de S05 para leer de `JobRepo`).
- **A/B testing de prompts del wizard** (E11-S02 ya da la infra).
- **Multi-language UI del wizard** (hoy hardcoded en español).

---

## Anexo: ¿Por qué E14 es nueva épica y no extensión de E13?

E13 es "QA Humana" — flujos donde el humano arbitra decisiones ambiguas
de la IA y gaps de superficie operativa **sobre lo construido**. Sus 5
stories rescatan desvíos de E1–E12.

E14 introduce **funcionalidad sustantiva nueva** (resume parsing, profile
generation, salary proposal, wizard UX) que no estaba en el plan
original. El backlog merece reflejarlo como first-class:

- Tema cohesivo distinto (onboarding vs operación / mantenimiento).
- Toca un pipeline nuevo (resume parsing, profile management) que no existía.
- Stories sustantivas, no rescates.

Mantener la separación E13 ("cierre de deuda") vs E14 ("nueva
funcionalidad") preserva la claridad narrativa del backlog.

---

## Anexo: Costo total esperado de E14 en operación

| Operación | Frecuencia esperada | Costo USD |
|---|---|---|
| Bootstrap one-shot (Opus + Sonnet) | 1 × initial + 0–2 × upon major career change | ~$0.20 cada uno |
| Re-generar variants (`profile rebuild-variants`) | 0–4 × año tras prompt iteration | ~$0.10 cada uno |
| Scoring multi-profile (3 activos) | runtime, 3x baseline | ~$0.006/job × N jobs/día |

Para un usuario con 1 perfil activo, E14 añade **<$1/mes** sostenido. Con
3 perfiles activos: **~$3/mes**. Aceptable.

---

**Fin Documento R.**
