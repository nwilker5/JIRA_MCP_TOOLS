# Virt RFE Quality Assessment (CNV & MTV)

Assess **Feature Request** quality in **CNV** and **MTV** using the aligned Virt Feature Request playbook.

## Quick start

```bash
source load_jira_env.sh

# Auto-detect project from key
./run_virt_rfe_assessment.sh CNV-12345
./run_virt_rfe_assessment.sh MTV-5653

# Pick project interactively (batch New RFEs)
./run_virt_rfe_assessment.sh --new

# Explicit project
./run_virt_rfe_assessment.sh --project cnv --new
./run_virt_rfe_assessment.sh --project mtv --new
```

Direct script path (from repo root):

```bash
python3 .cursor/skills/rfe-quality-check-vme/scripts/assess_virt_rfe.py MTV-5653
```

## Project selection

| Method | Example |
|--------|---------|
| Auto from key | `CNV-*` → CNV, `MTV-*` → MTV |
| Flag | `--project cnv` or `--project mtv` |
| Interactive | `--new` (prompts when project not set) |
| Force prompt | `--ask-project` |

## Modes

| Mode | Flags | Writes to Jira? |
|------|-------|-----------------|
| Draft / display | *(default)* | No |
| Markdown file | `--output FILE` | No |
| Comment preview | `--comment` | No |
| Comment post | `--comment --execute` | Yes |
| Batch New RFEs | `--project {cnv\|mtv} --new` | No (unless `--comment --execute`) |

## Rubric (5 × 0–2, /10)

| Criterion | Measures |
|-----------|----------|
| WHAT | Clear, specific customer need |
| WHY | Business justification; CIPOE = named customer evidence |
| Open to HOW | Need without mandating internal architecture |
| Not a task | Business outcome, not chore/tech debt |
| Right-sized | ~one strategy feature |

**Pass:** ≥ 7/10 and no zeros | **Fail:** < 7 or any zero

## Links

| Link | Purpose |
|------|---------|
| **CIPOE** | Customer evidence (WHY); required for NEW → REFINEMENT |
| **VIRTSTRAT** | Strategy feature tracking; required for REFINEMENT → IN PROGRESS |

## State transitions

```
NEW → REFINEMENT → IN PROGRESS → CLOSED
```

Same playbook exit criteria for CNV and MTV.

## Reference

- **Script:** `.cursor/skills/rfe-quality-check-vme/scripts/assess_virt_rfe.py`
- **Launcher:** `run_virt_rfe_assessment.sh`
- **Skill:** `.cursor/skills/rfe-quality-check-vme/SKILL.md`
- **VirtStrat Features:** `assess_virtstrat_feature.py` (not yet reorganized)
