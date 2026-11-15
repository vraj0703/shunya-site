#!/usr/bin/env python3
"""Checks tools/build_log.py without the network: the details link, both log shapes, the cursor,
and the record for a failed and a passed build. Run: python test/build_log_test.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import build_log as b

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + name)

ACC, UUID = "c0" * 16, "94f9f660-1a98-4259-8faa-f6d64c69ec55"
URL = f"https://dash.cloudflare.com/{ACC}/workers/services/view/shunya-systems-site/production/builds/{UUID}"
check("details link gives account, worker and build", b.parse_details(URL) == (ACC, "shunya-systems-site", UUID))
check("the ?to= form of the link is read too", b.parse_details(URL.replace(".com/", ".com/?to=/")) == (ACC, "shunya-systems-site", UUID))
check("another link gives nothing", b.parse_details("https://github.com/x/y/actions/runs/1") is None and b.parse_details(None) is None)
check("log lines as [time, text] pairs", b.log_lines({"result": {"lines": [[1, "a"], [2, "b\n"]]}}) == ["a", "b"])
check("log lines as objects and as strings", b.log_lines({"result": [{"message": "a"}, "b", {"x": 1}]}) == ["a", "b"])
check("an unexpected body gives no lines", b.log_lines({"result": None}) == [] and b.log_lines("x") == [])

pages = iter([{"result": {"lines": [[1, "one"]], "truncated": True, "cursor": "c1"}}, {"result": {"lines": [[2, "two"]], "truncated": False}}])
asked = []
def fake(url, headers=None):
    asked.append((url, headers)); return next(pages)
check("the cursor is followed and the token rides as a bearer",
      b.fetch_log(ACC, UUID, "tok", get=fake) == ["one", "two"] and asked[1][0].endswith("/logs?cursor=c1")
      and f"/accounts/{ACC}/builds/builds/{UUID}/logs" in asked[0][0] and asked[0][1] == {"Authorization": "Bearer tok"})

def event(conclusion, branch="logo-page"):
    return {"repository": {"full_name": "vraj0703/shunya-site", "default_branch": "main"},
            "check_run": {"name": "Workers Builds: shunya-systems-site", "status": "completed", "conclusion": conclusion, "details_url": URL,
                          "head_sha": "c66a5f5aaaaaaaaa", "app": {"slug": b.CF_APP}, "check_suite": {"head_branch": branch}}}
lines = ["Cloning", "Running build command", "✘ [ERROR] A request to the Cloudflare API failed.", "Failed: error occurred while running deploy command"]
r = b.record(event("failure"), "shunya-site", lines)
check("a failed build is an error with the last error line and the log tail",
      r["level"] == "error" and r["error"] == {"type": "CloudflareBuildFailed", "message": lines[-1]} and r["fields"]["log_tail"].endswith(lines[-1])
      and r["fields"]["log_lines"] == 4 and r["trace_id"] == UUID and r["app"] == "shunya-site" and r["service"] == "cloudflare-builds"
      and r["message"] == "Cloudflare build failure: shunya-systems-site logo-page c66a5f5" and r["fields"]["event"] == "cloudflare_build_finished"
      and r["fields"]["production"] is False)
r = b.record(event("success", "main"), "shunya-site", ["done"])
check("a passed build on main is info, production, no error", r["level"] == "info" and "error" not in r and r["fields"]["production"] is True)
r = b.record(event("failure"), "shunya-site", None, "CLOUDFLARE_API_TOKEN is not set")
check("a failure without a log still says so", r["level"] == "error" and "no log was read" in r["error"]["message"] and r["fields"]["log_note"].startswith("CLOUDFLARE") and "log_tail" not in r["fields"])
r = b.record(event("failure"), "shunya-site", [f"line {i}" for i in range(500)])
check("the tail is the last 80 lines", r["fields"]["log_tail"].splitlines()[0] == "line 420" and r["fields"]["log_lines"] == 500)
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
