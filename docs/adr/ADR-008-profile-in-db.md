# ADR-008: Profile and CV Variants Live in DB, Not Files

## Status
Accepted (decisión tomada 2026-05-02; implementación pendiente en E14 — ver
`docs/Plan automatizado.../R_Backlog_Nivel_2_E14.md`).

## Context

Hasta hoy, el perfil del candidato y sus variantes de CV viven en **archivos
en disco**, distribuidos en tres lugares con tres mecanismos de carga
distintos:

| Artefacto | Ubicación | Quién lo lee |
|---|---|---|
| Perfil del candidato (formato yaml) | `prompts/candidate_profile.yaml` | `outreach/generator.py`, `outreach/scoring.py` |
| **Mismo perfil duplicado literal** dentro del prompt de scoring | bloque `candidate_profile:` embebido en `prompts/scoring/v1.md` | `scoring/scorer.JobScorer` |
| Variantes de CV en markdown | `.local/cv_variants/{ai_python,flutter,fullstack}.md` (gitignored) | `application/cv.load_cv()`, `cover_letter.py`, `cv_tweaks.py`, `ats_keywords.py` |

Esta organización tiene **tres problemas estructurales**:

1. **Duplicación de fuente de verdad.** El perfil aparece dos veces — una en
   `candidate_profile.yaml` (leído dinámicamente para outreach) y otra
   embebida dentro del prompt v1 de scoring. Cualquier cambio debe
   propagarse manualmente a los dos sitios. Es deuda técnica heredada del
   bootstrap (en E1/E2 la persistencia aún no estaba madura).
2. **El usuario es la única entidad de dominio que NO vive en BD.** Jobs,
   aplicaciones, contactos outreach, mensajes outreach, emails procesados,
   tokens OAuth y llamadas LLM tienen sus tablas y repos. El usuario,
   paradójicamente, es la entidad **más** central del sistema y vive en
   archivos sueltos.
3. **No hay audit trail ni history.** Cuando el usuario sube su `floor_usd_
   month` de $5500 a $6500 el 2026-04-15, nada en el sistema lo registra. Si
   un job scoreado el 2026-04-10 fue marcado tier B parcialmente porque
   estaba debajo del floor de entonces, esa decisión es irreproducible 6
   meses después.

Adicionalmente, durante el diseño de E14 (Onboarding Automation) se decidió
que el wizard de onboarding viviría en el dashboard web y que las variantes
de CV serían **user-defined** (no hardcoded a 3 nombres fijos). Ambas
decisiones son funcionalmente bloqueadas por la persistencia en archivo:

- Editar archivos desde una página Streamlit sin coordinación con git/
  filesystem es frágil y rompe el principio de "el dashboard no toca el
  filesystem fuera de outputs efímeros".
- Variantes user-defined con N arbitrario chocan con la lógica
  `if/else` hardcoded del `variant_selector` que conoce los 3 nombres fijos
  para mapear keywords del job → variant correcta.

## Decision

El perfil del candidato y sus variantes de CV se persisten en **PostgreSQL**
como entidades de primera clase, con esta estructura (schema híbrido —
columnas para campos queryables, `JSONB`/`TEXT[]` para flexibles):

```
candidate_profiles                 (1 row por perfil activo, multi-profile OK)
  └─ candidate_profile_history     (snapshot pre-cambio, vía trigger SQL)
  └─ cv_variants                   (N rows por perfil, user-defined names)
      └─ cv_variant_experiences    (M rows por variant, ordenadas)
```

Los consumidores actuales (`outreach/generator.py`, `outreach/scoring.py`,
`application/cv.py`, `application/cover_letter.py`, `application/cv_tweaks.py`,
`application/ats_keywords.py`, y `scoring/scorer.JobScorer`) se refactorizan
para leer de la BD vía `CandidateProfileRepo` y `CVVariantRepo`.

El prompt `prompts/scoring/v1.md` reemplaza su bloque `candidate_profile:`
embebido por un placeholder `{candidate_profile_yaml}` que el scorer rellena
en runtime con el yaml-equivalente del perfil cargado de BD (mismo patrón
que ya usan los prompts de outreach).

Los archivos `prompts/candidate_profile.yaml` y `.local/cv_variants/*.md`
existentes se importan automáticamente a la BD vía migration Alembic, y los
originales se archivan en `prompts/_legacy/{timestamp}/` (no se borran — el
usuario puede consultar/restaurar).

La implementación ocurre en la épica **E14 — Onboarding Automation &
Profile Generation** (11 stories, ~23h).

## Rationale

1. **Una sola fuente de verdad.** El perfil deja de estar duplicado entre
   yaml y prompt embebido. Cambiar el `floor_usd_month` o el `primary_stack`
   afecta a TODOS los consumidores en la siguiente operación, sin riesgo de
   olvidar un sitio.
