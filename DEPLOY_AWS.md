# Deploy a AWS — Instancia EC2 autocontenida

Guía para desplegar Job Hunter EU en **una sola instancia EC2** con PostgreSQL,
dashboard, sidecar API y todos los crons en el mismo host. Es un setup
intencionalmente simple para uso personal de un solo usuario; para
multi-tenant o alta disponibilidad ver §10 (Limitaciones y cuándo migrar).

> **Pre-requisito:** una cuenta AWS y la AWS CLI configurada localmente
> (`aws configure`).

---

## 1. Resumen de la arquitectura objetivo

```
┌────────────────────────────────────────────────────────────────┐
│ EC2 t4g.medium (ARM, Ubuntu 24.04 LTS)                         │
│                                                                │
│  ┌──────────┐     ┌─────────────┐     ┌────────────────────┐   │
│  │ nginx    │────▶│ Streamlit   │     │ systemd timers:    │   │
│  │ (HTTPS)  │  ┌─▶│ dashboard   │     │ - pipeline-cycle   │   │
│  │ :443     │  │  │ :8501       │     │ - weekly-digest    │   │
│  └────┬─────┘  │  └─────────────┘     │ - followup-checks  │   │
│       │        │                       │ - health-check     │   │
│       │  ┌─────┴────┐                  │ - email-poll       │   │
│       └─▶│ FastAPI  │                  │ - weekly-analysis  │   │
│          │ sidecar  │                  │ - backup-to-s3     │   │
│          │ :8000    │                  └────────────────────┘   │
│          └────┬─────┘                            │              │
│               ▼                                  ▼              │
│         ┌────────────────────────────────────────────────┐      │
│         │ PostgreSQL 16 (local, /var/lib/postgresql)     │      │
│         └────────────────────────────────────────────────┘      │
└─────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼ (cron)
                    ┌──────────────┐
                    │ S3 bucket    │
                    │ (backups)    │
                    └──────────────┘
```

**Decisión clave:** se reemplazan los workflows de GitHub Actions por
**systemd timers** locales. El plan original (`docs/Plan automatizado.../
L_Backlog_Nivel_2_E8.md`) usa GH Actions porque son gratis y sin servidor;
en este deploy ya pagamos por el servidor, así que mover los crons al host
elimina dependencia externa y latencia (no hay que esperar a que GH Actions
cole el runner).

---

## 2. Recomendaciones de infraestructura

### Instancia

| Recurso | Recomendación | Razón |
|---|---|---|
| Tipo | **`t4g.medium`** (2 vCPU ARM, 4 GB RAM) | ARM (Graviton) es ~20% más barato que x86. 4 GB cubre Postgres + Streamlit + workers concurrentes con holgura. |
| OS | **Ubuntu 24.04 LTS** (`ami-...arm64-server-...`) | LTS hasta 2029, repos modernos, comunidad amplia para troubleshooting. |
| Storage | **30 GB gp3 EBS** (root) | gp3 es más barato y rápido que gp2; 30 GB cubre OS + Postgres con margen para 1+ año de operación. |
| Elastic IP | **Asignar** | Evita que la IP pública cambie en cada reinicio (y rompa DNS / firewall rules). |
| Región | La más cercana a tu zona horaria | Para Colombia: `us-east-1` (Virginia). Para EU: `eu-central-1` (Frankfurt). |

### Costo mensual estimado (US East, on-demand 2026)

| Item | Precio | Notas |
|---|---|---|
| `t4g.medium` on-demand | ~$24.10 | $0.0336/h × 730 h |
| 30 GB gp3 EBS | ~$2.40 | $0.08/GB-mes |
| Elastic IP (en uso) | $0 | Gratis si está asociada a una instancia corriendo |
| S3 backups (1–5 GB) | <$0.20 | Standard tier |
| Data transfer out | <$1 | Tráfico personal mínimo |
| **Total** | **~$28/mes** | |

**Reservar 1 año** baja el costo del compute a ~$15/mes (≈$19/mes total).

