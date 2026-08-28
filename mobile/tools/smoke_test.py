#!/usr/bin/env python3
"""Headless smoke test: boot the bundle and walk every section of both datasets.

    python3 mobile/tools/smoke_test.py [path-to-html]

Loads the file over file:// exactly as a phone would. The app carries two
independent datasets and switches between them, so both are exercised:

  تفصيلي   window.DASH      — the AR snapshots (11 sections)
  18 شهرًا  window.DASH_DATA — the repo's precomputed aggregates (9 sections)

Fails on any JS error, any section that renders empty, or any section missing
from the nav — so a broken build cannot pass silently.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "mobile" / "dist" / "Abu_Hashem_Mobile_standalone.html"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# Section labels per dataset, kept here so one silently vanishing fails the test.
PATHS = {
    "تفصيلي": ["لوحة المعلومات", "المبيعات", "العملاء", "المنتجات", "المديونية",
               "التحصيل والتسويات", "الحوافز", "التحليلات المتقدمة",
               "جودة البيانات", "أعمار العملاء", "حركة المديونية"],
    "18 شهرًا": ["المالية", "المبيعات", "العملاء", "المديونية", "العلامات",
                 "الأصناف", "التنبؤ", "جودة البيانات", "التحليل التفاعلي"],
}
MIN_CHARS = 300          # below this a section is effectively blank


def walk(page, labels, problems, key):
    out = {}
    for label in labels:
        try:
            page.locator(f"text='{label}'").first.click(timeout=2500)
        except Exception:
            try:                                  # not on the five-slot bar
                page.locator("text='المزيد'").first.click(timeout=4000)
                page.wait_for_timeout(350)
                page.locator(f"text='{label}'").first.click(timeout=4000)
            except Exception:
                problems.append(f"{key}: section not reachable — {label}")
                continue
        page.wait_for_timeout(750)
        body = page.inner_text("#root")
        out[label] = {"chars": len(body), "charts": page.locator("svg").count()}
        if len(body) < MIN_CHARS:
            problems.append(f"{key}: section rendered empty — {label}")
    return out


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

        for tab, labels in PATHS.items():
            page.locator(f"text='{tab}'").first.click(timeout=5000)
            page.wait_for_timeout(900)
            result[tab] = walk(page, labels, problems, tab)
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
    n = sum(len(v) for k, v in result.items() if k in PATHS)
    print(f"\nboot OK — {n} sections across both datasets, no JS errors")
    return 0


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT))
