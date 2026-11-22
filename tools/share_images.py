#!/usr/bin/env python3
"""Draws the two share images (assets/og-shunya.png, assets/og-tantr.png, 1200 x 630) from the marks, with
headless Chromium. The line under the name is the first sentence of the first page's description
(articles/<site>/00-home.json), so the card says what the page says. Run by hand when a mark or
the words change, then commit the PNGs:

    python tools/share_images.py          (needs playwright, as test/e2e.py does)
"""
import json
import pathlib
import re

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent


def first_sentence(site):
    words = json.loads((ROOT / "articles" / site / "00-home.json").read_text(encoding="utf-8"))
    return re.split(r"(?<=[.!?])\s", words["description"].strip(), maxsplit=1)[0]

SHUNYA = ('<svg viewBox="-72 -72 144 144" width="300" height="300"><g fill="#d9a441">'
          '<path d="M-5 -68.06 C-25 -70 -45 -66 -52.36 -42.36 C-57.17 -26.91 -52.36 -10 -68.54 0 C-52.36 10 -57.17 26.91 -52.36 42.36 C-45 66 -25 70 -5 68.06 C-26.31 63.96 -42.36 34.72 -42.36 0 C-42.36 -34.72 -26.31 -63.96 -5 -68.06 Z"/>'
          '<path d="M5 -68.06 C25 -70 45 -66 52.36 -42.36 C57.17 -26.91 52.36 -10 68.54 0 C52.36 10 57.17 26.91 52.36 42.36 C45 66 25 70 5 68.06 C26.31 63.96 42.36 34.72 42.36 0 C42.36 -34.72 26.31 -63.96 5 -68.06 Z"/></g></svg>')
TANTR = ('<svg viewBox="0 0 112 112" width="260" height="260"><rect width="112" height="112" rx="30.24" fill="#ff5a36"/>'
         '<rect x="34.4" y="18.4" width="24" height="75.2" rx="12" fill="#f7f6f2"/><rect x="18.4" y="24.8" width="75.2" height="24" rx="12" fill="#f7f6f2"/>'
         '<circle cx="85.2" cy="85.2" r="9.2" fill="#f7f6f2"/></svg>')
CARDS = {
    "og-shunya.png": dict(bg="#050505", ink="#f5f3ee", soft="#8e8b84", accent="#d9a441", mark=SHUNYA, name="Shunya Systems",
                          line=first_sentence("shunya"), foot="shunya.systems"),
    "og-tantr.png": dict(bg="#101114", ink="#f7f6f2", soft="#9a9aa2", accent="#ff5a36", mark=TANTR, name="tantr",
                         line=first_sentence("tantr"), foot="shunya.systems/tantr"),
}
PAGE = """<!doctype html><meta charset="utf-8"><body style="margin:0;width:1200px;height:630px;background:{bg};color:{ink};
font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Inter,Roboto,'Helvetica Neue',Arial,sans-serif;display:flex;align-items:center;gap:72px;padding:0 88px;box-sizing:border-box">
<div style="flex:none">{mark}</div>
<div><div style="font-size:84px;font-weight:600;letter-spacing:-0.04em;line-height:1">{name}</div>
<div style="font-size:31px;line-height:1.3;color:{soft};margin-top:26px;max-width:640px">{line}</div>
<div style="font-size:24px;color:{accent};margin-top:34px;font-family:ui-monospace,Menlo,Consolas,monospace">{foot}</div></div></body>"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        for name, card in CARDS.items():
            page.set_content(PAGE.format(**card))
            page.screenshot(path=str(ROOT / "assets" / name))
            print("drew", name)
        browser.close()


if __name__ == "__main__":
    main()
