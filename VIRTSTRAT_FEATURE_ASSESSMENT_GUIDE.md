# VIRTSTRAT Feature Assessment Tool

Assess VirtStrat **Feature** issues against the [Feature Playbook](https://docs.google.com/drawings/d/1izGjS9b7fR2tBGCkIkOWgYW1ntBCZo7VoiAkzZV5yQ8/edit?usp=sharing), using the same pattern as the RFE quality checker.

---

## Quick Start

```bash
source .env_wilker_jira   # or your .env_jira
python assess_virtstrat_feature.py VIRTSTRAT-600
```

---

## What It Checks

### Quality rubric (5 × 0–2)

| Criterion | Measures |
|-----------|----------|
| **Overview** | Feature Overview section clear? |
| **Goal** | Outcome and business value? |
| **Requirements** | Actionable needs vs tasks? |
| **Customer evidence** | CIPOE / RFE / named customer? |
| **Right-sized** | Size set; single feature scope? |

**Pass:** ≥ 7/10 and no zeros — computed automatically by `assess_virtstrat_feature.py`.

### Playbook workflow

```
NEW → REFINEMENT → BACKLOG → IN PROGRESS → RELEASE PENDING → CLOSED
```

### Links & structure

| Check | Why |
|-------|-----|
| **CIPOE** | Customer evidence for Goal / customer evidence criterion |
| **Child CNV epics** | Parent link; required from Refinement/Backlog onward |
| **Fix versions** | On feature and epics before / during delivery |

---

## Options

```bash
python assess_virtstrat_feature.py VIRTSTRAT-600
python assess_virtstrat_feature.py VIRTSTRAT-600 --json          # includes reference block
python assess_virtstrat_feature.py VIRTSTRAT-600 --check-state refinement
python assess_virtstrat_feature.py VIRTSTRAT-600 --compare-to VIRTSTRAT-564
python assess_virtstrat_feature.py VIRTSTRAT-564 --no-compare    # skip self-comparison
```

By default every assessment is **compared to VIRTSTRAT-564**, the well-formed reference feature.

---

## Gold standard: VIRTSTRAT-564

A well-formed feature is a **shared contract**: concrete problem, behavioral delta, MVP cut line, exclusions, and delivery ownership — not just section headings.

| What good looks like | Example in 564 | Who it helps |
|----------------------|----------------|--------------|
| Feature Overview | S3PR + pass-through → virtio-scsi | Engineers see constraint; PM states problem |
| Goals | Before/after table (migration blocked → supported) | Everyone shares definition of success |
| Requirements | MVP flags + Notes (RHEL prereq vs KubeVirt) | Engineers sequence; PM negotiates scope |
| Use Cases | Cluster admin + app owner scenarios | PM/QE sign-off; QE writes tests |
| Out of Scope | No cross-DC migration, no auto-remediation | Stops scope creep in In Progress |
| Background | Cross-team RHEL/QEMU before OCP-V | Eng leads plan dependencies |
| CIPOE + epics | HSBC link; 11 child epics | PM tracks; teams own slices |

Full section-by-section specifics and PM/engineering success tables:  
`.cursor/skills/virtstrat-feature-assessment/gold-standard.md`

---

## Cursor skill

Ask in Cursor: *"Assess VIRTSTRAT-600"* or *"Is VIRTSTRAT-600 ready for Backlog?"*

Skill: `.cursor/skills/virtstrat-feature-assessment/SKILL.md`

---

## Reference

- Playbook detail: `.cursor/skills/virtstrat-feature-assessment/reference.md`
- RFE counterpart: `RFE_ASSESSMENT_GUIDE.md`, `assess_virt_rfe.py`