### Networking (Security Group)

| Puerto | Origen | Servicio | Notas |
|---|---|---|---|
| 22 (SSH) | **tu IP /32** | SSH | Nunca abrir 0.0.0.0/0. Usar SSH key, no password. |
| 80 (HTTP) | 0.0.0.0/0 | nginx | Sólo para redirección a HTTPS y challenge ACME de Let's Encrypt. |
| 443 (HTTPS) | 0.0.0.0/0 | nginx → Streamlit / FastAPI | El dashboard expone aquí; auth via `DASHBOARD_PASSWORD` (E7-S01). |

**No exponer** el puerto 5432 (Postgres) ni 8501 (Streamlit directo) ni 8000
(FastAPI directo) externamente. Sólo nginx en 443.

### Alternativas más baratas

- **`t4g.small`** (2 vCPU, 2 GB RAM): viable si la operación es ligera (1 ciclo de scoring/8h, <10 jobs por ciclo). Ahorra ~$12/mes. **Riesgo:** Postgres + Streamlit pueden saturar 2 GB durante picos.
- **Lightsail**: instancia `2GB RAM, 2 vCPU` por $12/mes con bandwidth incluido. Más simple de configurar pero menos flexibilidad.
- **EC2 Spot**: ~70% más barato pero la instancia puede ser terminada con 2 min de aviso. **No recomendado** para este uso porque los crons son stateful (Postgres en disco efímero perdido en cada terminación).

---

## 3. Setup paso a paso

### 3.1 Crear la instancia

Vía AWS CLI (sustituir `<ami-id>` por la AMI Ubuntu 24.04 LTS arm64 vigente
en tu región — buscar con `aws ec2 describe-images --owners 099720109477
--filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"`):

```bash
aws ec2 run-instances \
  --image-id <ami-id> \
  --instance-type t4g.medium \
  --key-name jobhunter-key \
  --security-group-ids sg-xxxxx \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=jobhunter-eu}]'
```

Asociar Elastic IP:

```bash
aws ec2 allocate-address --domain vpc
aws ec2 associate-address --instance-id i-xxxxx --allocation-id eipalloc-xxxxx
```

### 3.2 Conectar e instalar dependencias del sistema

```bash
ssh -i ~/.ssh/jobhunter-key.pem ubuntu@<elastic-ip>
```

Una vez dentro:

```bash
# Actualizar sistema y habilitar unattended-upgrades para parches de seguridad
sudo apt update && sudo apt upgrade -y
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# Dependencias core
sudo apt install -y \
    python3.12 python3.12-venv python3.12-dev \
    postgresql-16 postgresql-contrib-16 \
    nginx certbot python3-certbot-nginx \
    git build-essential libpq-dev \
    awscli jq curl

# uv (gestor del proyecto)
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Crear usuario de servicio dedicado (no correr como ubuntu/root)
sudo useradd -r -m -s /bin/bash jobhunter
sudo -u jobhunter mkdir -p /home/jobhunter/{app,backups,logs}
```

### 3.3 Configurar PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE USER jobhunter WITH PASSWORD 'CAMBIAR_ESTA_PASSWORD';
CREATE DATABASE jobhunter OWNER jobhunter;
GRANT ALL PRIVILEGES ON DATABASE jobhunter TO jobhunter;
SQL

# Verificar que sólo escucha en localhost (default en Ubuntu, pero confirmar)
sudo grep -E "^listen_addresses" /etc/postgresql/16/main/postgresql.conf
# Debe ser: listen_addresses = 'localhost'   (NO '*' ni la IP pública)

