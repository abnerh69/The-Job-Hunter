# Documento G — Backlog Nivel 2: Descomposición de E3 (Multi-source Job Ingestion)

**Épica origen:** E3 — Multi-source Job Ingestion (Documento D).
**Tamaño épica:** L (4-6 días).
**Total stories:** 9.
**Estimación total:** 16–19 horas (3-4 sesiones de medio día).

**Convenciones:** mismas que documentos E y F. ID `E03-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E3 es la primera épica de **lógica de negocio** del sistema. Toma el contrato de datos de E2 y lo alimenta con ofertas reales del mundo. La decisión arquitectónica clave es **plugin pattern**: cada fuente es una clase que implementa `BaseSource`, y añadir una nueva no requiere tocar el orquestador. Esto paga dividendos cuando inevitablemente quieras agregar fuente #5, #6, #7.

### Decisiones técnicas clave

1. **Plugin pattern con registry** — añadir fuente = crear clase + registrar.
2. **`httpx` async** — múltiples fuentes en paralelo, no serial.
3. **Circuit breaker por fuente** — un scraper roto no detiene los otros.
4. **HTTP cassettes** (`pytest-recording` o `vcrpy`) para tests reproducibles sin red.
5. **Canonicalización de URL** antes del hash — `https://example.com/job/?utm=foo` y `https://example.com/job/` deben deduplicar como uno.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E03-S01 | `BaseSource` ABC + `RawJob` + Registry | 1.5h | E2 cerrada | — |
| E03-S02 | HTTP client wrapper (retry, backoff, rate limit) | 2h | S01 | — |
| E03-S03 | `ArbeitnowSource` adapter | 1.5h | S02 | con S04, S05, S06 |
| E03-S04 | `RemoteOKSource` adapter | 1.5h | S02 | con S03, S05, S06 |
| E03-S05 | `WeWorkRemotelySource` (RSS) adapter | 2h | S02 | con S03, S04, S06 |
| E03-S06 | `FourDayWeekSource` adapter | 2h | S02 | con S03, S04, S05 |
| E03-S07 | Ingestion orchestrator + circuit breaker | 3h | S03–S06 | — |
| E03-S08 | CLI: `jobhunter ingest` | 1.5h | S07 | — |
| E03-S09 | Integration tests con HTTP cassettes | 2h | S03–S07 | — |

### Camino crítico

```
E2 ─→ S01 ─→ S02 ─→ ┬─→ S03 ─┐
                    ├─→ S04 ─┤
                    ├─→ S05 ─┼─→ S07 ─→ S08 ─→ S09
                    └─→ S06 ─┘
```

**Tiempo serial:** ~17h. **Con paralelización (S03–S06 en paralelo):** ~11h.

### Definition of Done de la épica (recordatorio)

```bash
# Comando ingest funciona contra fuentes reales
jobhunter ingest --source arbeitnow --limit 10

# Re-correr es idempotente (no duplica)
jobhunter ingest --source arbeitnow --limit 10  # 0 nuevos

# Una fuente rota no detiene el resto
jobhunter ingest  # ejecuta todas, reporta fallos individuales

# Tests integración corren sin red (cassettes)
pytest tests/integration/sources/ --no-network
```

---

## E03-S01 — `BaseSource` ABC + `RawJob` + Registry

**Como** dueño del sistema, **quiero** un contrato abstracto y un registry para fuentes de ingestion, **para que** añadir una nueva fuente sea estrictamente: crear clase, decorarla con `@register_source`, y nada más.

### Acceptance Criteria

- [ ] `src/jobhunter/sources/base.py` define `BaseSource(ABC)` con método abstracto `async fetch(since: datetime) -> AsyncIterator[RawJob]`.
- [ ] Cada `BaseSource` tiene: `name: str` (identificador único), `default_rate_limit: float`, método `canonicalize_url(url) -> str`.
- [ ] Pydantic model `RawJob` que normaliza la salida de cualquier fuente (campos: `source_name`, `source_id`, `url`, `title`, `company`, `location_raw`, `description`, `posted_at`, `raw_payload`).
- [ ] Función `compute_url_hash(url) -> str` que canonicaliza URL (lowercase host, strip query params de tracking comunes: `utm_*`, `gclid`, `fbclid`, `ref`, `mc_*`) y devuelve sha256.
- [ ] Decorator `@register_source` que añade clase al registry global.
- [ ] Función `get_all_sources() -> list[BaseSource]` itera el registry.
- [ ] Tests unitarios cubren `compute_url_hash` con casos: URL idéntica, con/sin trailing slash, query params reordenados, mixed case en host.

