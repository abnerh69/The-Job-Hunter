# Documento C — Playbook de Outreach a Reclutadores Alemanes/Europeos

**Propósito:** Estrategia complementaria al sistema de aplicación reactivo (Documento B). El outreach proactivo a reclutadores especializados históricamente convierte mejor (10–15% respuesta) que aplicar a JDs públicos en frío (5–10%), porque saltas el ATS y entras directo a la conversación humana.

**Objetivo de volumen:** 10 mensajes nuevos por semana a reclutadores curados + follow-ups apropiados. Esto mantiene un pipeline saludable de "warm leads" sin saturar tu calendario.

**Tiempo estimado por semana:** 60–90 minutos bien distribuidos.

---

## 1. Mapa del mercado de reclutamiento tech europeo

Tres tipos de reclutadores a distinguir (cada uno requiere abordaje distinto):

### 1.1 In-house tech recruiters
Trabajan dentro de la empresa target. Velocidad media, conocimiento profundo del producto.

- **Cómo identificarlos:** título "Tech Recruiter at [Company]", "Talent Acquisition Engineering at [Company]".
- **Mejor abordaje:** mensaje específico sobre la empresa + por qué encajas.
- **Pros:** sin comisión de por medio = empresa más dispuesta a negociar salario.
- **Contras:** solo te ayudan si tienen vacante abierta justo ahora.

### 1.2 Agencias especializadas en tech (boutique)
Empresas pequeñas-medianas centradas en perfiles técnicos senior. Las mejores tienen relaciones cercanas con CTOs.

- **Lista de boutique alemanas/EU notables (verifica al hacer outreach):** Honeypot (parte de New Work SE), Talently, Robert Walters Tech, Hays Technology, Michael Page Technology, Codeworks, Workmotion (focus Spanish-speaking), Riverbed Technology.
- **Cómo identificarlos:** títulos como "Senior Tech Recruiter at [Agency]", LinkedIn dice "Recruiting at [Boutique]".
- **Pros:** representan múltiples empresas, te pueden circular.
- **Contras:** comisión sale del salario (típicamente 15-25% del primer año), lo que a veces presiona el rango hacia abajo.

### 1.3 Plataformas reverse-recruiting
Tú creas perfil, ellos te traen ofertas. Filtran calidad de manera estructural.

- **Honeypot.io** (Berlin-based, fuerte en DACH, top tier) — hacen interview técnico y luego empresas pujan por ti.
- **Talent.io** (París, fuerte en Francia y EU).
- **Hired.com** (más US pero opera en EU).
- **Otta.com** / **Welcome to the Jungle** — más curado que LinkedIn para EU tech.

**Recomendación:** crea perfil en Honeypot **primero** (mejor ROI tiempo/oportunidad para tu perfil senior + AI). El proceso de onboarding toma una tarde.

---

## 2. Cómo encontrar buenos reclutadores

### 2.1 Búsqueda estructurada en LinkedIn

Filtros LinkedIn (cada combinación es una "búsqueda guardada" que revisas 1×/semana):

```
A. Reclutadores in-house en empresas target
   Title: "Tech Recruiter" OR "Talent Acquisition" OR "Engineering Recruiter"
   Company: [lista de empresas DACH AI-friendly — ver §2.2]
   Location: Germany OR Netherlands OR Switzerland OR Austria
   Posted in last 30 days: ✅ (asegura cuenta activa)

B. Reclutadores boutique especializados
   Title: "Senior Tech Recruiter" OR "Python Recruiter" OR "AI Recruiter" OR "ML Recruiter"
   Industry: Staffing & Recruiting
   Location: Germany OR Berlin OR Munich OR Hamburg

C. CTOs / Heads of Engineering en empresas target (outreach senior-to-senior)
   Title: "CTO" OR "VP Engineering" OR "Head of Engineering" OR "Engineering Manager"
   Company: [empresas target]
   Location: Germany / EU
   2nd connections preferred (warm intro posible)
```

### 2.2 Empresas alemanas/DACH AI-friendly con historial de hiring remoto LATAM

Esta lista debe verificarse al momento (las empresas cambian políticas). Como punto de partida, son conocidas por contratar remoto-global o LATAM-friendly:

- **Berlin tech scaleups:** N26, Trade Republic, Personio, Pitch, Contentful, Zalando Tech, GetYourGuide, HelloFresh Technology, Delivery Hero, Klarna (Berlin office).
- **AI/ML focused (DACH):** Aleph Alpha, DeepL, Helsing, Black Forest Labs, Synthesia (UK pero DACH-adjacent), Mistral (FR/DE presence), Parloa.
- **Remote-first explícito:** Doctolib, JOIN.com, Kontent.ai, Pipedrive.
- **Tech consultancies con clientes DACH:** Thoughtworks (DE), TNG Technology Consulting.
- **Fintech alemán:** SumUp, Solaris, Raisin, Mambu.

