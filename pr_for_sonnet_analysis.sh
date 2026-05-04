# 1. Crear y cambiar a la nueva rama
git checkout -b docs/infra-deploy-adrs-epic-docs

# 2. Agregar todos los archivos cambiados/nuevos
git add README.md docs/data_model.md pyproject.toml \
  src/jobhunter/config.py \
  "src/jobhunter/dashboard/pages/3_🔍_Manual_Review.py" \
  src/jobhunter/sources/base.py \
  CLAUDE.md DEPLOY_AWS.md HUMAN_SETUP.md LICENSE \
  "docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Confirmación Épicas 1-6 Completadas Correctamente.md" \
  "docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Confirmación Épicas 7-12 Completadas Correctamente.md" \
  "docs/Plan automatizado para búsqueda de trabajo remoto en Europa/Q_Backlog_Nivel2_E13.md" \
  docs/adr/ADR-006-no-settings-singleton.md \
  docs/adr/ADR-007-thin-basesource-contract.md

# 3. Commit con el mensaje acordado
git commit -m "docs(infra): add deployment guide, ADRs, epic docs and refine core config

- Add DEPLOY_AWS.md with full EC2 production setup runbook
- Add HUMAN_SETUP.md for local onboarding steps
- Add CLAUDE.md with AI assistant context for the project
- Add ADR-006 (no-settings-singleton) and ADR-007 (thin-BaseSouce-contract)
- Add backlog docs: confirmations E1–E12, E13 level-2 breakdown
- Refactor config.py and sources/base.py per ADR-006/ADR-007
- Update Manual Review dashboard page and data_model docs
- Bump pyproject.toml deps and project metadata"

# 4. Push de la rama al remote
git push -u origin docs/infra-deploy-adrs-epic-docs

# 5. Crear el PR (requiere GitHub CLI instalado)
gh pr create \
  --base main \
  --head docs/infra-deploy-adrs-epic-docs \
  --title "docs(infra): add deployment guide, ADRs, epic docs and refine core config" \
  --body "## Resumen
Consolida toda la documentación de infraestructura, decisiones arquitectónicas y avance épico generados en esta sesión.

## Cambios incluidos
- **DEPLOY_AWS.md** — Runbook completo para despliegue en EC2
- **HUMAN_SETUP.md** — Guía de onboarding local
- **CLAUDE.md** — Contexto del proyecto para asistentes AI
- **ADR-006** — No-settings-singleton pattern
- **ADR-007** — Thin BaseSouce contract
- **Confirmaciones E1–E12** — Épicas completadas documentadas
- **Q_Backlog_Nivel2_E13** — Descomposición de la siguiente épica
- Refactor de \`config.py\` y \`sources/base.py\` alineado a ADRs
- Actualización de \`data_model.md\`, dashboard Manual Review y \`pyproject.toml\`

## Checklist
- [x] CI pasa en \`main\`
- [x] Sin secrets expuestos
- [x] Documentación coherente con el estado actual del código"
