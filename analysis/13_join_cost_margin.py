#!/usr/bin/env python3
"""Join the June-2026 costing model to sales, producing profitability by item,
customer, representative, brand and month.

Until now this repository could not show margin: its README states that the
uploaded files carry no cost data. They do — in the sibling repository
hannopo1/Abohashem, whose costing model reconciles to the June 2026 income
statement to the cent. data/cost/model_rows.json is a verbatim copy of it (see
data/cost/PROVENANCE.md).

TWO BASES, NEVER MIXED
    measured    June 2026 only. Cost is observed. Figures come straight from the
                costing model and tie to the income statement.
    indicative  Every other month. June unit costs applied to that month's
                quantities. An estimate, not a measurement — every consumer of
                these files must label it as such.

THE PRICE-DRIFT GATE
    June-2026 costs charged against 2025 revenue produce negative operating
    margins for every month of 2025. That is an artefact, not history: a
    fixed-basket (Laspeyres) price index built on June quantities shows selling
    prices sat ~15% below June 2026 until February 2026, then stepped up in
    March-April 2026. Charging today's costs against yesterday's prices while
    yesterday's costs were also lower understates margin by roughly that gap.

    So each month carries price_index, cost_period_drift_pct and a boolean
    indicative_reliable (|drift| <= MAX_DRIFT_PCT). Every month is still
    emitted — nothing is hidden — but the headline indicative figures are taken
    only from months that pass the gate, and the rest are marked unreliable so
    no consumer can quote them as if they were comparable.

A THIRD BASIS: CALIBRATED (the monthly per-dimension figures)
    The gate above leaves "monthly margin per item / customer / rep" out of
    reach: fourteen of the eighteen months fail it. The income statements close
    that gap from the other side. They carry no per-SKU cost, but they do carry
    a measured cost-of-sales *ratio* for each month at company level.

    So the model supplies the mix and the statement supplies the level. For each
    month with a statement, one factor per cost layer scales June's unit costs
    until the month's overall ratios equal the statement's:

        k_cogs = (stmt_cogs / stmt_net_sales) × Σ net_revenue / Σ cogs
        k_opex = (stmt_expenses / stmt_net_sales) × Σ net_revenue / Σ (conv+opex)

    By construction the calibrated total then reproduces the statement's ratio
    for that month exactly, while the *relative* cost of one item against
    another stays as it was measured in June.

    That is the limit of the method, and it must be said wherever the figures
    appear: calibration corrects the level, not the mix. If one item's cost
    moved differently from the rest of the basket between June and the month in
    question, nothing here can see it. These are not measured per-item margins.

    Coverage is the intersection of the two windows — invoices run 2025-01 to
    2026-06, statements 2025-07 to 2026-07, so twelve months are calibrated.
    January–June 2025 have no statement and are emitted nowhere. June 2026 is
    measured, and its factors must come out at 1.0 or the run aborts: the model
    is built against that statement, so anything else means the tie has broken.
    The three Q1-2026 months inherit estimated=true from the quarterly
    allocation they were split out of.

WHAT IS NOT DONE
    Revenue outside June is gross: the repository holds no per-SKU returns for
    other months, so indicative margin is overstated by roughly the return rate
    (3.25% of gross in June). Reported in margin_summary.json, not hidden. The
    calibrated months inherit this: forcing a ratio onto a denominator that is
    ~3% too big leaves the margin *percentage* tied to the statement and the
    absolute EGP profit overstated by that same ~3%.

    Items with no cost row are never charged zero cost. Their revenue is carried
    as an explicit "uncosted" line so a margin percentage is always stated
    against the revenue it actually covers.

Inputs   data/processed/sales_transactions.csv, dim_items.csv, dim_customers.csv
         data/cost/model_rows.json
         data/cost/income_statements.json   (optional; absent = no calibration)
Outputs  data/processed/margin_unit_costs.csv
         data/processed/margin_by_{item,customer,rep,brand,month}.csv
         data/processed/margin_by_{item,customer,rep}_month.csv
         data/processed/margin_summary.json
         data/processed/margin_dashboard.json  (compact payload for the mobile app)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import statements as S            # noqa: E402

S.set_caller("13_join_cost_margin")

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
COST_JSON = ROOT / "data" / "cost" / "model_rows.json"

COST_MONTH = "2026-06"          # the month the costing model measures
RECON_TOL = 1.0                 # EGP; the model reconciles to the cent
# Price gap vs the cost month beyond which an indicative margin stops being
# comparable and is reported as unreliable rather than quoted.
MAX_DRIFT_PCT = 10.0
# How far the cost month's calibration factors may sit from 1.0. They are 1.0
# by construction — the model is built against that statement — so this is a
# tie-break tolerance for float arithmetic, not a modelling allowance.
CAL_TOL = 0.005

# The income statement the costing model is built against (model/README.md).
STATEMENT = {"revenue_net": 3_741_772.00, "cogs": 2_039_933.08,
             "conversion": 544_605.00, "opex": 738_392.00, "net_profit": 418_841.92}


def month_key(s: pd.Series) -> pd.Series:
    """Invoice dates are stored as YYYY/M/D (unpadded). -> 'YYYY-MM'."""
    d = pd.to_datetime(s, format="mixed", dayfirst=False, errors="coerce")
    return d.dt.strftime("%Y-%m")


def clean(obj):
    """NaN/inf -> None, so the JSON is strict. Same helper as step 10."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


