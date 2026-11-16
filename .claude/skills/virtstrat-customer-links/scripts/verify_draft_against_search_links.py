#!/usr/bin/env python3
"""
Filter a draft against a bulk search_links dump for VIRTSTRAT-.

Input:
  --draft virtstrat_customer_links_draft.json
  --links-file  text or JSON containing lines like:
      VIRTSTRAT-193 <-> NAME (mdm_pk=1721979) context=affected_by ...

Writes updated draft (still-missing only) when --write-draft is set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINE_RE = re.compile(
    r"(?P<issue>VIRTSTRAT-\d+)\s*<->\s*(?P<name>.+?)\s*\(mdm_pk=(?P<mdm>[^)]+)\)",
    re.I,
)


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[3]


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)


def parse_live_pairs(text: str) -> set[tuple[str, str]]:
    live: set[tuple[str, str]] = set()
    for match in LINE_RE.finditer(text):
        live.add((match.group("issue").upper(), match.group("mdm").strip()))
    return live


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=REPO_ROOT / "virtstrat_customer_links_draft.json")
    parser.add_argument("--links-file", type=Path, required=True, help="Paste/file of search_links output")
    parser.add_argument("--write-draft", action="store_true")
    args = parser.parse_args()

    draft = json.loads(args.draft.read_text())
    rows = draft.get("would_create") or []
    live = parse_live_pairs(args.links_file.read_text())

    kept, dropped = [], []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        pair = (row["virtstrat_key"].upper(), str(row["customer_mdm_pk"]).strip())
        if pair in live:
            dropped.append(row)
            continue
        if pair in seen:
            continue
        seen.add(pair)
        kept.append(row)

    print(
        f"draft={len(rows)} live_pairs_parsed={len(live)} "
        f"still_missing={len(kept)} already_live={len(dropped)}"
    )
    print("| VIRTSTRAT | Customer | mdm_pk | context | Via CNV |")
    print("|-----------|----------|--------|---------|---------|")
    for row in kept:
        print(
            f"| {row['virtstrat_key']} | {(row.get('customer_name') or '')[:36]} | "
            f"{row['customer_mdm_pk']} | {row.get('context')} | {row.get('source_key')} |"
        )

    if args.write_draft:
        out = {
            **draft,
            "mode": "draft",
            "live_verify": f"search_links dump {args.links_file.name}",
            "dropped_already_live": len(dropped),
            "would_create_count": len(kept),
            "virtstrat_affected": len({r["virtstrat_key"] for r in kept}),
            "would_create": kept,
        }
        args.draft.write_text(json.dumps(out, indent=2) + "\n")
        print(f"Wrote {args.draft}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
