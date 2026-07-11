#!/usr/bin/env python3
"""Inline every asset (CSS, JS libs, data, fonts) into a single portable HTML.

Produces executive_dashboard/dashboard_standalone.html — one file that opens from
anywhere with no vendor/ folder, no server and no internet.
"""
import base64
import re
from pathlib import Path

APP = Path(__file__).resolve().parent
V = APP / "vendor"

CSS = ["bootstrap.rtl.min.css", "dataTables.dataTables.min.css", "buttons.dataTables.min.css"]
JS = ["jquery.min.js", "bootstrap.bundle.min.js", "echarts.min.js", "plotly.min.js",
      "jszip.min.js", "dataTables.min.js", "dataTables.buttons.min.js",
      "buttons.html5.min.js", "buttons.print.min.js"]
FONTS = {"Cairo-400.woff2": 400, "Cairo-600.woff2": 600, "Cairo-700.woff2": 700}


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def safe_js(txt: str) -> str:
    return txt.replace("</script", "<\\/script")


def main():
    # --- fonts as data URIs ------------------------------------------------
    font_css = "\n".join(
        f"@font-face{{font-family:'Cairo';font-weight:{w};font-display:swap;"
        f"src:url(data:font/woff2;base64,{b64(V/'fonts'/f)}) format('woff2');}}"
        for f, w in FONTS.items()
    )
    # style.css minus its own @font-face block (replaced by data-URI version)
    style = (APP / "style.css").read_text(encoding="utf-8")
    style = re.sub(r"@font-face\s*\{[^}]*\}", "", style, count=len(FONTS))

    vendor_css = "\n".join((V / c).read_text(encoding="utf-8") for c in CSS)
    head_style = f"<style>{vendor_css}\n{font_css}\n{style}</style>"

    # --- body from index.html (strip external link/script refs) -----------
    html = (APP / "index.html").read_text(encoding="utf-8")
    body = html[html.index("<body"):html.index("</body>")]
    body = re.sub(r'\s*<link[^>]*>', "", body)
    body = re.sub(r'\s*<script src="[^"]*"></script>', "", body)

    # --- inline scripts in order ------------------------------------------
    scripts = []
    for j in JS:
        scripts.append(f"<script>{safe_js((V/j).read_text(encoding='utf-8'))}</script>")
    scripts.append(f"<script>{safe_js((APP/'data.js').read_text(encoding='utf-8'))}</script>")
    scripts.append(f"<script>{safe_js((APP/'script.js').read_text(encoding='utf-8'))}</script>")

    out = (
        '<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>أبو هاشم للحوم — لوحة الأداء التنفيذي · يونيو ٢٠٢٦</title>\n"
        f"{head_style}\n</head>\n{body}\n{''.join(scripts)}\n</body>\n</html>\n"
    )
    dest = APP / "dashboard_standalone.html"
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest}  ({dest.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
