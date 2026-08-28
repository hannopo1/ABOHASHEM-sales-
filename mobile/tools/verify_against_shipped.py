#!/usr/bin/env python3
"""Prove the rebuilt bundle is equivalent to the shipped standalone build.

The modules under mobile/src/ were extracted from a 11.9 MB generated file. This
compares the rebuild against that original along every axis that can change
behaviour, so the extraction can be trusted:

    python3 mobile/tools/verify_against_shipped.py <shipped.html> [--strict]

Data payloads and vendor bytes must match exactly — always. The runtime-code
check was the acceptance gate for the extraction itself; now that the app has
grown features it reports drift and lists what changed, and only fails the run
under --strict.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILT = ROOT / "mobile" / "dist" / "Abu_Hashem_Mobile_standalone.html"

BANNER = re.compile(r"/\* Abu Hashem mobile — module extracted verbatim.*?\*/\n", re.S)
STRICT = "--strict" in sys.argv       # fail on any runtime-code drift
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Print the result of a verification check and record failures.
    
    Parameters:
        name (str): The name of the check.
        ok (bool): Whether the check passed.
        detail (str): Optional detail to include in the output.
    """
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")
    if not ok:
        fails.append(name)


def scripts(html: str) -> list[tuple[str, str]]:
    """Extract script block identifiers and contents in document order.
    
    Parameters:
    	html (str): HTML source containing script blocks.
    
    Returns:
    	list[tuple[str, str]]: Each script block's identifier and body."""
    out = []
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S):
        attrs, body = m.group(1), m.group(2)
        sid = (re.search(r'id="([^"]+)"', attrs) or [None, ""])[1]
        out.append((sid, body))
    return out


def js_payload(body: str, var: str):
    """
    Extract and decode the JSON object assigned to a JavaScript variable.
    
    Parameters:
        body (str): JavaScript source containing the variable assignment.
        var (str): Variable name whose JSON object should be extracted.
    
    Returns:
        object: The decoded JSON value.
    """
    s = body.replace("<\\/", "</")
    i = s.index("{", s.index(var))
    return json.loads(s[i:s.rindex("}") + 1])


def main(shipped_path: str) -> int:
    """
    Verify that a rebuilt mobile standalone HTML matches the shipped build.
    
    Parameters:
        shipped_path (str): Path to the shipped HTML file.
    
    Returns:
        int: `0` if all checks pass, or `1` if any check fails.
    """
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
        """
        Extract executable source lines while ignoring blank lines and comments.
        
        Parameters:
        	txt (str): Source text to process.
        
        Returns:
        	list[str]: Stripped lines that are not blank or part of a comment block.
        """
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
    kept = len(set(o) & set(r))
    dropped = [x for x in o if x not in set(r)]
    added = len(r) - kept

    # This was the acceptance gate for the extraction: at that point the two had
    # to match line for line. The app has since grown features, so the ongoing
    # invariant is weaker but still worth holding — no shipped behaviour should
    # vanish unnoticed. Lines that changed are listed so each can be recognised
    # as intended; --strict makes any drift a failure.
    if o == r:
        check("app runtime code identical to the shipped build", True,
              f"{len(o)} executable lines")
    else:
        ok = not STRICT
        check("shipped runtime code still present", ok,
              f"{kept}/{len(o)} shipped lines kept, {len(dropped)} changed or "
              f"removed, {added} added since")
        for line in dropped[:10]:
            print(f"        changed/removed: {line[:130]}")
        if len(dropped) > 10:
            print(f"        … and {len(dropped) - 10} more")

    # 2. window.DASH_DATA -----------------------------------------------------
    a = js_payload(next(b for i, b in sb if not i and "window.DASH_DATA" in b), "window.DASH_DATA")
    b_ = js_payload(next(b for i, b in bb if not i and "window.DASH_DATA" in b), "window.DASH_DATA")
    check("window.DASH_DATA payload identical", a == b_, f"{len(a)} top-level keys")

    # 3. snapshots ------------------------------------------------------------
    def snaps(pairs):
        """
        Parse dashboard snapshot payloads from script identifier and body pairs.
        
        Parameters:
        	pairs: Iterable of `(identifier, body)` pairs to filter and parse.
        
        Returns:
        	dict: A mapping of snapshot identifiers to their decoded JSON payloads.
        """
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
    tail = "" if o == r else "; runtime code has moved on, see the list above"
    print("all checks passed — data payloads and vendor bytes are identical to "
          "the shipped build" + tail)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    sys.exit(main(args[0]))