2. **Audit trail nativo.** El trigger `BEFORE UPDATE` sobre
   `candidate_profiles` copia automáticamente el snapshot pre-cambio a
   `candidate_profile_history`, sin importar si el cambio vino del wizard,
   del CLI o de un `psql` directo. Combinado con `audit_log` (E13-S05), se
   puede responder "qué perfil tenía cuando este job fue scoreado".
3. **Multi-profile soportado naturalmente.** Permitir múltiples
   `is_active=true` en `candidate_profiles` habilita la "Estrategia C" de
   scoring por perfil que se discutió en la conversación previa
   (`Confirmación Épicas 7-12 Completadas Correctamente.md`). Sin BD, esto
   requeriría un sistema ad-hoc de directorios.
4. **Variants user-defined.** El `variant_selector` se reescribe para
   iterar sobre `cv_variants` cargados de BD y matchear por `target_role_
   keywords` + `target_stack` (metadata por row), no por `if name ==
   "ai_python"`. El usuario puede tener variants llamadas
   `python_backend`, `translator_es`, `ai_agent_consultant`, lo que sea.
5. **Wizard como UX principal habilitable.** Una página Streamlit que
   inserta/actualiza rows es trivial; una que coordina edits a yaml +
   markdowns + git pull/push es horrible. La BD desbloquea el flow
   conversacional de E14-S08.
6. **Backups cubiertos automáticamente.** El backup S3 (E12-S03) ya
   incluye toda la BD. Hoy el yaml + markdowns requerirían un proceso
   aparte (que no existe).
7. **Edit en vivo sin restart.** Cambiar el perfil desde el wizard se
   refleja en la siguiente llamada a scoring/outreach/cover-letter sin
   reiniciar servicios. Hoy un cambio al yaml requiere recargar el módulo
   o aceptar TTL del `lru_cache`.

## Consequences

### Pros

- Resuelve la deuda técnica del perfil duplicado.
- Elimina la inconsistencia "todas las entidades en BD excepto el usuario".
- Habilita E14 (wizard, multi-profile, variants user-defined,
  salary-proposer con datos reales en futuro).
- Cubierto por backup automático.
- Audit trail desbloqueado.

### Cons

- **Pérdida de diffability via `git diff`.** Un cambio al perfil ya no
  aparece como diff en un PR. *Contra-argumento:* el perfil contiene PII
  (nombre, salario, país); que NO esté en git history es deseable.
  `compliance export-data` (E13-S05) puede generar yaml para portabilidad/
  inspección puntual.
- **Migration de schema más pesada para cambios al perfil.** Añadir un
  campo nuevo requiere `alembic revision`, no editar yaml.
  *Contra-argumento:* la frecuencia esperada de cambios al schema es
  bajísima (¿una vez al año?). Los cambios al *contenido* del perfil son
  ligeros (un UPDATE).
- **Dependencia de Postgres en runtime.** Hoy el outreach generator carga
  el yaml en arranque y funciona sin DB. Tras E14, requiere DB activa.
  *Contra-argumento:* el resto del sistema ya requiere DB activa para
  funcionar.
- **Loss of "edit in your favorite editor"** workflow para usuarios que
  prefieren vim/VSCode. *Contra-argumento:* el wizard es la UX intencional;
  CLI `profile show > tmp.yaml && vim tmp.yaml && profile import tmp.yaml`
  cubre el caso de power user (story E14-S09).
- **Tests requieren DB seeded** con perfil mínimo en cada fixture.
  *Contra-argumento:* la mayoría ya requiere `db_session`; añadir
  `sample_candidate_profile` a `conftest.py` es trivial.

## Alternatives considered

- **Mantener yaml + markdowns, deduplicar via loader compartido.** Se
  consideró extraer el bloque `candidate_profile:` del prompt scoring v1.md
  a un loader común que también sirva al outreach. Resuelve la duplicación
  pero NO habilita audit, multi-profile robusto, ni wizard. Es
  semi-solución.
- **Hybrid: yaml authoritative + cache en BD.** Yaml sigue siendo fuente,
  pero un servicio carga al iniciar y cachea en BD. Pierde el wizard
  (cualquier edit del cache se sobrescribe en el próximo restart). No
  recomendado.
- **Otro storage (Redis, S3, KV-store).** Considerado y descartado: ya
  pagamos por Postgres, ya backupea, ya tiene audit trigger trivial. Sumar
  otro storage añade complejidad sin beneficio.

## Implementation reference

Ver `docs/Plan automatizado para búsqueda de trabajo remoto en Europa/R_Backlog_Nivel_2_E14.md`
para el desglose en 11 stories. La implementación es destructiva al modelo
de archivos pero no destructiva al usuario gracias a la migration legacy
(E14-S10) que importa automáticamente cualquier yaml/md preexistente.
