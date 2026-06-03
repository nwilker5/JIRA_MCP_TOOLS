---
name: rfe-quality-check-vme
description: >-
  Assess CNV or MTV Feature Request (RFE) quality against a scoring rubric, with draft/display/comment
  modes and state transition checks. Use when the user asks to assess, evaluate, check an RFE in CNV
  or MTV, batch assess new RFEs, or verify readiness to move to a new state.
---

# Virt RFE Quality Assessment (CNV & MTV)

Assess **Feature Request** issues in project **CNV** or **MTV** against a shared Virt RFE quality rubric. One tool: `assess_virt_rfe.py`. Project is auto-detected from `CNV-*` / `MTV-*` keys, set with `--project`, or chosen interactively.

## Usage

| Mode | Command |
|------|---------|
| **Auto-detect project** | `python assess_virt_rfe.py CNV-81784` or `MTV-5653` |
| **Explicit project** | `python assess_virt_rfe.py --project cnv --new` |
| **Interactive pick** | `python assess_virt_rfe.py --new` (prompts CNV or MTV) |
| **Draft / display** | `python assess_virt_rfe.py MTV-5653` (default — no Jira writes) |
| **Markdown file** | `python assess_virt_rfe.py MTV-5653 --output draft.md` |
| **Comment preview** | `python assess_virt_rfe.py MTV-5653 --comment` |
| **Comment execute** | `python assess_virt_rfe.py MTV-5653 --comment --execute` |
| **JSON** | `python assess_virt_rfe.py CNV-81784 --json` |
| **State check** | `python assess_virt_rfe.py MTV-5653 --check-state refinement` |

Launcher: `./run_virt_rfe_assessment.sh CNV-81784` or `./run_virt_rfe_assessment.sh --project mtv --new`

## Prerequisites

```bash
source /Users/nwilker/GIT/JIRA_MCP_TOOLS/.env_wilker_jira
# JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
```

## Workflow

1. Determine project: from issue key, `--project cnv|mtv`, or prompt user.
2. Run `assess_virt_rfe.py` in **draft** mode first unless the user explicitly asks to comment.
3. Report the **computed score table** from the script (do not leave scores blank).
4. For batch intake, use `--project {cnv|mtv} --new`.
5. Before `--comment --execute`, show preview unless the user already approved posting.
6. Comments use **Red Hat Employee** visibility and Claude AI attribution.

## Scoring Rubric

### Criteria (0-2 each, /10 total)

| # | Criterion | What it measures |
|---|-----------|------------------|
| 1 | **WHAT** | Is the customer need clear and specific? |
| 2 | **WHY** | Is there business justification (customers, revenue, strategy)? |
| 3 | **Open to HOW** | Does it leave architecture decisions to engineering? |
| 4 | **Not a task** | Is it a business need, not a chore/task? |
| 5 | **Right-sized** | Does it map to approximately one feature? |

### Pass/Fail
- **Pass:** Total >= 7/10 AND no zeros on any criterion
- **Fail:** Total < 7 OR any zero (automatic fail regardless of total)

---

## Detailed Scoring Guide

### 1. WHAT — Clear customer need? (0-2)
- **0** = Vague or unclear
- **1** = Ambiguous
- **2** = Clear and specific

Technical terms are OK for precision.

### 2. WHY — Business justification? (0-2)
- **0** = No justification, circular reasoning, or hype-chasing with no business case
- **1** = Generic segments, market positioning, analyst references — plausible but no customer-level evidence
- **2** = Named customer accounts, specific revenue/deal impact, strategic investment with clear causal chain

**CIPOE Links:** A link to a CIPOE item counts as named customer evidence. Check issuelinks for any keys starting with `CIPOE-`. A CIPOE link typically scores WHY = 2.

### 3. Open to HOW — Leaves architecture to engineering? (0-2)
- **0** = Mandates internal architecture or links design docs as "the solution"
- **1** = Leans into implementation but doesn't fully mandate
- **2** = Describes the need without prescribing architecture

**WHAT vs HOW:**
- Customer-facing surfaces (API endpoints, CLI flags, UI elements) = WHAT
- Internal architecture (database choices, repos, language choices) = HOW
- Platform vocabulary (KubeVirt, KServe, Prometheus, etc.) = Not automatically prescriptive

### 4. Not a task — Business need, not activity? (0-2)
- **0** = Task/chore/tech debt
- **1** = Borderline
- **2** = Clear business need

