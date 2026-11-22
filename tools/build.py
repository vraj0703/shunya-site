#!/usr/bin/env python3
"""Builds the site into dist/ for Cloudflare (Workers static assets, see wrangler.jsonc): the pages and assets only (no tools, tests or
README), plus config.js written from the environment and a _headers file.

The two first pages and every article are rendered here (the redesign from Vishal's wireframe):
  articles/<site>/00-home.json      the first page's words: title, description, button, meta
                                    (the page's meta description)
  articles/<site>/NN-slug.html      an article: first line an HTML comment holding JSON
                                    {"title","short","summary","slug","order","minutes"} (short:
                                    the first page's link label), then a body
                                    fragment in plain semantic HTML
through templates/home.html, templates/article.html and templates/request.html (the request-access
form, SHUNY-13). Shunya's articles go to /articles/<slug>/, tantr's to /tantr/articles/<slug>/;
each first page links its articles in order. `--out DIR` builds elsewhere (the e2e test does).

  POSTHOG_TOKEN   the PostHog project token (phc_...), set in the Worker's build variables
  POSTHOG_HOST    optional, default https://us.i.posthog.com
  TANTR_SERVER    optional; empty string switches tantr's road off, unset keeps https://tantr.app

Without POSTHOG_TOKEN the build still succeeds and says so loudly: the form then sends by tantr's
road only. A token that is not a phc_ project token fails the build, so a private key never ships."""
import html
import json
import os
import pathlib
import re
import shutil
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PAGES = ["privacy.html", "logo", "assets"]
ARTICLES = ROOT / "articles"
TEMPLATES = ROOT / "templates"
ORIGIN = "https://shunya.systems"

# The two marks, inline so they take the page's accent (as the old hand-written pages had them).
SHUNYA_MARK = ('<svg viewBox="-72 -72 144 144" fill="currentColor" aria-hidden="true">'
               '<path d="M-5 -68.06 C-25 -70 -45 -66 -52.36 -42.36 C-57.17 -26.91 -52.36 -10 -68.54 0 C-52.36 10 -57.17 26.91 -52.36 42.36 C-45 66 -25 70 -5 68.06 C-26.31 63.96 -42.36 34.72 -42.36 0 C-42.36 -34.72 -26.31 -63.96 -5 -68.06 Z"/>'
               '<path d="M5 -68.06 C25 -70 45 -66 52.36 -42.36 C57.17 -26.91 52.36 -10 68.54 0 C52.36 10 57.17 26.91 52.36 42.36 C45 66 25 70 5 68.06 C26.31 63.96 42.36 34.72 42.36 0 C42.36 -34.72 26.31 -63.96 5 -68.06 Z"/></svg>')
TANTR_MARK = ('<svg viewBox="0 0 112 112" aria-hidden="true"><rect width="112" height="112" rx="30.24" fill="currentColor"/>'
              '<rect x="34.4" y="18.4" width="24" height="75.2" rx="12" fill="#f7f6f2"/><rect x="18.4" y="24.8" width="75.2" height="24" rx="12" fill="#f7f6f2"/>'
              '<circle cx="85.2" cy="85.2" r="9.2" fill="#f7f6f2"/></svg>')
LINKEDIN = '<a href="https://www.linkedin.com/in/vraj0703/" rel="noopener">LinkedIn</a>'
SITES = {
    "shunya": dict(name="Shunya Systems", mark=SHUNYA_MARK, home="/", out="", og="og-shunya.png",
                   footer=f'<a href="/tantr/">tantr</a><a href="/logo/">Logo</a><a href="/privacy.html">Privacy</a>{LINKEDIN}'),
    "tantr": dict(name="tantr", mark=TANTR_MARK, home="/tantr/", out="tantr", og="og-tantr.png",
                  footer=f'<a href="/">Shunya Systems</a><a href="https://tantr.app" rel="noopener">tantr.app</a><a href="/privacy.html">Privacy</a>{LINKEDIN}'),
}
META = re.compile(r"\A\s*<!--\s*(\{.*?\})\s*-->\s*\n?", re.S)
SLUG = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")
# An article body is plain semantic HTML: nothing that runs, nothing that loads.
UNSAFE = re.compile(r"<\s*(script|style|iframe|object|embed|form|link|meta)\b|\son[a-z]+\s*=|javascript:", re.I)
# Framing (PORTFOLIO-6): the portfolio at vishalraj.space shows this site live in a gallery frame.
# X-Frame-Options can only say SAMEORIGIN or DENY, so it gives way to frame-ancestors, which names
# the site itself, the portfolio's two hosts and its Firebase preview for that work. A CSP host
# wildcard covers only a whole leftmost label, so the previews cannot be matched more narrowly
# than *.web.app (any Firebase site): each preview channel is named instead.
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: frame-ancestors 'self' https://www.vishalraj.space https://vishalraj.space https://vishal-raj-space-firebase-home--pr-28-7xiu4eqk.web.app
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


