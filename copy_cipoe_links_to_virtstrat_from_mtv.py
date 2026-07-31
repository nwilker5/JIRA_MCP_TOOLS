#!/usr/bin/env python3
"""Thin wrapper — prefer ./run_copy_cipoe_links_to_virtstrat.sh --source mtv"""
import runpy
import os
import sys

# Default this wrapper to MTV-only for backward compatibility with old script name.
if '--source' not in sys.argv:
    sys.argv[1:1] = ['--source', 'mtv']

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".cursor",
    "skills",
    "cnv-virtstrat-cipoe-links",
    "scripts",
    "copy_cipoe_links_to_virtstrat.py",
)
runpy.run_path(SCRIPT, run_name="__main__")
