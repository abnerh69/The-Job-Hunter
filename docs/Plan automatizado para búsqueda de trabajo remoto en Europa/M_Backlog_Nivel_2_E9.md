# Documento M — Backlog Nivel 2: Descomposición de E9 (Recruiter Outreach Module)

**Épica origen:** E9 — Recruiter Outreach Module (Documento D).
**Tamaño épica:** M (2-3 días).
**Total stories:** 8.
**Estimación total:** 13–16 horas (2-3 sesiones de medio día).

**Convenciones:** mismas que documentos E–L. ID `E09-S##`, formato user story + AC + tasks + estimación + notas.

---

## Resumen ejecutivo

E9 lleva a código el **Documento C — Playbook de Outreach a Reclutadores**. Hasta aquí el sistema descubre y aplica a ofertas públicas; E9 añade el canal proactivo: identificar reclutadores en LinkedIn/Xing, enviarles mensajes específicos asistidos por IA, y trackear cadencia de follow-ups. Históricamente outreach proactivo convierte mejor (10–15%) que aplicar en frío (5–10%).

**Principio operativo crítico:** el sistema **NUNCA envía mensajes automáticamente.** Genera borradores que tú revisas y envías manualmente. Razón explícita: LinkedIn/Xing detectan automation y banean cuentas. El sistema te ahorra el 90% del trabajo (research, draft, tracking) pero conserva el 10% que más impacto tiene (la firma humana + el envío manual).

### Decisiones técnicas clave

1. **`OutreachContact` y `OutreachRepo` ya existen** (E2-S04, E2-S07) — esta épica añade flujo de mensajes, generación IA, y cadencia.
2. **Templates de mensajes en `prompts/outreach/`** versionados, igual que prompts de E4 y templates de E5. Cuatro templates iniciales del Doc C: A_inhouse, B_boutique, C_senior, D_followup.
3. **Modelo Sonnet para generación** — calidad importa más que costo (los mensajes los lee un humano que decide si responder), pero Opus es overkill para mensajes de 4-6 frases. ~$0.015 por mensaje × 50/mes = $0.75.
4. **Tabla nueva `outreach_messages`** — auditable, separada de `outreach_contacts`. Permite múltiples mensajes a un mismo contacto.
5. **NO hay envío automático.** Todos los mensajes generados quedan como `status='draft'` hasta que el usuario los marque manualmente como enviados.
6. **Cadencia automatizada** — workflow diario detecta contactos que necesitan follow-up (7-10 días sin respuesta) y los marca para acción.
7. **Importación desde LinkedIn export** — flujo común: exportar conexiones desde LinkedIn → CSV → importar al sistema con scoring de relevancia.

### Tabla de stories

| ID | Título | Estimación | Depende de | Paralelizable |
|----|---|---|---|---|
| E09-S01 | Tabla `outreach_messages` + repo extension | 1.5h | E2 cerrada | — |
| E09-S02 | Templates de mensajes versionados | 1h | S01 | con S03 |
| E09-S03 | Generador IA de mensajes (Sonnet) | 2h | E4 cerrada | con S02 |
| E09-S04 | LinkedIn CSV importer + contact scoring | 2h | E2-S07 | con S03 |
| E09-S05 | Cadencia y follow-ups automatizados | 2h | S01, E5 cerrada | — |
| E09-S06 | CLI: `jobhunter outreach` (suite completa) | 2h | S03, S04, S05 | — |
| E09-S07 | Activación en dashboard (E7 outreach page) | 1.5h | S03, S06, E7-S05 | — |
| E09-S08 | Métricas de outreach + tests | 1.5h | S05, S06 | — |

### Camino crítico

```
E2,E4,E5,E7 ─→ S01 ─→ ┬─→ S02 ─┐
                      ├─→ S03 ─┴─→ S05 ─→ S06 ─→ S07 ─→ S08
                      └─→ S04 ──────────┘
```

**Tiempo serial:** ~13.5h. **Con paralelización (S02+S03 juntos, S04 con S05):** ~10h.

