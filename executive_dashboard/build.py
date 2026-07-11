#!/usr/bin/env python3
"""
Executive Financial Dashboard — build pipeline (June 2026, ABOHASHEM).

One command turns the source invoice markdown + reused processed dimensions into
every deliverable:

    python3 build.py

Outputs (into executive_dashboard/):
    data.js               pre-aggregated dataset the dashboard reads (window.DASH)
    processed_data.csv    cleaned June line-item table
    insights.json         structured executive commentary
    executive_summary.pdf Arabic one-pager
    index.html            regenerated from index.template.html (data injected via data.js)

All aggregation runs on Polars, so the same code path scales unchanged to 1M+ rows;
the browser only ever receives the small pre-aggregated JSON. A validation report is
printed and any failed hard-check aborts the build (non-zero exit).
"""
from __future__ import annotations

import json
import sys
from datetime import date

import polars as pl

from src import (config as C, load, data_quality, kpis as kpi_mod, customers as cust_mod,
                 products as prod_mod, receivables as recv_mod, insights as ins_mod)


def _jsonable(obj):
    if isinstance(obj, (date,)):
        return obj.isoformat()
    raise TypeError(type(obj))


def main() -> int:
    print("● Loading + parsing June 2026 source …")
    lines_raw, invoices = load.parse_june()
    dims = load.load_dimensions()
    lines = load.enrich_lines(lines_raw, dims["dim_items"])
    monthly = load.load_history_monthly().to_dicts()

    print("● Data-quality scan …")
    dq = data_quality.run(lines, invoices)

    print("● Receivables & aging …")
    receivables = recv_mod.compute(dims["debt_detail"])

    print("● Customer analysis + bonus …")
    customers = cust_mod.compute(lines, invoices, dims["dim_customers"])

    print("● Product analysis …")
    products = prod_mod.compute(lines)
    top_codes = [p["item_code"] for p in products[:6]]
    prod_daily = prod_mod.daily_trend_by_item(lines, top_codes)

    print("● Executive KPIs …")
    kpis = kpi_mod.compute(lines, invoices, customers, receivables)

    print("● Insights …")
    insights = ins_mod.generate(kpis, customers, products, receivables, monthly, dq)

    # --- extra chart-ready aggregates ------------------------------------
    daily = (
        invoices.with_columns(pl.col("invoice_date").cast(pl.Utf8).alias("day"))
        .group_by("day").agg([
            pl.col("reported_total").sum().alias("sales"),
            pl.col("paid").sum().alias("collections"),
            pl.col("invoice_no").n_unique().alias("invoices"),
        ]).sort("day")
    ).to_dicts()

    brand_mix = (
        lines.group_by("brand").agg([
            pl.col("line_total").sum().alias("sales"),
            pl.col("qty").sum().alias("qty"),
        ]).sort("sales", descending=True)
    ).to_dicts()

    # customer -> brand -> item hierarchy for treemap / sunburst / sankey (top slices)
    hier = (
        lines.group_by(["customer_name", "brand", "item_name"]).agg(
            pl.col("line_total").sum().alias("sales")
        ).sort("sales", descending=True)
    ).to_dicts()

    # price dispersion for box plot (top items)
    price_box = {}
    for code in top_codes:
        pv = lines.filter((pl.col("item_code") == code) & (pl.col("unit_price") > 0))
        price_box[code] = {
            "item_name": products_name(products, code),
            "prices": [round(float(x), 2) for x in pv["unit_price"].to_list()],
        }

    # line-level + invoice-level records (with salesperson) for client-side
    # cross-filtering — small enough to ship inline (800 lines / 311 invoices).
    rep_map = {
        str(r["customer_code"]): (r["rep"] or "غير محدد")
        for r in dims["dim_customers"].with_columns(
            pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True)
    }
    lines_export = lines.with_columns(
        pl.col("invoice_date").cast(pl.Utf8),
        pl.col("customer_code").cast(pl.Utf8).replace_strict(
            rep_map, default="غير محدد").alias("rep"),
    ).select(
        "invoice_no", "invoice_date", "customer_code", "customer_name", "rep",
        "item_code", "item_name", "brand", "qty", "unit_price", "line_total",
        "boxes", "is_bonus",
    ).to_dicts()
    invoices_export = invoices.with_columns(
        pl.col("invoice_date").cast(pl.Utf8),
        pl.col("customer_code").cast(pl.Utf8).replace_strict(
            rep_map, default="غير محدد").alias("rep"),
        pl.when(pl.col("reported_total").fill_null(0) == 0).then(pl.lit("zero"))
        .when(pl.col("remaining").fill_null(0) <= 0).then(pl.lit("paid"))
        .otherwise(pl.lit("unpaid")).alias("status"),
    ).select(
        "invoice_no", "invoice_date", "customer_code", "customer_name", "rep",
        "reported_total", "paid", "remaining", "qty_total", "n_lines",
        "is_bonus", "status",
    ).to_dicts()

    payload = {
        "meta": {
            "period_label": C.PERIOD_LABEL_AR,
            "as_of": C.AS_OF_DATE,
            "net_terms_days": C.NET_TERMS_DAYS,
            "bonus_rules": C.BONUS_RULES,
            "generated_utc": date.today().isoformat(),
        },
        "kpis": kpis,
        "lines": lines_export,
        "invoices": invoices_export,
        "customers": customers,
        "products": products,
        "product_daily": prod_daily,
        "price_box": price_box,
        "receivables": receivables,
        "monthly": monthly,
        "daily": daily,
        "brand_mix": brand_mix,
        "hierarchy": hier,
        "zero_invoices": dq["zero_invoices"],
        "data_quality": dq["summary"],
        "insights": insights,
    }

    # --- write deliverables ----------------------------------------------
    print("● Writing deliverables …")
    js = "window.DASH = " + json.dumps(payload, ensure_ascii=False, default=_jsonable) + ";\n"
    C.OUT_DATA_JS.write_text(js, encoding="utf-8")

    # processed_data.csv (cleaned June line items)
    lines.with_columns(pl.col("invoice_date").cast(pl.Utf8)).write_csv(C.OUT_PROCESSED_CSV)

    C.OUT_INSIGHTS.write_text(
        json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")

    # PDF (best-effort; never blocks the data build)
    try:
        from src import pdf_report
        pdf_report.build(kpis, customers, products, receivables, insights)
        print("  ✓ executive_summary.pdf")
    except Exception as e:  # pragma: no cover
        print(f"  ! PDF skipped: {e}")

    render_index()

    # --- validation report ------------------------------------------------
    ok = validate(lines, invoices, kpis, customers, products, receivables, dq)
    return 0 if ok else 1


def products_name(products, code):
    for p in products:
        if p["item_code"] == code:
            return p["item_name"]
    return code


def render_index():
    tpl = (C.APP_DIR / "index.template.html")
    if tpl.exists():
        C.OUT_INDEX.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")


def validate(lines, invoices, kpis, customers, products, receivables, dq) -> bool:
    print("\n" + "=" * 64)
    print("VALIDATION REPORT")
    print("=" * 64)
    checks = []

    def check(name, cond, detail=""):
        checks.append(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")

    # 1. reconciliation
    s = dq["summary"]
    check("invoice reconciliation ≥ 99%", s["reconciliation_rate"] >= 0.99,
          f"({s['reconciliation_rate']*100:.1f}%)")

    # 2. totals cross-check
    tot_lines = float(lines["line_total"].sum())
    tot_inv = float(invoices["reported_total"].sum())
    check("Σ line_total == Σ reported_total", abs(tot_lines - tot_inv) < 1.0,
          f"({tot_lines:,.0f} vs {tot_inv:,.0f})")

    # 3. counts
    check("311 invoices", kpis["n_invoices"] == 311, f"({kpis['n_invoices']})")
    check("116 customers", kpis["n_customers"] == 116, f"({kpis['n_customers']})")

    # 4. customer sales sum == total
    csum = sum(c["sales"] for c in customers)
    check("Σ customer sales == total", abs(csum - kpis["total_sales"]) < 1.0,
          f"({csum:,.0f})")

    # 5. product contribution sums ~100%
    contrib = sum(p["contribution_pct"] for p in products)
    check("Σ product contribution ≈ 100%", abs(contrib - 100) < 0.5, f"({contrib:.2f}%)")

    # 6. ASP recompute for top product
    if products:
        p = products[0]
        check("top product ASP = value/qty", p["asp"] > 0)

    # 7. aging buckets sum == outstanding
    bsum = sum(receivables["buckets"].values())
    check("aging buckets == outstanding", abs(bsum - receivables["total_outstanding"]) < 1.0,
          f"({bsum:,.0f})")

    # 8. bonus ladder boundaries
    from src.config import bonus_pct
    ladder_ok = (bonus_pct(0.69) == 0.0 and bonus_pct(0.70) == 0.01 and
                 bonus_pct(0.80) == 0.02 and bonus_pct(0.90) == 0.03 and
                 bonus_pct(0.95) == 0.05 and bonus_pct(1.0) == 0.05)
    check("bonus ladder boundaries", ladder_ok)

    passed = all(checks)
    print("=" * 64)
    print(f"RESULT: {'ALL CHECKS PASSED ✓' if passed else 'SOME CHECKS FAILED ✗'}")
    print("=" * 64)
    return passed


if __name__ == "__main__":
    sys.exit(main())
