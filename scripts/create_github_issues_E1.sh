#!/bin/bash
# =============================================================================
# Job-Hunter-EU — Generador Automático de Issues
# Épica: E1 — Foundation & Project Bootstrap
# =============================================================================
# Requisito: gh (GitHub CLI) instalado y autenticado (`gh auth login`)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# ⚙️ CONFIGURACIÓN DEL REPOSITORIO Y PROYECTO
# ---------------------------------------------------------------------------
OWNER="Informatica-ASHware"
REPO="Job-Hunter-EU"
FULL_REPO="${OWNER}/${REPO}"
PROJECT_NUMBER="2"
PROJECT_ID="PVT_kwDOEBSEkc4BV46-"

# ---------------------------------------------------------------------------
# 🗂️ IDs DE LOS CAMPOS DEL PROYECTO (del manifest)
# ---------------------------------------------------------------------------
FIELD_EPIC="PVTSSF_lADOEBSEkc4BV46-zhRRYn4"
FIELD_PRIORITY="PVTSSF_lADOEBSEkc4BV46-zhRRYpk"

# ---------------------------------------------------------------------------
# 🎯 OPTION IDs — Epic E1 & Priority P0
# ---------------------------------------------------------------------------
OPT_EPIC_E1="0fe443e8"           # E1-Foundation
OPT_PRIORITY_P0="6f783caf"       # P0-MVP Critical

# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SUCCESS_COUNT=0
FAIL_COUNT=0