# ----------------------------------------------------------------- unit costs
def unit_costs(cost_rows: dict) -> pd.DataFrame:
    """Per-SKU unit costs implied by the June model.

    The model states totals; quantities match the June invoices exactly, so
    dividing gives a defensible cost per unit. Three levels are kept because
    they answer different questions:

        mat_unit    materials + packaging   -> gross profit (the statement's
                                               "تكلفة المبيعات")
        conv_unit   conversion overhead     -> factory cost
        opex_unit   allocated opex          -> operating profit
    """
    rows = []
    for code, r in cost_rows.items():
        q = r.get("qty") or 0
        if q <= 0:
            continue
        rows.append({
            "item_code": str(code).strip(),
            "cost_item_name": r.get("name"),
            "cost_brand": r.get("brand"),
            "june_qty": q,
            "mat_unit": r["act_mat_total"] / q,
            "conv_unit": r["conv_alloc"] / q,
            "opex_unit": r["opex_alloc"] / q,
            "full_unit": r["full_loaded_total"] / q,
            # The model books returns per SKU and nets them off revenue while
            # charging cost for the full quantity shipped — that is how its
            # figures tie to the income statement. The join has to do the same,
            # so the rate travels with the unit costs.
            "june_return_rate": ((r.get("returns") or 0.0) / r["gross_revenue"]
                                 if r.get("gross_revenue") else 0.0),
            "june_avg_price": r.get("avg_price"),
            "list_price": r.get("list_price"),
            "rec_price": r.get("rec_price"),
            "floor_price": r.get("floor_price"),
            "abc": r.get("abc"),
            "june_gross_margin": r.get("gross_margin"),
            "june_op_margin": r.get("op_margin"),
            "flags": r.get("flags"),
        })
    u = pd.DataFrame(rows)
    u["mat_unit"] = u["mat_unit"].round(6)
    return u


