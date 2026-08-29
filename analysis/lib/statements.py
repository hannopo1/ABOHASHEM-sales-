"""The company-level income-statement series, as a library.

This code used to live inside analysis/14_income_statements.py and had exactly
one caller. It moved here when analysis/13_join_cost_margin.py needed the same
series to calibrate its per-item costs against, because 14 runs *after* 13 and
the numbered steps cannot import one another.

Nothing about the series changed in the move. 14_income_statements.py is now a
thin driver over these functions and its outputs are byte-identical.

Standard library only. The rebuild workflow runs step 14 on the stock CI image,
and the document-parsing dependencies belong to
analysis/tools/extract_income_statements.py, not here.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data" / "processed"
SRC = ROOT / "data" / "cost" / "income_statements.json"

TOL = 1.0                       # EGP; the statements are kept to the piastre
QUARTER = "2026-Q1"
QUARTER_MONTHS = ["2026-01", "2026-02", "2026-03"]

# Repeated from analysis/13_join_cost_margin.py on purpose: this must fail if
# the two repositories ever stop describing the same June statement. 13 pins
# the same figures for its own reconciliation, and a change has to be made in
# both places deliberately rather than propagating silently from one.
JUNE = {"period": "2026-06", "net_sales": 3_741_772.00,
        "cogs": 2_039_933.08, "gross_profit": 1_701_838.92,
        # net_profit too: total_expenses and net_profit can be edited together
        # in a way that still satisfies both identities, so pinning the profit
        # is what actually closes that hole.
        "net_profit": 418_841.92}

# Set by the calling step so an abort names the step the user actually ran.
_WHO = "lib.statements"


def set_caller(name):
    """Name the running step, so an abort message points at what was invoked."""
    globals()["_WHO"] = name


def die(msg):
    sys.exit(f"{_WHO}: {msg}")


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


def series():
    """The whole series in one call, for a caller that only wants the numbers.

    Returns (meta, rows). Aborts on any failed identity, exactly as step 14
    does — a caller wanting the series must not get a silently unchecked one.
    """
    meta, obs = load_statements()
    revalidate(obs)
    return meta, monthly_series(obs, invoice_revenue_by_month())


def ratios():
    """{month: {"cogs": r, "opex": r, "basis": …, "estimated": …}}.

    The cost and expense ratios each month's statement reports, which is what
    analysis/13_join_cost_margin.py calibrates its per-item costs onto. Returns
    None when the vendored extract is absent, so a checkout without it keeps
    the pre-calibration behaviour rather than failing.
    """
    if not SRC.exists():
        return None
    _, rows = series()
    return {r["period"]: {"cogs": r["cogs"] / r["net_sales"],
                          "opex": r["total_expenses"] / r["net_sales"],
                          "net_sales": r["net_sales"],
                          "basis": r["basis"], "estimated": r["estimated"]}
            for r in rows}