sudo systemctl enable --now postgresql
```

### 3.4 Clonar e instalar la app

```bash
sudo -u jobhunter -H bash -c '
cd /home/jobhunter/app
git clone https://github.com/AbnerSHR/Job-Hunter-EU.git .
export PATH="$HOME/.local/bin:$PATH"
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen --no-dev
uv run playwright install chromium  # sólo si vas a correr tests E2E en el host
'
```

### 3.5 Configurar variables de entorno

```bash
sudo -u jobhunter tee /home/jobhunter/app/.env <<'ENV'
# Database
DATABASE_URL=postgresql://jobhunter:CAMBIAR_ESTA_PASSWORD@localhost:5432/jobhunter

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=xxx:yyy
TELEGRAM_CHAT_ID=123456

# SMTP / Gmail (opcional para digest)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu@gmail.com
SMTP_PASSWORD=app-password-gmail
DIGEST_TO_EMAIL=tu@gmail.com

# Dashboard
DASHBOARD_PASSWORD=password-fuerte-aqui

# Gmail OAuth (E10) — sólo si vas a usar response detection
GMAIL_CLIENT_ID=xxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxx
OAUTH_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Logging en producción
LOG_FORMAT=json

# Backups (S3)
BACKUP_STORAGE_PROVIDER=s3
BACKUP_STORAGE_BUCKET=jobhunter-backups-tu-cuenta
ENV

sudo chmod 600 /home/jobhunter/app/.env
sudo chown jobhunter:jobhunter /home/jobhunter/app/.env
```

> Para evitar tener `ANTHROPIC_API_KEY` en texto plano, considera **AWS
> Systems Manager Parameter Store** (gratis hasta 10K parámetros estándar)
> con un wrapper que descargue secrets al `.env` al iniciar. Para uso
> personal con disco cifrado, el `.env` con permisos 600 es aceptable.

### 3.6 Aplicar migraciones

```bash
sudo -u jobhunter -H bash -c '
cd /home/jobhunter/app
export PATH="$HOME/.local/bin:$PATH"
uv run alembic upgrade head
'
```

---

## 4. Servicios (systemd) — dashboard + API + crons

### 4.1 Dashboard Streamlit

`/etc/systemd/system/jobhunter-dashboard.service`:

```ini
[Unit]
Description=Job Hunter EU - Streamlit Dashboard
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=jobhunter
WorkingDirectory=/home/jobhunter/app
EnvironmentFile=/home/jobhunter/app/.env
ExecStart=/home/jobhunter/.local/bin/uv run streamlit run \
    src/jobhunter/dashboard/streamlit_app.py \
    --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4.2 FastAPI sidecar

`/etc/systemd/system/jobhunter-api.service`:

```ini
[Unit]
Description=Job Hunter EU - FastAPI Sidecar
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=jobhunter
WorkingDirectory=/home/jobhunter/app
EnvironmentFile=/home/jobhunter/app/.env
ExecStart=/home/jobhunter/.local/bin/uv run python -m jobhunter api run \
    --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Habilitar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jobhunter-dashboard jobhunter-api
sudo systemctl status jobhunter-dashboard jobhunter-api
```

### 4.3 Crons (reemplazo de GH Actions)

Crear un wrapper que carga `.env` y corre un comando del CLI. Cada cron es un
par `.service` (oneshot) + `.timer`. Ejemplo para `pipeline-cycle`:

`/etc/systemd/system/jobhunter-pipeline-cycle.service`:

```ini
[Unit]
Description=Job Hunter EU - Pipeline Cycle
After=postgresql.service

[Service]
Type=oneshot
User=jobhunter
WorkingDirectory=/home/jobhunter/app
EnvironmentFile=/home/jobhunter/app/.env
ExecStart=/home/jobhunter/.local/bin/uv run python -m jobhunter pipeline run-cycle
StandardOutput=append:/home/jobhunter/logs/pipeline-cycle.jsonl
StandardError=inherit
```

`/etc/systemd/system/jobhunter-pipeline-cycle.timer`:

```ini
[Unit]
Description=Run pipeline cycle every 8h

[Timer]
OnCalendar=*-*-* 00,08,16:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

Replicar el patrón para los otros crons (cambiar `OnCalendar` y comando):

| Timer | `OnCalendar` (UTC) | Comando |
|---|---|---|
| `jobhunter-pipeline-cycle.timer` | `*-*-* 00,08,16:00:00` | `pipeline run-cycle` |
| `jobhunter-weekly-digest.timer` | `Sun *-*-* 17:00:00` | `notify digest --send` |
| `jobhunter-followup-checks.timer` | `*-*-* 14:00:00` | `pipeline check-followups` |
| `jobhunter-health-check.timer` | `*-*-* 00,04,08,12,16,20:00:00` | `health-check` |
| `jobhunter-email-poll.timer` | `*:0/30` (cada 30 min) | `email poll-and-suggest` |
| `jobhunter-weekly-analysis.timer` | `Mon *-*-* 13:00:00` | `analytics check-regressions && analytics recommendations` |
| `jobhunter-backup.timer` | `Sun *-*-* 04:00:00` | `backup create --upload` |

Habilitar todos:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now \
    jobhunter-pipeline-cycle.timer \
    jobhunter-weekly-digest.timer \
    jobhunter-followup-checks.timer \
    jobhunter-health-check.timer \
    jobhunter-email-poll.timer \
    jobhunter-weekly-analysis.timer \
    jobhunter-backup.timer

# Verificar próximas ejecuciones
systemctl list-timers --all | grep jobhunter
```

> **Composite action `alert-on-failure` de E8-S06** se reemplaza por el
> mecanismo nativo de systemd: `OnFailure=jobhunter-alert@%n.service` con
> un service templated que dispara `curl` a Telegram. Documentado en
> §6.3.

---

## 5. Reverse proxy nginx + HTTPS

Apuntar tu dominio (ej. `jobhunter.tudominio.com`) a la Elastic IP vía
registro A en tu DNS provider, luego:

`/etc/nginx/sites-available/jobhunter`:

```nginx
server {
    listen 80;
    server_name jobhunter.tudominio.com;

    # ACME challenge (Let's Encrypt) y redirección a HTTPS
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name jobhunter.tudominio.com;

    # Configurado por certbot tras obtener el certificado
    # ssl_certificate /etc/letsencrypt/live/jobhunter.tudominio.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/jobhunter.tudominio.com/privkey.pem;

    # Headers de seguridad
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # API sidecar (/health, /readiness, /status público)
    location ~ ^/(health|readiness|status|api)/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Streamlit dashboard (resto)
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;  # Streamlit usa websockets long-lived
    }
}
```

Activar y obtener certificado:

```bash
sudo ln -s /etc/nginx/sites-available/jobhunter /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d jobhunter.tudominio.com
# certbot edita el server { 443 } y añade certificado + auto-renovación
```

Certbot crea un timer (`certbot.timer`) que renueva automáticamente.

---

## 6. Backups, monitoreo y alertas

### 6.1 Backups a S3

Crear bucket + IAM role con permisos mínimos:

```bash
aws s3 mb s3://jobhunter-backups-tu-cuenta
aws s3api put-bucket-versioning --bucket jobhunter-backups-tu-cuenta \
    --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration \
    --bucket jobhunter-backups-tu-cuenta \
    --lifecycle-configuration file://lifecycle.json
```

`lifecycle.json` (retención 12 semanas, alineado con `BACKUP_RETENTION_WEEKS`):

```json
{
  "Rules": [{
    "ID": "DeleteOldBackups",
    "Status": "Enabled",
    "Expiration": {"Days": 84},
    "Filter": {"Prefix": ""}
  }]
}
```

**IAM Role para EC2** con policy mínima (mejor que access keys hardcoded):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"],
    "Resource": [
      "arn:aws:s3:::jobhunter-backups-tu-cuenta",
      "arn:aws:s3:::jobhunter-backups-tu-cuenta/*"
    ]
  }]
}
```

Adjuntar el role a la instancia. `boto3` recoge automáticamente las
credenciales del instance metadata — no hace falta `BACKUP_ACCESS_KEY`/
`BACKUP_SECRET_KEY` en `.env`.

El timer `jobhunter-backup.timer` ejecuta `backup create --upload` los
domingos 04:00 UTC. Si quieres restore drill (validación post-backup como
pide E12-S03), añadir un script wrapper que después del upload restaure a
una DB efímera (`postgresql://jobhunter:...@localhost:5432/jobhunter_drill`)
y valide integridad.