# ----------------------------------------------------------------- price drift
def price_index(tx: pd.DataFrame, u: pd.DataFrame) -> pd.DataFrame:
    """Fixed-basket price index per month, cost month = 100.

    Laspeyres with June quantities as the weights, so the index moves with
    price and not with mix. Only SKUs priced in both the month and the cost
    month contribute, which keeps a newly-listed item from looking like
    inflation.
    """
    costed = tx[tx["item_code"].isin(set(u["item_code"]))]
    per = (costed.groupby(["month", "item_code"])[["line_total", "qty"]].sum()
           .assign(p=lambda d: d["line_total"] / d["qty"].replace(0, np.nan))
           .reset_index())
    qj = u.set_index("item_code")["june_qty"]
    pj = per[per["month"] == COST_MONTH].set_index("item_code")["p"]

    rows = []
    for month, g in per.groupby("month"):
        s_ = g.set_index("item_code")["p"]
        common = [i for i in s_.index
                  if i in pj.index and i in qj.index
                  and pd.notna(s_[i]) and pd.notna(pj[i])]
        den = sum(pj[i] * qj[i] for i in common)
        idx = (sum(s_[i] * qj[i] for i in common) / den * 100) if den else np.nan
        rows.append({"month": month, "price_index": idx,
                     "cost_period_drift_pct": idx - 100 if pd.notna(idx) else None,
                     "n_skus_in_basket": len(common),
                     "indicative_reliable": bool(pd.notna(idx)
                                                 and abs(idx - 100) <= MAX_DRIFT_PCT)})
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- reconcile
def reconcile(cost_rows: dict, tx: pd.DataFrame) -> dict:
    """Hard checks. A failure here means the two repositories have drifted."""
    m = pd.DataFrame(cost_rows).T
    tot = {k: float(pd.to_numeric(m[k]).sum()) for k in
           ["revenue", "gross_revenue", "returns", "act_mat_total",
            "conv_alloc", "opex_alloc", "full_loaded_total", "qty"]}

    june = tx[tx["month"] == COST_MONTH]
    codes = {str(c).strip() for c in cost_rows}
    jc = june[june["item_code"].isin(codes)]

    # Per-SKU, not just the total. Two items with swapped quantities sum to the
    # same grand total and would sail through an aggregate check, while every
    # cost in build() is computed from the individual quantity — so the totals
    # would agree and the margins would still be wrong.
    model_qty = {str(c).strip(): float(r.get("qty") or 0.0)
                 for c, r in cost_rows.items() if (r.get("qty") or 0) > 0}
    inv_qty = jc.groupby("item_code")["qty"].sum().to_dict()
    qty_mismatches = sorted(
        code for code in set(model_qty) | set(inv_qty)
        if abs(model_qty.get(code, 0.0) - float(inv_qty.get(code, 0.0)))
        >= RECON_TOL)

    checks = {
        "model_net_profit_ties_to_statement": abs(
            tot["revenue"] - tot["act_mat_total"] - tot["conv_alloc"]
            - tot["opex_alloc"] - STATEMENT["net_profit"]) < RECON_TOL,
        "model_revenue_ties_to_statement": abs(
            tot["revenue"] - STATEMENT["revenue_net"]) < RECON_TOL,
        "june_qty_matches_invoices": abs(
            tot["qty"] - float(jc["qty"].sum())) < RECON_TOL,
        "june_qty_matches_invoices_per_item": not qty_mismatches,
        "june_gross_revenue_matches_invoices": abs(
            tot["gross_revenue"] - float(jc["line_total"].sum())) < RECON_TOL,
    }
    return {
        "checks": checks,
        "qty_mismatched_items": qty_mismatches,
        "all_passed": all(checks.values()),
        "model_totals": tot,
        "june_invoice_qty": float(jc["qty"].sum()),
        "june_invoice_gross_revenue": float(jc["line_total"].sum()),
        "june_return_rate_pct": (tot["returns"] / tot["gross_revenue"] * 100
                                 if tot["gross_revenue"] else None),
    }


# ------------------------------------------------------------------ the join
def build(tx: pd.DataFrame, u: pd.DataFrame, pidx: pd.DataFrame) -> pd.DataFrame:
    j = tx.merge(u, on="item_code", how="left").merge(pidx, on="month", how="left")
    j["is_costed"] = j["mat_unit"].notna()
    for col, unit in [("cogs", "mat_unit"), ("conv_cost", "conv_unit"),
                      ("opex_cost", "opex_unit"), ("full_cost", "full_unit")]:
        # NaN, not 0, where there is no cost row: an uncosted item must never
        # look like a free one.
        j[col] = j["qty"] * j[unit]
    j["basis"] = np.where(j["month"] == COST_MONTH, "measured", "indicative")

    # REVENUE BASIS — the measured month is net of returns, the rest is not.
    #
    # The costing model nets each SKU's returns off its revenue but charges
    # cost for the whole quantity shipped; that is precisely how it reconciles
    # to the June income statement (net sales 3,741,772.00, net profit
    # 418,841.92). Charging that same cost against GROSS invoice revenue
    # overstated June by exactly the returns — 125,718.79 on both revenue and
    # profit — and put 47.25%/14.08% in front of a reader whose own income
    # statement says 45.48%/11.19%.
    #
    # Outside June there is no per-SKU return detail, so those months stay on
    # gross revenue and remain overstated by roughly the return rate. That was
    # already true, is reported in margin_summary.json, and is one more reason
    # the indicative basis is not quotable.
    j["net_revenue"] = np.where(
        j["basis"] == "measured",
        j["line_total"] * (1 - j["june_return_rate"].fillna(0.0)),
        j["line_total"])
    j["gross_profit"] = j["net_revenue"] - j["cogs"]
    j["op_profit"] = j["net_revenue"] - j["full_cost"]
    # The cost month is measured, so the gate only governs the other months.
    j["reliable"] = (j["basis"] == "measured") | j["indicative_reliable"].fillna(False)
    return j


