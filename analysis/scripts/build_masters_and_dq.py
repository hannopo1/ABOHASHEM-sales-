"""
Build customer/item master tables and compute the data-quality metrics that
feed analysis/reports/data_quality_report.md. All numbers here are computed
directly from invoices_header_merged.csv / invoice_lines_merged.csv - nothing
is invented.
"""
import re
import json
import pandas as pd
import numpy as np

pd.set_option("display.max_rows", 100)


def norm_name(s):
    s = str(s)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ى", "ي").replace("ة", "ه"))
    s = re.sub(r"[/\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    h = pd.read_csv("data/invoices_header_merged.csv", dtype={"customer_code": str})
    l = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    item_master = pd.read_csv("data/item_master.csv", dtype={"item_code": str})
    h["date"] = pd.to_datetime(h["date"], format="%Y/%m/%d")
    h["month"] = h["date"].dt.to_period("M").astype(str)

    dq = {}
    dq["n_invoices"] = int(len(h))
    dq["n_line_items"] = int(len(l))
    dq["date_min"] = str(h["date"].min().date())
    dq["date_max"] = str(h["date"].max().date())
    dq["n_customers_by_code"] = int(h["customer_code"].nunique())
    dq["n_customers_by_raw_name"] = int(h["customer_name"].nunique())
    dq["n_distinct_items"] = int(l["item_code"].nunique())

    # reconciliation check
    sums = l.groupby("invoice_id")["line_total"].sum().rename("sum_lines")
    chk = h.set_index("invoice_id")[["invoice_total"]].join(sums)
    chk["diff"] = (chk["invoice_total"] - chk["sum_lines"]).round(2)
    dq["invoices_reconciled_ok"] = int((chk["diff"].abs() <= 1).sum())
    dq["invoices_reconciliation_mismatch"] = int((chk["diff"].abs() > 1).sum())

    # duplicate invoice id
    dq["duplicate_invoice_ids"] = int(h["invoice_id"].duplicated().sum())

    # missing values summary
    dq["missing_header_fields"] = h.isna().sum().to_dict()
    dq["missing_line_fields"] = l.isna().sum().to_dict()

    # exact duplicate line rows (same invoice, item, qty, price -> possible double entry)
    dup_lines = l.duplicated(subset=["invoice_id", "item_code", "qty", "unit_price", "line_total"], keep=False)
    dq["duplicate_line_rows"] = int(dup_lines.sum())

    # zero-value / bonus lines
    dq["zero_total_lines"] = int((l["line_total"] == 0).sum())
    dq["zero_total_lines_pct"] = round(100 * dq["zero_total_lines"] / len(l), 2)
    dq["bonus_flagged_invoices"] = int(h["notes"].fillna("").str.contains("بونص").sum())

    # negative remaining / negative qty checks
    dq["negative_remaining_invoices"] = int((h["remaining"] < 0).sum())
    dq["negative_qty_lines"] = int((l["qty"] < 0).sum())
    dq["negative_price_lines"] = int((l["unit_price"] < 0).sum())

    # discount / tax pct ranges
    dq["discount_pct_min"] = float(l["discount_pct"].min())
    dq["discount_pct_max"] = float(l["discount_pct"].max())
    dq["tax_pct_min"] = float(l["tax_pct"].min())
    dq["tax_pct_max"] = float(l["tax_pct"].max())

    # price outliers per item (z-score on unit_price within item_code, positive-price lines only)
    priced = l[l["unit_price"] > 0].copy()
    grp = priced.groupby("item_code")["unit_price"]
    priced["z"] = (priced["unit_price"] - grp.transform("mean")) / grp.transform("std").replace(0, np.nan)
    outliers = priced[priced["z"].abs() > 4]
    dq["price_outlier_lines_z_gt_4"] = int(len(outliers))
    outliers[["invoice_id", "item_code", "item_name_raw", "unit_price", "z"]].to_csv(
        "data/price_outliers.csv", index=False, encoding="utf-8-sig"
    )

    # brand / carton mapping coverage
    dq["items_unclassified_brand"] = int((item_master["match_method"] == "unclassified").sum())
    dq["items_total"] = int(len(item_master))
    lm = l.merge(item_master[["item_code", "brand"]], on="item_code", how="left")
    dq["revenue_unclassified_brand_pct"] = round(
        100 * lm.loc[lm["brand"].str.startswith("غير مصنف", na=False), "line_total"].sum() / lm["line_total"].sum(), 4
    )
    dq["items_missing_carton_capacity"] = int(item_master["units_per_carton"].isna().sum())

    # customer name normalization
    h["name_norm"] = h["customer_name"].map(norm_name)
    g_raw = h.groupby("customer_code")["customer_name"].nunique()
    g_norm = h.groupby("customer_code")["name_norm"].nunique()
    dq["customer_codes_with_multiple_raw_names"] = int((g_raw > 1).sum())
    dq["customer_codes_with_multiple_names_after_normalization"] = int((g_norm > 1).sum())
    dq["cash_customer_code_1_invoice_count"] = int((h["customer_code"] == "1").sum())
    dq["cash_customer_code_1_revenue_pct"] = round(
        100 * h.loc[h["customer_code"] == "1", "invoice_total"].sum() / h["invoice_total"].sum(), 2
    )

    with open("data/data_quality_metrics.json", "w", encoding="utf-8") as f:
        json.dump(dq, f, ensure_ascii=False, indent=2, default=str)

    # ---- customer master ----
    canonical_name = (h.groupby("customer_code")["customer_name"]
                       .agg(lambda x: x.value_counts().index[0]))
    cust_agg = h.groupby("customer_code").agg(
        n_invoices=("invoice_id", "count"),
        total_revenue=("invoice_total", "sum"),
        total_paid=("paid", "sum"),
        total_remaining=("remaining", "sum"),
        first_invoice_date=("date", "min"),
        last_invoice_date=("date", "max"),
    )
    cust_master = cust_agg.join(canonical_name.rename("canonical_name"))
    cust_master["is_cash_or_generic_bucket"] = cust_master.index == "1"
    cust_master = cust_master.reset_index()
    cust_master.to_csv("data/customer_master.csv", index=False, encoding="utf-8-sig")

    print(json.dumps(dq, ensure_ascii=False, indent=2, default=str))
    print("\ncustomer_master rows:", len(cust_master))


if __name__ == "__main__":
    main()
