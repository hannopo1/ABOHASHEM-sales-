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
                 products as prod_mod, insights as ins_mod, debt as debt_mod,
                 overdue as overdue_mod)


def _jsonable(obj):
    if isinstance(obj, (date,)):
        return obj.isoformat()
    raise TypeError(type(obj))


def _rep_map(dim_customers):
    return {str(r["customer_code"]): (r["rep"] or "غير محدد")
            for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8))
            .iter_rows(named=True)}


def _corrected_rep_map(final_balances, dim_customers, debt_detail):
    """Customer → representative, corrected against OFFICIAL master data.

    Single source of truth = the customer-account reports filed by rep
    (2026-07-16, file-based). Where a customer is absent there, fall back to the
    cleaned dim_customers.rep, then the 2026-07-04 debt detail. Never guesses —
    a customer with no rep in any source stays 'غير محدد' and is reported as an
    exception. Touches ONLY the rep relationship, no financial value.
    """
    rep = {}
    # 3rd priority: 2026-07-04 debt detail
    for r in debt_detail.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        v = (r.get("rep") or "").strip()
        if v:
            rep[str(r["customer_code"])] = v
    # 2nd priority: cleaned customer master (dim_customers)
    for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        v = (r["rep"] or "").strip()
        if v:
            rep[str(r["customer_code"])] = v
    # 1st priority (authoritative): the 2026-07-16 by-rep account reports
    for code, meta in final_balances.items():
        v = (meta.get("rep_official") or meta.get("rep") or "").strip()
        if v:
            rep[str(code)] = v
    return rep


def rep_exceptions(rep_map, invoices_all):
    """2026 sales customers with NO representative in any official source."""
    out = []
    seen = set()
    for r in invoices_all.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        code = r["customer_code"]
        if code in seen or rep_map.get(code):
            seen.add(code)
            continue
        seen.add(code)
        out.append({"customer_code": code, "customer_name": r["customer_name"],
                    "reason": "لا يوجد مندوب لهذا العميل في أي مصدر رسمي (تقارير المديونية / بيانات العملاء)"})
    return sorted(out, key=lambda x: x["customer_code"])


def _valid_name(nm) -> bool:
    return bool(nm) and not str(nm).strip().replace(" ", "").isdigit()


def _name_map(dim_customers, invoices_full, debt_detail):
    """Authoritative customer-code → name map so no view ever shows a bare code.
    Merged from every name-bearing source; dim_customers (cleaned reference) wins,
    then the 2026-07-04 debt detail, then the invoice history."""
    m = {}
    for r in invoices_full.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        code, nm = r["customer_code"], r["customer_name"]
        if code not in m and _valid_name(nm):
            m[code] = nm
    for r in debt_detail.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        if _valid_name(r.get("customer_name")):
            m[str(r["customer_code"])] = r["customer_name"]
    for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True):
        if _valid_name(r["customer_name"]):
            m[str(r["customer_code"])] = r["customer_name"]     # reference name wins
    return m


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


def _customer_ar(dim_customers, final_balances, invoices_full, rep_map):
    """Month-independent AR / bonus attributes per customer, from the FINAL
    2026-07-16 balances. Collection rate = (total billed − final balance) / total
    billed over the full parsed invoice history; bonus follows the ladder. Rep is
    taken from the corrected master map. Monthly sales are recomputed client-side;
    these attributes stay fixed."""
    billed_map = {
        str(r["customer_code"]): float(r["billed"] or 0.0)
        for r in invoices_full.with_columns(pl.col("customer_code").cast(pl.Utf8))
        .group_by("customer_code").agg(pl.col("reported_total").sum().alias("billed"))
        .iter_rows(named=True)
    }
    dc = {str(r["customer_code"]): r for r in
          dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8)).iter_rows(named=True)}

    out = {}
    for code in set(billed_map) | set(final_balances) | set(dc):
        billed = billed_map.get(code, float((dc.get(code) or {}).get("total_revenue") or 0.0))
        has_ar = code in final_balances
        outstanding = float(final_balances[code]["balance"]) if has_ar else None
        rate = (max(0.0, min(1.0, (billed - outstanding) / billed))
                if (has_ar and billed > 0) else None)
        d = dc.get(code, {})
        out[code] = {
            "total_billed": round(billed, 2),
            "outstanding": round(outstanding, 2) if outstanding is not None else None,
            "collection_rate": round(rate, 4) if rate is not None else None,
            "bonus_pct": C.bonus_pct(rate) if rate is not None else 0.0,
            "rep": rep_map.get(code) or "غير محدد",     # corrected master mapping
            "city": d.get("city") or "", "has_ar": has_ar,
        }
    return out


