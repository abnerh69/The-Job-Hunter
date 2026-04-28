# Documento H — Backlog Nivel 2: Descomposición de E4 (AI Scoring Engine)

**Épica origen:** E4 — AI Scoring Engine (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 13–16 horas (2-3 sesiones de medio día).

**Convenciones:** mismas que documentos E, F, G. ID `E04-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E4 es el **cerebro del sistema**. Toma las ofertas crudas que E3 ingiere y, mediante el prompt maestro del Documento A, las clasifica en tiers A/B/C/REJECT con metadata estructurada. El output dispara las decisiones downstream: notificación inmediata (E5), aplicación asistida (E6), o archivo silencioso.

### Decisiones técnicas clave

1. **Prompt versionado en repo** (`prompts/scoring_v1.md`) — cualquier cambio se commitea, `score_version` se persiste con cada job, permite A/B testing histórico.
2. **Pydantic strict para validar respuesta IA** — la IA puede devolver JSON malformado; un schema Pydantic atrapa esto antes de que contamine la DB.
3. **Resilencia: fallos no pierden el job** — si la API cae, el job se queda en `status='new'` para retry en próxima corrida. Idempotencia.
4. **Dos modelos: Haiku para volumen, Sonnet/Opus opcional para re-score** — Haiku 4.5 cuesta ~$0.002/job, suficiente para 95% de casos.
5. **Costo observable** — cada llamada registra tokens y costo USD; alerta si excede budget mensual.
6. **Fixtures de respuestas IA grabadas** para tests reproducibles sin gastar API.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E04-S01 | Esquema Pydantic para respuesta del scoring | 1h | E2 cerrada | — |
| E04-S02 | Cargador de prompt versionado | 1h | S01 | con S03 |
| E04-S03 | Anthropic API client wrapper | 2h | E2 cerrada | con S02 |
| E04-S04 | Scorer principal: `JobScorer.score(job)` | 2h | S01, S02, S03 | — |
| E04-S05 | Pipeline batch + transición de estados | 2h | S04 | — |
| E04-S06 | Tracking de costos + alertas de budget | 1.5h | S03 | con S05 |
| E04-S07 | CLI: `jobhunter score` + comandos auxiliares | 1.5h | S05 | — |
| E04-S08 | Tests con fixtures de respuestas IA | 2h | S04, S05 | — |

### Camino crítico

```
E2 ─→ S01 ─→ S02 ─┐
              ↓    │
              S03 ─┴─→ S04 ─→ S05 ─→ S07 ─→ S08
              │            ↑
              └─→ S06 ─────┘
```

**Tiempo serial:** ~13h. **Con paralelización (S02+S03 juntos, S05+S06 juntos):** ~10h.

### Definition of Done de la épica (recordatorio)

```bash
# Procesa jobs en status='new' → tier asignado
jobhunter score --limit 50

# Re-correr no procesa los ya scoreados
jobhunter score --limit 50  # 0 procesados

# Forzar re-score (ej. tras cambiar prompt)
jobhunter score --rescore-tier-a --limit 10

# Costo observable
jobhunter scoring stats
# Output: 200 jobs scored last week, $0.42 spent, 0 errors

# Re-score automático con Sonnet para tier A (variante 7A del Doc A)
jobhunter score --rescore-tier-a-with sonnet
```

---

## E04-S01 — Esquema Pydantic para respuesta del scoring

**Como** dueño del sistema, **quiero** un Pydantic model estricto que valide la respuesta JSON del prompt maestro, **para que** respuestas malformadas de la IA fallen con error claro antes de contaminar la DB.

### Acceptance Criteria

- [ ] `src/jobhunter/scoring/schema.py` con clase `ScoringResult(BaseModel)` que refleja exactamente el schema del Documento A §3.
- [ ] Sub-modelos: `CompanyInfo`, `RoleInfo`, `CompensationInfo`, `LogisticsInfo`, `MatchAnalysis`, `Recommendation`.
- [ ] Enums: `Tier` (A/B/C/REJECT), `Action` (apply_now/apply_with_caveats/manual_review/skip), `Priority` (high/medium/low), `RemoteType`, `TimezoneRequirement`, `ContractType`, `CompanyStage`, `Seniority`.
- [ ] Validators: `fit_score` debe estar en [0, 100]; si `tier=REJECT`, debe haber al menos 1 `red_flag`; si `tier='A'`, no puede haber `red_flags`.
- [ ] Schema de "respuesta inválida" (`InvalidScoringResponse`) cuando la IA decide que la oferta es spam: `{valid: false, reason: str}`.
- [ ] Función `parse_scoring_response(raw_text: str) -> ScoringResult | InvalidScoringResponse` que tolera markdown fences (` ```json ... ``` `) y los strippea antes de parsear.
- [ ] Tests unitarios cubren: respuesta válida típica, respuesta REJECT, respuesta `valid=false`, JSON malformado (raise), JSON con campo extra (tolerar o no — decidir), `tier='A'` con red_flags (raise).

### Tasks

- [ ] Crear `src/jobhunter/scoring/__init__.py`
- [ ] Crear `src/jobhunter/scoring/schema.py` con todos los modelos
- [ ] Implementar `parse_scoring_response` con limpieza de markdown fences (regex simple)
- [ ] Tests en `tests/unit/scoring/test_schema.py`
- [ ] Decisión: `model_config = ConfigDict(extra='forbid')` para fallar en campos extra (más estricto, mejor para detectar drift del prompt).

### Estimación: 1h

### Notas

- **Pydantic strict vs lenient.** Empezar strict (`extra='forbid'`) — si la IA devuelve un campo nuevo no esperado, lo sabes inmediatamente. Si después se vuelve molesto, relajar a `extra='ignore'`.
- **Markdown fences.** Aunque el prompt diga "JSON sin fences", Claude a veces los devuelve. El parser tolera ambos casos.

---

## E04-S02 — Cargador de prompt versionado

**Como** dueño del sistema, **quiero** el prompt maestro almacenado en archivos versionados con el código, **para que** cada cambio quede en git history, sea diffable, y cada job persista qué versión lo scoreó.

### Acceptance Criteria

- [ ] Directorio `prompts/scoring/` en el repo con archivos `v1.md`, `v2.md`, etc.
- [ ] `prompts/scoring/v1.md` contiene el prompt maestro completo del Documento A (system + candidate profile + user template + rúbrica + few-shots).
- [ ] `src/jobhunter/scoring/prompt.py` con función `load_prompt(version: str = 'latest') -> ScoringPrompt`.
- [ ] `ScoringPrompt` (Pydantic) con campos: `version`, `system_prompt`, `user_template`, `loaded_from`.
- [ ] `'latest'` resuelve al archivo de versión semánticamente mayor (parseo de nombre).
- [ ] Función `render_user_prompt(template, job: Job) -> str` que sustituye placeholders (`{title}`, `{company}`, etc.) con valores del job.
- [ ] Tests cubren: cargar v1, cargar 'latest', placeholders sustituidos, error si placeholder no existe en el job.

### Tasks

- [ ] Crear `prompts/scoring/v1.md` copiando el contenido del Documento A
- [ ] Estructura del archivo: secciones delimitadas por headers markdown (`## SYSTEM`, `## USER_TEMPLATE`) que el loader parsea
- [ ] Crear `src/jobhunter/scoring/prompt.py` con `load_prompt` y `render_user_prompt`
- [ ] Decidir engine de templating: `str.format()` simple es suficiente (no se necesita Jinja2 para esto)
- [ ] Tests unitarios

### Estimación: 1h

### Paralelizable con

S03.

### Notas

- **Versionado semántico simple:** `v1.md`, `v2.md`. No hace falta `v1.0.0.md` — el granularidad mensual es suficiente.
- **Por qué archivo y no constante Python:** los prompts son largos (~150 líneas). En archivo `.md` se renderiza bonito en GitHub, se diffea claro en PRs, y Claude (asistiendo en ediciones) puede modificarlo sin tocar código.

---

## E04-S03 — Anthropic API client wrapper

**Como** dueño del sistema, **quiero** un wrapper robusto sobre el SDK `anthropic` con retry, timeout, manejo de errores, y captura de tokens/costo, **para que** el scorer (S04) y futuros consumidores (E6 cover letters) lo reusen.

### Acceptance Criteria

- [ ] `src/jobhunter/llm/anthropic_client.py` con clase `AnthropicLLMClient`.
- [ ] Método `async complete(system: str, user: str, model: str, max_tokens: int = 1500) -> LLMResponse`.
- [ ] `LLMResponse` (Pydantic): `text`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `stop_reason`.
- [ ] Retry con `tenacity`: exponential backoff (1s, 2s, 4s, max 3) en `RateLimitError`, `APIConnectionError`, `InternalServerError`.
- [ ] **No retry** en `BadRequestError`, `AuthenticationError` (errores de configuración, fallar rápido).
- [ ] Timeout configurable (default 60s para scoring; 120s para cover letters).
- [ ] Cost calculator: tabla de precios por modelo en `src/jobhunter/llm/pricing.py` (input/output USD per million tokens).
- [ ] Logging estructurado: cada llamada log con `model`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `attempt`.
- [ ] Tests con `anthropic` mockeado (no consume API real).

### Tasks

- [ ] Verificar pricing actualizado en https://docs.claude.com/en/docs/about-claude/pricing — hardcodear con comentario "verified YYYY-MM-DD"
- [ ] Crear módulo `src/jobhunter/llm/__init__.py`
- [ ] Crear `src/jobhunter/llm/pricing.py`:
  ```python
  # USD per million tokens, verified YYYY-MM-DD
  PRICING = {
      "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
      "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
      "claude-opus-4-7": {"input": 15.0, "output": 75.0},
  }
  
  def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float: ...
  ```
- [ ] Crear `src/jobhunter/llm/anthropic_client.py` con `AnthropicLLMClient`
- [ ] Tests: respuesta exitosa, retry en rate limit, no retry en auth error, cálculo correcto de costo

### Estimación: 2h

### Paralelizable con

S02.

### Notas

- **Web search para pricing.** Antes de implementar, verifica precios actuales (cambia ocasionalmente). Si no estás seguro, marca con `# TODO: verify pricing` y manda un mensaje al implementar.
- **Async vs sync SDK.** Usar `AsyncAnthropic` — coherente con el resto del sistema y permite paralelizar scoring batch.

---

## E04-S04 — Scorer principal: `JobScorer.score(job)`

**Como** dueño del sistema, **quiero** una función que tome un `Job`, lo envíe al modelo con el prompt maestro, valide la respuesta, y devuelva un `ScoringResult` listo para persistir, **para que** el pipeline batch (S05) tenga la unidad de trabajo bien encapsulada.

### Acceptance Criteria

- [ ] `src/jobhunter/scoring/scorer.py` con clase `JobScorer`.
- [ ] Constructor: `JobScorer(llm_client, prompt_version='latest', model='claude-haiku-4-5-20251001')`.
- [ ] Método `async score(job: Job) -> ScoringOutcome` donde `ScoringOutcome` envuelve: `result: ScoringResult | InvalidScoringResponse`, `model`, `prompt_version`, `cost_usd`, `duration_ms`, `raw_response: str`.
- [ ] Trunca `job.description` a ~8000 caracteres antes de pasarlo (proteger context window).
- [ ] Si la respuesta no parsea como JSON válido, hacer **un retry** con instrucción reforzada ("Respond with valid JSON only, no preamble"); si falla de nuevo, raise `ScoringParseError` con `raw_response` para debug.
- [ ] Tests cubren: scoring exitoso, retry en JSON malformado primer intento, fallo definitivo tras retry.

### Tasks

- [ ] Crear excepciones custom: `ScoringError` (base), `ScoringParseError`, `ScoringAPIError`
- [ ] Implementar `JobScorer.score()` con:
  1. Cargar prompt
  2. Render user prompt con `job`
  3. Llamar `llm_client.complete()`
  4. Parsear con `parse_scoring_response`
  5. En fallo de parsing, retry con prompt reforzado
  6. Devolver `ScoringOutcome`
- [ ] Función `_truncate_description(text, max_chars=8000)` que corta inteligente (no a media palabra)
- [ ] Tests con LLM client mockeado

### Estimación: 2h

### Notas

- **Truncate description.** 8000 chars ≈ 2000 tokens, deja espacio para el resto del prompt y la respuesta. Para roles con descripción muy larga, los primeros 8000 chars suelen contener stack + benefits + rango — lo importante.
- **Retry de parsing.** Modelos LLM pequeños como Haiku ocasionalmente meten texto antes/después del JSON. Un retry con prompt reforzado salva ~80% de estos casos.

---

## E04-S05 — Pipeline batch + transición de estados

**Como** dueño del sistema, **quiero** una función que tome todos los jobs en `status='new'`, los scoree en paralelo controlado, persista resultados, y maneje las transiciones de estado, **para que** el cron de E8 simplemente la invoque.

### Acceptance Criteria

- [ ] `src/jobhunter/scoring/pipeline.py` con `async score_pending_jobs(session, limit: int = 100, concurrency: int = 5) -> ScoringBatchReport`.
- [ ] Selecciona jobs `status='new'` ordenados por `scraped_at ASC` (FIFO).
- [ ] Procesa en paralelo controlado con `asyncio.Semaphore(concurrency)` (default 5 — respeta rate limits Anthropic Tier 1).
- [ ] Por cada job:
  - **Éxito + tier A/B:** persiste `score_data`, `tier`, `fit_score`, `score_model`, `score_version`, `scored_at`, `status='queued'`.
  - **Éxito + tier C:** mismo + `status='manual_review'`.
  - **Éxito + tier REJECT:** mismo + `status='rejected'`.
  - **Respuesta `valid=false`:** persiste razón, `status='archived'`.
  - **Error API/parsing:** **NO modifica** el job (queda en `status='new'` para retry); log estructurado con error.
- [ ] Comando para re-scoring: función separada `rescore_jobs(filter, with_model)` para variante 7A del Doc A (re-score tier A con Sonnet).
- [ ] `ScoringBatchReport` (Pydantic): `total_processed`, `success_count`, `failed_count`, `tier_distribution: dict[Tier, int]`, `total_cost_usd`, `duration_seconds`.
- [ ] Tests cubren: batch exitoso, fallo aislado (no detiene el resto), idempotencia (re-correr no procesa los ya scoreados).

### Tasks

- [ ] Crear `src/jobhunter/scoring/pipeline.py`
- [ ] Implementar `score_pending_jobs` con `asyncio.gather` + `Semaphore`
- [ ] Función auxiliar `_persist_scoring_outcome(session, job, outcome)` que centraliza la lógica de transición de estado (testeable aisladamente)
- [ ] Implementar `rescore_jobs(filter_dict, with_model)` para variante 7A
- [ ] Tests con scorer mockeado

### Estimación: 2h

### Notas

- **Idempotencia clave.** El cron (E8) correrá cada 8h. Si una corrida anterior ya scoreó un job, la siguiente no debe re-procesarlo. Filtrar por `status='new'` lo garantiza.
- **Concurrency=5.** Anthropic Tier 1 permite ~50 req/min. Con 5 workers concurrentes y latencia ~3s por scoring, somos cómodamente sub-rate-limit.

---

## E04-S06 — Tracking de costos + alertas de budget

**Como** dueño del sistema, **quiero** observabilidad sobre el costo del scoring y alertas si excede el budget mensual, **para que** un bug (ej. loop infinito de retry) no me genere $200 de factura sin avisar.

### Acceptance Criteria

- [ ] Nueva tabla `llm_calls` (migration): `id`, `called_at`, `model`, `purpose` (scoring/cover_letter/etc.), `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `success: bool`, `job_id: UUID | null`.
- [ ] `LLMCallRepo` con método `record_call(...)` y `monthly_total_usd(year, month)`.
- [ ] `AnthropicLLMClient` (de S03) integra: cada `complete()` registra automáticamente vía repo.
- [ ] Configuración nueva en `Settings`: `llm_monthly_budget_usd: float = 25.0`.
- [ ] Función `check_budget(session) -> BudgetStatus` con campos: `current_month_spend`, `budget`, `pct_used`, `is_exceeded`, `is_warning` (>80%).
- [ ] Si `is_exceeded`, el scorer (S04) raise `BudgetExceededError` antes de llamar a la API — para failsafe.
- [ ] Comando CLI `jobhunter scoring stats` muestra: total mes actual, total última semana, breakdown por modelo, tasa de éxito.
- [ ] Tests cubren: registro de llamadas, agregación mensual, throwing en budget exceeded.

### Tasks

- [ ] Migration Alembic para `llm_calls`
- [ ] `LLMCallRepo` en `src/jobhunter/db/repos/llm_calls.py`
- [ ] Modificar `AnthropicLLMClient` para inyectar repo y registrar llamadas (incluso fallidas, con `success=false`)
- [ ] Crear `src/jobhunter/llm/budget.py` con `check_budget` y `BudgetExceededError`
- [ ] Integrar check en `JobScorer.score()`
- [ ] Comando CLI `scoring stats`
- [ ] Tests

### Estimación: 1.5h

### Paralelizable con

S05.

### Notas

- **Por qué tabla separada y no extender `jobs`.** `llm_calls` también capturará cover letters (E6), re-scorings, futuros usos. Separar permite analytics cross-purpose.
- **Budget de $25/mes** es generoso para empezar. Con Haiku para scoring (~$0.002/job × 800 jobs = $1.60) y Opus para cover letters (~$0.10 × 30 = $3), el real será ~$5-8. El budget de $25 es failsafe ante bugs.

---

## E04-S07 — CLI: `jobhunter score` + comandos auxiliares

**Como** dueño del sistema, **quiero** comandos CLI para operación manual del scoring, **para que** desarrollo, debugging, y re-scoring tras cambios de prompt sean inmediatos.

### Acceptance Criteria

- [ ] Comando `jobhunter score` con flags:
  - [ ] `--limit N` (default: 100) — máximo jobs a procesar.
  - [ ] `--concurrency N` (default: 5).
  - [ ] `--model NAME` (default: from settings) — overridear modelo (ej. para experimentar con Sonnet).
  - [ ] `--prompt-version VER` (default: latest) — usar versión específica de prompt.
  - [ ] `--dry-run` — score pero no persiste.
- [ ] Comando `jobhunter score-job <JOB_ID>` para scoring puntual de un job (debug).
- [ ] Comando `jobhunter rescore` con flags:
  - [ ] `--tier A` (filtra por tier actual)
  - [ ] `--with-model NAME` (modelo a usar)
  - [ ] `--limit N`
- [ ] Comando `jobhunter scoring stats` (de S06).
- [ ] Output con `rich`: tabla con tier distribution, costo, errores; barra de progreso durante batch.
- [ ] Exit code 1 si tasa de éxito < 90% (señal para alerting en cron).

### Tasks

- [ ] Implementar comandos en `src/jobhunter/cli.py` (subgroup `score` + `rescore` + `scoring stats`)
- [ ] Progress bar con `rich.progress.Progress`
- [ ] Tests CLI con `typer.testing.CliRunner`

### Estimación: 1.5h

### Notas

- **`score-job <ID>` para debug.** Cuando el prompt da resultados raros para un job específico, este comando permite re-correr aislado y ver `raw_response` completa.

---

## E04-S08 — Tests con fixtures de respuestas IA

**Como** dueño del sistema, **quiero** tests que no consuman la API real pero sí validen el flujo end-to-end, **para que** CI sea rápido, gratis, y reproducible.

### Acceptance Criteria

- [ ] `tests/fixtures/scoring_responses/` con archivos JSON capturados de respuestas reales del modelo:
  - `tier_a_python_ai.json` — caso ideal (Senior Python AI, salario alto, B2B-friendly).
  - `tier_a_flutter.json` — Flutter senior, remote global.
  - `tier_b_borderline.json` — match decente pero no ideal.
  - `tier_c_manual_review.json` — caso ambiguo.
  - `reject_eu_only.json` — REJECT por requerir EU permit.
  - `reject_low_salary.json` — REJECT por salario debajo de floor.
  - `invalid_response.json` — respuesta `{valid: false, reason: ...}`.
  - `malformed_json.txt` — JSON roto (para test de retry).
- [ ] `MockLLMClient` que devuelve respuesta de fixture según pattern del job input (ej. si título contiene "Python AI", devuelve `tier_a_python_ai.json`).
- [ ] Tests end-to-end del pipeline: job → scorer → repo → verificar `Job.tier`, `Job.status`, `Job.score_data` en DB.
- [ ] Test que verifica `BudgetExceededError` si se excede budget.
- [ ] Test de batch con 20 jobs mockeados, verifica distribución de tiers correcta.

### Tasks

- [ ] Capturar fixtures: correr `JobScorer.score()` real contra 8 jobs reales variados, guardar `raw_response` como fixture JSON
- [ ] Sanitizar fixtures (revisar que no contengan info sensible)
- [ ] Implementar `MockLLMClient` en `tests/conftest.py`
- [ ] Tests integración en `tests/integration/scoring/`
- [ ] Update `.github/workflows/ci.yml` (deps ya están)

### Estimación: 2h

### Notas

- **Fixtures ≠ snapshots.** Los fixtures son inputs estables. Si el prompt cambia, los fixtures NO cambian (siguen siendo respuestas válidas históricas). Si quieres validar que el prompt actual sigue produciendo el tier esperado para X job, eso es otro test (más caro, opcional).
- **Capturar fixtures gasta ~$0.02.** Una sola vez. No optimizar.

---

## Definition of Ready para E5

E4 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con tests usando fixtures (sin red real).
- [ ] `jobhunter score --limit 10` ejecuta contra jobs reales y persiste correctamente.
- [ ] Idempotencia verificada manualmente (re-correr no re-scorea).
- [ ] `jobhunter scoring stats` muestra costo real coherente.
- [ ] DB tiene 50+ jobs con `tier` asignado y mix de A/B/C/REJECT.
- [ ] Tag `v0.4.0` creado.

A partir de aquí, **E5 (Notification System)** se puede empezar — hay tier A reales para notificar.

---

## Anexo: Validación temprana del prompt

**Recomendación operativa** (no es story, es proceso): tras cerrar E4-S04, antes de continuar con S05, ejecutar manualmente:

```bash
# Tomar 20 jobs reales recién ingestados y scorearlos
jobhunter score-job <id1>
jobhunter score-job <id2>
...
```

Revisar cada `score_data` y comparar con tu intuición:
- ¿Qué jobs marcó tier A que tú habrías marcado B?
- ¿Qué red flags detectó vs perdió?
- ¿Hay patrones donde el `cover_letter_angle` es genérico o irrelevante?

Si hay drift significativo (>20% de mismatches), iterar el prompt en `prompts/scoring/v2.md` antes de procesar a escala. **No es overkill** — el prompt es el cerebro del sistema; calibrarlo con 20 ejemplos reales antes de procesar 1000 ahorra horas de revisión manual después.

---

**Fin Documento H.**