### Tasks

- [ ] Crear `src/jobhunter/sources/__init__.py`
- [ ] Crear `src/jobhunter/sources/base.py`:
  ```python
  from abc import ABC, abstractmethod
  from collections.abc import AsyncIterator
  from datetime import datetime
  from pydantic import BaseModel, ConfigDict
  
  class RawJob(BaseModel):
      model_config = ConfigDict(frozen=True)
      source_name: str
      source_id: str | None
      url: str
      title: str
      company: str
      location_raw: str | None
      description: str
      posted_at: datetime | None
      raw_payload: dict
  
  class BaseSource(ABC):
      name: str
      default_rate_limit: float = 1.0  # requests per second
  
      @abstractmethod
      async def fetch(self, since: datetime) -> AsyncIterator[RawJob]: ...
      
      def canonicalize_url(self, url: str) -> str:
          # default impl, subclasses can override
          ...
  ```
- [ ] Crear `src/jobhunter/sources/registry.py` con `register_source` decorator y `get_all_sources()`
- [ ] Crear `src/jobhunter/sources/url_utils.py` con `canonicalize_url` y `compute_url_hash`
- [ ] Tests unitarios en `tests/unit/sources/test_url_utils.py`

### Estimación: 1.5h

### Notas

- **`AsyncIterator` vs `list`.** Streamear con generator permite procesar resultados a medida que llegan (deduplicación early, no esperar a tener 200 ofertas para guardar la primera). Si una fuente falla a mitad, los primeros N ya están persistidos.
- **Canonicalización de URL.** No es trivial. Casos a manejar: case en hostname, trailing slash, parámetros de tracking, fragmentos (`#section`). Ver `urllib.parse.urlsplit` + manipulación.

---

## E03-S02 — HTTP client wrapper

**Como** dueño del sistema, **quiero** un cliente HTTP centralizado con retry, backoff exponencial, y rate limiting, **para que** todos los adapters lo reusen y nunca tengan que reimplementar manejo de errores HTTP.

### Acceptance Criteria

- [ ] `src/jobhunter/sources/http.py` expone clase `SourceHttpClient` que envuelve `httpx.AsyncClient`.
- [ ] Retry automático en errores transitorios (5xx, timeout, connection error) con backoff exponencial: 1s, 2s, 4s, max 3 reintentos.
- [ ] Rate limiting por host: max N req/s configurable; usa `asyncio.Semaphore` o token bucket.
- [ ] User-Agent identificable: `"jobhunter-eu/0.3 (+https://github.com/Informatica-ASHware/Job-Hunter-EU)"`.
- [ ] Logging estructurado con `structlog`: cada request log con `host`, `status_code`, `duration_ms`, `attempt`.
- [ ] No reintenta en 4xx (excepto 429 con `Retry-After`).
- [ ] Test unitario con `httpx.MockTransport`: verifica retry, backoff, rate limit.

### Tasks

- [ ] Añadir dependencias: `httpx`, `tenacity` (para retry decorators)
- [ ] Crear `src/jobhunter/sources/http.py` con clase `SourceHttpClient`
- [ ] Implementar context manager async (`async with SourceHttpClient(...) as client:`)
- [ ] Configurar retry con `tenacity` retrying en: `httpx.HTTPStatusError` (status >= 500), `httpx.TimeoutException`, `httpx.ConnectError`
- [ ] Manejo especial de 429: respetar `Retry-After` header
- [ ] Tests con `httpx.MockTransport`:
  - [ ] `test_retries_on_500_then_succeeds`
  - [ ] `test_no_retry_on_404`
  - [ ] `test_respects_retry_after_on_429`
  - [ ] `test_rate_limit_throttles_concurrent_requests`

### Estimación: 2h

### Notas

