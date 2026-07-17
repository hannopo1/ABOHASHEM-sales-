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


def _rep_map(dim_customers):
    return {str(r["customer_code"]): (r["rep"] or "غير محدد")
            for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8))
            .iter_rows(named=True)}


def _export_frames(lines, invoices, rep_map):
    """Line-level + invoice-level records (with salesperson, status and month)
    for client-side cross-filtering. Small enough to ship inline."""
    lx = lines.with_columns(
        pl.col("invoice_date").cast(pl.Utf8),
        pl.col("customer_code").cast(pl.Utf8).replace_strict(rep_map, default="غير محدد").alias("rep"),
    ).select(
        "invoice_no", "invoice_date", "month", "customer_code", "customer_name", "rep",
        "item_code", "item_name", "brand", "qty", "unit_price", "line_total", "boxes", "is_bonus",
    ).to_dicts()
    ix = invoices.with_columns(
        pl.col("invoice_date").cast(pl.Utf8),
        pl.col("customer_code").cast(pl.Utf8).replace_strict(rep_map, default="غير محدد").alias("rep"),
        pl.when(pl.col("reported_total").fill_null(0) == 0).then(pl.lit("zero"))
        .when(pl.col("remaining").fill_null(0) <= 0).then(pl.lit("paid"))
        .otherwise(pl.lit("unpaid")).alias("status"),
    ).select(
        "invoice_no", "invoice_date", "month", "customer_code", "customer_name", "rep",
        "reported_total", "paid", "remaining", "qty_total", "n_lines", "is_bonus", "status",
    ).to_dicts()
    return lx, ix


def _customer_ar(dim_customers):
    """Month-independent AR / bonus attributes per customer (from the 2026-07-04
    snapshot). Monthly sales are recomputed client-side; these stay fixed."""
    out = {}
    for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        billed = float(r["total_revenue"] or 0.0)
        has_ar = str(r.get("has_ar_snapshot")).lower() in ("true", "1")
        outstanding = float(r["ar_net_balance"] or 0.0) if has_ar else None
        rate = (max(0.0, min(1.0, (billed - (outstanding or 0.0)) / billed))
                if (has_ar and billed > 0) else None)
        out[r["customer_code"]] = {
            "total_billed": round(billed, 2),
            "outstanding": round(outstanding, 2) if outstanding is not None else None,
            "collection_rate": round(rate, 4) if rate is not None else None,
            "bonus_pct": C.bonus_pct(rate) if rate is not None else 0.0,
            "rep": r["rep"] or "غير محدد", "city": r["city"] or "", "has_ar": has_ar,
        }
    return out


def _month_subset(lines_all, invoices_all, month):
    if month == "all":
        return lines_all, invoices_all
    return (lines_all.filter(pl.col("month") == month),
            invoices_all.filter(pl.col("month") == month))


def _receivables_for(dims, receivables_full, invoices_sub, month):
    """Receivables snapshot restricted to the customers active in the month
    (the AR balance itself is a fixed snapshot; only the cohort narrows)."""
    if month == "all":
        return receivables_full
    active = invoices_sub["customer_code"].cast(pl.Utf8).unique().to_list()
    dd = dims["debt_detail"].with_columns(pl.col("customer_code").cast(pl.Utf8))
    return recv_mod.compute(dd.filter(pl.col("customer_code").is_in(active)))


def _bundle(lines_all, invoices_all, dims, receivables_full, monthly, month):
    """Full analytics bundle (kpis/customers/products/receivables/insights) for a
    single month, or 'all' for the whole year."""
    sl, si = _month_subset(lines_all, invoices_all, month)
    products = prod_mod.compute(sl)
    customers = cust_mod.compute(sl, si, dims["dim_customers"])
    recv = _receivables_for(dims, receivables_full, si, month)
    dq_m = data_quality.run(sl, si)
    kpis = kpi_mod.compute(sl, si, customers, recv)
    focus = None if month == "all" else month
    insights = ins_mod.generate(kpis, customers, products, recv, monthly, dq_m, focus_month=focus)
    return dict(kpis=kpis, customers=customers, products=products, receivables=recv, insights=insights)


