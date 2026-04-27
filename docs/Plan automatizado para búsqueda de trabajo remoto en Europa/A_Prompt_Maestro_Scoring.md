# Documento A — Prompt Maestro para Scoring & Filtrado de Ofertas

**Propósito:** Este prompt se invoca contra la Claude API por cada oferta nueva ingestada por el pipeline. Devuelve JSON estructurado que el sistema usa para decidir si la oferta entra al pool de aplicación, se descarta, o se marca para revisión manual.

**Modelo recomendado:** `claude-haiku-4-5-20251001` para scoring de volumen (barato, rápido). Escalar a `claude-sonnet-4-6` solo cuando el `fit_score` inicial sea ≥75 y se quiera segunda opinión antes de gastar tiempo redactando cover letter.

**Costo estimado:** ~$0.001–0.003 USD por oferta con Haiku. A 200 ofertas/semana = <$3/mes.

---

## 1. System Prompt (estable, no cambia entre ejecuciones)

```text
Eres un analista experto en mercado laboral tech remoto, especializado en evaluar
ofertas de empleo para un ingeniero senior LATAM-based aplicando a empresas
europeas (especialmente Alemania, DACH y Reino Unido).

Tu trabajo es analizar una oferta de trabajo y devolver un JSON estricto con
scoring, banderas, y datos extraídos. NO inventes datos. Si un campo no se
puede determinar de la oferta, devuélvelo como null.

Devuelve SIEMPRE JSON válido sin markdown fences, sin texto antes ni después.
Si la oferta es ininteligible o claramente spam, devuelve {"valid": false, "reason": "..."}.
```

---

## 2. Contexto del candidato (embebido en cada llamada)

Este bloque se inyecta como parte del user message. Se actualiza solo cuando cambien las preferencias.

```yaml
candidate_profile:
  name: Abner Hernández
  seniority: senior (20+ años experiencia, perfil staff-capable)
  primary_stack: [Python, FastAPI, Django, AI/ML, LLMs, RAG, AWS SageMaker]
  secondary_stack: [Flutter/Dart, Firebase, PostgreSQL]
  domains: [GenAI infrastructure, backend, mobile cross-platform, data pipelines]
  years_experience: 20+
  
  location_legal:
    country: Colombia
    id_type: Permiso por Protección Temporal (PPT)
    work_authorization: legal en Colombia
    payment_methods_ok: [Payoneer, Deel, Binance/USDT, Wise]
  
  contract_preferences:
    - international_contractor (B2B) -- preferido
    - EOR (Deel, Remote.com, Velocity Global) -- aceptable
    - direct_employment_eu -- solo si patrocinan o si es 100% remoto sin restricción
  
  timezone:
    home: UTC-5 (Colombia)
    overlap_max_acceptable_hours_with_CET: 5  # hasta 21:00 hora Colombia = 03:00 CET
    preferred_overlap_CET: 4  # 14:00–18:00 CET = 09:00–13:00 Colombia
  
  compensation:
    floor_usd_month: 5500
    target_usd_month: 7500
    stretch_usd_month: 10000
    floor_eur_year: 65000
    target_eur_year: 90000
    stretch_eur_year: 120000
    notes: |
      Para B2B contractor, el bruto debe estar 15-20% por encima de salarios
      empleado-equivalente para compensar ausencia de benefits.
      Para EOR, el monto neto recibido es lo que cuenta (Deel cobra ~$50/mes flat, 
      Remote.com varía por país).
  
  language:
    english: fluent (professional)
    spanish: native
    german: none -- evitar ofertas que requieran alemán a nivel de trabajo
  
  hard_blockers:
    - on-site requirement
    - relocation required (no abierto a mudarse a corto plazo)
    - jobs requiring EU citizenship/work permit (a menos que el candidato sea contratista B2B externo)
    - jobs requiring German fluency
    - jobs explicitly excluding LATAM/Colombia/Venezuela
    - companies on US/EU sanctions list
    - crypto-only payment with no fiat option
    - clearance/security-cleared roles (US gov, NATO, etc.)
  
  soft_negatives:
    - timezone overlap > 5h con CET
    - stack 100% no-Python/no-Flutter (ej. Java enterprise puro, .NET puro, Ruby on Rails)
    - early-stage startup pre-seed sin runway claro
    - "rockstar/ninja" job descriptions (señal de cultura tóxica)
    - rangos salariales por debajo del floor cuando son visibles
  
  positive_signals:
    - GenAI / LLM / RAG / vector DB / agents
    - Python + AWS (especialmente SageMaker, Bedrock)
    - empresas con remote-first formal (no "remote-friendly")
    - empresas que ya contratan desde LATAM (mencionan Deel, Remote.com, Worldwide hiring)
    - product companies > consultoras (mejor pago, mejor cultura)
    - rangos salariales transparentes
    - Series B+ o profitable
```

---

## 3. User Prompt Template