### 5. Right-sized — Maps to ~1 strategy feature? (0-2)
- **0** = Needs 3+ independent features
- **1** = Bundles 1-2 separable features
- **2** = Focused single need

**Independence test:** Could each deliverable ship alone and provide value?

---

## Output Format

```markdown
## {CNV|MTV} RFE Quality Assessment

**{KEY}** — {issue summary}

| Criterion | Score | Notes |
|-----------|-------|-------|
| WHAT | X/2 | [explanation] |
| WHY | X/2 | [cite evidence or note absence; mention CIPOE links if found] |
| Open to HOW | X/2 | [note any architecture prescription] |
| Not a task | X/2 | [business need vs activity] |
| Right-sized | X/2 | [scope assessment] |
| **Total** | **X/10** | **PASS/FAIL** |

### Verdict
[One sentence summary]

### Feedback
[If fail: actionable suggestions. If pass: strengths and minor improvements.]

---
*Assessment generated via Claude AI assistant.*
```

---

## Feedback Guidelines

When WHY scores 0 or 1, include:

> **Recommended:** Add a link to a CIPOE item to provide customer evidence. CIPOE links are the preferred way to demonstrate named customer need.

When any criterion scores 0, prioritize feedback for that criterion first.

---

## Checking for CIPOE Links

After fetching the issue, check `issuelinks` for CIPOE items:

```python
links = data['fields'].get('issuelinks', [])
cipoe_links = []
for link in links:
    target = link.get('outwardIssue') or link.get('inwardIssue')
    if target and target.get('key', '').startswith('CIPOE'):
        cipoe_links.append(target['key'])
```

If CIPOE links are found, note them in the WHY assessment and score accordingly.

---

## State Transition Check (Optional)

When user requests a state transition review, check exit criteria based on the CNV/MTV Feature Request Playbook (aligned process for both projects).

### Workflow States

```
NEW → REFINEMENT → IN PROGRESS → CLOSED
```

### Exit Criteria by State

#### Exiting NEW (ready for REFINEMENT)

| # | Requirement | Field/Check |
|---|-------------|-------------|
| 1 | PM identified | `assignee` is set |
| 2 | Overview & Goal in Description | Description has Overview and Goal sections |
| 3 | Engineering Lead identified (if known) | `customfield_*` Architect Contributor field |
| 4 | CIPOE linked | issuelinks contains CIPOE item |
| 5 | Summary set | `summary` is not empty |
| 6 | Priority set | `priority` is set |
| 7 | Component set | `components` is not empty |

**SLA:** 5 business days

#### Exiting REFINEMENT (ready for IN PROGRESS)

| # | Requirement | Field/Check |
|---|-------------|-------------|
| 1 | Engineering Lead confirmed | Architect Contributor field set |
| 2 | Size agreed | Scope/size discussed (check description) |
| 3 | Feature created in VIRTSTRAT | issuelinks contains VIRTSTRAT item |
| 4 | CIPOE linked (as necessary) | issuelinks contains CIPOE item |
| 5 | Ranked | `customfield_*` Rank field set |
| 6 | Development Team identified | Team assigned |

**SLA:** 14 business days

#### Exiting IN PROGRESS (ready for CLOSED)

| # | Requirement | Field/Check |
|---|-------------|-------------|
| 1 | Development complete | Linked VIRTSTRAT Feature is Done |
| 2 | Definition of Done met | Acceptance criteria satisfied |
| 3 | Documentation complete | Docs/release notes confirmed |

**SLA:** 4-12 months

---

### State Transition Output Format

```markdown
## State Transition Review: {KEY}

**Current State:** {current status}
**Target State:** {requested state}

### Exit Criteria Check

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | PM identified | ✅/❌ | [details] |
| 2 | Overview & Goal | ✅/❌ | [details] |
| ... | ... | ... | ... |

### Verdict
**READY / NOT READY** to move to {target state}

### Blockers (if not ready)
- [List missing requirements]

### Recommendations
- [Actions needed to become ready]
```

---

### Fields to Fetch for State Check

```bash
curl -s -u "${JIRA_USERNAME}:${JIRA_API_TOKEN}" \
  "${JIRA_URL}/rest/api/3/issue/{KEY}?fields=summary,description,assignee,priority,components,status,issuelinks" \
  | python3 -m json.tool
```

Check for:
- `assignee` - PM assigned
- `priority` - Priority set  
- `components` - Component assigned
- `status.name` - Current state
- `issuelinks` - CIPOE and VIRTSTRAT links
- `description` - Overview/Goal sections present
