#!/usr/bin/env python3
"""
Virt RFE Quality Assessment Tool (CNV & MTV)
Assesses Feature Requests against the shared Virt RFE quality rubric.

Usage:
    ./run_virt_rfe_assessment.sh CNV-12345
    python .cursor/skills/rfe-quality-check-vme/scripts/assess_virt_rfe.py MTV-5653 --project mtv --new
    python .cursor/skills/rfe-quality-check-vme/scripts/assess_virt_rfe.py MTV-5653 --comment --execute

Environment: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN (via load_jira_env.sh / .env_jira)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

JIRA_URL = os.environ.get("JIRA_URL", "").rstrip("/")
JIRA_USERNAME = os.environ.get("JIRA_USERNAME")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

ARCHITECT_FIELD = "customfield_10467"
RANK_FIELD = "customfield_10019"
PLAYBOOK = "CNV/MTV Feature Request Playbook (aligned RFE process)"
SUPPORTED_PROJECTS = ("CNV", "MTV")

PROJECT_CONFIG = {
    "CNV": {
        "label": "OpenShift Virtualization (CNV)",
        "need_patterns": re.compile(
            r"customer|user|vm|kubevirt|virtual|cluster|tenant|admin|operator|business|workload|guest",
            re.I,
        ),
    },
    "MTV": {
        "label": "Migration Toolkit for Virtualization (MTV)",
        "need_patterns": re.compile(
            r"customer|user|migration|vmware|provider|tenant|admin|operator|business|warm|cold",
            re.I,
        ),
    },
}

FETCH_FIELDS = (
    "summary,description,issuelinks,status,priority,components,assignee,issuetype,project,"
    f"{ARCHITECT_FIELD},{RANK_FIELD}"
)

DESCRIPTION_SECTIONS = [
    ("overview", re.compile(r"\boverview\b", re.I)),
    ("goal", re.compile(r"\bgoals?\b", re.I)),
]

PRESCRIPTIVE_PATTERNS = [
    re.compile(r"\bmust use\b", re.I),
    re.compile(r"\b(implement|built?) (using|with|in)\b", re.I),
    re.compile(r"\b(postgres|mysql|mongodb|redis)\b", re.I),
    re.compile(r"\brewrite (the|in|using)\b", re.I),
    re.compile(r"\bfollow (this|the) (design|architecture)\b", re.I),
    re.compile(r"\buse (repository|repo|module)\b", re.I),
]

TASK_PATTERNS = [
    re.compile(r"\btech(nical)? debt\b", re.I),
    re.compile(r"\brefactor\b", re.I),
    re.compile(r"\bclean\s*up\b", re.I),
    re.compile(r"\bupgrade (dependency|dependencies|library|libraries)\b", re.I),
    re.compile(r"\bfix (typo|lint|formatting)\b", re.I),
    re.compile(r"\brename (variable|function|file)\b", re.I),
]

BUNDLE_PATTERNS = [
    re.compile(r"\b(and also|additionally|in addition)\b", re.I),
    re.compile(r"\bpart\s+[12]\b", re.I),
    re.compile(r"\b(separate|independent) feature\b", re.I),
    re.compile(r"\bmultiple (features|capabilities|enhancements)\b", re.I),
]

STATE_ALIASES = {
    "refinement": "refinement",
    "in progress": "in progress",
    "in-progress": "in progress",
    "inprogress": "in progress",
    "closed": "closed",
}


def comment_marker(project: str) -> str:
    return f"{project} RFE Quality Assessment"


def extract_text_from_adf(node) -> str:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") == "hardBreak":
            return "\n"
        if node.get("type") in ("paragraph", "heading", "listItem"):
            extra = "\n\n" if node.get("type") == "paragraph" else "\n"
            if node.get("type") == "heading":
                level = node.get("attrs", {}).get("level", 1)
                return "#" * level + " " + extract_text_from_adf(node.get("content", [])) + extra
            return extract_text_from_adf(node.get("content", [])) + extra
        content = node.get("content", [])
        return "".join(extract_text_from_adf(c) for c in content)
    if isinstance(node, list):
        return "".join(extract_text_from_adf(c) for c in node)
    return ""


def require_credentials() -> None:
    missing = [
        v
        for v, val in [
            ("JIRA_URL", JIRA_URL),
            ("JIRA_USERNAME", JIRA_USERNAME),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        ]
        if not val
    ]
    if missing:
        print("Error: missing environment variables:", ", ".join(missing))
        print("  source load_jira_env.sh")
        sys.exit(1)


def normalize_project(value: str | None) -> str | None:
    if not value:
        return None
    project = value.strip().upper()
    if project not in SUPPORTED_PROJECTS:
        print(f"Error: unsupported project '{value}'. Choose: cnv or mtv")
        sys.exit(1)
    return project


def project_from_issue_key(issue_key: str | None) -> str | None:
    if not issue_key or "-" not in issue_key:
        return None
    prefix = issue_key.split("-", 1)[0].upper()
    return prefix if prefix in SUPPORTED_PROJECTS else None


def prompt_for_project() -> str:
    print("Which project?")
    print("  1) CNV — OpenShift Virtualization")
    print("  2) MTV — Migration Toolkit for Virtualization")
    while True:
        try:
            choice = input("Enter 1 or 2 (or cnv/mtv): ").strip().lower()
        except EOFError:
            print("\nError: project required. Use --project cnv or --project mtv.")
            sys.exit(1)
        if choice in ("1", "cnv"):
            return "CNV"
        if choice in ("2", "mtv"):
            return "MTV"
        print("Invalid choice. Enter 1, 2, cnv, or mtv.")


def resolve_project_for_run(
    *,
    project_arg: str | None,
    issue_key: str | None,
    batch_new: bool,
    force_prompt: bool,
) -> str:
    if project_arg:
        return normalize_project(project_arg)  # type: ignore[return-value]

    if force_prompt and sys.stdin.isatty():
        return prompt_for_project()

    if batch_new:
        if sys.stdin.isatty():
            return prompt_for_project()
        print("Error: --new requires --project cnv or --project mtv in non-interactive mode.")
        sys.exit(1)

    detected = project_from_issue_key(issue_key)
    if detected:
        return detected

    if sys.stdin.isatty():
        return prompt_for_project()

    print("Error: could not detect project from issue key. Use --project cnv or --project mtv.")
    sys.exit(1)


def fetch_issue(issue_key: str) -> dict:
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key.upper()}"
    r = requests.get(
        url,
        params={"fields": FETCH_FIELDS},
        auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
        timeout=60,
    )
    if r.status_code != 200:
        print(f"Error fetching {issue_key}: {r.status_code}\n{r.text}")
        sys.exit(1)
    return r.json()


def search_new_rfes(project: str, max_results: int = 50) -> list[str]:
    jql = (
        f'project = {project} AND issuetype = "Feature Request" '
        f'AND status = New ORDER BY created DESC'
    )
    r = requests.get(
        f"{JIRA_URL}/rest/api/3/search/jql",
        params={"jql": jql, "maxResults": max_results, "fields": "key"},
        auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
        timeout=60,
    )
    if r.status_code != 200:
        print(f"Error searching {project} RFEs: {r.status_code}\n{r.text}")
        sys.exit(1)
    return [issue["key"] for issue in r.json().get("issues", [])]


def detect_description_sections(description: str) -> dict[str, bool]:
    found = {name: False for name, _ in DESCRIPTION_SECTIONS}
    if not description:
        return found
    for line in description.splitlines():
        stripped = line.strip().lstrip("#").strip()
        for name, pattern in DESCRIPTION_SECTIONS:
            if pattern.search(stripped):
                found[name] = True
    return found


def user_display(field_value) -> str | None:
    if not field_value:
        return None
    return field_value.get("displayName") or field_value.get("name")


def analyze_issue(data: dict, expected_project: str | None = None) -> dict:
    fields = data["fields"]
    desc_raw = fields.get("description")
    description = extract_text_from_adf(desc_raw).strip() if desc_raw else ""
    sections = detect_description_sections(description)

    links = fields.get("issuelinks", [])
    cipoe_links, virtstrat_links, other_links = [], [], []
    for link in links:
        target = link.get("outwardIssue") or link.get("inwardIssue")
        if not target:
            continue
        key = target.get("key", "")
        entry = {"key": key, "summary": target.get("fields", {}).get("summary", "")}
        if key.startswith("CIPOE"):
            cipoe_links.append(entry)
        elif key.startswith("VIRTSTRAT"):
            virtstrat_links.append(entry)
        else:
            other_links.append(entry)

    project_key = (fields.get("project") or {}).get("key", "")
    issue_type = (fields.get("issuetype") or {}).get("name", "")

    info = {
        "key": data["key"],
        "summary": fields.get("summary", "N/A"),
        "status": fields.get("status", {}).get("name", "N/A"),
        "priority": fields.get("priority", {}).get("name", "N/A"),
        "assignee": user_display(fields.get("assignee")) or "Unassigned",
        "architect": user_display(fields.get(ARCHITECT_FIELD)) or "Unset",
        "components": [c.get("name", "") for c in fields.get("components", [])],
        "issue_type": issue_type,
        "project": project_key,
        "description": description,
        "sections": sections,
        "cipoe_links": cipoe_links,
        "virtstrat_links": virtstrat_links,
        "other_links": other_links,
        "rank_set": bool(fields.get(RANK_FIELD)),
        "expected_project": expected_project or project_key,
    }
    info["scores"] = compute_rfe_scores(info)
    info["feedback"] = build_feedback(info)
    return info


def compute_rfe_scores(info: dict) -> dict:
    desc = info.get("description", "")
    desc_lower = desc.lower()
    sec = info["sections"]
    project = info.get("project", "CNV")
    need_re = PROJECT_CONFIG.get(project, PROJECT_CONFIG["CNV"])["need_patterns"]
    need_signals = bool(need_re.search(desc))

    if not desc or len(desc) < 80:
        what_score, what_note = 0, "Missing or very short description"
    elif (sec.get("overview") or sec.get("goal")) and len(desc) > 200 and need_signals:
        what_score, what_note = 2, "Clear need with Overview/Goal context"
    elif len(desc) > 250 and need_signals:
        what_score, what_note = 2, "Specific customer/user need described"
    elif len(desc) > 120:
        what_score, what_note = 1, "Need described but ambiguous or missing Overview/Goal"
    else:
        what_score, what_note = 0, "Vague or unclear customer need"

    if info["cipoe_links"]:
        keys = ", ".join(link["key"] for link in info["cipoe_links"][:3])
        why_score, why_note = 2, f"CIPOE linked ({keys})"
    elif re.search(r"customer|account|enterprise|deal|revenue|named", desc_lower):
        why_score, why_note = 1, "Named need in text; link CIPOE for evidence"
    elif re.search(r"market|segment|analyst|competitive|strategy", desc_lower):
        why_score, why_note = 1, "Generic market/strategy language only"
    else:
        why_score, why_note = 0, "No customer evidence or business justification"

    prescriptive_hits = sum(1 for p in PRESCRIPTIVE_PATTERNS if p.search(desc))
    if prescriptive_hits >= 2:
        how_score, how_note = 0, "Mandates implementation/architecture choices"
    elif prescriptive_hits == 1:
        how_score, how_note = 1, "Leans into implementation details"
    elif re.search(r"api|ui|cli|metric|prometheus|dashboard|wizard", desc_lower):
        how_score, how_note = 2, "Customer-facing need; HOW left to engineering"
    elif len(desc) > 150:
        how_score, how_note = 2, "Describes need without prescribing architecture"
    else:
        how_score, how_note = 1, "Limited detail; verify no HOW prescription"

    task_hits = sum(1 for p in TASK_PATTERNS if p.search(desc))
    business_signals = bool(
        re.search(r"enable|allow|support|provide|customer|business value|reduce|improve experience", desc_lower)
    )
    if task_hits >= 2 and not business_signals:
        task_score, task_note = 0, "Reads as chore/tech debt, not business need"
    elif task_hits == 1 and business_signals:
        task_score, task_note = 1, "Borderline — mixes maintenance with user value"
    elif business_signals or info["cipoe_links"]:
        task_score, task_note = 2, "Clear business need"
    elif len(desc) > 100:
        task_score, task_note = 1, "Borderline — clarify business outcome"
    else:
        task_score, task_note = 0, "Insufficient business framing"

    bundle_hits = sum(1 for p in BUNDLE_PATTERNS if p.search(desc))
    bullet_sections = len(re.findall(r"^\s*[-*]\s+", desc, re.M))
    if bundle_hits >= 2 or bullet_sections >= 6:
        size_score, size_note = 0, "Multiple independent features bundled"
    elif bundle_hits == 1 or bullet_sections >= 4:
        size_score, size_note = 1, "May bundle 1–2 separable features"
    else:
        size_score, size_note = 2, "Focused single need"

    criteria = {
        "what": {"label": "WHAT", "score": what_score, "note": what_note},
        "why": {"label": "WHY", "score": why_score, "note": why_note},
        "open_to_how": {"label": "Open to HOW", "score": how_score, "note": how_note},
        "not_a_task": {"label": "Not a task", "score": task_score, "note": task_note},
        "right_sized": {"label": "Right-sized", "score": size_score, "note": size_note},
    }
    total = sum(c["score"] for c in criteria.values())
    has_zero = any(c["score"] == 0 for c in criteria.values())
    passed = total >= 7 and not has_zero
    return {
        "criteria": criteria,
        "total": total,
        "max": 10,
        "pass": passed,
        "verdict": "PASS" if passed else "FAIL",
    }


def build_feedback(info: dict) -> list[str]:
    scores = info["scores"]
    criteria = scores["criteria"]
    feedback: list[str] = []

    if criteria["why"]["score"] < 2:
        feedback.append(
            "Add a CIPOE link to provide named customer evidence (preferred for WHY scoring)."
        )
    if criteria["what"]["score"] < 2:
        feedback.append(
            "Add Overview and Goal sections with a specific user/customer problem statement."
        )
    if criteria["open_to_how"]["score"] < 2:
        feedback.append(
            "Describe the business need without mandating internal architecture or implementation."
        )
    if criteria["not_a_task"]["score"] < 2:
        feedback.append("Reframe as a business outcome rather than an engineering chore.")
    if criteria["right_sized"]["score"] < 2:
        feedback.append("Split bundled capabilities into separate Feature Requests (~one feature each).")

    if info["status"] == "New":
        if info["assignee"] == "Unassigned":
            feedback.append("Assign a PM (required before exiting New).")
        if info["priority"] in ("Undefined", "N/A"):
            feedback.append("Set priority.")
        if not info["components"]:
            feedback.append("Set component(s).")
        if not info["cipoe_links"]:
            feedback.append("Link CIPOE before moving to Refinement (playbook exit criteria).")

    if info["status"] == "Refinement" and not info["virtstrat_links"]:
        feedback.append("Create and link a VIRTSTRAT Feature before exiting Refinement.")

    if scores["verdict"] == "PASS" and not feedback:
        feedback.append("RFE meets quality bar; minor polish on description structure is optional.")

    return feedback


def format_assessment_markdown(info: dict) -> str:
    scores = info["scores"]
    criteria = scores["criteria"]
    order = ("what", "why", "open_to_how", "not_a_task", "right_sized")
    project = info.get("project", "RFE")
    marker = comment_marker(project)

    lines = [
        f"## {marker}",
        "",
        f"**{info['key']}** — {info['summary']}",
        "",
        "| Criterion | Score | Notes |",
        "|-----------|-------|-------|",
    ]
    for key in order:
        c = criteria[key]
        lines.append(f"| {c['label']} | {c['score']}/2 | {c['note']} |")
    lines.append(f"| **Total** | **{scores['total']}/10** | **{scores['verdict']}** |")
    lines.append("")
    lines.append("### Verdict")
    if scores["verdict"] == "PASS":
        lines.append(
            f"This {project} RFE scores {scores['total']}/10 and meets the quality bar for refinement."
        )
    else:
        zeros = [criteria[k]["label"] for k in order if criteria[k]["score"] == 0]
        if zeros:
            lines.append(
                f"This {project} RFE scores {scores['total']}/10 and **fails** (zero on: {', '.join(zeros)})."
            )
        else:
            lines.append(
                f"This {project} RFE scores {scores['total']}/10 and **fails** (below 7/10 threshold)."
            )

    lines.extend(["", "### Links"])
    if info["cipoe_links"]:
        lines.append(f"- CIPOE: {', '.join(l['key'] for l in info['cipoe_links'])}")
    else:
        lines.append("- CIPOE: none")
    if info["virtstrat_links"]:
        lines.append(f"- VIRTSTRAT: {', '.join(l['key'] for l in info['virtstrat_links'])}")
    else:
        lines.append("- VIRTSTRAT: none")

    lines.extend(["", "### Feedback"])
    for item in info["feedback"]:
        lines.append(f"- {item}")

    lines.extend(["", "---", "*Assessment generated via Claude AI assistant.*"])
    return "\n".join(lines)


def print_assessment_display(info: dict) -> None:
    scores = info["scores"]
    criteria = scores["criteria"]
    order = ("what", "why", "open_to_how", "not_a_task", "right_sized")
    project = info.get("project", "RFE")
    project_label = PROJECT_CONFIG.get(project, {}).get("label", project)

    print("=" * 72)
    print(f"{project} RFE ASSESSMENT: {info['key']}")
    print("=" * 72)
    print()
    print("ISSUE DETAILS")
    print("-" * 40)
    print(f"Project:     {project_label}")
    print(f"Summary:     {info['summary']}")
    print(f"Status:      {info['status']}")
    print(f"Type:        {info['issue_type']}")
    print(f"Priority:    {info['priority']}")
    print(f"Assignee:    {info['assignee']}")
    print(f"Architect:   {info['architect']}")
    print(f"Components:  {', '.join(info['components']) or 'None'}")
    expected = info.get("expected_project")
    if expected and info["project"] != expected:
        print(f"⚠️  Project mismatch: issue is {info['project']}, expected {expected}")
    if info["issue_type"] != "Feature Request":
        print(f"⚠️  Issue type: {info['issue_type']} (expected Feature Request)")
    print()

    print("DESCRIPTION PREVIEW")
    print("-" * 40)
    preview = info["description"][:800]
    if len(info["description"]) > 800:
        preview += "\n... [truncated]"
    print(preview or "(empty)")
    print()

    print("LINKS")
    print("-" * 40)
    if info["cipoe_links"]:
        print(f"  ✅ CIPOE: {len(info['cipoe_links'])}")
        for link in info["cipoe_links"][:5]:
            print(f"     - {link['key']}: {link['summary'][:55]}")
    else:
        print("  ❌ CIPOE: 0 (no customer evidence)")
    if info["virtstrat_links"]:
        print(f"  ✅ VIRTSTRAT: {len(info['virtstrat_links'])}")
        for link in info["virtstrat_links"][:3]:
            print(f"     - {link['key']}: {link['summary'][:55]}")
    else:
        print("  ⚠️  VIRTSTRAT: 0 (needed before exiting Refinement)")
    print()

    print("QUALITY SCORING")
    print("-" * 40)
    print("  0 = Does not meet | 1 = Partial | 2 = Fully meets")
    print("  PASS: >= 7/10 AND no zeros on any criterion")
    print()
    print("┌─────────────────┬───────┬────────────────────────────────────────────┐")
    print("│ Criterion       │ Score │ Notes                                      │")
    print("├─────────────────┼───────┼────────────────────────────────────────────┤")
    for i, key in enumerate(order):
        c = criteria[key]
        note = c["note"][:42]
        print(f"│ {c['label']:<15} │ {c['score']}/2   │ {note:<42} │")
        if i < len(order) - 1:
            print("├─────────────────┼───────┼────────────────────────────────────────────┤")
    print("├─────────────────┼───────┼────────────────────────────────────────────┤")
    print(f"│ TOTAL           │ {scores['total']}/10 │ {scores['verdict']:<42} │")
    print("└─────────────────┴───────┴────────────────────────────────────────────┘")
    print()

    print("FEEDBACK")
    print("-" * 40)
    for item in info["feedback"]:
        print(f"  • {item}")
    print()
    print(f"Playbook: {PLAYBOOK}")
    print("Skill: .cursor/skills/rfe-quality-check-vme/SKILL.md")


def check_state_exit_criteria(info: dict, target_state: str) -> None:
    target = STATE_ALIASES.get(target_state.lower(), target_state.lower())
    print("=" * 72)
    print(f"STATE TRANSITION CHECK: {info['key']}")
    print("=" * 72)
    print(f"Current State: {info['status']}")
    print(f"Target State:  {target.title()}")
    print()

    checks: list[tuple[str, bool, str]] = []
    sla = ""

    if target == "refinement":
        checks = [
            ("PM identified (Assignee)", info["assignee"] != "Unassigned", info["assignee"]),
            ("Priority set", info["priority"] not in ("Undefined", "N/A"), info["priority"]),
            ("Component set", len(info["components"]) > 0, ", ".join(info["components"]) or "None"),
            ("CIPOE linked", len(info["cipoe_links"]) > 0, f"{len(info['cipoe_links'])} link(s)"),
            (
                "Overview/Goal in description",
                info["sections"]["overview"] or info["sections"]["goal"],
                "section detected",
            ),
            ("Description has content", len(info["description"]) > 50, f"{len(info['description'])} chars"),
        ]
        sla = "5 business days (NEW → REFINEMENT)"
    elif target == "in progress":
        checks = [
            ("PM identified", info["assignee"] != "Unassigned", info["assignee"]),
            ("Architect set", info["architect"] != "Unset", info["architect"]),
            ("VIRTSTRAT Feature linked", len(info["virtstrat_links"]) > 0, f"{len(info['virtstrat_links'])} link(s)"),
            ("CIPOE linked (as needed)", len(info["cipoe_links"]) > 0, f"{len(info['cipoe_links'])} link(s)"),
            ("Rank set", info["rank_set"], "Rank field"),
            ("Priority set", info["priority"] not in ("Undefined", "N/A"), info["priority"]),
            ("Component set", len(info["components"]) > 0, ", ".join(info["components"]) or "None"),
        ]
        sla = "14 business days (REFINEMENT → IN PROGRESS)"
    elif target == "closed":
        checks = [
            ("VIRTSTRAT Feature linked", len(info["virtstrat_links"]) > 0, f"{len(info['virtstrat_links'])} link(s)"),
        ]
        sla = "4–12 months (IN PROGRESS → CLOSED; verify linked Feature Done manually)"
    else:
        print(f"Unknown target state: {target_state}")
        print("Valid: refinement, in progress, closed")
        return

    print("EXIT CRITERIA CHECK")
    print("-" * 40)
    blockers = []
    for name, met, detail in checks:
        mark = "✅" if met else "❌"
        print(f"{mark} {name}: {detail}")
        if not met:
            blockers.append(name)

    print()
    print(f"SLA: {sla}")
    print()
    if blockers:
        print(f"❌ NOT READY — {len(blockers)} blocker(s):")
        for b in blockers:
            print(f"   - {b}")
    else:
        print(f"✅ READY (automated checks) to move toward {target.title()}")


def has_existing_assessment_comment(issue_key: str, project: str) -> bool:
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/comment"
    r = requests.get(
        url,
        params={"maxResults": 50, "orderBy": "-created"},
        auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
        timeout=60,
    )
    if r.status_code != 200:
        return False
    markers = {comment_marker(project), "RFE Quality Assessment"}
    for comment in r.json().get("comments", []):
        text = extract_text_from_adf(comment.get("body", {}))
        if any(marker in text for marker in markers):
            return True
    return False


def post_assessment_comment(issue_key: str, markdown_body: str) -> None:
    url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/comment"
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": markdown_body}],
                }
            ],
        },
        "visibility": {"type": "group", "value": "Red Hat Employee"},
    }
    r = requests.post(
        url,
        auth=HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if r.status_code >= 400:
        try:
            msg = r.json()
        except Exception:
            msg = r.text
        print(f"Error posting comment on {issue_key}: {r.status_code} {msg}")
        sys.exit(1)


def assess_and_output(
    issue_key: str,
    *,
    expected_project: str | None = None,
    as_json: bool = False,
    check_state: str | None = None,
    output_path: Path | None = None,
    comment: bool = False,
    execute: bool = False,
    skip_existing_comment: bool = True,
) -> dict:
    data = fetch_issue(issue_key)
    info = analyze_issue(data, expected_project=expected_project)

    if as_json:
        out = {k: v for k, v in info.items() if k != "description"}
        out["description_length"] = len(info["description"])
        out["has_cipoe"] = bool(info["cipoe_links"])
        out["has_virtstrat"] = bool(info["virtstrat_links"])
        print(json.dumps(out, indent=2))
    elif check_state:
        print_assessment_display(info)
        print()
        check_state_exit_criteria(info, check_state)
    else:
        print_assessment_display(info)

    markdown = format_assessment_markdown(info)
    if output_path:
        output_path.write_text(markdown + "\n", encoding="utf-8")
        print(f"\nWrote assessment to {output_path}")

    if comment:
        project = info.get("project", "RFE")
        if skip_existing_comment and has_existing_assessment_comment(info["key"], project):
            print(f"\n⏭ Skipped comment on {info['key']} (assessment comment already exists)")
        elif not execute:
            print(f"\n--- COMMENT PREVIEW ({info['key']}) ---")
            print(markdown)
            print("--- END PREVIEW ---")
            print("Run with --comment --execute to post this comment to Jira.")
        else:
            post_assessment_comment(info["key"], markdown)
            print(f"\n✓ Posted assessment comment on {info['key']} (Red Hat Employee visibility)")

    return info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assess CNV or MTV Virt Feature Request (RFE) quality — draft, display, or comment"
    )
    parser.add_argument(
        "issue_key",
        nargs="?",
        help="Issue key (e.g. CNV-12345 or MTV-5653). Omit when using --new.",
    )
    parser.add_argument(
        "--project",
        choices=["cnv", "mtv", "CNV", "MTV"],
        help="Project for batch mode or when key prefix is ambiguous (auto-detected from CNV-* / MTV-*)",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help='Assess all Feature Requests in status "New" for the chosen project',
    )
    parser.add_argument(
        "--ask-project",
        action="store_true",
        help="Prompt for CNV or MTV even when the issue key would auto-detect project",
    )
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    parser.add_argument(
        "--check-state",
        metavar="STATE",
        help="Check exit criteria (refinement, in progress, closed)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write assessment markdown to file (draft mode)",
    )
    parser.add_argument(
        "--comment",
        action="store_true",
        help="Include Jira comment (preview unless --execute)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="With --comment, post comment to Jira (default is draft/preview only)",
    )
    parser.add_argument(
        "--force-comment",
        action="store_true",
        help="Post comment even if an assessment comment already exists",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max issues when using --new (default: 50)",
    )
    args = parser.parse_args()

    require_credentials()

    project = resolve_project_for_run(
        project_arg=args.project,
        issue_key=args.issue_key,
        batch_new=args.new,
        force_prompt=args.ask_project,
    )

    output_path = Path(args.output) if args.output else None
    skip_existing = not args.force_comment

    if args.new:
        keys = search_new_rfes(project, max_results=args.limit)
        if not keys:
            print(f"No {project} Feature Requests in New status.")
            return
        print(f"Found {len(keys)} {project} RFE(s) in New status.\n")
        pass_count = 0
        for i, key in enumerate(keys, 1):
            if len(keys) > 1:
                print(f"\n{'#' * 72}\n# [{i}/{len(keys)}] {key}\n{'#' * 72}\n")
            info = assess_and_output(
                key,
                expected_project=project,
                as_json=args.json and len(keys) == 1,
                check_state=args.check_state,
                output_path=output_path if len(keys) == 1 else None,
                comment=args.comment,
                execute=args.execute,
                skip_existing_comment=skip_existing,
            )
            if info["scores"]["verdict"] == "PASS":
                pass_count += 1
        if len(keys) > 1 and not args.json:
            print(f"\nSummary: {pass_count}/{len(keys)} PASS, {len(keys) - pass_count}/{len(keys)} FAIL")
        return

    if not args.issue_key:
        parser.error("issue_key is required unless --new is used")

    assess_and_output(
        args.issue_key,
        expected_project=project if args.project or args.ask_project else None,
        as_json=args.json,
        check_state=args.check_state,
        output_path=output_path,
        comment=args.comment,
        execute=args.execute,
        skip_existing_comment=skip_existing,
    )


if __name__ == "__main__":
    main()
