# Configuración humana — habilitar el sistema al 100%

Guía paso a paso de **todo lo que el sistema NO puede hacer por sí solo** y un
humano debe configurar para que Job Hunter EU funcione contra cuentas reales,
busque empleo con tu perfil real y notifique a tu Telegram/email reales.

Compañera de [`DEPLOY_AWS.md`](./DEPLOY_AWS.md): aquel cubre la
infraestructura; este cubre **credenciales, perfil y datos personales**.

---

## 0. Resumen — qué requiere intervención humana

| Categoría | Ítem | Tiempo | Frecuencia |
|---|---|---|---|
| **Cuentas externas** | Anthropic API + facturación | 5 min | una vez |
| | Telegram Bot + chat ID | 10 min | una vez |
| | Gmail App Password (SMTP) | 5 min | una vez |
| | Gmail OAuth (response detection) | 15 min | una vez |
| | AWS account + S3 bucket | 10 min | una vez |
| | Dominio + DNS A-record | 5 min | una vez |
| **Datos personales** | `candidate_profile.yaml` | 30 min | una vez (revisar trimestralmente) |
| | 1–3 variantes de CV reales | 30–60 min cada uno | una vez (actualizar al cambiar empleo) |
| **Bootstrap** | Primer login + ceremonias | 30 min | una vez |
| **Operación diaria** | Revisar matches, mover apps, aprobar sugerencias | 10–20 min | diaria |
| **Outreach manual** | Copy-paste drafts a LinkedIn | 5 min/mensaje | semanal |
| **Mantenimiento** | Rotar secretos comprometidos | 30 min | sólo cuando aplique |

Total setup inicial: **~2.5 horas humanas**, distribuibles en 2 sesiones.

---

## 1. Cuentas externas — pasos por servicio

> **Convención de comandos.** Todos los comandos `python -m jobhunter ...` de
> esta sección asumen que estás en la raíz del repo y se ejecutan **dentro
> del venv gestionado por `uv`**. Sin esto, Python responde
> `No module named jobhunter`. Dos formas equivalentes:
>
> ```bash
> # Opción A (recomendada, sin activar venv):
> uv run python -m jobhunter <comando>
>
> # Opción B (activar venv una vez en la sesión):
> source .venv/bin/activate
> python -m jobhunter <comando>
> ```
>
> En la EC2 desplegada (`DEPLOY_AWS.md`) los comandos los corre el usuario
> de servicio `jobhunter` desde `/home/jobhunter/app` con `uv run` —
> mismo principio.

### 1.1 Anthropic (obligatorio)

El modelo principal del sistema. Sin esto no hay scoring ni cover letters.

1. Ir a <https://console.anthropic.com/> y crear cuenta.
2. **Agregar método de pago** en *Settings → Billing*. Cargar al menos $10 de crédito (suficiente para 4-6 meses de operación normal).
3. Crear API Key en *Settings → API Keys → Create Key*. Nombrarla `jobhunter-prod`.
4. **Copiar la key inmediatamente** (sólo se muestra una vez) y guardarla en el `.env` como `ANTHROPIC_API_KEY=sk-ant-...`.
5. Verificar el budget configurado en `Settings.LLM_MONTHLY_BUDGET_USD = 25.0` — el sistema lo usa como failsafe (E4-S06). Ajustar si tu uso esperado es distinto.

**Costo esperado:** ~$5–8/mes con uso normal (Haiku para scoring, Opus para cover letters, Sonnet para outreach + reportes).

### 1.2 Telegram Bot (recomendado)

Notificaciones tier-A en tiempo real + sugerencias de cambio de estado por respuesta de email (E10).