# ------------------------------------------------------------- calibration --
def calibrate(j: pd.DataFrame, ratios: dict | None) -> dict:
    """Scale June unit costs per month onto that month's income statement.

    Mutates j with cal_cogs / cal_full_cost / cal_gross_profit / cal_op_profit
    and a `calibrated` flag, and returns the per-month metadata describing what
    was done. Passing ratios=None (no vendored statements) leaves every row
    uncalibrated, so a checkout without the extract keeps the earlier behaviour
    instead of failing.

    Factors are computed over COSTED lines only, because that is the population
    the margin percentages are stated against everywhere else in this file.
    """
    j["calibrated"] = False
    for c in ("k_cogs", "k_opex", "cal_cogs", "cal_full_cost",
              "cal_gross_profit", "cal_op_profit"):
        j[c] = np.nan
    meta: dict[str, dict] = {}
    if not ratios:
        return meta

    costed = j[j["is_costed"]]
    for month, g in costed.groupby("month"):
        r = ratios.get(month)
        if r is None:
            continue                        # no statement for this month
        rev = float(g["net_revenue"].sum())
        cogs = float(g["cogs"].sum())
        conv = float((g["conv_cost"] + g["opex_cost"]).sum())
        if rev <= 0 or cogs <= 0 or conv <= 0:
            continue
        k_cogs = r["cogs"] * rev / cogs
        k_opex = r["opex"] * rev / conv

        if month == COST_MONTH:
            # The costing model IS this statement. Factors away from 1.0 mean
            # the join has stopped reproducing it, and every calibrated month
            # downstream would inherit the same error silently.
            for name, k in (("cost", k_cogs), ("expense", k_opex)):
                if abs(k - 1.0) > CAL_TOL:
                    raise SystemExit(
                        f"\n{COST_MONTH} {name} calibration factor is {k:.6f}, "
                        f"not 1.0 — the join no longer reproduces the income "
                        f"statement it is built on; refusing to calibrate")
            k_cogs = k_opex = 1.0           # keep the measured month untouched

        m = j["month"] == month
        j.loc[m, "k_cogs"] = k_cogs
        j.loc[m, "k_opex"] = k_opex
        j.loc[m & j["is_costed"], "calibrated"] = True
        meta[month] = {
            "k_cogs": k_cogs, "k_opex": k_opex,
            "basis": "measured" if month == COST_MONTH else "calibrated",
            "estimated": bool(r["estimated"]),
            "statement_basis": r["basis"],
            "statement_cogs_ratio": r["cogs"] * 100,
        }

    j["cal_cogs"] = j["cogs"] * j["k_cogs"]
    j["cal_full_cost"] = (j["cal_cogs"]
                          + (j["conv_cost"] + j["opex_cost"]) * j["k_opex"])
    j["cal_gross_profit"] = j["net_revenue"] - j["cal_cogs"]
    j["cal_op_profit"] = j["net_revenue"] - j["cal_full_cost"]
    return meta


def agg_monthly(j: pd.DataFrame, keys: list[str], meta: dict) -> pd.DataFrame:
    """One dimension by month, on the calibrated basis.

    Only calibrated months appear. A month with no statement is absent from the
    file rather than present with an unreliable figure, because the whole point
    of these three files is that every row in them ties to a statement.
    """
    src = j[j["is_costed"] & j["calibrated"]]
    if src.empty:
        return pd.DataFrame()
    g = (src.groupby(["month"] + keys, dropna=False).agg(
            revenue=("net_revenue", "sum"), qty=("qty", "sum"),
            cogs=("cal_cogs", "sum"), full_cost=("cal_full_cost", "sum"),
            gross_profit=("cal_gross_profit", "sum"),
            op_profit=("cal_op_profit", "sum"), n_lines=("qty", "size"))
         .reset_index())
    g["gross_margin_pct"] = g["gross_profit"] / g["revenue"] * 100
    g["op_margin_pct"] = g["op_profit"] / g["revenue"] * 100
    g["basis"] = g["month"].map(lambda m: meta[m]["basis"])
    g["estimated"] = g["month"].map(lambda m: meta[m]["estimated"])
    return g.sort_values(["month", "revenue"], ascending=[True, False])


def verify_calibration(j: pd.DataFrame, meta: dict) -> None:
    """Abort unless every calibrated month actually reproduces its statement.

    Two independent things are asserted, because they fail differently:

      * the ratio. If the arithmetic is right this holds to machine precision;
        anything looser means a month was scaled by the wrong factor.
      * dimension parity. Item, customer and representative are three cuts of
        the same lines, so their monthly profit must agree. A join that
        duplicated or dropped rows on one dimension would still produce a
        plausible-looking file, and this is what catches it.
    """
    if not meta:
        return
    src = j[j["is_costed"] & j["calibrated"]]
    for month, g in src.groupby("month"):
        want = meta[month]["statement_cogs_ratio"] / 100.0
        got = float(g["cal_cogs"].sum()) / float(g["net_revenue"].sum())
        if abs(got - want) > 1e-9:
            raise SystemExit(
                f"\n{month}: calibrated cost ratio is {got:.9f} but the income "
                f"statement says {want:.9f} — refusing to emit monthly margin")

    cuts = [agg_monthly(j, k, meta)
            for k in (["item_code"], ["customer_code"], ["rep"])]
    ref = cuts[0].groupby("month")["gross_profit"].sum().round(2)
    for c in cuts[1:]:
        other = c.groupby("month")["gross_profit"].sum().round(2)
        if not ref.equals(other):
            bad = sorted(set(ref.index) ^ set(other.index)) or [
                m for m in ref.index if ref[m] != other.get(m)]
            raise SystemExit(
                f"\nmonthly gross profit disagrees between dimensions at "
                f"{bad[:5]} — the three cuts are not the same lines")
    print(f"  PASS  calibrated_months_reproduce_their_statements "
          f"({len(meta)} month(s))")


