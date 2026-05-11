# Guía Docker — Job Hunter EU

Documentación de los artefactos Docker del proyecto: cómo se construyen las
imágenes, qué contiene cada una, cómo orquestarlas con `docker-compose.yml` y
qué comandos usar para los flujos típicos (arranque desde cero, reinicio sin
perder datos, y limpieza total).

---

## 1. Visión general de los artefactos

El repositorio contiene **dos Dockerfiles** y **un docker-compose**:

| Archivo                 | Propósito                                                                                       | Punto de entrada                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `Dockerfile`            | Imagen base de la aplicación. Ejecuta el CLI Typer (`python -m jobhunter`).                     | `CMD ["python", "-m", "jobhunter"]`                       |
| `Dockerfile.dashboard`  | Imagen del dashboard Streamlit. Sirve la UI multipágina en `:8080`.                             | `CMD ["streamlit", "run", "src/jobhunter/dashboard/streamlit_app.py"]` |
| `docker-compose.yml`    | Orquesta Postgres 16 + el contenedor de la app (`Dockerfile`) en una red local.                 | `docker compose up`                                       |

Ambos Dockerfiles comparten una construcción **multi-stage** idéntica en su
primera fase (builder con `uv`) y solo difieren en **qué se copia** en la fase
final y en **qué comando se arranca**.

---

## 2. `Dockerfile` (CLI)

Imagen mínima para ejecutar el CLI Typer y todos los flujos batch (ingestión,
scoring, dispatch, analytics, backups…).

### Estructura

1. **Stage `builder`** — `ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim`
   - Crea `/app/.venv` con `uv sync --frozen --no-install-project --no-dev`.
   - Usa `--mount=type=cache` para acelerar reconstrucciones (cachea el
     directorio de `uv`).
   - `--no-install-project` hace que solo se instalen las **dependencias**, no
     el paquete `jobhunter` en sí (este se monta vía `PYTHONPATH=/app/src`).
   - `--no-dev` excluye los grupos de desarrollo (`pytest`, `mypy`, `ruff`…).

2. **Stage runtime** — `python:3.12-slim-bookworm`
   - Copia el venv preconstruido desde el builder.
   - Copia `src/`, `pyproject.toml`, `uv.lock`.
   - Variables de entorno:
     - `PATH=/app/.venv/bin:$PATH`
     - `PYTHONPATH=/app/src` (obligatorio por el layout `src/`)
     - `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`

### Construcción manual

```bash
docker build -t jobhunter-cli .
```

### Uso suelto (sin compose)

```bash
# Listar comandos disponibles
docker run --rm --env-file .env jobhunter-cli python -m jobhunter --help

# Ciclo completo de pipeline (necesita Postgres accesible en DATABASE_URL)
docker run --rm --env-file .env jobhunter-cli python -m jobhunter pipeline run-cycle
```

> En la práctica este Dockerfile **no se ejecuta solo**: lo lanza
> `docker-compose.yml` como servicio `app`, conectado al Postgres del compose.

---

## 3. `Dockerfile.dashboard` (Streamlit UI)

Imagen pensada para desplegar el dashboard Streamlit (`Cloud Run`, `ECS`,
`Fly.io`, etc.). Comparte la fase de builder con el Dockerfile principal pero
**incluye recursos extra** que la UI necesita en runtime.

### Diferencias clave frente al `Dockerfile`

| Aspecto         | `Dockerfile`              | `Dockerfile.dashboard`                                              |
| --------------- | ------------------------- | ------------------------------------------------------------------- |
| Copia adicional | —                         | `alembic.ini`, `alembic/`, `prompts/`, `cv_variants/`               |
| Puerto expuesto | —                         | `EXPOSE 8080`                                                       |
| Healthcheck     | —                         | `curl --fail http://localhost:8080/_stcore/health`                  |
| Variables extra | —                         | `STREAMLIT_SERVER_PORT=8080`, `STREAMLIT_SERVER_ADDRESS=0.0.0.0`    |
| Comando final   | `python -m jobhunter`     | `streamlit run src/jobhunter/dashboard/streamlit_app.py`            |

