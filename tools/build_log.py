#!/usr/bin/env python3
"""Sends the outcome of a Cloudflare Workers build, with the tail of its log, to the tantr logger
(which forwards to PostHog). Run by .github/workflows/build-log.yml when Cloudflare's check on a
commit completes; it reads the GitHub event, nothing else.

  GITHUB_EVENT_PATH      the check_run event (set by GitHub Actions)
  LOGS_API_KEY           the logger's ingest key for this app; without it nothing is sent
  LOGS_APP               the app that key names (default shunya-site)
  TANTR_LOGS_URL         default https://logs.tantr.app
  CLOUDFLARE_API_TOKEN   a user-scoped token that can read Workers builds; without it the outcome
                         is still sent, without the log

Exits 0 when it is not configured or the check is not Cloudflare's, so a missing secret never turns
a commit red; exits 1 only when the logger refuses the record. No secret is ever printed."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

CF_APP = "cloudflare-workers-and-pages"
DETAILS = re.compile(r"dash\.cloudflare\.com/(?:\?to=/)?([0-9a-f]{32})/workers/services/view/([^/]+)/[^/]+/builds/([0-9a-f-]{36})")
ERROR_LINE = re.compile(r"\b(error|failed|failure|fatal|exception|not found|denied|invalid)\b", re.I)
TAIL_LINES, TAIL_CHARS = 80, 12000


def parse_details(url):
    """(account id, worker name, build uuid) from the check's details link, or None."""
    m = DETAILS.search(url or "")
    return m.groups() if m else None


def log_lines(body):
    """The text lines of a build-log response. Cloudflare's shape is read tolerantly: a list under
    result.lines (or result itself) whose items are [time, text] pairs, objects with a message, or
    plain strings."""
    result = body.get("result", body) if isinstance(body, dict) else body
    items = result.get("lines", []) if isinstance(result, dict) else result
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, (list, tuple)) and item:
            out.append(str(item[-1]))
        elif isinstance(item, dict):
            text = item.get("message", item.get("line", item.get("text")))
            if text is not None:
                out.append(str(text))
    return [line.rstrip("\n") for line in out]


def next_cursor(body):
    result = body.get("result") if isinstance(body, dict) else None
    if isinstance(result, dict) and result.get("truncated") and result.get("cursor"):
        return str(result["cursor"])
    return None


def fetch_log(account, build, token, get=None):
    """Every line of the build's log, following the cursor (at most 20 pages)."""
    get = get or http_json
    lines, cursor = [], None
    for _ in range(20):
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/builds/builds/{build}/logs" + (f"?cursor={cursor}" if cursor else "")
        body = get(url, headers={"Authorization": f"Bearer {token}"})
        lines += log_lines(body)
        cursor = next_cursor(body)
        if not cursor:
            break
    return lines


def record(event, app, lines=None, log_note=None):
    """The logger record for a completed check_run event."""
    run = event["check_run"]
    details = parse_details(run.get("details_url"))
    worker, build = (details[1], details[2]) if details else (run.get("name", "worker"), None)
    ok = run.get("conclusion") == "success"
    branch = (run.get("check_suite") or {}).get("head_branch") or "?"
    sha = (run.get("head_sha") or "")[:7]
    fields = {"event": "cloudflare_build_finished", "worker": worker, "branch": branch, "commit": sha,
              "conclusion": run.get("conclusion"), "repository": (event.get("repository") or {}).get("full_name"),
              "production": branch == (event.get("repository") or {}).get("default_branch")}
    if build:
        fields["build_uuid"] = build
    if log_note:
        fields["log_note"] = log_note
    rec = {"app": app, "service": "cloudflare-builds", "level": "info" if ok else "error",
           "message": f"Cloudflare build {run.get('conclusion')}: {worker} {branch} {sha}", "fields": fields}
    if build:
        rec["trace_id"] = build
    if lines:
        tail = "\n".join(lines[-TAIL_LINES:])[-TAIL_CHARS:]
        fields["log_lines"] = len(lines)
        fields["log_tail"] = tail
        if not ok:
            last = next((line for line in reversed(lines) if ERROR_LINE.search(line)), lines[-1])
            rec["error"] = {"type": "CloudflareBuildFailed", "message": last.strip()[:500]}
    elif not ok:
        rec["error"] = {"type": "CloudflareBuildFailed", "message": f"{worker} failed on {branch} {sha}; no log was read"}
    return rec


def http_json(url, headers=None, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"content-type": "application/json", "user-agent": "shunya-site-build-log", **(headers or {})},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def main():
    event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
    run = event.get("check_run") or {}
    if (run.get("app") or {}).get("slug") != CF_APP or run.get("status") != "completed":
        print("build-log: not a completed Cloudflare check; nothing to do")
        return 0
    key = os.environ.get("LOGS_API_KEY", "").strip()
    if not key:
        print("build-log: LOGS_API_KEY is not set; nothing is sent (see README, 'Build logs')")
        return 0
    app = os.environ.get("LOGS_APP", "").strip() or "shunya-site"
    base = (os.environ.get("TANTR_LOGS_URL", "").strip() or "https://logs.tantr.app").rstrip("/")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    details = parse_details(run.get("details_url"))
    lines, note = None, None
    if not token:
        note = "CLOUDFLARE_API_TOKEN is not set"
    elif not details:
        note = "the check's details link did not name a build"
    else:
        try:
            lines = fetch_log(details[0], details[2], token)
            if not lines:
                note = "Cloudflare returned no log lines"
        except urllib.error.HTTPError as e:
            note = f"Cloudflare's log API answered {e.code}"
        except (urllib.error.URLError, ValueError, OSError) as e:
            note = f"Cloudflare's log API could not be read: {type(e).__name__}"
    rec = record(event, app, lines, note)
    try:
        http_json(base + "/ingest", headers={"x-api-key": key}, data=rec)
    except urllib.error.HTTPError as e:
        print(f"build-log: the logger refused the record: {e.code}")
        return 1
    print(f"build-log: sent '{rec['message']}' with {len(lines or [])} log lines" + (f" ({note})" if note else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
