#!/usr/bin/env python3
"""Data-quality diagnostics on the parsed & enriched transactional dataset."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
OUT = ROOT / "data" / "processed" / "data_quality_metrics.json"

MAIN_MD = ROOT / "فواتير المبيعات من 112025 الى 3152026.md"


def month_key(s):
    y, m, d = s.split("/")
    return f"{int(y):04d}-{int(m):02d}"


def main():
    df = pd.read_csv(TX, dtype={"customer_code": str, "invoice_no": str})
    df["invoice_date_parsed"] = pd.to_datetime(df["invoice_date"], format="%Y/%m/%d", errors="coerce")
    df["month"] = df["invoice_date_parsed"].dt.to_period("M").astype(str)

    q = {}
    q["n_rows"] = int(len(df))
    q["n_invoices"] = int(df["invoice_no"].nunique())
    q["date_min"] = str(df["invoice_date_parsed"].min())
    q["date_max"] = str(df["invoice_date_parsed"].max())
    q["n_unparseable_dates"] = int(df["invoice_date_parsed"].isna().sum())

    # missing values
    miss = {}
    for c in ["customer_code", "customer_name_raw", "phone", "item_code", "item_name_raw",
              "qty", "unit_price", "discount_pct", "tax_pct", "line_total", "brand"]:
        miss[c] = dict(n_missing=int(df[c].isna().sum()), pct_missing=round(float(df[c].isna().mean() * 100), 3))
    q["missing_values"] = miss

    # duplicate line-level rows (same invoice+seq+item+qty+total repeated identically -> possible double parse)
    dup_mask = df.duplicated(subset=["invoice_no", "seq", "item_code", "qty", "line_total"], keep=False)
    q["n_duplicate_line_candidates"] = int(dup_mask.sum())

    # duplicate invoice numbers across sources (main vs june overlap window 2026-06-01..09)
    dup_inv = df.groupby("invoice_no")["source"].nunique()
    q["invoice_numbers_in_both_sources"] = int((dup_inv > 1).sum())

    # zero / negative / bonus lines
    q["n_zero_price_lines"] = int((df["unit_price"] == 0).sum())
    q["n_zero_total_lines"] = int((df["line_total"] == 0).sum())
    q["n_negative_qty"] = int((df["qty"] < 0).sum())
    q["n_negative_total"] = int((df["line_total"] < 0).sum())
    q["n_bonus_lines"] = int(df["is_bonus"].sum())
    q["bonus_share_of_lines_pct"] = round(float(df["is_bonus"].mean() * 100), 3)

    # discount / "tax" field ranges (documents the empirical finding that this field
    # behaves as a subtractive rate: line_total ~= qty*unit_price*(1-discount_pct/100)*(1-tax_pct/100))
    check = df.dropna(subset=["qty", "unit_price", "line_total"]).copy()
    check["discount_pct_f"] = check["discount_pct"].fillna(0)
    check["tax_pct_f"] = check["tax_pct"].fillna(0)
    check["expected_total"] = (check["qty"] * check["unit_price"]
                                * (1 - check["discount_pct_f"] / 100) * (1 - check["tax_pct_f"] / 100))
    check["resid"] = check["line_total"] - check["expected_total"]
    q["formula_check_mean_abs_residual"] = round(float(check["resid"].abs().mean()), 4)
    q["formula_check_max_abs_residual"] = round(float(check["resid"].abs().max()), 2)
    q["formula_check_pct_within_1_egp"] = round(float((check["resid"].abs() < 1).mean() * 100), 3)
    q["discount_pct_range"] = [float(df["discount_pct"].min()), float(df["discount_pct"].max())]
    q["tax_pct_range"] = [float(df["tax_pct"].dropna().min()), float(df["tax_pct"].dropna().max())]

    # invoice-level reconciliation (already enforced at parse time, re-verify here)
    inv_sum = df.groupby("invoice_no").agg(line_sum=("line_total", "sum"),
                                            reported=("invoice_reported_total", "first")).reset_index()
    inv_sum["diff"] = (inv_sum["line_sum"] - inv_sum["reported"]).abs()
    q["n_invoices_reconciliation_mismatch_over_1egp"] = int((inv_sum["diff"] > 1).sum())

    # outliers on unit_price per item_code (IQR method), excluding bonus (price=0) lines
    outlier_rows = []
    nonbonus = df[~df["is_bonus"] & (df["unit_price"] > 0)]
    for code, sub in nonbonus.groupby("item_code"):
        if len(sub) < 8:
            continue
        q1, q3 = sub["unit_price"].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        out = sub[(sub["unit_price"] < lo) | (sub["unit_price"] > hi)]
        if len(out):
            outlier_rows.append(dict(item_code=int(code), item_name=sub["item_name_canonical"].iloc[0],
                                      n_outliers=int(len(out)), n_total=int(len(sub)),
                                      price_range_normal=[round(float(lo), 2), round(float(hi), 2)],
                                      outlier_price_min=float(out["unit_price"].min()),
                                      outlier_price_max=float(out["unit_price"].max())))
    q["price_outliers_by_item"] = sorted(outlier_rows, key=lambda r: -r["n_outliers"])[:20]
    q["n_items_with_price_outliers"] = len(outlier_rows)

    # customer / brand normalization stats
    q["n_distinct_customer_codes"] = int(df["customer_code"].nunique())
    q["n_distinct_customer_names_raw"] = int(df["customer_name_raw"].nunique())
    q["n_distinct_item_codes"] = int(df["item_code"].nunique())
    q["n_distinct_item_names_raw"] = int(df["item_name_raw"].nunique())
    q["n_distinct_brands"] = int(df["brand"].nunique())
    q["revenue_share_unclassified_brand_pct"] = round(
        float(df.loc[df["brand"] == "غير مصنف", "line_total"].sum() / df["line_total"].sum() * 100), 4)

    # cross-validate monthly invoice counts against the source file's own stated index
    monthly_index_text = """2025-01: 320
2025-02: 256
2025-03: 322
2025-04: 244
2025-05: 277
2025-06: 184
2025-07: 227
2025-08: 283
2025-09: 314
2025-10: 319
2025-11: 250
2025-12: 260
2026-01: 266
2026-02: 270
2026-03: 231
2026-04: 287
2026-05: 281"""
    stated = {}
    for line in monthly_index_text.strip().split("\n"):
        k, v = line.split(":")
        stated[k.strip()] = int(v.strip())
    parsed_counts = df[df["source"] == "main_2025_2026H1"].groupby("month")["invoice_no"].nunique().to_dict()
    recon = {m: dict(stated=stated[m], parsed=int(parsed_counts.get(m, 0))) for m in stated}
    mismatches = {m: v for m, v in recon.items() if v["stated"] != v["parsed"]}
    q["monthly_invoice_count_reconciliation"] = recon
    q["monthly_invoice_count_mismatches"] = mismatches

    q["total_revenue_egp"] = round(float(df["line_total"].sum()), 2)
    q["total_qty_units"] = round(float(df["qty"].sum()), 2)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in q.items() if k not in
                       ("price_outliers_by_item", "monthly_invoice_count_reconciliation")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
