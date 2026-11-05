#!/usr/bin/env python3
"""
Draft Customer Intelligence links to copy from CNV onto VIRTSTRAT.

Input is a Dataverse CSV of virtstrat_cnv_customer_gaps.sql — not a
full-project REST dump. This script never calls create_link.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[3]


REPO_ROOT = find_repo_root(SCRIPT_DIR)
DRAFT_OUT = REPO_ROOT / "virtstrat_customer_links_draft.json"

COL_VS = "virtstrat_issue_key"
COL_VS_SUM = "virtstrat_summary"
COL_VS_ST = "virtstrat_status"
COL_CNV = "cnv_issue_key"
COL_CNV_SUM = "cnv_summary"
COL_NAME = "customer_name"
COL_MDM = "customer_mdm_pk"
COL_CTX = "customer_link_context"
COL_BY = "customer_linked_by"


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = {COL_VS, COL_MDM} - set(reader.fieldnames or [])
        if missing:
            print(f"CSV missing columns: {sorted(missing)}", file=sys.stderr)
            sys.exit(1)
        return [row for row in reader if (row.get(COL_VS) or "").strip()]


def dedupe(rows: list[dict]) -> list[dict]:
    """One create candidate per (VIRTSTRAT, mdm_pk); keep first CNV source."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in rows:
        vs = (row.get(COL_VS) or "").strip()
        mdm = str(row.get(COL_MDM) or "").strip()
        if not vs or not mdm:
            continue
        key = (vs, mdm)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "virtstrat_key": vs,
                "virtstrat_summary": (row.get(COL_VS_SUM) or "").strip(),
                "virtstrat_status": (row.get(COL_VS_ST) or "").strip(),
                "source_key": (row.get(COL_CNV) or "").strip(),
                "source_summary": (row.get(COL_CNV_SUM) or "").strip(),
                "customer_name": (row.get(COL_NAME) or "").strip(),
                "customer_mdm_pk": mdm,
                "context": (row.get(COL_CTX) or "affected_by").strip() or "affected_by",
                "customer_linked_by": (row.get(COL_BY) or "").strip(),
            }
        )
    return out


def print_table(rows: list[dict]) -> None:
    print(
        f"Warehouse candidates: {len(rows)} unique (VIRTSTRAT, customer) pair(s) "
        f"on {len({r['virtstrat_key'] for r in rows})} Feature(s)"
    )
    print(
        "No create_link calls were made. Live-verify with bulk MCP "
        "search_links q=VIRTSTRAT- (not per-issue get_issue_links)."
    )
    if not rows:
        return
    print(
        "\n| VIRTSTRAT | Status | Customer | mdm_pk | context | Via CNV |"
    )
    print("|-----------|--------|----------|--------|---------|---------|")
    for row in rows:
        print(
            f"| {row['virtstrat_key']} | {row['virtstrat_status'][:16]} | "
            f"{row['customer_name'][:36]} | {row['customer_mdm_pk']} | "
            f"{row['context']} | {row['source_key']} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DRAFT only: collapse Dataverse customer-gap CSV. Never creates links."
    )
    parser.add_argument("--draft", "--dry-run", dest="draft", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--from-csv",
        required=True,
        help="CSV exported from sql/virtstrat_cnv_customer_gaps.sql",
    )
    parser.add_argument("--write-draft", action="store_true")
    args = parser.parse_args()
    if args.execute:
        print(
            "Refused: --execute is not supported. Create links via Customer "
            "Intelligence MCP create_link after live verify.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("=" * 70)
    print("Mode: DRAFT (Dataverse CSV — no Customer Intelligence writes)")
    print("=" * 70)

    path = Path(args.from_csv).expanduser()
    if not path.is_file():
        print(f"Missing CSV: {path}", file=sys.stderr)
        sys.exit(1)

    candidates = dedupe(load_rows(path))
    if args.write_draft:
        payload = {
            "mode": "draft",
            "source": "dataverse-csv",
            "would_create_count": len(candidates),
            "would_create": candidates,
            "scope": "CNV Feature Requests → VIRTSTRAT Features (from Dataverse CSV)",
            "note": "Verify with bulk search_links q=VIRTSTRAT- before create_link.",
        }
        DRAFT_OUT.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"Wrote {DRAFT_OUT}")
    print_table(candidates)


if __name__ == "__main__":
    main()
