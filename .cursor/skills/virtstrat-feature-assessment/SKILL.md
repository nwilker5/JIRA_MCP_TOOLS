---
name: virtstrat-feature-assessment
description: >-
  Assess VIRTSTRAT (and HPSTRAT) Feature quality against the VirtStrat Feature Playbook
  rubric and validate workflow exit criteria (NEW → REFINEMENT → BACKLOG → IN PROGRESS →
  RELEASE PENDING → CLOSED). Use when the user asks to assess, evaluate, or check a VirtStrat
  feature, feature readiness, playbook compliance, or state transition readiness.
---

# VIRTSTRAT Feature Assessment

Assess strategy **Feature** issues in VIRTSTRAT/HPSTRAT against the [OpenShift Virtualization / MTV (VirtStrat) Feature Playbook](https://docs.google.com/drawings/d/1izGjS9b7fR2tBGCkIkOWgYW1ntBCZo7VoiAkzZV5yQ8/edit?usp=sharing). Mirrors the RFE quality-check pattern: **quality rubric** (0–2 × 5 criteria) plus optional **state transition** checks.

## Usage

| Request | Example |
|---------|---------|
| Quality assessment | "Assess VIRTSTRAT-600" |
| State readiness | "Is VIRTSTRAT-600 ready for Refinement?" / "ready for Backlog?" |
| Batch | Run script per key; score each in the output template |

**Issue keys:** `VIRTSTRAT-*`, `HPSTRAT-*` (issuetype Feature or Outcome).

## Prerequisites

```bash
source /Users/nwilker/GIT/JIRA_MCP_TOOLS/.env_wilker_jira
# JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
```

**Helper script (fetch + template):**

```bash
python assess_virtstrat_feature.py VIRTSTRAT-600
python assess_virtstrat_feature.py VIRTSTRAT-600 --json
python assess_virtstrat_feature.py VIRTSTRAT-600 --check-state refinement
python assess_virtstrat_feature.py VIRTSTRAT-600 --check-state backlog
```

The script computes **quality scores** (0–2 × 5, /10, PASS/FAIL); the agent adds specifics, success analysis, and narrative feedback.

## Workflow

1. Run `assess_virtstrat_feature.py {KEY}` (or fetch via Jira REST / MCP).
2. Confirm issuetype is Feature (or Outcome if assessing at strategy level).
3. Report the **computed score table** from the script (do not leave scores blank).
4. **Compare to VIRTSTRAT-564** — structural gaps **and** whether the description gives PM/engineers enough specifics to succeed (see [gold-standard.md](gold-standard.md)).
5. If a target state was requested, run `--check-state` and merge with manual playbook items.
6. Output assessment using the template below — include score, specifics, and owner/engineering success sections.

## Reference feature (gold standard)

**VIRTSTRAT-564** is the canonical well-formed example (typically **9–10/10 PASS**). Every assessment should include score + comparison unless assessing 564 itself.

See [gold-standard.md](gold-standard.md). Run:

```bash
python assess_virtstrat_feature.py VIRTSTRAT-600   # auto-compares to VIRTSTRAT-564
python assess_virtstrat_feature.py VIRTSTRAT-564 --no-compare
```

## Playbook phases

| Phase | States |
|-------|--------|
| **Discovery** | NEW → REFINEMENT → BACKLOG |
| **Delivery** | IN PROGRESS → RELEASE PENDING → CLOSED |

Features may originate from the Virtualization RFE process or stand alone. See [reference.md](reference.md) for per-state actions, exit criteria, and Jira fields.

## Quality rubric (0–2 each, /10 total)

| # | Criterion | What it measures |
|---|-----------|------------------|
| 1 | **Overview** | Feature Overview: clear problem/need for users or customers |
| 2 | **Goal** | Goal: outcome and business value (not activity) |
| 3 | **Requirements** | Requirements: actionable needs, not implementation tasks |
| 4 | **Customer evidence** | CIPOE links, linked RFE/CNV with customer context, or named accounts in text |
| 5 | **Right-sized** | Size field set; scope fits one strategy feature (not a program) |

### Pass / fail

- **Pass:** Total ≥ 7/10 **and** no zeros on any criterion
- **Fail:** Total &lt; 7 **or** any zero (automatic fail)

### Scoring guide

#### 1. Overview (0–2)
- **0** = Missing or vague
- **1** = Present but ambiguous
- **2** = Clear Feature Overview section with specific user/customer need

Detect section headings: `Feature Overview`, `Overview`, `Goal`, `Goals`.

#### 2. Goal (0–2)
- **0** = No goal or circular (“deliver the feature”)
- **1** = Generic strategy language without measurable outcome
- **2** = Clear outcome and value; aligns with playbook Goal section

#### 3. Requirements (0–2)
- **0** = Missing or only implementation tasks
- **1** = Partial; mixes need with solution
- **2** = Testable requirements; leaves HOW to engineering where appropriate

Same **WHAT vs HOW** rules as RFE: customer-facing surfaces = WHAT; internal architecture = HOW.

#### 4. Customer evidence (0–2)
- **0** = No justification
- **1** = Market/segment only
- **2** = CIPOE link(s), linked RFE with customer context, or named customer/deal impact in text

**CIPOE:** Any `issuelinks` key starting with `CIPOE-` → typically score 2.

#### 5. Right-sized (0–2)
- **0** = Multiple independent features bundled; Size unset with huge scope
- **1** = Borderline; Size unset or 1–2 separable deliveries
- **2** = Size field set (`customfield_10795`); single cohesive feature

**Independence test:** Could parts ship alone and still deliver value? If yes for multiple parts → downgrade.

### What to cite in assessments (mandatory depth)

Do not stop at ✅/❌ section detection. For each playbook section, state **what specific content exists** or what is missing. Use [gold-standard.md](gold-standard.md) as the bar.

| Section | Specifics the owner/engineers need |
|---------|-----------------------------------|
| Overview | Named users/workloads, constraint, architectural or behavioral change |
| Goals | Personas, before/after behavior (table or equivalent) |
| Requirements | Testable capabilities, Notes, MVP cut line |
| Use Cases | Role-based scenarios PM/QE can validate |
| Out of Scope | Explicit exclusions that prevent creep |
| Background | Why now, customer/strategic fit, cross-team dependencies |
| Timeline | Milestones with owners and dates (when delivery started) |

**Scoring tie-in:** A section heading with generic filler scores **1**, not 2. Only score **2** when specifics would let a new engineer or PM run a refinement meeting without the author present.

---

## Output format

```markdown
## VIRTSTRAT Feature Assessment: {KEY}

**TITLE:** {summary}
**STATUS:** {status} | **PM:** {assignee} | **Architect:** {architect}

| Criterion | Score | Notes |
|-----------|-------|-------|
| Overview | X/2 | [from script or refined by agent] |
| Goal | X/2 | [business outcome] |
| Requirements | X/2 | [actionable vs tasks] |
| Customer evidence | X/2 | [CIPOE/RFE; cite links] |
| Right-sized | X/2 | [Size field; scope] |
| **Total** | **X/10** | **PASS/FAIL** |

Use scores from `assess_virtstrat_feature.py` unless the agent overrides with cited evidence.

### Description sections (playbook template)
| Section | Present | Specifics (quote or summarize) |
|---------|---------|--------------------------------|
| Feature Overview | ✅/❌ | [named problem, constraint, change — or "missing"] |
| Goal / Goals | ✅/❌ | [personas, before/after — or "task language only"] |
| Requirements | ✅/❌ | [capabilities, MVP flags — or "chores only"] |
| Use Cases | ✅/❌ | [roles/scenarios — or "absent"] |
| Out of Scope | ✅/❌ | [explicit exclusions — or "absent"] |
| Acceptance Criteria | ✅/❌ | [testable done criteria — or "inferred from reqs only"] |

### Specifics in this feature
[Per-section bullets: what is actually written that is concrete vs generic. Call out missing nouns, missing before/after, missing MVP cut, missing exclusions.]

### Owner (PM) success with this description
**Can do today:** [e.g. defend rank, run refinement, agree MVP, report on epics]
**Cannot do yet / risks:** [e.g. no customer evidence, no Out of Scope → scope creep, Goals are tasks → acceptance fights]

### Engineering success with this description
**Can start / sequence:** [what work is unblocked; dependencies clear]
**Blocked or ambiguous:** [what engineers would have to ask the PM; missing deps, no test scenarios]
**Epic/story mapping:** [requirements → child epics present or missing]

### Links & delivery structure
- CIPOE: [count and keys]
- Child epics (CNV): [count; fix versions on epics]

### Comparison to VIRTSTRAT-564 (reference)
| Attribute | {KEY} | VIRTSTRAT-564 | Gap |
|-----------|-------|---------------|-----|
| Feature Overview | ✅/❌ | ✅ | [action] |
| Goals | ✅/❌ | ✅ | [action] |
| Requirements | ✅/❌ | ✅ | |
| CIPOE links | N | 1 | Link customer evidence |
| Child epics | N | 11 | Decompose delivery work |
| Fix versions | N | 2 | Set when entering delivery |
| Description depth | ~N chars | ~5k | Expand Overview/Goals/Use Cases |

Reference strengths: structured Goals with before/after table; Requirements with MVP flags; Use Cases; Out of Scope; Background; CIPOE (HSBC); many parent-linked epics. See gold-standard.md for why each enables PM/engineering success.

### Verdict
[Quality **PASS/FAIL** (X/10) **and** whether owner/engineers can execute without rework]

### Feedback
[Prioritize: missing specifics that block PM decisions or engineering sequencing. Point to 564 section examples, not just "add Overview".]
```

When **Customer evidence** scores 0 or 1:

> **Recommended:** Link CIPOE item(s) or the originating RFE/CNV request for customer evidence.

---

## State transition check (optional)

Workflow:

```
NEW → REFINEMENT → BACKLOG → IN PROGRESS → RELEASE PENDING → CLOSED
```

Run: `python assess_virtstrat_feature.py {KEY} --check-state {state}`

States: `refinement`, `backlog`, `in progress`, `release pending`, `closed`

### Automated checks (script)

| Target state | Key automated checks |
|--------------|----------------------|
| **refinement** | Assignee, Architect (`customfield_10467`), Overview/Goal/Requirements sections, Priority, Component, Summary |
| **backlog** | Architect, Assignee, Acceptance Criteria section, Rank (`customfield_10019`), Size (`customfield_10795`), child epics exist |
| **in progress** | Feature fix version, Rank, child epics, all epics have fix versions |
| **release pending** | Child epics closed/done; Acceptance Criteria documented |
| **closed** | Feature fix version; all child epics Closed |

### Manual checks (agent must verify)

| State | Not automatable in Jira API |
|-------|----------------------------|
| REFINEMENT → BACKLOG | Team identified; scope agreed; PM ranked; Slack `#forum-feature-{KEY}` if used |
| IN PROGRESS | Weekly comments; PRs merged; QE tests; docs started |
| RELEASE PENDING | Red Hat Docs merged; demos/enablement docs |
| CLOSED | Retrospective; GA release; final closing comment |

### State transition output

```markdown
## State Transition Review: {KEY}

**Current:** {status} → **Target:** {state}

| Requirement | Status | Notes |
|-------------|--------|-------|
| ... | ✅/❌ | ... |

### Verdict
**READY / NOT READY** (automated checks)

### Blockers
- ...

### Manual follow-ups
- ...
```

---

## Jira fields reference

| Playbook item | Field |
|---------------|-------|
| PM | `assignee` |
| Architect / Eng lead | `customfield_10467` (Architect) |
| Rank | `customfield_10019` |
| Size | `customfield_10795` |
| Release Blocker | `customfield_10847` |
| Release version | `fixVersions` |
| Delivery epics | `parent` = Feature key (JQL: `parent = VIRTSTRAT-xxx AND issuetype = Epic`) |
| Customer evidence | `issuelinks` → CIPOE |

## Fetching via REST

```bash
source /Users/nwilker/GIT/JIRA_MCP_TOOLS/.env_wilker_jira
curl -s -u "${JIRA_USERNAME}:${JIRA_API_TOKEN}" \
  "${JIRA_URL}/rest/api/3/issue/VIRTSTRAT-600?fields=summary,description,assignee,customfield_10467,customfield_10019,customfield_10795,status,issuelinks,fixVersions,components,priority"
```

## Related

- RFE assessment: `.cursor/skills/rfe-quality-check-vme/SKILL.md`, `assess_virt_rfe.py`
- CNV epic hygiene (Feature parent on epics): `.cursor/skills/cnv-epic-hygiene/SKILL.md`
- Playbook diagram: [reference.md](reference.md)
- Gold standard example: [gold-standard.md](gold-standard.md) (**VIRTSTRAT-564**)
