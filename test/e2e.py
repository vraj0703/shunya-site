"""End to end against a fake capture endpoint: both pages, a full request and an address alone on
both roads, bad address, bot, repeat, PostHog blocked, network failure (SHUNY-13). Run: ~/yantr/.venv/bin/python test/e2e.py   (needs playwright + chromium)"""
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
        # SHUNY-13: request access, not the waitlist.
        check(f"{site}: the heading and the button say Request access",
              page.locator("h1").inner_text() == "Request access" and page.locator("form.join button").inner_text() == "Request access"
              and page.locator("form.join input[name=name]").count() == 1 and page.locator("form.join input[name=reason]").count() == 1)
        page.fill("input[type=email]", "not-an-email"); page.click("form.join button")
        check(f"{site}: a bad address is refused in words", "does not look like" in note.inner_text() and not seen and not envelopes)
        page.fill("input[type=email]", "")
        page.fill("input[name=name]", "Night Test"); page.click("form.join button")
        check(f"{site}: no address, a name alone: refused, nothing sent", "does not look like" in note.inner_text() and not seen and not envelopes)
        # A full request: address, name and reason.
        page.fill("input[type=email]", f"Night.Test+{site}@Example.com")
        page.fill("input[name=name]", "  Night   Test ")
        page.fill("input[name=reason]", "A form for my shop")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.note').dataset.kind === 'ok'", timeout=5000)
        check(f"{site}: the confirmation says what happens next", note.inner_text() == "Thank you. I read every request myself and will write back.")
        path_, body = seen[-1]; pr = body["properties"]
        check(f"{site}: one access_requested reaches /capture/", path_ == "/capture/" and body["event"] == "access_requested" and len(seen) == 1)
        check(f"{site}: address lowercased, on the event and on the person", body["distinct_id"] == f"night.test+{site}@example.com" == pr["email"] == pr["$set"]["email"])
        check(f"{site}: the event says a name and a reason were given, not what they are",
              pr["site"] == site and pr["has_name"] is True and pr["has_reason"] is True
              and "name" not in pr and "reason" not in pr and "Night" not in json.dumps(body) and "shop" not in json.dumps(body))
        check(f"{site}: page and utm ride along", pr["page"] == path and pr["utm_source"] == "test" and body["api_key"] == "phc_test")
        env = envelopes[-1][1][0] if envelopes else {}
        check(f"{site}: tantr's road got one collect.submission, formId access_request v1, with the whole request",
              len(envelopes) == 1 and isinstance(envelopes[0][1], list) and env.get("type") == "collect.submission"
              and env.get("direction") == "up" and env["meta"]["origin"] == "app" and env["payload"]["formId"] == "access_request"
              and env["payload"]["formVersion"] == 1 and env["payload"]["answers"] == {
                  "email": f"night.test+{site}@example.com", "site": site, "name": "Night Test", "reason": "A form for my shop"}
              and len(env["id"]) == 36)
        check(f"{site}: the form is cleared after it is sent",
              page.evaluate("[...document.querySelectorAll('form.join input.field')].every(i => i.value === '')"))
        # The address alone: name and reason are optional.
        page.fill("input[type=email]", f"only.mail+{site}@example.com"); page.click("form.join button")
        page.wait_for_function("document.querySelector('.note').dataset.kind === 'ok' && window.__n !== 2", timeout=5000)
        page.wait_for_timeout(300)
        pr2 = seen[-1][1]["properties"]; env2 = envelopes[-1][1][0]
        check(f"{site}: the address alone is a request too: has_name and has_reason false, no empty answers",
              len(seen) == 2 and len(envelopes) == 2 and pr2["has_name"] is False and pr2["has_reason"] is False
              and env2["payload"]["answers"] == {"email": f"only.mail+{site}@example.com", "site": site})
        page.fill("input[type=email]", f"only.mail+{site}@example.com"); page.click("form.join button")
        check(f"{site}: the same address again is not sent twice", "already asked" in note.inner_text() and len(seen) == 2)
        page.evaluate("document.querySelector('input[name=company]').value = 'bot inc'")
        page.fill("input[type=email]", "bot@example.com"); page.click("form.join button")
        check(f"{site}: the honeypot swallows a bot", len(seen) == 2 and len(envelopes) == 2)
        page.evaluate("document.querySelector('input[name=company]').value = ''")
        Capture.fail = "posthog"
        page.fill("input[type=email]", "blocked@example.com"); page.click("form.join button")
        page.wait_for_function("document.querySelector('.note').textContent.includes('Thank you')", timeout=5000)
        check(f"{site}: with PostHog blocked the request still arrives by tantr's road", len(envelopes) == 3 and len(seen) == 2)
        Capture.fail = "all"
        page.fill("input[type=email]", "later@example.com"); page.fill("input[name=reason]", "kept"); page.click("form.join button")
        page.wait_for_function("document.querySelector('.note').dataset.kind === 'err'", timeout=5000)
        check(f"{site}: a failed send says so, keeps what was typed and the button usable",
              "did not go through" in note.inner_text() and page.locator("form.join button").is_enabled()
              and page.input_value("input[type=email]") == "later@example.com" and page.input_value("input[name=reason]") == "kept")
        Capture.fail = False
        check(f"{site}: the panel painted and no script error", page.evaluate("(()=>{const c=document.querySelector('.panel canvas');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]>40)n++;return n})()") > 500 and not errors)
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
        check(f"{site}: no sideways scroll at 390 wide", page.evaluate("document.documentElement.scrollWidth <= 390"))
        page.set_viewport_size({"width": 320, "height": 640}); page.wait_for_timeout(200)
        check(f"{site}: no sideways scroll at 320 wide", page.evaluate("document.documentElement.scrollWidth <= 320"))
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
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
