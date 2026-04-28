# Documento I — Backlog Nivel 2: Descomposición de E5 (Real-time Notification System)

**Épica origen:** E5 — Real-time Notification System (Documento D).
**Tamaño épica:** S (≤1 día).
**Total stories:** 7.
**Estimación total:** 9–11 horas (1 sesión completa o 2 medias sesiones).

**Convenciones:** mismas que documentos E–H. ID `E05-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E5 cierra el ciclo del MVP P0. Una vez que E4 marca un job como tier A, este sistema notifica al usuario en <2 minutos vía Telegram, y consolida el resumen semanal vía email los domingos. Sin esto, el sistema corre en silencio y los matches de calidad se pierden en el dashboard hasta que el usuario lo abra (lo cual no escala).

### Decisiones técnicas clave

1. **Notifier pattern (plugin)** — `BaseNotifier` con implementaciones `TelegramNotifier`, `EmailNotifier`. Mismo espíritu que `BaseSource` en E3.
2. **Idempotencia vía tabla `notifications_sent`** — nunca dos notificaciones por el mismo job. Sobrevive a re-corridas y crashes.
3. **Templates Jinja2** versionados en `templates/notifications/` — consistente con prompts versionados de E4.
4. **Telegram bot read-only inicialmente** — solo envía; comandos interactivos (`/status`, `/note`) son P1, no P0. Mejor enviar bien que enviar + comandos a medias.
5. **Email digest agregado, no por job** — un solo email semanal con resumen, no spam diario.
6. **Failure resilience** — si Telegram cae, el sistema sigue funcionando; notificación queda pendiente para retry.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E05-S01 | `BaseNotifier` ABC + tabla `notifications_sent` | 1.5h | E2 cerrada | — |
| E05-S02 | Templates Jinja2 para mensajes | 1h | S01 | con S03 |
| E05-S03 | `TelegramNotifier` implementación | 2h | S01 | con S02 |
| E05-S04 | `EmailNotifier` (SMTP) implementación | 2h | S01 | con S03 |
| E05-S05 | Despachador de notificaciones tier-A | 1.5h | S02, S03 | — |
| E05-S06 | Email digest semanal | 1h | S04 | — |
| E05-S07 | CLI + tests de integración | 1.5h | S05, S06 | — |

### Camino crítico

```
E2 ─→ S01 ─→ ┬─→ S02 ─┐
             ├─→ S03 ─┴─→ S05 ─┐
             └─→ S04 ─→ S06 ────┴─→ S07
```

**Tiempo serial:** ~10h. **Con paralelización (S02+S03+S04 juntos):** ~7h.

### Definition of Done de la épica

```bash
# Despachar notificaciones pendientes (lo que invocará el cron de E8 tras cada scoring)
jobhunter notify dispatch
# → envía a Telegram cada job tier A no notificado, marca en notifications_sent

# Re-correr no envía duplicados
jobhunter notify dispatch  # 0 enviados

# Generar y enviar digest semanal
jobhunter notify digest --send