- **`tenacity` vs custom retry.** `tenacity` ahorra ~50 líneas y maneja edge cases (jitter, exponential backoff con cap). No reinventar.
- **Rate limit por host, no global.** RemoteOK y Arbeitnow son hosts distintos; no hay razón para serializarlos.

---

## E03-S03 — `ArbeitnowSource` adapter

**Como** dueño del sistema, **quiero** un adapter que ingiera ofertas de la API pública de Arbeitnow, **para que** la primera fuente productiva esté funcionando end-to-end.

### Acceptance Criteria

- [ ] `src/jobhunter/sources/arbeitnow.py` con clase `ArbeitnowSource(BaseSource)` decorada `@register_source`.
- [ ] Consume `https://www.arbeitnow.com/api/job-board-api` (REST, JSON, sin auth).
- [ ] Mapea respuesta a `RawJob` correctamente; campos faltantes manejados como `None`.
- [ ] Filtra ofertas con `posted_at < since` (parameter del método).
- [ ] Maneja paginación si la API la soporta.
- [ ] Test con cassette real (response capturada una sola vez): yields N `RawJob` válidos.

### Tasks

- [ ] Investigar 5 min: schema actual de la API (un `curl` para ver respuesta real)
- [ ] Crear adapter con métodos `_parse_job(raw: dict) -> RawJob | None` (None si está malformado)
- [ ] Implementar paginación si aplica (parámetro `page` o cursor)
- [ ] Test de integración con cassette grabada
- [ ] Test que un job malformado en la respuesta no rompe la iteración (skip + log warning)

### Estimación: 1.5h

### Paralelizable con

S04, S05, S06 (no dependencias entre adapters).

### Notas

- **Cassette grabar una sola vez.** Usar `pytest-recording` con `--record-mode=once`. Re-grabar solo si la API cambia.
- **No grabar cassettes con datos privados.** Arbeitnow es público, no hay riesgo. En el futuro, si añadimos fuente con auth, el cassette sanitiza headers `Authorization`.

---

## E03-S04 — `RemoteOKSource` adapter

**Como** dueño del sistema, **quiero** ingerir ofertas de RemoteOK, **para que** tengamos cobertura de roles remotos globales (US-centric pero amplio).

### Acceptance Criteria

- [ ] `src/jobhunter/sources/remoteok.py` con clase `RemoteOKSource(BaseSource)` registrada.
- [ ] Consume `https://remoteok.com/api` (REST, JSON, requiere User-Agent identificable).
- [ ] Primer elemento de la respuesta es metadata (no un job) — saltarse correctamente.
- [ ] Filtra por `tags` que contengan al menos uno de: `python`, `ai`, `ml`, `flutter`, `dart`, `senior`, `backend`. (Configurable, pero default razonable.)
- [ ] Mapea `RawJob`; `posted_at` viene en formato ISO8601.
- [ ] Test con cassette.

### Tasks

- [ ] Crear adapter
- [ ] Implementar filtro de tags (configurable vía `__init__`)
- [ ] Manejar el "primer elemento es metadata" correctamente
- [ ] Test con cassette + test que verifica filtro de tags funciona

### Estimación: 1.5h

### Paralelizable con

S03, S05, S06.

### Notas

- **RemoteOK rate limit.** No documentado, pero 1 req/3s es seguro. Configurar `default_rate_limit = 0.33`.
- **User-Agent obligatorio.** Si no lo envías, devuelven HTML en vez de JSON. Verificar.

---

## E03-S05 — `WeWorkRemotelySource` (RSS) adapter

**Como** dueño del sistema, **quiero** ingerir ofertas de WeWorkRemotely vía sus feeds RSS, **para que** otra fuente de empleo remoto esté cubierta.

### Acceptance Criteria

- [ ] `src/jobhunter/sources/wwr.py` con clase `WeWorkRemotelySource(BaseSource)`.
- [ ] Consume múltiples feeds RSS configurables: `programming`, `devops-sysadmin-jobs`, `back-end-programming`, etc.
- [ ] Parsing con `feedparser` (dependencia nueva).
- [ ] Mapeo desde RSS entry a `RawJob`: title, link, summary (description), pubDate, author/category.
- [ ] Manejo de descripciones HTML: strip HTML tags, mantener texto limpio (`beautifulsoup4` o `lxml.html`).
- [ ] Test con cassette XML.