### Definition of Done de la épica

```bash
# Importar contactos desde LinkedIn export
jobhunter outreach import --from ~/Downloads/linkedin_connections.csv

# Identificar candidatos para outreach esta semana (top 10 por score)
jobhunter outreach candidates --limit 10

# Generar mensaje para un contacto específico
jobhunter outreach draft --contact-id X --type A_inhouse --note "Vi que postearon Senior Python role hace 3 días"
# → output: borrador editable, NO enviado

# Marcar como enviado tras hacer copy-paste manual a LinkedIn
jobhunter outreach sent --message-id Y

# Workflow diario detecta follow-ups pendientes (de E8-S05 extendido)
# → notificación Telegram: "💌 5 contactos esperan follow-up"

# Métricas
jobhunter outreach stats
# → tasa de respuesta por template, por mercado, por tipo de contacto
```

---

## E09-S01 — Tabla `outreach_messages` + repo extension

**Como** dueño del sistema, **quiero** persistir cada mensaje de outreach (borrador, enviado, follow-up) con su contenido, contexto, y estado, **para que** tenga audit trail completo y pueda medir efectividad por template/contacto.

### Acceptance Criteria

- [ ] Migration Alembic crea tabla `outreach_messages`:
  - `id` UUID PK.
  - `contact_id` UUID FK → `outreach_contacts(id)`, ON DELETE CASCADE.
  - `template_type` VARCHAR (enum: `A_inhouse`, `B_boutique`, `C_senior`, `D_followup`, `custom`).
  - `template_version` VARCHAR (ej. "v1") — qué versión del template generó este mensaje.
  - `subject` TEXT NULLABLE (para templates que llevan asunto).
  - `body` TEXT NOT NULL — el mensaje generado/editado.
  - `body_edited_by_user` BOOL — true si el usuario modificó el draft generado por IA.
  - `research_notes` TEXT NULLABLE — la frase específica que el usuario aportó al generar.
  - `model_used` VARCHAR — `claude-sonnet-4-6` típicamente.
  - `cost_usd` NUMERIC.
  - `status` VARCHAR (enum: `draft`, `sent`, `replied`, `ghosted`, `discarded`).
  - `created_at` TIMESTAMPTZ default now().
  - `sent_at` TIMESTAMPTZ NULLABLE.
  - `replied_at` TIMESTAMPTZ NULLABLE.
  - `parent_message_id` UUID NULLABLE FK self — para tracking de threads de follow-up.
- [ ] Índices: `(contact_id, created_at DESC)`, `(status, sent_at)` (parcial sobre estados activos).
- [ ] `OutreachMessageRepo` (extiende patrón de E2):
  - `create_draft(contact_id, template_type, body, ...) -> OutreachMessage`.
  - `mark_sent(message_id, sent_at=None)` — actualiza status, persiste timestamp, transiciona contact a `contacted`.
  - `mark_replied(message_id, replied_at=None)` — transiciona contact a `replied`.
  - `mark_ghosted(message_id)` — automático tras N días sin reply.
  - `list_by_contact(contact_id) -> list[OutreachMessage]` — historial completo del contacto.
  - `list_pending_followups(today, days_threshold=7) -> list[OutreachMessage]`.
- [ ] Tests: CRUD básico, transiciones de estado, índice parcial verificado, FK cascade.

### Tasks

- [ ] Migration Alembic `add_outreach_messages_table`.
- [ ] Enum `OutreachMessageStatus` y `OutreachMessageTemplate` en `db/enums.py`.
- [ ] Modelo SQLAlchemy en `db/models.py`.
- [ ] `OutreachMessageRepo` en `db/repos/outreach_messages.py`.
- [ ] Tests integración.

### Estimación: 1.5h

### Notas

- **`parent_message_id` para threads:** outreach D_followup puede referenciar el mensaje original A/B/C. Permite consultas tipo "muéstrame todos los threads donde el follow-up tuvo respuesta".
- **`body_edited_by_user`:** señal valiosa para calibración de prompts. Si 80% de los mensajes generados se editan significativamente antes de enviar, el prompt necesita iteración.
- **No `discarded` automático.** Mensajes draft que el usuario decide no enviar se marcan manualmente. Drafts viejos abandonados quedan visibles para limpieza periódica.

