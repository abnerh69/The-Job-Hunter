# Documento E — Backlog Nivel 2: Descomposición de E1 (Foundation & Project Bootstrap)

**Épica origen:** E1 — Foundation & Project Bootstrap (Documento D).
**Tamaño épica:** S (≤1 día).
**Total stories:** 8.
**Estimación total:** 6–9 horas (un día de trabajo enfocado, o dos sesiones de medio día).

**Convenciones:**
- **ID:** `E01-S##` (story).
- **Formato:** `Como… quiero… para…` + Acceptance Criteria testeables + Tasks ejecutables (L3 ligero).
- **Estimación:** horas reales de trabajo, no story points (proyecto solo-developer).
- **Estado del checkbox:** los `[ ]` te sirven para tracking directo desde el archivo.

---

## Resumen ejecutivo

E1 entrega el "esqueleto vivo" del proyecto: clonar el repo y tener entorno corriendo en menos de 10 minutos. No hay lógica de negocio aquí — solo infraestructura para que toda épica downstream tenga dónde aterrizar.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E01-S01 | Inicializar repositorio y estructura base | 30 min | — | — |
| E01-S02 | Configurar proyecto Python con uv | 45 min | S01 | — |
| E01-S03 | Tooling de calidad: ruff, black, mypy, pre-commit | 1h | S02 | con S04, S05, S06 |
| E01-S04 | Framework de testing con pytest | 45 min | S02 | con S03, S05, S06 |
| E01-S05 | Gestión de configuración con pydantic-settings | 1h | S02 | con S03, S04, S06 |
| E01-S06 | Entorno containerizado: Docker + Postgres | 1.5h | S01 | con S03, S04, S05 |
| E01-S07 | CI pipeline en GitHub Actions | 1h | S03, S04 | — |
| E01-S08 | README y verificación end-to-end de onboarding | 1h | todas | — |

### Camino crítico

```
S01 ─→ S02 ─→ ┬─→ S03 ─┐
              ├─→ S04 ─┤
              └─→ S05  ├─→ S07 ─→ S08
S01 ─────────────→ S06 ─┘
```

**Tiempo mínimo si se paraleliza S03/S04/S05/S06:** ~5 horas reloj.
**Tiempo serial:** ~7-9 horas.

### Definition of Done de la épica (recordatorio)

Esta secuencia debe funcionar en una máquina limpia, en orden, sin errores:

```bash
git clone <repo>
cd jobhunter-eu
cp .env.example .env
docker-compose up -d
uv sync
uv run pytest
uv run pre-commit run --all-files
```

Si esto pasa, E1 está cerrada.

---

## E01-S01 — Inicializar repositorio y estructura base

**Como** dueño del sistema, **quiero** un repositorio Git con estructura de directorios definida, **para que** todas las épicas downstream tengan un lugar predecible donde colocar código.

### Acceptance Criteria

- [ ] Repositorio Git inicializado, branch principal `main`.
- [ ] `.gitignore` cubre Python (`__pycache__`, `.venv`, `*.pyc`), entorno (`.env`, `.env.local`), IDE (`.vscode/`, `.idea/`), DB locales (`*.db`, `pgdata/`), build (`dist/`, `build/`, `*.egg-info`).
- [ ] Estructura de directorios creada según §5 del Documento B (con `.gitkeep` en directorios vacíos).
- [ ] Repositorio configurado como **privado** en GitHub.
- [ ] `LICENSE` decidido (recomendación: privado por ahora, si en el futuro se libera, MIT o Apache-2.0).

### Tasks

- [ ] `git init && git branch -m main`
- [ ] Crear `.gitignore` (template de `gitignore.io` para Python + macOS/Linux + VSCode)
- [ ] Crear estructura: `src/jobhunter/{db,sources,scoring,application,notify,dashboard,outreach}/`, `tests/{unit,integration,fixtures}/`, `docs/`, `alembic/`, `.github/workflows/`
- [ ] `touch .gitkeep` en directorios vacíos
- [ ] Symlinks o copias de `A_Prompt_Maestro_Scoring.md`, `B_Arquitectura_Sistema.md`, `C_Outreach_Playbook.md`, `D_Backlog_Nivel_1_Epicas.md`, `E_Backlog_Nivel_2_E1.md` en `docs/`
- [ ] Crear repo en GitHub (privado), añadir como remote, primer push

