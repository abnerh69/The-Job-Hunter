# Job Hunter EU

Sistema automatizado de búsqueda de empleo en Europa

## Desarrollo con Docker

El proyecto está containerizado para facilitar el desarrollo local.

### Requisitos

- Docker
- Docker Compose

### Levantar el entorno

1. Configura las variables de entorno:
```bash
cp .env.example .env
```
*(Asegúrate de editar `.env` y poner tu `ANTHROPIC_API_KEY`)*

2. Inicia la base de datos y la aplicación:
```bash
docker compose up -d
```

Esto levantará:
- **Postgres**: Accesible en `localhost:5432` con usuario `jobhunter` y contraseña `jobhunter_local`.
- **App**: Ejecutará la aplicación automáticamente.

### Ver logs

```bash
docker compose logs -f app
```

### Parar el entorno

```bash
docker compose down
```

### Reset completo

Para borrar los contenedores y **todos los datos de la base de datos** (volúmenes):

```bash
docker compose down -v
```