---

## E09-S02 — Templates de mensajes versionados

**Como** dueño del sistema, **quiero** los 4 templates del Documento C como prompts versionados en repo, **para que** ajustar tono o estructura sea diffable en PRs y cada mensaje persista qué versión lo generó.

### Acceptance Criteria

- [ ] Directorio `prompts/outreach/` en repo.
- [ ] 4 templates iniciales en `prompts/outreach/v1/`:
  - `A_inhouse.md` — reclutador in-house en empresa target.
  - `B_boutique.md` — reclutador de agencia boutique.
  - `C_senior.md` — outreach senior-to-senior (CTO, VP Eng).
  - `D_followup.md` — follow-up a un mensaje anterior sin respuesta.
- [ ] Cada template tiene estructura:
  ```markdown
  ## SYSTEM
  Eres un asistente que ayuda a Abner a redactar mensajes profesionales...
  
  ## USER_TEMPLATE
  Genera un mensaje de outreach tipo {template_type} para:
  CONTACT: {contact_name} ({contact_role}) en {contact_company}
  RESEARCH_NOTES: {research_notes}
  CANDIDATE_PROFILE: {candidate_profile_yaml}
  TARGET_TONE: directo, no genérico, 4-6 frases máximo
  ...
  
  ## REQUIREMENTS
  - Idioma: inglés (default) o español si {target_language}=es
  - Longitud: 80-150 palabras
  - Frases prohibidas: "I am writing to express", "amazing opportunity"
  - DEBE incluir referencia específica de research_notes
  ```
- [ ] `prompts/outreach/forbidden_phrases.txt` versionado (mismo concepto que cover letters de E6).
- [ ] `src/jobhunter/outreach/templates.py` con `load_template(template_type, version='latest') -> OutreachTemplate`.
- [ ] `OutreachTemplate` (Pydantic): `template_type`, `version`, `system_prompt`, `user_template`, `requirements`.
- [ ] Tests: cargar cada template, render con context dummy.

### Tasks

- [ ] Crear directorio + 4 templates iniciales basados en Documento C §3.
- [ ] Crear `forbidden_phrases.txt`.
- [ ] Implementar loader con versioning.
- [ ] Tests.

### Estimación: 1h

### Paralelizable con

S03.

### Notas

- **Iteración de templates es continua.** v1 es punto de partida; tras 20 mensajes enviados con response data, se ajusta a v2. Versionado permite A/B test entre v1 y v2 si vale la pena.
- **`target_tone` parametrizable:** algunos contactos requieren más formal (Alemania), otros casual (UK). Default formal-directo.

---

## E09-S03 — Generador IA de mensajes (Sonnet)

**Como** dueño del sistema, **quiero** generar borradores de mensajes específicos al contacto y contexto, **para que** la única edición humana sea ajuste de tono y verificación de precisión.

### Acceptance Criteria

- [ ] `src/jobhunter/outreach/generator.py` con `async generate_message(contact, template_type, research_notes, llm_client) -> MessageGenerationResult`.
- [ ] `MessageGenerationResult` (Pydantic): `body: str`, `subject: str | None`, `template_version: str`, `model: str`, `cost_usd: float`, `word_count: int`.
- [ ] Modelo: `claude-sonnet-4-6` (configurable vía `Settings.outreach_model`).
- [ ] Contexto inyectado en el prompt:
  - Datos del contacto (`name`, `role`, `company`, `market`, `notes`).
  - `research_notes` aportadas por el usuario.
  - Candidate profile (mismo YAML del Doc A).
  - Si `template_type='D_followup'`, también el `parent_message.body` para contexto.