def agg(j: pd.DataFrame, keys: list[str], reliable_only: bool = True) -> pd.DataFrame:
    """Aggregate, keeping costed and uncosted revenue apart throughout.

    reliable_only drops months that fail the price-drift gate, so a per-customer
    or per-item margin is never a blend of comparable and non-comparable months.
    The per-month file passes False: it reports every month with its own flag.
    """
    src = j[j["reliable"]] if reliable_only else j
    c = src[src["is_costed"]]
    g = c.groupby(keys, dropna=False).agg(
        # net_revenue, not line_total: a margin percentage whose denominator
        # is gross while its numerator is net is wrong in both directions.
        revenue_costed=("net_revenue", "sum"), qty=("qty", "sum"),
        cogs=("cogs", "sum"), conv_cost=("conv_cost", "sum"),
        opex_cost=("opex_cost", "sum"), full_cost=("full_cost", "sum"),
        gross_profit=("gross_profit", "sum"), op_profit=("op_profit", "sum"),
        n_lines=("qty", "size"))
    # Same basis as revenue_costed, so revenue_uncosted stays exactly the
    # revenue with no cost row rather than absorbing a returns difference.
    allr = src.groupby(keys, dropna=False).agg(revenue_total=("net_revenue", "sum"))
    out = g.join(allr, how="outer").reset_index()
    out["revenue_uncosted"] = (out["revenue_total"] - out["revenue_costed"]).round(2)
    # Margins are stated against COSTED revenue only — the denominator the
    # numerator actually came from.
    out["gross_margin_pct"] = out["gross_profit"] / out["revenue_costed"] * 100
    out["op_margin_pct"] = out["op_profit"] / out["revenue_costed"] * 100
    out["cost_coverage_pct"] = out["revenue_costed"] / out["revenue_total"] * 100
    return out.sort_values("revenue_total", ascending=False)


def level3(monthly: dict, cal: dict, rows) -> dict:
    """The calibrated monthly cuts, as payload keys — or nothing at all.

    An empty dict rather than empty lists when there is no calibration, so the
    app tests for the key instead of for length and a pre-calibration build
    keeps the payload it had.
    """
    if not cal:
        return {}
    common = ["month", "basis", "estimated"]
    tail = ["revenue", "gross_profit", "op_profit",
            "gross_margin_pct", "op_margin_pct"]
    return {
        "calibration": {
            "months": sorted(cal),
            "cost_month": COST_MONTH,
            "n_estimated_months": sum(1 for v in cal.values() if v["estimated"]),
            "estimated_months": sorted(m for m, v in cal.items()
                                       if v["estimated"]),
            "by_month": [dict(cal[m], month=m) for m in sorted(cal)],
            "method": "June-2026 unit costs scaled per month so the total cost "
                      "and expense ratios equal that month's income statement. "
                      "Corrects the level, not the mix.",
        },
        "by_item_month": rows(
            monthly["margin_by_item_month.csv"],
            common + ["item_code", "item_name", "brand", "qty"] + tail),
        "by_customer_month": rows(
            monthly["margin_by_customer_month.csv"],
            common + ["customer_code", "customer_name", "rep"] + tail),
        "by_rep_month": rows(
            monthly["margin_by_rep_month.csv"], common + ["rep"] + tail),
    }


