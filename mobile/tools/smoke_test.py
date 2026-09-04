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
    "receivables", "overdue", "aging", "collections", "bonus",
    "r:fin", "r:sales", "r:customers", "r:brands", "r:products",
    "r:analysis", "r:forecast", "r:debt",
    "r:margin", "r:expenses", "r:reports",
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
            for group in ["الفواتير والمبيعات", "التحليل — ",
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

        # --- the labels must be DERIVED, not written -------------------------
        # Every one of these was a literal typed into the string that displayed
        # it, and every one of them went on asserting a window that had moved:
        # the nav said «يناير – يوليو 2026» after August landed, the badge said
        # «18 شهرًا» after the series reached twenty, and «المالية» announced an
        # AR snapshot dated 2026/7/4 two months after the balances were re-struck.
        # A grep over the rendered app is the only check that catches the next one.
        page.evaluate("() => window.__app.go('overview')")
        page.wait_for_timeout(400)
        seen = {}
        for key in registry:
            page.evaluate("k => window.__app.go(k)", key)
            page.wait_for_timeout(250)
            seen[key] = page.inner_text("#root")
        page.evaluate("() => window.__app.setState({sheet: 'nav'})")
        page.wait_for_timeout(400)
        seen["__nav"] = page.inner_text("#root")
        page.evaluate("() => window.__app.setState({sheet: null})")
        all_text = "\n".join(seen.values())

        # Matched as the LABEL, not as a bare date: "2026/7/4" is also a real
        # invoice date for a real customer, and a customer's own dates must not
        # trip a check about the app's chrome.
        # The last two are the pre-due-date wording: the app now applies a real
        # 30-day term, so calling its aging "تقديرية" or claiming the source has
        # no due dates would understate a rule it actually enforces.
        STALE = ["18 شهرًا", "لقطة 2026/7/4", "بتاريخ 2026/7/4",
                 "يناير – يوليو 2026", "يناير 2025 – يونيو 2026",
                 "الأعمار تقديرية", "لا تواريخ استحقاق بالمصدر"]
        for bad in STALE:
            hits = sorted(k for k, v in seen.items() if bad in v)
            if hits:
                problems.append(f"stale hard-coded label «{bad}» in: {hits[:6]}")

        # and the derived ones must actually appear
        meta = page.evaluate("() => (window.__app.state.api||{}).D "
                             "? window.__app.state.api.D.meta : null")
        if not meta or not meta.get("snapshot_date"):
            problems.append("payload carries no meta.snapshot_date")
        else:
            result["snapshot_date"] = meta["snapshot_date"]
            result["as_of"] = meta.get("as_of")
            if meta["snapshot_date"] == meta.get("as_of"):
                problems.append("snapshot_date must not be re-dated to as_of")
        for want in ["لقطة 4 سبتمبر 2026", "يناير – أغسطس 2026"]:
            if want not in all_text:
                problems.append(f"derived label missing everywhere — «{want}»")

        # --- المصروفات: what it must show, and what it must never show ------
        # The section exists to open up an expense total that used to be one
        # number. Two failure modes matter more than the rest: a month with no
        # income statement quietly appearing with a figure, and the six detailed
        # months losing their detail in a refactor.
        exp = seen.get("r:expenses", "")
        if not exp:
            problems.append("«المصروفات» section is not in the registry")
        else:
            for want in ["يوليو 2025", "مرتبات", "ايجارات",
                         "كل بند على حدة", "توحيد أسماء البنود"]:
                if want not in exp:
                    problems.append(f"«المصروفات» is missing «{want}»")
            # August 2026 filed no income statement. It may be NAMED as absent
            # — that is the point of the coverage card — but it must never be
            # shown carrying an expense figure, so it must not appear as a row
            # of the monthly table.
            months = page.evaluate("""() => {
                const S = (window.DASH_MARGIN||{}).statements;
                if(!S) return null;
                return {periods: (S.by_month||[]).map(r => r.period),
                        detail: (S.by_month||[]).filter(r => r.has_item_detail)
                                                .map(r => r.period),
                        items: (S.by_month||[]).reduce(
                                  (a,r) => a + (r.expense_items||[]).length, 0),
                        allocatedWithItems: (S.by_month||[])
                          .filter(r => r.basis === "allocated"
                                    && (r.expense_items||[]).length).length};
            }""")
            if not months:
                problems.append("the statements block carries no by_month")
            else:
                result["expenses"] = months
                if "2026-08" in months["periods"]:
                    problems.append("2026-08 has no income statement but "
                                    "appears in the expense series")
                if len(months["detail"]) < 6:
                    problems.append("fewer than six months carry expense line "
                                    f"items: {months['detail']}")
                if months["allocatedWithItems"]:
                    problems.append("an allocated month carries line items — "
                                    "allocation divides magnitudes, it does not "
                                    "create items")

        # The debt is a stock struck on one date. It used to be re-totalled over
        # "customers invoiced in the selected month", so the August view read
        # 2,275,995 against a real 2,942,822 and hid 666,827 that was overdue to
        # the last pound. Read the KPI through the app's own aggregator under two
        # different months: the number must not move.
        debt = page.evaluate("""() => {
            const api = window.__app.state.api; if(!api) return null;
            const at = m => api.buildContext({month: m}).kpis;
            const a = at('all'), b = at('2026-08'), c = at('2026-01');
            return {all: a.outstanding, aug: b.outstanding, jan: c.outstanding,
                    overdue_all: a.overdue, overdue_aug: b.overdue};
        }""")
        if not debt:
            problems.append("could not read the receivables KPI")
        else:
            result["debt"] = debt
            if not (abs(debt["all"] - debt["aug"]) < 0.02
                    and abs(debt["all"] - debt["jan"]) < 0.02):
                problems.append(
                    "receivables move with the month filter: "
                    f"all={debt['all']:,.2f} aug={debt['aug']:,.2f} jan={debt['jan']:,.2f}")
            if abs(debt["overdue_all"] - debt["overdue_aug"]) >= 0.02:
                problems.append("overdue moves with the month filter")

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