- [ ] Validaciones post-LLM:
  - 80-150 palabras (mensajes de outreach efectivos son cortos).
  - No contiene frases prohibidas.
  - Incluye referencia textual a `research_notes` (verificación heurística simple: substring match).
  - Si validation falla → un retry con prompt reforzado, después raise `OutreachGenerationError`.
- [ ] Persiste el resultado como `OutreachMessage` con `status='draft'`.
- [ ] Costo registrado en `llm_calls` con `purpose='outreach_message'`.
- [ ] Tests con LLM mockeado.

### Tasks

- [ ] Crear `src/jobhunter/outreach/__init__.py` y `generator.py`.
- [ ] Implementar `generate_message`.
- [ ] Validators post-LLM.
- [ ] Tests con fixtures.

### Estimación: 2h

### Paralelizable con

S02.

### Notas

- **Investment de 30 min en prompt design** antes de cerrar la story. Capturar 3 fixtures reales con Sonnet contra contactos imaginarios y verificar tono.
- **`research_notes` es la salsa secreta.** Sin esto, el mensaje será genérico. La aplicación debe rechazar generar si `research_notes` está vacío o es muy corto (<20 chars).
- **No se envía nada automáticamente.** El generador solo crea drafts. Marcar como sent es paso manual posterior.

---

## E09-S04 — LinkedIn CSV importer + contact scoring

**Como** dueño del sistema, **quiero** importar contactos desde LinkedIn export con scoring automático de relevancia, **para que** pueda identificar de un batch de 500 conexiones cuáles 30 vale la pena contactar primero.

### Acceptance Criteria

- [ ] CLI command `jobhunter outreach import --from PATH` que:
  - Acepta CSV de LinkedIn export (formato: First Name, Last Name, URL, Email, Company, Position, Connected On).
  - Acepta CSV genérico con mapping flag `--mapping FILE`.
  - Detecta duplicados por LinkedIn URL (de E2-S07 `find_by_linkedin_url`).
  - Output: tabla con `imported`, `skipped (duplicate)`, `failed (validation)`.
- [ ] Scoring automático de relevancia para cada contacto importado:
  - `quality_score: int [1-5]` poblado heurísticamente:
    - +2 si position contiene "Tech Recruiter", "Talent Acquisition", "Engineering Recruiter".
    - +2 si position contiene "CTO", "VP Engineering", "Head of Engineering".
    - +1 si company es de las "AI-friendly DACH" (lista del Documento C §2.2).
    - +1 si specialty_stack matches CV stack primario.
    - Cap a 5.
  - `market` inferido de company location (best effort: keywords en company name "GmbH"→DE, "Ltd"→UK).
  - `specialty_stack` inferido de position keywords.
- [ ] **Modo `--enrich-with-ai`** (opcional, costo asumido): para cada contacto, invoca Haiku con prompt corto que evalúa relevancia leyendo position+company. Útil cuando la heurística no es suficiente.
- [ ] Helper `outreach/linkedin_csv.py`:
  - Parser robusto a variaciones de formato (LinkedIn cambia columnas ocasionalmente).
  - Validation: filas sin URL ni nombre se descartan con log.
- [ ] Tests con CSV de ejemplo.

### Tasks

- [ ] Implementar parser CSV con `csv.DictReader`.
- [ ] Implementar scoring heurístico.
- [ ] Modo `--enrich-with-ai` (opcional, batch con concurrency=5).
- [ ] CLI command.
- [ ] Test con CSV fixture.

### Estimación: 2h

### Paralelizable con

S03.

### Notas

- **LinkedIn export está limitado a tus conexiones,** no busca en LinkedIn público. Para contactar reclutadores que NO son conexiones, el flujo es manual (LinkedIn search → copy info → `jobhunter outreach add`).
- **`--enrich-with-ai`** cuesta ~$0.001 por contacto. Para batch de 500 = $0.50. Usar si el batch tiene mucho ruido (recruiters mezclados con ex-colegas etc.).
- **Hardcoded list de empresas DACH AI-friendly** vive en `outreach/dach_companies.py` — versionada, fácil de actualizar.

---

## E09-S05 — Cadencia y follow-ups automatizados