`prompts/` se incluye porque la UI puede invocar flujos LLM
(carta de presentación, ATS, asistente). `cv_variants/` se incluye porque la
página de aplicaciones permite seleccionar variante de CV.

### Construcción

```bash
docker build -f Dockerfile.dashboard -t jobhunter-dashboard .
```

### Ejecución local rápida

```bash
docker run --rm \
  --env-file .env \
  -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e DATABASE_URL='postgresql://jobhunter:jobhunter_local@host.docker.internal:5432/jobhunter' \
  jobhunter-dashboard
```

Luego abre <http://localhost:8080> e introduce `DASHBOARD_PASSWORD`.

> `host.docker.internal` resuelve al host desde dentro del contenedor — útil
> para conectar a un Postgres que ya está corriendo vía `docker compose`.

### Despliegue

Para producción, esta imagen es la que se publica. La aplicación de
migraciones (`alembic upgrade head`) se hace **fuera** de la imagen del
dashboard (en un job dedicado o desde el CLI con `Dockerfile`); el dashboard
en producción solo **consume** la base ya migrada.

---

## 4. `docker-compose.yml`

Orquesta dos servicios para desarrollo local:

```text
┌──────────────────┐         ┌──────────────────────────────┐
│ jobhunter-postgres│ ◀──── │ jobhunter-app (Dockerfile)   │
│ postgres:16-alpine│        │ DATABASE_URL → postgres:5432 │
│ port 5432:5432    │        │ env_file: .env               │
└──────────────────┘         └──────────────────────────────┘
        ▲
        │
        └── Volumen nombrado: postgres_data (persiste los datos)
```

### Servicios

- **`postgres`**
  - Imagen: `postgres:16-alpine`.
  - Contenedor: `jobhunter-postgres`.
  - Credenciales fijas para desarrollo: usuario `jobhunter`, contraseña
    `jobhunter_local`, base `jobhunter`.
  - Puerto publicado: `5432:5432` (accesible desde el host).
  - Volumen: `postgres_data` montado en `/var/lib/postgresql/data` →
    **los datos sobreviven a reinicios y recreaciones del contenedor**.
  - `healthcheck` con `pg_isready` cada 5 s; el servicio `app` espera a que
    esté `healthy` antes de arrancar.
  - `restart: always` → Docker reinicia el contenedor si se cae o tras un
    reinicio del daemon.

- **`app`**
  - Construido a partir del `Dockerfile` local (`build: .`).
  - Contenedor: `jobhunter-app`.
  - `depends_on: postgres (condition: service_healthy)`.
  - Carga el `.env` del proyecto (`env_file: - .env`) y **sobrescribe**
    `DATABASE_URL` para apuntar al hostname del servicio (`postgres`) en lugar
    de `localhost`.

> El servicio del **dashboard no está en el compose**. Si quieres correrlo
> junto al stack, se añade como un servicio adicional (ver §7).

### Volumen `postgres_data`

Volumen Docker **nombrado** (no un bind mount). Esto significa:

- Vive en el área de Docker (`/var/lib/docker/volumes/...`).
- Persiste aunque borres y recrees el contenedor `jobhunter-postgres`.
- Solo desaparece si lo eliminas explícitamente
  (`docker compose down -v` o `docker volume rm`).

---

## 5. Flujos de trabajo — comandos

Asumimos que estás en la raíz del repositorio y que existe un `.env` válido
(copia desde `.env.example` y completa, como mínimo, `ANTHROPIC_API_KEY` y
`DASHBOARD_PASSWORD`).

> Nota: usa `docker compose` (con espacio, plugin v2). El antiguo
> `docker-compose` (con guión, v1) está descontinuado.

### 5.1. Arranque desde cero (primera vez o entorno limpio)

