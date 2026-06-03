---
name: mtv-rfe-quality-check
description: >-
  Deprecated alias — use rfe-quality-check-vme skill and assess_virt_rfe.py --project mtv.
  Assess MTV Feature Request quality. Use when the user asks to assess MTV RFE specifically.
---

# MTV RFE Quality Assessment

**Use the unified Virt tool:** `assess_virt_rfe.py` with `--project mtv` or an `MTV-*` issue key.

See [.cursor/skills/rfe-quality-check-vme/SKILL.md](../rfe-quality-check-vme/SKILL.md) for the full rubric, workflow, and comment rules.

## Quick commands

```bash
python assess_virt_rfe.py MTV-5653
python assess_virt_rfe.py --project mtv --new
python assess_virt_rfe.py MTV-5653 --comment --execute
./run_virt_rfe_assessment.sh --project mtv --new
```

Legacy wrappers (`assess_rfe.py`, `assess_mtv_rfe.py`, `run_rfe_assessment.sh`, `run_mtv_rfe_assessment.sh`) still work.
