#!/usr/bin/env python3
"""Turn the vendored income statements into a measured company-level margin
series, and attach it to the profitability payload the mobile app reads.

WHAT THIS CHANGES ABOUT THE ANALYSIS

Until now cost was measured for exactly one month (June 2026) and every other
month was an estimate behind a price-drift gate — see 13_join_cost_margin.py.
The income statements measure cost of sales for thirteen months, July 2025
through July 2026, at company level.

That settles a question 13_join_cost_margin.py could only argue by inference.
Charging June-2026 unit costs against 2025 revenue produced a −2.13% operating
margin; the fixed-basket price index said this was an artefact of the period
mismatch rather than a trading loss. The statements now measure those months
directly: gross margin runs 31.6%–49.2% across 2025 and is never negative. The
excluded basis is not merely excluded any more, it is disproven — by an
independent source rather than by our own reasoning.

WHAT IT DOES NOT CHANGE

The statements are company-level. They carry no per-SKU cost, so margin by
item, customer, representative and brand stays exactly where it was: June 2026
only, behind the same gate. Nothing here widens that.

THE ONE ESTIMATE INTRODUCED HERE

January–March 2026 arrived as a single combined quarterly statement, not three
monthly ones. It is split across the three months in proportion to invoiced
revenue, which is measured per month in eda_monthly_series.csv. That is an
estimate laid on top of measured data, so those three months are emitted with
basis="allocated" and estimated=true, and every surface that shows them — the
app, the exported workbook, the reports — must say so. The quarter itself is
also emitted, unsplit, as the observation that was actually measured.

Inputs   data/cost/income_statements.json  (see data/cost/PROVENANCE.md)
         data/processed/eda_monthly_series.csv
         data/processed/margin_dashboard.json
Outputs  data/processed/income_statements.json
         data/processed/income_statements_by_month.csv
         data/processed/margin_dashboard.json  (statements block added in place)
         data/processed/margin_summary.json    (statements block added in place)

WHERE THE SERIES ITSELF LIVES

In analysis/lib/statements.py, not here. It moved there unchanged when
analysis/13_join_cost_margin.py needed the same monthly ratios to calibrate its
per-item costs against — 13 runs before this step, and the numbered files
cannot import one another. This step is now the driver that writes the outputs.

Standard library only: the rebuild workflow runs this step, and the parsing
dependencies belong to analysis/tools/extract_income_statements.py, not here.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import statements as S            # noqa: E402

S.set_caller("14_income_statements")

ROOT = S.ROOT
P = S.P
QUARTER = S.QUARTER
QUARTER_MONTHS = S.QUARTER_MONTHS

die = S.die


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path, rows):
    cols = ["period", "basis", "estimated", "source_period", "net_sales",
            "cogs", "gross_profit", "gross_margin_pct", "total_expenses",
            "net_profit", "net_margin_pct"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def attach(name, block):
    """Add the series to an existing margin payload, in place.

    Two consumers read these files and both must see the same numbers: the
    mobile app inlines margin_dashboard.json as window.DASH_MARGIN, and the
    PDF report reads margin_summary.json. Attaching to both is what stops the
    two documents from disagreeing about the same month.

    Deliberately not a new file or a new global: everything downstream already
    loads these two, and a third payload would be one more thing to keep in
    step for no gain.
    """
    path = P / name
    if not path.exists():
        die(f"{path.relative_to(ROOT)} is missing; run "
            f"analysis/13_join_cost_margin.py first")
    d = json.loads(path.read_text(encoding="utf-8"))
    d["statements"] = block
    write_json(path, d)


def expense_block(rows, obs, weights):
    """What the line items need alongside themselves, and nothing they repeat.

    The items themselves already travel inside by_month; copying them into a
    second shape would create two numbers to keep in step. What does not live
    there is the reading applied to them (the alias map), how far the detail
    reaches (coverage, counted from the data rather than written down), and the
    rows the sheets contain but no group total counted.
    """
    # One row per STATEMENT, not per month. 2026-Q1 arrived as a single
    # quarterly document, so its line items describe three months at once and
    # belong to the quarter — attaching them to January, February or March
    # would claim a monthly breakdown the accountant never wrote.
    by_statement = []
    for o in sorted(obs, key=lambda o: o["period"]):
        items = S.expense_items(o)
        by_statement.append({
            "period": o["period"], "months": o["months"],
            "source": o["source"],
            "net_sales": S.r2(o["net_sales"]),
            "total_expenses": S.r2(o["total_expenses"]),
            "groups": o.get("expenses"),
            "categories": S.category_totals(items),
            # Said by the document itself: a statement that names an operating
            # group is one that declared all four categories.
            "four_way": "operating" in (o.get("expenses") or {}),
            "expense_items": items,
        })

    detail = [r["period"] for r in rows if r["has_item_detail"]]
    # A month that invoiced but filed no statement is absent, not zero. It is
    # named here so the app can say so instead of drawing a gap.
    have = {r["period"] for r in rows}
    invoiced = sorted(m for m in weights if m not in have)

    outside = []
    for o in obs:
        for it in o.get("expense_rows_outside_totals") or []:
            outside.append(dict(it, period=o["period"]))

    stated = [b["period"] for b in by_statement if b["four_way"]]
    return {
        "aliases": S.aliases.alias_table(),
        "categories": {
            "order": S.categories.CATEGORIES,
            "labels": S.categories.CATEGORY_LABELS,
            # The three statements that print the four groups themselves. Every
            # other row's category was read, not stated, and each item says so.
            "stated_periods": stated,
            "decisions": S.categories.decision_table(),
        },
        "by_statement": by_statement,
        "coverage": {
            "statements": len(by_statement),
            "statements_with_item_detail": sum(
                1 for b in by_statement if b["expense_items"]),
            "months": len(rows),
            "months_with_item_detail": len(detail),
            "item_detail_periods": detail,
            "total_only_periods": [r["period"] for r in rows
                                   if not r["has_item_detail"]],
            "allocated_periods": [r["period"] for r in rows if r["estimated"]],
            "no_statement_periods": invoiced,
            "n_items": sum(len(r["expense_items"]) for r in rows),
        },
        "rows_outside_totals": outside,
    }


def main():
    meta, obs = S.load_statements()
    S.revalidate(obs)
    weights = S.invoice_revenue_by_month()
    rows = S.monthly_series(obs, weights)
    tot = S.totals(rows)

    block = {
        "meta": {
            "source_repo": meta["source_repo"],
            "source_commit": meta["source_commit"],
            "see": "data/cost/PROVENANCE.md",
            "level": "company",
            "n_observations": len(obs),
            "quarter_period": QUARTER,
            "quarter_months": QUARTER_MONTHS,
            # Said here so it travels with the data rather than living only in
            # the app's copy: these statements do not cover the same span as
            # the invoices, and neither window may be described by the other.
            "sales_window": "2025-01..2026-06",
            "statement_window": f"{tot['period_from']}..{tot['period_to']}",
        },
        "totals": tot,
        "by_month": rows,
        "expenses": expense_block(rows, obs, weights),
    }

    write_json(P / "income_statements.json",
               {"meta": dict(meta, **block["meta"]), "totals": tot,
                "observations": obs, "by_month": rows})
    write_csv(P / "income_statements_by_month.csv", rows)
    attach("margin_dashboard.json", block)
    attach("margin_summary.json", block)

    print(f"14_income_statements: {len(obs)} observations -> "
          f"{tot['months']} months ({tot['period_from']}..{tot['period_to']}), "
          f"{tot['n_allocated_months']} allocated from {QUARTER}")
    print(f"  net sales {tot['net_sales']:>15,.2f}")
    print(f"  cost of sales {tot['cogs']:>11,.2f}")
    print(f"  gross profit {tot['gross_profit']:>12,.2f}  "
          f"({tot['gross_margin_pct']:.2f}%)")
    print(f"  net profit {tot['net_profit']:>14,.2f}  "
          f"({tot['net_margin_pct']:.2f}%)")
    print("  wrote income_statements.json, income_statements_by_month.csv, "
          "and the statements block of margin_dashboard.json + "
          "margin_summary.json")


if __name__ == "__main__":
    main()
