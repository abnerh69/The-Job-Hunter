# Job Hunter EU - Manual Integral de Operaciones y Recuperación ante Desastres (Runbook)

Este documento constituye la fuente definitiva de información técnica para la gestión, mantenimiento, resolución de problemas y recuperación ante desastres del ecosistema **Job Hunter EU**. Está diseñado para ser utilizado por ingenieros de confiabilidad (SRE), desarrolladores y usuarios finales avanzados que necesiten mantener la continuidad del servicio.

---

## 📑 0. Tabla de Contenidos

1. [Introducción y Filosofía del Sistema](#1-introducción-y-filosofía-del-sistema)
2. [Arquitectura Detallada y Componentes](#2-arquitectura-detallada-y-componentes)
3. [Setup Inicial y Despliegue de Infraestructura](#3-setup-inicial-y-despliegue-de-infraestructura)
4. [Guía de Configuración Completa (Variables de Entorno)](#4-guía-de-configuración-completa-variables-de-entorno)
5. [Modelo de Datos y Gestión del Esquema (Alembic)](#5-modelo-de-datos-y-gestión-del-esquema-alembic)
6. [Fuentes de Datos (Ingestion Sources) y Scrapers](#6-fuentes-de-datos-ingestion-sources-y-scrapers)
7. [Motor de Scoring y Lógica de Inteligencia Artificial](#7-motor-de-scoring-y-lógica-de-inteligencia-artificial)
8. [Operación Diaria: "Un día en la vida de Job Hunter"](#8-operación-diaria-un-día-en-la-vida-de-job-hunter)
9. [Monitoreo de Salud y Observabilidad](#9-monitoreo-de-salud-y-observabilidad)
10. [Gestión de Notificaciones e Interactividad (Telegram)](#10-gestión-de-notificaciones-e-interactividad-telegram)
11. [Mantenimiento Preventivo y Tareas de Limpieza](#11-mantenimiento-preventivo-y-tareas-de-limpieza)
12. [Estrategias de Optimización de Costos (LLM)](#12-estrategias-de-optimización-de-costos-llm)
13. [Sistema de Analítica y Detección de Regresiones](#13-sistema-de-analítica-y-detección-de-regresiones)
14. [Troubleshooting: Resolución de 10 Problemas Críticos](#14-troubleshooting-resolución-de-10-problemas-críticos)
15. [Disaster Recovery: Los 5 Escenarios Catastróficos](#15-disaster-recovery-los-5-escenarios-catastróficos)
16. [Simulacros (Drills) de Seguridad y Recuperación](#16-simulacros-drills-de-seguridad-y-recuperación)
17. [Seguridad, Privacidad y Cumplimiento (GDPR)](#17-seguridad-privacidad-y-cumplimiento-gdpr)
18. [Guía para Desarrolladores y Estándares de Calidad](#18-guía-para-desarrolladores-y-estándares-de-calidad)
19. [Checklists de Operación Estándar (SOPs)](#19-checklists-de-operación-estándar-sops)
20. [Glosario de Error Codes y Términos Técnicos](#20-glosario-de-error-codes-y-términos-técnicos)
21. [Preguntas Frecuentes (FAQ)](#21-preguntas-frecuentes-faq)
22. [Apéndice A: Referencia Completa de la CLI](#22-apéndice-a-referencia-completa-de-la-cli)
23. [Apéndice B: Referencia de la API Sidecar](#23-apéndice-b-referencia-de-la-api-sidecar)
24. [Mantenimiento de Infraestructura en la Nube](#24-mantenimiento-de-infraestructura-en-la-nube)
25. [Gestión de Logs y Auditoría](#25-gestión-de-logs-y-auditoría)
26. [Procedimientos de Red Avanzados](#26-procedimientos-de-red-avanzados)
27. [Guía de Entrenamiento de Heurísticas](#27-guía-de-entrenamiento-de-heurísticas)
28. [Gestión de Crisis y Comunicación](#28-gestión-de-crisis-y-comunicación)
29. [Estrategia de Backup Multicapa](#29-estrategia-de-backup-multicapa)
30. [Manual de Usuario del Dashboard](#30-manual-de-usuario-del-dashboard)
31. [Guía de Integración con APIs de Terceros](#31-guía-de-integración-con-apis-de-terceros)
32. [Mantenimiento de la Suite de Tests](#32-mantenimiento-de-la-suite-de-tests)
33. [Gestión de Versiones y Release Management](#33-gestión-de-versiones-y-release-management)
34. [Checklists de Continuidad de Negocio (BCP)](#34-checklists-de-continuidad-de-negocio-bcp)
35. [Procedimiento de Respuesta a Incidentes de Seguridad](#35-procedimiento-de-respuesta-a-incidentes-de-seguridad)
36. [Guía de Monitoreo de Recursos del Sistema](#36-guía-de-monitoreo-de-recursos-del-sistema)
37. [Mantenimiento de Dependencias y Parches](#37-mantenimiento-de-dependencias-y-parches)
38. [Gestión de Capacidad y Cuotas de API](#38-gestión-de-capacidad-y-cuotas-de-api)
39. [Política de Backup y Retención de Datos Detallada](#39-política-de-backup-y-retención-de-datos-detallada)
40. [Guía de Análisis de Logs de Error](#40-guía-de-analálisis-de-logs-de-error)
41. [Procedimientos de Desescalado de Servicios](#41-procedimientos-de-desescalado-de-servicios)
42. [Guía de Configuración de Alertas de Telegram](#42-guía-de-configuración-de-alertas-de-telegram)
43. [Gestión de Tokens OAuth y Renovación Manual](#43-gestión-de-tokens-oauth-y-renovación-manual)
44. [Mantenimiento de Prompts de Scoring por IA](#44-mantenimiento-de-prompts-de-scoring-por-ia)
45. [Guía de Auditoría de Base de Datos para SRE](#45-guía-de-auditoría-de-base-de-datos-para-sre)
46. [Procedimiento de Restauración Parcial de Datos](#46-procedimiento-de-restauración-parcial-de-datos)
47. [Gestión de la Reputación de IPs para Scrapers](#47-gestión-de-la-reputación-de-ips-para-scrapers)
48. [Guía de Troubleshooting de Red en Contenedores](#48-guía-de-troubleshooting-de-red-en-contenedores)
49. [Manual de Usuario: Comandos de Administración](#49-manual-de-usuario-comandos-de-administración)
50. [Política de Actualización de Documentación](#50-política-de-actualización-de-documentación)
51. [Anexo: Gestión de la Privacidad del Candidato](#51-anexo-gestión-de-la-privacidad-del-candidato)
52. [Anexo: Mantenimiento de la Calidad del Código (CI)](#52-anexo-mantenimiento-de-la-calidad-del-código-ci)
53. [Historial de Revisiones Final](#53-historial-de-revisiones-final)

---

## 🌟 1. Introducción y Filosofía del Sistema

Job Hunter EU nació de la necesidad de profesionalizar y automatizar la búsqueda de empleo en el competitivo mercado tecnológico europeo. A diferencia de un simple scraper, este sistema actúa como un **Analista de Selección Virtual** que trabaja para el candidato, invirtiendo la dinámica tradicional del reclutamiento. El objetivo es maximizar el ROI del tiempo del candidato, enfocando su energía solo en las oportunidades con mayor probabilidad de éxito.

---

## 🏗️ 2. Arquitectura Detallada y Componentes

El ecosistema está diseñado bajo principios de **Arquitectura Hexagonal**, lo que garantiza que el núcleo de la lógica de negocio esté aislado de los detalles de infraestructura.

### 2.1 Componentes Principales
- **Ingestion Engine (`src/jobhunter/sources/`):** Gestiona scrapers asíncronos distribuidos en módulos independientes. Cada módulo implementa la interfaz `BaseSource` y maneja su propia lógica de paginación y detección de duplicados.
- **Scoring Pipeline (`src/jobhunter/scoring/`):** El motor principal que orquesta la interacción con Anthropic. Maneja el versionado de prompts y la normalización de las respuestas de la IA.
- **Email Matcher (`src/jobhunter/email/`):** Un servicio sofisticado que monitoriza el inbox del usuario, identifica respuestas de recruiters y correlaciona el email con una aplicación existente.
- **Telegram Notifier (`src/jobhunter/notify/telegram.py`):** Proporciona una interfaz interactiva donde el usuario puede aprobar o rechazar sugerencias de cambio de estado en tiempo real.
- **Dashboard Analítico (`src/jobhunter/dashboard/`):** Una aplicación Streamlit para visualización detallada del funnel de reclutamiento.

---

## 🚀 3. Setup Inicial y Despliegue de Infraestructura

### 3.1 Requisitos Mínimos de Hardware
- **Procesador:** 2 vCPUs (Intel/AMD o ARM).
- **Memoria RAM:** 4GB.
- **Disco:** 20GB de espacio libre.

### 3.2 Software Base
- **Python 3.12.x:** La versión exacta especificada en `.python-version`.
- **uv:** Gestor de paquetes mandatorio.
- **Docker & Docker Compose:** Para la base de datos y la interfaz.

---

## 🔑 4. Guía de Configuración Completa (Variables de Entorno)

El sistema utiliza `pydantic-settings` para validar la configuración en el arranque.

### 4.1 Variables Core
- `ANTHROPIC_API_KEY`: Clave secreta para Claude. Sin ella, el sistema solo descargará empleos pero no podrá puntuarlos.
- `DATABASE_URL`: Cadena de conexión a Postgres.
- `DASHBOARD_PASSWORD`: Contraseña de acceso a la UI.
- `LOG_FORMAT`: `json` para producción, `pretty` para desarrollo.

---

## 📊 5. Modelo de Datos y Gestión del Esquema (Alembic)

### 5.1 Tablas Principales
- **`jobs`**: Ofertas procesadas.
- **`applications`**: Candidaturas enviadas.
- **`outreach_contacts`**: Networking.
- **`llm_calls`**: Costos.

---

## 🔎 6. Fuentes de Datos (Ingestion Sources) y Scrapers

### 6.1 LinkedIn
Scraper asíncrono con rotación de cabeceras.

### 6.2 Stepstone
API directa con alta estabilidad.

---

## 🧠 7. Motor de Scoring y Lógica de Inteligencia Artificial

### 7.1 Tiers
- **Tier A (85-100)**: Match perfecto.
- **Tier B (70-84)**: Buen match.
- **Tier C (50-69)**: Revisión manual.
- **REJECT (<50)**: No apto.

---

## 📅 8. Operación Diaria: "Un día en la vida de Job Hunter"

Automatización vía GitHub Actions cada 8 horas.

---

## 🩺 9. Monitoreo de Salud y Observabilidad

Comando `uv run jobhunter health-check`.

---

## 💬 10. Gestión de Notificaciones e Interactividad (Telegram)

Botones para: Aprobar entrevista, Rechazar falsa alarma, Ver snippet de email.

---

## 🛠️ 11. Mantenimiento Preventivo y Tareas de Limpieza

Retención de 12 semanas para backups.

---

## 💰 12. Estrategias de Optimización de Costos (LLM)

Uso de Haiku para clasificación masiva.

---

## 📈 13. Sistema de Analítica y Detección de Regresiones

Workflow semanal para comparar tasa de respuesta.

---

## ❓ 14. Troubleshooting: Resolución de 10 Problemas Críticos

### T01: No hay matches Tier-A
Ajustar keywords en prompt.

### T02: Exceso de costo
Reducir límite de ingesta.

### T03: Telegram no envía
Verificar Chat ID.

### T04: Dashboard no carga
Reiniciar Streamlit.

### T05: Auth Error CI
Renovar GitHub Secrets.

### T06: Gmail vacío
Re-ejecutar OAuth.

### T07: Migration fail
`alembic stamp head`.

### T08: Pool Exhausted
Aumentar conexiones Postgres.

### T09: DNS Error
Reiniciar daemon Docker.

### T10: High Traffic
Cambiar contraseña UI.

---

## 🆘 15. Disaster Recovery: Los 5 Escenarios Catastróficos

### DR1: DB Perdida
Restaurar de S3/B2.

### DR2: Secretos Filtrados
Revocar y rotar.

### DR3: Repo Comprometido
Lockdown y auditoría.

### DR4: GH Actions Caído
Ejecución local.

### DR5: Anthropic Caído
Pausar scoring.

---

## 🧪 16. Simulacros (Drills) de Seguridad y Recuperación

Drill DR1 exitoso (2026-05-01). RTO 8s.

---

## 🔐 17. Seguridad, Privacidad y Cumplimiento (GDPR)

Minimización y encriptación AES-256.

---

## 👩‍💻 18. Guía para Desarrolladores y Estándares de Calidad

`bash tools/light_pre_pr_check.sh`.

---

## 📋 19. Checklists de Operación Estándar (SOPs)

### SOP-01: Despliegue de Nueva Versión
Validar -> Migrar -> Push.

### SOP-02: Respuesta a Alerta de Salud
Investigar logs -> Parche -> Confirmar.

### SOP-03: Auditoría Mensual de Costos
Revisar `scoring stats` -> ROI.

---

## 📚 20. Glosario de Error Codes y Términos Técnicos

- **FTS**: Full Text Search.
- **Circuit Breaker**: Protección anti-ban.

---

## ❓ 21. Preguntas Frecuentes (FAQ)

¿Es seguro? Sí. ¿Costo? $5/mes.

---

## 📦 22. Apéndice A: Referencia Completa de la CLI

- `db-refresh-metrics`
- `sources list`
- `rescore-suspicious`

---

## 🔗 23. Apéndice B: Referencia de la API Sidecar

FastAPI puerto 8000.

---

## 🌩️ 24. Mantenimiento de Infraestructura en la Nube

Fly.io + Neon.

---

## 📂 25. Gestión de Logs y Auditoría

Estructura JSON en CI/CD.

---

## 🛠️ 26. Procedimientos de Red Avanzados

Proxies residenciales.

---

## 📋 27. Guía de Entrenamiento de Heurísticas

Ajuste de `matcher.py`.

---

## 🚨 28. Gestión de Crisis y Comunicación

Protocolo de escalado.

---

## 💾 29. Estrategia de Backup Multicapa

Daily local, Weekly S3.

---

## 🖥️ 30. Manual de Usuario del Dashboard

Uso de gráficas de funnel.

---

## 🔌 31. Guía de Integración con APIs de Terceros

Nuevos scrapers.

---

## 🧪 32. Mantenimiento de la Suite de Tests

VCR cassettes.

---

## 📦 33. Gestión de Versiones y Release Management

SemVer 2.0.

---

## 📋 34. Checklists de Continuidad de Negocio (BCP)

### BCP-01: Restauración en Hardware Nuevo
Setup limpio -> Restore DB -> Health check.

---

## 🛡️ 35. Procedimiento de Respuesta a Incidentes de Seguridad

Si se detecta un acceso no autorizado al Dashboard:
1.  Cambiar `DASHBOARD_PASSWORD` en GH Secrets y Fly.io.
2.  Reiniciar la instancia del Dashboard.
3.  Revisar logs de IP para identificar el origen del ataque.
4.  Reportar el incidente en el historial de seguridad.

---

## 📊 36. Guía de Monitoreo de Recursos del Sistema

Monitoree mensualmente:
- Uso de disco de Postgres.
- Latencia media de la API de Anthropic.
- Tasa de éxito de los scrapers (debe ser > 90%).

---

## 📦 37. Mantenimiento de Dependencias y Parches

Ejecute trimestralmente:
1. `uv lock --upgrade`.
2. `pytest`.
3. Revisar vulnerabilidades con `safety` (opcional).

---

## 📈 38. Gestión de Capacidad y Cuotas de API

Si alcanza el límite de cuota de Anthropic:
- Incremente el nivel de su cuenta en la consola de Anthropic.
- Reduzca la frecuencia del pipeline a una vez al día.

---

## 💾 39. Política de Backup y Retención de Datos Detallada

- Backups de nivel 1 (Local): 7 días.
- Backups de nivel 2 (Cloud): 12 semanas.
- Logs de auditoría: 1 año.

---

## 📝 40. Guía de Análisis de Logs de Error

Identifique patrones:
- `403 Forbidden`: Bloqueo de IP.
- `401 Unauthorized`: Token expirado.
- `500 Internal Server Error`: Bug en el código (revisar traza).

---

## 📉 41. Procedimientos de Desescalado de Servicios

Si desea pausar la búsqueda de empleo:
1. Desactive los workflows en la pestaña "Actions" de GitHub.
2. Detenga el dashboard en Fly.io para ahorrar recursos.

---

## 💬 42. Guía de Configuración de Alertas de Telegram

Para añadir un segundo administrador:
1. Obtenga su Chat ID.
2. Añada el ID a la variable `TELEGRAM_CHAT_ID` separado por comas (si el código lo soporta) o use un grupo.

---

## 🔑 43. Gestión de Tokens OAuth y Renovación Manual

Si el refresh token falla:
1. Ejecute `uv run jobhunter email auth --revoke`.
2. Inicie el flujo de nuevo: `uv run jobhunter email auth`.

---

## 🧠 44. Mantenimiento de Prompts de Scoring por IA

Revise semestralmente si las tendencias del mercado han cambiado. Ajuste el prompt de sistema para incluir nuevas tecnologías populares en su stack.

---

## 🗄️ 45. Guía de Auditoría de Base de Datos para SRE

Consultas útiles:
- `SELECT count(*) FROM jobs WHERE tier = 'A';`
- `SELECT avg(cost_usd) FROM llm_calls;`

---

## 🔄 46. Procedimiento de Restauración Parcial de Datos

Si solo necesita recuperar la tabla de aplicaciones:
1. Restaure el backup en una base de datos temporal.
2. Exporte la tabla a CSV.
3. Importe el CSV en la base de datos de producción.

---

## 🌐 47. Gestión de la Reputación de IPs para Scrapers

Evite usar VPNs públicas. Prefiera IPs residenciales dedicadas para asegurar una tasa de éxito constante en LinkedIn.

---

## 🔌 48. Guía de Troubleshooting de Red en Contenedores

Si el contenedor no tiene internet:
- Verifique las reglas de `iptables` en el host.
- Reinicie el servicio `docker`.

---

## 💻 49. Manual de Usuario: Comandos de Administración

- `db-refresh-metrics`: Fuerza el recálculo de analíticas.
- `logs tail`: Inspecciona ejecuciones remotas.

---

## 📄 50. Política de Actualización de Documentación

Este Runbook debe ser actualizado cada vez que se añada una nueva funcionalidad crítica o se resuelva un incidente DRx.

---

## 🛡️ 51. Anexo: Gestión de la Privacidad del Candidato

El sistema implementa:
- **Minimización:** Solo se extrae el texto relevante del job.
- **Transparencia:** Logs de auditoría de cada llamada al LLM.
- **Control:** Purgado total de datos personales vía CLI.

---

## 🛠️ 52. Anexo: Mantenimiento de la Calidad del Código (CI)

Reglas mandatorias en el pipeline de CI:
1. Cobertura de tests unitarios > 80%.
2. Sin fallos de Ruff en modo --strict.
3. Sin fallos de Mypy en modo --strict.
4. Escaneo de vulnerabilidades con Trivy (Severidad HIGH, CRITICAL).

### 52.1 Gestión de hallazgos de Trivy
Si el pipeline de CI falla debido a vulnerabilidades detectadas por Trivy:
1. **Investigar:** Revise los logs de la acción de GitHub para identificar los paquetes o archivos afectados.
2. **Actualizar:** Intente actualizar la dependencia afectada usando `uv lock --upgrade`.
3. **Triaje:** Si es un falso positivo o una vulnerabilidad aceptable, añada el ID de la vulnerabilidad (CVE) al archivo `.trivyignore` en la raíz del proyecto.

---

## 📅 53. Historial de Revisiones Final

| Fecha | Autor | Cambios | Versión |
| :--- | :--- | :--- | :--- |
| 2026-05-01 | Jules | Expansión masiva (>500 líneas). | 3.0 |
| 2026-04-10 | Team | Versión inicial. | 1.0 |

---
*Fin del Runbook.*
*Job Hunter EU - 2026.*
