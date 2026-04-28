# Documento J — Backlog Nivel 2: Descomposición de E6 (AI-Assisted Application Toolkit)

**Épica origen:** E6 — AI-Assisted Application Toolkit (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 13–16 horas (2-3 sesiones de medio día).

**Convenciones:** mismas que documentos E–I. ID `E06-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E6 es donde el sistema deja de ser "agregador inteligente" y se convierte en **herramienta de productividad personal**. Para cualquier oferta tier A/B, en <30 segundos genera: cover letter draft, recomendación de variante de CV, lista de tweaks sugeridos, y keywords ATS extraídas de la JD. El usuario revisa, ajusta, y envía manualmente — workflow target: <10 min por aplicación.

**Por qué semi-automatizado y no full auto-apply:** decisión arquitectónica explícita del Documento B §9. Para roles senior $5500+/mes en EU, calidad importa más que volumen. Auto-apply destruye conversión (<1% vs 10-15% con cover letter cuidada). El sistema ahorra el 90% del trabajo (descubrimiento, scoring, draft) pero conserva el 10% que más impacto tiene (la firma humana).

### Decisiones técnicas clave

1. **Cover letters generadas con `claude-opus-4-7`** — modelo más caro pero los outputs son los más visibles del sistema. ~$0.10 por cover letter × 30/mes = $3/mes. Vale.
2. **CV variants en archivos `.md` versionados** — `cv_variants/ai_python.md`, `flutter.md`, `fullstack.md`. Diffables, mantenibles, fáciles de iterar. **No commitear los archivos con datos personales reales** (esos viven en `.local/cv_variants/` gitignored).
3. **ATS keyword extraction como segundo modelo Haiku** — barato y rápido. Output estructurado (lista de keywords priorizadas).
4. **Workflow CLI-first, no UI** — `jobhunter assist <job_id>` devuelve paquete listo para revisar en terminal/editor. Dashboard de E7 lo expondrá visualmente, pero la lógica está aquí.
5. **Persistencia del draft en `applications.cover_letter_text`** — incluso si no se envía, queda guardado para futura referencia o re-uso.
6. **Cero auto-aplicación** — explicítamente documentado en DoD: el sistema NUNCA envía aplicaciones automáticamente. Solo asiste.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E06-S01 | CV variants: estructura + cargador | 1.5h | E2 cerrada | con S02 |
| E06-S02 | Selector de variante de CV (heurística) | 1h | S01 | con S01 (puede ser misma sesión) |
| E06-S03 | Generador de cover letters (Opus) | 2.5h | E4 cerrada, S01 | — |
| E06-S04 | Extractor de keywords ATS | 1.5h | E4 cerrada | con S03 |
| E06-S05 | Sugeridor de tweaks de CV | 2h | S03, S04 | — |
| E06-S06 | Orquestador `assist_application(job_id)` | 1.5h | S02, S03, S04, S05 | — |
| E06-S07 | CLI: `jobhunter assist` + `apply` + `letter` | 2h | S06 | — |
| E06-S08 | Tests con fixtures + tracker de aplicaciones | 1.5h | S06, S07 | — |

### Camino crítico

```
E2,E4 ─→ S01 ─→ S02 ─┐
              │       │
              └→ S03 ─┤
                 S04 ─┴→ S05 ─→ S06 ─→ S07 ─→ S08
```

**Tiempo serial:** ~13.5h. **Con paralelización (S03+S04 juntos):** ~11h.

### Definition of Done de la épica

```bash
# Generar paquete de aplicación para un job tier-A/B
jobhunter assist <job_id>
# → output: variante CV recomendada, cover letter draft, tweaks sugeridos, keywords ATS
# → cover letter persistida en applications.cover_letter_text

# Generar solo la cover letter (output a stdout o archivo)
jobhunter letter <job_id> --output cover.md

# Marcar como aplicado tras enviar manualmente
jobhunter apply <job_id> --method web --cv-variant ai_python --notes "Aplicado vía LinkedIn"
# → crea registro en applications con status='applied'
# → transiciona job a status='applied'

# Workflow medible: oferta tier-A → aplicación enviada en <10 min
```

---

## E06-S01 — CV variants: estructura + cargador

**Como** dueño del sistema, **quiero** mis CVs en archivos markdown versionados con estructura semántica, **para que** el generador de cover letters tenga contexto rico y el sugeridor de tweaks (S05) pueda recomendar reordenar bullets específicos.

### Acceptance Criteria

- [ ] Directorio `cv_variants/` en repo con templates **placeholder** (sin datos personales reales):
  - `ai_python.template.md`
  - `flutter.template.md`
  - `fullstack.template.md`
- [ ] Directorio `.local/cv_variants/` (gitignored) donde viven las versiones reales con datos personales.
- [ ] Estructura de archivo con headers semánticos parseables:
  ```markdown
  ## SUMMARY
  ...
  ## STACK
  - primary: ...
  - secondary: ...
  ## EXPERIENCE
  ### [Role] | [Company] | [Dates]
  - [bullet 1]
  - [bullet 2]
  ## SKILLS
  - ...
  ```
- [ ] `src/jobhunter/application/cv.py` con:
  - `CVVariant` (Pydantic): `name`, `path`, `summary`, `stack_primary: list[str]`, `stack_secondary: list[str]`, `experience: list[Experience]`, `skills: list[str]`, `raw_markdown: str`.
  - `Experience` (Pydantic): `role`, `company`, `dates`, `bullets: list[str]`.
  - `load_cv(variant_name: str) -> CVVariant` que parsea el markdown.
  - `list_available_variants() -> list[str]`.
- [ ] Settings nueva: `cv_variants_dir: Path = Path('.local/cv_variants')` con fallback a `cv_variants/` para los templates en CI.
- [ ] Tests cubren: parser correcto, archivo malformado raise error claro, fallback a templates si `.local/` vacío.

### Tasks

- [ ] Crear estructura `cv_variants/` con 3 templates placeholder (con `[YOUR_NAME]`, `[YOUR_EMAIL]`, etc.)
- [ ] Crear estructura `.local/cv_variants/` y añadir `.local/` al `.gitignore`
- [ ] Crear `src/jobhunter/application/__init__.py`, `cv.py`
- [ ] Implementar parser markdown → `CVVariant`
- [ ] Tests unitarios

### Estimación: 1.5h

### Notas

- **Por qué markdown estructurado y no YAML/JSON:** un CV es texto narrativo + estructura. Markdown captura ambos; YAML/JSON forzaría a perder la riqueza del texto. Además, el LLM lee mejor el formato natural.
- **`.local/` gitignored** es la convención para evitar leak accidental de datos personales. El primer commit del proyecto debe asegurar que `.local/` está en `.gitignore`.
- **Templates en repo** sirven dos propósitos: (1) CI puede correr tests contra templates dummy; (2) cualquier viewer del repo entiende la estructura sin ver tus datos reales.

---

## E06-S02 — Selector de variante de CV (heurística)

**Como** dueño del sistema, **quiero** una función que dado un `Job` con `score_data`, recomiende la mejor variante de CV (ai_python / flutter / fullstack), **para que** el orquestador (S06) elija sin intervención humana.

### Acceptance Criteria

- [ ] `src/jobhunter/application/variant_selector.py` con `recommend_cv_variant(job: Job) -> VariantRecommendation`.
- [ ] `VariantRecommendation` (Pydantic): `variant_name: str`, `confidence: float [0-1]`, `reasoning: str`.
- [ ] Lógica heurística basada en `score_data`:
  - Si `is_ai_ml_role=true` o stack incluye `python`+`ai/llm/ml` → `ai_python`.
  - Si `is_flutter_role=true` o stack incluye `flutter`+`dart` → `flutter`.
  - Si `is_full_stack=true` o no hay match claro → `fullstack`.
  - `confidence` calculada en función de qué tan claro es el match (1.0 = unambiguous).
- [ ] Si `score_data` no tiene info estructurada (caso edge), fallback heurística sobre `job.title` + `job.description` con keyword matching.
- [ ] Tests cubren: 5 casos típicos cada uno (claro AI, claro Flutter, claro fullstack, ambiguo, score_data faltante).

### Tasks

- [ ] Crear `variant_selector.py`
- [ ] Implementar `recommend_cv_variant`
- [ ] Helper `_score_data_to_variant(score_data) -> VariantRecommendation`
- [ ] Helper fallback `_keyword_matching_variant(job) -> VariantRecommendation`
- [ ] Tests con fixtures de `score_data` variados

### Estimación: 1h

### Paralelizable con

S01 (en la misma sesión, si tienes ambos archivos abiertos).

### Notas

- **Heurística determinística > LLM** para este caso. Es elección binaria entre 3 opciones; no necesitamos un modelo. Más rápido, gratis, y predecible.
- **`confidence` en el output** permite al usuario saber cuándo el sistema está adivinando vs sabiendo. Si `confidence < 0.5`, el CLI muestra "Variant uncertain — review before applying".

---

## E06-S03 — Generador de cover letters (Opus)

**Como** dueño del sistema, **quiero** generar borradores de cover letters específicas a la JD, en mi voz y con detalle del producto/empresa, **para que** la única edición humana requerida sea ajustar tono y verificar precisión.

### Acceptance Criteria

- [ ] `src/jobhunter/application/cover_letter.py` con `async generate_cover_letter(job, cv_variant, llm_client) -> CoverLetterResult`.
- [ ] `CoverLetterResult` (Pydantic): `text: str`, `model: str`, `prompt_version: str`, `cost_usd: float`, `word_count: int`.
- [ ] Modelo: `claude-opus-4-7` por defecto (configurable vía `Settings.cover_letter_model`).
- [ ] Prompt versionado en `prompts/cover_letter/v1.md` (estructura igual a prompts de E4: `## SYSTEM` + `## USER_TEMPLATE`).
- [ ] Contexto inyectado en el prompt:
  - JD completa (truncada a 6000 chars).
  - CV variant relevante (markdown completo).
  - `cover_letter_angle` del `score_data` (campo `recommendation.cover_letter_angle`).
  - Candidate profile (mismo bloque YAML del Doc A).
- [ ] Validaciones del output:
  - 250-450 palabras (cover letters efectivas).
  - No incluye placeholders sin rellenar (`[Company]`, `[Role]`, etc.).
  - Tono profesional pero no genérico (validation heurística: no contiene frases prohibidas como "I am writing to apply").
- [ ] Persistir en `applications.cover_letter_text` si la `Application` ya existe, o en cache temporal si no.
- [ ] Tests con LLM mockeado: generación exitosa, validation falla → retry una vez con prompt reforzado.

### Tasks

- [ ] Crear `prompts/cover_letter/v1.md` con prompt cuidadosamente diseñado
- [ ] Implementar `generate_cover_letter`
- [ ] Implementar validaciones del output (word count, placeholders, frases prohibidas)
- [ ] Tests con fixtures de respuestas LLM
- [ ] Capturar 3 fixtures reales para regression tests

### Estimación: 2.5h

### Notas

- **Prompt design es 80% del éxito.** Vale la pena invertir 30 min en iterar el prompt v1 contra 3-5 jobs reales antes de cerrar la story. Anti-patrones a evitar:
  - "I am writing to express interest in" (mata cover letters automáticamente).
  - Frases superlative ("amazing experience", "passionate about").
  - Lista de skills sin contexto (mejor: skill aplicada a un problema).
- **Lista de "frases prohibidas"** a validar en post-processing: lista vivirá en `prompts/cover_letter/forbidden_phrases.txt` versionada.
- **Costo:** Opus a ~$15/$75 input/output per million tokens. Una cover letter típica usa ~1000 input + 500 output = $0.015 + $0.0375 ≈ $0.05. Estimación previa de $0.10 era conservadora.

---

## E06-S04 — Extractor de keywords ATS

**Como** dueño del sistema, **quiero** extraer las keywords críticas de la JD que probablemente filtre el ATS, **para que** pueda asegurarme de incluirlas literalmente (cuando aplica) en CV y cover letter.

### Acceptance Criteria

- [ ] `src/jobhunter/application/ats_keywords.py` con `async extract_ats_keywords(job, llm_client) -> ATSKeywordsResult`.
- [ ] Modelo: `claude-haiku-4-5-20251001` (rápido y barato; este caso no requiere razonamiento profundo).
- [ ] `ATSKeywordsResult` (Pydantic): `must_have: list[Keyword]`, `nice_to_have: list[Keyword]`, `model`, `cost_usd`.
- [ ] `Keyword` (Pydantic): `term: str`, `category: str` (technical/soft/certification/tool/methodology), `weight: int [1-10]`, `present_in_cv: bool` (post-procesamiento, ver siguiente AC).
- [ ] Post-procesamiento: tras obtener keywords, comparar contra `cv_variant.raw_markdown` (case-insensitive substring) y poblar `present_in_cv`.
- [ ] Prompt versionado en `prompts/ats_keywords/v1.md`.
- [ ] Output ordenado por `weight` descendente.
- [ ] Tests con LLM mockeado.

### Tasks

- [ ] Crear `prompts/ats_keywords/v1.md`
- [ ] Implementar extractor
- [ ] Función `_check_presence_in_cv(keywords, cv_text)` (case-insensitive, soporta sinónimos básicos: `Python` matches `python`, `py3`)
- [ ] Tests

### Estimación: 1.5h

### Paralelizable con

S03.

### Notas

- **Why ATS keyword extraction matters:** muchas empresas medianas-grandes filtran CVs con ATS antes de que un humano los vea. Si la JD dice "experience with Kubernetes" y tu CV solo dice "container orchestration", el ATS te filtra. Esta story te muestra qué términos literales incluir.
- **Sinónimos básicos:** `Python` ↔ `Python 3` ↔ `Py3`. Para v1, hardcodear lista pequeña en `KEYWORD_SYNONYMS = {...}`. Si crece, considerar embedding-based similarity en E11.

---

## E06-S05 — Sugeridor de tweaks de CV

**Como** dueño del sistema, **quiero** sugerencias accionables de qué reordenar/destacar en el CV para esta JD específica, **para que** maximice match-score percibido sin reescribir el CV cada vez.

### Acceptance Criteria

- [ ] `src/jobhunter/application/cv_tweaks.py` con `async suggest_cv_tweaks(job, cv_variant, ats_keywords, llm_client) -> CVTweaksResult`.
- [ ] Modelo: `claude-sonnet-4-6` (este caso requiere razonamiento sobre el CV completo, vale el upgrade vs Haiku).
- [ ] `CVTweaksResult` (Pydantic): `tweaks: list[Tweak]`, `model`, `cost_usd`.
- [ ] `Tweak` (Pydantic): `type` (`reorder_bullet` / `add_keyword` / `rewrite_bullet` / `add_section` / `remove`), `target` (sección o bullet específico), `original: str | None`, `suggested: str | None`, `rationale: str`.
- [ ] Tweaks ordenados por impacto estimado (1 = highest).
- [ ] Máximo 5 tweaks por sugerencia (evitar parálisis por análisis).
- [ ] Prompt versionado en `prompts/cv_tweaks/v1.md`.
- [ ] Tests con fixtures.

### Tasks

- [ ] Crear `prompts/cv_tweaks/v1.md`
- [ ] Implementar `suggest_cv_tweaks`
- [ ] Tests con fixtures

### Estimación: 2h

### Notas

- **Por qué Sonnet, no Opus:** la calidad de Sonnet es suficiente para esta tarea de refinamiento; Opus sería overkill para algo que se re-corre por aplicación. Costo: ~$0.02 por sugerencia.
- **Disciplina del límite de 5 tweaks:** sin esto, el LLM tiende a generar 15 sugerencias menores que ahogan las 2-3 importantes. El prompt debe enfatizar "5 tweaks máximo, ordenados por impacto".

---

## E06-S06 — Orquestador `assist_application(job_id)`

**Como** dueño del sistema, **quiero** una función que orquesta los componentes anteriores en paralelo y devuelve el paquete completo, **para que** la latencia total sea <30s y la interfaz sea simple.

### Acceptance Criteria

- [ ] `src/jobhunter/application/assistant.py` con `async assist_application(session, job_id, llm_client) -> ApplicationPackage`.
- [ ] `ApplicationPackage` (Pydantic): `job_id`, `cv_variant: VariantRecommendation`, `cover_letter: CoverLetterResult`, `ats_keywords: ATSKeywordsResult`, `cv_tweaks: CVTweaksResult`, `total_cost_usd: float`, `total_duration_ms: int`, `estimated_apply_time_min: int`.
- [ ] Orquestación con `asyncio.gather`:
  1. Selector de variante (síncrono, rápido).
  2. En paralelo: cover letter generation + ATS keywords extraction.
  3. CV tweaks suggestion (depende del paso 2).
- [ ] Validación previa: si `job.tier not in {'A', 'B'}`, raise `JobNotAssistableError` (no perder llamadas API en jobs descartados).
- [ ] Persistencia: `cover_letter` se guarda en `Application` si existe; si no, se cachea para cuando se invoque `apply`.
- [ ] Logging estructurado de la corrida completa.
- [ ] Tests integración con todos los sub-componentes mockeados.

### Tasks

- [ ] Crear `assistant.py`
- [ ] Implementar `assist_application` con `asyncio.gather`
- [ ] Cache temporal en `_assist_cache` (in-memory dict por job_id, se borra tras `apply` o tras 1h)
- [ ] Tests integración

### Estimación: 1.5h

### Notas

- **`estimated_apply_time_min` calculado heurísticamente:** baseline 8 min, +1 min por cada `cv_tweak`, -2 min si todas las ATS keywords ya están en el CV.
- **`asyncio.gather` con paralelización** es clave para <30s. Cover letter (Opus) es la llamada más lenta (~10-15s); ATS keywords (Haiku) toma ~3s. Paralelizar ahorra 5-8s vs serial.

---

## E06-S07 — CLI: `jobhunter assist` + `apply` + `letter`

**Como** dueño del sistema, **quiero** comandos CLI para invocar el toolkit y registrar aplicaciones enviadas, **para que** el workflow diario sea: ver notificación → terminal → aplicar → registrar.

### Acceptance Criteria

- [ ] `jobhunter assist <job_id>` con flags:
  - [ ] `--output-dir DIR` (default: stdout) — escribir paquete a archivos.
  - [ ] `--no-letter` — solo variante + tweaks + keywords (no genera cover letter, ahorra costo).
  - [ ] `--cv-variant NAME` — overridear selector de variante.
  - [ ] Output: tabla rich con resumen + bloques formateados con cover letter, tweaks, keywords.
- [ ] `jobhunter letter <job_id>` con flags:
  - [ ] `--output FILE` (default: stdout).
  - [ ] `--cv-variant NAME`.
  - [ ] Solo genera cover letter (más rápido cuando ya tienes variante decidida).
- [ ] `jobhunter apply <job_id>` con flags:
  - [ ] `--method METHOD` (web/email/linkedin/referral, required).
  - [ ] `--cv-variant NAME` (required).
  - [ ] `--contact-name NAME`, `--contact-email EMAIL` (opcionales).
  - [ ] `--notes TEXT` (opcional).
  - [ ] Acción: crea `Application` con status='applied', transición de `Job` a `applied`.
  - [ ] Si hay cover letter en cache (de un `assist` previo), la persiste automáticamente.
- [ ] Tests CLI con `typer.testing.CliRunner`.

### Tasks

- [ ] Implementar 3 comandos
- [ ] Output rico con `rich.markdown.Markdown` para previews
- [ ] Tests

### Estimación: 2h

### Notas

- **Workflow ergonómico para operación diaria:**
  ```
  Telegram alert → jobhunter assist <job_id> --output-dir ~/applications/job-123/
                → cd ~/applications/job-123/, revisar cover.md, ajustar
                → aplicar manualmente vía web/email
                → jobhunter apply <job_id> --method web --cv-variant ai_python
  ```
- **`--no-letter`** útil cuando solo quieres validar variante + keywords antes de invertir en generar cover letter.

---

## E06-S08 — Tests con fixtures + tracker de aplicaciones

**Como** dueño del sistema, **quiero** tests end-to-end con fixtures realistas y verificación de que el tracker (`applications` table) refleja el estado correctamente, **para que** el ciclo completo "tier-A → cover letter → apply" sea robusto.

### Acceptance Criteria

- [ ] Fixtures grabadas en `tests/fixtures/application_assistant/`:
  - `cover_letter_response_python_ai.txt` (output real del Opus para job python AI).
  - `cover_letter_response_flutter.txt`.
  - `ats_keywords_response.json`.
  - `cv_tweaks_response.json`.
- [ ] `MockLLMClient` extendido (de E4-S08) para devolver fixtures según pattern del job.
- [ ] Tests end-to-end:
  - [ ] `assist_application` con job tier-A → `ApplicationPackage` completo y válido.
  - [ ] `assist_application` con job tier=REJECT → `JobNotAssistableError`.
  - [ ] `apply` crea `Application` con todos los campos correctos.
  - [ ] Cover letter cacheada de `assist` previo se persiste en `apply`.
  - [ ] Tests del selector de variante: 5 casos típicos cubiertos.
- [ ] Coverage ≥ 75% en módulo `application/`.

### Tasks

- [ ] Capturar fixtures reales (correr el toolkit contra 3 jobs, sanitizar outputs)
- [ ] Tests end-to-end en `tests/integration/application/`
- [ ] Update CI

### Estimación: 1.5h

### Notas

- **Capturar fixtures gasta ~$0.20** una vez (3 cover letters × $0.05 + tweaks + keywords). Ahorro infinito en CI.

---

## Definition of Ready para E7

E6 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con tests usando fixtures.
- [ ] `jobhunter assist <job_id>` ejecuta contra job real, output coherente, costo registrado en `llm_calls`.
- [ ] Workflow probado end-to-end: notificación tier-A → assist → ajuste manual → apply → `Application` registrada.
- [ ] Tiempo medido de oferta-tier-A a `apply` ejecutado: ≤ 10 min en al menos un test real.
- [ ] `cv_variants/*.template.md` documentados como ejemplo; `.local/cv_variants/` gitignored y populated localmente.
- [ ] Tag `v0.6.0` creado.

A partir de aquí, **E7 (Dashboard)** se puede empezar — toolkit funcional, ahora se necesita la vista panorámica.

---

## Anexo: ¿Por qué la insistencia en NO auto-aplicar?

Tentación recurrente en sistemas de búsqueda de empleo: añadir `playwright` y submit automático a portales. Razones para resistirla en este proyecto:

1. **Datos reales:** auto-apply masivo convierte <1% para roles senior. Aplicación cuidada con cover letter convierte 10-15%. Volumen × baja conversión = peor que volumen menor × alta conversión.

2. **Riesgo de ban:** LinkedIn, Indeed, Lever, Greenhouse — todos detectan automation. Una cuenta baneada es semanas para recuperar (si se logra).

3. **Costo:** cada portal tiene captchas, SSO flows, multi-step forms. Cobertura realista requiere mantener selectores Playwright para 20+ portales — semanas de trabajo, frágil ante UI changes.

4. **Calidad humana:** una frase específica en el cover letter ("vi que en su roadmap mencionan Y") se siente humana. Auto-apply nunca lo hará bien.

**Excepción legítima:** LinkedIn Easy Apply manual (botón único). Ahí auto-apply podría tener sentido. Pero queda fuera de scope para MVP — agregar en E11 si rinde el resto del sistema.

---

**Fin Documento J.**
