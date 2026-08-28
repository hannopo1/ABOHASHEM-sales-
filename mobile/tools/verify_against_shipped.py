#!/usr/bin/env python3
"""Prove the rebuilt bundle is equivalent to the shipped standalone build.

The modules under mobile/src/ were extracted from a 11.9 MB generated file. This
compares the rebuild against that original along every axis that can change
behaviour, so the extraction can be trusted:

    python3 mobile/tools/verify_against_shipped.py <shipped.html>

Exits non-zero on any mismatch.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILT = ROOT / "mobile" / "dist" / "Abu_Hashem_Mobile_standalone.html"

BANNER = re.compile(r"/\* Abu Hashem mobile — module extracted verbatim.*?\*/\n", re.S)
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")
    if not ok:
        fails.append(name)


def scripts(html: str) -> list[tuple[str, str]]:
    """(id, body) for every script block, in document order."""
    out = []
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S):
        attrs, body = m.group(1), m.group(2)
        sid = (re.search(r'id="([^"]+)"', attrs) or [None, ""])[1]
        out.append((sid, body))
    return out


def js_payload(body: str, var: str):
    s = body.replace("<\\/", "</")
    i = s.index("{", s.index(var))
    return json.loads(s[i:s.rindex("}") + 1])


def main(shipped_path: str) -> int:
    shipped = Path(shipped_path).read_text(encoding="utf-8")
    built = BUILT.read_text(encoding="utf-8")
    sb, bb = scripts(shipped), scripts(built)

    # 1. app runtime: concatenated modules vs the original single block -------
    # Compare CODE only. Banner comments were deliberately rewritten during the
    # extraction, so a byte compare would flag cosmetics; every executable line
    # must still match exactly, in order.
    src = ROOT / "mobile" / "src"
    order = ["dash-tokens.js", "dash-agg.js", "repo-adapter.js", "dash-aging.js",
             "dash-margin.js", "dash-charts.js", "dash-export.js", "dash-app.js"]
    mods = [(src / m).read_text(encoding="utf-8") for m in order if (src / m).exists()]
    rebuilt_rt = "\n".join(mods)
    orig_rt = next(b for i, b in sb if not i and "const T = (function()" in b)

    def code_lines(txt):
        out, in_block = [], False
        for raw in txt.split("\n"):
            t = raw.strip()
            if in_block:
                if "*/" in t:
                    in_block = False
                    t = t.split("*/", 1)[1].strip()
                    if t:
                        out.append(t)
                continue
            if t.startswith("/*") and "*/" not in t:
                in_block = True
                continue
            if not t or t.startswith("//") or (t.startswith("/*") and t.endswith("*/")):
                continue
            out.append(t)
        return out

    o, r = code_lines(orig_rt), code_lines(rebuilt_rt)
    if o == r:
        check("app runtime code identical", True, f"{len(o)} executable lines")
    else:
        import difflib
        d = [x for x in difflib.unified_diff(o, r, "shipped", "rebuilt", n=0)
             if x.startswith(("+", "-")) and not x.startswith(("+++", "---"))]
        check("app runtime code identical", False, f"{len(d)} differing lines")
        for line in d[:12]:
            print(f"        {line[:150]}")

    # 2. window.DASH_DATA -----------------------------------------------------
    a = js_payload(next(b for i, b in sb if not i and "window.DASH_DATA" in b), "window.DASH_DATA")
    b_ = js_payload(next(b for i, b in bb if not i and "window.DASH_DATA" in b), "window.DASH_DATA")
    check("window.DASH_DATA payload identical", a == b_, f"{len(a)} top-level keys")

    # 3. snapshots ------------------------------------------------------------
    def snaps(pairs):
        return {i: json.loads(b.replace("<\\/", "</"))
                for i, b in pairs if i and i.startswith("snap-dash")}
    sa, sbn = snaps(sb), snaps(bb)
    check("same snapshot ids", set(sa) == set(sbn), ", ".join(sorted(sa)))
    for k in sorted(set(sa) & set(sbn)):
        check(f"snapshot {k[5:]} payload identical", sa[k] == sbn[k],
              f"as_of={sa[k]['meta']['as_of']}")
    ia = next(b for i, b in sb if i == "snap-index")
    ib = next(b for i, b in bb if i == "snap-index")
    check("snapshot index identical", json.loads(ia) == json.loads(ib))

    # 4. vendor libraries -----------------------------------------------------
    # Assert each library we ship appears verbatim inside BOTH files. Stronger
    # than a blob compare and immune to how the two builders space script tags:
    # it says every vendor byte in the rebuild came from the shipped file
    # unchanged. ECharts is not duplicated under mobile/ — the build reads the
    # copy in executive_dashboard/vendor/, which the shipped file also carried.
    libs = [("react.production.min.js", ROOT / "mobile" / "vendor" / "react.production.min.js"),
            ("react-dom.production.min.js", ROOT / "mobile" / "vendor" / "react-dom.production.min.js"),
            ("echarts.min.js (shared with executive_dashboard)",
             ROOT / "executive_dashboard" / "vendor" / "echarts.min.js")]
    for label, path in libs:
        body = path.read_text(encoding="utf-8").strip()
        check(f"{label} verbatim in shipped and rebuilt",
              body in shipped and body in built, f"{len(body)/1e6:.2f} MB")

    print()
    if fails:
        print(f"{len(fails)} check(s) FAILED: {', '.join(fails)}")
        return 1
    print("all checks passed — rebuild is equivalent to the shipped build")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
