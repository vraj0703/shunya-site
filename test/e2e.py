"""End to end against a fake capture endpoint: both pages, good address, bad address, bot, repeat,
network failure. Run: ~/yantr/.venv/bin/python test/e2e.py   (needs playwright + chromium)"""
import http.server, json, pathlib, threading, functools, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
seen = []
envelopes = []

# The headers Cloudflare sends for every page, from tools/build.py itself (it writes dist/_headers),
# so the local site behaves as the deployed one does: frame-ancestors above all.
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
PAGE_HEADERS = {}
_block = build.HEADERS.split("/*\n", 1)[1].split("\n/", 1)[0]
for line in _block.strip().splitlines():
    k, v = line.strip().split(": ", 1)
    PAGE_HEADERS[k] = v

class Site(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def end_headers(self):
        for k, v in PAGE_HEADERS.items():
            self.send_header(k, v)
        super().end_headers()
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

# Framing (PORTFOLIO-6): the portfolio shows this site in a gallery frame, so it may be framed by
# itself and by the portfolio's own origins, and by nothing else.
check("framing: no X-Frame-Options (it cannot name the portfolio)", "X-Frame-Options" not in PAGE_HEADERS)
check("framing: frame-ancestors names self, the portfolio's two hosts and its preview, nothing wider",
      PAGE_HEADERS.get("Content-Security-Policy", "").split() == ["frame-ancestors", "'self'",
      "https://www.vishalraj.space", "https://vishalraj.space",
      "https://vishal-raj-space-firebase-home--pr-28-7xiu4eqk.web.app"])

class Parent(http.server.BaseHTTPRequestHandler):
    """A page on another origin that tries to frame the site."""
    def log_message(self, *a): pass
    def do_GET(self):
        body = b'<iframe src="http://127.0.0.1:8767/" width="600" height="400"></iframe>'
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(body)
serve(Parent, 8768)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(); page = ctx.new_page()
    page.goto("http://127.0.0.1:8767/privacy.html")
    page.evaluate("document.body.innerHTML = '<iframe src=\"/\" width=600 height=400></iframe>'")
    page.wait_for_timeout(1500)
    own = [f for f in page.frames if f != page.main_frame]
    check("framing: the site may frame itself", bool(own) and own[0].url.startswith("http://127.0.0.1:8767/"))
    page.goto("http://127.0.0.1:8768/"); page.wait_for_timeout(1500)
    other = [f for f in page.frames if f != page.main_frame]
    check("framing: another origin is refused", bool(other) and not other[0].url.startswith("http://127.0.0.1:8767"))
    ctx.close()
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
    page = b.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8767/logo/")
    check("logo: the page shows the mark and its three files answer", page.locator("h1").inner_text().startswith("A zero") and page.locator("svg.mk").count() >= 10
          and all(page.request.get(f"http://127.0.0.1:8767/logo/{a.get_attribute('href')[2:]}").ok and "<svg" in page.request.get(f"http://127.0.0.1:8767/logo/{a.get_attribute('href')[2:]}").text() for a in page.locator("a[download]").all())
          and page.locator("a[download]").count() == 3 and not errors)
    page.goto("http://127.0.0.1:8767/")
    check("home: the header carries the mark (two braces, no ring) and the footer links to /logo/",
          page.locator("a.brand svg path").count() == 2 and page.locator("a.brand svg circle").count() == 0 and page.locator('footer a[href="./logo/"]').count() == 1
          and "M-5 -68.06" in page.request.get("http://127.0.0.1:8767/assets/shunya.svg").text())
    for path, img in (("/", "og-shunya.png"), ("/tantr/", "og-tantr.png")):
        page.goto(f"http://127.0.0.1:8767{path}")
        got = page.request.get(f"http://127.0.0.1:8767/assets/{img}")
        check(f"{img}: the page names it as its share image and the file is a 1200 x 630 PNG",
              page.locator('meta[property="og:image"]').get_attribute("content") == f"https://shunya.systems/assets/{img}"
              and page.locator('meta[name="twitter:card"]').get_attribute("content") == "summary_large_image"
              and got.ok and got.body()[:8] == b"\x89PNG\r\n\x1a\n" and got.body()[16:24] == (1200).to_bytes(4, "big") + (630).to_bytes(4, "big"))
    page.goto("http://127.0.0.1:8767/tantr/")
    check("tantr: the header and the favicon carry the Spark mark (tile, stem, crossbar, idea node)",
          page.locator("a.brand svg rect").count() == 3 and page.locator("a.brand svg circle").count() == 1 and page.locator("a.brand svg path").count() == 0
          and 'rx="30.24"' in page.request.get("http://127.0.0.1:8767/assets/tantr.svg").text())
    page.goto("http://127.0.0.1:8767/logo/")
    page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
    check("logo: no sideways scroll at 390 wide", page.evaluate("document.documentElement.scrollWidth <= 390"))
    page.screenshot(path=str(ROOT / "test" / "logo-phone.png"), full_page=True); page.close()
    b.close()
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
