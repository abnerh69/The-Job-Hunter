# Documento O — Backlog Nivel 2: Descomposición de E11 (Metrics, Analytics & Continuous Tuning)

**Épica origen:** E11 — Metrics, Analytics & Continuous Tuning (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 14–17 horas (3 sesiones de medio día).

**Convenciones:** mismas que documentos E–N. ID `E11-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E11 cierra el ciclo de mejora continua del sistema. Hasta aquí cada épica ha agregado métricas locales (E4 costos LLM, E5 tasa de envío, E6 cover letters, E9 outreach response rate, E10 precision/recall del matcher). E11 las **consolida cross-épica**, añade **A/B testing infraestructural** para iterar prompts y templates, genera **reportes mensuales narrativos**, y detecta **regresiones automáticamente**.

**Principio operativo:** sin esta épica, el sistema funciona pero opera en piloto automático sin reflexión. E11 lo convierte en una **máquina que aprende de sí misma** — el prompt v1 dio response rate X%, v2 ajustado dio X+Y%, mantenemos v2; templates A_inhouse generan más respuestas que C_senior, ajustamos cadencia.

### Decisiones técnicas clave

1. **Servicios de métricas centralizados** en `src/jobhunter/analytics/` — toda query de métrica vive aquí, no duplicada en dashboard/digest/CLI. DRY brutal.
2. **A/B testing por feature flag** — cada nueva versión de prompt/template tiene un flag `prompt_version_split: dict[str, float]` que distribuye tráfico (50/50, 80/20, etc.). Los resultados se persisten con `prompt_version` para análisis post-hoc.
3. **Reportes mensuales generados por LLM** — datos crudos se pasan a Sonnet con prompt analítico, output: narrativa de 1-2 páginas con insights, recomendaciones, anomalías. Coste ~$0.10/mes.
4. **Regresion detection automatizada** — workflow semanal compara métricas de la semana actual vs últimas 4. Si hay drop significativo (>30% en cualquier métrica clave), alerta Telegram.
5. **Recomendaciones automáticas accionables** — el sistema analiza métricas y sugiere "tu tasa de respuesta cayó 30% — considera revisar el prompt v2" o "fuente Arbeitnow no produce A-tier hace 14 días — revisar circuit breaker o filtros".
6. **Export de reportes a PDF** — para archivado y portfolio piece (sí, mostrar el reporte mensual auto-generado del propio sistema en una entrevista es una historia poderosa).
7. **NO hay "Auto-tuning" automático** — el sistema sugiere cambios al prompt/template/filtros, pero NO los aplica sin aprobación humana. Mismo principio que E10 con sugerencias de cambio de estado.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E11-S01 | Servicio de métricas consolidadas | 2.5h | E4–E10 | — |
| E11-S02 | A/B testing infrastructure (feature flags) | 2h | E4 cerrada | con S01 |
| E11-S03 | Detector de regresiones + alertas | 2h | S01 | con S04 |
| E11-S04 | Análisis de "false rejects" y "missed opportunities" | 2h | S01 | con S03 |
| E11-S05 | Generador de reportes mensuales (Sonnet) | 2h | S01 | — |
| E11-S06 | Recomendaciones automáticas accionables | 2h | S03, S04 | — |
| E11-S07 | Export PDF + UI dashboard | 1.5h | S05, S06 | — |
| E11-S08 | Tests + workflow semanal de análisis | 1.5h | S03, S05, S06 | — |

### Camino crítico

```
E4–E10 ─→ S01 ─→ ┬─→ S02 ─┐
                 ├─→ S03 ─┤
                 ├─→ S04 ─┼─→ S06 ─→ S07 ─→ S08
                 └─→ S05 ─┘
```

**Tiempo serial:** ~14h. **Con paralelización (S02+S03+S04+S05 juntos):** ~10h.

### Definition of Done de la épica

```bash
# Métricas consolidadas accesibles desde un comando único
jobhunter analytics dashboard
# → vista global cross-épica: pipeline, costos, calidad, A/B tests activos

# A/B test de prompt
jobhunter analytics ab-test create --name "scoring_v2_test" \
  --variants v1=0.5,v2=0.5 --metric tier_a_precision

jobhunter analytics ab-test results scoring_v2_test
# → tabla con sample size, conversion rate por variant, statistical significance

# Reporte mensual generado
jobhunter analytics report --month 2026-04 --output pdf
# → PDF con narrativa de Sonnet, gráficas, recomendaciones

# Detección de regresiones (workflow semanal)
gh workflow run weekly-analysis.yml
# → si hay drop, alerta Telegram con root cause analysis

# Recomendaciones accionables
jobhunter analytics recommendations
# → "Tu tasa de respuesta cayó 30%, revisa prompt v2"
# → "Fuente RemoteOK no produce A-tier hace 14 días"
# → "El template C_senior tiene 0% response rate, considerar pausar"
```

---

## E11-S01 — Servicio de métricas consolidadas

**Como** dueño del sistema, **quiero** un módulo único que centralice todas las queries de métricas cross-épica, **para que** dashboard, digest, CLI, y reportes consuman las mismas funciones — DRY brutal y ningún risk de divergencia entre vistas.

### Acceptance Criteria

- [ ] Crear `src/jobhunter/analytics/` con submódulos por dominio:
  - `pipeline_metrics.py` — funnel de descubrimiento → aplicación → entrevista → oferta.
  - `quality_metrics.py` — tier distribution, fit_score por fuente, false rejects.
  - `cost_metrics.py` — LLM usage, cost per outcome (cost per tier-A, cost per application).
  - `outreach_metrics.py` — response rate por template/market/score.
  - `email_metrics.py` — precision/recall del matcher (de E10).
  - `prompt_metrics.py` — performance por prompt_version (foundation para A/B testing).
- [ ] Cada submódulo expone funciones puras: `get_funnel(session, date_range) -> FunnelResult`, etc.
- [ ] Pydantic models para todos los resultados (testeables, serializables a JSON).
- [ ] **Refactor de dashboard E7 y digest E5** para consumir estos servicios en lugar de queries inline.
- [ ] Caching coordinado: `@lru_cache` para queries deterministas, `@st.cache_data` en Streamlit, `redis` opcional si rinde — pero default in-memory suficiente.
- [ ] Tests unitarios cubren cada función con DB seeded `rich`.

### Tasks

- [ ] Crear estructura `analytics/` con submódulos.
- [ ] Migrar queries del dashboard E7-S06 a `analytics/`.
- [ ] Migrar queries del digest E5-S06 a `analytics/`.
- [ ] Pydantic result models.
- [ ] Tests unitarios.
- [ ] Verificar que dashboard E7 y digest E5 siguen funcionando tras migración.

### Estimación: 2.5h

### Notas

- **Esto es deuda técnica saneada.** Hasta E10, queries de métricas pueden estar duplicadas (una versión en `dashboard/services/metrics.py`, otra en `notify/digest.py`, otra en `outreach/stats`). E11-S01 consolida, otras stories de E11 dependen de esta consolidación.
- **No reinventar SQL.** Aprovechar la materialized view `weekly_metrics` (de E2-S05) y `llm_calls` (de E4-S06). Sumar lógica nueva solo donde no existe.

---

## E11-S02 — A/B testing infrastructure

**Como** dueño del sistema, **quiero** infraestructura ligera de A/B testing para prompts y templates, **para que** pueda comparar versiones empíricamente en lugar de adivinar.

### Acceptance Criteria

- [ ] Tabla nueva `ab_tests` (migration):
  - `id` UUID PK.
  - `name` VARCHAR UNIQUE — ej. "scoring_v2_test".
  - `description` TEXT.
  - `metric_target` VARCHAR — ej. "tier_a_precision", "outreach_response_rate".
  - `variants` JSONB — ej. `{"v1": 0.5, "v2": 0.5}`.
  - `started_at` TIMESTAMPTZ.
  - `ended_at` TIMESTAMPTZ NULLABLE.
  - `status` VARCHAR (enum: `active`, `concluded`, `aborted`).
  - `conclusion` TEXT NULLABLE — analista escribe su conclusión.
- [ ] CLI `jobhunter analytics ab-test create --name X --variants v1=0.5,v2=0.5 --metric M`.
- [ ] CLI `jobhunter analytics ab-test results <NAME>` — muestra tabla:
  - Variant, sample size, metric value, confidence interval, statistical significance vs control.
- [ ] CLI `jobhunter analytics ab-test conclude <NAME> --winner v2 --conclusion "..."`.
- [ ] **Selector de variant** en código (`src/jobhunter/analytics/ab_testing.py`):
  - `select_variant(test_name: str, entity_id: str) -> str` — determinístico por hash(entity_id) para que el mismo job siempre vaya a la misma variant (no flaps).
  - Si no hay test activo para `test_name`, devuelve "default".
- [ ] Integración en E4 scorer y E9 outreach generator: ambos consultan `select_variant("scoring_prompt", job.id)` antes de cargar el prompt.
- [ ] Cálculo de significancia estadística simple (Z-test para proporciones, suficiente para nuestro caso).
- [ ] Tests cubren: assignment determinístico, variants distribution correcta, significance calculation con sample size pequeño.

### Tasks

- [ ] Migration `ab_tests` table.
- [ ] Modelo SQLAlchemy + repo.
- [ ] `src/jobhunter/analytics/ab_testing.py` con `select_variant` + `compute_significance`.
- [ ] CLI commands.
- [ ] Integración en scorer (E4) y outreach generator (E9).
- [ ] Tests.

### Estimación: 2h

### Paralelizable con

S01.

### Notas

- **Determinístico por hash:** `hash(entity_id + test_name) % 100` → bucket. Mismo entity siempre cae en mismo bucket. Sin esto, un job sería scoreado por v1 una vez, v2 otra vez, distorsionando el test.
- **Sample size mínimo para conclusión:** 30 por variant es el rule of thumb estadístico. CLI advierte si < 30 al pedir results.
- **No es Optimizely.** Es A/B testing artesanal pero suficiente. Si el sistema crece, considerar GrowthBook o Unleash.

---

## E11-S03 — Detector de regresiones + alertas

**Como** dueño del sistema, **quiero** detección automática de drops significativos en métricas clave, **para que** un cambio que rompe sutilmente el sistema (ej. nueva versión de prompt que baja precision) sea visible en horas, no en semanas.

### Acceptance Criteria

- [ ] Comando CLI `jobhunter analytics check-regressions` que:
  1. Compara métricas de la **última semana** contra **promedio de las 4 semanas anteriores** (excluyendo la actual).
  2. Métricas monitoreadas:
     - Tier A rate (% de jobs ingestados que terminan tier A).
     - Application rate (% de tier A que se aplican).
     - Response rate (% de aplicaciones con cualquier respuesta).
     - Outreach response rate.
     - Email matcher precision.
     - Pipeline cycle success rate.
  3. Threshold de regresión: drop > 30% relativo, o drop > 5 puntos porcentuales absolutos (lo que sea mayor).
  4. Si detectado, output structured con: métrica, valor anterior, valor actual, % drop, contexto (¿hubo deploy reciente? ¿cambio de prompt?).
- [ ] Comando CLI `jobhunter analytics check-anomalies` complementario para detectar **anomalías upward** (subida brusca también puede indicar bug — ej. precision súbitamente al 100% probablemente es bug en cálculo).
- [ ] Si regresión detectada, dispara alerta Telegram con:
  - Métrica afectada y magnitud.
  - Contexto inferido (commits recientes, prompts cambiados, configs).
  - Link al dashboard.
  - Sugerencia: "Considera correr `analytics report --week-ending YYYY-MM-DD` para análisis completo".
- [ ] **Anti-flapping:** si la misma regresión ya alertó en últimos 3 días, no re-alerta (a menos que empeoró 20%+).
- [ ] Tests con DB seeded simulando drops.

### Tasks

- [ ] Implementar `check-regressions` con queries de S01.
- [ ] Implementar `check-anomalies`.
- [ ] Lógica de alerting con anti-flapping (usa `notifications_sent` con dedup_key).
- [ ] Integración con sistema de alertas de E8.
- [ ] Tests con scenarios de regresión simulados.

### Estimación: 2h

### Paralelizable con

S04.

### Notas

- **Threshold conservador para evitar false positives.** Drop de 30% relativo es significativo; 10% puede ser ruido normal en sample size pequeño. Si el sistema rinde y tiene más data, ajustar a 20%.
- **Contexto inferido es valioso.** "Tu precision cayó 35% el día después que mergeaste el prompt v3" es accionable. "Tu precision cayó 35%" sin contexto te deja googleando.

---

## E11-S04 — Análisis de "false rejects" y "missed opportunities"

**Como** dueño del sistema, **quiero** identificar jobs que el sistema marcó REJECT pero que en retrospectiva eran válidos, **para que** pueda calibrar el prompt y no perder oportunidades silenciosamente.

### Acceptance Criteria

- [ ] CLI `jobhunter analytics false-rejects [--limit N]`:
  - Query: jobs `tier='REJECT'` en últimos 60 días donde el usuario, manualmente desde dashboard, los promovió (`status='archived' → 'queued'` con event en `application_events` o similar trail).
  - Output: lista con título, empresa, razón original de REJECT, razón de promoción manual.
- [ ] CLI `jobhunter analytics missed-opportunities`:
  - Heurística: jobs `tier='REJECT'` donde el `red_flag` que los marcó es ahora menos común en la población (ej. "EU permit required" puede ser sobre-restrictivo si el sistema rinde con LATAM-friendly companies).
  - Output: lista de candidatos a re-score con prompt actualizado.
- [ ] CLI `jobhunter analytics rescore-suspicious [--limit N --confirm]`:
  - Toma los top-N de `missed-opportunities`, los re-scorea con el prompt actual (puede ser una versión nueva que cambió el balance).
  - Si re-score difiere significativamente (REJECT → A/B), reporta y permite promover.
- [ ] Integración: estos análisis aparecen como sección en dashboard E7 (Analytics page futura) y en reporte mensual (S05).
- [ ] Tests con DB seeded.

### Tasks

- [ ] Migration: añadir columna `manually_promoted_at` y `manually_promoted_reason` a `jobs` (o usar `application_events` extendido).
- [ ] Implementar comandos CLI.
- [ ] Heurística de `missed-opportunities`.
- [ ] Tests.

### Estimación: 2h

### Paralelizable con

S03.

### Notas

- **"Manualmente promovido" es la señal más clara de false reject.** Si el usuario explícitamente hizo override del REJECT del sistema, eso es feedback ground truth.
- **`missed-opportunities` es exploratoria.** Es heurística, no certeza. El usuario decide si promover. Sirve más como "lista de cosas a revisar" que como "deuda".

---

## E11-S05 — Generador de reportes mensuales (Sonnet)

**Como** dueño del sistema, **quiero** un reporte mensual narrativo generado por LLM con insights, recomendaciones, y anomalías, **para que** tenga visión cualitativa además de las métricas crudas.

### Acceptance Criteria

- [ ] CLI `jobhunter analytics report --month YYYY-MM [--output md|html|pdf]`.
- [ ] Pipeline de generación:
  1. Recolectar todas las métricas del mes desde S01.
  2. Comparar contra mes anterior y trimestre anterior.
  3. Identificar top 3 cambios significativos.
  4. Pasar todo a Sonnet con prompt analítico que produce:
     - **Resumen ejecutivo** (1 párrafo).
     - **Highlights** (3-5 logros, expresados en métricas concretas).
     - **Lowlights** (3-5 problemas o regresiones).
     - **Anomalías** observadas.
     - **Recomendaciones priorizadas** (top 5).
     - **Predicciones** para próximo mes basadas en tendencia.
- [ ] Prompt versionado en `prompts/analytics_report/v1.md`.
- [ ] Modelo: Sonnet 4.6 (calidad alta, costo bajo: ~$0.10 por reporte).
- [ ] Output formats:
  - `md` — markdown puro (default).
  - `html` — con CSS embebido para email-friendly.
  - `pdf` — usa `weasyprint` para conversión MD→HTML→PDF.
- [ ] Si `--month` no se especifica, default: mes anterior completo.
- [ ] Reportes guardados en `reports/YYYY-MM-monthly.{md,pdf}` automáticamente.
- [ ] Tests con LLM mockeado.

### Tasks

- [ ] Crear `prompts/analytics_report/v1.md` (prompt cuidadosamente diseñado).
- [ ] Implementar pipeline de recolección + generación.
- [ ] Integración con `weasyprint` para PDF.
- [ ] CLI command.
- [ ] Tests con fixture de respuesta LLM.

### Estimación: 2h

### Notas

- **Prompt design crítico.** El reporte debe ser HONESTO sobre los lowlights. Anti-pattern: LLMs tienden a sugar-coat. El prompt debe explícitamente pedir "ser brutal sobre lo que no funcionó".
- **Reporte mensual = portfolio piece.** Mostrar el reporte auto-generado del sistema mismo en entrevistas (especialmente si aplicas a roles AI/ML) es una historia poderosa.

---

## E11-S06 — Recomendaciones automáticas accionables

**Como** dueño del sistema, **quiero** un comando que produzca recomendaciones específicas y accionables sobre qué cambiar para mejorar resultados, **para que** la operación sea data-driven, no intuición.

### Acceptance Criteria

- [ ] CLI `jobhunter analytics recommendations` produce lista de recomendaciones con:
  - **Acción específica:** ej. "Iterar prompt scoring v2 a v3", "Pausar template C_senior", "Revisar circuit breaker de RemoteOK".
  - **Razón data-driven:** ej. "Tu tasa de respuesta cayó de 12% a 4% tras el cambio del 14 abril".
  - **Impacto estimado:** ej. "Resolver esto recuperaría ~3-5 matches A-tier por semana".
  - **Esfuerzo estimado:** Low / Medium / High.
  - **Prioridad:** P1 / P2 / P3.
- [ ] Reglas heurísticas implementadas (no LLM por ahora — heurística determinística es más predecible):
  - Si tasa de respuesta de un template es 0% en últimas 4 semanas con ≥10 sends → recomienda pausar.
  - Si fuente no produce A-tier en 14 días → recomienda revisar filtros o circuit breaker.
  - Si prompt v actual tiene precision <80% en últimas 4 semanas (vs prev de 90%+) → recomienda rollback.
  - Si más de 30% de jobs en `manual_review` están sin decisión > 7 días → recomienda revisar threshold de tier C.
  - Si costo LLM mensual >80% del budget → recomienda revisión de uso.
  - Si circuit breaker de fuente abierto >24h sin recuperación → recomienda investigar manualmente.
- [ ] Output: tabla rich + JSON exportable.
- [ ] Sección en dashboard E7 (página Analytics dedicada).
- [ ] Tests con DB seeded simulando cada escenario.

### Tasks

- [ ] Crear `src/jobhunter/analytics/recommendations.py` con engine de reglas.
- [ ] Cada regla como función separada testeable: `_check_template_zero_response()`, etc.
- [ ] CLI command con output rich.
- [ ] Sección dashboard.
- [ ] Tests para cada regla.

### Estimación: 2h

### Notas

- **Heurística > LLM aquí.** Las reglas son específicas, predecibles, debugeables. LLM en este caso introduciría variabilidad innecesaria.
- **El usuario decide.** El sistema NO aplica las recomendaciones automáticamente. Pausar un template significa setear `enabled=false` en config, lo cual es decisión humana.
- **Prioridad puede ser dinámica:** una recomendación P1 ignorada 3 semanas se vuelve P2 (entropía social).

---

## E11-S07 — Export PDF + UI dashboard

**Como** dueño del sistema, **quiero** poder exportar reportes mensuales y recommendations como PDF + tener una página dedicada en dashboard para analytics avanzado, **para que** archivado y consumo visual sean ergonómicos.

### Acceptance Criteria

- [ ] Página nueva en dashboard: `pages/8_📈_Analytics.py`.
- [ ] Secciones:
  - **Recommendations:** lista (de S06) con priority badges, acciones quickbutton para "Snooze", "Acted on", "Ignore".
  - **A/B tests activos:** tabla con name, variants, sample size, current significance — link a "End test" si concluida.
  - **False rejects review:** lista paginada con preview del job + botón "Promote" (ejecuta promoción manual).
  - **Reports archive:** lista de reportes mensuales generados con preview + botón download.
- [ ] Botón "Generate report" genera reporte del mes actual on-demand (con spinner).
- [ ] Botón "Export to PDF" en cualquier vista convierte a PDF descargable (usando `weasyprint`).
- [ ] Email automático del reporte mensual al usuario el día 1 de cada mes (extiende workflow `weekly-digest.yml` o crea nuevo `monthly-report.yml`).

### Tasks

- [ ] Página Streamlit con 4 secciones.
- [ ] Integración con servicios de S05 y S06.
- [ ] Workflow `monthly-report.yml` con cron `'0 8 1 * *'` (día 1 de cada mes 08:00 UTC = 03:00 COT).
- [ ] Tests E2E (Playwright) de la página.

### Estimación: 1.5h

### Notas

- **Email automático del reporte el día 1** cierra el ciclo de feedback mensual sin que el usuario tenga que pedirlo.
- **"Snooze" en recommendations:** marca como vista, oculta por X días. Útil para recommendations recurrentes que ya estás trabajando.

---

## E11-S08 — Tests + workflow semanal de análisis

**Como** dueño del sistema, **quiero** workflow automatizado de análisis semanal y tests cross-épica del módulo analytics, **para que** la detección de regresiones y recomendaciones corran sin intervención manual.

### Acceptance Criteria

- [ ] `.github/workflows/weekly-analysis.yml`:
  - Schedule cron: `'0 13 * * 1'` (lunes 13:00 UTC = 08:00 COT — info al empezar la semana).
  - Trigger manual.
  - Steps:
    1. `uv run jobhunter analytics check-regressions`.
    2. `uv run jobhunter analytics check-anomalies`.
    3. `uv run jobhunter analytics recommendations` → output a Action Summary.
    4. Si hay regresiones críticas, alerta Telegram.
- [ ] Tests integración cross-épica:
  - **Pipeline completo simulado:** seed DB con datos representativos de 3 meses → run analytics → verificar métricas, regresiones detectadas, recomendaciones coherentes.
  - **A/B testing E2E:** crear test → assignar 100 jobs → simular outcomes → conclude → verificar significance.
  - **Reporte mensual E2E:** generar reporte completo → verificar estructura, contenido, sin errores LLM.
- [ ] Coverage `analytics/` ≥ 80%.
- [ ] Performance: el workflow `weekly-analysis` debe completar en <3 min.

### Tasks

- [ ] Workflow YAML.
- [ ] Tests integración con DB seeded representativa (3 meses de data).
- [ ] Coverage report.

### Estimación: 1.5h

### Notas

- **Lunes 08:00 COT** elegido para que las recomendaciones y regresiones aterrizen al inicio de la semana de trabajo, no en domingo cuando estás en café.
- **Action Summary con tablas markdown** hace los resultados directamente visibles en GitHub UI sin descargar logs.

---

## Definition of Ready para E12

E11 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con tests integración cross-épica.
- [ ] Workflow `weekly-analysis.yml` corre exitosamente al menos una semana.
- [ ] Al menos 1 reporte mensual generado y revisado (calidad del output del LLM).
- [ ] Al menos 1 A/B test creado y conducido (incluso con sample size pequeño, para validar el flujo).
- [ ] Sección Analytics del dashboard funcional con las 4 sub-secciones.
- [ ] Tag `v0.11.0` creado.

A partir de aquí: **E12 (Observability avanzada)** es la última épica — completar telemetría, dashboards de salud del sistema, hardening security.

---

## Anexo: ¿Por qué heurística para recommendations en lugar de LLM?

Tentación: usar LLM para que "te diga qué hacer" basado en métricas. Razones para resistirla en E11-S06:

1. **Reproducibilidad.** Mismo input siempre da misma output con heurística. Con LLM, dos corridas con misma data dan recomendaciones diferentes — confunde más de lo que ayuda.
2. **Debugability.** Si una recomendación es absurda, en heurística rastreas la regla específica que disparó. En LLM, "el modelo lo dijo".
3. **Costo.** Heurística es gratis. LLM analizando todas las métricas mensualmente cuesta ~$0.50/corrida × 4 corridas/mes = $2/mes. No es prohibitivo, pero por nada.
4. **Calidad para este caso.** Las reglas de "si X entonces recomienda Y" son específicas y conocibles a priori. No requieren razonamiento general.

**Excepción válida:** la generación del reporte mensual narrativo (S05) sí usa LLM, porque ahí el output es prosa, no decisiones discretas. LLM brilla en narrativas; pierde en lógica determinística.

---

## Anexo: A/B testing — sample size y patience

Para que un A/B test sea estadísticamente significativo, necesitas:

- **Métricas con alta varianza** (ej. binary outcomes como "respondió" vs "no respondió"): ~100-200 muestras por variant para detectar diferencias del 10%.
- **Métricas continuas** (ej. fit_score promedio): ~30-50 muestras suficientes con t-test.

Para el contexto de búsqueda de empleo personal:
- 100 aplicaciones distribuidas 50/50 entre dos variantes de cover letter prompt = 50 sends por variant.
- A 20-30 aplicaciones/semana, esto es 4-5 semanas para conclusión.

**Implicación operativa:** ser paciente. No concluir tests prematuramente. CLI `ab-test results` advierte si sample size < 30 por variant y rechaza calling a winner.

---

## Anexo: Cuando NO ejecutar E11

Si tras 8-12 semanas operando el MVP la búsqueda dio fruto (ej. ya tienes oferta firmada y aceptada), E11 puede no rendir el ROI. Escenario:

1. **Sistema funcionó tal cual.** No necesitas analytics elaborado para iterar.
2. **El portfolio piece** del sistema base (E1-E10) ya es suficiente sin la sofisticación de E11.

Por otro lado, **si planeas usar el sistema continuamente** (ej. siempre estás "open to opportunities"), E11 paga dividendos altos al automatizar la mejora continua.

**Decision rule:** si vas a operar el sistema >3 meses, E11 vale la pena. Si <3 meses, considera saltarla.

---

**Fin Documento O.**
