#!/usr/bin/env bash
# Terminar el script inmediatamente si algún comando falla
set -e

echo "🚀 Iniciando validación local ligera (Fast Pre-PR Check)..."

# Configurar variables de entorno dummy necesarias para que el código compile/importe bien
export ANTHROPIC_API_KEY="dummy_key_for_ci"
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
export TELEGRAM_CHAT_ID="123456789"
export DASHBOARD_PASSWORD="dummy_password_for_tests"
export PYTHONPATH="src"

# Usar una DB en memoria o dummy para que SQLAlchemy no explote al importar
export DATABASE_URL="sqlite:///:memory:"

echo "📥 Instalando/Sincronizando dependencias..."
uv sync --all-groups

echo "Install Playwright Browsers..."
uv run playwright install chromium

echo "🔍 Ejecutando Ruff Linter..."
uv run ruff check .

echo "🎨 Comprobando formato con Ruff..."
uv run ruff format --check .

echo "🧐 Ejecutando chequeo de tipos con Mypy..."
uv run mypy .

echo "🧪 Ejecutando tests (Excluyendo integración con DB)..."
# Usaremos el marcador "db" para excluir esos tests
uv run pytest -v --cov --ignore=tests/e2e -m "not db"

echo "🎉 ¡Todo en verde! Validación ligera completada con éxito. Ya puedes crear el PR."