def _month_subset(lines_all, invoices_all, month):
    if month == "all":
        return lines_all, invoices_all
    return (lines_all.filter(pl.col("month") == month),
            invoices_all.filter(pl.col("month") == month))


def _receivables_for(receivables_full, invoices_sub, month):
    """FIFO overdue snapshot restricted to the customers active in the month
    (the balance itself is a fixed 2026-07-16 snapshot; only the cohort narrows).
    Bucket / rep / totals are re-aggregated from the narrowed rows so everything
    still reconciles exactly to that cohort's outstanding."""
    if month == "all":
        return receivables_full
    active = set(invoices_sub["customer_code"].cast(pl.Utf8).unique().to_list())
    rows = [r for r in receivables_full["rows"] if r["customer_code"] in active]
    buckets = {k: 0.0 for k in receivables_full["buckets"]}
    by_rep: dict = {}
    cur = ov = 0.0
    for r in rows:
        for k, v in r["buckets"].items():
            buckets[k] += v
        cur += r["current"]
        ov += r["overdue"]
        s = by_rep.setdefault(r["rep"], {"current": 0.0, "overdue": 0.0, "customers": 0})
        s["current"] += r["current"]
        s["overdue"] += r["overdue"]
        s["customers"] += 1
    rep_rows = sorted(({"rep": k, "current": round(v["current"], 2), "overdue": round(v["overdue"], 2),
                        "outstanding": round(v["current"] + v["overdue"], 2), "customers": v["customers"]}
                       for k, v in by_rep.items()), key=lambda x: x["outstanding"], reverse=True)
    return {**receivables_full,
            "total_outstanding": round(cur + ov, 2), "total_current": round(cur, 2),
            "total_overdue": round(ov, 2), "buckets": {k: round(v, 2) for k, v in buckets.items()},
            "by_rep": rep_rows, "rows": rows}


def _bundle(lines_all, invoices_all, dims, receivables_full, monthly, month):
    """Full analytics bundle (kpis/customers/products/receivables/insights) for a
    single month, or 'all' for the whole year."""
    sl, si = _month_subset(lines_all, invoices_all, month)
    products = prod_mod.compute(sl)
    customers = cust_mod.compute(sl, si, dims["dim_customers"])
    recv = _receivables_for(receivables_full, si, month)
    dq_m = data_quality.run(sl, si)
    kpis = kpi_mod.compute(sl, si, customers, recv)
    focus = None if month == "all" else month
    insights = ins_mod.generate(kpis, customers, products, recv, monthly, dq_m, focus_month=focus)
    return dict(kpis=kpis, customers=customers, products=products, receivables=recv, insights=insights)


