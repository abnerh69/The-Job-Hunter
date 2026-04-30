#!/usr/bin/env bash
# Terminar el script inmediatamente si algún comando falla
set -e

echo "🚀 Iniciando validación local (Pre-PR Check)..."

# Verificar si Docker está en ejecución
if ! docker info > /dev/null 2>&1; then
  echo "❌ Error: Docker no está en ejecución. Por favor, inicia Docker e inténtalo de nuevo."
  exit 1
fi

CONTAINER_NAME="jobhunter-db-ci-local"

# Limpiar cualquier contenedor previo que haya quedado colgado
docker rm -f $CONTAINER_NAME 2>/dev/null || true

echo "📦 Levantando contenedor de PostgreSQL efímero..."
docker run --name $CONTAINER_NAME \
  -e POSTGRES_USER=jobhunter \
  -e POSTGRES_PASSWORD=jobhunter_local \
  -e POSTGRES_DB=jobhunter \
  -p 5432:5432 \
  -d postgres:16-alpine > /dev/null

# Función para limpiar el contenedor al finalizar (incluso si el script falla)
cleanup() {
  echo "🧹 Limpiando contenedor de PostgreSQL..."
  docker rm -f $CONTAINER_NAME > /dev/null
}
trap cleanup EXIT

echo "⏳ Esperando a que PostgreSQL esté listo..."
until docker exec $CONTAINER_NAME pg_isready -U jobhunter > /dev/null 2>&1; do
  sleep 1
done
echo "✅ Base de datos lista."

# Configurar las variables de entorno exactas del CI
export DATABASE_URL="postgresql://jobhunter:jobhunter_local@localhost:5432/jobhunter"
export ANTHROPIC_API_KEY="dummy_key_for_ci"
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
export TELEGRAM_CHAT_ID="123456789"
export PYTHONPATH="src"

echo "📥 Instalando/Sincronizando dependencias..."
uv sync --all-groups

echo "🔍 Ejecutando Ruff Linter..."
uv run ruff check .

echo "🎨 Comprobando formato con Ruff..."
uv run ruff format --check .

echo "🧐 Ejecutando chequeo de tipos con Mypy..."
uv run mypy .

echo "🗄️ Ejecutando migraciones de base de datos (Alembic)..."
uv run alembic upgrade head

echo "🧪 Ejecutando tests con cobertura..."
uv run pytest -v --cov

echo "🎉 ¡Todo en verde! Validación local completada con éxito. Ya puedes crear el PR."