#!/usr/bin/env python3
"""Backward-compatible wrapper — use assess_virt_rfe.py --project mtv instead."""

import sys

if __name__ == "__main__":
    print("Note: assess_mtv_rfe.py is deprecated. Use: python assess_virt_rfe.py --project mtv ...")
    if "--project" not in sys.argv:
        sys.argv[1:1] = ["--project", "mtv"]
    from assess_virt_rfe import main

    main()
