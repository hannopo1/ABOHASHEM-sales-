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

Standard library only: the rebuild workflow runs this step, and the parsing
dependencies belong to analysis/tools/extract_income_statements.py, not here.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
SRC = ROOT / "data" / "cost" / "income_statements.json"

TOL = 1.0                       # EGP; the statements are kept to the piastre
QUARTER = "2026-Q1"
QUARTER_MONTHS = ["2026-01", "2026-02", "2026-03"]

# Repeated from analysis/13_join_cost_margin.py on purpose: this step must fail
# if the two repositories ever stop describing the same June statement, and it
# must fail without importing a numbered module.
JUNE = {"period": "2026-06", "net_sales": 3_741_772.00,
        "cogs": 2_039_933.08, "gross_profit": 1_701_838.92}


def die(msg):
    sys.exit(f"14_income_statements: {msg}")


def close(a, b, tol=TOL):
    return abs(a - b) <= tol


def r2(x):
    """Round for output. Fixed precision keeps rebuilds byte-identical."""
    return None if x is None else round(float(x) + 0.0, 2)


def pct(num, den):
    return None if not den else round(num / den * 100.0, 4)


# ------------------------------------------------------------------ inputs --

def load_statements():
    if not SRC.exists():
        die(f"{SRC.relative_to(ROOT)} is missing. Run "
            f"analysis/tools/extract_income_statements.py --repo <costing repo>")
    d = json.loads(SRC.read_text(encoding="utf-8"))
    obs = d["observations"]
    if not obs:
        die("no observations in the vendored extract")
    return d["meta"], obs


def revalidate(obs):
    """Re-assert the identities on the vendored file.

    The extractor already checked these. Checking again here is deliberate
    defence in depth: this runs against what was actually committed, with a
    different implementation, so a bad hand-edit to the JSON cannot slip past
    review into a board report.
    """
    seen = set()
    for o in obs:
        p = o["period"]
        if p in seen:
            die(f"{p}: duplicated observation")
        seen.add(p)
        if not close(o["net_sales"] - o["cogs"], o["gross_profit"]):
            die(f"{p}: net sales − cost of sales ≠ gross profit")
        if not close(o["gross_profit"] - o["total_expenses"], o["net_profit"]):
            die(f"{p}: gross profit − expenses ≠ net profit")
        if o["net_sales"] <= 0:
            die(f"{p}: non-positive net sales")
        if o["cogs"] < 0:
            die(f"{p}: negative cost of sales")

    june = next((o for o in obs if o["period"] == JUNE["period"]), None)
    if june is None:
        die("the June 2026 statement is missing — it is the anchor tying this "
            "series to the costing model")
    for k, want in JUNE.items():
        if k == "period":
            continue
        if not close(june[k], want):
            die(f"2026-06 {k} is {june[k]}, but analysis/13_join_cost_margin.py "
                f"carries {want}. The statements and the costing model no "
                f"longer describe the same month.")


def invoice_revenue_by_month():
    """Measured invoiced revenue per month — the weights for the Q1 split."""
    path = P / "eda_monthly_series.csv"
    if not path.exists():
        die(f"{path.relative_to(ROOT)} is missing; run analysis/05_eda.py first")
    out = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row["month"]] = float(row["revenue"])
            except (KeyError, TypeError, ValueError):
                die(f"unreadable revenue for month {row.get('month')!r}")
    return out


# ------------------------------------------------------------- allocation --

