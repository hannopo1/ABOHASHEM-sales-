#!/usr/bin/env python3
"""Headless smoke test: boot the bundle and walk every section.

    python3 mobile/tools/smoke_test.py [path-to-html]

Loads the file over file:// exactly as a phone would.

The two datasets used to sit behind a switcher and this test walked each in
turn. They are merged now: one navigation over both payloads, so the walk is a
single pass over the unified registry. A section that vanishes from that
registry, renders empty, or throws still fails the run.

Sections are driven through the app's own `go()` rather than by clicking the
label, because several labels appear twice in the merged list (المبيعات and
العملاء exist on both the invoice and the eighteen-month side) and a text click
cannot say which one it meant. The nav itself is still exercised: the five
bottom slots and the «المزيد» sheet are clicked before the walk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "mobile" / "dist" / "Abu_Hashem_Mobile_standalone.html"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# Every section key the merged registry must still carry. Listed here so one
# silently disappearing fails the test rather than quietly shrinking the app.
EXPECTED = [
    "overview", "sales", "customers", "products",
    "receivables", "aging", "collections", "bonus",
    "r:fin", "r:sales", "r:customers", "r:brands", "r:products",
    "r:analysis", "r:forecast", "r:debt",
    "r:margin", "r:reports",
    "analytics", "quality", "r:quality",
]
MIN_CHARS = 300          # below this a section is effectively blank


def run(path: Path) -> int:
    errors: list[str] = []
    problems: list[str] = []
    result: dict = {"file": path.name, "size_mb": round(path.stat().st_size / 1e6, 1)}

    with sync_playwright() as pw:
        kw = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
        browser = pw.chromium.launch(**kw)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.as_uri())
        page.wait_for_selector("#root > div", timeout=30_000)
        page.wait_for_timeout(1500)
        result["title"] = page.title()

        registry = page.evaluate("() => window.__app.registry().map(s => s.key)")
        result["sections"] = len(registry)
        for key in EXPECTED:
            if key not in registry:
                problems.append(f"section missing from the registry — {key}")

        # The nav itself: the bottom slots, then the grouped «المزيد» sheet.
        # Scoped to the nav container — every one of these labels also appears
        # as a row or a heading inside the page body, and an unscoped text
        # match opens a detail sheet that then covers the bar.
        nav = page.locator('[data-print="nav"]')
        for label in ["المبيعات", "العملاء", "المديونية", "لوحة"]:
            try:
                nav.locator(f"text='{label}'").first.click(timeout=4000)
                page.wait_for_timeout(300)
            except Exception:
                problems.append(f"bottom nav slot not clickable — {label}")
        try:
            nav.locator("text='المزيد'").first.click(timeout=4000)
            page.wait_for_timeout(500)
            sheet = page.inner_text("#root")
            for group in ["الفواتير والمبيعات", "التحليل — 18 شهرًا",
                          "الربحية والتقارير"]:
                if group not in sheet:
                    problems.append(f"nav sheet missing its group — {group}")
            page.evaluate("() => window.__app.setState({sheet: null})")
            page.wait_for_timeout(300)
        except Exception as exc:
            problems.append(f"«المزيد» sheet did not open — {exc}")

        walked = {}
        for key in registry:
            page.evaluate("k => window.__app.go(k)", key)
            page.wait_for_timeout(700)
            body = page.inner_text("#root")
            walked[key] = {"chars": len(body), "charts": page.locator("svg").count()}
            if len(body) < MIN_CHARS:
                problems.append(f"section rendered empty — {key}")
        result["walk"] = walked
        browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        print("\nJS ERRORS:")
        for e in dict.fromkeys(errors):
            print("  " + e[:300])
    for p in problems:
        print("  PROBLEM: " + p)
    if errors or problems:
        print(f"\nFAILED — {len(set(errors))} JS error(s), {len(problems)} problem(s)")
        return 1
    print(f"\nboot OK — {len(result['walk'])} sections in one merged navigation, "
          "no JS errors")
    return 0


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT))
