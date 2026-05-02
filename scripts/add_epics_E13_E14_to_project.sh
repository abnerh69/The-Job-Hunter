#!/bin/bash
# =============================================================================
# jobhunter-eu — Añadir Épicas E13 y E14 al GitHub Project (V2)
# Versión: 2026.05.02
# Proyecto: Sistema automatizado de búsqueda de empleo
# =============================================================================
# Este script añade dos opciones nuevas al campo "Epic" del Project ya
# existente (Project #2 de Informatica-ASHware):
#
#   - E13-QA Humana
#       Épica nueva contenedora de gaps de operación humana detectados
#       durante la verificación de E1–E12 (placeholder pages, comandos CLI
#       faltantes, prompts inline, audit log pendiente).
#
#   - E14-Onboarding
#       Épica nueva (no estaba en el plan original) que automatiza la
#       creación del perfil del candidato y sus variantes de CV a partir
#       de un master resume subido al wizard. Cambia arquitectura:
#       perfil pasa de archivos a entidades de primera clase en BD.
#       Ver `docs/adr/ADR-008-profile-in-db.md`.
#
# CONTEXTO HISTÓRICO:
# - El project se creó originalmente con `setup_jobhunter_project.sh` (12 épicas).
# - Los IDs de los campos existentes están en `project_manifest.json`.
# - GitHub Projects V2 NO permite añadir opciones a un single-select field
#   sin REPLACE de toda la lista. Este script preserva los IDs de las 12
#   épicas existentes y agrega 2 nuevas vía mutación GraphQL atómica.
# - Tras éxito, actualiza `project_manifest.json` con los nuevos IDs.
#
# IDEMPOTENCIA: si E13 / E14 ya existen, se detectan por nombre y se omiten
# (no se duplican opciones).
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

# Manifest del proyecto (fuente de verdad de IDs)
MANIFEST="project_manifest.json"

# Definición de las nuevas épicas a añadir.
# Formato por línea: NAME|COLOR|DESCRIPTION
# Colores válidos en GitHub Projects V2:
#   GRAY, BLUE, GREEN, YELLOW, ORANGE, RED, PINK, PURPLE
NEW_EPICS=(
    "E13-QA Humana|PURPLE|Rescate de desvíos cross-épica (UI/CLI/audit)"
    "E14-Onboarding|GREEN|Onboarding Automation & Profile Generation"
)

# ---------------------------------------------------------------------------
# 🛠️ VALIDACIONES
# ---------------------------------------------------------------------------
if ! command -v jq &> /dev/null; then
    echo -e "${RED}[ERROR] 'jq' no está instalado. Es necesario para procesar JSON.${NC}"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo -e "${RED}[ERROR] GitHub CLI no está autenticado. Corre 'gh auth login'.${NC}"
    exit 1
fi

if [ ! -f "$MANIFEST" ]; then
    echo -e "${RED}[ERROR] No se encontró '$MANIFEST'. Ejecuta este script desde la raíz del repo.${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 📥 LECTURA DEL CONTEXTO DEL PROYECTO
# ---------------------------------------------------------------------------
OWNER=$(jq -r '.project_context.owner' "$MANIFEST")
REPO=$(jq -r '.project_context.repo' "$MANIFEST")
PROJECT_NUMBER=$(jq -r '.project_context.project_number' "$MANIFEST")
PROJECT_ID=$(jq -r '.project_context.project_id' "$MANIFEST")
EPIC_FIELD_ID=$(jq -r '.mapping_guide[] | select(.field_name == "Epic") | .field_id' "$MANIFEST")

if [ -z "$EPIC_FIELD_ID" ] || [ "$EPIC_FIELD_ID" = "null" ]; then
    echo -e "${RED}[ERROR] No se encontró el campo 'Epic' en el manifest.${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 📊 RESUMEN PREVIO + CONFIRMACIÓN