1. En Telegram, abrir chat con [`@BotFather`](https://t.me/BotFather).
2. Enviar `/newbot`. Cuando pida nombre, poner algo descriptivo (`Job Hunter Personal Bot`). Cuando pida username, debe terminar en `bot` (`tu_jobhunter_bot`).
3. BotFather devuelve el **token** con formato `123456789:ABCdef...`. Copiarlo a `.env` como `TELEGRAM_BOT_TOKEN`.
4. Iniciar conversación con tu nuevo bot (`/start`).
5. Obtener el **chat ID**: visitar `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` en el navegador. Buscar `"chat":{"id":123456789,...}`. Copiar ese número a `.env` como `TELEGRAM_CHAT_ID`.
6. Probar con `uv run python -m jobhunter notify test --channel telegram --message "ping"` — debe llegar el mensaje. Si aparece `No module named jobhunter`, falta el prefijo `uv run` o el venv no está activo (ver convención al inicio de §1).

**Permisos del bot:** ningún permiso especial. El bot sólo te envía a ti, en tu chat 1-a-1. Los inline buttons (E10-S06) funcionan dentro de ese chat sin webhook.

### 1.3 Gmail SMTP — para digest semanal (opcional)

Si quieres recibir el digest semanal por correo (E5-S06).

1. La cuenta Gmail debe tener **2FA activada** (sino no puedes generar app password).
2. Ir a <https://myaccount.google.com/apppasswords>.
3. Generar una **App Password** específica para "Job Hunter". Google devuelve 16 caracteres tipo `abcd efgh ijkl mnop`.
4. En `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=tu@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop      # sin espacios
   DIGEST_TO_EMAIL=tu@gmail.com         # puede ser el mismo o distinto
   ```
5. Probar con `uv run python -m jobhunter notify test --channel email --subject "Test" --message "Hello"`.

**Alternativas a Gmail:** SendGrid (100 emails/día free), Resend (3000/mes free). Más confiables que SMTP residencial pero requieren cambios mínimos en la app si quieres usarlos. Para el volumen actual (1 digest/semana + ~10 alertas/mes), Gmail SMTP basta.

### 1.4 Gmail OAuth — para response detection (E10) (opcional pero recomendado)

Lee tu inbox para detectar respuestas a aplicaciones y proponer cambios de estado por Telegram. Si no lo configuras, pierdes E10 entera (todo el resto sigue funcionando).

1. Ir a <https://console.cloud.google.com/>. Crear proyecto `jobhunter-personal`.
2. *APIs & Services → Library → Gmail API → Enable*.
3. *APIs & Services → OAuth consent screen*:
   - User type: **External**.
   - App name: `Job Hunter Personal`.
   - Developer contact email: tu email.
   - Scopes: añadir `gmail.readonly` y `gmail.modify` (los únicos que el sistema usa — scope mínimo).
   - Test users: **añadir tu email de Gmail** (mientras esté en modo Testing, sólo los test users pueden autenticar).
4. *APIs & Services → Credentials → Create Credentials → OAuth Client ID*:
   - Application type: **Desktop app**.
   - Name: `jobhunter-cli`.
   - Descargar el JSON o copiar `client_id` y `client_secret`.
5. En `.env`:
   ```
   GMAIL_CLIENT_ID=xxxx.apps.googleusercontent.com
   GMAIL_CLIENT_SECRET=GOCSPX-xxxx
   GMAIL_REDIRECT_URI=http://localhost:8765/oauth/callback   # default, no cambiar
   OAUTH_ENCRYPTION_KEY=<generar con: uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
   ```
6. **Ejecutar el flow OAuth una sola vez**:
   ```bash
   uv run python -m jobhunter email auth
   ```
   - Esto abre el navegador, pide login + consent, y captura el callback en `localhost:8765`.
   - El refresh token queda **cifrado en la DB** con `OAUTH_ENCRYPTION_KEY` (E10-S01).
   - Si el deploy es en EC2 sin navegador local, hacer port-forward SSH: `ssh -L 8765:localhost:8765 ec2-user@...` y correr el comando dentro de la EC2; el navegador se abre en tu máquina local.

**Importante:** si pierdes la `OAUTH_ENCRYPTION_KEY`, todos los tokens OAuth quedan inutilizables y debes re-correr `email auth`. Backupéala fuera del repo (1Password, Bitwarden, o similar).

### 1.5 AWS — para backups en S3 (recomendado)

Cubierto en `DEPLOY_AWS.md` §6.1. Resumen para humano:

1. Cuenta AWS (free tier funciona durante 12 meses).
2. Crear bucket `jobhunter-backups-<algo-único>`.
3. Crear IAM Role con la policy de S3 (la del DEPLOY doc) y adjuntarlo a la EC2 — **no usar access keys hardcoded** si es posible.
4. Lifecycle policy: borrar backups >84 días (alineado con `BACKUP_RETENTION_WEEKS=12`).

### 1.6 LinkedIn — export de contactos (recomendado para outreach)

E9 (Recruiter Outreach Module) puede importar tus conexiones de LinkedIn para empezar la base de contactos. **El sistema NO envía mensajes automáticamente** (decisión arquitectónica E9, anexo): tú haces copy-paste manual del draft generado.

1. En LinkedIn: *Me → Settings → Data Privacy → Get a copy of your data*.
2. Seleccionar **"Connections"**. LinkedIn envía un email con el CSV en 10–24 horas.
3. Descargar `Connections.csv`.
4. Importar al sistema:
   ```bash
   uv run python -m jobhunter outreach import --from ~/Downloads/Connections.csv
   ```
5. Opcionalmente con AI scoring para clasificar relevancia (~$0.50 para 500 contactos):
   ```bash
   uv run python -m jobhunter outreach import --from ~/Downloads/Connections.csv --enrich-with-ai
   ```

### 1.7 Dominio + DNS (sólo si expones el dashboard)

Si vas a acceder al dashboard desde fuera de tu red local:

1. Comprar dominio (Namecheap, Cloudflare, etc.) — `~$10–15/año`.
2. En el panel DNS, crear registro **A** apuntando a la Elastic IP de la EC2:
   ```
   jobhunter.tudominio.com   A   <ELASTIC_IP>   TTL 300
   ```
3. Esperar propagación (5–60 min).
4. Continuar con `certbot --nginx -d jobhunter.tudominio.com` (paso de `DEPLOY_AWS.md` §5).

**Alternativa sin dominio público:** [Tailscale](https://tailscale.com/) gratis para personal use. Instala el cliente en EC2 + tu laptop/móvil, y el dashboard es accesible vía la IP privada de Tailscale (`100.x.x.x`) sin exponer nada a internet. **Más seguro** y sin necesidad de Let's Encrypt ni dominio.

---

## 2. Personalización del perfil — el corazón del scoring

Sin estos archivos personalizados, el sistema scoreará jobs **contra el perfil de otra persona** y los matches serán irrelevantes.

> ### ⚠️ Estado de transición — el contenido de §2 será reemplazado por E14
>
> Las secciones §2.1–§2.5 describen el **flujo manual actual** basado en
> archivos (`prompts/candidate_profile.yaml` + `.local/cv_variants/*.md`).
> Esta es deuda arquitectónica heredada del bootstrap (ver
> [`ADR-008`](docs/adr/ADR-008-profile-in-db.md)).
>
> **La épica E14 — Onboarding Automation** (ver
> [`R_Backlog_Nivel_2_E14.md`](docs/Plan%20automatizado%20para%20b%C3%BAsqueda%20de%20trabajo%20remoto%20en%20Europa/R_Backlog_Nivel_2_E14.md))
> automatiza esta sección entera con un wizard web que:
>
> 1. Acepta tu CV maestro en PDF/MD/DOCX subido desde el dashboard.
> 2. Extrae datos estructurados con Opus (~$0.10).
> 3. Genera el perfil + N variants de CV (user-defined, no las 3 fijas
>    actuales) + propuesta de rango salarial con Sonnet (~$0.06).
> 4. Persiste todo en BD (no en archivos), habilita multi-profile, audit
>    trail y edit en vivo desde el mismo wizard.
> 5. Coste total bootstrap: **~$0.20 one-shot** vs. ~30–60 min manuales hoy.
>
> Mientras E14 no esté implementada, sigue las instrucciones manuales de
> §2.1–§2.5. Cuando E14 cierre, esta sección se reescribirá para apuntar al
> wizard. La migración de tu yaml/markdowns existentes a BD será automática
> (`alembic upgrade head` los importa y archiva los originales — ver
> E14-S10).

### 2.1 `prompts/candidate_profile.yaml` — perfil maestro (manual, hoy)

Este YAML alimenta:

- El **outreach generator** (E9) — lee el archivo en cada generación de mensaje.
- El **outreach contact scoring** (E9) — usa `primary_stack` para heurística.

> **Nota técnica importante** (correcta con la realidad del código): el
> scoring de jobs (E4) NO lee este archivo. El perfil está **literalmente
> embebido** dentro de `prompts/scoring/v1.md` como bloque yaml hardcoded.
> Esto significa que **debes mantener los dos sincronizados a mano**: si
> editas el yaml debes editar también el bloque dentro del prompt v1.md (o
> aceptar que el scoring evalúa contra un perfil distinto al outreach). Esta
> duplicación es exactamente la deuda técnica que E14 resuelve.

**Editar `prompts/candidate_profile.yaml`** con tus datos. Campos críticos:

| Campo | Qué pongo | Impacto |
|---|---|---|
| `name`, `seniority`, `years_experience` | Datos básicos | Aparece en cover letters y outreach. |
| `primary_stack` | Las 4-7 tecnologías que dominas a nivel senior | Prompt de scoring premia jobs con overlap; penaliza los muy alejados. |
| `secondary_stack` | Tecnologías que conoces pero no son foco | Suben el score si aparecen en la JD pero no son blockers si faltan. |
| `domains` | Áreas de expertise (ej. `[GenAI, backend, mobile]`) | Influye en la recomendación de tier B vs A. |
| `location_legal.country` + `work_authorization` | Tu situación legal | Crítico: el scorer aplica `hard_blockers` si la JD pide ciudadanía/permiso EU. |
| `contract_preferences` | B2B contractor / EOR / direct employment | Determina compatibilidad con cómo paga la empresa. |
| `timezone.home` + `overlap_max_acceptable_hours_with_CET` | Tu zona y tu límite de overlap | Filtra jobs que requieren too-much overlap síncrono. |
| `compensation.floor_usd_month` / `target` / `stretch` | Tus 3 thresholds salariales | Jobs por debajo del floor → REJECT automático. |
| `language.{english,spanish,...}` | Niveles reales | Jobs que requieren idiomas que no tienes → blockers. |
| `hard_blockers` | Lista de criterios que **siempre** son REJECT | Define qué jobs ni se evalúan. |
| `soft_negatives` | Penalizaciones (no blockers) | Bajan score pero no rechazan. |
| `positive_signals` | Patterns que suben score | Lo que tu CV tiene de single. |

**Iteración:** después de procesar 20–30 jobs reales, revisar las decisiones del scorer. Si marca tier A jobs que tú considerarías tier B (o viceversa), **ajusta el bloque embebido en `prompts/scoring/v1.md`** (es lo que el scorer realmente lee) y **el yaml** (lo que outreach realmente lee). Con E14 cerrada, esto se vuelve un único punto de actualización.

### 2.2 CV variants — `cv_variants/*.template.md` → `.local/cv_variants/*.md`

> Hoy hardcoded a las 3 variantes siguientes; con E14 esto será **N variantes
> user-defined** (puedes tener `python_backend`, `translator_es`,
> `ai_agent_consultant`, lo que sea — el `variant_selector` se refactoriza
> para soportar nombres arbitrarios).

El sistema actual espera **3 variantes de CV** en formato markdown
estructurado:

- `ai_python.md` — perfil AI/Python/ML/LLM.
- `flutter.md` — perfil Flutter/Dart/mobile.
- `fullstack.md` — perfil generalista web full-stack.

**Plantillas vacías** (sin tus datos) viven en `cv_variants/` con sufijo `.template.md`. **Las versiones reales** (con tus datos personales) viven en `.local/cv_variants/` (gitignored — nunca se commitea).

**Pasos para crear los reales:**

1. Crear el directorio local:
   ```bash
   mkdir -p .local/cv_variants
   ```
2. Copiar cada template como punto de partida:
   ```bash
   cp cv_variants/ai_python.template.md .local/cv_variants/ai_python.md
   cp cv_variants/flutter.template.md .local/cv_variants/flutter.md
   cp cv_variants/fullstack.template.md .local/cv_variants/fullstack.md
   ```
3. **Editar cada uno** sustituyendo placeholders por tu información real, manteniendo la estructura semántica que el parser necesita:
   ```markdown
   # [TU NOMBRE]

   ## SUMMARY
   <2-3 frases describiéndote para esta variante específica>

   ## STACK
   - primary: <tecnologías core, separadas por coma>
   - secondary: <tecnologías complementarias>

   ## EXPERIENCE
   ### <Rol> | <Empresa> | <Fechas>
   - <Bullet 1: logro cuantificable cuando se pueda>
   - <Bullet 2>
   - <Bullet 3>

   ### <Rol anterior> | <Empresa anterior> | <Fechas>
   - ...

   ## SKILLS
   - <Habilidad 1>
   - <Habilidad 2>
   ```

**¿Por qué 3 variantes?** El sistema (E6-S02) elige automáticamente la mejor según el job: si la JD es para AI Engineer, usa `ai_python`; si es para Flutter Senior, usa `flutter`; en ambigüedad usa `fullstack`. Tu cover letter y CV final reflejan la variante elegida.

**Si sólo te postulas a un tipo de rol**, puedes dejar las 3 idénticas o crear sólo `fullstack.md` y modificar `variant_selector.recommend_cv_variant` para que siempre devuelva `fullstack`. Pero perderás precisión.

### 2.3 Frases prohibidas — `prompts/{cover_letter,outreach}/forbidden_phrases.txt`

Listas de frases que el LLM NO debe incluir en cover letters / outreach messages. Ya hay defaults razonables (en español/inglés mezclados):

```
I am writing to express interest in
amazing experience
passionate about
team player
fast learner
...
```

**Personalizar:** añadir frases que tú detectas como genéricas en cover letters que has recibido o enviado. El sistema valida post-LLM: si el draft contiene alguna prohibida, hace un retry con prompt reforzado.

### 2.4 Empresas DACH AI-friendly — `src/jobhunter/outreach/dach_companies.py`

Lista hardcoded de empresas en Alemania/Austria/Suiza que el scoring de outreach (E9-S04) considera "AI-friendly" (suben el score de un contacto que trabaja en ellas). Default incluye N26, Trade Republic, Personio, Aleph Alpha, DeepL, Klarna, etc.

**Personalizar:** si tu lista de target companies es distinta (ej. fintech US-only o latam-focused), reemplazar el set por tu lista. Es código Python pero es trivial:

```python
AI_FRIENDLY_DACH_COMPANIES = {
    "MyTargetCo1",
    "MyTargetCo2",
    ...
}
```

### 2.5 Iteración de prompts (avanzado, opcional)

Los prompts versionados (`prompts/scoring/v1.md`, `prompts/cover_letter/v1.md`, etc.) son **plantillas genéricas que funcionan para casi cualquier perfil**. NO necesitas tocarlos para empezar.

**Cuándo iterar a v2:**

- Tras 50+ scorings observas drift consistente (ej. el scorer no penaliza suficientemente jobs con timezone overlap problemático).
- Tras 10+ cover letters generadas, los outputs sienten un patrón repetitivo o demasiado formal/informal para tu voz.

Workflow para iterar:

1. Copiar `v1.md` → `v2.md`.
2. Editar `v2.md` con los ajustes.
3. Probar con `score-job <ID>` o `letter <job-id>` puntual.
4. Si funciona mejor, actualizar `Settings.PROMPT_VERSION` o usar A/B testing (E11-S02) para validar en sample real.
5. Cuando v2 supere a v1 con significancia estadística, marcar v2 como default.

---

## 3. Bootstrap inicial — primeros 30 minutos tras `DEPLOY_AWS.md`

Asumiendo que la EC2 está funcional y `.env` está rellenado con todas las credenciales, secuencia recomendada:

```bash
# 1. SSH a la EC2 (o local si pruebas en tu máquina)
ssh -i ~/.ssh/jobhunter-key.pem ubuntu@<elastic-ip>

# 2. Verificar que todos los servicios cargan correctamente
sudo systemctl status jobhunter-dashboard jobhunter-api postgresql

# 3. Probar canales de notificación (NO consume Anthropic, sólo Telegram + email)
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter notify test --channel telegram --message "Setup test ✅"'
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter notify test --channel email --subject "Setup test" --message "Bootstrap OK"'

# 4. (Opcional) OAuth de Gmail si vas a usar response detection
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter email auth'
# (Requiere SSH tunnel localhost:8765 si la EC2 no tiene navegador)

# 5. (Opcional) Sembrar DB con datos demo para explorar el dashboard sin esperar al pipeline
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter db-seed --scenario rich'

# 6. Primer ingest manual con límite bajo para verificar conectividad
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter ingest --limit 5 --since "1 day ago"'
# Deberías ver: 5 ofertas nuevas por fuente (o explicación de por qué 0)

# 7. Primer scoring contra los jobs ingestados
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter score --limit 10'
# Deberías ver: 10 jobs scoreados, distribución de tiers, costo en USD

# 8. Primer dispatch de notificaciones tier-A
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter notify dispatch'

# 9. Estado de salud
sudo -u jobhunter -H bash -c 'cd /home/jobhunter/app && uv run python -m jobhunter health-check'

# 10. Ver el dashboard en el navegador
# https://jobhunter.tudominio.com  (o IP elastic via Tailscale)
# Login con DASHBOARD_PASSWORD del .env
```

**Si todo funcionó:** los timers de cron tomarán el relevo. El próximo ciclo automático ocurre según la calendar configurada en `DEPLOY_AWS.md` §4.3.

**Si algo falló:** `journalctl -u <service> --since "10 min ago"` y `docs/runbook.md` (sección Troubleshooting).

---

## 4. Operación diaria humana

Lo que NO se automatiza, por diseño (E6, E9, E10 todos preservan "human in the loop"):

### Mañana (5–10 min)

1. Abrir dashboard, ir a **New Matches**. Revisar tier A nuevos.
2. Por cada uno: leer score reasoning + match points. Decidir:
   - **Apply** → click "Assist", revisar cover letter generada en `pages/7_🛠_Assist.py`, copiarla, aplicar manualmente al portal/email del job, luego "Mark Applied".
   - **Skip** → click "Skip" (transiciona a `archived`).
3. Si hay alertas Telegram pendientes (ej. "Posible respuesta de N26 → mover a `screening`?"), tap "Aprobar" o "Rechazar".

### A lo largo del día (reactivo)

- Llega notificación Telegram de match A nueva → decidir si vale la pena interrumpir y aplicar ya.
- Llega notificación Telegram de respuesta detectada → confirmar/rechazar el cambio de estado.

### Tarde / fin de día (5 min)

1. Pipeline page del dashboard: mover aplicaciones que cambiaron de estado por feedback que no llegó por email (ej. te llamaron por teléfono).
2. Outreach page: enviar 1–3 mensajes proactivos vía LinkedIn:
   - Ir a "Outreach", "Generate Message", elegir contacto + template + escribir research notes específicas (ej. "Vi que tu equipo lanzó X la semana pasada").
   - Click "Generate" (~5s).
   - Editar el draft si es necesario. Copiar.
   - Pegar en LinkedIn manualmente. Enviar.
   - Click "Mark as Sent" en el dashboard.

### Semana (15 min, los lunes)

1. Domingo recibes el digest semanal por email — leerlo.
2. Lunes recibes alerta Telegram si hay regresiones (E11-S03) — investigar si las hay.
3. Manual review (`pages/3_🔍_Manual_Review.py`) — revisar tier C acumulados (cuando esa página esté implementada — ver E13-S01).
4. Si vas a iterar el prompt o ajustar el perfil, hacerlo el lunes en frío.

### Trimestral (1 hora)

- Revisar `prompts/candidate_profile.yaml`: ¿siguen vigentes mis preferencias salariales? ¿Cambió mi stack?
- Revisar `cv_variants/*.md`: ¿hay nuevos roles/logros que añadir?
- Revisar reportes mensuales generados en `reports/` (E11-S05): ¿qué dice la IA sobre tendencias?

---

## 5. Materiales de ayuda — qué documentación existe y qué faltaría

### Ya in-tree (consultar primero)

| Documento | Cuándo consultarlo |
|---|---|
| `README.md` | Descripción general, badges, quick start. |
| `CLAUDE.md` | Para asistir a Claude Code en este repo (no para humanos directamente). |
| `DEPLOY_AWS.md` | Setup de infraestructura. |
| `docs/runbook.md` (53 secciones) | Troubleshooting y disaster recovery. **El documento más denso del repo.** Empezar siempre aquí ante un incidente. |
| `docs/data_model.md` | Si necesitas entender el schema o añadir una tabla. |
| `docs/ARCHITECTURE.md` | Vista de alto nivel de los módulos. |
| `docs/adr/ADR-00*.md` | Decisiones arquitectónicas explicadas (por qué Streamlit, por qué Postgres, etc.). |
| `docs/sources.md` | Catálogo de fuentes de empleo soportadas. |
| `docs/Plan automatizado.../*.md` | Backlog completo nivel 2 con AC por story. Útil para entender por qué algo está hecho como está. |
| `CONTRIBUTING.md` | Estándar de PRs (Conventional Commits, branch flow). |

### Documentación que NO existe pero valdría la pena escribir

| Material | Para quién | Esfuerzo | Por qué |
|---|---|---|---|
| **`QUICKSTART.md`** local-dev (sin AWS) | Cualquiera que quiera probar antes de deploy | 30 min | Acortar el path "clonar → pytest verde → primer ingest" para evaluadores rápidos. |
| **Screencast: tour del dashboard** (5–7 min) | Reviewers / portfolio | 1 hora | Mostrar las 8 páginas en vivo. Subir a Loom o YouTube no-listado. |
| **Screencast: workflow diario** (3 min) | Tú mismo en 6 meses | 30 min | Recordatorio visual de "matches → assist → apply → mark" cuando vuelvas tras pausa. |
| **Screencast: bootstrap inicial** (10 min) | Tú mismo o si compartes el sistema | 1 hora | Cubre §1 + §3 de este doc en video. Especialmente útil para el OAuth de Gmail (la parte más confusa). |
| **GIF anotado del dashboard** en README | Visitantes del repo | 15 min | El badge `dashboard preview` ya existe pero un GIF de 10s con overlays ayuda. |
| **`PROMPT_TUNING.md`** | Yo en 3 meses, cuando quiera ajustar | 1 hora | Cómo iterar v1 → v2, cómo medir mejora, cuándo concluir un A/B test. |
| **FAQ.md** | Reviewers que evalúan el portfolio | 30 min | Preguntas anticipadas: "¿por qué no auto-apply?", "¿cuánto cuesta operar?", "¿es legal scrapear esos sites?". |

**Recomendación práctica:** los 3 screencasts cortos son los de **mayor ROI**. Una hora de grabación = años de "yo del futuro" agradecido. Subir como **unlisted** en YouTube y enlazarlos en el README.

### Materiales externos relevantes

- [Streamlit docs](https://docs.streamlit.io/) — para entender los patrones del dashboard.
- [Anthropic prompt engineering guide](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview) — cuando vayas a iterar prompts.
- [Telegram Bot API](https://core.telegram.org/bots/api) — si quieres extender funcionalidad del bot.
- [Gmail API OAuth scopes](https://developers.google.com/identity/protocols/oauth2/scopes#gmail) — si necesitas ampliar permisos del email matcher.

---

## 6. Rotación de secretos — cuándo y cómo

Si una credencial se filtra o sospechas compromiso, sigue este orden:

| Secreto | Cómo rotar | Impacto |
|---|---|---|
| `ANTHROPIC_API_KEY` | Console Anthropic → revocar key vieja, crear nueva, actualizar `.env`, `systemctl restart jobhunter-*` | 0 downtime si rapido. |
| `TELEGRAM_BOT_TOKEN` | `@BotFather → /revoke → /newtoken`. Actualizar `.env` + restart. | Mensajes en cola se pierden. |
| `GMAIL_CLIENT_SECRET` | Google Cloud Console → Credentials → eliminar y recrear. **Usuarios deben re-autenticar** (correr `email auth` de nuevo). | Pierdes detección de respuestas hasta re-auth. |
| `OAUTH_ENCRYPTION_KEY` | **Más crítico.** Generar nueva con `Fernet.generate_key()`. **TODOS los OAuth tokens en DB quedan inutilizables** — re-correr `email auth` para cada provider. | Backup la nueva key fuera del repo inmediatamente. |
| `SMTP_PASSWORD` | Google → App Passwords → revocar + crear nueva. | Pierdes envío de email hasta actualizar `.env`. |
| `DASHBOARD_PASSWORD` | Cambiar en `.env`, restart. Cierra todas las sesiones activas. | Mínimo. |
| `DATABASE_URL` (password de Postgres) | `sudo -u postgres psql -c "ALTER USER jobhunter PASSWORD 'nuevo'"` + actualizar `.env` + restart todo. | Downtime ~30s. |
| AWS access keys (si los usas en vez de IAM role) | IAM Console → desactivar key vieja, crear nueva, actualizar config. | Backups pueden fallar 1 ciclo. |

**Cada rotación se debe registrar** en `audit_log` (E13-S05 cuando esté implementado). Mientras tanto, `git commit` en un archivo `SECRETS_ROTATIONS.md` privado (NO en este repo) con fecha + razón es buen sustituto.

---

## 7. Checklist final del setup humano

Imprimir o pinear este checklist. Cuando los 20 ítems estén ✓, el sistema está completamente operativo:

### Cuentas externas

- [ ] Anthropic account + billing + API key copiada al `.env`.
- [ ] Telegram bot creado, token + chat ID en `.env`.
- [ ] Gmail App Password generada (si usarás digest).
- [ ] Google Cloud project + OAuth Client ID generado (si usarás response detection).
- [ ] AWS account + S3 bucket + IAM role adjunto a EC2 (si usarás backups).
- [ ] LinkedIn Connections.csv exportado (si usarás outreach).
- [ ] Dominio registrado + DNS A-record apuntando a Elastic IP (si expones dashboard) **o** Tailscale instalado.

### Datos personales

- [ ] `prompts/candidate_profile.yaml` revisado y editado con tus datos.
- [ ] Al menos 1 CV variant real creada en `.local/cv_variants/`.
- [ ] (Recomendado) Las 3 variants creadas para que el selector funcione bien.
- [ ] `forbidden_phrases.txt` revisada y ajustada (opcional).
- [ ] `dach_companies.py` revisada (opcional, sólo si tu target geográfico no es DACH).

### Bootstrap

- [ ] `notify test --channel telegram` recibido en tu Telegram.
- [ ] `notify test --channel email` recibido en tu inbox.
- [ ] `email auth` ejecutado, OAuth flow completado sin error.
- [ ] `ingest --limit 5` muestra al menos 5 jobs nuevos.
- [ ] `score --limit 10` muestra distribución de tiers y costo.
- [ ] `notify dispatch` ejecutado al menos una vez (puede ser 0 envíos si no hay tier-A).
- [ ] Login al dashboard funciona vía HTTPS (o IP Tailscale).
- [ ] `health-check` retorna `status: healthy`.

### Operación

- [ ] Recibido al menos 1 digest semanal.
- [ ] Aprobada o rechazada al menos 1 sugerencia de cambio de estado por Telegram.

Cuando los 20 ítems estén ✓, **el sistema está al 100% personalizado para ti**. Cualquier ajuste posterior (iterar prompts, añadir variants, cambiar empresas target) es opcional y data-driven.