def dashboard_payload(summary: dict, outs: dict, u: pd.DataFrame,
                      monthly: dict, cal: dict) -> dict:
    """Compact payload the mobile app inlines as window.DASH_MARGIN.

    Deliberately separate from dashboards/data.js: that file is the desktop
    dashboard's data contract and nothing here should perturb it.
    """
    def rows(df, cols, n=None):
        d = df if n is None else df.head(n)
        return clean(d[cols].round(4).to_dict("records"))

    # Items priced below what the costing model recommends, worst gap first.
    pricing = u.dropna(subset=["rec_price", "june_avg_price"]).copy()
    pricing["gap_pct"] = ((pricing["rec_price"] - pricing["june_avg_price"])
                          / pricing["june_avg_price"] * 100)
    pricing = pricing[pricing["gap_pct"] > 0].sort_values("gap_pct", ascending=False)

    return {
        "meta": {
            "cost_month": summary["cost_month"],
            "coverage_pct": summary["coverage"]["coverage_pct"],
            "revenue_uncosted": summary["coverage"]["revenue_uncosted"],
            "n_items_costed": summary["coverage"]["n_items_costed"],
            "n_items_total": summary["coverage"]["n_items_total"],
            "reliable_months": summary["price_drift"]["reliable_months"],
            "excluded_months": summary["price_drift"]["excluded_months"],
            "max_drift_pct": MAX_DRIFT_PCT,
            "source": summary["cost_source"],
        },
        "totals": {"measured": summary["measured"],
                   "indicative": summary["indicative"],
                   "excluded": summary["indicative_excluded"]},
        "by_month": rows(outs["margin_by_month.csv"],
                         ["month", "basis", "revenue_costed", "gross_profit", "op_profit",
                          "gross_margin_pct", "op_margin_pct", "price_index",
                          "cost_period_drift_pct", "indicative_reliable"]),
        "by_brand": rows(outs["margin_by_brand.csv"],
                         ["brand", "revenue_total", "revenue_costed", "gross_profit",
                          "op_profit", "gross_margin_pct", "op_margin_pct",
                          "cost_coverage_pct"]),
        "by_rep": rows(outs["margin_by_rep.csv"],
                       ["rep", "revenue_total", "revenue_costed", "gross_profit",
                        "op_profit", "gross_margin_pct", "op_margin_pct",
                        "cost_coverage_pct"]),
        "by_item": rows(outs["margin_by_item.csv"],
                        ["item_code", "item_name", "brand", "revenue_costed", "qty",
                         "gross_profit", "op_profit", "gross_margin_pct", "op_margin_pct"]),
        "by_customer": rows(outs["margin_by_customer.csv"],
                            ["customer_code", "customer_name", "rep", "revenue_total",
                             "revenue_costed", "gross_profit", "op_profit",
                             "gross_margin_pct", "op_margin_pct"], n=60),
        # Level three: monthly, per dimension, on the calibrated basis. Absent
        # entirely — not present and empty — when there are no statements, so
        # the app can decide whether the level exists by asking for the key.
        **level3(monthly, cal, rows),
        "uncosted_items": summary["coverage"]["uncosted_items_top"],
        "pricing_gap": clean(pricing[["item_code", "cost_item_name", "cost_brand",
                                      "june_avg_price", "rec_price", "floor_price",
                                      "gap_pct", "abc", "flags"]]
                             .round(4).to_dict("records")),
        "caveats": summary["caveats"],
    }


