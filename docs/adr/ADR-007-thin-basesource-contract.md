# ADR-007: Thin `BaseSource` Contract

## Status
Accepted

## Context
El backlog de E3 (E03-S01, Documento G) pedía que `BaseSource` declarara
explícitamente los atributos `name: str`, `default_rate_limit: float` y un
método `canonicalize_url(url) -> str`.

La implementación actual deja `BaseSource` reducido a un único método
abstracto `async fetch(since) -> AsyncIterator[RawJob]`. La canonicalización
de URLs vive como función libre en `src/jobhunter/sources/url_utils.py`
(`canonicalize_url`, `compute_url_hash`), y `default_rate_limit` lo declaran
sólo las subclases que se desvían del default (p. ej.
`RemoteOKSource.default_rate_limit = 0.33`).

## Decision
`BaseSource` mantiene un contrato mínimo:

- **Sólo** el método abstracto `async fetch(since)`.
- Sin atributos de clase obligatorios (`name`, `default_rate_limit`).
- Sin método `canonicalize_url` colgado de la jerarquía.

Las responsabilidades originalmente previstas se mueven:

| Responsabilidad del AC | Dónde vive en realidad |
|---|---|
| `name: str` | Cada subclase pasa un literal en cada `RawJob(source_name="…", …)` que emite. El registry indexa por `cls.__name__` (`registry._REGISTRY[cls.__name__] = cls`). |
| `default_rate_limit: float` | Atributo opcional en subclases que se desvían del default (`RemoteOKSource = 0.33`); el rate-limit efectivo lo aplica `SourceHttpClient` por host vía `asyncio.Semaphore`, no la fuente. |
| `canonicalize_url(url)` | Función libre `sources.url_utils.canonicalize_url`. Idéntica para todas las fuentes — no se beneficia de override por subclase. |

## Rationale
1. **Ningún caller necesita el contrato propuesto.** El orchestrator
   (`sources/orchestrator.py`) sólo invoca `source.fetch(since)`; nunca lee
   `source.name` ni `source.default_rate_limit`. El rate-limit real se aplica
   a nivel HTTP, donde es más útil (semáforo por host, no por clase).
2. **La canonicalización es lógica de dominio, no de protocolo.** Las 4
   fuentes actuales canonicalizan exactamente igual (lowercases host,
   strips tracking params, sorts query). Mover esto a un método de instancia
   invitaría a que cada subclase reinvente la rueda; mantenerlo libre en
   `url_utils` da una única implementación testeada.
3. **Menos contrato → más fácil añadir fuentes.** El AC pretendía que sumar
   una fuente fuera "crear clase + decorar". Hoy es exactamente eso: heredar
   de `BaseSource`, implementar `fetch`, decorar con `@register_source`.
   Forzar atributos extra los volvería ceremonia.

## Consequences
- **Pros:** Contrato más pequeño, menos código en la base, ningún atributo
  declarado pero no usado.
- **Cons:** El nombre de la fuente (`source_name` en `RawJob`) se duplica en
  cada subclase. Si en el futuro queremos un *registry de instancias* (en
  vez de clases) o un dashboard que liste fuentes con su rate-limit, habrá
  que añadir las propiedades entonces.
- **Desviación documentada respecto a E03-S01.** El AC literal no se cumple,
  pero la "Definition of Done" de la épica (idempotencia, fuentes en
  paralelo, circuit breaker, tests con cassettes) sí.

## Alternatives considered
- **Cumplir el AC literal** declarando `name: ClassVar[str]`,
  `default_rate_limit: ClassVar[float] = 1.0` y un método
  `canonicalize_url` que delegue en `url_utils`. Es trivial de aplicar, pero
  añade obligaciones a las subclases sin caller que las consuma. Si en el
  futuro un consumidor las necesita, esta migración es local a `base.py`.
- **Registry de instancias** en vez de clases (`get_all_sources() ->
  list[BaseSource]`). Permitiría leer atributos sin instanciar, pero obliga
  a definir un constructor sin argumentos en cada fuente. No vale la pena
  hoy.
