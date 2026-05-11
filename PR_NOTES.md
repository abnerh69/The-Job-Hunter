# PR: Local deploy con dashboard en navegador

## Cambios

| Archivo | Acción |
|---|---|
| `Dockerfile` | **Modificar** (reemplazar con el del zip) |
| `docker-compose.yml` | **Modificar** (reemplazar con el del zip) |
| `Dockerfile.dashboard` | **Eliminar** (`git rm Dockerfile.dashboard`) |

## Qué se arregla

1. **CMD del Dockerfile rompía el contenedor.** Era `python -m jobhunter --help` → imprime help y sale. Ahora corre el API sidecar FastAPI (`api run` en puerto 8000), proceso long-running con `/health` y `/readiness`.
2. **Faltaban assets en el runtime image.** El `Dockerfile` original no copiaba `alembic/`, `prompts/`, ni `cv_variants/`, así que casi cualquier comando CLI fallaba dentro del contenedor.
3. **Duplicación `Dockerfile` vs `Dockerfile.dashboard`.** Eran 90% idénticos. Unificados en un solo `Dockerfile`; los servicios cambian `command:` en compose.
4. **No había migraciones automáticas.** Añadido servicio `migrate` (one-shot, `alembic upgrade head`) que bloquea el arranque de `app` y `dashboard` vía `service_completed_successfully`.
5. **No había UI accesible.** Añadido servicio `dashboard` (Streamlit en `http://localhost:8080`).
6. **Healthchecks sin dependencia externa.** El `Dockerfile.dashboard` usaba `curl` (no presente en la imagen slim → healthcheck quebrado). Ahora ambos healthchecks usan `python -c urllib.request`.

## Topología resultante

```
postgres (5432)
   └── migrate (one-shot: alembic upgrade head)
          ├── app       (FastAPI sidecar :8000)
          └── dashboard (Streamlit :8080)
```

## Uso

```bash
cp .env.example .env   # rellenar ANTHROPIC_API_KEY
docker compose up -d --build
```

- Dashboard: http://localhost:8080
- API health: http://localhost:8000/health
- CLI puntual: `docker compose exec app python -m jobhunter <comando>`
- Seed demo: `docker compose exec app python -m jobhunter db-seed`

## Commit sugerido

```
feat(deploy): local deploy with Streamlit dashboard + API sidecar

- Unify Dockerfile (remove Dockerfile.dashboard duplication)
- Copy alembic/, prompts/, cv_variants/ into runtime image
- Replace 'python -m jobhunter --help' CMD with API sidecar (long-running)
- Add migrate service (alembic upgrade head) gating app & dashboard
- Add dashboard service (Streamlit on :8080)
- Add Python-based healthchecks (no curl dependency)
```

## Pendiente / posible follow-up

Si el dashboard exige password al abrir el navegador, mirar `src/jobhunter/dashboard/auth.py` para identificar la variable de entorno (probablemente `DASHBOARD_PASSWORD`) y añadirla a `.env` y a `HUMAN_SETUP.md` en un commit aparte del mismo PR.
