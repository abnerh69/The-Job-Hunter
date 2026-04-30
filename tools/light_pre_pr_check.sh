#!/usr/bin/env bash
# Terminar el script inmediatamente si algún comando falla
set -e

echo "🚀 Iniciando validación local ligera (Fast Pre-PR Check)..."

# Configurar variables de entorno dummy necesarias para que el código compile/importe bien
export ANTHROPIC_API_KEY="dummy_key_for_ci"
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
export TELEGRAM_CHAT_ID="123456789"
export PYTHONPATH="src"

echo "📥 Sincronizando dependencias..."
uv sync --all-groups

echo "🔍 Ejecutando Ruff Linter..."
uv run ruff check .

echo "🎨 Comprobando formato con Ruff..."
uv run ruff format --check .

echo "🧐 Ejecutando chequeo de tipos con Mypy..."
uv run mypy .

echo "🧪 Ejecutando tests (Solo lógica, sin base de datos real)..."
# Nota: Si tienes tests que dependen de la DB, puedes omitir este paso
# o usar un flag como `-m "not db"` si usas marcas (markers) en pytest.
uv run pytest -v --cov

echo "🎉 ¡Todo en verde! Validación ligera completada con éxito. Ya puedes crear el PR."