### 6.2 Monitoreo

Para uso personal, lo nativo del sistema es suficiente:

- **`systemctl status`** — estado de servicios.
- **`journalctl -u jobhunter-pipeline-cycle.service -f`** — logs en vivo.
- **`/health` endpoint** del sidecar FastAPI (E12-S04) ya implementado —
  retorna JSON con estado de DB, Anthropic, Telegram, Gmail, costo mensual,
  circuit breakers.
- **CloudWatch Agent** (opcional, gratis hasta 10 métricas custom) si quieres
  gráficas de CPU/RAM/disk:
  ```bash
  wget https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/arm64/latest/amazon-cloudwatch-agent.deb
  sudo dpkg -i amazon-cloudwatch-agent.deb
  ```

### 6.3 Alertas Telegram en fallos de cron

Reemplaza la composite action `alert-on-failure` de E8-S06.
`/etc/systemd/system/jobhunter-alert@.service`:

```ini
[Unit]
Description=Send Telegram alert on failure of %i

[Service]
Type=oneshot
User=jobhunter
EnvironmentFile=/home/jobhunter/app/.env
ExecStart=/bin/bash -c '\
  MSG="🚨 Servicio falló: %i en $(hostname)"; \
  curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
    -d chat_id="$TELEGRAM_CHAT_ID" --data-urlencode "text=$MSG"'
```

Y en cada `.service` de cron añadir:

```ini
[Unit]
OnFailure=jobhunter-alert@%n.service
```

---

## 7. Hardening

### 7.1 SSH

```bash
# Editar /etc/ssh/sshd_config
sudo sed -i \
    -e 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' \
    -e 's/^#*PermitRootLogin.*/PermitRootLogin no/' \
    -e 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' \
    /etc/ssh/sshd_config
sudo systemctl restart ssh
```

### 7.2 Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <tu-ip>/32 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 7.3 fail2ban (protege SSH y nginx)

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

Defaults razonables: tras 5 intentos fallidos de SSH, bloqueo 10 min. La
tabla `failed_login_attempts` de E12-S05 sigue funcionando para el dashboard.

### 7.4 EBS encryption + disk encryption

Lanzar la instancia con `--encrypted` en el block-device-mapping (encriptación
en reposo del EBS, transparente para la app).

---

## 8. Operación diaria

### Logs

```bash
# Logs de un timer/servicio específico (últimas 24h)
sudo journalctl -u jobhunter-pipeline-cycle.service --since "24 hours ago"

# Live tail del dashboard
sudo journalctl -u jobhunter-dashboard.service -f

# Logs estructurados JSON del pipeline
tail -f /home/jobhunter/logs/pipeline-cycle.jsonl | jq .
```

### Restart de servicios

```bash
sudo systemctl restart jobhunter-dashboard
sudo systemctl restart jobhunter-api
```

### Update workflow (deploy de cambios)

```bash
sudo -u jobhunter -H bash -c '
cd /home/jobhunter/app
git pull origin main
export PATH="$HOME/.local/bin:$PATH"
uv sync --frozen --no-dev
uv run alembic upgrade head
'
sudo systemctl restart jobhunter-dashboard jobhunter-api
```

Considerar empaquetar lo anterior en `/home/jobhunter/app/scripts/deploy.sh`
con `set -e` y validación de health post-deploy.

### Forzar ejecución de un timer (debug)

```bash
sudo systemctl start jobhunter-pipeline-cycle.service
```

---

## 9. Disaster recovery

Procedimiento (alineado con `docs/runbook.md` §DR1):