### Estimación: 30 min

### Notas

- No incluir el CV real (con datos personales) en el repo. Las variantes en `cv_variants/` se añadirán como template/placeholder; los reales viven solo localmente o en un repo aparte privado.

---

## E01-S02 — Configurar proyecto Python con uv

**Como** dueño del sistema, **quiero** un proyecto Python moderno con gestión rápida de dependencias, **para que** instalar/actualizar paquetes sea instantáneo y el lock file garantice reproducibilidad.

### Acceptance Criteria

- [ ] `pyproject.toml` declarando proyecto, Python ≥3.12, dependencias mínimas iniciales.
- [ ] `uv` instalado y `uv sync` corre sin errores.
- [ ] `uv.lock` generado y commiteado.
- [ ] Virtual env reproducible: borrar `.venv` y `uv sync` lo regenera idéntico.
- [ ] Comando `uv run python -c "import jobhunter; print('ok')"` ejecuta exitosamente.

### Tasks

- [ ] Instalar `uv` (si no está): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [ ] `uv init --package jobhunter --python 3.12`
- [ ] Editar `pyproject.toml`: nombre, descripción, autor, license=Proprietary
- [ ] Añadir dependencias core: `httpx`, `sqlalchemy>=2.0`, `alembic`, `pydantic>=2`, `pydantic-settings`, `anthropic`, `structlog`, `typer`
- [ ] Añadir dependencias de dev en grupo separado: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `black`, `mypy`, `pre-commit`
- [ ] `uv sync`
- [ ] Crear `src/jobhunter/__init__.py` con `__version__ = "0.1.0"`
- [ ] Verificar import con `uv run python -c "import jobhunter; print(jobhunter.__version__)"`
- [ ] Commit

### Estimación: 45 min

### Notas

- **¿Por qué uv y no poetry?** uv es 10-100x más rápido en resolución/instalación, mantenido por Astral (los de ruff), y la curva de aprendizaje es mínima viniendo de pip/poetry. Ya lo conocen los reclutadores tech como señal de developer al día.
- Si prefieres Poetry porque ya lo dominas, sustituye 1:1 — las dependencias y estructura no cambian.

---

## E01-S03 — Tooling de calidad: ruff, black, mypy, pre-commit

**Como** dueño del sistema, **quiero** linting, formatting y type-checking automatizados antes de cada commit, **para que** el código mantenga estándar consistente sin esfuerzo manual.

### Acceptance Criteria

- [ ] `ruff check src/ tests/` corre sin errores (sobre el código mínimo actual).
- [ ] `ruff format` y `black` integrados (uno actúa como source of truth — recomiendo solo `ruff format`).
- [ ] `mypy --strict src/jobhunter/` corre sin errores sobre el código mínimo.
- [ ] `pre-commit install` registrado; hooks corren al hacer commit local.
- [ ] Configuración centralizada en `pyproject.toml` (no archivos sueltos `.ruff.toml`, `mypy.ini`, etc., a menos que sea inevitable).

### Tasks

