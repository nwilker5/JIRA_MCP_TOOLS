#!/usr/bin/env python3
"""
Move RFE Feature Request issues to CNV or MTV as Feature Request.

Uses the Jira Cloud bulk move API, posts a Red Hat Employee–only comment,
then removes the acting user as a watcher (move/comment auto-watches).

Each person uses their own Jira login (.env_jira). Never commit tokens.

Usage:
  python3 rfe_feature_move.py RFE-1234 --target CNV
  python3 rfe_feature_move.py RFE-1 RFE-2 --target MTV
  python3 rfe_feature_move.py RFE-1 --target CNV --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
FEATURE_REQUEST = "Feature Request"
RH_EMPLOYEE_GROUP = "Red Hat Employee"
ATTRIBUTION = "This issue was updated via Claude AI assistant."
COMMENT_TEMPLATE = (
    "Moved from {old_key} to {target} as Feature Request via bulk move API."
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


def resolve_env_file(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # Prefer shared .env_jira; fall back to common personal/bot files if present
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
            "Copy env.jira.example to .env_jira and add your credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def myself(sess: requests.Session, base: str, auth: HTTPBasicAuth) -> dict:
    r = sess.get(f"{base}/rest/api/3/myself", auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def get_issue(
    sess: requests.Session, base: str, auth: HTTPBasicAuth, key: str
) -> dict:
    r = sess.get(
        f"{base}/rest/api/3/issue/{key}",
        auth=auth,
        params={
            "fields": "summary,project,issuetype,status,assignee",
        },
        timeout=60,
    )
    if not r.ok:
        print(f"Error fetching {key}: {r.status_code} {r.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return r.json()


def feature_request_type_id(
    sess: requests.Session, base: str, auth: HTTPBasicAuth, project: str
) -> str:
    r = sess.get(
        f"{base}/rest/api/3/issue/createmeta/{project}/issuetypes",
        auth=auth,
        timeout=60,
    )
    r.raise_for_status()
    for it in r.json().get("values", r.json().get("issueTypes", [])):
        if it.get("name") == FEATURE_REQUEST:
            return str(it["id"])
    print(
        f"Error: '{FEATURE_REQUEST}' issue type not found in {project}.",
        file=sys.stderr,
    )
    sys.exit(1)


def bulk_move(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    keys: list[str],
    target: str,
    type_id: str,
) -> str:
    """Submit bulk move; return taskId. Retries with notifications if needed."""
    mapping = {
        f"{target},{type_id}": {
            "inferClassificationDefaults": True,
            "inferFieldDefaults": True,
            "inferStatusDefaults": True,
            "inferSubtaskTypeDefault": True,
            "issueIdsOrKeys": keys,
        }
    }
    for notify in (False, True):
        body = {
            "sendBulkNotification": notify,
            "targetToSourcesMapping": mapping,
        }
        r = sess.post(
            f"{base}/rest/api/3/bulk/issues/move",
            auth=auth,
            json=body,
            timeout=120,
        )
        if r.status_code in (200, 201):
            return r.json()["taskId"]
        # Some accounts cannot disable bulk mail notifications
        if (
            r.status_code == 403
            and "bulk mail notifications" in r.text
            and not notify
        ):
            continue
        print(f"Move failed: {r.status_code} {r.text[:2000]}", file=sys.stderr)
        sys.exit(1)
    print("Move failed after notification retry.", file=sys.stderr)
    sys.exit(1)


def wait_task(
    sess: requests.Session, base: str, auth: HTTPBasicAuth, task_id: str
) -> dict:
    for i in range(60):
        time.sleep(2)
        r = sess.get(
            f"{base}/rest/api/3/bulk/queue/{task_id}",
            auth=auth,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print(f"  Poll {i + 1}: {status}")
        if status in ("COMPLETE", "FAILED", "CANCELLED"):
            return data
    print("Timed out waiting for bulk move task.", file=sys.stderr)
    sys.exit(1)


def add_comment(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    new_key: str,
    old_key: str,
    target: str,
) -> None:
    text = COMMENT_TEMPLATE.format(old_key=old_key, target=target)
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": ATTRIBUTION,
                            "marks": [{"type": "em"}],
                        }
                    ],
                },
            ],
        },
        "visibility": {"type": "group", "value": RH_EMPLOYEE_GROUP},
    }
    r = sess.post(
        f"{base}/rest/api/3/issue/{new_key}/comment",
        auth=auth,
        json=body,
        timeout=60,
    )
    if not r.ok:
        print(f"  Comment failed on {new_key}: {r.status_code} {r.text[:400]}")
    else:
        print(f"  Comment OK (Red Hat Employee) on {new_key}")


def remove_watcher(
    sess: requests.Session,
    base: str,
    auth: HTTPBasicAuth,
    issue_key: str,
    account_id: str,
) -> None:
    wr = sess.get(
        f"{base}/rest/api/3/issue/{issue_key}/watchers",
        auth=auth,
        timeout=60,
    )
    if not wr.ok:
        print(f"  Watcher check failed on {issue_key}: {wr.status_code}")
        return
    watchers = [w.get("accountId") for w in wr.json().get("watchers", [])]
    if account_id not in watchers:
        print(f"  Not watching {issue_key} (skip unwatch)")
        return
    dr = sess.delete(
        f"{base}/rest/api/3/issue/{issue_key}/watchers",
        auth=auth,
        params={"accountId": account_id},
        timeout=60,
    )
    if dr.status_code == 204:
        print(f"  Watcher removed on {issue_key}")
    else:
        print(f"  Unwatch failed on {issue_key}: {dr.status_code} {dr.text[:200]}")


def normalize_keys(raw: list[str]) -> list[str]:
    keys: list[str] = []
    for item in raw:
        for part in item.replace(",", " ").split():
            k = part.strip().upper()
            if k:
                keys.append(k)
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move RFE Feature Requests to CNV or MTV"
    )
    parser.add_argument(
        "keys",
        nargs="+",
        help="One or more RFE issue keys (e.g. RFE-1234)",
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=["CNV", "MTV"],
        help="Destination project",
    )
    parser.add_argument(
        "--env-file",
        help="Path to env file (default: .env_jira in repo root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — do not move, comment, or unwatch",
    )
    parser.add_argument(
        "--keep-watcher",
        action="store_true",
        help="Do not remove the acting user as watcher after the move",
    )
    args = parser.parse_args()

    env_path = resolve_env_file(args.env_file)
    load_env_file(env_path)
    if not env_path.is_file():
        print(f"Error: env file not found: {env_path}", file=sys.stderr)
        print("Copy env.jira.example to .env_jira and add credentials.", file=sys.stderr)
        sys.exit(1)

    keys = normalize_keys(args.keys)
    base, auth = jira_config()
    sess = session()
    me = myself(sess, base, auth)
    account_id = me["accountId"]
    print(f"Acting as: {me.get('displayName')} ({me.get('emailAddress')})")
    print(f"Env file:  {env_path}")
    print(f"Target:    {args.target} / {FEATURE_REQUEST}")
    if args.dry_run:
        print("Mode:      DRY-RUN\n")

    type_id = feature_request_type_id(sess, base, auth, args.target)
    previews: list[tuple[str, str, dict]] = []  # old_key, issue_id, fields
    for key in keys:
        if not key.startswith("RFE-"):
            print(f"Warning: {key} is not an RFE key — continuing anyway")
        issue = get_issue(sess, base, auth, key)
        f = issue["fields"]
        proj = f["project"]["key"]
        itype = f["issuetype"]["name"]
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        print(
            f"{key}: {proj} | {itype} | {f['status']['name']} | {assignee}"
        )
        print(f"  {f['summary']}")
        if proj == args.target and itype == FEATURE_REQUEST:
            print(f"  Already in {args.target} as Feature Request — will skip move")
        previews.append((key, issue["id"], f))

    to_move = [
        k
        for k, _iid, f in previews
        if not (
            f["project"]["key"] == args.target
            and f["issuetype"]["name"] == FEATURE_REQUEST
        )
    ]
    if args.dry_run:
        print(
            f"\nWould move {len(to_move)} of {len(keys)} issue(s) "
            f"→ {args.target} ({FEATURE_REQUEST})."
        )
        return

    if not to_move:
        print("Nothing to move.")
        return

    print(f"\nMoving {len(to_move)} issue(s)…")
    task_id = bulk_move(sess, base, auth, to_move, args.target, type_id)
    print(f"Task: {task_id}")
    result = wait_task(sess, base, auth, task_id)
    if result.get("failedAccessibleIssues"):
        print(f"FAILED: {result['failedAccessibleIssues']}", file=sys.stderr)
    if result.get("status") != "COMPLETE":
        print(f"Move ended with status {result.get('status')}", file=sys.stderr)
        sys.exit(1)

    print("\nResults:")
    for old_key, issue_id, _f in previews:
        d = get_issue(sess, base, auth, issue_id)
        new_key = d["key"]
        nf = d["fields"]
        print(
            f"  {old_key} → {new_key} | {nf['project']['key']} | "
            f"{nf['issuetype']['name']} | {nf['status']['name']}"
        )
        print(f"    {BROWSE}/{new_key}")

        if old_key in to_move or new_key != old_key:
            add_comment(sess, base, auth, new_key, old_key, args.target)

        if not args.keep_watcher:
            remove_watcher(sess, base, auth, new_key, account_id)


if __name__ == "__main__":
    main()
