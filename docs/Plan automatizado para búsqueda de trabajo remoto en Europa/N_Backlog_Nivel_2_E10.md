# Documento N — Backlog Nivel 2: Descomposición de E10 (Response Detection — Gmail Integration)

**Épica origen:** E10 — Response Detection (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 14–17 horas (3 sesiones de medio día).

**Convenciones:** mismas que documentos E–M. ID `E10-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E10 cierra el ciclo de seguimiento. Hasta aquí, cuando una empresa o reclutador responde a una aplicación o outreach, el usuario tiene que **manualmente** abrir el dashboard y mover el estado. Para 5 aplicaciones/semana es manejable; para 30+ se vuelve fricción real. E10 lee el inbox vía Gmail API, detecta respuestas, las correlaciona con `applications` o `outreach_messages`, y propone update de estado. **Reducción de tiempo de actualización manual estimada: 80%.**

**Principio operativo crítico:** el sistema **NUNCA cambia estados automáticamente sin confirmación.** Siempre **propone** el cambio (vía Telegram o dashboard), el usuario **confirma**. Razón: false positives en correlación de email destruirían la integridad del tracker — un email de marketing de una empresa donde aplicaste podría confundirse con respuesta del proceso.

### Decisiones técnicas clave

1. **OAuth2 con scope mínimo** (`gmail.readonly` + `gmail.modify` solo para etiquetas). Refresh token persistido en DB cifrado.
2. **Polling cada 30 min**, NO push notifications. Push (Gmail watch + Pub/Sub) requiere infra de webhook server pública — overkill para este volumen.
3. **Matching híbrido: heurística + IA opcional.** Primero match por dominio + asunto (gratis, ~70% precisión); si ambiguo, escalar a Haiku para clasificación (`is_response_to_application: bool, suggested_status: ...`).
4. **Tabla `email_messages` para audit** — cada email procesado se persiste con su match decision. Permite debugging de false positives/negatives.
5. **Etiquetado en Gmail propio** (`jobhunter/applied`, `jobhunter/screening`, etc.) — bidireccional: el usuario también puede mover labels manualmente y el sistema lo respeta.
6. **Sugerencias vía Telegram con botones inline** — el usuario aprueba/rechaza con un tap, sin abrir dashboard.
7. **Privacidad first** — emails procesados se almacenan SOLO con metadata (sender, subject, date, sentiment) y un hash del body, NUNCA el contenido completo. Excepción: snippet de 200 chars para contexto de la sugerencia.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E10-S01 | OAuth2 Gmail setup + token storage | 2h | E2 cerrada | — |
| E10-S02 | Tabla `email_messages` + repo | 1.5h | S01 | con S03 |
| E10-S03 | Gmail API client wrapper | 2h | S01 | con S02 |
| E10-S04 | Email matcher (heurística + IA) | 3h | S02, S03 | — |
| E10-S05 | Sugeridor de cambios de estado | 1.5h | S04 | con S06 |
| E10-S06 | Telegram bot inline buttons (interactividad) | 2h | E5 cerrada, S05 | con S05 |
| E10-S07 | Workflow `email-poll` cada 30 min | 1h | S05, S06, E8 cerrada | — |
| E10-S08 | Métricas de detección + tests | 1.5h | S07 | — |

### Camino crítico

```
E2 ─→ S01 ─→ ┬─→ S02 ─┐
             └─→ S03 ─┴─→ S04 ─→ ┬─→ S05 ─┐
                                 └─→ S06 ─┴─→ S07 ─→ S08
```

**Tiempo serial:** ~14h. **Con paralelización (S02+S03 juntos, S05+S06 juntos):** ~11h.

### Definition of Done de la épica

```bash
# Setup OAuth (paso manual del usuario una sola vez)
jobhunter email auth
# → abre browser, OAuth flow, persiste refresh_token cifrado

# Polling manual (verifica que funciona)
jobhunter email poll
# → conecta a Gmail, lee últimos 50 emails, matchea, propone updates

# Workflow automatizado corre cada 30 min en producción
gh workflow run email-poll.yml

# Cuando llega match probable → notificación Telegram con botones:
# "Email de @company.com sugiere mover Job#123 a 'screening'?"
# [Aprobar] [Rechazar] [Más contexto]

# Métricas tras 2 semanas:
jobhunter email stats
# → 90%+ detección de respuestas, 0 false positives críticos
```

---

## E10-S01 — OAuth2 Gmail setup + token storage

**Como** dueño del sistema, **quiero** autenticación Gmail vía OAuth2 con scope mínimo y persistencia segura de tokens, **para que** el sistema pueda leer mi inbox sin almacenar mi password ni requerir re-auth en cada polling.

### Acceptance Criteria

- [ ] Proyecto creado en Google Cloud Console (o reutilizar uno existente):
  - Gmail API habilitada.
  - OAuth consent screen configurado en "External" pero limitado a tu Google account.
  - OAuth Client ID generado (tipo "Desktop app").
- [ ] Credenciales (`client_id`, `client_secret`) en `Settings`:
  - `gmail_client_id: SecretStr`.
  - `gmail_client_secret: SecretStr`.
  - `gmail_redirect_uri: str = "http://localhost:8765/oauth/callback"`.
- [ ] Comando CLI `jobhunter email auth` que:
  1. Imprime URL de OAuth.
  2. Abre browser automáticamente (con `webbrowser.open()`).
  3. Levanta servidor HTTP local efímero en port 8765 para capturar el callback.
  4. Captura el `code`, intercambia por `access_token` + `refresh_token`.
  5. Persiste tokens cifrados en DB (nueva tabla `oauth_tokens`).
  6. Cierra servidor, imprime "Auth successful".
- [ ] Tabla nueva `oauth_tokens` (migration):
  - `id` UUID PK.
  - `provider` VARCHAR ("gmail", futuro: "linkedin", etc.).
  - `account_email` VARCHAR.
  - `access_token` TEXT (cifrado at rest con `cryptography.fernet`).
  - `refresh_token` TEXT (cifrado).
  - `expires_at` TIMESTAMPTZ.
  - `scopes` ARRAY[VARCHAR].
  - `created_at`, `updated_at`.
  - UNIQUE constraint `(provider, account_email)`.
- [ ] Settings nueva: `oauth_encryption_key: SecretStr` — clave Fernet generada una vez con `Fernet.generate_key()`. Documentar generación en runbook.
- [ ] Comando `jobhunter email auth --revoke` para revocar tokens (importante para security).
- [ ] Tests con mocks de OAuth flow.
- [ ] Documentación en `docs/runbook.md`:
  - Cómo crear el proyecto en Google Cloud Console paso a paso.
  - Cómo correr `auth` la primera vez.
  - Cómo rotar credenciales si se filtran.
  - Cómo revocar acceso desde Google Account settings.

### Tasks

- [ ] Crear proyecto Google Cloud + Gmail API enabled (manual).
- [ ] Configurar OAuth consent screen + generar Client ID.
- [ ] Settings: añadir 4 campos nuevos.
- [ ] Migration `oauth_tokens` con cifrado.
- [ ] `OAuthTokenRepo` en `db/repos/oauth_tokens.py` con métodos `save`, `get_active`, `delete`.
- [ ] Helper `crypto.py` con `encrypt(plaintext, key)` / `decrypt(ciphertext, key)` usando Fernet.
- [ ] Comando CLI `email auth` con flow completo.
- [ ] Tests con mocks.
- [ ] Runbook actualizado.

### Estimación: 2h

### Notas

- **Scope mínimo crítico.** `gmail.readonly` + `gmail.modify` (solo para labels). NO `gmail.send`, NO `gmail.compose`. Si Google revisa el OAuth consent (porque pasaste 100 usuarios), querrás defender un scope mínimo.
- **Cifrado at rest.** Fernet (symmetric) es suficiente; clave en `Settings.oauth_encryption_key` (env var). Si la DB se filtra sin la clave, los tokens son inutilizables.
- **Test mode vs Production.** Google permite OAuth apps en "Testing" mode hasta 100 usuarios sin verificación. Para sistema personal, basta. Si en el futuro otros usuarios accedieran, requeriría verification (días de espera + revisión Google).
- **Refresh token rotation.** Google refresh tokens NO expiran a menos que se revoquen explícitamente. Aceptable. Pero implementar refresh: `access_token` expira en 1h, hay que refresharlo on-demand antes de cada llamada.

---

## E10-S02 — Tabla `email_messages` + repo

**Como** dueño del sistema, **quiero** persistir cada email procesado con su match decision, **para que** debug de false positives/negatives sea posible y métricas de detección sean trackables.

### Acceptance Criteria

- [ ] Migration `add_email_messages_table`:
  - `id` UUID PK.
  - `gmail_message_id` VARCHAR UNIQUE — id de Gmail (`<...>@mail.gmail.com`).
  - `gmail_thread_id` VARCHAR — agrupar respuestas en threads.
  - `received_at` TIMESTAMPTZ.
  - `from_email` VARCHAR.
  - `from_domain` VARCHAR — extraído (ej. `recruiter@n26.com` → `n26.com`).
  - `subject` TEXT.
  - `snippet` TEXT — primeros 200 chars del body (para contexto en sugerencias).
  - `body_hash` VARCHAR(64) — sha256 del body completo (para detectar duplicados sin almacenar contenido).
  - `match_status` VARCHAR (enum: `unmatched`, `auto_matched`, `ai_matched`, `user_confirmed`, `user_rejected`, `ignored_marketing`).
  - `matched_application_id` UUID NULLABLE FK.
  - `matched_outreach_message_id` UUID NULLABLE FK.
  - `match_confidence` FLOAT (0-1).
  - `match_reasoning` TEXT — heurística que disparó el match.
  - `suggested_status_change` JSONB — ej. `{"from": "applied", "to": "screening"}`.
  - `processed_at` TIMESTAMPTZ.
- [ ] Constraint: solo uno de `matched_application_id` o `matched_outreach_message_id` puede ser NOT NULL.
- [ ] Índices: `(from_domain)`, `(match_status)`, `(received_at DESC)`.
- [ ] `EmailMessageRepo` con:
  - `record(gmail_msg, from_addr, ...) -> EmailMessage`.
  - `find_by_gmail_id(id) -> EmailMessage | None` (idempotencia: re-procesar mismo email no crea duplicados).
  - `list_unmatched(limit) -> list[EmailMessage]`.
  - `update_match(message_id, app_id|outreach_id, confidence, reasoning, suggestion)`.
  - `mark_user_confirmed(message_id) / mark_user_rejected(message_id)`.
- [ ] Tests CRUD + idempotencia.

### Tasks

- [ ] Enum `EmailMatchStatus` en `db/enums.py`.
- [ ] Migration Alembic.
- [ ] Modelo SQLAlchemy.
- [ ] Repo.
- [ ] Tests.

### Estimación: 1.5h

### Paralelizable con

S03.

### Notas

- **`body_hash`, no `body`.** Decisión de privacidad explícita. Si en el futuro querer contenido completo para LLM context, se hace fetch fresh from Gmail (audit trail vía Google) en vez de almacenar localmente.
- **`gmail_message_id` UNIQUE para idempotencia.** El polling puede traer overlap entre corridas; nunca duplicar.

---

## E10-S03 — Gmail API client wrapper

**Como** dueño del sistema, **quiero** un wrapper sobre la Gmail API con manejo de tokens, refresh automático, y rate limit, **para que** los servicios downstream lo usen sin pensar en OAuth plumbing.

### Acceptance Criteria

- [ ] `src/jobhunter/email/gmail_client.py` con clase `GmailClient`.
- [ ] Constructor recibe `OAuthTokenRepo`; carga tokens desde DB.
- [ ] Métodos:
  - `async list_messages(query: str, max_results: int = 50) -> list[GmailMessage]` — usa Gmail search syntax (ej. `"newer_than:1d"`, `"from:no-reply"`).
  - `async get_message(message_id: str) -> GmailMessageDetail` — incluye body parseado (HTML+text).
  - `async add_label(message_id: str, label_name: str)` — crea label si no existe.
  - `async remove_label(message_id: str, label_name: str)`.
  - `async list_labels() -> list[Label]`.
- [ ] Refresh automático del `access_token` cuando expira (detectar 401 → refresh → retry).
- [ ] Rate limit: respetar quota Gmail (~250 quota units por user per second; un `get_message` cuesta 5 units). Conservador: 1 req/200ms.
- [ ] `GmailMessage` (Pydantic): `id`, `thread_id`, `received_at`, `from_email`, `to_email`, `subject`, `snippet`, `labels`.
- [ ] `GmailMessageDetail` extiende con `body_text`, `body_html`.
- [ ] Tests con `google-api-python-client` mockeado.

### Tasks

- [ ] Añadir dependencias: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`.
- [ ] Implementar `GmailClient` con refresh logic.
- [ ] Helper `_parse_message(raw)` que extrae body de payload multipart de Gmail.
- [ ] Rate limiter con `asyncio.Semaphore`.
- [ ] Tests con mocks.

### Estimación: 2h

### Paralelizable con

S02.

### Notas

- **Gmail search syntax** es muy rica: `from:@n26.com newer_than:1d -in:spam`. Permite filtros precisos sin descargar todo el inbox.
- **Body de Gmail es nightmare-encoded.** Multipart, base64, charset variable, HTML+text alternativas. La librería oficial `google-api-python-client` ayuda pero el parser custom siempre hace falta. Dedicar tiempo a este helper.

---

## E10-S04 — Email matcher (heurística + IA)

**Como** dueño del sistema, **quiero** un servicio que reciba un email y proponga match contra `application` o `outreach_message`, **para que** las sugerencias de cambio de estado sean precisas.

### Acceptance Criteria

- [ ] `src/jobhunter/email/matcher.py` con `async match_email(email: GmailMessage, session, llm_client) -> MatchResult`.
- [ ] **Estrategia de matching escalonada:**
  1. **Heurística 1 — Domain match:** extrae `from_domain`, busca `applications` con `Job.company` similar al dominio o `contact_email` con mismo dominio en `outreach_contacts`. Si hay 1 match único → confidence 0.9.
  2. **Heurística 2 — Subject keyword match:** subject contiene "re: [job title]", "your application", "interview", "next steps" + match heurística 1 → confidence 0.95.
  3. **Heurística 3 — Marketing detector:** `from` contiene "noreply", "no-reply", "newsletter", `unsubscribe` en body → marcar como `ignored_marketing`. NO procesar.
  4. **Escalación a IA (si confidence <0.8):** invocar Haiku con prompt corto que recibe `(email subject + snippet, candidate jobs/contacts list)` y devuelve match + sugerencia de status change.
- [ ] `MatchResult` (Pydantic): `match_status`, `application_id | None`, `outreach_message_id | None`, `confidence`, `reasoning`, `suggested_change: dict | None`.
- [ ] **`suggested_change`** infiere transición de estado:
  - "interview" / "schedule a call" → `applied → screening` o `screening → interview_1`.
  - "rejected" / "moved forward with" / "regret to inform" → `* → rejected`.
  - "offer" / "compensation package" → `* → offer`.
  - Outreach: respuesta directa → `outreach_message.status = replied`.
- [ ] Persiste resultado en `email_messages` table.
- [ ] Tests cubren: 5 casos típicos (interview invite, rejection, marketing email, ambiguous outreach reply, unknown email).
- [ ] Coverage del módulo ≥ 80%.

### Tasks

- [ ] Crear `src/jobhunter/email/__init__.py` y `matcher.py`.
- [ ] Implementar 3 heurísticas + escalación IA.
- [ ] Prompt versionado en `prompts/email_matcher/v1.md`.
- [ ] `EmailMatcher.detect_status_change(email_content) -> str` — heurística sobre keywords.
- [ ] Tests con fixtures de emails reales (sanitizados).

### Estimación: 3h

### Notas

- **Heurística primero, IA después.** Ahorra ~70% de las llamadas LLM (la mayoría de respuestas son obvias por dominio + keywords). Costo total estimado: <$0.01/día en escala normal.
- **`reasoning` es valor en oro** para debugging. Cuando el sistema sugiere mal, leer `reasoning` te dice qué heurística falló.
- **Marketing detector es crítico.** Un solo email de marketing de N26 (donde aplicaste) confundido con respuesta destruiría el tracker. Lista de "marketing markers" hardcoded + lista learnable de senders frecuentes.

---

## E10-S05 — Sugeridor de cambios de estado

**Como** dueño del sistema, **quiero** un servicio que tome resultados del matcher y produzca sugerencias accionables al usuario, **para que** pueda aprobar/rechazar con un tap.

### Acceptance Criteria

- [ ] `src/jobhunter/email/suggester.py` con `async suggest_state_changes(session) -> list[StateSuggestion]`.
- [ ] Procesa emails recientes con `match_status='auto_matched'` o `'ai_matched'` y `confidence >= 0.7`.
- [ ] `StateSuggestion` (Pydantic):
  - `email_id`, `application_id | outreach_message_id`, `current_state`, `suggested_state`, `confidence`, `email_snippet`, `reasoning`.
- [ ] Threshold dinámico según confidence:
  - `confidence ≥ 0.9` y heurística clara → notificación informativa "auto-applied" (no requiere confirmación, pero sí log auditable).
  - `confidence 0.7-0.9` → notificación con botones de confirmación.
  - `confidence < 0.7` → silent, deja como `unmatched` para review manual en dashboard.
- [ ] Política conservadora documentada: **solo "auto-apply" para transiciones positivas** (applied→screening, screening→interview). Para rejected/offer SIEMPRE requiere confirmación humana, sin importar confidence.
- [ ] Sugerencias persistidas en `email_messages.suggested_status_change`.
- [ ] Tests cubren los 3 paths de threshold.

### Tasks

- [ ] Implementar `suggest_state_changes`.
- [ ] Política de auto-vs-confirm-required en helper `_requires_confirmation(suggestion) -> bool`.
- [ ] Tests con DB seeded.

### Estimación: 1.5h

### Paralelizable con

S06.

### Notas

- **"Auto-applied" sin confirmación humana es controvertido.** Decisión: solo para casos muy claros (confidence ≥0.9 + heurística sin escalación a IA + transición positiva). Cualquier duda → confirmar. Mejor errar del lado conservador.
- **Rejected/offer SIEMPRE confirma.** Razón: error en rejected pierde una oportunidad real (no recuperas un proceso marcado rechazado por error). Error en offer es false-celebration.

---

## E10-S06 — Telegram bot inline buttons (interactividad)

**Como** dueño del sistema, **quiero** notificaciones de sugerencias con botones inline en Telegram (Aprobar/Rechazar/Más contexto), **para que** confirmar cambios sea un tap, no abrir el dashboard.

### Acceptance Criteria

- [ ] Extender `TelegramNotifier` (de E5-S03) con `async send_with_buttons(message, buttons: list[Button]) -> str` (devuelve `message_id` para tracking).
- [ ] Mensaje formato:
  ```
  📧 Posible respuesta detectada
  
  Email de: sarah@n26.com
  "Hi Abner, we'd love to schedule a 30-min..."
  
  Sugerencia: Job#1234 (N26 Senior Python) 
  applied → screening
  Confidence: 87%
  
  [✅ Aprobar]  [❌ Rechazar]  [📄 Más contexto]
  ```
- [ ] Botones inline (Telegram `InlineKeyboardMarkup`) con callback_data: `approve:{suggestion_id}`, `reject:{suggestion_id}`, `context:{suggestion_id}`.
- [ ] **Webhook receiver en CLI:** comando `jobhunter telegram-webhook` levanta servidor local que procesa callbacks. Para producción usa polling (más simple sin webhook público).
- [ ] **Modo polling:** workflow `email-poll` (S07) tras enviar sugerencias también consume callbacks pendientes y procesa.
- [ ] Procesamiento de callbacks:
  - `approve` → ejecuta el cambio de estado, persiste en `email_messages.match_status='user_confirmed'`, edita el mensaje Telegram a "✅ Aplicado: applied → screening".
  - `reject` → marca `email_messages.match_status='user_rejected'`, edita mensaje a "❌ Rechazado".
  - `context` → envía mensaje secundario con detalle expandido (full snippet, link a dashboard).
- [ ] Idempotencia: un callback procesado dos veces no aplica el cambio dos veces (verifica `match_status` antes de actuar).
- [ ] Tests con Telegram mockeado.

### Tasks

- [ ] Extender `TelegramNotifier` con métodos para inline buttons.
- [ ] Implementar `process_callback_updates(updates)` que procesa callbacks pendientes via `Bot.get_updates()`.
- [ ] Comando `jobhunter telegram process-callbacks` para correr standalone.
- [ ] Integración en workflow de S07.
- [ ] Tests.

### Estimación: 2h

### Notas

- **Polling > webhook para este uso.** Webhook requiere servidor público con HTTPS. Polling: el workflow `email-poll` (cada 30 min) tras enviar sugerencias también consume callbacks. Latencia hasta 30 min para procesar respuesta del usuario — aceptable para este caso.
- **Telegram callback expira.** Si el usuario tarda > 1 día en responder, el botón aún funciona (Telegram no expira callbacks por tiempo). Pero si rechazas, recordar que el sistema NO va a re-sugerir el mismo email — `user_rejected` es final.

---

## E10-S07 — Workflow `email-poll` cada 30 min

**Como** dueño del sistema, **quiero** un workflow que dispare polling de Gmail + matching + sugerencias cada 30 min, **para que** las respuestas se detecten en near-real-time sin intervención manual.

### Acceptance Criteria

- [ ] `.github/workflows/email-poll.yml` con:
  - Schedule cron: `'*/30 * * * *'` (cada 30 min).
  - Trigger manual.
  - Steps:
    1. Checkout, setup uv, sync.
    2. Composite action `setup-env` (de E8-S01) extendida con env vars de Gmail (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `OAUTH_ENCRYPTION_KEY`).
    3. `uv run jobhunter email poll-and-suggest`.
  - Timeout: 5 min.
  - Concurrency control: `email-poll`, `cancel-in-progress: false`.
- [ ] Comando CLI `jobhunter email poll-and-suggest` que:
  1. Llama `GmailClient.list_messages(query="newer_than:1h -from:me")`.
  2. Para cada email no procesado (verificar `email_messages.gmail_message_id`):
     - Procesa con `EmailMatcher`.
     - Si match con confidence suficiente, ejecuta `suggester` y envía Telegram con botones (S06).
  3. Procesa callbacks Telegram pendientes.
- [ ] Anti-spam (mismo patrón que E8): si el usuario está en una "tormenta" de emails (ej. 10 sugerencias en 1 hora), agruparlas en una sola notificación con summary.
- [ ] Alertas en caso de fallo (composite action de E8-S06).
- [ ] Logs estructurados upload (consistente con E8-S07).

### Tasks

- [ ] Workflow YAML.
- [ ] Extender `setup-env` con vars Gmail.
- [ ] Comando CLI orquestador.
- [ ] Logic de agrupación si >5 sugerencias pendientes.
- [ ] Tests del comando.

### Estimación: 1h

### Notas

- **Cron cada 30 min** = 48 corridas/día = ~50 minutos/día de runner si cada corrida toma 1 min = ~1500 min/mes. Sumado a workflows de E8 (~900 min/mes), **total ~2400 min/mes** vs free tier 2000 min/mes. **Posible overflow.**
- **Mitigaciones:** si overflow, reducir a cada 60 min (24/día → 720 min/mes). O sumar billing — GH Actions cobra $0.008/min después de free tier, ~$3/mes peor caso.

---

## E10-S08 — Métricas de detección + tests end-to-end

**Como** dueño del sistema, **quiero** métricas de precision/recall del matcher y tests end-to-end, **para que** pueda iterar las heurísticas y CI valide flujos completos.

### Acceptance Criteria

- [ ] Comando `jobhunter email stats` muestra:
  - Total emails procesados (último mes).
  - **Tasa de match:** % auto-matched, % ai-matched, % unmatched.
  - **Precision (estimada):** % de auto-matched que el usuario confirmó (vs rechazó). Target ≥85%.
  - **Recall (estimada):** difícil de medir automáticamente; reportar % de aplicaciones con cambio de estado manual reciente vs vía email (proxy de "missed responses").
  - **Costo IA:** total mes de calls de matcher con escalación.
  - **Top dominios** generadores de emails (para identificar marketing senders no detectados).
- [ ] Sección equivalente en dashboard E7 Metrics page.
- [ ] Tests integración end-to-end:
  - Email con interview invite → matcher detecta → suggester crea sugerencia → Telegram envía con botones → simular "approve" callback → verificar `Application.status='screening'`.
  - Email de marketing → matcher marca `ignored_marketing` → NO sugerencia.
  - Email ambiguo → matcher escala a IA → sugiere con confidence 0.75 → requiere confirmación humana.
  - Idempotencia: re-procesar mismo email no crea duplicados.
- [ ] Coverage `email/` ≥ 80%.

### Tasks

- [ ] Implementar `email stats` con queries.
- [ ] Sección dashboard.
- [ ] Tests integración con fixtures de emails.
- [ ] Coverage report.

### Estimación: 1.5h

### Notas

- **Precision is gold here.** Si <85%, el usuario aprende a desconfiar del sistema y deja de aprobar/rechazar — pierde valor. Si rinde alto, el sistema es maravilloso.
- **Recall imposible de medir 100%.** No podemos saber qué emails NO detectó como respuesta válida. Proxy: si una `Application` cambia de estado manualmente desde dashboard, posiblemente fue una respuesta missed — flag para revisión.

---

## Definition of Ready para E11

E10 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con tests integración.
- [ ] OAuth flow probado end-to-end al menos una vez.
- [ ] Workflow `email-poll` corre exitosamente al menos 24h.
- [ ] Al menos 5 emails reales procesados con sugerencias generadas y aprobadas/rechazadas vía Telegram.
- [ ] Precision ≥80% en muestra de 10 sugerencias.
- [ ] Tag `v0.10.0` creado.

A partir de aquí: **E11 (Analytics & Tuning)** consolida métricas cross-épica y A/B testing de prompts. **E12 (Observability avanzada)** podría consolidar observabilidad cross-épica.

---

## Anexo: ¿Por qué no IMAP en lugar de Gmail API?

Tentación: usar IMAP genérico (cualquier provider, no solo Gmail). Razones para usar Gmail API específicamente:

1. **Search syntax:** Gmail API soporta `newer_than:1d`, `from:domain`, `has:attachment` — IMAP lo simula con flags y date arithmetic engorroso.
2. **Labels:** Gmail labels >> IMAP folders. Etiquetar `jobhunter/screening` sin mover de inbox principal es nativo en Gmail.
3. **Threading:** Gmail conoce threads (`thread_id`); IMAP requiere reconstruirlos por subject + reply-to.
4. **Rate limits explícitos:** Gmail API documenta 250 quota units/sec; IMAP es opaco.

**Trade-off:** Gmail-only. Si en el futuro usas otro email provider, hay que reimplementar. Aceptable porque cuenta principal personal probablemente seguirá siendo Gmail.

---

## Anexo: Privacidad de emails

Decisión deliberada: **no almacenar contenido completo de emails.** Solo metadata + snippet (200 chars) + body_hash.

**Razones:**
1. **Reducir blast radius** si DB se compromete.
2. **GDPR-compliant by design.** Si en el futuro otros usuarios usan el sistema, sus emails NO viven en la DB.
3. **Suficiente para casos comunes.** El snippet de 200 chars es lo que el matcher necesita para >90% de casos.

**Excepción controlada:** si el matcher escala a IA y necesita más contexto, se hace fetch fresh from Gmail API en ese momento (audit log queda en Google), no se cachea localmente.

---

## Anexo: ¿Por qué no extender a otros providers (Outlook, Apple Mail, etc.)?

Para MVP del sistema personal, Gmail-only es suficiente. Outlook tiene su propia API (Graph API) con scope OAuth distinto — sería ~70% del trabajo de E10 reaplicado. Apple Mail no tiene API server-side (solo IMAP genérico).

**Si rinde:** abstraer `EmailProvider` interface y agregar `OutlookProvider` como story para E12 o futuro. Por ahora YAGNI.

---

**Fin Documento N.**
