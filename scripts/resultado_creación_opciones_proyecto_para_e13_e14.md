bash scripts/add_epics_E13_E14_to_project.sh 
============================================================
  Añadir Épicas E13 y E14 al GitHub Project
============================================================
  Owner:           Informatica-ASHware
  Repo:            Job-Hunter-EU
  Project number:  #2
  Project ID:      PVT_kwDOEBSEkc4BV46-
  Epic field ID:   PVTSSF_lADOEBSEkc4BV46-zhRRYn4

Épicas a añadir:
  • E13-QA Humana (color=PURPLE) — Rescate de desvíos cross-épica (UI/CLI/audit)
  • E14-Onboarding (color=GREEN) — Onboarding Automation & Profile Generation

¿Proceder? (s/n): s

[1/4] Consultando opciones existentes del campo 'Epic'...
  ✓ 12 opciones existentes leídas.
[2/4] Construyendo payload de opciones...
  + 'E13-QA Humana' será añadida.
  + 'E14-Onboarding' será añadida.
  ✓ Payload listo: 12 existentes + 2 nuevas = 14 opciones totales.
[3/4] Ejecutando mutation updateProjectV2Field...
  ✓ Mutation exitosa: 14 opciones en el campo Epic.
    → E13-QA Humana: b2d0749f
    → E14-Onboarding: 48fed495
[4/4] Actualizando project_manifest.json...
  ✓ Backup creado: project_manifest.json.bak
  ✓ project_manifest.json actualizado con 14 opciones de Epic.

============================================================
 🎉 ÉPICAS E13 / E14 AÑADIDAS AL PROJECT EXITOSAMENTE
============================================================
Project URL:     https://github.com/orgs/Informatica-ASHware/projects/2
Manifest:        project_manifest.json (backup: project_manifest.json.bak)

Resumen:
  Opciones añadidas: 2
    • E13-QA Humana
    • E14-Onboarding

PRÓXIMOS PASOS:
  1. Ejecutar: bash scripts/create_issues_E13.sh
     → auto-descubrirá el OPT_EPIC_E13 desde el Project.
  2. Ejecutar: bash scripts/create_issues_E14.sh
     → auto-descubrirá el OPT_EPIC_E14 desde el Project.
  3. Verificar issues en:
     https://github.com/Informatica-ASHware/Job-Hunter-EU/issues?q=is%3Aissue+label%3Aepic%3AE13
     https://github.com/Informatica-ASHware/Job-Hunter-EU/issues?q=is%3Aissue+label%3Aepic%3AE14
============================================================