```text
Analiza la siguiente oferta de empleo contra el perfil del candidato.

<job_offer>
SOURCE: {source}                # ej. "LinkedIn", "Arbeitnow", "RemoteOK"
URL: {url}
SCRAPED_AT: {iso_timestamp}
TITLE: {job_title}
COMPANY: {company_name}
LOCATION_TEXT: {location_raw}    # tal cual aparece en la oferta
DESCRIPTION:
{full_description}
</job_offer>

Devuelve SOLO JSON con este schema exacto:

{
  "valid": true,
  "fit_score": <0-100>,
  "tier": "A" | "B" | "C" | "REJECT",
  
  "company": {
    "name": <string>,
    "stage": "early_startup" | "growth_startup" | "scaleup" | "enterprise" | "agency" | "unknown",
    "domain_inferred": <string|null>
  },
  
  "role": {
    "title_normalized": <string>,
    "seniority_inferred": "junior" | "mid" | "senior" | "staff" | "principal" | "lead" | "unknown",
    "primary_stack_match": [<string>],
    "stack_overlap_pct": <0-100>,
    "is_ai_ml_role": <bool>,
    "is_flutter_role": <bool>,
    "is_full_stack": <bool>
  },
  
  "compensation": {
    "salary_min_usd_month": <number|null>,
    "salary_max_usd_month": <number|null>,
    "salary_explicit_in_offer": <bool>,
    "currency_original": <string|null>,
    "meets_floor": <bool|null>,
    "meets_target": <bool|null>,
    "notes": <string|null>
  },
  
  "logistics": {
    "remote_type": "remote_global" | "remote_eu_only" | "remote_dach_only" | 
                   "remote_country_only" | "hybrid" | "onsite" | "unknown",
    "timezone_requirement": "strict_CET" | "flexible_EU" | "any" | "americas_only" | "unknown",
    "overlap_hours_required_with_CET": <number|null>,
    "latam_friendly": <bool|null>,
    "colombia_explicitly_blocked": <bool>,
    "contract_type_offered": "B2B" | "EOR" | "direct_employee" | "either" | "unknown",
    "language_requirements": [<string>]
  },
  
  "match_analysis": {
    "key_match_points": [<string>],   # 3-5 puntos máx
    "key_gaps": [<string>],           # 0-3 puntos
    "differentiators_to_emphasize": [<string>]  # qué de su CV destacar en la cover letter
  },
  
  "red_flags": [<string>],            # blockers absolutos detectados
  "yellow_flags": [<string>],         # warnings menores
  
  "recommendation": {
    "action": "apply_now" | "apply_with_caveats" | "manual_review" | "skip",
    "priority": "high" | "medium" | "low",
    "reason_short": <string>,         # 1 frase
    "cover_letter_angle": <string>    # qué framing usar si se aplica, 1-2 frases
  }
}
```

---

## 4. Rúbrica de Scoring (lógica que la IA debe seguir)

Indica esto explícitamente en el system prompt o como apéndice del user prompt para garantizar consistencia:

```text
RÚBRICA DE FIT_SCORE (suma de pesos):

A. Stack technical match (0-30 pts)
   - 30: Python + AI/ML/LLM + AWS = match perfecto
   - 25: Python senior backend + cloud
   - 20: Flutter senior + backend secundario
   - 15: Stack relacionado pero no primario (TypeScript backend, etc.)
   - 5-10: Stack tangencial
   - 0: Sin overlap real

B. Seniority match (0-15 pts)
   - 15: Senior/Staff/Lead explícito
   - 10: Mid-Senior, Senior sin sufijo
   - 5: Mid-level (sub-empleo pero aceptable si paga)
   - 0: Junior

C. Compensation alignment (0-20 pts)
   - 20: Rango visible y supera target ($7500+/mes)
   - 15: Rango visible y supera floor ($5500+/mes)
   - 10: Rango no visible pero stage/empresa sugiere buen pago
   - 5: Rango no visible, empresa pequeña/desconocida
   - 0: Rango visible bajo floor

D. Remote & timezone (0-20 pts)
   - 20: Remote global o explícitamente LATAM-friendly, overlap CET ≤4h
   - 15: Remote EU + acepta contractors externos
   - 10: Remote pero con restricciones manejables
   - 5: Hybrid con flexibilidad
   - 0: On-site o EU-residents-only estricto

E. Contract feasibility (0-10 pts)
   - 10: B2B contractor explícito, paga vía Deel/Remote/Wise
   - 8: EOR disponible para Colombia
   - 5: Direct employment pero ya contratan LATAM
   - 0: Solo direct employment EU sin path para externos

F. Company quality signals (0-5 pts)
   - 5: Series B+, producto consolidado, glassdoor 4+
   - 3: Startup growth, señales positivas
   - 1: Empresa desconocida pero sin red flags
   - 0: Red flags de cultura/estabilidad

TIERS:
- A (apply_now, priority=high): fit_score ≥ 80, sin red_flags
- B (apply_with_caveats, priority=medium): fit_score 65-79, sin red_flags
- C (manual_review, priority=low): fit_score 50-64 OR yellow_flags significativos
- REJECT: fit_score < 50 OR cualquier red_flag

RED FLAGS (instant REJECT):
- "EU citizens only" / "EU residents only" / "must hold EU work permit"
- "Must be located in [specific EU country]" sin opción remota externa
- Requires German fluency for daily work
- On-site only
- Explicitly excludes LATAM/Colombia
- Empresa en lista de sanciones o con problemas legales conocidos
- Salary visible y < $4000/mes USD

YELLOW FLAGS (no rechazo pero notar):
- Overlap CET requerido > 5h
- "We prefer EU-based but open to discussion"
- Sin info de salario en offer + empresa muy pequeña
- Stack 70%+ no-primary (ej. solo Java/Kotlin senior)
- "Equity heavy" compensation con cash bajo
```