Para cada empresa target, mantén ficha en `outreach_contacts` (ver Documento B §4.1) con: nombre, score de fit, reclutadores in-house identificados, status.

### 2.3 Otras plataformas para identificar reclutadores

- **Xing:** red profesional dominante en DACH (más que LinkedIn en Alemania para perfiles ≥35 años). Perfil Xing en alemán básico es plus, pero perfil en inglés también funciona para roles tech.
- **Honeypot.io:** los reclutadores te encuentran a ti.
- **GitHub:** reclutadores que comentan en proyectos AI/Python. Perfil tuyo limpio + algún repo público señalado en pin atrae outreach inbound.

---

## 3. Templates de mensajes

**Principio guía:** corto, específico, con call-to-action claro y un detalle que demuestre que el mensaje no es plantilla. La IA (Claude) genera el draft; tú añades 1 frase concreta sobre la persona/empresa.

### 3.1 Template A — Reclutador in-house (cold, en LinkedIn)

```
Asunto / primera línea: Senior Python/AI Engineer interesado en {Empresa}

Hola {Nombre},

Soy ingeniero senior con 20+ años en backend Python y los últimos años centrado 
en GenAI infrastructure (LLMs, RAG, AWS SageMaker — actualmente como consultor 
para Amazon SageMaker vía Revelo).

Vi que {Empresa} está {detalle específico: "expandiendo el equipo de ML 
platform" / "trabajando en X producto" / "buscando Python seniors según 
job board"}, y me interesa conversar.

Trabajo desde Colombia como contratista internacional (B2B vía Deel/Payoneer), 
con overlap completo con horario CET hasta las 18:00 hora alemana. Stack 
actual: Python, FastAPI, SageMaker, Dask, Pandas, Docker.

¿Tendría sentido una llamada de 15 min esta semana o la próxima?

Gracias,
Abner Hernández
{linkedin URL}
```

**Notas:**
- Abre con valor (años + especialidad concreta), no con "soy senior buscando trabajo".
- "Detalle específico" es **obligatorio** — investiga 30 seg en la página de la empresa o en su LinkedIn antes de enviar.
- Mencionar B2B + Deel + overlap CET preempta tres preguntas habituales de reclutadores DACH.
- No menciones salario en el primer mensaje (eso destruye conversión); lo dejas para la screening call.

### 3.2 Template B — Reclutador boutique / agencia

```
Hola {Nombre},

Vi tu perfil — veo que trabajas con {empresas/sector específico de su pipeline}.

Soy ingeniero senior con foco en Python, AI/ML (LLMs, RAG, SageMaker) y 
también experiencia sólida en Flutter cross-platform. 20+ años en software, 
actualmente trabajando con Amazon SageMaker como consultor vía Revelo.

Estoy explorando posiciones senior remotas con empresas EU (especialmente 
DACH). Trabajo legalmente desde Colombia como contratista internacional. 
Compensación target en el rango de mercado para senior AI/Python en EU.

¿Tienes algún rol abierto que pueda encajar? Adjunto CV.

Saludos,
Abner Hernández
```

**Notas:**
- Con boutique, sé más explícito sobre compensación esperada ("rango de mercado") porque ellos toman fees y necesitan filtrar rápido.
- Adjunta CV en el primer mensaje (en plataforma diferente a LinkedIn donde hay límite de longitud, divides en 2 mensajes).
- Si no responden en 10 días, **un solo** follow-up; después marcar `ghosted` y mover.

### 3.3 Template C — CTO / Engineering Manager (warm intro o 2nd connection)

```
Hola {Nombre},

Me llamó la atención {detalle muy específico: "tu post sobre evaluación de 
LLMs en producción" / "el work que hicieron en {producto}" / "tu charla en 
{conferencia}"}.

Soy ingeniero senior Python/AI, actualmente con Amazon SageMaker (LLM 
training pipelines, RAG components). Leí que {Empresa} está {detalle de 
tracción/proyecto}.

No sé si están hiring directamente, pero quería ponerme en tu radar para 
roles senior en ML platform / Python backend. Trabajo desde Colombia como 
contratista (B2B) con overlap CET completo.

¿Habrá apetito por una llamada de 15 min, o me puedes referir con quien 
maneje hiring en tu equipo?

{firma}
```

**Notas:**
- Este template **requiere investigación real** — 5-10 min por persona. No funciona como volumen.
- Mejor target: 2 mensajes/semana de este tipo a personas que de verdad admiras o cuya empresa te interesa muchísimo.
- Tasa de respuesta esperada: 25-40% (mucho más alta que A o B), pero por baja escala.

