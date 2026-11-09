#!/usr/bin/env python3
"""
CNV rogue component investigator.

1) Diff the live CNV component catalog against the expected allowlist.
2) For named suspects (or catalog extras), find the earliest Component-field
   assignment via issue changelogs, and show who / when / which issue / co-set.

Requires JIRA_URL, JIRA_API_TOKEN, and JIRA_USERNAME or JIRA_EMAIL.
Use .env_jira (copy from env.jira.example) — each team member uses their own token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
PROJECT = "CNV"

# Expected CNV project components (update when the team intentionally adds one).
# zArchive names may change; anything starting with "zArchive" is also allowed.
ALLOWLIST = frozenset(
    {
        "CNV Chaos",
        "CNV CI and Release",
        "CNV Documentation",
        "CNV Infrastructure",
        "CNV Install, Upgrade and Operators",
        "CNV Network",
        "CNV Perf/Scale",
        "CNV QE DevOps",
        "CNV User Interface",
        "CNV Virt-Cluster",
        "CNV Virt-Node",
        "CNV Virtualization",
        "Storage Ecosystem",
        "Storage Platform",
        "Upstream CI Platform",
        "zArchive - do not use CNV Integration",
        "zArchive - do not use CNV Migration",
        "zArchive - do not use CNV Release Readiness",
        "zArchive - do not use CNV User Experience",
        "zArchive - do not use KNI Community",
    }
)

# Names that contain commas must be matched as wholes (changelog values are
# comma-separated lists of component names).
COMMA_NAMES = frozenset(
    {
        "CNV Install, Upgrade and Operators",
        "Install, Upgrade and Operators",
    }
) | {n for n in ALLOWLIST if "," in n}


@dataclass
class ComponentEvent:
    key: str
    when: str
    who: str
    email: str
    account_id: str
    side: str  # "to" (add) or "from" (remove)
    from_string: str | None
    to_string: str | None
    co_set_on_add: list[str]


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


def resolve_env_file(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # scripts/ -> skill/ -> skills/ -> .cursor/ -> repo root
    root = Path(__file__).resolve().parents[4]
    for name in (".env_jira", ".env_wilker_jira", ".env_vme_automation_bot"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return root / ".env_jira"


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
            "Copy env.jira.example to .env_jira and add credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def is_allowed(name: str, allowlist: frozenset[str]) -> bool:
    if name in allowlist:
        return True
    if name.startswith("zArchive"):
        return True
    return False


def parse_component_list(side: str | None) -> list[str]:
    """Split a changelog Component fromString/toString into names.

    Handles known comma-containing names without treating their commas as
    separators.
    """
    if not side:
        return []
    remaining = side
    found: list[str] = []
    # Longest first so "CNV Install, Upgrade..." wins over the rogue short form
    for multi in sorted(COMMA_NAMES, key=len, reverse=True):
        if multi in remaining:
            found.append(multi)
            remaining = remaining.replace(multi, "\x00")
    for part in remaining.split(","):
        name = part.replace("\x00", "").strip()
        if name:
            found.append(name)
    # Preserve order, drop dupes
    out: list[str] = []
    seen: set[str] = set()
    for n in found:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def list_project_components(
    sess: requests.Session, base: str, auth: HTTPBasicAuth
) -> list[dict]:
    r = sess.get(
        f"{base}/rest/api/3/project/{PROJECT}/components",
        auth=auth,
        timeout=60,
    )
    r.raise_for_status()
    return sorted(r.json(), key=lambda c: c["name"].lower())


def search_keys(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    jql: str,
    limit: int | None = None,
) -> list[str]:
    keys: list[str] = []
    token = None
    while True:
        payload: dict = {
            "jql": jql,
            "maxResults": 100,
            "fields": ["key"],
        }
        if token:
            payload["nextPageToken"] = token
        r = sess.post(
            f"{base}/rest/api/3/search/jql",
            auth=auth,
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        for issue in data.get("issues") or []:
            keys.append(issue["key"])
            if limit is not None and len(keys) >= limit:
                return keys
        token = data.get("nextPageToken")
        if data.get("isLast") or not token:
            break
    return keys


def get_changelogs(
    sess: requests.Session, base: str, auth: HTTPBasicAuth, key: str
) -> list[dict]:
    start = 0
    out: list[dict] = []
    while True:
        r = sess.get(
            f"{base}/rest/api/3/issue/{key}/changelog",
            auth=auth,
            params={"startAt": start, "maxResults": 100},
            timeout=60,
        )
        if not r.ok:
            return out
        data = r.json()
        values = data.get("values") or []
        out.extend(values)
        if data.get("isLast", True):
            break
        start += len(values)
        if not values:
            break
    return out


def events_for_target(
    key: str, histories: list[dict], target: str
) -> list[ComponentEvent]:
    events: list[ComponentEvent] = []
    for h in histories:
        author = h.get("author") or {}
        for item in h.get("items") or []:
            if item.get("field") != "Component":
                continue
            fr = item.get("fromString")
            to = item.get("toString")
            from_names = parse_component_list(fr)
            to_names = parse_component_list(to)
            if target in to_names:
                co = [n for n in to_names if n != target]
                # Also include names that appeared in the same history entry
                # as sibling Component item adds (Jira often emits one item
                # per component change).
                sibling_adds: list[str] = []
                for other in h.get("items") or []:
                    if other.get("field") != "Component":
                        continue
                    sibling_adds.extend(
                        n
                        for n in parse_component_list(other.get("toString"))
                        if n != target
                    )
                co_set = []
                seen: set[str] = set()
                for n in co + sibling_adds:
                    if n not in seen:
                        seen.add(n)
                        co_set.append(n)
                events.append(
                    ComponentEvent(
                        key=key,
                        when=h.get("created") or "",
                        who=author.get("displayName") or "—",
                        email=author.get("emailAddress") or "—",
                        account_id=author.get("accountId") or "",
                        side="to",
                        from_string=fr,
                        to_string=to,
                        co_set_on_add=co_set,
                    )
                )
            if target in from_names:
                events.append(
                    ComponentEvent(
                        key=key,
                        when=h.get("created") or "",
                        who=author.get("displayName") or "—",
                        email=author.get("emailAddress") or "—",
                        account_id=author.get("accountId") or "",
                        side="from",
                        from_string=fr,
                        to_string=to,
                        co_set_on_add=[],
                    )
                )
    return events


def fetch_issue_summary(
    sess: requests.Session, base: str, auth: HTTPBasicAuth, key: str
) -> dict:
    r = sess.get(
        f"{base}/rest/api/3/issue/{key}",
        auth=auth,
        params={
            "fields": "summary,issuetype,status,created,creator,assignee,parent"
        },
        timeout=60,
    )
    if not r.ok:
        return {}
    f = r.json().get("fields") or {}
    return {
        "summary": f.get("summary") or "",
        "issuetype": (f.get("issuetype") or {}).get("name") or "",
        "status": (f.get("status") or {}).get("name") or "",
        "created": f.get("created") or "",
        "creator": (f.get("creator") or {}).get("displayName") or "—",
        "creator_email": (f.get("creator") or {}).get("emailAddress") or "—",
        "assignee": (f.get("assignee") or {}).get("displayName") or "—",
        "parent": (f.get("parent") or {}).get("key") or "",
    }


def scan_keys_for_target(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    keys: list[str],
    target: str,
    workers: int,
) -> list[ComponentEvent]:
    events: list[ComponentEvent] = []

    def work(key: str) -> list[ComponentEvent]:
        # Per-thread session avoids sharing one Session across threads.
        local = session()
        histories = get_changelogs(local, base, auth, key)
        return events_for_target(key, histories, target)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(work, key): key for key in keys}
        for fut in as_completed(futures):
            events.extend(fut.result())
    return events


def investigate_target(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    target: str,
    since: date,
    max_scan: int,
    workers: int,
    progress: bool,
) -> dict:
    """Find first add of target; return report dict."""
    if progress:
        print(f"  probing current issues with component = {target!r} ...", flush=True)

    current_keys: list[str] = []
    try:
        current_keys = search_keys(
            sess,
            base,
            auth,
            f'project = {PROJECT} AND component = "{target}" ORDER BY key ASC',
        )
    except requests.HTTPError:
        current_keys = []

    keys: list[str] = list(current_keys)
    if progress:
        print(f"    currently assigned: {len(current_keys)} issue(s)", flush=True)

    # Always also scan recently updated issues so deleted assignments are found.
    since_s = since.isoformat()
    if progress:
        print(
            f"  scanning changelogs for issues updated since {since_s} "
            f"(cap {max_scan}) ...",
            flush=True,
        )
    hist_keys = search_keys(
        sess,
        base,
        auth,
        f'project = {PROJECT} AND updated >= "{since_s}" ORDER BY updated DESC',
        limit=max_scan,
    )
    # Prefer union: current + history window
    seen: set[str] = set()
    ordered: list[str] = []
    for k in current_keys + hist_keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)

    if progress:
        print(f"    scanning {len(ordered)} issue changelog(s) ...", flush=True)

    events = scan_keys_for_target(sess, base, auth, ordered, target, workers)
    adds = sorted([e for e in events if e.side == "to"], key=lambda e: e.when)
    removes = sorted(
        [e for e in events if e.side == "from"], key=lambda e: e.when
    )

    first = adds[0] if adds else None
    issue_meta = fetch_issue_summary(sess, base, auth, first.key) if first else {}

    return {
        "component": target,
        "in_catalog_now": None,  # filled by caller
        "currently_assigned_count": len(current_keys),
        "currently_assigned_keys": current_keys[:50],
        "scanned_issues": len(ordered),
        "add_count": len(adds),
        "remove_count": len(removes),
        "first_add": asdict(first) if first else None,
        "first_issue": issue_meta,
        "all_adds": [asdict(e) for e in adds[:30]],
    }


def render_markdown(
    catalog_names: list[str],
    extras: list[str],
    missing: list[str],
    reports: list[dict],
    since: date,
) -> str:
    lines: list[str] = []
    lines.append("# CNV rogue component investigation")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_ · "
        f"history window from **{since.isoformat()}**"
    )
    lines.append("")
    lines.append("## Catalog vs allowlist")
    lines.append("")
    lines.append(f"- CNV components now: **{len(catalog_names)}**")
    lines.append(f"- Not on allowlist (suspect): **{len(extras)}**")
    if extras:
        for name in extras:
            lines.append(f"  - `{name}`")
    else:
        lines.append("  - _(none)_")
    if missing:
        lines.append(
            f"- On allowlist but missing from catalog: **{len(missing)}**"
        )
        for name in missing:
            lines.append(f"  - `{name}`")
    lines.append("")

    if not reports:
        lines.append("_No suspects investigated. Pass `--suspect` or use `--diff` only._")
        lines.append("")
        return "\n".join(lines)

    lines.append("## First use of each suspect")
    lines.append("")
    lines.append(
        "| Component | First use (UTC) | Who | Email | Issue | Co-set in same edit |"
    )
    lines.append(
        "|-----------|-----------------|-----|-------|-------|---------------------|"
    )
    for rep in reports:
        first = rep.get("first_add")
        if not first:
            lines.append(
                f"| `{rep['component']}` | _not found in window_ | — | — | — | — |"
            )
            continue
        co = ", ".join(f"`{c}`" for c in first.get("co_set_on_add") or []) or "—"
        key = first["key"]
        lines.append(
            f"| `{rep['component']}` | {first['when']} | {first['who']} | "
            f"{first['email']} | [{key}]({BROWSE}/{key}) | {co} |"
        )
    lines.append("")

    for rep in reports:
        first = rep.get("first_add")
        lines.append(f"### `{rep['component']}`")
        lines.append("")
        catalog = rep.get("in_catalog_now")
        lines.append(
            f"- In catalog now: **{'yes' if catalog else 'no'}** · "
            f"Currently on issues: **{rep.get('currently_assigned_count', 0)}** · "
            f"Adds found: **{rep.get('add_count', 0)}** (scanned {rep.get('scanned_issues', 0)} issues)"
        )
        if not first:
            lines.append(
                "- No Component-field **add** found in the history window. "
                "Widen with `--since` / `--max-scan`, or confirm the exact name."
            )
            lines.append("")
            continue
        meta = rep.get("first_issue") or {}
        lines.append(
            f"- **First add:** {first['when']} by **{first['who']}** "
            f"<{first['email']}> on [{first['key']}]({BROWSE}/{first['key']})"
        )
        if meta:
            lines.append(
                f"- Issue: {meta.get('issuetype')} · {meta.get('status')} · "
                f"created {meta.get('created')} by {meta.get('creator')} · "
                f"{meta.get('summary')}"
            )
            if meta.get("parent"):
                lines.append(f"- Parent: [{meta['parent']}]({BROWSE}/{meta['parent']})")
        co = first.get("co_set_on_add") or []
        if co:
            lines.append(
                "- Same-edit components: "
                + ", ".join(f"`{c}`" for c in co)
            )
            # Near-miss hint
            near = [
                c
                for c in co
                if c != rep["component"]
                and (
                    rep["component"].lower() in c.lower()
                    or c.lower() in rep["component"].lower()
                    or (
                        "storage" in rep["component"].lower()
                        and "storage" in c.lower()
                    )
                    or (
                        "install" in rep["component"].lower()
                        and "install" in c.lower()
                    )
                )
            ]
            if near:
                lines.append(
                    "- **Likely near-miss:** rogue name set alongside "
                    + ", ".join(f"`{c}`" for c in near)
                )
        lines.append("")
        adds = rep.get("all_adds") or []
        if len(adds) > 1:
            lines.append("Later adds (up to 10):")
            lines.append("")
            for e in adds[1:11]:
                lines.append(
                    f"- {e['when']} · {e['who']} · "
                    f"[{e['key']}]({BROWSE}/{e['key']})"
                )
            lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- First **Component** changelog add is the practical origin signal. "
        "Jira audit logs (who created the project component object) need "
        "Jira Administrator access and are not used here."
    )
    lines.append(
        "- Comma-containing names (e.g. `Install, Upgrade and Operators`) are "
        "matched as whole tokens so they are not confused with "
        "`CNV Install, Upgrade and Operators`."
    )
    lines.append(
        "- Typical pattern: someone editing Components types/selects a near-miss "
        "name next to the real one (e.g. `Storage` with `Storage Platform`)."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate rogue / unexpected CNV Jira components."
    )
    parser.add_argument(
        "--env-file",
        help="Path to env file (default: repo .env_jira or personal fallbacks)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Diff live CNV catalog against allowlist (default if no --suspect)",
    )
    parser.add_argument(
        "--suspect",
        nargs="+",
        metavar="NAME",
        help="Component name(s) to trace to first use",
    )
    parser.add_argument(
        "--investigate-extras",
        action="store_true",
        help="Also investigate every catalog name not on the allowlist",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="History window start for changelog scan (default: 120 days ago)",
    )
    parser.add_argument(
        "--max-scan",
        type=int,
        default=500,
        help="Max recently-updated issues to changelog-scan per suspect (default 500)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel changelog fetch workers (default 8)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress on stderr",
    )
    args = parser.parse_args()

    env_path = resolve_env_file(args.env_file)
    load_env_file(env_path)
    base, auth = jira_config()
    sess = session()
    progress = not args.quiet and not args.json

    if args.since:
        since = date.fromisoformat(args.since)
    else:
        since = (datetime.now(timezone.utc) - timedelta(days=120)).date()

    if progress:
        print(f"Using env: {env_path}", flush=True)
        print(f"Fetching {PROJECT} component catalog ...", flush=True)

    catalog = list_project_components(sess, base, auth)
    catalog_names = [c["name"] for c in catalog]
    extras = sorted(n for n in catalog_names if not is_allowed(n, ALLOWLIST))
    missing = sorted(n for n in ALLOWLIST if n not in catalog_names and not n.startswith("zArchive"))
    # zArchive allowlist entries that vanished
    missing_z = sorted(
        n for n in ALLOWLIST if n.startswith("zArchive") and n not in catalog_names
    )
    missing = missing + missing_z

    suspects: list[str] = []
    if args.suspect:
        suspects.extend(args.suspect)
    if args.investigate_extras:
        suspects.extend(extras)
    # Dedupe preserve order
    seen: set[str] = set()
    ordered_suspects: list[str] = []
    for n in suspects:
        if n not in seen:
            seen.add(n)
            ordered_suspects.append(n)

    do_diff = args.diff or (not args.suspect and not args.investigate_extras)
    if do_diff and progress:
        print(
            f"Catalog: {len(catalog_names)} · extras vs allowlist: {len(extras)}",
            flush=True,
        )
        for n in extras:
            print(f"  EXTRA: {n}", flush=True)

    reports: list[dict] = []
    for name in ordered_suspects:
        if progress:
            print(f"Investigating {name!r} ...", flush=True)
        rep = investigate_target(
            sess,
            base,
            auth,
            name,
            since=since,
            max_scan=args.max_scan,
            workers=args.workers,
            progress=progress,
        )
        rep["in_catalog_now"] = name in catalog_names
        reports.append(rep)

    payload = {
        "project": PROJECT,
        "since": since.isoformat(),
        "catalog": catalog_names,
        "extras": extras,
        "missing_from_catalog": missing,
        "reports": reports,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            render_markdown(
                catalog_names, extras, missing, reports, since=since
            )
        )


if __name__ == "__main__":
    main()