### Tasks

- [ ] Añadir dependencias: `feedparser`, `beautifulsoup4`
- [ ] Crear adapter; iterar lista de feeds en `__init__`
- [ ] Función `_strip_html(html: str) -> str` para limpiar descripción
- [ ] `_parse_entry(entry: feedparser.FeedParserDict) -> RawJob`
- [ ] Cassette: capturar respuesta XML real una vez
- [ ] Test verifica parsing correcto de fechas RFC 822

### Estimación: 2h

### Paralelizable con

S03, S04, S06.

### Notas

- **`feedparser` es lento pero robusto.** Para N feeds × 50 entries ≈ 2-3s total, aceptable.
- **HTML en descriptions.** WWR mete HTML pesado. Stripear es necesario antes de pasar a scoring (Claude no necesita el markup).

---

## E03-S06 — `FourDayWeekSource` adapter

**Como** dueño del sistema, **quiero** ingerir ofertas de 4dayweek.io, **para que** cubramos empresas con culturas de trabajo modernas (señal positiva de calidad).

### Acceptance Criteria

- [ ] `src/jobhunter/sources/fourdayweek.py` con clase `FourDayWeekSource(BaseSource)`.
- [ ] Consume el feed público de 4dayweek.io (verificar al implementar: API JSON o feed RSS).
- [ ] Mapeo a `RawJob` con todos los campos requeridos.
- [ ] Test con cassette.

### Tasks

- [ ] Investigar 5 min: ¿API JSON o RSS? Documentar la URL exacta usada.
- [ ] Implementar adapter
- [ ] Cassette test

### Estimación: 2h

### Paralelizable con

S03, S04, S05.

### Notas

- **Si 4dayweek.io no expone feed/API utilizable**, sustituir por:
  1. `GermanTechJobs.de` (alineado con foco DACH)
  2. `Wellfound` vía RSS de búsquedas guardadas
  3. `LinkedIn` vía RSS de búsquedas guardadas
  
  Documentar la decisión en commit message y en `docs/data_model.md`.

---

## E03-S07 — Ingestion orchestrator + circuit breaker

**Como** dueño del sistema, **quiero** un orquestador que ejecute todas las fuentes en paralelo, persista resultados deduplicados, y aísle fallos por fuente, **para que** una fuente rota no detenga el pipeline completo.

### Acceptance Criteria

- [ ] `src/jobhunter/sources/orchestrator.py` con función `async run_ingestion(sources, since, session) -> IngestionReport`.
- [ ] Ejecuta fuentes en paralelo con `asyncio.gather(..., return_exceptions=True)`.
- [ ] Cada fuente con su propio circuit breaker (3 fallos seguidos → pausa 24h, persistido en DB o en archivo state).
- [ ] Usa `JobRepo.bulk_create_skipping_duplicates` para persistir; cuenta nuevos vs duplicados.
- [ ] `IngestionReport` (Pydantic): `source_results: list[SourceResult]`, `total_new`, `total_duplicates`, `total_errors`, `started_at`, `finished_at`.
- [ ] Cada `SourceResult`: `source_name`, `status` (success/failed/skipped_breaker), `new_jobs`, `duplicates`, `error: str | None`, `duration_ms`.
- [ ] Logging estructurado por fuente; al final, log agregado con resumen.
- [ ] Tests con `BaseSource` mockeado: 3 fuentes, una falla, otra exitosa, otra con circuit breaker abierto.

### Tasks

- [ ] Crear `src/jobhunter/sources/circuit_breaker.py` con clase `CircuitBreaker` (state: closed/open/half_open, persistencia de fallos)
- [ ] Decidir persistencia de circuit breaker: tabla `source_health` en DB (mejor) o archivo JSON local (más simple)
- [ ] Crear orquestador con manejo de excepciones por fuente
- [ ] Pydantic models para `SourceResult` e `IngestionReport`
- [ ] Tests de integración con sources mockeados

### Estimación: 3h

### Notas

- **Circuit breaker simple, no aiobreaker.** Para 4-6 fuentes, una clase de 30 líneas es suficiente. Aiobreaker añade complejidad innecesaria.
- **Persistencia: nueva tabla `source_health`.** Vale la pena migration; permite query desde dashboard "qué fuentes están degradadas".

