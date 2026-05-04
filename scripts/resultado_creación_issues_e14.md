/bin/bash "/Users/abnershernandez/Dev/ashware/Job Hunter EU/scripts/create_issues_E14.sh"
(jobhunter) scripts $ /bin/bash "/Users/abnershernandez/Dev/ashware/Job Hunter EU/scripts/create_issues_E14.sh"
Auto-descubriendo OPT_EPIC_E14 desde el Project...
  ✓ OPT_EPIC_E14 = 48fed495

Verificando/creando labels necesarios...
✓ Label "epic:E14" created in Informatica-ASHware/Job-Hunter-EU
  ✓ Label creado: epic:E14
✓ Label "component:onboarding" created in Informatica-ASHware/Job-Hunter-EU
  ✓ Label creado: component:onboarding
✓ Label "component:profile" created in Informatica-ASHware/Job-Hunter-EU
  ✓ Label creado: component:profile
  ✓ Label creado: status:ready
  ✓ Label creado: type:refactor
  ✓ Label creado: type:infra
  ✓ Label creado: component:dashboard

============================================================
 Generador de Backlog Job-Hunter-EU — Épica E14 (Onboarding)
 Repositorio: Informatica-ASHware/Job-Hunter-EU | Proyecto: #2
============================================================

Creando issue: [E14-S01] Schema BD: candidate_profiles + history + cv_variants + experiencias
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/204
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S02] ResumeIngestor: parser de CV con LLM (PDF/MD/DOCX → ResumeData)
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/205
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S03] ProfileGenerator: ResumeData + inputs → candidate_profiles
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/206
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S04] CVVariantGenerator: variants user-defined
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/207
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S05] SalaryProposer: rango salarial con rationale
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/208
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S06] Refactor variant_selector para variants arbitrarias
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/209
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S07] Refactor cross-épica: scoring/outreach/application leen perfil de DB
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/210
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S08] Wizard dashboard: pages/0_🎯_Onboarding.py (7 pasos + edit mode)
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/211
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S09] CLI profile bootstrap: alternativo para power users
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/212
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S10] Migration legacy: yaml + markdowns → BD
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/213
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E14-S11] Tests E2E + Playwright wizard + actualización de docs (HUMAN_SETUP, CLAUDE, ARCHITECTURE)
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/214
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.

============================================================
 PROCESO COMPLETADO
 Issues creados exitosamente: 11
 Issues fallidos:             0
============================================================

 🎉 BACKLOG L2 CREADO PARA LA ÉPICA E14 — ONBOARDING (11 stories, ~23h).

 Próximos pasos:
   1. Verifica los issues en: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues?q=is%3Aissue+label%3Aepic%3AE14
   2. Verifica el proyecto en: https://github.com/orgs/Informatica-ASHware/projects/2
   3. ⚠️  E14-S07 (refactor cross-épica) es la story de mayor riesgo de regresión.
       Considera feature flag para rollback si CI rojo.
   4. ⚠️  E14-S10 (migration legacy) corre vacía si no hay yaml previo —
       importante para futuros forks/clones.
   5. ⚠️  Las decisiones del usuario están documentadas en ADR-008 y en
       'R_Backlog_Nivel_2_E14.md' bajo 'Decisiones técnicas clave'.
   6. Costo runtime de multi-profile: ~3x baseline si hay 3 perfiles activos.
       Documentar en runbook tras S07.

 Total stories E14: 11  |  Estimación: ~23-25h
 Costo bootstrap one-shot LLM: ~$0.20
