# Arquitectura de Job Hunter EU

## 🎯 Contexto
Job Hunter EU es un sistema automatizado diseñado para optimizar la búsqueda de empleo en Europa.

## 🏗️ Estructura del Proyecto

La estructura del repositorio sigue una organización modular por dominios:

- `src/jobhunter/`: Directorio raíz del código fuente.
  - `db/`: Gestión de la base de datos y modelos.
  - `sources/`: Integraciones con diferentes portales de empleo y fuentes de datos.
  - `scoring/`: Algoritmos para calificar la relevancia de las ofertas.
  - `application/`: Lógica central para la gestión de aplicaciones.
  - `notify/`: Sistema de notificaciones (email, slack, etc.).
  - `dashboard/`: Visualización de métricas y estado del sistema.
  - `outreach/`: Automatización de contacto y seguimiento.

- `tests/`: Suite de pruebas.
  - `unit/`: Pruebas unitarias para componentes individuales.
  - `integration/`: Pruebas de integración entre módulos.
  - `fixtures/`: Datos y configuraciones de prueba reutilizables.

- `docs/`: Documentación técnica y arquitectónica.
- `alembic/`: Migraciones de base de datos.
- `.github/workflows/`: Pipelines de CI/CD.

## ✅ Estándares de Calidad
- **Código Limpio**: Uso de `ruff` para linting.
- **Tipado Estático**: Uso de `mypy --strict` para garantizar la seguridad de tipos.
- **Testing**: Pruebas automatizadas con `pytest`.
