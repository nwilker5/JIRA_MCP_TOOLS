#!/usr/bin/env python3
"""
Inventory issues in a Jira Plan (Advanced Roadmaps) timeline view, filtered by
project, component, and/or label.

Uses the same internal JPO APIs the Plans UI calls (not the admin-only Plans
CRUD API). Requires the acting user's own Jira API token.

Example:
  python3 jira_plan_inventory.py \\
    --url 'https://redhat.atlassian.net/jira/plans/3019/scenarios/3020/timeline?vid=2908' \\
    --project OCPSTRAT \\
    --component Networking \\
    --include-parents
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from requests.auth import HTTPBasicAuth

PLAN_URL_RE = re.compile(
    r"/jira/plans/(?P<plan>\d+)/scenarios/(?P<scenario>\d+)",
    re.I,
)


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def jira_user() -> str:
    user = os.environ.get("JIRA_USERNAME") or os.environ.get("JIRA_EMAIL")
    if not user:
        print("Error: set JIRA_USERNAME or JIRA_EMAIL.", file=sys.stderr)
        sys.exit(1)
    return user


def jira_config() -> tuple[str, HTTPBasicAuth]:
    url = os.environ.get("JIRA_URL", "").rstrip("/")
    token = os.environ.get("JIRA_API_TOKEN", "")
    missing = [k for k, v in [("JIRA_URL", url), ("JIRA_API_TOKEN", token)] if not v]
    if missing:
        print(f"Error: missing {', '.join(missing)}.", file=sys.stderr)
        print(
            "Copy env.jira.example to .env_jira and add your own credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def parse_plan_url(url: str) -> tuple[int, int, int | None]:
    m = PLAN_URL_RE.search(url)
    if not m:
        raise ValueError(
            "URL must look like .../jira/plans/{planId}/scenarios/{scenarioId}/...?vid={viewId}"
        )
    plan_id = int(m.group("plan"))
    scenario_id = int(m.group("scenario"))
    qs = parse_qs(urlparse(url).query)
    view_id = int(qs["vid"][0]) if qs.get("vid") else None
    return plan_id, scenario_id, view_id


def jpo_get(s: requests.Session, base: str, auth: HTTPBasicAuth, path: str) -> Any:
    r = s.get(
        f"{base}{path}",
        auth=auth,
        headers={"Accept": "application/json", "X-Atlassian-Token": "no-check"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def jpo_post(
    s: requests.Session, base: str, auth: HTTPBasicAuth, path: str, body: dict
) -> Any:
    r = s.post(
        f"{base}{path}",
        auth=auth,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Atlassian-Token": "no-check",
        },
        json=body,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def resolve_projects(
    s: requests.Session, base: str, auth: HTTPBasicAuth, project_ids: set[Any]
) -> dict[Any, str]:
    out: dict[Any, str] = {}
    for pid in project_ids:
        if pid is None:
            continue
        r = s.get(
            f"{base}/rest/api/3/project/{pid}",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if r.ok:
            out[pid] = r.json().get("key", str(pid))
        else:
            out[pid] = str(pid)
    return out


def resolve_issue_types(
    s: requests.Session, base: str, auth: HTTPBasicAuth, type_ids: set[Any]
) -> dict[Any, str]:
    out: dict[Any, str] = {}
    for tid in type_ids:
        if tid is None:
            continue
        r = s.get(
            f"{base}/rest/api/3/issuetype/{tid}",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if r.ok:
            out[tid] = r.json().get("name", str(tid))
            out[str(tid)] = out[tid]
        else:
            out[tid] = str(tid)
            out[str(tid)] = str(tid)
    return out


def resolve_components(
    s: requests.Session, base: str, auth: HTTPBasicAuth, component_ids: set[Any]
) -> dict[Any, str]:
    """Best-effort: component IDs are not always resolvable without project context."""
    out: dict[Any, str] = {}
    for cid in component_ids:
        if cid is None:
            continue
        r = s.get(
            f"{base}/rest/api/3/component/{cid}",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if r.ok:
            name = r.json().get("name", str(cid))
            out[cid] = name
            out[str(cid)] = name
        else:
            out[cid] = str(cid)
            out[str(cid)] = str(cid)
    return out


def hierarchy_type_to_level(meta: dict) -> dict[Any, int]:
    mapping: dict[Any, int] = {}
    for lvl in (meta.get("hierarchy") or {}).get("levels") or []:
        level = lvl.get("level")
        for t in lvl.get("issueTypes") or []:
            mapping[int(t)] = level
            mapping[str(t)] = level
    return mapping


def view_hierarchy_range(view: dict | None) -> tuple[int, int] | None:
    if not view:
        return None
    prefs = view.get("preferences") or {}
    filters = prefs.get("filtersV1") or {}
    hr = filters.get("state.domain.view-settings.filters.HIERARCHY_RANGE_FILTER_ID") or {}
    value = hr.get("value") if isinstance(hr, dict) else None
    if isinstance(value, dict) and "start" in value and "end" in value:
        return int(value["start"]), int(value["end"])
    return None


def matches_criteria(
    item: dict,
    *,
    projects: set[str] | None,
    labels: set[str] | None,
    components: set[str] | None,
    component_ids: set[str] | None,
) -> bool:
    if projects and item["project"] not in projects:
        return False
    if labels:
        item_labels = {str(x) for x in (item.get("labels") or [])}
        if not labels.intersection(item_labels):
            return False
    if components or component_ids:
        names = {str(x).lower() for x in (item.get("component_names") or [])}
        ids = {str(x) for x in (item.get("component_ids") or [])}
        ok = False
        if components and any(c.lower() in names for c in components):
            ok = True
        if component_ids and component_ids.intersection(ids):
            ok = True
        if not ok:
            return False
    return True


def build_items(
    issues: list[dict],
    proj_map: dict[Any, str],
    type_map: dict[Any, str],
    type_to_level: dict[Any, int],
    comp_map: dict[Any, str],
) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for iss in issues:
        jv = iss.get("jiraValues") or {}
        pid = jv.get("project")
        num = iss.get("issueKey")
        project_key = proj_map.get(pid, str(pid))
        iid = str(iss["id"])
        type_id = jv.get("type")
        comp_ids = jv.get("components") or []
        parent = jv.get("parent")
        by_id[iid] = {
            "id": iid,
            "key": f"{project_key}-{num}",
            "summary": jv.get("summary") or "",
            "project": project_key,
            "type_id": type_id,
            "type": type_map.get(type_id, type_map.get(str(type_id), str(type_id))),
            "level": type_to_level.get(type_id, type_to_level.get(str(type_id))),
            "labels": jv.get("labels") or [],
            "component_ids": comp_ids,
            "component_names": [comp_map.get(c, comp_map.get(str(c), str(c))) for c in comp_ids],
            "parent": str(parent) if parent is not None else None,
            "excluded": bool(jv.get("excluded")),
            "status": jv.get("status"),
        }
    return by_id


def parents_of_matches(by_id: dict[str, dict], match_ids: set[str]) -> list[dict]:
    """Return unique parent issues (any project) of matched items."""
    parents: dict[str, dict] = {}
    for iid in match_ids:
        item = by_id[iid]
        pid = item.get("parent")
        if pid and pid in by_id and pid not in match_ids:
            parents[pid] = by_id[pid]
    return sorted(parents.values(), key=lambda x: x["key"])


def format_report(
    *,
    plan: dict,
    view: dict | None,
    plan_id: int,
    scenario_id: int,
    view_id: int | None,
    matched: list[dict],
    parent_outcomes: list[dict],
    criteria: dict,
) -> str:
    lines: list[str] = []
    view_name = (view or {}).get("name") or "(default / unspecified)"
    lines.append(f"# Plan inventory — {plan.get('title')}")
    lines.append("")
    lines.append(f"- Plan ID: `{plan_id}`")
    lines.append(f"- Scenario ID: `{scenario_id}`")
    lines.append(f"- View: `{view_id}` — {view_name}")
    hr = view_hierarchy_range(view)
    if hr:
        lines.append(f"- View hierarchy range (AR levels): `{hr[0]}` → `{hr[1]}`")
    lines.append(f"- Criteria: `{json.dumps(criteria)}`")
    lines.append("")

    by_type = Counter(i["type"] for i in matched)
    by_project = Counter(i["project"] for i in matched)
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Matched issues in plan backlog: **{len(matched)}**")
    lines.append(f"- By type: {dict(by_type)}")
    lines.append(f"- By project: {dict(by_project)}")
    if parent_outcomes:
        lines.append(
            f"- Parent issues of matches (other keys, often Outcomes): **{len(parent_outcomes)}**"
        )
    lines.append("")
    lines.append(
        "> Note: Issue type **Outcome** may live in HPSTRAT (or another strat project) "
        "while Features live in your product project. Count both if the UI shows a hierarchy."
    )
    lines.append("")

    if parent_outcomes:
        lines.append("## Parent issues of matches")
        lines.append("")
        lines.append("| Key | Type | Project | Summary |")
        lines.append("|-----|------|---------|---------|")
        for p in parent_outcomes:
            lines.append(
                f"| {p['key']} | {p['type']} | {p['project']} | {p['summary'].replace('|', '/')} |"
            )
        lines.append("")

    lines.append("## Matched issues")
    lines.append("")
    for type_name, _ in by_type.most_common():
        group = [i for i in matched if i["type"] == type_name]
        lines.append(f"### {type_name} ({len(group)})")
        lines.append("")
        lines.append("| Key | Project | Labels | Components | Summary |")
        lines.append("|-----|---------|--------|------------|---------|")
        for i in group:
            labels = ", ".join(i["labels"]) if i["labels"] else "—"
            comps = ", ".join(i["component_names"]) if i["component_names"] else "—"
            lines.append(
                f"| {i['key']} | {i['project']} | {labels} | {comps} | "
                f"{i['summary'].replace('|', '/')} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List issues in a Jira Plan view matching project/label/component criteria."
    )
    parser.add_argument("--url", help="Full plan timeline URL (preferred)")
    parser.add_argument("--plan-id", type=int)
    parser.add_argument("--scenario-id", type=int)
    parser.add_argument("--view-id", type=int)
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Project key to include (repeatable), e.g. OCPSTRAT",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="Label that must be present (repeatable; OR across labels)",
    )
    parser.add_argument(
        "--component",
        action="append",
        default=[],
        help="Component name that must be present (repeatable; case-insensitive OR)",
    )
    parser.add_argument(
        "--component-id",
        action="append",
        default=[],
        help="Component ID that must be present (repeatable)",
    )
    parser.add_argument(
        "--include-parents",
        action="store_true",
        help="Also list parent issues of matches (often Outcomes in another project)",
    )
    parser.add_argument(
        "--apply-view-hierarchy",
        action="store_true",
        help="Restrict to hierarchy levels configured on the saved view",
    )
    parser.add_argument(
        "--env-file",
        default=".env_jira",
        help="Credentials file (default: .env_jira)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("-o", "--output", help="Write report to file")
    args = parser.parse_args()

    # Resolve env: skill example, then cwd .env_jira / named file
    skill_root = Path(__file__).resolve().parents[1]
    for candidate in (
        Path(args.env_file),
        Path.cwd() / args.env_file,
        Path.cwd() / ".env_jira",
        skill_root / "env.jira.example",
    ):
        load_env_file(candidate)

    if args.url:
        plan_id, scenario_id, view_id = parse_plan_url(args.url)
        if args.view_id:
            view_id = args.view_id
    else:
        if not args.plan_id or not args.scenario_id:
            parser.error("Provide --url or both --plan-id and --scenario-id")
        plan_id, scenario_id, view_id = args.plan_id, args.scenario_id, args.view_id

    projects = {p.upper() for p in args.project} or None
    labels = set(args.label) or None
    components = set(args.component) or None
    component_ids = {str(x) for x in args.component_id} or None
    if not any([projects, labels, components, component_ids]):
        parser.error(
            "Provide at least one of --project, --label, --component, --component-id"
        )

    base, auth = jira_config()
    s = session()

    plan = jpo_get(s, base, auth, f"/rest/jpo/1.0/plans/{plan_id}")
    meta = jpo_post(
        s,
        base,
        auth,
        "/rest/jpo/1.0/info/metadata",
        {"planId": plan_id, "scenarioId": scenario_id},
    )
    backlog = jpo_post(
        s,
        base,
        auth,
        "/rest/jpo/1.0/backlog",
        {
            "planId": plan_id,
            "scenarioId": scenario_id,
            "filter": {
                "includeCompleted": True,
                "includeIssueLinks": True,
                "performDependencyCompletion": False,
            },
        },
    )

    views = (meta.get("savedViewsInfoFull") or {}).get("savedViews") or []
    view = next((v for v in views if view_id and v.get("id") == view_id), None)
    if view_id and view is None:
        print(f"Warning: view {view_id} not found in plan saved views.", file=sys.stderr)

    issues = backlog.get("issues") or []
    project_ids = {(iss.get("jiraValues") or {}).get("project") for iss in issues}
    type_ids = {(iss.get("jiraValues") or {}).get("type") for iss in issues}

    proj_map = resolve_projects(s, base, auth, project_ids)
    type_map = resolve_issue_types(s, base, auth, type_ids)
    type_to_level = hierarchy_type_to_level(meta)

    # First pass: build items without resolving component names (ids only).
    by_id = build_items(issues, proj_map, type_map, type_to_level, {})

    # Optional hierarchy clip from saved view
    level_lo = level_hi = None
    if args.apply_view_hierarchy:
        hr = view_hierarchy_range(view)
        if hr:
            level_lo, level_hi = min(hr), max(hr)

    # If filtering by component *name*, resolve only enough components to decide matches.
    # Prefer matching by id when --component-id is used (no bulk lookup).
    comp_map: dict[Any, str] = {}
    if components:
        # Collect component ids from project-filtered candidates first to limit lookups.
        candidate_comp_ids: set[Any] = set()
        for item in by_id.values():
            if projects and item["project"] not in projects:
                continue
            if labels:
                item_labels = {str(x) for x in (item.get("labels") or [])}
                if not labels.intersection(item_labels):
                    continue
            for c in item.get("component_ids") or []:
                candidate_comp_ids.add(c)
        comp_map = resolve_components(s, base, auth, candidate_comp_ids)
        for item in by_id.values():
            item["component_names"] = [
                comp_map.get(c, comp_map.get(str(c), str(c)))
                for c in (item.get("component_ids") or [])
            ]

    matched: list[dict] = []
    match_ids: set[str] = set()
    for iid, item in by_id.items():
        if level_lo is not None and item.get("level") is not None:
            if not (level_lo <= item["level"] <= level_hi):
                continue
        if matches_criteria(
            item,
            projects=projects,
            labels=labels,
            components=components,
            component_ids=component_ids,
        ):
            matched.append(item)
            match_ids.add(iid)

    # Resolve component names only for matched rows + parents (for display).
    display_ids: set[Any] = set()
    for item in matched:
        display_ids.update(item.get("component_ids") or [])
    parent_outcomes = parents_of_matches(by_id, match_ids) if args.include_parents else []
    for p in parent_outcomes:
        display_ids.update(p.get("component_ids") or [])
    missing = {c for c in display_ids if c not in comp_map and str(c) not in comp_map}
    if missing:
        comp_map.update(resolve_components(s, base, auth, missing))
    for item in matched + parent_outcomes:
        item["component_names"] = [
            comp_map.get(c, comp_map.get(str(c), str(c)))
            for c in (item.get("component_ids") or [])
        ]

    matched.sort(key=lambda x: (x["type"], x["project"], x["key"]))

    criteria = {
        "projects": sorted(projects) if projects else None,
        "labels": sorted(labels) if labels else None,
        "components": sorted(components) if components else None,
        "component_ids": sorted(component_ids) if component_ids else None,
        "apply_view_hierarchy": args.apply_view_hierarchy,
    }

    if args.json:
        payload = {
            "plan": {"id": plan_id, "title": plan.get("title"), "scenarioId": scenario_id},
            "view": {"id": view_id, "name": (view or {}).get("name")},
            "criteria": criteria,
            "matched": matched,
            "parents": parent_outcomes,
        }
        text = json.dumps(payload, indent=2)
    else:
        text = format_report(
            plan=plan,
            view=view,
            plan_id=plan_id,
            scenario_id=scenario_id,
            view_id=view_id,
            matched=matched,
            parent_outcomes=parent_outcomes,
            criteria=criteria,
        )

    if args.output:
        Path(args.output).write_text(text)
        print(f"Wrote {args.output}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