DOD_TEMPLATE="
### ✅ Definition of Done (DoD)
1. **Código Limpio:** Pasa linters (\`ruff check\`) y \`mypy --strict\` sin violaciones.
2. **Testing:** Tests unitarios pasando en verde si aplica.
3. **Documentación:** Cambios significativos documentados; estructura clara en README.
4. **Verificación:** Pasos de aceptación ejecutados manualmente y confirmados.
5. **Revisión:** Cambios commiteados, CI en verde."

# ---------------------------------------------------------------------------
# 🛠️ FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

create_issue() {
    local title="$1"
    local body="$2"
    local labels="$3"
    local opt_epic="$4"
    local opt_priority="$5"

    echo -e "${BLUE}Creando issue:${NC} $title"

    # 1. Crear el Issue y capturar la URL
    local issue_url
    if issue_url=$(gh issue create \
        --repo "$FULL_REPO" \
        --title "$title" \
        --body "$body" \
        --label "$labels" 2>/dev/null); then

        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo -e "  ${GREEN}✓${NC} Issue creado: $issue_url"

        # 2. Añadir el Issue al GitHub Project
        local item_id
        if item_id=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$issue_url" --format json -q '.id' 2>/dev/null); then
            echo -e "  ${GREEN}✓${NC} Añadido al Proyecto."

            # 3. Editar los campos del proyecto
            if [ -n "$opt_epic" ]; then
                gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$FIELD_EPIC" --single-select-option-id "$opt_epic" >/dev/null 2>&1
            fi
            if [ -n "$opt_priority" ]; then
                gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$FIELD_PRIORITY" --single-select-option-id "$opt_priority" >/dev/null 2>&1
            fi
            echo -e "  ${GREEN}✓${NC} Metadatos (Epic, Priority) asignados."
        else
            echo -e "  ${YELLOW}⚠${NC} Issue creado pero no se pudo añadir al proyecto."
        fi
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo -e "  ${RED}✗${NC} Error creando el issue: $title"
    fi

    # Pausa intencional para API Rate Limit
    sleep 1.5
}

# ---------------------------------------------------------------------------
# 🔖 VERIFICACIÓN DE LABELS NECESARIOS
# ---------------------------------------------------------------------------

echo -e "${YELLOW}Verificando/creando labels necesarios...${NC}"

create_label_if_missing() {
    local label="$1"
    local color="$2"
    local description="$3"
    if ! gh label list --repo "$FULL_REPO" --json name -q '.[].name' | grep -q "^${label}$"; then
        gh label create "$label" --repo "$FULL_REPO" --color "$color" --description "$description" 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} Label creado: $label"
    fi
}

create_label_if_missing "status:ready"     "0075ca" "Issue listo para ser trabajado"
create_label_if_missing "type:infra"       "004b97" "Tarea de infraestructura"
create_label_if_missing "component:devops" "1d76db" "Componente DevOps/CI-CD"
create_label_if_missing "epic:E1"          "0E8A16" "Épica E1 - Foundation"

echo ""

# ---------------------------------------------------------------------------
# 🚀 MAIN - CREACIÓN DE BACKLOG PARA E1
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Generador de Backlog Job-Hunter-EU V1 — Épica E1"
echo " Repositorio: ${FULL_REPO} | Proyecto: #${PROJECT_NUMBER}"
echo "============================================================"
echo ""

# E01-S01 — Inicializar repositorio y estructura base
create_issue \
    "[E01-S01] Inicializar repositorio y estructura base" \
    "## 🎯 Contexto
El punto de partida. Crear un repositorio Git limpio con estructura de directorios predecible, \`.gitignore\` robusto y configuración inicial.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] Repositorio Git inicializado, branch principal \`main\`
- [ ] \`.gitignore\` cubre Python, IDE, DB locales, build artifacts
- [ ] Estructura de directorios según arquitectura (src/, tests/, docs/, alembic/, .github/workflows/)
- [ ] Repositorio configurado como privado en GitHub
- [ ] Documentos arquitectónicos copiados en \`docs/\`

### Tasks
- [ ] \`git init && git branch -m main\`
- [ ] Crear \`.gitignore\` exhaustivo para Python + macOS/Linux + VSCode
- [ ] Crear estructura: \`src/jobhunter/{db,sources,scoring,application,notify,dashboard,outreach}/\`, \`tests/{unit,integration,fixtures}/\`, \`docs/\`, \`alembic/\`, \`.github/workflows/\`
- [ ] \`touch .gitkeep\` en directorios vacíos
- [ ] Copiar documentos arquitectónicos a \`docs/\`
- [ ] Crear repo en GitHub (privado), añadir como remote, primer push

## ⏱️ Estimación: 30 min

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S02 — Configurar proyecto Python con uv
create_issue \
    "[E01-S02] Configurar proyecto Python con uv" \
    "## 🎯 Contexto
Gestión moderna de dependencias con \`uv\`. Lock file garantiza reproducibilidad; instalación instantánea.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`pyproject.toml\` declarando proyecto, Python ≥3.12, dependencias mínimas iniciales
- [ ] \`uv\` instalado y \`uv sync\` corre sin errores
- [ ] \`uv.lock\` generado y commiteado
- [ ] Virtual env reproducible: borrar \`.venv\` y \`uv sync\` lo regenera idéntico
- [ ] \`uv run python -c \"import jobhunter; print('ok')\"\` ejecuta exitosamente

### Tasks
- [ ] Instalar \`uv\`: \`curl -LsSf https://astral.sh/uv/install.sh | sh\`
- [ ] \`uv init --package jobhunter --python 3.12\`
- [ ] Editar \`pyproject.toml\`: nombre, descripción, autor, license=Proprietary
- [ ] Añadir dependencias core: \`httpx\`, \`sqlalchemy>=2.0\`, \`alembic\`, \`pydantic>=2\`, \`pydantic-settings\`, \`anthropic\`, \`structlog\`, \`typer\`
- [ ] Añadir dependencias de dev: \`pytest\`, \`pytest-asyncio\`, \`pytest-cov\`, \`ruff\`, \`mypy\`, \`pre-commit\`
- [ ] \`uv sync\`
- [ ] Crear \`src/jobhunter/__init__.py\` con \`__version__ = \"0.1.0\"\`
- [ ] Verificar import con \`uv run python -c \"import jobhunter; print(jobhunter.__version__)\"\`
- [ ] Commit

## ⏱️ Estimación: 45 min

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S03 — Tooling de calidad: ruff, black, mypy, pre-commit
create_issue \
    "[E01-S03] Tooling de calidad: ruff, black, mypy, pre-commit" \
    "## 🎯 Contexto
Linting, formatting y type-checking automatizados. Pre-commit hooks previenen commits sucios. \`detect-secrets\` evita API keys commiteadas.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`ruff check src/ tests/\` corre sin errores sobre código mínimo
- [ ] \`ruff format\` integrado como source of truth de formateo
- [ ] \`mypy --strict src/jobhunter/\` corre sin errores
- [ ] \`pre-commit install\` registrado; hooks corren al hacer commit local
- [ ] Configuración centralizada en \`pyproject.toml\`

### Tasks
- [ ] Configurar \`[tool.ruff]\` en \`pyproject.toml\`: line-length=100, target-version=py312
- [ ] Configurar \`[tool.ruff.format]\`
- [ ] Configurar \`[tool.mypy]\`: strict=true, python_version=3.12
- [ ] Crear \`.pre-commit-config.yaml\` con hooks: ruff, mypy, check-yaml, check-toml, end-of-file-fixer, trailing-whitespace, detect-secrets
- [ ] \`uv run pre-commit install\`
- [ ] \`uv run pre-commit run --all-files\` para primera pasada
- [ ] Resolver violaciones
- [ ] \`detect-secrets scan > .secrets.baseline\`
- [ ] Commit

## ⏱️ Estimación: 1h

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S04 — Framework de testing con pytest
create_issue \
    "[E01-S04] Framework de testing con pytest" \
    "## 🎯 Contexto
Infraestructura de testing lista. \`pytest-asyncio\` para scrapers async. \`pytest-cov\` para coverage reporting.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`uv run pytest\` ejecuta sin errores
- [ ] Al menos un test smoke (\`test_imports\`) verifica que el paquete se importa
- [ ] \`pytest-asyncio\` configurado (\`asyncio_mode = auto\`)
- [ ] \`pytest-cov\` configurado, reporta coverage
- [ ] Estructura \`tests/unit/\`, \`tests/integration/\`, \`tests/fixtures/\` con \`__init__.py\` y \`conftest.py\`

### Tasks
- [ ] Configurar \`[tool.pytest.ini_options]\` en \`pyproject.toml\`: testpaths=[\"tests\"], asyncio_mode=auto
- [ ] Configurar \`[tool.coverage.run]\`: source=[\"src/jobhunter\"], branch=true
- [ ] Crear \`tests/conftest.py\` con fixtures placeholders
- [ ] Crear \`tests/unit/test_smoke.py\` con test trivial
- [ ] Correr \`uv run pytest -v --cov\` y verificar output limpio
- [ ] Commit

## ⏱️ Estimación: 45 min

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S05 — Gestión de configuración con pydantic-settings
create_issue \
    "[E01-S05] Gestión de configuración con pydantic-settings" \
    "## 🎯 Contexto
Variables de entorno fuertemente tipadas. Un único \`Settings\` que valida y centraliza toda la configuración (DB, APIs, Telegram, etc.).

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`Settings\` dataclass usando \`pydantic.BaseSettings\` cubre: DATABASE_URL, ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_USER, SMTP_PASSWORD, DIGEST_TO_EMAIL
- [ ] Parsing automático de \`.env\` (via \`pydantic.settings.SettingsConfigDict\`)
- [ ] Valores por defecto sensatos para dev; required en producción
- [ ] Logging de settings no-sensibles al startup
- [ ] Tests unitarios verifican parsing y validación

### Tasks
- [ ] Crear \`src/jobhunter/config.py\` con clase \`Settings\`
- [ ] Configurar \`SettingsConfigDict\` con env_file=\".env\"
- [ ] Crear \`.env.example\` con placeholders y documentación
- [ ] Crear \`.env\` local (no committed) para desarrollo
- [ ] Tests: \`test_config.py\` verifica parsing desde vars de entorno
- [ ] Crear \`src/jobhunter/__main__.py\` que instancia \`Settings\` y printea versión
- [ ] Verificar que \`uv run python -m jobhunter\` muestra config sin errores
- [ ] Commit

## ⏱️ Estimación: 1h

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S06 — Entorno containerizado: Docker + Postgres
create_issue \
    "[E01-S06] Entorno containerizado: Docker + Postgres" \
    "## 🎯 Contexto
\`docker-compose.yml\` con Postgres y app. Desarrollo local hermético; cualquier máquina con Docker corre el proyecto idéntico.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`docker-compose.yml\` define dos servicios: postgres (16-alpine) y app
- [ ] Health check de Postgres asegura que está listo antes de app
- [ ] \`.env\` y \`.env.example\` documentan DATABASE_URL
- [ ] \`Dockerfile\` multi-stage, usa imagen oficial de uv, instalación reproducible
- [ ] \`docker-compose up -d\` levanta servicios sin error
- [ ] \`docker-compose down -v\` borra todo (incluido volumen de datos)

### Tasks
- [ ] Crear \`docker-compose.yml\` con servicios postgres y app
- [ ] Postgres en puerto 5432, usuario/password documentados
- [ ] Crear \`Dockerfile\` multi-stage: builder con uv, runner ligera
- [ ] Añadir \`DATABASE_URL=postgresql://jobhunter:jobhunter_local@localhost:5432/jobhunter\` a \`.env.example\`
- [ ] Test manual: \`docker-compose up -d postgres && psql ... -c \"SELECT 1;\"\`
- [ ] Documentar en README: reset completo es \`docker-compose down -v\`
- [ ] Commit

## ⏱️ Estimación: 1.5h

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S07 — CI pipeline en GitHub Actions
create_issue \
    "[E01-S07] CI pipeline en GitHub Actions" \
    "## 🎯 Contexto
Cada push/PR dispara linting, type-checking, tests automáticamente. CI verde es prerequisito para merge.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] \`.github/workflows/ci.yml\` corre en push a \`main\` y en PRs
- [ ] CI ejecuta: ruff check, ruff format --check, mypy, pytest
- [ ] Tests corren contra Postgres provisto por runner
- [ ] CI falla si cualquier paso falla
- [ ] Tiempo total < 3 minutos
- [ ] Badge de status en README

### Tasks
- [ ] Crear \`.github/workflows/ci.yml\` con job quality
- [ ] Setup: checkout, astral-sh/setup-uv, Python 3.12
- [ ] Postgres service en CI con credenciales dummy
- [ ] Steps: install deps, lint, format check, type check, pytest
- [ ] Env vars dummy para Anthropic/Telegram (CI no hace calls reales)
- [ ] Push, verificar que workflow corre y pasa
- [ ] Commit

## ⏱️ Estimación: 1h

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

# E01-S08 — README y verificación end-to-end de onboarding
create_issue \
    "[E01-S08] README y verificación end-to-end de onboarding" \
    "## 🎯 Contexto
README claro y testeable. Portfolio piece que demuestra senioridad en setup, documentación, CI/CD. E1 se cierra cuando cualquiera (incluyéndote en 6 meses) puede clonar y correr en <10 minutos.

## 📐 Alcance Técnico

### Acceptance Criteria
- [ ] README incluye: descripción, badge CI, prerequisitos, setup paso a paso, estructura del repo, links a arquitectura
- [ ] Sección \"Quick start\" con 5 comandos copy-pasteable
- [ ] Sección \"Project structure\" referenciando docs/
- [ ] Verificación manual: en máquina limpia, seguir README y llegar a \`pytest\` en <10 min
- [ ] \`CONTRIBUTING.md\` ligero con branching strategy y PR checklist
- [ ] Badge de CI en README (screenshot o markdown badge)

### Tasks
- [ ] Crear \`README.md\` con secciones: header, Why this exists, Tech stack, Prerequisites, Quick start, Project structure, Development workflow, License
- [ ] Crear \`CONTRIBUTING.md\` con branching strategy, conventional commits, PR checklist
- [ ] Verificación end-to-end: \`docker run -it ubuntu:24.04 bash\`, instalar git+uv+docker, clonar, seguir README, cronometrar
- [ ] Refinar README si algún paso es confuso o toma tiempo
- [ ] Tomar screenshot del CI verde, pegar en README
- [ ] Commit final, mergear todo a \`main\`, crear tag \`v0.1.0\`

## ⏱️ Estimación: 1h

${DOD_TEMPLATE}" \
    "status:ready,type:infra,component:devops,epic:E1" \
    "$OPT_EPIC_E1" \
    "$OPT_PRIORITY_P0"

echo ""
echo "============================================================"
echo -e " ${GREEN}PROCESO COMPLETADO${NC}"
echo -e " Issues creados exitosamente: ${GREEN}${SUCCESS_COUNT}${NC}"
echo -e " Issues fallidos:             ${RED}${FAIL_COUNT}${NC}"
echo "============================================================"
echo ""
echo -e "${BLUE}Próximos pasos:${NC}"
echo "1. Verifica que los 8 issues aparezcan en el proyecto"
echo "2. Asigna los issues a ti mismo en GitHub"
echo "3. Comienza con E01-S01 siguiendo el orden sugerido"
echo ""