- [ ] Configurar sección `[tool.ruff]` en `pyproject.toml`: `line-length = 100`, `target-version = "py312"`, lint rules razonables (E, F, I, N, UP, B, C4, SIM)
- [ ] Configurar `[tool.ruff.format]`: como reemplazo de Black (suficiente y más rápido)
- [ ] Configurar `[tool.mypy]`: `strict = true`, `python_version = "3.12"`, `ignore_missing_imports = true` para libs sin stubs
- [ ] Crear `.pre-commit-config.yaml` con hooks: `ruff` (lint + format), `mypy`, `check-yaml`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`, `detect-secrets`
- [ ] `uv run pre-commit install`
- [ ] `uv run pre-commit run --all-files` para ejecutar primera pasada
- [ ] Resolver violaciones que aparezcan
- [ ] Commit

### Estimación: 1h

### Notas

- **`detect-secrets`** es importante: previene commitear API keys accidentalmente. Genera baseline inicial con `detect-secrets scan > .secrets.baseline`.
- Si prefieres Black además de Ruff, ten cuidado con conflictos de formateo. Recomendación: solo Ruff (`ruff format` reemplaza Black 1:1).

---

## E01-S04 — Framework de testing con pytest

**Como** dueño del sistema, **quiero** infraestructura de testing lista, **para que** cada épica downstream pueda añadir tests sin fricción y el CI tenga algo que correr.

### Acceptance Criteria

- [ ] `uv run pytest` ejecuta sin errores.
- [ ] Al menos un test smoke (`test_imports`) verifica que el paquete se importa.
- [ ] `pytest-asyncio` configurado (lo necesitarás para los scrapers async).
- [ ] `pytest-cov` configurado, reporta coverage.
- [ ] Estructura `tests/unit/`, `tests/integration/`, `tests/fixtures/` poblada con `__init__.py` y `conftest.py`.

### Tasks

- [ ] Configurar `[tool.pytest.ini_options]` en `pyproject.toml`: `testpaths = ["tests"]`, `asyncio_mode = "auto"`, marcadores custom (`unit`, `integration`, `slow`)
- [ ] Configurar `[tool.coverage.run]`: `source = ["src/jobhunter"]`, `branch = true`
- [ ] Crear `tests/conftest.py` con fixtures placeholders
- [ ] Crear `tests/unit/test_smoke.py` con un test trivial:
  ```python
  def test_package_imports():
      import jobhunter
      assert jobhunter.__version__
  ```
- [ ] Correr `uv run pytest -v --cov` y verificar output limpio
- [ ] Commit

### Estimación: 45 min

### Notas

- `asyncio_mode = "auto"` evita tener que decorar cada test async con `@pytest.mark.asyncio`. Pequeño quality of life.

---

## E01-S05 — Gestión de configuración con pydantic-settings

**Como** dueño del sistema, **quiero** un único punto de carga de configuración tipada desde variables de entorno, **para que** ningún componente lea `os.environ` directamente y `.env` sea la fuente de verdad para credenciales.

### Acceptance Criteria

- [ ] Clase `Settings` en `src/jobhunter/config.py` con todos los campos esperados (DB URL, Anthropic API key, Telegram token, etc.) tipados.
- [ ] `.env.example` enumera **todas** las variables con valores placeholder y comentarios.
- [ ] `Settings` lanza error claro al instanciar si falta una variable requerida.
- [ ] `from jobhunter.config import settings` devuelve la instancia singleton cargada de `.env`.
- [ ] `.env` está en `.gitignore` y nunca se commitea.

### Tasks

- [ ] Crear `src/jobhunter/config.py`:
  ```python
  from pydantic import SecretStr
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
      
      # Database
      database_url: str
      
      # Anthropic
      anthropic_api_key: SecretStr
      anthropic_model_scoring: str = "claude-haiku-4-5-20251001"
      anthropic_model_cover_letter: str = "claude-opus-4-7"
      
      # Telegram
      telegram_bot_token: SecretStr
      telegram_chat_id: str
      
      # Email (digest)
      smtp_host: str = "smtp.gmail.com"
      smtp_port: int = 587
      smtp_user: str
      smtp_password: SecretStr
      digest_to_email: str
      
      # Operacional
      log_level: str = "INFO"
      environment: str = "local"  # local | production

  settings = Settings()  # type: ignore
  ```
- [ ] Crear `.env.example` espejo de la clase, todos los valores placeholder (`your-key-here`)
- [ ] Crear `.env` local con valores reales (no commitear)
- [ ] Verificar carga: `uv run python -c "from jobhunter.config import settings; print(settings.environment)"`
- [ ] Test unitario que verifica carga con `.env.example` (sustituyendo placeholders por dummies en fixture)
- [ ] Commit

### Estimación: 1h

### Notas

- Usa `SecretStr` para credenciales — evita leaks accidentales en logs (su `repr` muestra `**********`).
- Más adelante, cuando agregues más servicios (Gmail OAuth, etc.), simplemente añades campos a `Settings`. Centralización paga dividendos rápido.

---

## E01-S06 — Entorno containerizado: Docker + Postgres

**Como** dueño del sistema, **quiero** levantar Postgres local con un comando, **para que** desarrollo y testing no dependan de tener Postgres instalado en la máquina ni de configuraciones manuales.

### Acceptance Criteria

- [ ] `docker-compose up -d` levanta Postgres 16 con persistencia en volumen.
- [ ] DB accesible en `localhost:5432`, credenciales coinciden con `DATABASE_URL` en `.env.example`.
- [ ] `docker-compose down` para todo limpiamente; `docker-compose down -v` borra el volumen (reset completo).
- [ ] `Dockerfile` para la app construye imagen funcional (aunque la app esté vacía).
- [ ] `docker-compose up app` corre la app contra la DB containerizada (smoke test).

### Tasks

- [ ] Crear `docker-compose.yml`:
  ```yaml
  services:
    postgres:
      image: postgres:16-alpine
      environment:
        POSTGRES_USER: jobhunter
        POSTGRES_PASSWORD: jobhunter_local
        POSTGRES_DB: jobhunter
      ports:
        - "5432:5432"
      volumes:
        - pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U jobhunter"]
        interval: 5s
        retries: 5
    
    app:
      build: .
      depends_on:
        postgres:
          condition: service_healthy
      env_file: .env
      command: ["uv", "run", "python", "-m", "jobhunter.cli", "--help"]
  
  volumes:
    pgdata:
  ```
- [ ] Crear `Dockerfile` multi-stage usando imagen oficial de uv:
  ```dockerfile
  FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
  WORKDIR /app
  COPY pyproject.toml uv.lock ./
  RUN uv sync --frozen --no-install-project
  COPY src/ ./src/
  RUN uv sync --frozen
  CMD ["uv", "run", "python", "-m", "jobhunter.cli"]
  ```
- [ ] Añadir `DATABASE_URL=postgresql://jobhunter:jobhunter_local@localhost:5432/jobhunter` a `.env.example`  # pragma: allowlist secret
- [ ] Test manual: `docker-compose up -d postgres && psql ... -c "SELECT 1;"`
- [ ] Documentar en notas del repo: `docker-compose down -v` para reset completo
- [ ] Commit