```bash
# 1. Localizar último backup válido en S3
aws s3 ls s3://jobhunter-backups-tu-cuenta/ --recursive | tail

# 2. Descargar
aws s3 cp s3://jobhunter-backups-tu-cuenta/jobhunter_YYYYMMDD_HHMMSS.sql.gz \
    /tmp/restore.sql.gz

# 3. Restore (desde la app)
sudo -u jobhunter -H bash -c '
cd /home/jobhunter/app
export PATH="$HOME/.local/bin:$PATH"
uv run python -m jobhunter backup restore /tmp/restore.sql.gz
'

# 4. Verificar
sudo -u jobhunter -H bash -c '
cd /home/jobhunter/app
export PATH="$HOME/.local/bin:$PATH"
uv run python -m jobhunter health-check
'
```

**Si la instancia entera se pierde:** lanzar nueva EC2 con la misma AMI,
asociar la Elastic IP, repetir §3 (instalación) y §9 (restore desde S3). El
tiempo objetivo es <30 min asumiendo que tienes scripts/Terraform.

---

## 10. Limitaciones del enfoque single-instance y cuándo migrar

| Limitación | Síntoma | Cuándo migrar |
|---|---|---|
| **Single point of failure** | Si la EC2 muere, el sistema cae. | Cuando uptime importe >99% (SaaS multi-usuario). Mover Postgres a RDS Multi-AZ. |
| **Sin auto-scaling** | Picos de jobs ralentizan todo. | Cuando volumen de scoring >1000 jobs/día. Mover workers a ECS/Fargate. |
| **Backup diario, no continuo** | Pérdida potencial de hasta 24h de data. | Cuando la pérdida de un día sea inaceptable. RDS con automated backups + PITR. |
| **Sin separación read/write** | Dashboard pesado puede impactar workers. | Cuando dashboard reciba tráfico real. RDS read replica. |
| **Postgres en mismo disco que app** | Disk full → todo cae. | Cuando DB >5 GB sostenido. EBS dedicado para `/var/lib/postgresql`. |
| **Sin DDoS protection** | Botnets pueden saturar el dashboard. | Si `/status` se hace popular. CloudFront + WAF. |

**Path de migración suave** (cuando rinda):
1. Mover Postgres a RDS (cambio de `DATABASE_URL` + restore desde backup → ~30 min de downtime).
2. Mover el dashboard a App Runner / Fargate (sigue siendo barato, gana auto-scaling).
3. Mover los crons a EventBridge + Lambda o volver a GH Actions con la DB ahora hosted.
4. Mover backups a S3 lifecycle + Glacier (más barato a largo plazo).

Cada paso es independiente; no hay que hacer big-bang.

---

## 11. Checklist final

- [ ] Instancia EC2 creada con `t4g.medium` + 30 GB gp3 + Elastic IP.
- [ ] Security Group: 22 (tu IP), 80 (todos), 443 (todos).
- [ ] PostgreSQL 16 instalado, escuchando sólo en `localhost`.
- [ ] App clonada en `/home/jobhunter/app`, `uv sync` ok.
- [ ] `.env` con permisos 600, propietario `jobhunter`.
- [ ] Migraciones aplicadas (`alembic upgrade head`).
- [ ] `jobhunter-dashboard.service` + `jobhunter-api.service` en `running`.
- [ ] 7 timers de cron habilitados (`systemctl list-timers | grep jobhunter`).
- [ ] nginx + Let's Encrypt funcionando en HTTPS.
- [ ] Bucket S3 + IAM role asociado a la EC2.
- [ ] Primer backup exitoso (`sudo systemctl start jobhunter-backup.service`).
- [ ] Restore drill ejecutado al menos una vez (validación de DR1).
- [ ] Login al dashboard via HTTPS funciona; `/health` retorna `{"status": "healthy"}`.
- [ ] Alerta Telegram de prueba (forzar fallo en un servicio dummy).

Cuando los 13 ítems estén ✓, el sistema está en producción.
