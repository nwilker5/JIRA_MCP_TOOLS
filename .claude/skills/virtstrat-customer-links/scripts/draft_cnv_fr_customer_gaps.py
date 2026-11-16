#!/usr/bin/env python3
"""
Draft missing Customer Intelligence links:
  CNV Feature Request customers → linked VIRTSTRAT Features

Inputs (repo root):
  virtstrat_cnv_fr_graph.json   — Jira Feature↔CNV FR map
  virtstrat_customer_links_ci_raw.json — CI search_links dump

Output:
  virtstrat_customer_links_draft.json
  stdout draft table
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[4]


REPO = find_repo_root(Path(__file__).resolve().parent)
GRAPH = REPO / "virtstrat_cnv_fr_graph.json"
CI_RAW = REPO / "virtstrat_customer_links_ci_raw.json"
OUT = REPO / "virtstrat_customer_links_draft.json"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing {path}")
    return json.loads(path.read_text())


def index_links(rows: list[dict]) -> dict[str, list[dict]]:
    by_issue: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        issue = (row.get("issue_key") or "").strip()
        mdm = str(row.get("customer_mdm_pk") or "").strip()
        if not issue or not mdm:
            continue
        key = (issue, mdm)
        if key in seen:
            continue
        seen.add(key)
        by_issue[issue].append(row)
    return by_issue


def main() -> None:
    graph = load_json(GRAPH)
    ci = load_json(CI_RAW)
    fr_to_vs: dict[str, list[str]] = graph["fr_to_vs"]
    vs_meta: dict[str, dict] = graph["vs_meta"]
    cnv_meta: dict[str, dict] = graph["cnv_meta"]

    cnv_by = index_links(ci.get("cnv_links") or [])
    vs_by = index_links(ci.get("virtstrat_links") or [])

    fr_with_ci = [k for k in fr_to_vs if k in cnv_by]
    gaps = []
    seen_pair: set[tuple[str, str]] = set()

    for fr_key, vs_keys in sorted(fr_to_vs.items()):
        for cust in cnv_by.get(fr_key, []):
            mdm = str(cust["customer_mdm_pk"]).strip()
            for vs_key in vs_keys:
                vs_mdms = {str(r["customer_mdm_pk"]).strip() for r in vs_by.get(vs_key, [])}
                if mdm in vs_mdms:
                    continue
                pair = (vs_key, mdm)
                if pair in seen_pair:
                    continue
                seen_pair.add(pair)
                gaps.append(
                    {
                        "virtstrat_key": vs_key,
                        "virtstrat_summary": (vs_meta.get(vs_key) or {}).get("summary", ""),
                        "virtstrat_status": (vs_meta.get(vs_key) or {}).get("status", ""),
                        "source_key": fr_key,
                        "source_summary": (cnv_meta.get(fr_key) or {}).get("summary", ""),
                        "source": "cnv",
                        "source_issuetype": "Feature Request",
                        "customer_name": cust.get("customer_name", ""),
                        "customer_mdm_pk": mdm,
                        "context": cust.get("context") or "affected_by",
                    }
                )

    gaps.sort(key=lambda r: (r["virtstrat_key"], r["customer_name"], r["source_key"]))

    draft = {
        "mode": "draft",
        "source": "jira_fr_graph + ci_search_links",
        "scope": "CNV Feature Requests linked to VIRTSTRAT Features",
        "cnv_feature_requests_linked": len(fr_to_vs),
        "cnv_feature_requests_with_ci_links": len(fr_with_ci),
        "virtstrat_with_fr_links": len(graph["vs_to_fr"]),
        "would_create_count": len(gaps),
        "virtstrat_affected": len({g["virtstrat_key"] for g in gaps}),
        "would_create": gaps,
        "note": "Draft only. Live-verify with get_issue_links before create_link.",
    }
    OUT.write_text(json.dumps(draft, indent=2))

    print("=" * 72)
    print("DRAFT — CNV Feature Request → VIRTSTRAT Customer Intelligence gaps")
    print("=" * 72)
    print(f"CNV Feature Requests linked to VIRTSTRAT: {len(fr_to_vs)}")
    print(f"CNV FRs that have CI customer links:     {len(fr_with_ci)}")
    print(f"VIRTSTRAT Features with CNV FR link:     {len(graph['vs_to_fr'])}")
    print(f"Missing (VIRTSTRAT, customer) creates:   {len(gaps)}")
    print(f"VIRTSTRAT Features affected:             {draft['virtstrat_affected']}")
    print()
    if not gaps:
        print("No gaps — every CNV FR customer is already on linked VIRTSTRAT Features.")
        return

    print("| VIRTSTRAT | Customer | mdm_pk | context | Via CNV FR |")
    print("|-----------|----------|--------|---------|------------|")
    for g in gaps:
        name = (g["customer_name"] or "")[:36]
        print(
            f"| {g['virtstrat_key']} | {name} | {g['customer_mdm_pk']} | "
            f"{g['context']} | {g['source_key']} |"
        )
    print()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