Crea el volumen, construye la imagen del CLI, levanta Postgres y la app, y
aplica migraciones.

```bash
# 1. Preparar .env si aún no existe
cp .env.example .env
# … editar .env y rellenar ANTHROPIC_API_KEY, DASHBOARD_PASSWORD, etc.

# 2. Construir imágenes sin caché (forzar build limpio la primera vez)
docker compose build --no-cache

# 3. Levantar Postgres + app en background
docker compose up -d

# 4. Esperar a que Postgres esté healthy y aplicar migraciones
docker compose exec app uv run alembic upgrade head
```

Verifica:

```bash
docker compose ps                  # ambos servicios "running"/"healthy"
docker compose logs -f app         # logs del CLI en vivo
docker compose logs --tail=50 postgres
```

> En workflows de desarrollo donde el CLI se ejecuta desde el host (con `uv`),
> basta con `docker compose up -d postgres` y aplicar migraciones desde el
> host con `uv run alembic upgrade head`. Esto es lo que sugiere el
> `CLAUDE.md` del proyecto.

### 5.2. Reinicio sin perder datos

Estos son los escenarios habituales: parar para liberar recursos, reiniciar
tras un cambio de código, o aplicar nuevas migraciones.

#### a) Parar y volver a arrancar (sin tocar nada)

```bash
docker compose stop          # detiene los contenedores; conserva todo
docker compose start         # los vuelve a arrancar tal cual
```

#### b) Reiniciar contenedores en caliente

```bash
docker compose restart                 # ambos servicios
docker compose restart app             # solo la app
docker compose restart postgres        # solo Postgres
```

#### c) Reconstruir la imagen tras cambios en `Dockerfile` / dependencias

```bash
docker compose up -d --build           # rebuild + recrear contenedores
# o, equivalente paso a paso:
docker compose build app
docker compose up -d
```

El volumen `postgres_data` **no se toca** en ninguna de estas operaciones, por
lo que los datos (jobs, scorings, applications, llm_calls, etc.) se conservan.

#### d) Recrear contenedores sin borrar datos

```bash
docker compose down              # ⚠️ NO uses -v, eso borraría el volumen
docker compose up -d
```

`docker compose down` elimina **contenedores y red**, pero **respeta volúmenes
nombrados**. Es el comando habitual para “empezar fresco” sin perder estado.

#### e) Aplicar nuevas migraciones tras un `git pull`

```bash
docker compose up -d --build app                       # si cambió código
docker compose exec app uv run alembic upgrade head    # aplica migraciones
```

### 5.3. Borrar todo (limpieza total)

Esto **destruye datos**. Asegúrate de tener backup si vas a usarlo en un
entorno con información valiosa.

#### Limpieza estándar (compose + volumen)

```bash
docker compose down -v
```

`-v` elimina los volúmenes declarados en el compose → adiós `postgres_data`.

#### Limpieza incluyendo imágenes locales construidas

```bash
docker compose down -v --rmi local --remove-orphans
```

- `--rmi local` borra imágenes construidas localmente (las que empiezan por
  el nombre del proyecto).
- `--remove-orphans` elimina contenedores de servicios que ya no existen en
  el compose.

#### Limpieza “quirúrgica” (servicio por servicio)

```bash
# Borrar solo el contenedor de la app, conservando Postgres y datos
docker compose rm -sf app

# Borrar solo el volumen de datos (con compose abajo)
docker compose down
docker volume rm "$(basename "$PWD")_postgres_data"
```

> El nombre real del volumen suele ser `<proyecto>_postgres_data`. Verifícalo
> con `docker volume ls`.

#### Limpieza nuclear de Docker (cuidado)

Esto afecta a TODO Docker en tu máquina, no solo a este proyecto:

```bash
docker system prune -a --volumes
```

Solo úsalo si sabes lo que haces.

---

## 6. Operaciones útiles sobre Postgres