# Test manual de canales
jobhunter notify test --channel telegram --message "ping"
```

Y, evidencia visual: recibir el primer mensaje real en Telegram.

---

## E05-S01 — `BaseNotifier` ABC + tabla `notifications_sent`

**Como** dueño del sistema, **quiero** un contrato abstracto para canales de notificación y persistencia para deduplicar envíos, **para que** añadir un canal nuevo (ej. Discord, SMS) sea estrictamente: implementar interfaz, registrar.

### Acceptance Criteria

- [ ] `src/jobhunter/notify/base.py` con `BaseNotifier(ABC)` y método abstracto `async send(message: NotificationMessage) -> NotificationResult`.
- [ ] Cada `BaseNotifier` tiene: `name: str` (identificador único), `is_enabled() -> bool` (lee de `Settings`).
- [ ] `NotificationMessage` (Pydantic): `channel: str`, `subject: str | None`, `body_text: str`, `body_html: str | None`, `metadata: dict` (ej. `{"job_id": "uuid"}`).
- [ ] `NotificationResult` (Pydantic): `success: bool`, `provider_message_id: str | None`, `error: str | None`, `duration_ms: int`.
- [ ] Nueva tabla `notifications_sent` (migration Alembic):
  - `id` UUID PK, `channel` VARCHAR, `dedup_key` VARCHAR (unique), `job_id` UUID nullable FK, `sent_at` TIMESTAMPTZ, `provider_message_id` TEXT, `success` BOOL, `error` TEXT.
  - Constraint UNIQUE en `(channel, dedup_key)`.
  - Índice en `(job_id, channel)`.
- [ ] `src/jobhunter/db/repos/notifications.py` con `NotificationsRepo`:
  - `was_sent(channel, dedup_key) -> bool`
  - `record_sent(channel, dedup_key, job_id, result)`
  - `failures_in_last(hours) -> int` (para alerting).
- [ ] Registry: decorator `@register_notifier` análogo al de E3.

### Tasks

- [ ] Crear `src/jobhunter/notify/__init__.py`
- [ ] Crear `src/jobhunter/notify/base.py` con ABC, registry, modelos Pydantic
- [ ] Migration Alembic `notifications_sent`
- [ ] Crear `NotificationsRepo`
- [ ] Tests unitarios sobre `was_sent` (true/false), `record_sent` (idempotencia con UNIQUE)

### Estimación: 1.5h

### Notas

- **`dedup_key` por canal, no global.** Ej.: para Telegram tier-A, `dedup_key = f"tier_a:{job_id}"`. Para digest semanal, `dedup_key = f"digest:{year}:{week_number}"`. Esto permite que el mismo job pueda generar múltiples notificaciones distintas (tier-A inicial + interview reminder, etc., en el futuro).
- **`UNIQUE(channel, dedup_key)`** garantiza idempotencia a nivel DB — incluso si dos workers llaman `send()` simultáneamente, solo uno persiste.

---

## E05-S02 — Templates Jinja2 para mensajes

**Como** dueño del sistema, **quiero** templates versionados para los mensajes, **para que** ajustar la presentación no requiera tocar código y los cambios queden diffables en PRs.

### Acceptance Criteria

- [ ] Directorio `templates/notifications/` en repo.
- [ ] Templates iniciales:
  - `tier_a_match_telegram.md` — mensaje compacto con: título, empresa, score, salario estimado, link, top 3 match points.
  - `tier_a_match_email.html` — versión HTML para email (si se decide enviar también por email; opcional).
  - `weekly_digest_email.html` — resumen semanal: matches A nuevos, B pendientes, follow-ups vencidos, métricas top.
  - `weekly_digest_email.txt` — versión texto plano (multipart fallback).
- [ ] `src/jobhunter/notify/templates.py` con función `render(template_name, context) -> str`.
- [ ] Jinja2 environment configurado: `autoescape=select_autoescape(['html'])`, `trim_blocks=True`, `lstrip_blocks=True`.
- [ ] Filtros custom útiles: `format_currency`, `format_date_human` ("hace 2 días"), `truncate_words`.

### Tasks

- [ ] Añadir dependencia `jinja2` (probablemente ya transitiva)
- [ ] Crear directorio + 4 templates iniciales
- [ ] Implementar `render()` con caching del environment
- [ ] Filtros custom
- [ ] Tests: render con context dummy produce string esperado, sin escape issues

### Estimación: 1h

### Paralelizable con

S03, S04.

### Notas

- **Markdown para Telegram**, HTML para email. Telegram soporta MarkdownV2 con caveats (caracteres a escapar). Documentar en el template + función helper `escape_telegram_markdown()`.
- **Templates en repo, no en DB.** Versionado git, diff en PRs, simple. La justificación es la misma que para los prompts.

---

## E05-S03 — `TelegramNotifier` implementación

**Como** dueño del sistema, **quiero** notificaciones de matches tier-A llegando a Telegram en tiempo real, **para que** pueda reaccionar a buenas oportunidades en minutos, no horas.

### Acceptance Criteria

- [ ] `src/jobhunter/notify/telegram.py` con clase `TelegramNotifier(BaseNotifier)` registrada.
- [ ] Usa `python-telegram-bot` (async) — `Bot(token).send_message(chat_id, text, parse_mode='MarkdownV2')`.
- [ ] Lee credenciales de `Settings.telegram_bot_token` y `Settings.telegram_chat_id`.
- [ ] `is_enabled()` devuelve `False` si token o chat_id están vacíos (permite deshabilitar limpiamente).
- [ ] Manejo de errores: `RetryAfter` (rate limit Telegram) → respeta `retry_after`; `BadRequest` (mensaje malformado) → log + return failure (no raise).
- [ ] Helper `escape_telegram_markdown_v2(text)` que escapa caracteres especiales de MarkdownV2 (`_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`).
- [ ] Trunca mensaje a 4096 chars (limit Telegram); si excede, agrega "…" al final.
- [ ] Tests con `python-telegram-bot` mockeado: éxito, rate limit retry, BadRequest no-raise.

### Tasks

- [ ] Añadir dependencia `python-telegram-bot[asyncio]` (verificar versión actual)
- [ ] Implementar `TelegramNotifier`
- [ ] Implementar `escape_telegram_markdown_v2`
- [ ] Tests con mocks
- [ ] Test manual end-to-end: `jobhunter notify test --channel telegram --message "Hello from setup"` debe llegar al chat real

### Estimación: 2h

### Paralelizable con

S02, S04.

### Notas

- **Setup del bot** (proceso humano, fuera de código):
  1. Hablar con `@BotFather` en Telegram → `/newbot` → guardar token.
  2. Iniciar conversación con tu bot, enviar `/start`.
  3. Visitar `https://api.telegram.org/bot<TOKEN>/getUpdates` → extraer `chat.id`.
  4. Poner ambos en `.env`.
  
  Documentar este proceso en `docs/runbook.md`.