**Como** dueño del sistema, **quiero** detección automática de mensajes que necesitan follow-up y mensajes ghosted, **para que** el sistema empuje a actuar en la ventana correcta (7-10 días).

### Acceptance Criteria

- [ ] Comando CLI `jobhunter outreach check-cadence` que:
  - Identifica mensajes `status='sent'` con `sent_at` entre 7-10 días atrás → marca contacto como "due for followup" en notificación.
  - Identifica mensajes `status='sent'` con `sent_at` > 21 días → automáticamente marca `status='ghosted'`, transiciona contact a `ghosted`.
  - Refresh de estadísticas relevantes.
- [ ] Notificación Telegram (vía `EmailNotifier`/`TelegramNotifier` de E5) con lista compacta cuando hay follow-ups due:
  - "💌 3 contactos esperan follow-up: [Sarah at N26, Mark at Trade Republic, Anna at HelloFresh]. `jobhunter outreach draft --contact-id X --type D_followup`"
- [ ] **Política estricta de máximo 2 toques** (consistente con Doc C §3.4):
  - Si contacto ya tiene 2 mensajes con `template_type IN ('A','B','C','D_followup')`, NO se sugiere otro follow-up. El sistema fuerza a desistir.
- [ ] Comando se integra al workflow de E8-S05 (`followup-checks.yml`) — extender el comando ya existente para incluir outreach.
- [ ] Anti-spam: solo notificar si hay ≥1 follow-up pendiente; no enviar mensaje vacío "0 pendientes hoy".
- [ ] Tests con DB seeded variando antigüedades de mensajes.

### Tasks

- [ ] Implementar `check_outreach_cadence()` en `src/jobhunter/outreach/cadence.py`.
- [ ] Lógica anti-spam (dedup_key con bloque de día).
- [ ] Integración con E8-S05.
- [ ] Tests.

### Estimación: 2h

### Notas

- **Máximo 2 toques.** Sin esta regla, el sistema sugeriría follow-up cada 7 días en bucle. La regla del Documento C §3.4 ("Nunca tres mensajes sin respuesta") es ley. Después del 2do, el contacto se marca `ghosted` o `warm` (decisión manual desde dashboard).
- **No automatizar el envío del follow-up.** Solo se sugiere; el usuario invoca `outreach draft --type D_followup` manualmente.

---

## E09-S06 — CLI: `jobhunter outreach` (suite completa)

**Como** dueño del sistema, **quiero** una suite de comandos CLI ergonómica para el workflow completo de outreach, **para que** la operación diaria sea: identificar candidatos → generar draft → editar → enviar manual → registrar.

### Acceptance Criteria

- [ ] Subgroup `jobhunter outreach` con comandos:

#### `outreach add`
Añade contacto manualmente.
- Flags: `--name`, `--linkedin-url`, `--company`, `--role`, `--market`, `--notes`.

#### `outreach import`
(De S04) — importa CSV de LinkedIn.

#### `outreach candidates`
Lista contactos prioritarios para outreach esta semana.
- Flags: `--limit N` (default 10), `--market germany`, `--min-score 4`.
- Output: tabla rich con name, company, role, score, status, last_contacted.

#### `outreach draft <contact-id>`
Genera draft de mensaje.
- Flags: `--type A_inhouse|B_boutique|C_senior|D_followup` (required), `--note TEXT` (research_notes, required), `--language en|es` (default en).
- Output: tabla con datos del contacto + mensaje generado en bloque markdown rendering + comando para marcar enviado.
- Default: NO copia al clipboard (evita persisting in clipboard accidentalmente). Flag `--copy` opcional.

#### `outreach sent <message-id>`
Marca mensaje como enviado.
- Flag opcional `--at TIMESTAMP`.

#### `outreach replied <message-id>`
Marca como respondido.

#### `outreach list`
Lista todos los mensajes con filtros.
- Flags: `--status`, `--contact-id`, `--last N` (días).

#### `outreach stats`
(De S08) — métricas.

