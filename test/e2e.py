"""End to end against fake endpoints, on the site as tools/build.py renders it: both first pages and
their words, all eight articles reached from their four links, the request-access form on both
roads (a full request and an address alone) from a first page and from an article, validation,
a bot, a repeat, PostHog blocked, a network failure, no script error anywhere, phone widths, the
share images, framing (SHUNY-13, the redesign). Run: ~/yantr/.venv/bin/python test/e2e.py
(needs playwright + chromium)"""
import http.server, json, pathlib, threading, functools, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = pathlib.Path(tempfile.mkdtemp(prefix="shunya-site-e2e-")) / "dist"
subprocess.run([sys.executable, str(ROOT / "tools" / "build.py"), "--out", str(SITE)], check=True, capture_output=True)
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
HOME = {s: json.loads((ROOT / "articles" / s / "00-home.json").read_text(encoding="utf-8")) for s in ("shunya", "tantr")}
ARTS = {s: [m for m, _ in build.articles(s)] for s in ("shunya", "tantr")}


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


serve(functools.partial(Site, directory=str(SITE)), 8767); serve(Capture, 8766)
BASE = "http://127.0.0.1:8767"
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

check("content: four articles a site, in order, each with a short label",
      all(len(ARTS[s]) == 4 and [m["order"] for m in ARTS[s]] == sorted(m["order"] for m in ARTS[s]) and all(m.get("short") for m in ARTS[s]) for s in ARTS))


# How the first page's article links look: sizes, colour against --body and --accent, the hairline,
# and the WCAG contrast of each link's colour on the page background (relative luminance).
LINK_LOOK = """(() => {
  const rgb = s => s.match(/[\\d.]+/g).slice(0, 3).map(Number);
  const lum = c => { const l = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const probe = v => { const s = document.createElement('span'); s.style.color = `var(${v})`; document.body.append(s);
    const c = getComputedStyle(s).color; s.remove(); return c; };
  const bg = getComputedStyle(document.body).backgroundColor;
  const a = [...document.querySelectorAll('nav.reads a')].map(e => getComputedStyle(e));
  return { sizes: a.map(s => parseFloat(s.fontSize)), color: a[0].color, body: probe('--body'), accent: probe('--accent'),
    border: a[0].borderTopWidth, firstColor: a[0].color, firstBorder: a[0].borderTopColor,
    rest: Math.min(...a.map(s => ratio(s.color, bg))), first: ratio(a[0].color, bg) };
})()"""


