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

WHAT IS NOT DONE
    Revenue outside June is gross: the repository holds no per-SKU returns for
    other months, so indicative margin is overstated by roughly the return rate
    (3.25% of gross in June). Reported in margin_summary.json, not hidden.

    Items with no cost row are never charged zero cost. Their revenue is carried
    as an explicit "uncosted" line so a margin percentage is always stated
    against the revenue it actually covers.

Inputs   data/processed/sales_transactions.csv, dim_items.csv, dim_customers.csv
         data/cost/model_rows.json
Outputs  data/processed/margin_unit_costs.csv
         data/processed/margin_by_{item,customer,rep,brand,month}.csv
         data/processed/margin_summary.json
         data/processed/margin_dashboard.json  (compact payload for the mobile app)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
COST_JSON = ROOT / "data" / "cost" / "model_rows.json"

COST_MONTH = "2026-06"          # the month the costing model measures
RECON_TOL = 1.0                 # EGP; the model reconciles to the cent
# Price gap vs the cost month beyond which an indicative margin stops being
# comparable and is reported as unreliable rather than quoted.
MAX_DRIFT_PCT = 10.0

# The income statement the costing model is built against (model/README.md).
STATEMENT = {"revenue_net": 3_741_772.00, "cogs": 2_039_933.08,
             "conversion": 544_605.00, "opex": 738_392.00, "net_profit": 418_841.92}


def month_key(s: pd.Series) -> pd.Series:
    """
    Convert date values to year-month keys in ``YYYY-MM`` format.
    
    Parameters:
        s (pd.Series): Date values to convert.
    
    Returns:
        pd.Series: Formatted year-month values, with invalid or missing dates represented as missing values.
    """
    d = pd.to_datetime(s, format="mixed", dayfirst=False, errors="coerce")
    return d.dt.strftime("%Y-%m")


