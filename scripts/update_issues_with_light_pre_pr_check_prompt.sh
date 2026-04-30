#!/usr/bin/env bash
# Terminar el script inmediatamente si algún comando crítico falla
set -e

echo "🚀 Iniciando actualización masiva de Issues..."

# 1. Validar que la herramienta GitHub CLI (gh) esté instalada
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI (gh) no está instalado."
    echo "Puedes instalarlo desde: https://cli.github.com/"
    exit 1
fi

# 2. Validar que se haya iniciado sesión en gh
if ! gh auth status &> /dev/null; then
    echo "❌ Error: No se ha iniciado sesión en GitHub CLI."
    echo "Por favor, ejecuta 'gh auth login' antes de usar este script."
    exit 1
fi

# 3. Validar que estamos dentro de un repositorio Git local
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    echo "❌ Error: El directorio actual no es un repositorio Git."
    exit 1
fi

# 4. Definir el bloque de texto (El prompt ligero)
# Usamos un identificador único al principio para evitar duplicados en el futuro.
BLOCK_TEXT=$(cat << 'EOF'
> [!WARNING]
> **REGLA CRÍTICA DE CALIDAD PARA PULL REQUESTS**
>
> Como agente, TIENES PROHIBIDO crear un Pull Request (PR) o dar por finalizada una tarea de código sin antes validar la calidad del código localmente.
>
> ANTES de interactuar con GitHub para crear un PR, DEBES:
>
> 1. Ejecutar el script de validación ligera en la terminal:
>    `bash tools/light_pre_pr_check.sh`
> 2. Analizar el resultado:
>    - Este script valida Linter (Ruff), Formato (Ruff format) y Tipos estáticos (Mypy).
> 3. SI EL SCRIPT FALLA (exit code != 0):
>    - Detente. NO crees el PR.
>    - Lee el error en la terminal (problemas de tipado, variables no usadas, mal formato, etc.).
>    - Corrige el código y vuelve al paso 1.
> 4. SI EL SCRIPT ES EXITOSO (exit code == 0):
>    - Tienes luz verde para hacer el commit final, pushear los cambios y crear el Pull Request.
>
> Esta regla es estricta. Todo el código subido debe cumplir con las convenciones del proyecto validadas por las herramientas de CI incluidas en el script.

---

EOF
)

# Obtener información del repositorio actual para mostrar en consola
REPO_NAME=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
echo "📁 Repositorio detectado: $REPO_NAME"

# 5. Obtener los números de todos los issues abiertos
echo "🔍 Buscando issues abiertos..."
ISSUE_NUMBERS=$(gh issue list --state open --json number --jq '.[].number')

if [ -z "$ISSUE_NUMBERS" ]; then
    echo "ℹ️ No se encontraron issues abiertos en este repositorio."
    exit 0
fi

# 6. Iterar sobre cada issue para actualizarlo
for ISSUE in $ISSUE_NUMBERS; do
    echo "🔄 Procesando Issue #$ISSUE..."

    # Obtener el contenido actual del issue
    CURRENT_BODY=$(gh issue view "$ISSUE" --json body --jq '.body')

    # Validar si el bloque ya existe para no duplicarlo (busca la primera frase clave)
    if echo "$CURRENT_BODY" | grep -q "REGLA CRÍTICA DE CALIDAD PARA PULL REQUESTS"; then
        echo "   ⚠️ El Issue #$ISSUE ya tiene la regla aplicada. Omitiendo."
        continue
    fi

    # Crear un archivo temporal para construir el nuevo contenido
    # (Usar un archivo temporal es más seguro que manejar cadenas gigantes con saltos de línea en Bash)
    TEMP_FILE=$(mktemp)

    # Escribir el bloque nuevo
    printf "%s\n" "$BLOCK_TEXT" > "$TEMP_FILE"
    # Añadir el contenido original debajo
    printf "%s\n" "$CURRENT_BODY" >> "$TEMP_FILE"

    # 7. Actualizar el issue en GitHub
    gh issue edit "$ISSUE" --body-file "$TEMP_FILE" > /dev/null 2>&1

    # Limpiar el archivo temporal
    rm "$TEMP_FILE"

    echo "   ✅ Issue #$ISSUE actualizado correctamente."
done

echo "🎉 ¡Finalizado! Todos los issues abiertos han sido actualizados."