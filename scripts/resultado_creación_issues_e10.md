/bin/bash "/Users/abnershernandez/Dev/ashware/Job Hunter EU/scripts/create_issues_E10.sh"
(jobhunter) scripts $ /bin/bash "/Users/abnershernandez/Dev/ashware/Job Hunter EU/scripts/create_issues_E10.sh"
Verificando/creando labels necesarios...
✓ Label "epic:E10" created in Informatica-ASHware/Job-Hunter-EU
  ✓ Label creado: epic:E10
  ✓ Label creado: type:cli
  ✓ Label creado: type:infra
✓ Label "component:email" created in Informatica-ASHware/Job-Hunter-EU
  ✓ Label creado: component:email
  ✓ Label creado: component:auth
  ✓ Label creado: component:notify

============================================================
 Generador de Backlog Job-Hunter-EU — Épica E10
 Repositorio: Informatica-ASHware/Job-Hunter-EU | Proyecto: #2
============================================================

Creando issue: [E10-S01] OAuth2 Gmail setup + token storage cifrado
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/126
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S02] Tabla `email_messages` + repo
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/127
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S03] Gmail API client wrapper
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/128
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S04] Email matcher (heurística + IA)
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/129
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S05] Sugeridor de cambios de estado
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/130
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S06] Telegram bot inline buttons (interactividad)
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/131
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S07] Workflow `email-poll` cada 30 min
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/132
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.
Creando issue: [E10-S08] Métricas de detección + tests end-to-end
  ✓ Issue creado: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues/133
  ✓ Añadido al Proyecto.
  ✓ Metadatos (Epic, Priority) asignados.

============================================================
 PROCESO COMPLETADO
 Issues creados exitosamente: 8
 Issues fallidos:             0
============================================================

 Próximos pasos:
   1. Verifica los issues en: https://github.com/Informatica-ASHware/Job-Hunter-EU/issues
   2. Verifica el proyecto en: https://github.com/orgs/Informatica-ASHware/projects/2
   3. ⚠️  ANTES DE IMPLEMENTAR S01: crear proyecto en Google Cloud Console,
       habilitar Gmail API, generar OAuth Client ID (Desktop type).
   4. ⚠️  Política CRÍTICA: rejected/offer SIEMPRE requieren confirmación humana,
       sin importar confidence. NO la saltes.
   5. ⚠️  Privacy first: NUNCA almacenar contenido completo de emails.
       Solo metadata + snippet (200 chars) + body_hash.
