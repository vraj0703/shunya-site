#!/usr/bin/env python3
"""Writes config.js from the environment (CI): POSTHOG_TOKEN, optional POSTHOG_HOST. Prints lengths
only. Refuses when the token is missing or is not a phc_ project token. On the pc use
tools/write-config.ps1, which reads .secret/logger.env instead."""
import os
import pathlib
import sys

token = os.environ.get("POSTHOG_TOKEN", "").strip()
host = os.environ.get("POSTHOG_HOST", "").strip() or "https://us.i.posthog.com"
if not token.startswith("phc_"):
    sys.exit("write_config: POSTHOG_TOKEN is missing or is not a phc_ project token; nothing written")
out = pathlib.Path(__file__).resolve().parent.parent / "config.js"
out.write_text(f'window.WAITLIST_CONFIG = {{ token: "{token}", host: "{host}" }};\n', encoding="utf-8")
print(f"config.js written: token length {len(token)}, host {host}")