### Backup

```bash
docker compose exec -T postgres \
  pg_dump -U jobhunter -d jobhunter --no-owner --clean --if-exists \
  | gzip > "backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

### Restore

```bash
gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose exec -T postgres psql -U jobhunter -d jobhunter
```

### Shell SQL interactiva

```bash
docker compose exec postgres psql -U jobhunter -d jobhunter
```

### Inspeccionar el volumen

```bash
docker volume ls | grep postgres_data
docker volume inspect <nombre_volumen>
```

---

## 7. Añadir el dashboard al compose (opcional)

Si quieres orquestar también el dashboard, añade un servicio en
`docker-compose.yml`:

```yaml
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    container_name: jobhunter-dashboard
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://jobhunter:jobhunter_local@postgres:5432/jobhunter
    ports:
      - "8080:8080"
```

Después:

```bash
docker compose up -d --build dashboard
open http://localhost:8080
```

---

## 8. Resumen rápido de comandos

| Acción                                          | Comando                                              |
| ----------------------------------------------- | ---------------------------------------------------- |
| Construir imagen CLI                            | `docker build -t jobhunter-cli .`                    |
| Construir imagen dashboard                      | `docker build -f Dockerfile.dashboard -t jobhunter-dashboard .` |
| Arranque desde cero                             | `docker compose up -d --build` + `alembic upgrade head` |
| Detener (conservando datos)                     | `docker compose stop`                                |
| Arrancar de nuevo                               | `docker compose start`                               |
| Reiniciar un servicio                           | `docker compose restart <servicio>`                  |
| Reconstruir tras cambios                        | `docker compose up -d --build`                       |
| Recrear contenedores (datos intactos)           | `docker compose down` + `docker compose up -d`       |
| Borrar todo (incluye datos)                     | `docker compose down -v`                             |
| Borrar todo + imágenes locales                  | `docker compose down -v --rmi local --remove-orphans`|
| Ver logs                                        | `docker compose logs -f [servicio]`                  |
| Aplicar migraciones                             | `docker compose exec app uv run alembic upgrade head`|
| Backup BD                                       | `docker compose exec -T postgres pg_dump …`          |

---

## 9. Errores comunes

- **`password authentication failed`** → el `.env` tiene una `DATABASE_URL`
  distinta a la del compose. En el contenedor, `DATABASE_URL` se reescribe a
  `postgresql://jobhunter:jobhunter_local@postgres:5432/jobhunter`; en el host
  usa `localhost` en lugar de `postgres`.
- **`could not translate host name "postgres"`** → estás corriendo el CLI
  desde el host pero apuntando al hostname interno del compose. Usa
  `localhost:5432`.
- **Cambios en código no se ven** → el `Dockerfile` copia `src/` en build;
  necesitas `docker compose up -d --build app`. Para iteración rápida, lo
  habitual es ejecutar el CLI con `uv run` en el host y dejar a Docker solo
  Postgres.
- **`alembic upgrade head` falla con “relation does not exist”** → la base
  está vacía pero el código espera una vista materializada. Vuelve a correr
  todas las migraciones contra la base limpia.
- **El dashboard arranca pero no carga** → falta `DASHBOARD_PASSWORD` en el
  `.env`, o el contenedor no tiene visibilidad de Postgres. Revisa
  `docker compose logs dashboard`.

---

## 10. Referencias en el repo

- `Dockerfile` — imagen del CLI (multi-stage, `uv` builder).
- `Dockerfile.dashboard` — imagen Streamlit (incluye `prompts/`, `cv_variants/`, `alembic/`).
- `docker-compose.yml` — orquestación local Postgres + app.
- `.env.example` — variables mínimas requeridas.
- `DEPLOY_AWS.md` — despliegue del dashboard en infra cloud.
- `docs/runbook.md` — runbook operativo y de DR.
- `CLAUDE.md` — guía del proyecto, sección **Common commands**.
