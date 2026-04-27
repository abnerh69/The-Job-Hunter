#!/bin/bash
# =============================================================================
# jobhunter-eu — Generador de GitHub Project (V2)
# Versión: 2026.04.27
# Proyecto: Sistema automatizado de búsqueda de empleo
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# ⚙️ CONFIGURACIÓN
# ---------------------------------------------------------------------------
# Colores para terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# 🛠️ VALIDACIONES
# ---------------------------------------------------------------------------
if ! command -v jq &> /dev/null; then
    echo -e "${RED}[ERROR] 'jq' no está instalado. Es necesario para procesar JSON.${NC}"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo -e "${RED}[ERROR] GitHub CLI no está autenticado.${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 🔍 VALIDACIÓN DE REPOSITORIO Y OBTENCIÓN DE DATOS
# ---------------------------------------------------------------------------

# 1. Validar si es un repositorio Git
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo -e "${RED}[ERROR] Este script debe ejecutarse desde el directorio de un repositorio Git.${NC}"
    exit 1
fi

# 2. Obtener el OWNER (Sugerir el usuario actual de GitHub como default)
SUGGESTED_OWNER=$(gh api user -q .login)
echo -e "${BLUE}➤ Configuración del Propietario (Owner)${NC}"
read -p "Ingresa el Usuario u Organización de GitHub [$SUGGESTED_OWNER]: " INPUT_OWNER
OWNER=${INPUT_OWNER:-$SUGGESTED_OWNER}

# 3. Obtener el NOMBRE DEL PROYECTO
DEFAULT_NAME="jobhunter-eu — Algorithmic Job Search"
echo -e "\n${BLUE}➤ Configuración del Nombre del Proyecto${NC}"
read -p "Ingresa el nombre para el proyecto [$DEFAULT_NAME]: " INPUT_NAME
PROJECT_NAME=${INPUT_NAME:-$DEFAULT_NAME}

# 4. Confirmación Final
echo -e "\n${YELLOW}============================================================${NC}"
echo -e "${YELLOW} RESUMEN DE CONFIGURACIÓN${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo -e "  Owner:        ${CYAN}$OWNER${NC}"
echo -e "  Proyecto:     ${CYAN}$PROJECT_NAME${NC}"
echo -e "  Repositorio:  ${CYAN}$(git remote get-url origin)${NC}"
echo -e "${YELLOW}============================================================${NC}"

read -p "¿Deseas proceder con la creación? (s/n): " CONTINUE
if [[ ! "$CONTINUE" =~ ^[sS]$ ]]; then
    echo -e "${RED}Operación cancelada por el usuario.${NC}"
    exit 0
fi
echo -e "${GREEN}Continuando...${NC}\n"

# ---------------------------------------------------------------------------
# 🚀 INICIO DEL PROCESO
# ---------------------------------------------------------------------------
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}   jobhunter-eu: Configuración de GitHub Project V2${NC}"
echo -e "${BLUE}============================================================${NC}"

# 1. Buscar o Crear el Proyecto
echo -e "${YELLOW}[1/5] Validando existencia del proyecto...${NC}"
EXISTING_PROJECT=$(gh project list --owner "$OWNER" --format json -q ".projects[] | select(.title == \"$PROJECT_NAME\")" 2>/dev/null || echo "")

if [ -n "$EXISTING_PROJECT" ]; then
    echo -e "${GREEN}✓ Proyecto encontrado. Recuperando datos...${NC}"
    PROJECT_ID=$(echo "$EXISTING_PROJECT" | jq -r '.id')
    PROJECT_NUMBER=$(echo "$EXISTING_PROJECT" | jq -r '.number')
else
    echo -e "${YELLOW}Creando nuevo proyecto: ${PROJECT_NAME}...${NC}"
    CREATE_RESP=$(gh project create --owner "$OWNER" --title "$PROJECT_NAME" --format json)
    PROJECT_ID=$(echo "$CREATE_RESP" | jq -r '.id')
    PROJECT_NUMBER=$(echo "$CREATE_RESP" | jq -r '.number')
    echo -e "${GREEN}✓ Proyecto creado con ID: $PROJECT_ID${NC}"
fi

echo -e "${GREEN}✓ Proyecto configurado con ID: $PROJECT_ID (Número: $PROJECT_NUMBER)${NC}"

# Obtener la lista actual de campos para evitar llamadas repetitivas a la API
CURRENT_FIELDS=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json -q '.fields[].name' 2>/dev/null || echo "")

# Función para crear campos de forma idempotente
ensure_field() {
    local name="$1"
    local type="$2"
    local options="$3"

    if echo "$CURRENT_FIELDS" | grep -qxw "$name" 2>/dev/null; then
        echo -e "  ${BLUE}ℹ${NC} Campo '$name' ya existe. Omitiendo..."
    else
        echo -e "  ${GREEN}✓${NC} Creando campo '$name'..."
        gh project field-create "$PROJECT_NUMBER" --owner "$OWNER" --name "$name" --data-type "$type" --single-select-options "$options" > /dev/null 2>&1 || echo -e "  ${YELLOW}⚠${NC} Error creando campo '$name' (puede existir o rechazar formato)"
    fi
}

# 2. Configurar Campo: Épicas (E1 a E12)
echo -e "${YELLOW}[2/5] Configurando campo 'Epic'...${NC}"
ensure_field "Epic" "SINGLE_SELECT" "E1-Foundation,E2-Persistence,E3-Ingestion,E4-Scoring,E5-Notifications,E6-Toolkit,E7-Dashboard,E8-Automation,E9-Outreach,E10-Gmail,E11-Analytics,E12-Observability"

# 3. Configurar Campo: Priority
echo -e "${YELLOW}[3/5] Configurando campo 'Priority'...${NC}"
ensure_field "Priority" "SINGLE_SELECT" "P0-MVP Critical,P1-MVP Desirable,P2-Post-MVP"

# 4. Configurar Campo: Wave (Olas de desarrollo)
echo -e "${YELLOW}[4/5] Configurando campo 'Wave'...${NC}"
ensure_field "Wave" "SINGLE_SELECT" "Wave 1 (MVP),Wave 2 (Productivity),Wave 3 (Operations)"

# 5. Configurar Campo: Sprint
echo -e "${YELLOW}[5/5] Configurando campo 'Sprint'...${NC}"
ensure_field "Sprint" "SINGLE_SELECT" "S0,S1,S2,S3,S4"

# Campos opcionales (sin parar si fallan)
echo -e "${BLUE}[+] Configurando campos opcionales...${NC}"
ensure_field "Size" "SINGLE_SELECT" "S,M,L,XL"
#ensure_field "Status" "SINGLE_SELECT" "Not Started,In Progress,Blocked,Done"
ensure_field "Dependencies" "TEXT" ""

# ---------------------------------------------------------------------------
# 📊 RESUMEN
# ---------------------------------------------------------------------------
echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN} 🎉 PROYECTO CONFIGURADO EXITOSAMENTE${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "Nombre:     $PROJECT_NAME"
echo -e "ID:         $PROJECT_ID"
echo -e "Número:     $PROJECT_NUMBER"
echo -e "URL:        https://github.com/users/$OWNER/projects/$PROJECT_NUMBER"
echo -e "${BLUE}============================================================${NC}"
echo -e "${YELLOW}PRÓXIMOS PASOS:${NC}"
echo -e "1. Usa PROJECT_NUMBER ($PROJECT_NUMBER) en scripts de creación de issues"
echo -e "2. Las épicas están listas como opciones en el campo 'Epic'"
echo -e "3. Ref. backlog: Documento D — Épicas jobhunter-eu"
echo ""
