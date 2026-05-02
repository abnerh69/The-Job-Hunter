# ADR-006: No Module-Level `settings` Singleton

## Status
Accepted

## Context
El backlog original (E01-S05, Documento E) pedía exportar una instancia singleton `settings = Settings()` desde `src/jobhunter/config.py`, de modo que los consumidores la importaran con `from jobhunter.config import settings`.

Durante la implementación se optó por no crear ese singleton: cada consumidor instancia `Settings()` localmente cuando lo necesita (`__main__.py`, `pipeline.py`, `notify/*`, `llm/budget.py`, etc.).

## Decision
`src/jobhunter/config.py` exporta únicamente la **clase** `Settings`. No existe una instancia a nivel de módulo. Cada call-site hace `settings = Settings()` cuando requiere configuración.

## Rationale
1. **Tests aislados.** Un singleton evaluado en import-time obliga a que `.env` (o todas las variables requeridas) esté disponible apenas se importa cualquier módulo que dependa transitiva­mente de `config.py`. Eso complica los tests unitarios y obliga a parchear el módulo. Instanciar localmente permite que los tests pasen `Settings(_env_file=None, …)` o monkey-patcheen `Settings.__init__` por test sin tocar estado global.
2. **Validación al borde, no al import.** `__main__.callback()` valida `Settings()` en cada invocación de la CLI y falla con un error legible si falta una variable requerida. Esto es preferible a un `ImportError` opaco lanzado durante la carga del paquete.
3. **Distintos entry-points, distintos requisitos.** El dashboard de Streamlit, la CLI, la API FastAPI y los workers de GitHub Actions tienen perfiles de variables ligeramente distintos. Forzar una instancia compartida significaría declarar todos los campos como opcionales o cargar el superconjunto en cada proceso.
4. **pydantic-settings ya cachea la lectura del entorno.** Instanciar `Settings()` varias veces no implica re-leer disco repetidamente en hot paths; el coste es despreciable y los call-sites actuales no están en bucles internos.

## Consequences
- **Pros:** Tests más simples, errores de configuración más explícitos, mayor flexibilidad por entry-point.
- **Cons:** Cada call-site repite `settings = Settings()  # type: ignore[call-arg]`. El `type: ignore` es necesario porque mypy no puede inferir que las variables requeridas vendrán de `.env` en runtime.
- **Desviación documentada respecto a E01-S05.** El AC literal de la story no se cumple, pero el objetivo subyacente — un único punto de carga tipado desde el entorno, sin que ningún componente lea `os.environ` directo — sí se cumple.

## Alternatives considered
- **Singleton lazy con `functools.lru_cache`.** Resuelve el coste de re-instanciación pero mantiene los problemas de tests (estado global cacheado entre tests, requiere `cache_clear()` en fixtures).
- **Inyección por argumento.** Pasar `settings: Settings` como parámetro a cada función. Más limpio en teoría, pero invasivo para el tamaño actual del proyecto y poco idiomático en una CLI Typer.

Si el coste del `type: ignore` repetido se vuelve molesto, la migración a un helper `get_settings() -> Settings` con `lru_cache` es local a `config.py` y no rompe call-sites.
