# Directiva: Job Hunter EU — Reparación, Multi-LLM (Gemini / Antigravity CLI) y Parametrización Multi-Perfil

## 1. Objetivo
Habilitar `The-Job-Hunter` para operar con costo \$0 en infraestructura y LLM (usando SQLite local o PostgreSQL, y Gemini API o `agy -p` en el servidor remoto como proveedor LLM), reparar el registro automático de fuentes de empleo, y desacoplar el perfil del candidato para soportar tanto búsqueda personal como servicio "Done-For-You" (DFY) / producto vendible.

## 2. Entradas
- **Variables de Entorno (`.env`):**
  - `DATABASE_URL`: `sqlite:///./jobhunter.db` (local) o PostgreSQL.
  - `LLM_PROVIDER`: `anthropic` | `gemini` | `agy_cli` | `mock`.
  - `ANTHROPIC_API_KEY`: Requerido solo si `LLM_PROVIDER=anthropic`.
  - `GEMINI_API_KEY` y `GEMINI_MODEL`: Requeridos si `LLM_PROVIDER=gemini`.
  - `AGY_CLI_BIN` y `AGY_MODEL`: Usados si `LLM_PROVIDER=agy_cli` (ejecución en servidor remoto con `agy -p`).
  - `DASHBOARD_PASSWORD`: Contraseña de acceso al dashboard Streamlit.
  - `CANDIDATE_PROFILE_PATH`: Ruta opcional a un archivo YAML/MD con el perfil del candidato (reemplaza el bloque hardcodeado en `prompts/scoring/v1.md`).
- **Archivos de entrada:**
  - `prompts/scoring/v1.md`
  - `cv_variants/*.md` o `.local/cv_variants/*.md`

## 3. Lógica y Procedimiento Operativo Estándar (SOP)
1. **Registro de Fuentes (`src/jobhunter/sources/__init__.py`):**
   - Importar explícitamente `arbeitnow`, `fourdayweek`, `remoteok` y `wwr` en `__init__.py` para que el decorador `@register_source` pueble `_REGISTRY` antes de llamar `get_all_sources()`.
2. **Abstracción de Proveedor LLM (`src/jobhunter/llm/`):**
   - Definir un protocolo común `LLMClient` con método `async def complete(...) -> LLMResponse`.
   - Implementar `GeminiLLMClient` vía REST (`httpx`) contra `generativelanguage.googleapis.com` (sin dependencias nuevas).
   - Implementar `AgyCLILLMClient` vía subproceso (`agy -p`) para aprovechar la sesión/cuota de Antigravity con Gemini en el servidor remoto (`cost_usd=0.0`), con timeout y limpieza de markdown fences.
   - Proveer `create_llm_client(settings)` como fábrica única usada por `pipeline.py`, `__main__.py` y `application/`.
3. **Configuración y Compatibilidad SQLite:**
   - Hacer `ANTHROPIC_API_KEY` opcional en `Settings` cuando se usa otro proveedor.
   - Documentar todas las variables requeridas en `.env.example`.
   - Ejecutar `alembic upgrade head` sobre SQLite local para pruebas rápidas sin Docker.
4. **Parametrización Multi-Perfil:**
   - Permitir inyectar el perfil del candidato desde `CANDIDATE_PROFILE_PATH` en `prompts/scoring/` para correr el pipeline para distintos clientes o compradores sin editar código fuente.

## 4. Salidas
- **Base de datos (`jobhunter.db` o PostgreSQL):** Vacantes normalizadas, scores, métricas de llamadas LLM y estado de postulaciones.
- **Dashboard Streamlit (`http://localhost:8080`):** Visualización de vacantes, pipeline y asistente de CV/Cover Letter.

## 5. Restricciones y Casos Borde (Memoria Viva)
- *Nota 1 (2026-11-18):* `src/jobhunter/db/session.py` instancia `Settings()` al importarse el módulo; cualquier ejecución de `pytest` o CLI falla si faltan campos obligatorios sin valor por defecto en `Settings`.
- *Nota 2 (2026-11-18):* `get_all_sources()` devolvía `[]` en producción porque `src/jobhunter/sources/__init__.py` no existía y los módulos con `@register_source` no se importaban.
- *Nota 3 (2026-11-18):* En `agy_cli`, el CLI `agy -p` solo está disponible en el servidor remoto (no en macOS local si no está instalado en `PATH`), por lo que en local se debe usar `gemini` (API), `anthropic` o `mock`.