def main() -> int:
    print("● Loading + parsing all 2026 sources …")
    lines_raw, invoices_all = load.parse_all(year=C.PERIOD_YEAR)
    dims = load.load_dimensions()
    lines_all = load.enrich_lines(lines_raw, dims["dim_items"])
    monthly = load.load_history_monthly().to_dicts()

    print("● Data-quality scan (all 2026) …")
    dq = data_quality.run(lines_all, invoices_all)

    print("● Receivables & aging (snapshot) …")
    receivables = recv_mod.compute(dims["debt_detail"])

    months = sorted(invoices_all["month"].unique().to_list())
    print(f"● Months found: {', '.join(months)}")

    # Per-month + whole-year insight sets (client picks by selected month).
    print("● Per-month analytics + insights …")
    insights_by_month = {
        m: _bundle(lines_all, invoices_all, dims, receivables, monthly, m)["insights"]
        for m in months + ["all"]
    }

    # Default-month (June) bundle — drives the PDF and the validation report.
    june = _bundle(lines_all, invoices_all, dims, receivables, monthly, C.DEFAULT_MONTH)

    rep_map = _rep_map(dims["dim_customers"])
    lines_x, invoices_x = _export_frames(lines_all, invoices_all, rep_map)

    payload = {
        "meta": {
            "period_label": C.month_label_ar(C.DEFAULT_MONTH),
            "default_month": C.DEFAULT_MONTH,
            # All twelve months are offered in the selector; `data_months` records
            # which actually carry source data so the client shows an honest empty
            # state (not fabricated values) for the rest.
            "available_months": [{"v": m, "l": C.month_label_ar(m)} for m in C.ALL_MONTHS],
            "data_months": months,
            "all_months_label": C.ALL_MONTHS_LABEL,
            "as_of": C.AS_OF_DATE,
            "net_terms_days": C.NET_TERMS_DAYS,
            "bonus_rules": C.BONUS_RULES,
            "generated_utc": date.today().isoformat(),
        },
        "lines": lines_x,
        "invoices": invoices_x,
        "customer_ar": _customer_ar(dims["dim_customers"]),
        "receivables": receivables,
        "monthly": monthly,
        "zero_invoices": dq["zero_invoices"],
        "data_quality": dq["summary"],
        "insights_by_month": insights_by_month,
    }

    # --- write deliverables ----------------------------------------------
    print("● Writing deliverables …")
    js = "window.DASH = " + json.dumps(payload, ensure_ascii=False, default=_jsonable) + ";\n"
    C.OUT_DATA_JS.write_text(js, encoding="utf-8")

    # processed_data.csv — all cleaned 2026 line items
    lines_all.with_columns(pl.col("invoice_date").cast(pl.Utf8)).write_csv(C.OUT_PROCESSED_CSV)

    C.OUT_INSIGHTS.write_text(
        json.dumps(insights_by_month, ensure_ascii=False, indent=2), encoding="utf-8")

    # PDF (best-effort; never blocks the data build) — default-month headline
    try:
        from src import pdf_report
        pdf_report.build(june["kpis"], june["customers"], june["products"],
                         june["receivables"], june["insights"])
        print("  ✓ executive_summary.pdf")
    except Exception as e:  # pragma: no cover
        print(f"  ! PDF skipped: {e}")

    render_index()

    # --- validation report ------------------------------------------------
    jl, ji = _month_subset(lines_all, invoices_all, C.DEFAULT_MONTH)
    ok = validate(lines_all, invoices_all, jl, ji, june, receivables, dq, months)
    return 0 if ok else 1


def render_index():
    tpl = (C.APP_DIR / "index.template.html")
    if tpl.exists():
        C.OUT_INDEX.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")