### 3.4 Follow-up template (7-10 días después, una sola vez)

```
Hola {Nombre},

Solo para retomar mi mensaje anterior — entiendo que estás ocupado/a.

Si no es buen momento o no hay match ahora mismo, perfecto. Si quieres 
mantenerme en el radar para futuros roles, me puedes seguir o conectar.

Gracias por tu tiempo,
Abner
```

**Reglas estrictas:**
- **Nunca** tres mensajes sin respuesta. Es contraproductivo y daña tu marca.
- El follow-up explícitamente da una salida ("si no es buen momento") — esto incrementa tasa de respuesta.

### 3.5 Template D — Respuesta a primera reacción positiva

```
Genial, gracias por responder.

Adjunto mi CV en PDF. Algunos highlights relevantes para {Empresa}:
- {bullet 1: impacto medible}
- {bullet 2: stack overlap}
- {bullet 3: cualquier signal único — proyecto open source, charla, etc.}

Disponible para llamada esta semana — {2-3 slots concretos en la zona horaria 
del recruiter}. ¿Cuál te conviene?

Saludos,
Abner
```

**Notas:**
- Ofrece slots concretos en **su** zona horaria (CET), no la tuya. Calcula y escribe en hora local del recruiter.
- 3 bullets máximo — el CV ya tiene el detalle.

---

## 4. Cadencia operativa semanal

```
LUNES (45 min)
├── 09:00–09:15: Revisar inbox LinkedIn + email; mover responses al tracker
├── 09:15–09:30: Identificar 5 reclutadores nuevos (búsqueda LinkedIn guardada)
├── 09:30–10:00: Enviar 5 mensajes (Template A o B según corresponda),
│                con detalle específico generado IA-asistido + edit manual

MIÉRCOLES (30 min)
├── 09:00–09:15: Identificar 5 reclutadores adicionales
├── 09:15–09:30: Enviar 5 mensajes más

VIERNES (15 min)
├── Follow-ups a mensajes enviados hace 7-10 días sin respuesta (Template del §3.4)
├── Auto-marcar como "ghosted" los outreach > 21 días sin respuesta

SÁBADO (opcional, 30 min)
├── Outreach senior-to-senior (Template C) a 2 personas. Calidad >> volumen.
```

**Volumen total/semana:** ~12-15 mensajes nuevos + follow-ups. Después de 8 semanas tendrás 100+ contactos en pipeline.

---

## 5. Notas culturales para el mercado alemán/DACH

Los pequeños detalles importan. La cultura tech alemana tiende a ser más formal y directa que la US/LATAM:

- **Saludo:** "Hallo {Vorname}" en alemán o "Hello {First name}" en inglés. Evita "Hey" o "What's up".
- **Despedida:** "Beste Grüße" (alemán) o "Best regards" / "Kind regards". Evita "Cheers" en primera comunicación.
- **Tono:** directo y factual. Los superlatives ("amazing experience working on cutting-edge AI") suenan inflados a oídos alemanes; prefieren métricas concretas.
- **Idioma del primer mensaje:** inglés está bien para roles tech. Si tu alemán es nulo (como el tuyo), no intentes 2 frases en alemán mal escritas — peor señal que escribir todo en inglés.
- **Negotiation style:** alemán/holandés/suizo tienden a hacer una oferta cercana a la final. Margen de negociación menor que en mercados US (5-10%, no 20%).
- **Speed:** procesos formales más lentos que en US. Una respuesta a los 2 semanas es normal, no rechazo.
- **Probationary period:** "Probezeit" de 6 meses es estándar incluso para contractors B2B (cancelable con 2 semanas de aviso). Esto es normal — no señal roja.
- **Vacaciones:** si te ofrecen rol como empleado (vía EOR), 25-30 días de vacaciones es estándar, no perk especial.
- **References:** alemanes piden referencias y revisan exhaustivamente. Ten 2-3 references listos (idealmente uno en inglés).

### Reino Unido específicamente
- Más casual que DACH ("Hi" funciona).
- Procesos más rápidos.
- IR35 (legislación contratistas UK) puede aplicar — para B2B externo no-UK no debería, pero verifica.

### Holanda específicamente
- 30% ruling es solo para residentes. No aplica a ti como contractor externo.
- Mucha más apertura a remoto-LATAM que Alemania.

---

## 6. Asistencia IA en outreach (integración con sistema del Documento B)

El módulo `outreach/message_gen.py` debe ofrecer:

```python
def generate_outreach_message(
    contact: dict,        # nombre, empresa, role, linkedin
    template_type: str,   # 'A_inhouse' | 'B_boutique' | 'C_senior' | 'followup'
    research_notes: str,  # detalle específico que tú le pasas (1-2 frases)
    candidate_profile: dict
) -> str:
    """
    Genera el mensaje personalizado usando Claude Sonnet 4.6.
    Devuelve borrador listo para edit manual + send.
    """
    ...
```

**Flujo recomendado:**

1. Identificas al reclutador en LinkedIn → 30 segundos en su perfil.
2. CLI: `jobhunter outreach draft --contact <name> --type A_inhouse --note "Vi que postearon para Senior Python ML hace 3 días"`.
3. La IA genera el borrador en 2 segundos.
4. Tú revisas, ajustas tono, envías. Tiempo total: ~3 min/mensaje.

**Importante:** **revisa siempre antes de enviar.** Los reclutadores detectan mensajes IA-only fácilmente. El template debe sentirse como tú escribiendo con asistencia, no la IA escribiendo por ti.

---

## 7. Métricas y mejora continua

Trackear semanalmente en el dashboard (Documento B §4.1, tabla `outreach_contacts`):

| Métrica | Target sano | Acción si no se cumple |
|---|---|---|
| Mensajes enviados/semana | 10–15 | Si <10: aumentar tiempo de búsqueda LinkedIn |
| Tasa de respuesta inicial | 10–20% | Si <10%: revisar template, personalización, target audience |
| Tasa de respuesta a follow-up | 5–10% adicional | Si 0%: dejar de hacer follow-ups, pierde tiempo |
| Conversión a llamada | 30–50% de respuestas | Si <30%: revisar mensaje de respuesta (Template D) |
| Conversión llamada → proceso real | 30–50% | Si <30%: refinar pitch verbal |

**Re-calibración cada 4 semanas:**

- ¿Qué template tiene mejor tasa? Replicar approach.
- ¿Qué tipo de empresa responde más? Doblar apuesta ahí.
- ¿Hay segmentos sin tracción (ej. "AI startups Berlin <50 personas")? Eliminarlos del pipeline.

---

## 8. Errores comunes a evitar

1. **Plantillas obvias:** mensaje genérico = ignored. Siempre 1 frase específica del receptor.
2. **Spam masivo en LinkedIn:** 50 mensajes/día activa filtros, baja deliverability y tu cuenta puede ser restringida.
3. **Mencionar salario primero:** te descalifica antes de la screening call. Espera a que ellos pregunten.
4. **Tono desesperado:** "I really need a job" o "open to anything" señaliza red flag al reclutador.
5. **CV no actualizado:** asegura que el CV que mandas refleja exactamente las skills del JD donde aplicas.
6. **No medir:** si no trackeas tasa de respuesta por template, no puedes optimizar.
7. **Triple follow-up:** dos toques máximo, después dejar ir.
8. **Mismo mensaje a in-house y agencia:** sus incentivos son distintos; tu mensaje debe reflejarlo.

---

## 9. Ramp-up sugerido (primeras 4 semanas)

**Semana 1:** Setup

- Crear perfil Honeypot, completar interview técnico.
- Optimizar LinkedIn (titular, About, Featured con 2-3 proyectos).
- Crear perfil Xing en inglés.
- Crear las 3 búsquedas LinkedIn guardadas (§2.1).
- Identificar primeros 20 reclutadores target (mix in-house + boutique).

**Semana 2:** Primer batch

- 10 mensajes Template A/B.
- Empezar a poblar `outreach_contacts` en el sistema.
- Configurar comando IA-asistido `jobhunter outreach draft`.

**Semana 3:** Cadencia normal

- 12 mensajes nuevos + primeros follow-ups.
- 2 mensajes Template C a personas senior (curado).

**Semana 4:** Primera revisión

- Calcular tasa de respuesta por template.
- Decidir qué replicar y qué cambiar.
- Si tasa muy baja: revisar perfil LinkedIn (suele ser el culpable).

---

## 10. Recursos rápidos

- **LinkedIn Premium Career trial:** 1 mes gratis, te da InMail credits y mejor visibility en búsquedas. Vale la pena para el primer mes de outreach.
- **Hunter.io / Apollo.io:** para encontrar emails directos de reclutadores cuando LinkedIn no responde. Free tier suficiente para tu volumen.
- **Calendly:** comparte link en Template D para reducir fricción de scheduling. Configura disponibilidad en hora CET por defecto para reclutadores DACH.
- **Loom:** un video de 60 segundos de presentación personalizada (para targets muy importantes — Template C) puede multiplicar tasa de respuesta. Úsalo selectivamente.

---

**Fin Documento C.**
