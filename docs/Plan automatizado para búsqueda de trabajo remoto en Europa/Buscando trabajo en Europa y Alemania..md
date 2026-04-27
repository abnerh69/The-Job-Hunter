# Buscando trabajo en Europa y Alemania.

Buen pedido. Te armo un plan ejecutable, pensado para tu perfil senior y aprovechando que tú mismo puedes construir buena parte de la automatización.

**Nota previa:** tu CV dice Medellín pero pides desde Venezuela. Estas son situaciones distintas para empresas EU (sanciones, EORs disponibles, métodos de pago). Decide cuál vas a usar como base "oficial" antes de empezar — recomiendo Colombia si tienes residencia, mucho menos fricción.

---

## Fase 0 — Decisiones estratégicas (antes de cualquier código)

Tres preguntas que debes responderte primero, porque condicionan todo lo demás:

1. **¿Modalidad de contratación?** Contratista B2B vs. empleado vía EOR (Deel, Remote.com, Velocity Global). Las empresas alemanas suelen ofrecer una de las dos, no ambas. Tu pipeline debe filtrar por esto.
2. **¿Stack prioritario?** Python/AI tiene mejor pago en EU que Flutter puro. Sugerencia: dos pipelines paralelos con scoring distinto, pero priorizar AI/Python.
3. **¿Overlap horario?** Venezuela (UTC-4) vs. Alemania (UTC+1/+2) = 5–6h de diferencia. Muchas ofertas EU exigen 4h+ de overlap CET. Define ahora hasta qué hora estás dispuesto a trabajar (¿16h venezolanas = 21h CET?). Esto descarta ~30% de ofertas de entrada.

Realidad de mercado: $4000 USD/mes (~€3700) es razonable-bajo para senior con tu experiencia en Alemania. El rango realista es €60–110k anuales. No te subvendas.

---

## Fase 1 — Preparación de activos (one-time, ~1 semana)

**Versiones de CV:** crea tres variantes manteniendo un mismo "core":

- CV-AI/Python (énfasis en SageMaker, LLMs, RAG, FastAPI, Dask)
- CV-Flutter (énfasis en cross-platform, Firebase, BLoC, métricas de impacto)
- CV-FullStack (balanceado)

**Templates de IA reutilizables:** redacta y guarda como archivos `.md` versionados:

- Prompt maestro para generar cover letter desde JD + CV
- Prompt para extraer requisitos críticos de una oferta (salario, timezone, visa, stack)
- Prompt para responder preguntas frecuentes de ATS (¿por qué nuestra empresa?, salary expectations, etc.)
- Mensaje LinkedIn frío para reclutadores (3 variantes: alemán/inglés/español)

**Perfiles optimizados:**

- LinkedIn: titular con keywords densas ("Senior Python/AI Engineer | LLMs · RAG · SageMaker · Flutter · Open to EU Remote"), Open to Work activado solo a reclutadores, ubicación en Colombia.
- GitHub: pin de 3–5 repos con READMEs decentes. Si construyes el sistema de búsqueda (ver Fase 7), ese mismo proyecto se vuelve un repo destacado.
- Cuenta en Honeypot.io, Wellfound, Otta, Arbeitnow.

---

## Fase 2 — Sistema de descubrimiento (automatizable, corre cada N días)

Fuentes que vale la pena consumir programáticamente para EU/DE remoto, en orden de señal:

- **Arbeitnow.com** — tiene API pública JSON, ideal para empezar
- **RemoteOK** — API JSON pública
- **WeWorkRemotely** — RSS feed
- **Wellfound (AngelList)** — scraping con cuidado
- **GermanTechJobs.de**
- **Honeypot.io** — funciona al revés (las empresas te buscan a ti); registro obligatorio
- **4dayweek.io**
- **LinkedIn** — el más importante pero el más antagónico al scraping; mejor RSS via servicios como `linkedin-jobs-rss` o uso manual con filtros guardados
- **Berlin Startup Jobs**, **JOIN.com**

**Filtros de descubrimiento (al ingerir):**

- Keywords positivos: `Python`, `Senior`, `AI/ML`, `Flutter`, `Remote`, `Worldwide`, `EU`, `Germany`
- Keywords negativos: `EU residents only`, `must be in {city}`, `on-site`, `relocation required`, `clearance required`
- Salario mínimo (cuando esté): $4000/mes equivalente

---

## Fase 3 — Filtrado con IA (Claude API)

Para cada oferta nueva ingestada, llamada a LLM con prompt estructurado que devuelve JSON:

```
{
  "fit_score": 0-100,
  "estimated_salary_usd": number | null,
  "timezone_requirement": "strict_CET" | "flexible_EU" | "any" | "americas_only",
  "venezuela_friendly": true | false | "unknown",
  "contract_type": "B2B" | "EOR" | "either" | "unknown",
  "red_flags": [string],
  "key_match_points": [string],
  "key_gaps": [string]
}
```

Solo las ofertas con `fit_score >= 70` y sin red flags duros pasan a Fase 4. Esto te ahorra 80% del tiempo.

---

## Fase 4 — Aplicación (semi-automatizada)

