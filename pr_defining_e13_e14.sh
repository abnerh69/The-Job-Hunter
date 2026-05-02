#!/bin/bash
# =============================================================================
# PR: docs/define-epics-e13-e14
# Cambios: backlog E14, ADR-008, correcciones HUMAN_SETUP/DEPLOY_AWS/tests
# =============================================================================

set -euo pipefail

# 1. Crear y cambiar a la nueva rama
git checkout -b docs/define-epics-e13-e14

# 2. Agregar todos los archivos modificados y nuevos
git add \
  DEPLOY_AWS.md \
  HUMAN_SETUP.md \
  README.md \
  pr_defining_e13_e14.sh \
  pr_for_sonnet_analysis.sh \
  x.md \
  tests/e2e/dashboard/test_outreach_metrics_e2e.py \
  "docs/Plan automatizado para búsqueda de trabajo remoto en Europa/R_Backlog_Nivel_2_E14.md" \
  docs/adr/ADR-008-profile-in-db.md \
  scripts/add_epics_E13_E14_to_project.sh \
  scripts/create_issues_E13.sh \
  scripts/create_issues_E14.sh

# 3. Commit
git commit -m "docs(backlog): define E14 onboarding automation and add ADR-008

- Add R_Backlog_Nivel_2_E14.md: 10-story epic for profile bootstrap
  from resume (ResumeIngestor, ProfileGenerator, CVVariantGenerator,
  SalaryProposer, Onboarding wizard, CLI, migration)
- Add ADR-008: candidate profile moves from YAML to DB (hybrid schema A3,
  multi-profile B2, soft-gating wizard, one-shot migration D1)
- Fix HUMAN_SETUP.md: all 'python -m jobhunter' commands prefixed with
  'uv run'; add convention note at top of §1; §2.1/2.2 reference E14
- Fix DEPLOY_AWS.md: add '# pragma: allowlist secret' on placeholder
  credential lines 157 and 187 to silence detect-secrets false positives
- Fix tests/e2e/dashboard/test_outreach_metrics_e2e.py: add pragma on
  ANTHROPIC_API_KEY dummy assignment (line 41) — same false-positive fix
- Add scripts/create_issues_E13.sh and create_issues_E14.sh for GitHub
  Issues bulk creation
- Add scripts/add_epics_E13_E14_to_project.sh to register epics in the
  GitHub Project V2 board"

# 4. Push al remote
git push -u origin docs/define-epics-e13-e14

# 5. Crear el PR con GitHub CLI
gh pr create \
  --base main \
  --head docs/define-epics-e13-e14 \
  --title "docs(backlog): define E14 onboarding automation and add ADR-008" \
  --body "## Resumen

Consolida la definición de la Épica E14 *(Onboarding Automation & Profile
Generation)* y el ADR-008, junto con correcciones de documentación y
falsos positivos en el CI de detect-secrets.

---

## Cambios incluidos

### 🆕 Nuevos archivos
| Archivo | Descripción |
|---|---|
| \`docs/.../R_Backlog_Nivel_2_E14.md\` | Backlog nivel-2 de E14: 10 stories (~21.5h) |
| \`docs/adr/ADR-008-profile-in-db.md\` | Decisión: perfil de candidato migra de YAML a BD Postgres |
| \`scripts/create_issues_E13.sh\` | Bulk-create GitHub Issues para E13 |
| \`scripts/create_issues_E14.sh\` | Bulk-create GitHub Issues para E14 |
| \`scripts/add_epics_E13_E14_to_project.sh\` | Registrar épicas E13/E14 en GitHub Project V2 |

### ✏️ Archivos modificados
| Archivo | Cambio |
|---|---|
| \`HUMAN_SETUP.md\` | Comandos \`python -m jobhunter\` → \`uv run python -m jobhunter\`; nota de convención en §1; §2.1/2.2 referencian E14 |
| \`DEPLOY_AWS.md\` | Pragma \`allowlist secret\` en líneas 157 y 187 (placeholders de documentación) |
| \`tests/e2e/.../test_outreach_metrics_e2e.py\` | Pragma \`allowlist secret\` en línea 41 (ANTHROPIC_API_KEY dummy) |
| \`README.md\` | Ajustes menores |

---

## Decisiones arquitectónicas (E14 / ADR-008)

| Eje | Decisión |
|---|---|
| Schema | **A3 híbrido**: columnas para campos queryables, JSONB para listas |
| Multi-perfil | **B2**: multi-profile desde día 1 (variant_selector dinámico) |
| Wizard | **Soft gating**: banner si no hay perfil, no bloquea navegación |
| Migración YAML | **D1**: one-shot a BD + archive; YAML deja de ser autoritativo |
| Encryption PII | **E1**: sin cifrado MVP (disk encryption EBS + auth dashboard) |
| CV Variants | **User-defined**: no hardcodeadas; refactor variant_selector en E14-S06 |

---

## CI
- [ ] Lint (ruff)
- [ ] Format (ruff format)
- [ ] Type check (mypy)
- [ ] Tests (pytest)
- [ ] detect-secrets (falsos positivos corregidos con pragma)"
