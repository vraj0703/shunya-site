#!/usr/bin/env python3
"""Builds the site into dist/ for Cloudflare (Workers static assets, see wrangler.jsonc): the pages and assets only (no tools, tests or
README), plus config.js written from the environment and a _headers file.

  POSTHOG_TOKEN   the PostHog project token (phc_...), set in the Worker's build variables
  POSTHOG_HOST    optional, default https://us.i.posthog.com
  TANTR_SERVER    optional; empty string switches tantr's road off, unset keeps https://tantr.app

Without POSTHOG_TOKEN the build still succeeds and says so loudly: the form then sends by tantr's
road only. A token that is not a phc_ project token fails the build, so a private key never ships."""
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PAGES = ["index.html", "privacy.html", "tantr", "assets"]
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: SAMEORIGIN
  Permissions-Policy: camera=(), microphone=(), geolocation=()
/config.js
  Cache-Control: no-cache
/assets/*
  Cache-Control: public, max-age=3600
"""


NOT_FOUND = """<!doctype html>
<html lang="en" data-brand="shunya"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not found: Shunya Systems</title><link rel="icon" href="/assets/shunya.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css"></head>
<body><main class="prose"><h1>Nothing here</h1><p>That page does not exist. <a href="/">Back to Shunya Systems</a>.</p></main></body></html>
"""


def main():
    token = os.environ.get("POSTHOG_TOKEN", "").strip()
    host = os.environ.get("POSTHOG_HOST", "").strip() or "https://us.i.posthog.com"
    if token and not token.startswith("phc_"):
        sys.exit("build: POSTHOG_TOKEN is not a phc_ project token; refusing to ship it")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in PAGES:
        src = ROOT / name
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, DIST / name)
    cfg = {"token": token, "host": host}
    if "TANTR_SERVER" in os.environ:
        cfg["tantr"] = os.environ["TANTR_SERVER"].strip()
    (DIST / "config.js").write_text("window.WAITLIST_CONFIG = " + json.dumps(cfg) + ";\n", encoding="utf-8")
    (DIST / "_headers").write_text(HEADERS, encoding="utf-8")
    (DIST / "404.html").write_text(NOT_FOUND, encoding="utf-8")
    files = sum(1 for p in DIST.rglob("*") if p.is_file())
    print(f"build: dist/ has {files} files; PostHog token length {len(token)}, host {host}")
    if not token:
        print("build: WARNING: POSTHOG_TOKEN is not set; signups will not reach PostHog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