### Estimación: 1.5h

### Notas

- En docker-compose, `app` apunta a `postgres` por nombre de servicio (no `localhost`); pero cuando corres la app desde tu máquina (no contenedor), apunta a `localhost`. Documentar esta diferencia en README.
- **No** poner `postgres_password` real en `docker-compose.yml` — para local está bien hardcoded, pero deja un comentario indicando que en cloud sería desde secret manager.

---

## E01-S07 — CI pipeline en GitHub Actions

**Como** dueño del sistema, **quiero** que cada PR/push a main ejecute lint, typecheck y tests automáticamente, **para que** errores básicos se detecten antes de merge sin esfuerzo manual.

### Acceptance Criteria

- [ ] `.github/workflows/ci.yml` corre en push a `main` y en PRs.
- [ ] CI ejecuta: `ruff check`, `ruff format --check`, `mypy`, `pytest`.
- [ ] Tests corren contra Postgres provisto por el runner.
- [ ] CI falla si cualquier paso falla.
- [ ] Tiempo total de CI < 3 minutos.
- [ ] Badge de status agregado al README (post S08).

### Tasks

- [ ] Crear `.github/workflows/ci.yml`:
  ```yaml
  name: CI
  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]
  
  jobs:
    quality:
      runs-on: ubuntu-latest
      services:
        postgres:
          image: postgres:16-alpine
          env:
            POSTGRES_USER: jobhunter
            POSTGRES_PASSWORD: jobhunter_local
            POSTGRES_DB: jobhunter
          ports: ['5432:5432']
          options: >-
            --health-cmd pg_isready --health-interval 5s
            --health-timeout 5s --health-retries 5
      env:
        DATABASE_URL: postgresql://jobhunter:jobhunter_local@localhost:5432/jobhunter  # pragma: allowlist secret
        ANTHROPIC_API_KEY: dummy-for-ci
        TELEGRAM_BOT_TOKEN: dummy-for-ci
        TELEGRAM_CHAT_ID: '0'
        SMTP_USER: dummy@example.com
        SMTP_PASSWORD: dummy
        DIGEST_TO_EMAIL: dummy@example.com
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v3
          with:
            enable-cache: true
        - name: Set up Python
          run: uv python install 3.12
        - name: Install deps
          run: uv sync --frozen
        - name: Lint (ruff)
          run: uv run ruff check src/ tests/
        - name: Format check (ruff)
          run: uv run ruff format --check src/ tests/
        - name: Type check (mypy)
          run: uv run mypy src/jobhunter
        - name: Tests (pytest)
          run: uv run pytest -v
  ```