def main() -> None:
    tx = pd.read_csv(P / "sales_transactions.csv",
                     dtype={"customer_code": str, "item_code": str})
    tx["item_code"] = tx["item_code"].str.strip()
    tx["customer_code"] = tx["customer_code"].str.strip()
    tx["month"] = month_key(tx["invoice_date"])
    for c in ("qty", "line_total"):
        tx[c] = pd.to_numeric(tx[c], errors="coerce").fillna(0.0)

    items = pd.read_csv(P / "dim_items.csv", dtype={"item_code": str})
    items["item_code"] = items["item_code"].str.strip()
    custs = pd.read_csv(P / "dim_customers.csv", dtype={"customer_code": str})
    custs["customer_code"] = custs["customer_code"].str.strip()

    tx = tx.merge(items[["item_code", "item_name", "brand"]], on="item_code", how="left")
    tx = tx.merge(custs[["customer_code", "customer_name", "rep"]],
                  on="customer_code", how="left")
    tx["brand"] = tx["brand"].fillna("غير مصنف")
    tx["rep"] = tx["rep"].fillna("غير محدد")

    cost_rows = json.loads(COST_JSON.read_text(encoding="utf-8"))
    u = unit_costs(cost_rows)
    pidx = price_index(tx, u)
    rec = reconcile(cost_rows, tx)

    print("reconciliation")
    for k, v in rec["checks"].items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    if not rec["all_passed"]:
        raise SystemExit("\ncost model no longer ties to the invoices or the "
                         "income statement — refusing to emit margin figures")

    j = build(tx, u, pidx)

    # The join's own measured month must reproduce the income statement. The
    # four checks above only prove the model ties to the invoices; they say
    # nothing about what build() then does with the revenue. Charging June cost
    # against gross invoice revenue passed every one of them while reporting a
    # 14.08% operating margin for a month whose statement says 11.19%. This is
    # the check that catches that class of error.
    meas = j[j["basis"] == "measured"]
    for label, got, want in (
            ("measured revenue", float(meas["net_revenue"].sum()),
             STATEMENT["revenue_net"]),
            ("measured operating profit", float(meas["op_profit"].sum()),
             STATEMENT["net_profit"])):
        if abs(got - want) >= RECON_TOL:
            raise SystemExit(
                f"\n{label} is {got:,.2f} but the {COST_MONTH} income "
                f"statement says {want:,.2f} — refusing to emit margin figures")
    print("  PASS  measured_month_reproduces_the_income_statement")

    # The third basis. S.ratios() returns None when the vendored statements are
    # absent, and everything below then behaves exactly as it did before them.
    cal = calibrate(j, S.ratios())
    verify_calibration(j, cal)

    by_month = (agg(j, ["month", "basis"], reliable_only=False)
                .merge(pidx, on="month", how="left").sort_values("month"))

    u.to_csv(P / "margin_unit_costs.csv", index=False)
    outs = {
        "margin_by_item.csv": agg(j, ["item_code", "item_name", "brand"]),
        "margin_by_customer.csv": agg(j, ["customer_code", "customer_name", "rep"]),
        "margin_by_rep.csv": agg(j, ["rep"]),
        "margin_by_brand.csv": agg(j, ["brand"]),
        "margin_by_month.csv": by_month,
    }
    monthly = {
        "margin_by_item_month.csv":
            agg_monthly(j, ["item_code", "item_name", "brand"], cal),
        "margin_by_customer_month.csv":
            agg_monthly(j, ["customer_code", "customer_name", "rep"], cal),
        "margin_by_rep_month.csv": agg_monthly(j, ["rep"], cal),
    }
    for name, df in list(outs.items()) + list(monthly.items()):
        if len(df):
            df.round(4).to_csv(P / name, index=False)

    costed = j[j["is_costed"]]
    measured = costed[costed["basis"] == "measured"]
    indicative = costed[(costed["basis"] == "indicative") & costed["reliable"]]
    excluded = costed[(costed["basis"] == "indicative") & ~costed["reliable"]]
    uncosted_items = (j[~j["is_costed"]].groupby(["item_code", "item_name"])
                      ["line_total"].sum().sort_values(ascending=False))

    def block(d: pd.DataFrame) -> dict:
        # net_revenue, matching agg(): the measured month is net of returns and
        # its margin percentages have to be taken against that same figure.
        rev = float(d["net_revenue"].sum())
        return {"revenue_costed": rev, "qty": float(d["qty"].sum()),
                "cogs": float(d["cogs"].sum()),
                "gross_profit": float(d["gross_profit"].sum()),
                "op_profit": float(d["op_profit"].sum()),
                "gross_margin_pct": float(d["gross_profit"].sum()) / rev * 100 if rev else None,
                "op_margin_pct": float(d["op_profit"].sum()) / rev * 100 if rev else None,
                "months": sorted(d["month"].dropna().unique().tolist())}

    summary = {
        "cost_month": COST_MONTH,
        "cost_source": {"repo": "hannopo1/Abohashem", "path": "model/model_rows.json",
                        "see": "data/cost/PROVENANCE.md"},
        "reconciliation": rec,
        "coverage": {
            "n_items_costed": int(u.shape[0]),
            "n_items_total": int(tx["item_code"].nunique()),
            "revenue_total": float(tx["line_total"].sum()),
            "revenue_costed": float(costed["line_total"].sum()),
            "revenue_uncosted": float(j[~j["is_costed"]]["line_total"].sum()),
            "coverage_pct": float(costed["line_total"].sum()) / float(tx["line_total"].sum()) * 100,
            "uncosted_items_top": [
                {"item_code": c, "item_name": n, "revenue": float(v)}
                for (c, n), v in uncosted_items.head(15).items()],
        },
        "price_drift": {
            "max_drift_pct": MAX_DRIFT_PCT,
            "basis": "Laspeyres, June-2026 quantities as fixed weights, cost month = 100",
            "by_month": clean(pidx.sort_values("month").to_dict("records")),
            "reliable_months": sorted(pidx[pidx["indicative_reliable"]]["month"].tolist()),
            "excluded_months": sorted(pidx[~pidx["indicative_reliable"]]["month"].tolist()),
        },
        "measured": block(measured),
        "indicative": block(indicative),
        "indicative_excluded": (block(excluded) if len(excluded) else None),
        "calibration": ({
            "months": sorted(cal),
            "n_months": len(cal),
            "estimated_months": sorted(m for m, v in cal.items() if v["estimated"]),
            "by_month": [dict(cal[m], month=m) for m in sorted(cal)],
            "basis": "June-2026 unit costs scaled per month onto that month's "
                     "income-statement cost and expense ratios",
        } if cal else None),
        "caveats": [
            "المقيس: يونيو 2026 فقط — تكلفة مرصودة، مطابقة لقائمة الدخل.",
            f"بوابة انحراف الأسعار: تُستبعد الشهور التي تبعد أسعارها عن شهر التكلفة "
            f"بأكثر من {MAX_DRIFT_PCT:.0f}%. الأسعار كانت أدنى من يونيو 2026 بنحو 15% "
            "حتى فبراير 2026 ثم ارتفعت في مارس–أبريل 2026؛ احتساب تكلفة يونيو على "
            "أسعار ما قبل الزيادة يُظهر هامشًا تشغيليًا سالبًا طوال 2025 وهو أثر "
            "منهجي لا واقعة تاريخية. لذلك لا يمتد الهامش الموثوق قبل مارس 2026.",
            "التقديري: تكلفة وحدة يونيو 2026 مطبَّقة على كميات شهور أخرى. تقدير لا قياس.",
            "إيراد الشهور غير يونيو إجمالي (قبل المرتجعات)؛ لا توجد مرتجعات لكل صنف "
            f"خارج يونيو. نسبة المرتجعات في يونيو {rec['june_return_rate_pct']:.2f}% "
            "من الإجمالي، ولذلك الهامش التقديري أعلى من الواقع بهذا القدر تقريبًا.",
            "الأصناف بلا تكلفة لا تُحتسب لها تكلفة صفرية؛ إيرادها يُعرض منفصلًا "
            "وكل نسبة هامش محسوبة على الإيراد المُسعَّر فقط.",
        ] + ([
            f"المعايَر: {len(cal)} شهرًا ({min(cal)} – {max(cal)}). تكلفة وحدة "
            "يونيو 2026 مضروبة في معامل شهري يجعل نسبتَي التكلفة والمصروفات "
            "مطابقتين لقائمة دخل الشهر نفسه. المعايرة تصحّح مستوى التكلفة لا "
            "توزيعها بين الأصناف: إن تحرّكت تكلفة صنف بعينه عكس بقية السلة بين "
            "يونيو وذلك الشهر فلا شيء هنا يرصده. فهي ليست ربحية مقيسة لكل صنف.",
            "الأشهر المعايَرة ترث إجمالية الإيراد (قبل المرتجعات): النسبة "
            "المئوية مطابقة للقائمة، أما الربح بالجنيه فأعلى من الواقع بنحو "
            "نسبة المرتجعات نفسها.",
        ] if cal else []),
    }
    (P / "margin_summary.json").write_text(
        json.dumps(clean(summary), ensure_ascii=False, indent=2), encoding="utf-8")

    (P / "margin_dashboard.json").write_text(
        json.dumps(clean(dashboard_payload(summary, outs, u, monthly, cal)),
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    cov = summary["coverage"]
    print(f"\ncoverage  {cov['n_items_costed']}/{cov['n_items_total']} items · "
          f"{cov['coverage_pct']:.1f}% of {cov['revenue_total']:,.0f} EGP revenue")
    d = summary["price_drift"]
    print(f"price gate  {len(d['reliable_months'])} month(s) within "
          f"{MAX_DRIFT_PCT:.0f}% of the cost month; "
          f"{len(d['excluded_months'])} excluded as not comparable")
    for label, b in (("measured   (cost month)", summary["measured"]),
                     ("indicative (reliable)", summary["indicative"]),
                     ("excluded   (not comparable)", summary["indicative_excluded"])):
        if not b:
            continue
        print(f"  {label:28s} revenue {b['revenue_costed']:>13,.0f}  "
              f"gross {b['gross_margin_pct']:>6.2f}%  operating {b['op_margin_pct']:>7.2f}%")
    if cal:
        est = sorted(m for m, v in cal.items() if v["estimated"])
        print(f"calibration  {len(cal)} month(s) {min(cal)}..{max(cal)} scaled "
              f"onto their income statements; {len(est)} of them estimated "
              f"({', '.join(est) or 'none'})")
        rowsn = {k: len(v) for k, v in monthly.items()}
        print(f"             rows {rowsn}")
    else:
        print("calibration  skipped — data/cost/income_statements.json absent")
    print(f"\nwrote margin_unit_costs.csv + {len(outs)} aggregates + "
          f"{len(monthly)} monthly cuts + margin_summary.json + "
          "margin_dashboard.json")


if __name__ == "__main__":
    main()