- [ ] Todos los comandos respetan exit codes coherentes (0 ok, 1 error).
- [ ] Tests CLI con `typer.testing.CliRunner`.

### Tasks

- [ ] Implementar 8 comandos en `src/jobhunter/cli.py` (subgroup `outreach`).
- [ ] Output rico con `rich.markdown.Markdown` para drafts.
- [ ] Tests CLI.

### Estimación: 2h

### Notas

- **`outreach candidates` ordenamiento**: por `quality_score DESC`, `last_contacted_at ASC NULLS FIRST`. Prioriza alto-score nunca-contactado.
- **`outreach draft` NO sale al clipboard por default**: evita riesgo de pegar accidentalmente. `--copy` explícito si lo quieres.
- **No hay `outreach send`.** Decisión arquitectónica: el sistema no envía. Si en el futuro hay automation safe (ej. webhook a un cliente Telegram-DM o un proxy controlado), podría revisarse.

---

## E09-S07 — Activación en dashboard (E7 outreach page)

**Como** dueño del sistema, **quiero** que el botón "Generate Message" de la página Outreach del dashboard (E7-S05) funcione, **para que** todo el workflow viva en una sola UI sin volver a terminal.

### Acceptance Criteria

- [ ] La página `pages/4_💌_Outreach.py` (de E7-S05) ahora tiene botón "Generate Message" funcional (estaba deshabilitado con tooltip "Available in E9").
- [ ] Click abre modal con form:
  - Template type (radio: A/B/C/D_followup).
  - Research notes (textarea, required, ≥20 chars).
  - Language (radio: en/es).
  - Botón "Generate".
- [ ] Spinner durante generación (~3-5s con Sonnet).
- [ ] Output renderizado:
  - Mensaje en textarea editable.
  - Botón "Copy" (con notificación de éxito).
  - Botón "Mark as Sent" (asume copy-paste manual hecho).
  - Botón "Discard" (status='discarded').
  - Si el usuario edita el mensaje antes de "Mark Sent", `body_edited_by_user=true` se persiste.
- [ ] Nueva columna en tabla de outreach: "Last Message" — link al mensaje más reciente con status badge.
- [ ] Vista expandible por contacto: timeline de todos los mensajes (drafts/sent/replied), similar a `application_events` timeline de E7-S03.

### Tasks

- [ ] Modal con form + validation.
- [ ] Integración con `generate_message` de S03.
- [ ] Persistir ediciones del usuario.
- [ ] Componente `render_message_timeline(messages)`.
- [ ] Tests E2E (Playwright) del flujo completo.

### Estimación: 1.5h

### Notas

- **Edit + persist**: las ediciones del usuario son señal valiosa para iterar el prompt. Si el usuario reescribe completamente el draft de la IA, es signal de que el prompt necesita trabajo.
- **Timeline por contacto** es importante: muestra cómo evolucionó la relación. "Apliqué a job X en empresa Y" + "outreached a recruiter Z el mes pasado, no respondió" — contexto valioso al decidir próxima acción.

---

## E09-S08 — Métricas de outreach + tests

**Como** dueño del sistema, **quiero** métricas de efectividad de outreach (tasa de respuesta por template, por mercado, por tipo de contacto) y tests end-to-end, **para que** pueda iterar la estrategia con data y CI valide el flujo completo.

### Acceptance Criteria

- [ ] Comando `jobhunter outreach stats` muestra:
  - Total mensajes enviados (último mes, últimas 8 semanas).
  - **Tasa de respuesta global** y desagregada por:
    - `template_type` (A_inhouse, B_boutique, etc.).
    - `market` (germany, eu_wide, uk).
    - `quality_score` del contacto (1-2, 3-4, 5).
  - Top 5 contactos warmest (status='warm' o `replied_at` reciente).
  - Mensajes pendientes follow-up vs ghosted vs activos.
  - **Tiempo medio a respuesta** (cuando hay reply).