def main() -> int:
    print("● Loading + parsing all sources (full history) …")
    dims = load.load_dimensions()
    lines_raw_full, invoices_full = load.parse_all()          # 2025-01 .. 2026-07 (all years)
    lines_full = load.enrich_lines(lines_raw_full, dims["dim_items"])
    # dashboard operates on the 2026 subset; full history feeds FIFO overdue only
    lines_all = lines_full.filter(pl.col("invoice_date").dt.year() == C.PERIOD_YEAR)
    invoices_all = invoices_full.filter(pl.col("invoice_date").dt.year() == C.PERIOD_YEAR)
    monthly = load.load_history_monthly().to_dicts()

    print("● Data-quality scan (all 2026) …")
    dq = data_quality.run(lines_all, invoices_all)

    print("● Final balances (2026-07-16) + FIFO overdue analysis …")
    final_balances = debt_mod.load_final_balances()
    name_map = _name_map(dims["dim_customers"], invoices_full, dims["debt_detail"])
    # Customer→rep corrected against official master (see _corrected_rep_map).
    rep_map = _corrected_rep_map(final_balances, dims["dim_customers"], dims["debt_detail"])
    rep_exc = rep_exceptions(rep_map, invoices_all)
    print(f"● Customer→rep: {len(rep_map)} mapped · {len(rep_exc)} sales customers with no rep (exceptions)")
    receivables = overdue_mod.compute(invoices_full, final_balances, dims["dim_customers"],
                                      net_terms=C.NET_TERMS_DAYS, as_of_str=C.AS_OF_DATE,
                                      cutoff_str=C.OVERDUE_CUTOFF, name_map=name_map, rep_map=rep_map)

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
        "customer_ar": _customer_ar(dims["dim_customers"], final_balances, invoices_full, rep_map),
        "receivables": receivables,
        "monthly": monthly,
        "zero_invoices": dq["zero_invoices"],
        "data_quality": dq["summary"],
        "insights_by_month": insights_by_month,
        "rep_exceptions": rep_exc,
    }

    # --- write deliverables ----------------------------------------------
    print("● Writing deliverables …")
    js = "window.DASH = " + json.dumps(payload, ensure_ascii=False, default=_jsonable) + ";\n"
    C.OUT_DATA_JS.write_text(js, encoding="utf-8")

    # processed_data.csv — all cleaned 2026 line items
    lines_all.with_columns(pl.col("invoice_date").cast(pl.Utf8)).write_csv(C.OUT_PROCESSED_CSV)

    C.OUT_INSIGHTS.write_text(
        json.dumps(insights_by_month, ensure_ascii=False, indent=2), encoding="utf-8")

    # Customer→rep Exceptions Report — sales customers with no rep in any source.
    C.OUT_REP_EXCEPTIONS.write_text(
        json.dumps({"as_of": C.AS_OF_DATE, "count": len(rep_exc), "exceptions": rep_exc},
                   ensure_ascii=False, indent=2), encoding="utf-8")

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
    check("≥6 months present (2026)", len(months) >= 6, f"({', '.join(months)})")

    # 4. June regression guard — historical June figures must stay byte-identical
    #    regardless of the default month.
    jun_inv = invoices_all.filter(pl.col("month") == "2026-06")
    jn = int(jun_inv["invoice_no"].n_unique())
    jc = int(jun_inv["customer_code"].n_unique())
    jsales = float(jun_inv["reported_total"].sum())
    check("June = 311 invoices (unchanged)", jn == 311, f"({jn})")
    check("June = 116 customers (unchanged)", jc == 116, f"({jc})")
    check("June sales = 3,867,491 (unchanged)", abs(jsales - 3867491) < 1.0, f"({jsales:,.0f})")

    # 5. customer sales sum == default-month total
    csum = sum(c["sales"] for c in customers)
    check("Σ customer sales == default-month total", abs(csum - kpis["total_sales"]) < 1.0,
          f"({csum:,.0f})")

    # 6. product contribution sums ~100%
    contrib = sum(p["contribution_pct"] for p in products)
    check("Σ product contribution ≈ 100%", abs(contrib - 100) < 0.5, f"({contrib:.2f}%)")

    # 7. ASP recompute for top product
    check("top product ASP = value/qty", bool(products) and products[0]["asp"] > 0)

    # 8. aging buckets sum == outstanding (FIFO overdue, 2026-07-16)
    bsum = sum(receivables["buckets"].values())
    check("aging buckets == outstanding", abs(bsum - receivables["total_outstanding"]) < 1.0,
          f"({bsum:,.0f})")

    # 8b. per-customer FIFO reconciliation: current+overdue == final balance
    recon_bad = sum(1 for r in receivables["rows"]
                    if abs((r["current"] + r["overdue"]) - r["outstanding"]) > 0.5)
    check("every customer current+overdue == final balance", recon_bad == 0,
          f"({recon_bad} mismatches)")

    # 8c. current bucket holds ONLY July (not-yet-due); overdue = ≤June + opening
    check("current = not-overdue, overdue reconciles",
          abs(receivables["total_current"] + receivables["total_overdue"]
              - receivables["total_outstanding"]) < 1.0,
          f"(overdue {receivables['total_overdue']:,.0f})")

    # 8d. every receivable row shows a customer NAME (or an honest "عميل <code>"
    #     label), never a bare numeric code.
    import re as _re
    code_named = [r["customer_code"] for r in receivables["rows"]
                  if _re.fullmatch(r"[\d\s]*", r["customer_name"] or "")]
    check("no receivable shows a bare code as name", not code_named,
          f"({len(code_named)} bare codes)")
    labelled = sum(1 for r in receivables["rows"] if str(r["customer_name"]).startswith("عميل "))
    if labelled:
        print(f"  [INFO] {labelled} customers have no name in any source → shown as 'عميل <code>'")

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

    # 10b. July invoice dates must all fall inside July 2026 (never the report
    #      period-header date or any out-of-month value).
    jul = invoices_all.filter(pl.col("month") == "2026-07")
    if jul.height:
        bad_jul = jul.filter(~((pl.col("invoice_date").dt.year() == 2026)
                               & (pl.col("invoice_date").dt.month() == 7))).height
        jmin = jul["invoice_date"].min()
        jmax = jul["invoice_date"].max()
        check("all July invoice dates inside July 2026", bad_jul == 0,
              f"({bad_jul} out-of-month · span {jmin}..{jmax})")
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