def request(page, note, site, email, name="", reason="", expect="ok"):
    """Open the dialog from a Request access button, fill it, send it, wait for the answer."""
    page.locator("button.ask").first.click()
    check(f"{site}: Request access opens the form, the address field focused",
          page.evaluate("document.querySelector('dialog.request').open") and page.evaluate("document.activeElement.name") == "email")
    page.fill("input[type=email]", email); page.fill("input[name=name]", name); page.fill("input[name=reason]", reason)
    page.click("form.join button")
    if expect:
        page.wait_for_function(f"document.querySelector('.note').dataset.kind === '{expect}'", timeout=5000)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(); page = ctx.new_page()
    page.goto(f"{BASE}/privacy.html")
    page.evaluate("document.body.innerHTML = '<iframe src=\"/\" width=600 height=400></iframe>'")
    page.wait_for_timeout(1500)
    own = [f for f in page.frames if f != page.main_frame]
    check("framing: the site may frame itself", bool(own) and own[0].url.startswith(f"{BASE}/"))
    page.goto("http://127.0.0.1:8768/"); page.wait_for_timeout(1500)
    other = [f for f in page.frames if f != page.main_frame]
    check("framing: another origin is refused", bool(other) and not other[0].url.startswith(BASE))
    check("privacy: says what is collected and where it goes, both places",
          all(w in page.goto(f"{BASE}/privacy.html").text() for w in ("tantr.app", "PostHog", "name", "what you would use it for")))
    ctx.close()

    for path, site in (("/", "shunya"), ("/tantr/", "tantr")):
        ctx = b.new_context(); page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{BASE}{path}?utm_source=test"); note = page.locator(".note")
        words = HOME[site]
        # The first page: its words from 00-home.json, one source.
        check(f"{site}: the first page's title, description and button come from 00-home.json",
              page.locator("h1.id").inner_text().strip() == words["title"] and page.locator(".lede").inner_text().strip() == words["description"]
              and page.locator("button.ask").inner_text().strip() == words["button"]
              and page.locator('meta[name="description"]').get_attribute("content") == words["meta"])
        check(f"{site}: no waitlist left: no 'Launching soon', no tags", "waitlist" not in page.content().lower() and page.locator(".badge, .facts").count() == 0)
        links = page.locator("nav.reads a")
        check(f"{site}: four article links, labelled with each article's short label, in order",
              links.count() == 4 and [links.nth(i).inner_text().strip() for i in range(4)] == [m["short"] for m in ARTS[site]])
        # The form, from the first page.
        page.locator("button.ask").click()
        page.fill("input[type=email]", "not-an-email"); page.click("form.join button")
        check(f"{site}: a bad address is refused in words", "does not look like" in note.inner_text() and not seen and not envelopes)
        page.fill("input[type=email]", ""); page.fill("input[name=name]", "Night Test"); page.click("form.join button")
        check(f"{site}: a name without an address: refused, nothing sent", "does not look like" in note.inner_text() and not seen and not envelopes)
        page.keyboard.press("Escape")
        request(page, note, site, f"Night.Test+{site}@Example.com", "  Night   Test ", "A form for my shop")
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
        page.keyboard.press("Escape")
        check(f"{site}: Escape closes the form", not page.evaluate("document.querySelector('dialog.request').open"))
        request(page, note, site, f"only.mail+{site}@example.com")
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
        page.keyboard.press("Escape")
        check(f"{site}: the panel painted", page.evaluate("(()=>{const c=document.querySelector('.panel canvas');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]>40)n++;return n})()") > 500)
        page.set_viewport_size({"width": 1440, "height": 900}); page.wait_for_timeout(200)
        check(f"{site}: a desktop first page fits one screen", page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
        for w in (1440, 900):
            page.set_viewport_size({"width": w, "height": 900}); page.wait_for_timeout(200)
            st = page.evaluate(LINK_LOOK)
            check(f"{site}: at {w} wide the article links are 15-16 px in the body ink, hairline above, {st['rest']:.1f}:1 at rest",
                  all(15 <= s <= 16 for s in st["sizes"]) and st["color"] == st["body"] and st["border"] == "1px" and st["rest"] >= 4.5)
        links.nth(0).hover(); page.wait_for_timeout(300)
        hov = page.evaluate(LINK_LOOK)
        links.nth(0).focus(); page.mouse.move(0, 0); page.wait_for_timeout(300)
        foc = page.evaluate(LINK_LOOK)
        check(f"{site}: hover and focus turn a link and its hairline the brand colour, {hov['first']:.1f}:1 hovered, {foc['first']:.1f}:1 focused",
              hov["firstColor"] == hov["accent"] == hov["firstBorder"] and foc["firstColor"] == foc["accent"] and hov["first"] >= 4.5 and foc["first"] >= 4.5)
        page.set_viewport_size({"width": 1440, "height": 900}); page.mouse.move(0, 0); page.evaluate("document.activeElement.blur()"); page.wait_for_timeout(300)
        page.screenshot(path=str(ROOT / "test" / f"{site}-desktop.png"))
        page.set_viewport_size({"width": 1424, "height": 1024}); page.wait_for_timeout(200)
        check(f"{site}: at the portfolio frame's 1424 x 1024 it fits one screen", page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
        page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
        check(f"{site}: a phone stacks it: the links a 2 x 2 grid of 48 dp rows, then the panel",
              page.evaluate("""(() => { const a = [...document.querySelectorAll('nav.reads a')].map(e => e.getBoundingClientRect());
                const p = document.querySelector('.panel').getBoundingClientRect();
                return a.length === 4 && a.every(r => r.height >= 48) && a[0].top === a[1].top && a[2].top > a[0].top && a[1].left > a[0].left && p.top > a[3].bottom; })()"""))
        check(f"{site}: no sideways scroll at 390 wide", page.evaluate("document.documentElement.scrollWidth <= 390"))
        page.screenshot(path=str(ROOT / "test" / f"{site}-phone.png"), full_page=True)
        page.set_viewport_size({"width": 320, "height": 640}); page.wait_for_timeout(200)
        check(f"{site}: no sideways scroll at 320 wide", page.evaluate("document.documentElement.scrollWidth <= 320"))
        page.set_viewport_size({"width": 1280, "height": 800})

        # All four articles, reached from the first page's links.
        for i, m in enumerate(ARTS[site]):
            page.goto(f"{BASE}{path}"); page.locator("nav.reads a").nth(i).click(); page.wait_for_load_state()
            want = f"{'/tantr' if site == 'tantr' else ''}/articles/{m['slug']}/"
            check(f"{site}: link {i + 1} reaches '{m['title']}' at {want}",
                  page.url == f"{BASE}{want}" and page.locator("article.read h1").inner_text().strip() == m["title"]
                  and page.locator(".summary").inner_text().strip() == m["summary"] and f"{m['minutes']} min read" in page.locator(".meta").inner_text()
                  and page.locator('meta[property="og:title"]').get_attribute("content") == m["title"]
                  and page.locator('meta[property="og:description"]').get_attribute("content") == m["summary"]
                  and page.locator("a.brand").get_attribute("href") == path)
            check(f"{site}: '{m['slug']}' links its neighbours",
                  page.locator('.pager a[rel="prev"]').count() == (1 if i > 0 else 0) and page.locator('.pager a[rel="next"]').count() == (1 if i < 3 else 0))
            page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(150)
            check(f"{site}: '{m['slug']}' at 390 wide: no sideways scroll, tables scroll in their own box",
                  page.evaluate("document.documentElement.scrollWidth <= 390")
                  and page.evaluate("[...document.querySelectorAll('.read table, .read pre')].every(t => t.getBoundingClientRect().right <= 390)"))
            page.set_viewport_size({"width": 1280, "height": 800})
        # A request from the end of an article.
        request(page, note, site, f"from.article+{site}@example.com")
        check(f"{site}: a request from an article's end arrives on both roads, from that page",
              len(seen) == 3 and seen[-1][1]["properties"]["page"].endswith(f"/articles/{ARTS[site][-1]['slug']}/") and len(envelopes) == 4)
        # The three 503s are this test's own: the fake endpoints failing on purpose above.
        unexpected = [e for e in errors if "status of 503" not in e]
        check(f"{site}: no script or console error on the first page or any article (beyond the three 503s asked for)",
              not unexpected and len(errors) - len(unexpected) == 3)
        seen.clear(); envelopes.clear(); ctx.close()

    page = b.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/logo/")
    check("logo: the page shows the mark and its three files answer", page.locator("h1").inner_text().startswith("A zero") and page.locator("svg.mk").count() >= 10
          and all(page.request.get(f"{BASE}/logo/{a.get_attribute('href')[2:]}").ok and "<svg" in page.request.get(f"{BASE}/logo/{a.get_attribute('href')[2:]}").text() for a in page.locator("a[download]").all())
          and page.locator("a[download]").count() == 3 and not errors)
    page.goto(f"{BASE}/")
    check("home: the heading carries the mark (two braces, no ring) and the footer links to /logo/",
          page.locator("h1 a.brand svg path").count() == 2 and page.locator("h1 a.brand svg circle").count() == 0 and page.locator('footer a[href="/logo/"]').count() == 1
          and "M-5 -68.06" in page.request.get(f"{BASE}/assets/shunya.svg").text())
    for path, img in (("/", "og-shunya.png"), ("/tantr/", "og-tantr.png")):
        page.goto(f"{BASE}{path}")
        got = page.request.get(f"{BASE}/assets/{img}")
        check(f"{img}: the page names it as its share image and the file is a 1200 x 630 PNG",
              page.locator('meta[property="og:image"]').get_attribute("content") == f"https://shunya.systems/assets/{img}"
              and page.locator('meta[name="twitter:card"]').get_attribute("content") == "summary_large_image"
              and got.ok and got.body()[:8] == b"\x89PNG\r\n\x1a\n" and got.body()[16:24] == (1200).to_bytes(4, "big") + (630).to_bytes(4, "big"))
    page.goto(f"{BASE}/tantr/")
    check("tantr: the heading and the favicon carry the Spark mark (tile, stem, crossbar, idea node)",
          page.locator("h1 a.brand svg rect").count() == 3 and page.locator("h1 a.brand svg circle").count() == 1 and page.locator("h1 a.brand svg path").count() == 0
          and 'rx="30.24"' in page.request.get(f"{BASE}/assets/tantr.svg").text())
    page.goto(f"{BASE}/logo/")
    page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(200)
    check("logo: no sideways scroll at 390 wide", page.evaluate("document.documentElement.scrollWidth <= 390"))
    page.screenshot(path=str(ROOT / "test" / "logo-phone.png"), full_page=True); page.close()
    b.close()
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
