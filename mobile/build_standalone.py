#!/usr/bin/env python3
"""Assemble the Abu Hashem mobile app into one portable HTML file.

Mirrors executive_dashboard/make_standalone.py: everything (React, ECharts, the
dataset, the AR snapshots, the app modules) is inlined, so the result opens from
file:// on a phone with no server and no network.

    python3 mobile/build_standalone.py

Output: mobile/dist/Abu_Hashem_Mobile_standalone.html

Sources are read in place and never copied into mobile/:
  * ECharts        <- executive_dashboard/vendor/echarts.min.js  (byte-identical
                      to the copy the shipped build carried; kept single so both
                      dashboards stay pinned to one version)
  * window.DASH_DATA <- dashboards/data.js (produced by
                      analysis/10_export_dashboard_data.py)
Only the AR snapshots live under mobile/data/, because they are build.py exports
that were never committed anywhere else in the repo.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
SRC = APP / "src"
SNAPS = APP / "data" / "snapshots"

# Reused from elsewhere in the repo rather than duplicated here.
ECHARTS = ROOT / "executive_dashboard" / "vendor" / "echarts.min.js"
DASH_DATA_JS = ROOT / "dashboards" / "data.js"
# Profitability payload from analysis/13_join_cost_margin.py. Deliberately a
# separate global: dashboards/data.js is the desktop dashboard's data contract
# and nothing here should perturb it. Absent -> the app hides the section.
MARGIN_JSON = ROOT / "data" / "processed" / "margin_dashboard.json"
FONT_DIR = ROOT / "executive_dashboard" / "vendor" / "fonts"
ASSETS = APP / "assets"

# Cairo carries the Arabic text and is embedded as a data URI. The shipped build
# pulled it from fonts.googleapis.com, which broke its own "opens with no
# network" promise: offline (a phone in airplane mode) Arabic silently fell back
# to a system face. Numerals ask for JetBrains Mono and fall back to the system
# monospace stack already named in app.css, so no second family is embedded.
FONTS = {"Cairo-400.woff2": 400, "Cairo-600.woff2": 600, "Cairo-700.woff2": 700}

# Load order matters: React before ReactDOM, tokens before the modules that use
# them, the app last.
VENDOR = ["react.production.min.js", "react-dom.production.min.js"]
MODULES = ["dash-tokens.js", "dash-agg.js", "repo-adapter.js", "dash-aging.js",
           "dash-margin.js", "dash-charts.js", "dash-export.js", "dash-app.js"]

TITLE = "أبو هاشم للحوم — لوحة الأداء"
THEME = "#0a0e1a"


def data_uri(name: str) -> str:
    return "data:image/png;base64," + b64(ASSETS / name)


def head_meta() -> str:
    """Icons, theme colour and an inline manifest, so the app can be installed
    to a phone's home screen and open chrome-free.

    No service worker, deliberately. The bundle issues no network requests at
    all — React, ECharts, the fonts, the dataset and the snapshots are inlined —
    so there is nothing for one to cache, and a worker cannot be registered from
    a blob URL anyway. Offline already works; the manifest only adds the install
    and the standalone window, and a browser will only honour it when the file
    is served over http(s), not opened from file://.
    """
    manifest = json.dumps({
        "name": "أبو هاشم للحوم — لوحة الأداء",
        "short_name": "أبو هاشم",
        "lang": "ar", "dir": "rtl",
        "start_url": ".", "scope": ".",
        "display": "standalone", "orientation": "portrait",
        "background_color": THEME, "theme_color": THEME,
        "icons": [
            {"src": data_uri("icon-192.png"), "sizes": "192x192",
             "type": "image/png", "purpose": "any maskable"},
            {"src": data_uri("icon-512.png"), "sizes": "512x512",
             "type": "image/png", "purpose": "any maskable"},
        ],
    }, ensure_ascii=False)
    import base64 as _b64
    man_uri = ("data:application/manifest+json;base64,"
               + _b64.b64encode(manifest.encode("utf-8")).decode())
    return (
        f'<meta name="theme-color" content="{THEME}">\n'
        '<meta name="mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="apple-mobile-web-app-title" content="أبو هاشم">\n'
        f'<link rel="apple-touch-icon" href="{data_uri("apple-touch-icon.png")}">\n'
        f'<link rel="icon" type="image/png" href="{data_uri("icon-192.png")}">\n'
        f'<link rel="manifest" href="{man_uri}">\n')


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def font_css() -> str:
    return "\n".join(
        f"@font-face{{font-family:'Cairo';font-style:normal;font-weight:{w};"
        f"font-display:swap;src:url(data:font/woff2;base64,{b64(FONT_DIR / f)}) "
        "format('woff2');}"
        for f, w in FONTS.items())


def safe_js(txt: str) -> str:
    """Stop a literal closing script tag inside data from ending the block."""
    return txt.replace("</script", "<\\/script")


def read(p: Path) -> str:
    if not p.exists():
        raise SystemExit(f"missing input: {p.relative_to(ROOT)}")
    return p.read_text(encoding="utf-8")


def read_css(p: Path) -> str:
    """A stray </style> would close the inlined block early and dump the rest of
    the stylesheet into the page as visible text. Fail loudly instead."""
    txt = read(p)
    if "</style" in txt.lower():
        raise SystemExit(f"{p.name} contains a literal </style> tag — that is "
                         "HTML, not CSS, and would truncate the inlined block")
    return txt


def build() -> Path:
    parts: list[str] = []

    # --- vendor ------------------------------------------------------------
    for v in VENDOR:
        parts.append(f"<script>{safe_js(read(APP / 'vendor' / v))}</script>")
    parts.append(f"<script>{safe_js(read(ECHARTS))}</script>")

    # --- precomputed aggregate dataset (window.DASH_DATA) ------------------
    parts.append(f"<script>{safe_js(read(DASH_DATA_JS))}</script>")

    # --- brand marks, so the header carries the real logo, not initials ----
    parts.append("<script>window.DASH_BRAND="
                 + json.dumps({"logo": data_uri("logo-header.png"),
                               "special": data_uri("special-logo.png")},
                              ensure_ascii=False) + ";</script>")

    # --- profitability payload (window.DASH_MARGIN) ------------------------
    if MARGIN_JSON.exists():
        parts.append("<script>window.DASH_MARGIN="
                     + safe_js(read(MARGIN_JSON).strip()) + ";</script>")
    else:
        print(f"note: {MARGIN_JSON.name} missing — building without الربحية; "
              "run analysis/13_join_cost_margin.py first")

    # --- AR snapshots as inert JSON blocks, parsed on demand by the app ----
    index = json.loads(read(SNAPS / "index.json"))
    parts.append('<script type="application/json" id="snap-index">'
                 + json.dumps(index, ensure_ascii=False) + "</script>")
    for entry in index:
        payload = read(SNAPS / entry["file"]).strip()
        parts.append(f'<script type="application/json" id="snap-{entry["file"]}">'
                     + safe_js(payload) + "</script>")

    # --- app modules -------------------------------------------------------
    # No .exists() filter: MODULES is the required load order, so a renamed or
    # deleted module must stop the build. Skipping it produced a bundle that
    # loaded cleanly and then failed at runtime, with nothing printed.
    mods = [read(SRC / m) for m in MODULES]
    parts.append("<script>\n" + safe_js("\n".join(mods)) + "\n</script>")

    head = (
        '<!DOCTYPE html>\n<html dir="rtl" lang="ar">\n<head>\n<meta charset="utf-8">\n'
        # No maximum-scale: several Arabic labels render at 9-11px and
        # blocking pinch zoom leaves a low-vision reader no way to enlarge them.
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        f"<title>{TITLE}</title>\n"
        + head_meta()
        + f"<style>\n{font_css()}\n{read_css(SRC / 'app.css')}</style>\n</head>\n"
    )
    out = head + '<body>\n<div id="root"></div>\n' + "\n".join(parts) + "\n</body>\n</html>\n"

    dest = APP / "dist" / "Abu_Hashem_Mobile_standalone.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    return dest


if __name__ == "__main__":
    d = build()
    print(f"wrote {d.relative_to(ROOT)}  ({d.stat().st_size / 1e6:.1f} MB)")