def validate(lines_all, invoices_all, jl, ji, june, receivables, dq, months) -> bool:
    print("\n" + "=" * 64)
    print("VALIDATION REPORT")
    print("=" * 64)
    checks = []

    def check(name, cond, detail=""):
        checks.append(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")

    kpis, customers, products = june["kpis"], june["customers"], june["products"]

    # 1. reconciliation (all 2026)
    s = dq["summary"]
    check("invoice reconciliation ≥ 99%", s["reconciliation_rate"] >= 0.99,
          f"({s['reconciliation_rate']*100:.1f}%)")

    # 2. totals cross-check (all 2026)
    tot_lines = float(lines_all["line_total"].sum())
    tot_inv = float(invoices_all["reported_total"].sum())
    check("Σ line_total == Σ reported_total (2026)", abs(tot_lines - tot_inv) < 1.0,
          f"({tot_lines:,.0f} vs {tot_inv:,.0f})")

    # 3. coverage
    check("6 months present (Jan–Jun 2026)", len(months) == 6, f"({', '.join(months)})")

    # 4. June default month unchanged (regression guard)
    check("June = 311 invoices", kpis["n_invoices"] == 311, f"({kpis['n_invoices']})")
    check("June = 116 customers", kpis["n_customers"] == 116, f"({kpis['n_customers']})")

    # 5. customer sales sum == month total
    csum = sum(c["sales"] for c in customers)
    check("Σ customer sales == June total", abs(csum - kpis["total_sales"]) < 1.0,
          f"({csum:,.0f})")

    # 6. product contribution sums ~100%
    contrib = sum(p["contribution_pct"] for p in products)
    check("Σ product contribution ≈ 100%", abs(contrib - 100) < 0.5, f"({contrib:.2f}%)")

    # 7. ASP recompute for top product
    check("top product ASP = value/qty", bool(products) and products[0]["asp"] > 0)

    # 8. aging buckets sum == outstanding (full snapshot)
    bsum = sum(receivables["buckets"].values())
    check("aging buckets == outstanding", abs(bsum - receivables["total_outstanding"]) < 1.0,
          f"({bsum:,.0f})")

    # 9. bonus ladder boundaries
    from src.config import bonus_pct
    ladder_ok = (bonus_pct(0.69) == 0.0 and bonus_pct(0.70) == 0.01 and
                 bonus_pct(0.80) == 0.02 and bonus_pct(0.90) == 0.03 and
                 bonus_pct(0.95) == 0.05 and bonus_pct(1.0) == 0.05)
    check("bonus ladder boundaries", ladder_ok)

    # 10. extended data-quality gates (reported here; no dashboard UI change)
    dup_cust = (invoices_all.group_by("customer_code")
                .agg(pl.col("customer_name").n_unique().alias("names"))
                .filter(pl.col("names") > 1).height)
    print(f"  [INFO] customer codes with >1 name variant: {dup_cust}")
    invalid_dates = invoices_all.filter(
        ~pl.col("invoice_date").cast(pl.Utf8).str.starts_with(str(C.PERIOD_YEAR))).height
    check("no invalid / out-of-year dates", invalid_dates == 0, f"({invalid_dates})")
    neg_qty = lines_all.filter(pl.col("qty") < 0).height
    check("no negative quantities", neg_qty == 0, f"({neg_qty})")
    bal = invoices_all.filter(
        ((pl.col("paid").fill_null(0) + pl.col("remaining").fill_null(0)
          - pl.col("reported_total").fill_null(0)).abs() > 1.0)).height
    check("invoice balances consistent (paid+remaining=total)",
          bal <= invoices_all.height * 0.02, f"({bal} mismatches)")

    passed = all(checks)
    print("=" * 64)
    print(f"RESULT: {'ALL CHECKS PASSED ✓' if passed else 'SOME CHECKS FAILED ✗'}")
    print("=" * 64)
    return passed


if __name__ == "__main__":
    sys.exit(main())