**Advertencia importante:** no uses auto-apply ciego (LazyApply, Sonara, Simplify). Para roles senior $4k+ EU, la calidad importa muchísimo más que el volumen. La tasa de respuesta cae a <1% con auto-apply, vs. 10–15% con aplicaciones cuidadas.

**Flujo recomendado por aplicación (5–10 min cada una):**

1. La IA genera borrador de cover letter usando JD + CV-variante adecuada
2. La IA sugiere qué tweaks hacer al CV (reordenar bullets, ajustar keywords para ATS)
3. Tú revisas, ajustas tono, agregas un detalle específico de la empresa (1 frase del about page)
4. Aplicas manualmente
5. El sistema registra todo automáticamente

**Excepción válida para automatizar:** 
LinkedIn Easy Apply usando Playwright con tu cuenta principal puede ser razonable, pero arriesgas restricción. Mejor hacerlo manualmente — son 30 segundos cada una.

**Bonus:** outreach proactivo a reclutadores. Cada lunes, lista de 10 reclutadores en Berlin/Munich/Hamburg con stack matching, mensaje personalizado generado por IA, envío manual. Esto históricamente convierte mejor que aplicar a ofertas.

---

## Fase 5 — Tracker (registro de propuestas)

Tabla con estos campos como mínimo:

| Campo | Tipo |
|---|---|
| id, fecha_aplicacion, empresa, puesto, url, fuente | meta |
| salario_min, salario_max, moneda | número |
| stack, modalidad (B2B/EOR), tz_requerida | enum |
| estado | enum: applied → screening → interview_1 → interview_n → offer → rejected → ghosted |
| proxima_accion, fecha_proxima_accion | tarea |
| fit_score, ai_notes | IA |
| contacto_reclutador, contacto_linkedin | string |
| follow_up_count, ultima_actualizacion | int/date |

**Opciones de implementación, ordenadas por esfuerzo:**

- **Notion** o **Huntr.co** — listo en 30 min, integraciones decentes
- **Airtable** — mejor para automatizaciones con webhooks
- **PostgreSQL + Streamlit dashboard custom** — mayor esfuerzo (un fin de semana), pero se vuelve portfolio piece y lo dominas

Dado tu perfil, la opción 3 es la que más jugo te da — el repo en sí es un argumento de venta.

---

## Fase 6 — Cadencia operativa

Esto es lo que ejecutas cada N días una vez todo está montado:

- **Diario (10 min):** revisar inbox + LinkedIn por respuestas, mover estados en tracker, agendar entrevistas.
- **Cada 2–3 días (45–60 min):** correr pipeline de descubrimiento, revisar matches IA con score >70, aplicar a 5–10 mejores con cover letters generadas.
- **Semanal (30 min):** outreach a 10 reclutadores nuevos, follow-up a aplicaciones de hace 7 días sin respuesta, revisar métricas.
- **Mensual:** análisis de tasa de respuesta por fuente/keyword, ajuste de filtros, A/B test de templates, actualización de CV con aprendizajes.

---

## Fase 7 — Stack del sistema (puedes construirlo tú)

Idea clave: este mismo sistema, bien hecho y open-source, es un proyecto que demuestra exactamente las skills que vendes. Lo pones en GitHub y lo mencionas en cover letters.

Stack sugerido:

- **API/orquestación:** FastAPI
- **Scraping:** httpx para APIs/RSS, Playwright para sitios JS-heavy
- **IA:** Anthropic API (Claude Sonnet 4.6 o Haiku 4.5 para scoring de bajo costo, Opus 4.7 para cover letters)
- **DB:** PostgreSQL
- **Scheduling:** Airflow (lo conoces) o GitHub Actions con cron — para empezar, GH Actions es gratis e infinitamente más simple
- **Dashboard:** Streamlit (rápido) o Flutter Web (luce tu stack)
- **Notificaciones:** bot de Telegram para alertas en tiempo real de matches con score >90

---

## Métricas de salud del sistema

Define umbrales para diagnosticar dónde está el problema cuando los resultados no llegan:

- Aplicaciones/semana: meta 25–40
- Tasa de respuesta: <5% indica problema de CV/perfil; 10–15% es saludable; >20% indica que estás aplicando muy bajo de tu nivel
- Tasa de entrevista→oferta: <20% indica problema de preparación de entrevistas
- Salario promedio ofertado: si <$4k, estás targeting empresas equivocadas

---

## Consideraciones específicas Venezuela

- Verifica métodos de pago aceptados antes de aplicar fuerte: prioriza empresas que paguen vía Deel, Remote.com, Wise o crypto. Algunas empresas EU rechazan contratistas en Venezuela por compliance (sanciones US/EU); detecta esto temprano.
- Si tienes residencia colombiana, úsala como base administrativa — elimina el 90% de la fricción.
- Fiscalmente: contratista internacional, declaración según país de residencia fiscal real.

---

¿Quieres que profundicemos en alguna fase específica? Lo más útil suele ser: (a) el prompt maestro de scoring/filtrado, (b) el esqueleto de código del sistema en FastAPI + GH Actions, o (c) el playbook de outreach a reclutadores alemanes. Dime cuál y la armamos.