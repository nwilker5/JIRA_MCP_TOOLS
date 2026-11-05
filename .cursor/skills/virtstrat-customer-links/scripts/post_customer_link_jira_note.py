#!/usr/bin/env python3
"""Post Red Hat Employee Jira note as VME Automation Bot; unwatch bot + operator."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from jira import JIRA

SCRIPT_DIR = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[3]


REPO_ROOT = find_repo_root(SCRIPT_DIR)
# Optional: set CUSTOMER_LINKS_UNWATCH_ACCOUNT_ID to also remove a personal watcher.
DEFAULT_UNWATCH_ACCOUNT_ID = os.environ.get("CUSTOMER_LINKS_UNWATCH_ACCOUNT_ID", "")
COMMENT_BODY = (
    "Customer links were updated.\n\n"
    "---\n"
    "*Comment added via Claude AI assistant.*"
)
COMMENT_PREFIX = "Customer links were updated."


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'").strip('"')
    return env


def connect(env_name: str, default_user: str | None = None) -> JIRA:
    env = load_env_file(REPO_ROOT / env_name)
    url = env.get("JIRA_URL") or os.environ.get("JIRA_URL") or "https://redhat.atlassian.net"
    user = env.get("JIRA_USERNAME") or env.get("JIRA_EMAIL") or default_user
    token = env.get("JIRA_API_TOKEN")
    if not user or not token:
        print(f"Missing credentials in {env_name}", file=sys.stderr)
        sys.exit(1)
    return JIRA(server=url, basic_auth=(user, token))


def unwatch(jira: JIRA, issue_key: str, account_id: str) -> str:
    try:
        watchers = jira.watchers(issue_key)
        ids = [getattr(w, "accountId", None) for w in (watchers.watchers or [])]
        if account_id not in ids:
            return "not watching"
        jira.remove_watcher(issue_key, account_id)
        return "removed"
    except Exception as exc:
        return f"error: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", action="append", required=True)
    parser.add_argument("--replace-personal-comment", action="store_true")
    parser.add_argument("--attach-log")
    parser.add_argument("--devo-issue", default="DEVO-258")
    args = parser.parse_args()
    keys = [k.strip().upper() for k in args.issue]

    personal = None
    for name in (".env_jira", ".env_wilker_jira"):
        if (REPO_ROOT / name).is_file():
            personal = connect(name)
            break
    if personal is None and (args.replace_personal_comment or args.attach_log):
        print("No personal .env_jira found (needed for --replace-personal-comment / --attach-log)", file=sys.stderr)
        sys.exit(1)

    if args.attach_log:
        assert personal is not None
        log_path = Path(args.attach_log).expanduser()
        if not log_path.is_file():
            print(f"Missing log: {log_path}", file=sys.stderr)
            sys.exit(1)
        personal.add_attachment(
            issue=args.devo_issue,
            attachment=str(log_path),
            filename=log_path.name,
        )
        print(f"Attached {log_path.name} to {args.devo_issue} (watcher kept: DEVO assignee)")

    bot = connect(".env_vme_automation_bot", "vme-automation-bot@redhat.com")
    bot_id = bot.myself()["accountId"]
    unwatch_personal_id = DEFAULT_UNWATCH_ACCOUNT_ID
    if personal is not None and not unwatch_personal_id:
        unwatch_personal_id = personal.myself().get("accountId") or ""

    for key in keys:
        if args.replace_personal_comment and personal is not None and unwatch_personal_id:
            issue = personal.issue(key, fields="comment")
            comments = getattr(issue.fields, "comment", None)
            for c in getattr(comments, "comments", []) or []:
                body = getattr(c, "body", "") or ""
                body_text = body if isinstance(body, str) else str(body)
                author = getattr(getattr(c, "author", None), "accountId", None)
                if author == unwatch_personal_id and COMMENT_PREFIX in body_text:
                    personal.comment(key, c.id).delete()
                    print(f"Deleted personal comment {c.id} on {key}")
        bot.add_comment(
            key,
            COMMENT_BODY,
            visibility={"type": "group", "value": "Red Hat Employee"},
        )
        print(f"Bot comment posted on {key}")
        print(f"  Unwatch bot: {unwatch(bot, key, bot_id)}")
        if personal is not None and unwatch_personal_id:
            print(f"  Unwatch personal: {unwatch(personal, key, unwatch_personal_id)}")


if __name__ == "__main__":
    main()
