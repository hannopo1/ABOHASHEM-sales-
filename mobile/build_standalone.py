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
    mods = [read(SRC / m) for m in MODULES if (SRC / m).exists()]
    parts.append("<script>\n" + safe_js("\n".join(mods)) + "\n</script>")

    head = (
        '<!DOCTYPE html>\n<html dir="rtl" lang="ar">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'maximum-scale=1, viewport-fit=cover">\n'
        f"<title>{TITLE}</title>\n"
        f"<style>\n{font_css()}\n{read_css(SRC / 'app.css')}</style>\n</head>\n"
    )
    out = head + '<body>\n<div id="root"></div>\n' + "\n".join(parts) + "\n</body>\n</html>\n"

    dest = APP / "dist" / "Abu_Hashem_Mobile_standalone.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    return dest


if __name__ == "__main__":
    d = build()
    print(f"wrote {d.relative_to(ROOT)}  ({d.stat().st_size / 1e6:.1f} MB)")