- [ ] Sección equivalente añadida al dashboard de E7-S06 (Metrics page).
- [ ] Tests integración end-to-end:
  - Importar 5 contactos → generar 3 mensajes → marcar 2 sent + 1 replied → verificar stats coherentes.
  - Cadencia: mensaje sent hace 8 días → check-cadence detecta como "due followup".
  - Cadencia: mensaje sent hace 22 días → check-cadence marca como ghosted.
- [ ] Coverage ≥ 75% en módulo `outreach/`.

### Tasks

- [ ] Implementar `outreach stats` con queries agregadas.
- [ ] Sección en dashboard.
- [ ] Tests integración con DB seeded.
- [ ] Coverage report.

### Estimación: 1.5h

### Notas

- **Tasa de respuesta como métrica central.** Debería ser 10-20% sano (Doc C §7). <5% = problema de templates, perfiles target, o personalización.
- **A/B testing futuro:** si se ve que template A_inhouse v1 tiene 8% response y vale la pena, generar v2 con tweaks y comparar 4 semanas. Esta story prepara la base; el A/B testing real entra en E11.

---

## Definition of Ready para E10

E9 cerrada cuando:

- [ ] Las 8 stories tienen AC ✅.
- [ ] CI verde con tests integración.
- [ ] Workflow probado E2E desde dashboard: generar mensaje → marcar sent → simular reply → ver en stats.
- [ ] Al menos 5 mensajes reales enviados manualmente (con copy-paste a LinkedIn) usando drafts del sistema.
- [ ] Métricas iniciales capturadas (aunque sample sea pequeño).
- [ ] Tag `v0.9.0` creado.

A partir de aquí: **E10 (Gmail Response Detection)** es el siguiente lógico — automatizar la detección de respuestas a aplicaciones y outreach (hasta ahora se marca `replied` manualmente).

---

## Anexo: ¿Por qué no automatizar el envío?

Tentación recurrente: usar Playwright o LinkedIn API para enviar mensajes automáticamente. Razones para resistirla en E9 (y posiblemente para siempre):

1. **LinkedIn TOS** prohíbe explícitamente automation no autorizada. Riesgo de ban permanente con una sola cuenta.
2. **API oficial limitada:** LinkedIn API solo permite envío de mensajes a contactos a través de programas específicos (LinkedIn Sales Navigator, Recruiter) que cuestan cientos al mes.
3. **Calidad del touch:** "Mark as Sent" tras review humano garantiza que cada mensaje pasó tu filtro. Auto-send saturaría conversiones.
4. **Volumen apropiado:** outreach senior funciona con 10-15 mensajes/semana cuidados. No 100/día. Auto-send resuelve un problema que no tenemos.
5. **Detección anti-spam de LinkedIn** es agresiva. Patrones como "envió 20 mensajes en 1 hora" disparan alarmas.

**Excepción muy condicional:** si LinkedIn permitiera vía API oficial Y tuvieras Sales Navigator Y solo después de 6+ meses operando manualmente con éxito comprobado — quizás. Pero queda fuera de scope para siempre del MVP.

---

## Anexo: Email outreach como alternativa

**Tentación válida:** si LinkedIn auto-send es no-go, ¿por qué no email? Hunter.io o Apollo.io pueden encontrar email de cualquier reclutador.

**Razones para mantenerlo manual** en E9 también:
1. **Cold email tiene leyes anti-spam estrictas** (CAN-SPAM US, CASL Canada, GDPR EU). Para volumen bajo (10/semana) es manejable, pero requiere cuidado legal.
2. **Email frío de individuo a individuo es OK** legalmente; lo que viola es bulk send a listas no-opt-in. Mientras sea 1-a-1 con research específico, es legítimo.
3. **El sistema YA puede enviar email** (E5-S04 EmailNotifier). Pero la decisión deliberada en E9 es: el usuario hace copy-paste manual al cliente de email para mantener "human in the loop".

Si en el futuro rinde, agregar `jobhunter outreach send-email --message-id X` como story para E11 — usa el `EmailNotifier` ya existente, validation extra en compliance.

---

**Fin Documento M.**
