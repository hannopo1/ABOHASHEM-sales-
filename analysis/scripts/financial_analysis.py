"""
Revenue-side financial analysis. IMPORTANT SCOPE NOTE: the uploaded source
files are sales invoices only (no purchase/production cost ledger, no
inventory stock levels, no balance sheet or payables data). Therefore COGS,
Gross Profit, Gross/Operating Margin, EBITDA and Net Profit CANNOT be
computed and are explicitly reported as not available here rather than
estimated. Only figures derivable from invoice-level revenue, discount, tax,
and receivable (paid/remaining) fields are produced.
"""
import json
import numpy as np
import pandas as pd

OUT = "data/eda"


def hhi(shares_pct):
    s = np.asarray(shares_pct) / 100
    return float((s ** 2).sum() * 10000)


def main():
    h = pd.read_csv("data/invoices_header_merged.csv", dtype={"customer_code": str})
    l = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    im = pd.read_csv("data/item_master.csv", dtype={"item_code": str})
    h["date"] = pd.to_datetime(h["date"], format="%Y/%m/%d")
    l = l.merge(im[["item_code", "brand"]], on="item_code", how="left")

    result = {}
    result["total_revenue"] = float(h["invoice_total"].sum())
    result["total_tax_collected"] = float(h["tax_total"].sum())
    result["total_paid"] = float(h["paid"].sum())
    result["total_remaining_receivables"] = float(h["remaining"].sum())
    result["pct_revenue_outstanding"] = round(100 * result["total_remaining_receivables"] / result["total_revenue"], 2)

    # discount impact: line_total appears net-of-discount already (gross = qty*price); estimate discount euros
    l["gross_value"] = l["qty"] * l["unit_price"]
    l["discount_value"] = l["gross_value"] * l["discount_pct"] / 100
    result["total_gross_value_before_discount"] = float(l["gross_value"].sum())
    result["total_discount_value"] = float(l["discount_value"].sum())
    result["avg_discount_pct_weighted"] = round(100 * result["total_discount_value"] / result["total_gross_value_before_discount"], 3)

    # AR aging proxy: invoices with remaining > 0, bucketed by age from invoice date to dataset max date
    as_of = h["date"].max()
    unpaid = h[h["remaining"] > 0].copy()
    unpaid["age_days"] = (as_of - unpaid["date"]).dt.days
    bins = [-1, 30, 60, 90, 180, 10_000]
    labels = ["0-30", "31-60", "61-90", "91-180", "180+"]
    unpaid["bucket"] = pd.cut(unpaid["age_days"], bins=bins, labels=labels)
    aging = unpaid.groupby("bucket", observed=True)["remaining"].sum()
    aging_df = aging.reset_index()
    aging_df.columns = ["age_bucket_days", "outstanding_amount"]
    aging_df["pct_of_total_outstanding"] = (aging_df["outstanding_amount"] / aging_df["outstanding_amount"].sum() * 100).round(2)
    aging_df.to_csv(f"{OUT}/ar_aging.csv", index=False, encoding="utf-8-sig")
    result["n_invoices_with_outstanding_balance"] = int((h["remaining"] > 0).sum())
    result["n_invoices_fully_paid"] = int((h["remaining"] <= 0).sum())

    # customer concentration (HHI, already partly in eda) restated here for the financial section
    cust = h.groupby("customer_code")["invoice_total"].sum().sort_values(ascending=False)
    cust_shares = (cust / cust.sum() * 100)
    result["customer_hhi"] = round(hhi(cust_shares), 1)
    result["top1_customer_pct"] = round(float(cust_shares.iloc[0]), 2)
    result["top5_customer_pct"] = round(float(cust_shares.iloc[:5].sum()), 2)
    result["top10_customer_pct"] = round(float(cust_shares.iloc[:10].sum()), 2)
    result["n_customers"] = int(len(cust))

    # brand concentration
    brand_rev = l.groupby("brand")["line_total"].sum().sort_values(ascending=False)
    brand_shares = (brand_rev / brand_rev.sum() * 100)
    result["brand_hhi"] = round(hhi(brand_shares), 1)
    result["top_brand_pct"] = round(float(brand_shares.iloc[0]), 2)

    # product (item) concentration
    item_rev = l.groupby("item_code")["line_total"].sum().sort_values(ascending=False)
    item_shares = (item_rev / item_rev.sum() * 100)
    result["item_hhi"] = round(hhi(item_shares), 1)
    result["top1_item_pct"] = round(float(item_shares.iloc[0]), 2)
    result["top5_item_pct"] = round(float(item_shares.iloc[:5].sum()), 2)
    result["top10_item_pct"] = round(float(item_shares.iloc[:10].sum()), 2)

    # explicitly flag unavailable financial statement items
    result["NOT_AVAILABLE_from_uploaded_files"] = [
        "COGS (Cost of Goods Sold) - no purchase/production cost ledger uploaded",
        "Gross Profit / Gross Margin - requires COGS",
        "Operating Margin / EBITDA / Net Profit - requires opex and full P&L, not uploaded",
        "Working Capital - requires balance sheet (current assets/liabilities), not uploaded",
        "Inventory Turnover - requires stock/inventory level data, not uploaded",
        "Customer Lifetime Value (profit-based) - requires margin data; a revenue-based proxy is provided instead in the dashboards",
    ]

    with open(f"{OUT}/financial_summary.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
