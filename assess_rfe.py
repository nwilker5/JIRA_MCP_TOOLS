#!/usr/bin/env python3
"""Backward-compatible wrapper — use assess_virt_rfe.py instead."""

import sys

if __name__ == "__main__":
    print("Note: assess_rfe.py is deprecated. Use: python assess_virt_rfe.py ...")
    from assess_virt_rfe import main

    main()