---

## E03-S08 — CLI: `jobhunter ingest`

**Como** dueño del sistema, **quiero** un comando CLI ergonómico para correr ingestion manual, **para que** el desarrollo y debugging sea inmediato (no esperar al cron de E8).

### Acceptance Criteria

- [ ] Comando `jobhunter ingest` con flags:
  - [ ] `--source NAME` (opcional, repetible) — solo correr fuentes específicas.
  - [ ] `--since DATE` (default: últimos 7 días) — filtro de fecha.
  - [ ] `--limit N` (default: sin límite) — cap por fuente para testing rápido.
  - [ ] `--dry-run` — fetch + parse pero no persiste.
- [ ] Output: tabla con resultado por fuente (Rich library); resumen final con totales.
- [ ] Exit code 0 si todo OK, 1 si alguna fuente falló (útil para CI).
- [ ] Comando `jobhunter sources list` muestra fuentes registradas + estado del circuit breaker.

### Tasks

- [ ] Añadir dependencia `rich` si no está
- [ ] Configurar `typer` app principal en `src/jobhunter/cli.py`
- [ ] Comando `ingest` con flags
- [ ] Comando `sources list`
- [ ] Tests CLI con `typer.testing.CliRunner`

### Estimación: 1.5h

### Notas

- **`typer` sobre `argparse`.** Más declarativo, menos boilerplate. Ya alineado con el ecosistema FastAPI/pydantic.
- **`--dry-run` invaluable.** Permite verificar parser de una fuente sin saturar la DB con tests.

---

## E03-S09 — Integration tests con HTTP cassettes

**Como** dueño del sistema, **quiero** tests de integración que corran sin red usando cassettes grabados, **para que** el CI sea rápido y reproducible y los adapters no se rompan silenciosamente.

### Acceptance Criteria

- [ ] `pytest-recording` (o `vcrpy` directo) configurado.
- [ ] Cassettes en `tests/integration/sources/cassettes/` versionados en repo.
- [ ] Test end-to-end por adapter: cassette → orchestrator → DB → verifica registros persistidos.
- [ ] Test de circuit breaker: 3 fallos consecutivos → cuarta llamada se salta.
- [ ] Test de deduplicación: correr ingest 2 veces → segunda corrida 0 nuevos.
- [ ] Modo `--block-network` en CI: si un test intenta llamar a internet sin cassette, falla.
- [ ] CI verde con tests de integración corriendo.

### Tasks

- [ ] Añadir dependencia `pytest-recording`
- [ ] Configurar `pytest.ini`/`pyproject.toml` para cassettes
- [ ] Capturar cassettes iniciales: correr una vez con `--record-mode=once` apuntando a APIs reales
- [ ] Sanitizar cassettes (remover headers sensibles si los hay)
- [ ] Refactor de tests existentes (S03–S06) para usar cassettes consistentemente
- [ ] Test end-to-end orchestrator
- [ ] Test deduplicación (correr 2 veces)
- [ ] Test circuit breaker
- [ ] Update `.github/workflows/ci.yml` para correr tests de integración

### Estimación: 2h

### Notas

- **Cassettes como ground truth.** Cuando una API cambia su schema, el test fallará — bueno, eso es exactamente lo que queremos. Re-grabar cassette + adaptar parser.
- **Tamaño de cassettes.** Limitar a ~5-10 jobs por fuente; capturar cassettes con `?limit=5` cuando la API lo soporte.

---

## Definition of Ready para E4

E3 cerrada cuando:

- [ ] Las 9 stories tienen AC ✅.
- [ ] CI verde con tests de integración corriendo (con cassettes).
- [ ] `jobhunter ingest` ejecuta contra las 4 fuentes y persiste ofertas reales.
- [ ] Re-correr es idempotente (verificado manualmente).
- [ ] Circuit breaker probado: simular fallo de una fuente, verificar aislamiento.
- [ ] Tag `v0.3.0` creado.
- [ ] DB tiene 100+ jobs reales en `status='new'`, listos para que E4 (scoring) los procese.

A partir de aquí, **E4 (AI Scoring Engine)** se puede empezar — hay datos reales para entrenar/ajustar el prompt maestro contra la realidad.

---

**Fin Documento G.**