# ---------------------------------------------------------------------------
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  Añadir Épicas E13 y E14 al GitHub Project${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "  Owner:           ${CYAN}${OWNER}${NC}"
echo -e "  Repo:            ${CYAN}${REPO}${NC}"
echo -e "  Project number:  ${CYAN}#${PROJECT_NUMBER}${NC}"
echo -e "  Project ID:      ${CYAN}${PROJECT_ID}${NC}"
echo -e "  Epic field ID:   ${CYAN}${EPIC_FIELD_ID}${NC}"
echo ""
echo -e "${YELLOW}Épicas a añadir:${NC}"
for entry in "${NEW_EPICS[@]}"; do
    IFS='|' read -r name color description <<< "$entry"
    echo -e "  • ${GREEN}${name}${NC} (color=${color}) — ${description}"
done
echo ""
read -p "¿Proceder? (s/n): " CONTINUE
if [[ ! "$CONTINUE" =~ ^[sS]$ ]]; then
    echo -e "${RED}Operación cancelada por el usuario.${NC}"
    exit 0
fi
echo ""

# ---------------------------------------------------------------------------
# 🔍 [1/4] CONSULTAR OPCIONES EXISTENTES
# ---------------------------------------------------------------------------
echo -e "${YELLOW}[1/4] Consultando opciones existentes del campo 'Epic'...${NC}"

EXISTING_OPTIONS_JSON=$(gh api graphql -f query="
query {
  node(id: \"${EPIC_FIELD_ID}\") {
    ... on ProjectV2SingleSelectField {
      options { id name color description }
    }
  }
}" --jq '.data.node.options')

if [ -z "$EXISTING_OPTIONS_JSON" ] || [ "$EXISTING_OPTIONS_JSON" = "null" ]; then
    echo -e "${RED}[ERROR] No se pudieron leer las opciones del campo Epic.${NC}"
    exit 1
fi

EXISTING_COUNT=$(echo "$EXISTING_OPTIONS_JSON" | jq 'length')
echo -e "  ${GREEN}✓${NC} ${EXISTING_COUNT} opciones existentes leídas."

# ---------------------------------------------------------------------------
# 🔧 [2/4] CONSTRUIR PAYLOAD DE OPCIONES (preservar existentes + añadir nuevas)
# ---------------------------------------------------------------------------
echo -e "${YELLOW}[2/4] Construyendo payload de opciones...${NC}"

# Empezar con las existentes (incluyendo sus IDs para preservarlas).
# Filtramos campos null en description para evitar errores de GraphQL.
MERGED_JSON=$(echo "$EXISTING_OPTIONS_JSON" | jq '[.[] | {id: .id, name: .name, color: .color, description: (.description // "")}]')

ADDED_NAMES=()
SKIPPED_NAMES=()

for entry in "${NEW_EPICS[@]}"; do
    IFS='|' read -r name color description <<< "$entry"

    # Verificar si ya existe por nombre exacto (idempotencia).
    EXISTS=$(echo "$MERGED_JSON" | jq -r --arg n "$name" '[.[] | select(.name == $n)] | length')

    if [ "$EXISTS" -gt 0 ]; then
        echo -e "  ${BLUE}ℹ${NC} '${name}' ya existe — se omite."
        SKIPPED_NAMES+=("$name")
    else
        # Append como nueva opción (sin id; GitHub asignará uno).
        MERGED_JSON=$(echo "$MERGED_JSON" | jq \
            --arg n "$name" \
            --arg c "$color" \
            --arg d "$description" \
            '. + [{name: $n, color: $c, description: $d}]')
        echo -e "  ${GREEN}+${NC} '${name}' será añadida."
        ADDED_NAMES+=("$name")
    fi
done

if [ ${#ADDED_NAMES[@]} -eq 0 ]; then
    echo -e "${GREEN}Todas las épicas ya existen. Nada que hacer.${NC}"
    exit 0
fi

TOTAL_AFTER=$(echo "$MERGED_JSON" | jq 'length')
echo -e "  ${GREEN}✓${NC} Payload listo: ${EXISTING_COUNT} existentes + ${#ADDED_NAMES[@]} nuevas = ${TOTAL_AFTER} opciones totales."

# ---------------------------------------------------------------------------
# 🔨 [3/4] CONSTRUIR Y EJECUTAR MUTATION GRAPHQL
# ---------------------------------------------------------------------------
echo -e "${YELLOW}[3/4] Ejecutando mutation updateProjectV2Field...${NC}"

# La mutación recibe la lista completa (con IDs preservados para las existentes).
# Construir el array GraphQL inline iterando el JSON con jq.
OPTIONS_GQL=""
while IFS= read -r row; do
    id=$(echo "$row" | jq -r '.id // ""')
    name=$(echo "$row" | jq -r '.name')
    color=$(echo "$row" | jq -r '.color')
    description=$(echo "$row" | jq -r '.description // ""')

    # Escapar comillas dobles en nombres/descripciones por seguridad.
    name_escaped=${name//\"/\\\"}
    description_escaped=${description//\"/\\\"}

    if [ -n "$id" ]; then
        OPTIONS_GQL+="{id: \"${id}\", name: \"${name_escaped}\", color: ${color}, description: \"${description_escaped}\"}, "
    else
        OPTIONS_GQL+="{name: \"${name_escaped}\", color: ${color}, description: \"${description_escaped}\"}, "
    fi
done < <(echo "$MERGED_JSON" | jq -c '.[]')

# Quitar la coma + espacio finales.
OPTIONS_GQL="${OPTIONS_GQL%, }"

# Ejecutar la mutation.
MUTATION_RESULT=$(gh api graphql -f query="
mutation {
  updateProjectV2Field(input: {
    fieldId: \"${EPIC_FIELD_ID}\"
    singleSelectOptions: [${OPTIONS_GQL}]
  }) {
    projectV2Field {
      ... on ProjectV2SingleSelectField {
        options { id name }
      }
    }
  }
}" 2>&1) || {
    echo -e "${RED}[ERROR] La mutation falló:${NC}"
    echo "$MUTATION_RESULT"
    exit 1
}

UPDATED_OPTIONS=$(echo "$MUTATION_RESULT" | jq '.data.updateProjectV2Field.projectV2Field.options')
UPDATED_COUNT=$(echo "$UPDATED_OPTIONS" | jq 'length')
echo -e "  ${GREEN}✓${NC} Mutation exitosa: ${UPDATED_COUNT} opciones en el campo Epic."

# Mostrar los IDs asignados a las nuevas épicas.
for name in "${ADDED_NAMES[@]}"; do
    new_id=$(echo "$UPDATED_OPTIONS" | jq -r --arg n "$name" '.[] | select(.name == $n) | .id')
    echo -e "    ${GREEN}→${NC} ${name}: ${CYAN}${new_id}${NC}"
done

# ---------------------------------------------------------------------------
# 📝 [4/4] ACTUALIZAR project_manifest.json CON LOS NUEVOS IDs
# ---------------------------------------------------------------------------
echo -e "${YELLOW}[4/4] Actualizando ${MANIFEST}...${NC}"

# Reconstruir el array de opciones del campo Epic con los IDs actualizados.
NEW_EPIC_OPTIONS=$(echo "$UPDATED_OPTIONS" | jq '[.[] | {name: .name, id: .id}]')

# Backup del manifest antes de modificarlo.
cp "$MANIFEST" "${MANIFEST}.bak"
echo -e "  ${GREEN}✓${NC} Backup creado: ${MANIFEST}.bak"

# Reemplazar las options del campo Epic preservando el resto del manifest.
jq --argjson new_options "$NEW_EPIC_OPTIONS" '
  .mapping_guide |= map(
    if .field_name == "Epic" then
      .options = $new_options
    else . end
  )
' "$MANIFEST" > "${MANIFEST}.tmp" && mv "${MANIFEST}.tmp" "$MANIFEST"

echo -e "  ${GREEN}✓${NC} ${MANIFEST} actualizado con ${UPDATED_COUNT} opciones de Epic."

# ---------------------------------------------------------------------------
# 📊 RESUMEN FINAL
# ---------------------------------------------------------------------------
echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN} 🎉 ÉPICAS E13 / E14 AÑADIDAS AL PROJECT EXITOSAMENTE${NC}"
echo -e "${BLUE}============================================================${NC}"
echo -e "Project URL:     https://github.com/orgs/${OWNER}/projects/${PROJECT_NUMBER}"
echo -e "Manifest:        ${MANIFEST} (backup: ${MANIFEST}.bak)"
echo ""
echo -e "${YELLOW}Resumen:${NC}"
echo -e "  Opciones añadidas: ${#ADDED_NAMES[@]}"
for name in "${ADDED_NAMES[@]}"; do
    echo -e "    • ${GREEN}${name}${NC}"
done
if [ ${#SKIPPED_NAMES[@]} -gt 0 ]; then
    echo -e "  Opciones omitidas (ya existían): ${#SKIPPED_NAMES[@]}"
    for name in "${SKIPPED_NAMES[@]}"; do
        echo -e "    • ${BLUE}${name}${NC}"
    done
fi
echo ""
echo -e "${YELLOW}PRÓXIMOS PASOS:${NC}"
echo -e "  1. Ejecutar: ${CYAN}bash scripts/create_issues_E13.sh${NC}"
echo -e "     → auto-descubrirá el OPT_EPIC_E13 desde el Project."
echo -e "  2. Ejecutar: ${CYAN}bash scripts/create_issues_E14.sh${NC}"
echo -e "     → auto-descubrirá el OPT_EPIC_E14 desde el Project."
echo -e "  3. Verificar issues en:"
echo -e "     ${CYAN}https://github.com/${OWNER}/${REPO}/issues?q=is%3Aissue+label%3Aepic%3AE13${NC}"
echo -e "     ${CYAN}https://github.com/${OWNER}/${REPO}/issues?q=is%3Aissue+label%3Aepic%3AE14${NC}"
echo -e "${BLUE}============================================================${NC}"
