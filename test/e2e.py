"""End to end against a fake capture endpoint: both pages, good address, bad address, bot, repeat,
network failure. Run: ~/yantr/.venv/bin/python test/e2e.py   (needs playwright + chromium)"""
import http.server, json, pathlib, threading, functools, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
seen = []
envelopes = []

class Site(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/config.js":
            body = b'window.WAITLIST_CONFIG = { token: "phc_test", host: "http://127.0.0.1:8766", tantr: "http://127.0.0.1:8766" };'
            self.send_response(200); self.send_header("Content-Type", "text/javascript"); self.end_headers(); self.wfile.write(body); return
        super().do_GET()

class Capture(http.server.BaseHTTPRequestHandler):
    fail = False
    def log_message(self, *a): pass
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "content-type")
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if Capture.fail == "all" or (Capture.fail == "posthog" and self.path == "/capture/"):
            self.send_response(503); self._cors(); self.end_headers(); return
        (envelopes if self.path == "/v0/envelopes" else seen).append((self.path, body)); self.send_response(200); self._cors(); self.end_headers(); self.wfile.write(b'{"status":1}')

def serve(handler, port):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler); threading.Thread(target=s.serve_forever, daemon=True).start(); return s

serve(functools.partial(Site, directory=str(ROOT)), 8767); serve(Capture, 8766)
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + name)

with sync_playwright() as p:
    b = p.chromium.launch()
    for path, site in (("/", "shunya"), ("/tantr/", "tantr")):
        ctx = b.new_context(); page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:8767{path}?utm_source=test"); note = page.locator(".note")
        page.fill("input[type=email]", "not-an-email"); page.click("form.join button")
        check(f"{site}: a bad address is refused in words", "does not look like" in note.inner_text() and not seen)
        page.fill("input[type=email]", f"Night.Test+{site}@Example.com"); page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.note').dataset.kind === 'ok'", timeout=5000)
        path_, body = seen[-1]; pr = body["properties"]
        check(f"{site}: one waitlist_joined reaches /capture/", path_ == "/capture/" and body["event"] == "waitlist_joined" and len(seen) == 1)
        check(f"{site}: address lowercased, on the event and on the person", body["distinct_id"] == f"night.test+{site}@example.com" == pr["email"] == pr["$set"]["email"])
        check(f"{site}: site, page and utm ride along", pr["site"] == site and pr["page"] == path and pr["utm_source"] == "test" and body["api_key"] == "phc_test")
        env = envelopes[-1][1][0] if envelopes else {}
        check(f"{site}: tantr's road got one collect.submission, formId waitlist v2, with the address",
              len(envelopes) == 1 and isinstance(envelopes[0][1], list) and env.get("type") == "collect.submission"
              and env.get("direction") == "up" and env["meta"]["origin"] == "app" and env["payload"]["formId"] == "waitlist"
              and env["payload"]["formVersion"] == 2 and env["payload"]["answers"]["email"] == f"night.test+{site}@example.com"
              and len(env["id"]) == 36)
        page.fill("input[type=email]", f"night.test+{site}@example.com"); page.click("form.join button")
        check(f"{site}: the same address again is not sent twice", "already on the list" in note.inner_text() and len(seen) == 1)
        page.evaluate("document.querySelector('input[name=company]').value = 'bot inc'")
        page.fill("input[type=email]", "bot@example.com"); page.click("form.join button")
        check(f"{site}: the honeypot swallows a bot", len(seen) == 1)
        page.evaluate("document.querySelector('input[name=company]').value = ''")
        Capture.fail = "posthog"
        page.fill("input[type=email]", "blocked@example.com"); page.click("form.join button")
        page.wait_for_function("document.querySelector('.note').textContent.includes('on the list')", timeout=5000)
        check(f"{site}: with PostHog blocked the signup still arrives by tantr's road", len(envelopes) == 2 and len(seen) == 1)
        Capture.fail = "all"
        page.fill("input[type=email]", "later@example.com"); page.click("form.join button")
        page.wait_for_function("document.querySelector('.note').dataset.kind === 'err'", timeout=5000)
        check(f"{site}: a failed send says so and keeps the button usable", "did not go through" in note.inner_text() and page.locator("form.join button").is_enabled())
        Capture.fail = False
        check(f"{site}: the panel painted and no script error", page.evaluate("(()=>{const c=document.querySelector('.panel canvas');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]>40)n++;return n})()") > 500 and not errors)
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
        check(f"{site}: no sideways scroll at 390 wide", page.evaluate("document.documentElement.scrollWidth <= 390"))
        page.screenshot(path=str(ROOT / "test" / f"{site}-phone.png")); seen.clear(); envelopes.clear(); ctx.close()
    b.close()
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
