# VirtStrat Feature Playbook Reference

Source: **OpenShift Virtualization / MTV (VirtStrat) Feature Playbook**  
[Google Drawing](https://docs.google.com/drawings/d/1izGjS9b7fR2tBGCkIkOWgYW1ntBCZo7VoiAkzZV5yQ8/edit?usp=sharing)

Footnote on diagram: Features may be derived from the Virtualization RFE process or stand alone.

---

## Discovery

### NEW

| | |
|--|--|
| **Actions** | Weekly feature triage; PM/Eng Manager outline basics; PM updates rank in Roadmap |
| **Exit criteria** | PM and Eng Manager identified; Feature Overview, Goal, and Requirements completed; decision to invest further time |
| **Jira updated** | Summary, Assignee, Architect, Reporter, Priority, Component, Template |
| **SLA** | PM decision needed |

### REFINEMENT

| | |
|--|--|
| **Actions** | PM + Architect refine; update roadmap rank; refine scope/goals with team; stakeholders; Priority, Rank, Release Blocker; begin defining Epics |
| **Exit criteria** | Team fully identified; Overview/Goal/Acceptance Criteria discussed; work broken into Epics/Stories; team agrees size/scope; PM ranks feature |
| **Jira updated** | Architect, Assignee, Contributor fields, Priority, Description, Rank, Size |
| **As applicable** | Slack `#forum-feature-{KEY}` |

### BACKLOG

| | |
|--|--|
| **Actions** | Update rank; team/stakeholders; finalize Epics/Stories; kick off feature; recurring delivery discussions |
| **Exit criteria** | Rank and Release Version set; collaboration approach set; all work in Unified Backlog; delivery approach and capacity agreed |
| **Jira updated** | Release Version; delivery Epics via Parent Link; Epics get fix versions |

**Development Process bar (blue):** All requirements satisfied through end of Refinement.

---

## Delivery

### IN PROGRESS

| | |
|--|--|
| **Weekly actions** | Monitor Jira; updates on child Epics/Stories; Eng code/PRs/demos; QE tests; Docs; Product Ops enablement |
| **Exit criteria** | Continuous communication; progress in systems of record; code tested/merged with Fix Version; PM confirms AC met |
| **Updated** | Jira weekly comments & epic status; GitHub PRs; tests |

### RELEASE PENDING

| | |
|--|--|
| **Weekly actions** | PM coordinates delivery; status on children; Docs complete for publish |
| **Exit criteria** | Progress visible; documentation merged/ready; PM confirms docs meet AC |
| **Updated** | Jira comments & epic close status; Red Hat Docs; Google Docs (demos, 1-pagers) |

### CLOSED

| | |
|--|--|
| **Actions** | Close all children; PM sets Closed + Resolution; retrospective; celebrate; announce |
| **Exit criteria** | All delivery work closed; retro done; GA + documented + supported; epics + feature closed with final comment |
| **Jira updated** | All epics closed; Feature Closed with Resolution |

**Development Process for Done (green):** All exit criteria met from In Progress through Closed.

---

## Description template (assessment)

Recommended sections in the Feature description:

1. **Feature Overview** — problem and need  
2. **Goal** — outcome and business value  
3. **Requirements** — what must be delivered  
4. **Acceptance Criteria** — how PM/QE confirm done (required before Backlog)
