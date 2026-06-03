# Gold standard: VIRTSTRAT-564

**Reference feature** for well-formed VirtStrat Features. All assessments compare the subject issue to this example unless `--no-compare` is used.

**Issue:** [VIRTSTRAT-564](https://redhat.atlassian.net/browse/VIRTSTRAT-564) — workload mobility for clustered software members (VM live migrations using SCSI-3 persistent reservations)

**Status:** In Progress | **PM:** Natalie Gavrilov | **Component:** Storage Ecosystem

---

## What “well-formed” means

A well-formed feature is not a long description or a full Jira checklist. It is a **shared contract** between the PM (owner), architects, and engineers so everyone can answer:

1. **What problem** are we solving, for **whom**, and **why now**?
2. **What changes** for the user/customer when we ship (not what code we write)?
3. **What must be true** for us to call this done (MVP vs later)?
4. **What is explicitly not in scope** so engineers do not gold-plate or debate endlessly?
5. **Who depends on whom**, by when, so parallel work does not block?

VIRTSTRAT-564 does this with **concrete nouns** (S3PR, virtio-scsi, WSFC, Oracle RAC), **named personas**, **before/after states**, and **owned milestones** — not generic “improve virtualization” language.

---

## Section-by-section: specifics to look for

When assessing any feature, quote or paraphrase **what is actually written**. Vague sections fail even if the heading exists.

### Feature Overview — the problem statement

**Look for specifics:**
- Named workload or user type (e.g. clustered VMs: WSFC, VCS, Oracle RAC)
- Named technical constraint (S3PR held at node level via LUN pass-through)
- Named architectural shift (pass-through → virtio-scsi; reservation moves to VM)
- Why it matters (business-critical apps; workload mobility blocked today)

**564 example:** “Enable live migration of VMs running clustered software … that relies on SCSI-3 Persistent Reservations … architectural shift from LUN pass-through … to virtio-scsi volumes.”

**Weak counter-example:** “Improve managed provisioning for OpenShift-on-OpenShift” with no user, no constraint, no current vs desired behavior.

### Goals — outcomes and delta, not activities

**Look for specifics:**
- **Personas** with distinct benefits (cluster admin vs application owner)
- **Before/after table** or equivalent: dimension × today × future
- Rows that describe **observable behavior**, not repo names or sprint tasks

**564 example (table rows):**
| Dimension | Today | Future |
|-----------|-------|--------|
| Live migration of clustered VMs | Blocked; S3PR at node level | Supported; VM holds reservation |
| Host maintenance | Downtime or manual failover | Non-disruptive to cluster software |

**Weak counter-example:** “Deliver IPI provider” or “Complete POC” — that is a task, not a goal.

### Requirements — testable needs with MVP cut line

**Look for specifics:**
- Each requirement is a **deliverable capability**, not a Jira ticket title pasted in
- **Notes** explain dependency or layer (RHEL/QEMU prerequisite vs KubeVirt enablement)
- **isMVP?** (or equivalent) so engineers know what ships first vs what can slip
- Test automation called out explicitly when verification is part of done

**564 example:**
- “Implement virtio-scsi support in QEMU …” — Notes: “Foundational RHEL/QEMU, prerequisite” — MVP: Yes
- “Kubevirt workload anti-affinity for S3PR volumes” — Notes: anti-node affinity on shared disks — MVP: Yes

**Weak counter-example:** Bullet list of engineering chores with no MVP boundary; or requirements that prescribe internal design with no user-visible outcome.

### Use Cases — validation stories for QE and PM sign-off

**Look for specifics:**
- “As a [role], I want [capability], so that [outcome]” tied to Goals table rows
- Scenarios PM can use in **acceptance conversations** and QE can map to tests

**564 example:** Cluster admin upgrading OCP without tenant downtime during migration; app owner with SCSI-3 PR intact during live migrate.

### Out of Scope — scope guardrails

**Look for specifics:**
- Explicit **exclusions** that prevent scope creep (failed migration remediation, cross-DC, non-x86)
- Each line answers “engineers might assume we need X — we don’t”

**564 example:** No automatic cluster remediation on failed migration; no stretched-cluster migration; no older reservation mechanisms.

### Background and Strategic Fit — why we invest; cross-team reality

**Look for specifics:**
- Market/customer context (enterprise critical clustered workloads)
- **Current product limitation** in plain language (pinned to host; migration blocked)
- **Cross-team dependencies** named (QEMU/RHEL before KubeVirt enablement)

**564 example:** “Cross-team effort with dependency on QEMU and RHEL teams … before OCP-V team can build Kubevirt enablement.”

### Delivery timeline (when present) — who owns what by when

**Look for specifics:**
- Milestones with **due date**, **description**, **named owner**
- Covers upstream, testing env, manual/automation testing, docs, bug resolution

**564 example:** Upstream Support (Cong Li), Live Migration (Alvaro Romero), Manual Testing Completed (Kevin Goldblatt), Docs/Release notes (Catherine Tomasko).

---

## How the owner (PM) succeeds with a description like 564

| PM need | How 564 supports it |
|---------|----------------------|
| **Prioritize and defend rank** | Background + CIPOE (HSBC) tie work to customer/strategic value |
| **Run refinement without re-explaining** | Overview + Goals table = single source of truth in meetings |
| **Agree scope with engineering** | Requirements + MVP flags + Out of Scope = negotiable boundary |
| **Know when to say “done”** | Use cases + MVP requirements = acceptance conversation script |
| **Coordinate multi-team delivery** | Timeline with owners; epics split RHEL vs CNV vs DOC vs automation |
| **Report status in playbook states** | Child epics under parent; fix versions on feature when in delivery |
| **Avoid scope creep mid-flight** | Out of Scope section is the escalation anchor |

**PM anti-patterns** (features that fail in delivery):
- Description is only a summary line + link to a design doc → PM becomes the oral wiki
- No MVP cut → every requirement fights for the same release
- No Out of Scope → “while we’re here” expansions in In Progress
- No customer link or named need → rank and staffing debates reopen every quarter

---

## How engineers succeed with a description like 564

| Engineering need | How 564 supports it |
|------------------|---------------------|
| **Understand the real constraint** | Overview names S3PR + pass-through vs virtio-scsi — not “support migration” |
| **See the target behavior** | Goals table = definition of success without reading 50 comments |
| **Sequence work** | Requirements Notes + MVP + RHEL-before-KubeVirt ordering in Background |
| **Know what not to build** | Out of Scope stops design threads early |
| **Create epics/stories** | Requirements map 1:1 to child epics (QEMU/RHEL, anti-affinity, live migrate, automation, docs) |
| **Test and demo** | Use cases give QE concrete scenarios; automation requirement explicit |
| **Leave HOW open where appropriate** | Requirements state capability; Notes allow design (e.g. affinity labels) without mandating API |

**Engineering anti-patterns:**
- Requirements are copy-pasted epic titles with no “why” → rework when integration fails
- No dependency called out → parallel starts on blocked work
- Goals are tasks (“implement CAPOA”) → team optimizes for merge, not user outcome
- Missing test/automation requirement → “done” argued at release time

---

## Links and delivery structure (564)

| Item | Value | Success role |
|------|-------|--------------|
| CIPOE-109816 (HSBC) | Customer evidence | PM can justify priority; ties to real deployment |
| 11 child epics | RHEL + CNV + DOC + automation | Engineers own slices; PM tracks aggregate on parent |
| Fix versions | CNV v5.0.0, v5.1.0 | Release alignment for Backlog → In Progress |
| Rank | Set | Roadmap ordering |

**Known gaps (even in 564):** Architect unset; Size unset; no “Acceptance Criteria” heading (MVP reqs + timeline substitute). Do not penalize missing optional fields if substance is present.

---

## Using this in an assessment

For every feature assessed, the agent must include:

1. **Specifics found** — bullet per section with quoted/paraphrased content from the subject issue (or “missing / generic”)
2. **Owner success** — what the PM can and cannot do with this description today
3. **Engineering success** — what engineers can start, sequence, and test without chasing the PM
4. **Comparison to 564** — structural gaps only where they block the above

See SKILL.md output template for the required markdown sections.
