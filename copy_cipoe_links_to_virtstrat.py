#!/usr/bin/env python3
"""Thin wrapper — prefer the skill script or ./run_copy_cipoe_links_to_virtstrat.sh."""
import runpy
import os

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".cursor",
    "skills",
    "cnv-virtstrat-cipoe-links",
    "scripts",
    "copy_cipoe_links_to_virtstrat.py",
)
runpy.run_path(SCRIPT, run_name="__main__")