def clean(obj):
    """
    Convert nested data to JSON-compatible values.
    
    Replaces NaN and infinite floating-point values with `None` and converts NumPy numeric values to native Python types.
    
    Parameters:
    	obj: A value that may contain nested dictionaries, lists, or NumPy values.
    
    Returns:
    	The converted value with JSON-compatible numeric types and null values.
    """
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
    """
    Build per-SKU unit costs from June cost-model totals and quantities.
    
    Parameters:
        cost_rows (dict): Mapping of SKU codes to cost-model totals and metadata.
    
    Returns:
        pandas.DataFrame: Per-SKU material, conversion, operating-expense, and fully loaded unit costs, along with pricing, classification, and margin metadata. SKUs with non-positive quantities are omitted.
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
    """
    Reconcile costing-model totals with the income statement and June invoice data.
    
    Parameters:
        cost_rows (dict): Costing-model records keyed by item code.
        tx (pd.DataFrame): Sales transactions containing month, item code, quantity,
            and line-total fields.
    
    Returns:
        dict: Reconciliation checks, pass status, model totals, June invoice totals,
            and the June return rate percentage.
    """
    m = pd.DataFrame(cost_rows).T
    tot = {k: float(pd.to_numeric(m[k]).sum()) for k in
           ["revenue", "gross_revenue", "returns", "act_mat_total",
            "conv_alloc", "opex_alloc", "full_loaded_total", "qty"]}

    june = tx[tx["month"] == COST_MONTH]
    codes = {str(c).strip() for c in cost_rows}
    jc = june[june["item_code"].isin(codes)]

    checks = {
        "model_net_profit_ties_to_statement": abs(
            tot["revenue"] - tot["act_mat_total"] - tot["conv_alloc"]
            - tot["opex_alloc"] - STATEMENT["net_profit"]) < RECON_TOL,
        "model_revenue_ties_to_statement": abs(
            tot["revenue"] - STATEMENT["revenue_net"]) < RECON_TOL,
        "june_qty_matches_invoices": abs(
            tot["qty"] - float(jc["qty"].sum())) < RECON_TOL,
        "june_gross_revenue_matches_invoices": abs(
            tot["gross_revenue"] - float(jc["line_total"].sum())) < RECON_TOL,
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "model_totals": tot,
        "june_invoice_qty": float(jc["qty"].sum()),
        "june_invoice_gross_revenue": float(jc["line_total"].sum()),
        "june_return_rate_pct": (tot["returns"] / tot["gross_revenue"] * 100
                                 if tot["gross_revenue"] else None),
    }


# ------------------------------------------------------------------ the join
def build(tx: pd.DataFrame, u: pd.DataFrame, pidx: pd.DataFrame) -> pd.DataFrame:
    """
    Join transactions with unit costs and monthly price reliability data, then calculate transaction-level profitability fields.
    
    Parameters:
    	tx (pd.DataFrame): Sales transactions to enrich.
    	u (pd.DataFrame): Per-item unit-cost data keyed by `item_code`.
    	pidx (pd.DataFrame): Monthly price-index reliability data keyed by `month`.
    
    Returns:
    	pd.DataFrame: Enriched transactions with cost, profit, costing-status, measurement-basis, and reliability fields. Missing costs remain null.
    """
    j = tx.merge(u, on="item_code", how="left").merge(pidx, on="month", how="left")
    j["is_costed"] = j["mat_unit"].notna()
    for col, unit in [("cogs", "mat_unit"), ("conv_cost", "conv_unit"),
                      ("opex_cost", "opex_unit"), ("full_cost", "full_unit")]:
        # NaN, not 0, where there is no cost row: an uncosted item must never
        # look like a free one.
        j[col] = j["qty"] * j[unit]
    j["gross_profit"] = j["line_total"] - j["cogs"]
    j["op_profit"] = j["line_total"] - j["full_cost"]
    j["basis"] = np.where(j["month"] == COST_MONTH, "measured", "indicative")
    # The cost month is measured, so the gate only governs the other months.
    j["reliable"] = (j["basis"] == "measured") | j["indicative_reliable"].fillna(False)
    return j


def agg(j: pd.DataFrame, keys: list[str], reliable_only: bool = True) -> pd.DataFrame:
    """
    Aggregate profitability metrics by the specified dimensions while keeping costed and uncosted revenue separate.
    
    Parameters:
        j (pd.DataFrame): Transaction-level profitability data.
        keys (list[str]): Columns used to group the results.
        reliable_only (bool): Whether to include only rows marked as reliable.
    
    Returns:
        pd.DataFrame: Aggregated revenue, quantities, costs, profits, margins, and cost-coverage metrics, sorted by total revenue descending.
    """
    src = j[j["reliable"]] if reliable_only else j
    c = src[src["is_costed"]]
    g = c.groupby(keys, dropna=False).agg(
        revenue_costed=("line_total", "sum"), qty=("qty", "sum"),
        cogs=("cogs", "sum"), conv_cost=("conv_cost", "sum"),
        opex_cost=("opex_cost", "sum"), full_cost=("full_cost", "sum"),
        gross_profit=("gross_profit", "sum"), op_profit=("op_profit", "sum"),
        n_lines=("qty", "size"))
    allr = src.groupby(keys, dropna=False).agg(revenue_total=("line_total", "sum"))
    out = g.join(allr, how="outer").reset_index()
    out["revenue_uncosted"] = (out["revenue_total"] - out["revenue_costed"]).round(2)
    # Margins are stated against COSTED revenue only — the denominator the
    # numerator actually came from.
    out["gross_margin_pct"] = out["gross_profit"] / out["revenue_costed"] * 100
    out["op_margin_pct"] = out["op_profit"] / out["revenue_costed"] * 100
    out["cost_coverage_pct"] = out["revenue_costed"] / out["revenue_total"] * 100
    return out.sort_values("revenue_total", ascending=False)


def dashboard_payload(summary: dict, outs: dict, u: pd.DataFrame) -> dict:
    """
    Create a compact mobile-dashboard payload with profitability, coverage, pricing-gap, and caveat data.
    
    Parameters:
    	summary (dict): Reconciliation, coverage, price-drift, and profitability summary data.
    	outs (dict): Aggregate output tables keyed by their output filenames.
    	u (pd.DataFrame): Per-item unit-cost and pricing data.
    
    Returns:
    	dict: JSON-compatible dashboard payload containing metadata, totals, dimensional aggregates, uncosted items, pricing gaps, and caveats.
    """
    def rows(df, cols, n=None):
        """Convert selected dataframe columns into cleaned record dictionaries.
        
        Parameters:
            df (pandas.DataFrame): Source dataframe.
            cols (list): Columns to include in each record.
            n (int, optional): Maximum number of leading rows to include.
        
        Returns:
            list: Cleaned records with numeric values rounded to four decimal places.
        """
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
        "uncosted_items": summary["coverage"]["uncosted_items_top"],
        "pricing_gap": clean(pricing[["item_code", "cost_item_name", "cost_brand",
                                      "june_avg_price", "rec_price", "floor_price",
                                      "gap_pct", "abc", "flags"]]
                             .round(4).to_dict("records")),
        "caveats": summary["caveats"],
    }


def main() -> None:
    """
    Load source data, validate cost reconciliation, and generate profitability outputs and dashboard files.
    
    Raises:
    	SystemExit: If the costing model does not reconcile with the sales invoices or income statement.
    """
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
    for name, df in outs.items():
        df.round(4).to_csv(P / name, index=False)

    costed = j[j["is_costed"]]
    measured = costed[costed["basis"] == "measured"]
    indicative = costed[(costed["basis"] == "indicative") & costed["reliable"]]
    excluded = costed[(costed["basis"] == "indicative") & ~costed["reliable"]]
    uncosted_items = (j[~j["is_costed"]].groupby(["item_code", "item_name"])
                      ["line_total"].sum().sort_values(ascending=False))

    def block(d: pd.DataFrame) -> dict:
        """
        Summarize revenue, quantity, costs, profits, margins, and covered months for a transaction subset.
        
        Parameters:
        	d (pd.DataFrame): Transaction rows containing line totals, quantities, costs, profits, and month values.
        
        Returns:
        	dict: Aggregated financial metrics, margin percentages, and sorted months represented in the subset.
        """
        rev = float(d["line_total"].sum())
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
        ],
    }
    (P / "margin_summary.json").write_text(
        json.dumps(clean(summary), ensure_ascii=False, indent=2), encoding="utf-8")

    (P / "margin_dashboard.json").write_text(
        json.dumps(clean(dashboard_payload(summary, outs, u)),
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
    print(f"\nwrote margin_unit_costs.csv + {len(outs)} aggregates + "
          "margin_summary.json + margin_dashboard.json")


if __name__ == "__main__":
    main()