- [ ] Push, verificar que workflow corre y pasa.
- [ ] (Diferido a S08) añadir badge al README

### Estimación: 1h

### Notas

- Las credenciales dummy en `env:` son necesarias porque pydantic-settings exige los campos requeridos; en CI no se hace ninguna llamada real a Anthropic/Telegram. Cuando E5 (notificaciones) se implemente, los tests deben mockear esas integraciones.
- Si el CI tarda más de 3 min, revisar cache de uv.

---

## E01-S08 — README y verificación end-to-end de onboarding

**Como** dueño del sistema (y portfolio piece), **quiero** un README claro que cualquier desarrollador (incluyéndome a mí en 6 meses) pueda seguir, **para que** el onboarding sea < 10 minutos en máquina limpia y el repo sirva como evidencia de senioridad.

### Acceptance Criteria

- [ ] README incluye: descripción de 1 párrafo, badge de CI, prerequisitos, instrucciones de setup paso a paso, estructura del repo, link a documentos arquitectónicos en `docs/`.
- [ ] Sección "Quick start" con bloque de comandos copy-pasteable.
- [ ] Sección "Project structure" referenciando `B_Arquitectura_Sistema.md` para detalle.
- [ ] Verificación manual: en máquina limpia (o contenedor `ubuntu:24.04`), seguir el README y llegar a `pytest` corriendo en <10 min.
- [ ] `CONTRIBUTING.md` ligero (aunque solo seas tú: pasos para añadir feature, correr tests, abrir PR).

### Tasks

- [ ] Crear `README.md` con secciones: 
  - Header con título, descripción, badges
  - Why this exists (1 párrafo: contexto personal del proyecto)
  - Tech stack (lista)
  - Prerequisites (Docker, uv, Python 3.12+)
  - Quick start (5 comandos máx)
  - Project structure (referencia a docs)
  - Development workflow (lint, test, pre-commit)
  - License (Private / All rights reserved)
- [ ] Crear `CONTRIBUTING.md` con: branching strategy, conventional commits opcional, PR checklist
- [ ] Verificación end-to-end: usar `docker run -it ubuntu:24.04 bash`, instalar git+uv+docker, clonar, seguir README, cronometrar
- [ ] Cualquier paso confuso o que tome tiempo, refinar el README
- [ ] Tomar screenshot del CI verde, pegar en README como prueba
- [ ] Commit final, mergear todo a `main`, taguear `v0.1.0`

### Estimación: 1h

### Notas

- El README es **el primer artefacto que un reclutador o entrevistador ve**. Vale la pena 30 min extra para que esté bien.
- Considera añadir una sección "Architecture" con un mini-diagrama (puedes usar mermaid en GitHub directo) que linkee al Documento B.

---

## Orden de ejecución sugerido

**Sesión 1 (mañana, 3-4h):**
1. S01 — Repo init (30 min)
2. S02 — Python project (45 min)
3. S05 — Config management (1h) ← bloquea menos cosas que S03/S04 si la haces primero
4. S06 — Docker (1.5h)

**Sesión 2 (tarde, 3-4h):**
5. S03 — Quality tooling (1h)
6. S04 — Pytest (45 min)
7. S07 — CI pipeline (1h)
8. S08 — README + verificación (1h)

Si quieres terminar en una sola sesión maratónica, ~6-8h enfocadas. Si prefieres dividir en dos días, las sesiones de arriba son cortes naturales.

---

## Definition of Ready para próxima épica

E1 se considera cerrada cuando:

- [ ] Las 8 stories tienen todos sus AC ✅.
- [ ] CI verde en `main`.
- [ ] Verificación end-to-end pasa (S08).
- [ ] Tag `v0.1.0` creado.
- [ ] Documentos A, B, C, D, E referenciados en `docs/`.

A partir de aquí, **E2 (Data Persistence Layer)** es la siguiente. Su descomposición a L2 se hace cuando E1 esté cerrada (no antes — evita bikeshedding sobre detalles que pueden cambiar tras enfrentar la realidad del setup).

---

**Fin Documento E.**