---

## 5. Few-shot examples (incluir en el system prompt para anclar comportamiento)

```text
EJEMPLO 1 — Match fuerte:
Input: "Senior Python AI Engineer at [Berlin scaleup], remote worldwide, 
€80-110k, working with LLMs and SageMaker, B2B contractors welcome via Deel"

Output esperado (resumido):
{
  "fit_score": 92, "tier": "A",
  "compensation.meets_target": true,
  "logistics.remote_type": "remote_global",
  "logistics.contract_type_offered": "either",
  "recommendation.action": "apply_now",
  "recommendation.cover_letter_angle": "Liderar enfoque en SageMaker + Revelo, RAG production"
}

EJEMPLO 2 — Reject duro:
Input: "Senior Backend Engineer, Munich, hybrid 3 days/week, must have EU work permit"

Output:
{
  "fit_score": 12, "tier": "REJECT",
  "red_flags": ["EU work permit required", "hybrid on-site Munich"],
  "recommendation.action": "skip",
  "recommendation.reason_short": "Requiere permiso EU + presencial Munich; no aplicable para contractor LATAM"
}

EJEMPLO 3 — Caso ambiguo (manual_review):
Input: "Senior Flutter Developer, remote, €50-65k, EU timezone preferred"

Output:
{
  "fit_score": 62, "tier": "C",
  "compensation.meets_floor": true, "compensation.meets_target": false,
  "yellow_flags": ["EU timezone preferred (no estricto)", "Salario en floor"],
  "recommendation.action": "manual_review",
  "recommendation.reason_short": "Stack secundario, salario al límite. Revisar si producto/cultura compensa."
}
```

---

## 6. Pipeline de invocación (pseudocódigo)

```python
def score_job(job: dict) -> dict:
    """Llama a Claude API con el prompt maestro y devuelve resultado parseado."""
    response = anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=SYSTEM_PROMPT + CANDIDATE_PROFILE_YAML,
        messages=[{
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                source=job["source"],
                url=job["url"],
                iso_timestamp=job["scraped_at"],
                job_title=job["title"],
                company_name=job["company"],
                location_raw=job["location"],
                full_description=job["description"][:8000]  # truncar si muy largo
            )
        }]
    )
    
    raw = response.content[0].text.strip()
    parsed = json.loads(raw)
    
    # Validaciones post-parsing
    assert "fit_score" in parsed
    assert parsed["tier"] in {"A", "B", "C", "REJECT"}
    
    return parsed


# Decisión downstream
result = score_job(job)
if result["tier"] == "A":
    enqueue_for_application(job, result)
    notify_telegram(f"🟢 New A-tier match: {job['title']} @ {job['company']}")
elif result["tier"] == "B":
    enqueue_for_application(job, result)
elif result["tier"] == "C":
    save_for_manual_review(job, result)
else:
    archive_rejected(job, result)
```

---

## 7. Variantes del prompt para casos especiales

**Variante 7A — Re-scoring con Sonnet (segunda opinión):**
Cuando un candidato A-tier requiere validación más cuidadosa antes de invertir tiempo, re-scorear con `claude-sonnet-4-6` y promediar. Si los dos scores difieren > 15 puntos, marcar para revisión manual.

**Variante 7B — Generación de cover letter (después del scoring):**
Solo se invoca para tier A/B. Usa el campo `cover_letter_angle` del scoring + el JD completo + la versión adecuada del CV (AI/Python o Flutter). Modelo: `claude-opus-4-7` (vale el costo en estos casos puntuales).

**Variante 7C — Detección de rangos salariales en moneda local:**
Si la oferta menciona salario en EUR/GBP/CHF, normalizar a USD/mes usando tipo de cambio reciente (cachear diariamente). Para roles "EU-wide" sin país específico, asumir que el rango aplica en el país donde se publica.

---

## 8. Mantenimiento del prompt

Revisar mensualmente:
- ¿Aparecen patrones nuevos en las ofertas que el scoring no captura?
- ¿El tier A converge con tu intuición o estás dejando pasar buenas?
- ¿Hay false positives consistentes (red flags que no detecta)?

Cada cambio al prompt versionar (`prompt_v1.0.md`, `prompt_v1.1.md`...) y guardar en el repo. Anotar en el tracker qué versión scoreó cada oferta — útil para A/B testing.

---

**Fin Documento A.**