def allocate_quarter(q, weights):
    """Split the combined Q1 statement across its three months.

    Weighted by invoiced revenue, which is measured monthly. The residual from
    rounding is placed on the largest month so the three parts always sum back
    to the quarter exactly — an allocation that does not reconcile to its own
    source would be worse than no allocation at all.
    """
    missing = [m for m in QUARTER_MONTHS if m not in weights]
    if missing:
        die(f"no invoiced revenue for {missing}; cannot weight the "
            f"{QUARTER} allocation")
    w = {m: weights[m] for m in QUARTER_MONTHS}
    total = sum(w.values())
    if total <= 0:
        die(f"invoiced revenue for {QUARTER_MONTHS} sums to {total}")

    # Only the two independent quantities are allocated. Gross and net profit
    # are then derived from them, so the identities hold inside every allocated
    # month by construction instead of surviving three separate roundings.
    independent = ("net_sales", "cogs", "total_expenses")
    biggest = max(QUARTER_MONTHS, key=lambda m: w[m])
    rows = []
    for m in QUARTER_MONTHS:
        share = w[m] / total
        rows.append({"period": m, "months": 1, "basis": "allocated",
                     "estimated": True, "source_period": QUARTER,
                     "allocation_weight": round(share, 6),
                     **{f: r2(q[f] * share) for f in independent}})

    # Round first, then push the residual onto the largest month. Correcting
    # before rounding would reintroduce the very piastres it removes, and the
    # published figures — not some intermediate — are what must sum back.
    for f in independent:
        residual = round(r2(q[f]) - sum(r[f] for r in rows), 2)
        for r in rows:
            if r["period"] == biggest:
                r[f] = round(r[f] + residual, 2)

    for r in rows:
        r["gross_profit"] = round(r["net_sales"] - r["cogs"], 2)
        r["net_profit"] = round(r["gross_profit"] - r["total_expenses"], 2)

    for f in independent + ("gross_profit", "net_profit"):
        # round() around the sum, not just the parts: adding three rounded
        # floats can land a binary ulp away from the target, and an exact
        # comparison would reject a correct allocation.
        if round(sum(r[f] for r in rows), 2) != r2(q[f]):
            die(f"{QUARTER} allocation of {f} does not sum back to the quarter")
    return rows


# ---------------------------------------------------------------- assembly --

def monthly_series(obs, weights):
    """Thirteen months: ten measured directly, three allocated from Q1."""
    rows = []
    for o in obs:
        if o["period"] == QUARTER:
            rows.extend(allocate_quarter(o, weights))
            continue
        if o["months"] != 1:
            die(f"{o['period']} spans {o['months']} months and has no "
                f"allocation rule; refusing to treat it as monthly")
        rows.append({"period": o["period"], "months": 1, "basis": "measured",
                     "estimated": False, "source_period": o["period"],
                     "allocation_weight": None,
                     "net_sales": o["net_sales"], "cogs": o["cogs"],
                     "gross_profit": o["gross_profit"],
                     "total_expenses": o["total_expenses"],
                     "net_profit": o["net_profit"]})

    for r in rows:
        r["gross_margin_pct"] = pct(r["gross_profit"], r["net_sales"])
        r["net_margin_pct"] = pct(r["net_profit"], r["net_sales"])
        for f in ("net_sales", "cogs", "gross_profit", "total_expenses",
                  "net_profit"):
            r[f] = r2(r[f])
    rows.sort(key=lambda r: r["period"])

    if len(rows) != 13:
        die(f"expected a 13-month series, assembled {len(rows)}")
    return rows


def totals(rows):
    net = sum(r["net_sales"] for r in rows)
    cogs = sum(r["cogs"] for r in rows)
    gross = sum(r["gross_profit"] for r in rows)
    profit = sum(r["net_profit"] for r in rows)
    return {"months": len(rows),
            "period_from": rows[0]["period"], "period_to": rows[-1]["period"],
            "net_sales": r2(net), "cogs": r2(cogs), "gross_profit": r2(gross),
            "net_profit": r2(profit),
            "gross_margin_pct": pct(gross, net),
            "net_margin_pct": pct(profit, net),
            "n_allocated_months": sum(1 for r in rows if r["estimated"])}


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


def main():
    meta, obs = load_statements()
    revalidate(obs)
    weights = invoice_revenue_by_month()
    rows = monthly_series(obs, weights)
    tot = totals(rows)

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
