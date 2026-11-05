#!/usr/bin/env python3
"""
Emit create commands from virtstrat_customer_links_draft.json.

Formats:
  mcp-jsonl   — one JSON object per line for MCP create_link args
  rh-customers — shell lines for rh_customers create link (review before run)

Never calls the API itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[3]


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)
DEFAULT_DRAFT = REPO_ROOT / "virtstrat_customer_links_draft.json"


def load_draft(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    rows = data.get("would_create") or data.get("rows") or []
    if not isinstance(rows, list):
        raise SystemExit(f"Unexpected draft shape in {path}")
    return rows


def emit_mcp_jsonl(rows: list[dict]) -> None:
    for row in rows:
        payload = {
            "issue_key": row["virtstrat_key"],
            "customer_mdm_pk": str(row["customer_mdm_pk"]),
            "context": row.get("context") or "affected_by",
        }
        print(json.dumps(payload, separators=(",", ":")))


def emit_rh_customers(rows: list[dict]) -> None:
    print("#!/usr/bin/env bash")
    print("# Generated from virtstrat_customer_links_draft.json — review before run")
    print("set -euo pipefail")
    print("rh_customers auth login >/dev/null || true")
    for row in rows:
        vs = row["virtstrat_key"]
        mdm = str(row["customer_mdm_pk"])
        ctx = row.get("context") or "affected_by"
        name = (row.get("customer_name") or "").replace("'", "")
        print(f"# {vs} <- {name} ({mdm}) via {row.get('source_key', '')}")
        print(
            "rh_customers create link "
            f"--issue-key {vs} --customer-mdm-pk {mdm} --context {ctx}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument(
        "--format",
        choices=("mcp-jsonl", "rh-customers"),
        default="mcp-jsonl",
    )
    args = parser.parse_args()
    if not args.draft.is_file():
        print(f"Missing draft: {args.draft}", file=sys.stderr)
        sys.exit(1)
    rows = load_draft(args.draft)
    if args.format == "mcp-jsonl":
        emit_mcp_jsonl(rows)
    else:
        emit_rh_customers(rows)
    print(f"# {len(rows)} command(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