def esc(text):
    return html.escape(str(text), quote=True)


def template(name):
    return string.Template((TEMPLATES / name).read_text(encoding="utf-8"))


def articles(site):
    """The site's articles in order: (meta, body), each checked against the contract."""
    out, slugs = [], set()
    for path in sorted((ARTICLES / site).glob("[0-9][0-9]-*.html")):
        text = path.read_text(encoding="utf-8")
        m = META.match(text)
        if not m:
            sys.exit(f"build: {path.name}: the first line must be an HTML comment holding the article's JSON")
        meta = json.loads(m.group(1))
        missing = {"title", "summary", "slug", "order", "minutes"} - meta.keys()
        if missing:
            sys.exit(f"build: {path.name}: the JSON lacks {sorted(missing)}")
        if not SLUG.match(meta["slug"]) or meta["slug"] in slugs:
            sys.exit(f"build: {path.name}: slug {meta['slug']!r} is not lower-case words with hyphens, or is taken")
        body = text[m.end():]
        bad = UNSAFE.search(body)
        if bad:
            sys.exit(f"build: {path.name}: the body may hold plain semantic HTML only, not {bad.group(0)!r}")
        slugs.add(meta["slug"])
        out.append((meta, body))
    return sorted(out, key=lambda a: (a[0]["order"], a[0]["slug"]))


def article_path(site, slug):
    base = "/tantr" if site == "tantr" else ""
    return f"{base}/articles/{slug}/"


def render(out_dir):
    """The two first pages and every article, into out_dir."""
    request = (TEMPLATES / "request.html").read_text(encoding="utf-8")
    home_t, article_t = template("home.html"), template("article.html")
    count = 0
    for site, s in SITES.items():
        words = json.loads((ARTICLES / site / "00-home.json").read_text(encoding="utf-8"))
        items = articles(site)
        og = f"{ORIGIN}/assets/{s['og']}"
        # The first page's links carry the article's short label ("short"), its title otherwise.
        links = "".join(f'<a href="{article_path(site, m["slug"])}" title="{esc(m["title"])}">{esc(m.get("short") or m["title"])}</a>'
                        for m, _ in items)
        page = home_t.substitute(
            brand=site, name=esc(s["name"]), mark=s["mark"], home=s["home"], title=esc(words["title"]),
            page_title=esc(words["title"]), description=esc(words["description"]), button=esc(words["button"]),
            meta=esc(words.get("meta") or words["description"]),
            url=f"{ORIGIN}{s['home']}", og_image=og, links=links, footer=s["footer"], request=request)
        target = out_dir / s["out"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        count += 1
        for i, (m, body) in enumerate(items):
            prev = items[i - 1][0] if i > 0 else None
            nxt = items[i + 1][0] if i + 1 < len(items) else None
            pager = ""
            if prev:
                pager += f'<a rel="prev" href="{article_path(site, prev["slug"])}"><span>Previous</span>{esc(prev["title"])}</a>'
            if nxt:
                pager += f'<a rel="next" href="{article_path(site, nxt["slug"])}"><span>Next</span>{esc(nxt["title"])}</a>'
            path = article_path(site, m["slug"])
            page = article_t.substitute(
                brand=site, name=esc(s["name"]), mark=s["mark"], home=s["home"], title=esc(m["title"]),
                page_title=esc(f"{m['title']}: {s['name']}"), summary=esc(m["summary"]), minutes=int(m["minutes"]),
                body=body.rstrip() + "\n", url=f"{ORIGIN}{path}", og_image=og, pager=pager,
                footer=s["footer"], request=request)
            target = out_dir / path.strip("/") / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
            count += 1
    return count


def main():
    out_dir = DIST
    if "--out" in sys.argv:
        out_dir = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]).resolve()
    token = os.environ.get("POSTHOG_TOKEN", "").strip()
    host = os.environ.get("POSTHOG_HOST", "").strip() or "https://us.i.posthog.com"
    if token and not token.startswith("phc_"):
        sys.exit("build: POSTHOG_TOKEN is not a phc_ project token; refusing to ship it")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for name in PAGES:
        src = ROOT / name
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, out_dir / name)
    rendered = render(out_dir)
    cfg = {"token": token, "host": host}
    if "TANTR_SERVER" in os.environ:
        cfg["tantr"] = os.environ["TANTR_SERVER"].strip()
    (out_dir / "config.js").write_text("window.WAITLIST_CONFIG = " + json.dumps(cfg) + ";\n", encoding="utf-8")
    (out_dir / "_headers").write_text(HEADERS, encoding="utf-8")
    (out_dir / "404.html").write_text(NOT_FOUND, encoding="utf-8")
    files = sum(1 for p in out_dir.rglob("*") if p.is_file())
    print(f"build: {out_dir.name}/ has {files} files ({rendered} pages rendered); PostHog token length {len(token)}, host {host}")
    if not token:
        print("build: WARNING: POSTHOG_TOKEN is not set; signups will not reach PostHog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