- **MarkdownV2 es estricto.** Los puntos en URLs, los guiones en fechas, todo necesita escape. Una librería alternativa es `telegramify-markdown` si el escape custom resulta tedioso.

---

## E05-S04 — `EmailNotifier` (SMTP) implementación

**Como** dueño del sistema, **quiero** notificaciones por email vía Gmail SMTP, **para que** el digest semanal y backups de notificación crítica estén cubiertos.

### Acceptance Criteria

- [ ] `src/jobhunter/notify/email.py` con clase `EmailNotifier(BaseNotifier)`.
- [ ] Usa `aiosmtplib` para envío async (no bloquea el event loop).
- [ ] Soporta multipart (text + HTML) — fallback a text si cliente no renderiza HTML.
- [ ] Lee de `Settings`: `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `digest_to_email`.
- [ ] `is_enabled()` = `False` si credenciales vacías.
- [ ] Manejo de errores: `SMTPException` → log + failure, no raise.
- [ ] Test con `aiosmtplib` mockeado: envío exitoso, fallo SMTP no-raise.

### Tasks

- [ ] Añadir dependencia `aiosmtplib`
- [ ] Implementar `EmailNotifier` con multipart MIME
- [ ] Tests con mock
- [ ] Test manual: `jobhunter notify test --channel email --subject "Test" --message "Hello"` debe llegar al inbox

### Estimación: 2h

### Paralelizable con

S02, S03.

### Notas

- **Gmail App Password.** Si usas cuenta Gmail con 2FA (deberías), no se puede usar password directo de la cuenta. Requiere "App password" generado en https://myaccount.google.com/apppasswords. Documentar en `docs/runbook.md`.
- **Alternativa:** SendGrid free tier (100 emails/día) o Resend free tier. Más confiable que SMTP para deliverability, pero añade dep externa. Para volumen actual (1 digest/semana + ~20 alertas/mes), Gmail SMTP basta.

---

## E05-S05 — Despachador de notificaciones tier-A

**Como** dueño del sistema, **quiero** una función que tome jobs tier-A no notificados y los despache vía Telegram, **para que** el cron de E8 simplemente la invoque tras cada scoring batch.

### Acceptance Criteria

- [ ] `src/jobhunter/notify/dispatcher.py` con `async dispatch_tier_a_notifications(session) -> DispatchReport`.
- [ ] Selecciona jobs `tier='A'` que NO están en `notifications_sent` con `(channel='telegram', dedup_key='tier_a:{job_id}')`.
- [ ] Por cada job:
  1. Renderiza template `tier_a_match_telegram.md` con `job` + `score_data`.
  2. Llama `TelegramNotifier.send(message)`.
  3. Persiste en `notifications_sent` con resultado (incluso si falló — para evitar retry infinito; futura corrida puede limpiar fallos viejos).
- [ ] Lag objetivo: <2 min desde que `Job.scored_at` se setea hasta notificación enviada (cron de E8 lo hará posible).
- [ ] `DispatchReport` (Pydantic): `total_pending`, `success_count`, `failure_count`, `errors: list[str]`, `duration_ms`.
- [ ] Si `TelegramNotifier.is_enabled() == False`, función log warning y return early sin error.
- [ ] Tests: dispatch con 3 jobs (todos nuevos) → 3 enviados; correr de nuevo → 0 enviados; uno falla → otros completan.

### Tasks

- [ ] Crear `dispatcher.py`
- [ ] Implementar `dispatch_tier_a_notifications`
- [ ] Función auxiliar `_build_message(job, template_name)` (testeable aisladamente)
- [ ] Tests con notifier mockeado

### Estimación: 1.5h

### Notas

- **Política de retry para fallos.** Decisión: por simplicidad, MVP marca fallos como "sent=false" en `notifications_sent` y no reintenta automáticamente — evita infinite retry si Telegram banea el bot. Si en operación esto resulta molesto, añadir job de "retry failed notifications older than X" en E11 (analytics/ops).
- **Dedup_key incluye job_id** — futuro-proof: si más adelante quieres re-notificar por update (ej. "este job tier-A subió de score con re-scoring Sonnet"), usas un dedup_key diferente.

---

## E05-S06 — Email digest semanal

**Como** dueño del sistema, **quiero** un email resumen los domingos a las 18:00 COT con el estado del pipeline, **para que** tenga visibilidad agregada sin abrir el dashboard cada día.

### Acceptance Criteria

- [ ] `src/jobhunter/notify/digest.py` con `async send_weekly_digest(session, week_ending: date | None = None) -> NotificationResult`.
- [ ] Calcula contexto:
  - **Nuevos esta semana:** N jobs ingestados, N tier A, N tier B, N tier C.
  - **Aplicaciones:** N enviadas esta semana, X tasa de respuesta agregada (últimas 4 semanas).
  - **Pendientes:** N follow-ups vencidos, N tier A no aplicados (en `queued`), N tier C en `manual_review` esperando decisión.
  - **Top 5 tier A no aplicados:** lista con título, empresa, score, link.
  - **Métricas mensuales** (de `weekly_metrics` de E2): apps/semana, conversión a entrevista.
- [ ] Renderiza ambos templates: `weekly_digest_email.html` + `weekly_digest_email.txt`.
- [ ] Envía via `EmailNotifier`.
- [ ] Idempotencia: dedup_key = `digest:{iso_year}:{iso_week}`. Re-correr el mismo lunes no envía duplicado.
- [ ] Si NO hay actividad esta semana (0 jobs nuevos, 0 aplicaciones), aún envía el email (con tono honesto: "Pipeline silencioso esta semana, posibles causas: …"). Útil para detectar pipeline roto.

### Tasks

- [ ] Implementar `send_weekly_digest`
- [ ] Helper `_compute_digest_context(session, week_range)` (testeable)
- [ ] Test con DB seeded: contexto computado correctamente.
- [ ] Test con DB vacía: digest se envía con mensaje apropiado.
- [ ] Test idempotencia: re-correr no envía duplicado.

### Estimación: 1h

### Notas

- **Tono del digest.** Útil = honesto. Si una semana tuvo 0 matches A, el email lo dice + sugiere causas posibles ("¿fuente rota? ¿prompt muy estricto? Revisar `jobhunter sources list`"). Mejor que "no news is good news" silencioso.
- **`week_ending=None` default** = última semana ISO completada. Útil para el cron del domingo.

---

## E05-S07 — CLI + tests de integración

**Como** dueño del sistema, **quiero** comandos CLI para operación manual y tests end-to-end, **para que** debug, primer setup, y CI estén cubiertos.

### Acceptance Criteria

- [ ] Subgroup CLI `jobhunter notify` con comandos:
  - [ ] `notify dispatch` — invoca `dispatch_tier_a_notifications`. Salida con tabla rich.
  - [ ] `notify digest [--send] [--week-ending DATE]` — si `--send` envía, si no solo imprime preview en stdout.
  - [ ] `notify test --channel CHANNEL [--message MSG] [--subject SUBJ]` — envía mensaje arbitrario al canal especificado (debug).
  - [ ] `notify status` — muestra estado: ¿canales habilitados?, últimas 10 notificaciones enviadas, fallos en últimas 24h.
- [ ] Tests integración end-to-end con notifiers mockeados:
  - [ ] Dispatch tier-A: 3 jobs → 3 sends → 3 records en `notifications_sent`.
  - [ ] Re-dispatch: 0 sends.
  - [ ] Digest dispatch: 1 send con dedup_key correcto.
  - [ ] Test que verifica `notify status` muestra info coherente.
- [ ] Update `docs/runbook.md` con sección "Configurar Telegram bot" y "Configurar Gmail SMTP".

### Tasks

- [ ] Implementar comandos CLI
- [ ] Tests integración con DB + notifiers mockeados
- [ ] Documentación en runbook

### Estimación: 1.5h

### Notas

- **`notify status` es valioso.** Cuando algo falla en operación, este comando responde rápido "¿el canal está enabled? ¿cuándo fue la última notificación exitosa?". Sin él, debug requiere abrir DB.

---

## Definition of Ready para E6

E5 cerrada cuando:

- [ ] Las 7 stories tienen AC ✅.
- [ ] CI verde con tests integración (notifiers mockeados).
- [ ] Test manual end-to-end: notificación real recibida en Telegram.
- [ ] Test manual end-to-end: digest real recibido en email.
- [ ] `docs/runbook.md` documenta setup de Telegram bot y Gmail App Password.
- [ ] `jobhunter notify status` corre y muestra info coherente.
- [ ] Tag `v0.5.0` creado.

A partir de aquí: **MVP P0 funcionalmente completo** una vez se cierre E8 (scheduling). E6 (toolkit) y E7 (dashboard) son siguientes prioritarios para productividad operativa.

---

## Anexo: ¿Por qué no comandos interactivos en Telegram aún?

Telegram bots pueden recibir comandos (`/status`, `/note`, `/applied`) — sería ergonómico mover estados desde el chat. Pero implementarlo bien requiere:
- Webhook server expuesto a internet (ngrok local o hosting), o polling persistente.
- Manejo de sesión/estado conversacional.
- Auth (que solo tú puedas mandar comandos al bot).
- Tests más complejos.

Para MVP, **send-only es suficiente.** Comandos interactivos quedan como story candidata para E11 (analytics/ops) o como mini-épica futura, cuando tengas claro qué comandos te resultan más útiles tras 4 semanas operando.

---

**Fin Documento I.**
