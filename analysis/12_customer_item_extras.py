#!/usr/bin/env python3
"""
Additional customer/item cuts requested on top of the core pipeline:
  - item average selling price (ASP), with quantity re-expressed in
    boxes/cartons using the carton-capacity reference
  - per-customer sales, bonus (free-goods) share, and AR/rep linkage
  - explicit list of AR customers with zero invoices in the sales data
    (debt on the books but no matching sales transaction in this dataset)

Note: this does NOT include an "arrears aging" or "monthly credit rate"
calculation -- that requires a credit-term/rate assumption not stated in any
uploaded file, and is intentionally left out pending clarification (see the
chat) rather than guessed.
"""
import json
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"

tx = pd.read_csv(P / "sales_transactions_enriched.csv", dtype={"customer_code": str})
dim_items = pd.read_csv(P / "dim_items.csv")
dim_customers = pd.read_csv(P / "dim_customers.csv", dtype={"customer_code": str})
ar = pd.read_csv(P / "ar_customer_balances_2026-07-04.csv", dtype={"customer_code": str})
ar["net_balance"] = ar["debit"] - ar["credit"]
clog = json.load(open(P / "customer_dim_log.json", encoding="utf-8"))

# ---- 1. Item ASP + quantity in boxes/cartons -------------------------------
items = dim_items.copy()
items["carton_units"] = items["carton_capacity"].astype(str).str.extract(r"(\d+)").astype(float)
items["asp_egp"] = items["total_revenue"] / items["total_qty"].replace(0, pd.NA)
items["qty_in_boxes"] = items["total_qty"] / items["carton_units"]
items_out = items[["item_code", "item_name", "brand", "total_qty", "carton_capacity",
                    "carton_units", "qty_in_boxes", "asp_egp", "total_revenue", "n_lines"]].sort_values(
    "total_revenue", ascending=False)
items_out.to_csv(P / "item_asp_and_boxes.csv", index=False, encoding="utf-8")

# ---- 2. Per-customer sales, bonus share, rep/AR linkage --------------------
cust_dim_map = dim_customers.set_index("customer_code")
ar_rep_map = ar.groupby("customer_code").agg(rep=("rep", "first"), city=("city", "first"),
                                              net_balance=("net_balance", "sum")).to_dict("index")

rows = []
for code, sub in tx.groupby("customer_code"):
    total_qty = sub["qty"].sum()
    total_sales = sub["line_total"].sum()
    bonus_sub = sub[sub["is_bonus"] & (sub["unit_price"] == 0)]
    bonus_qty = bonus_sub["qty"].sum()
    # value the bonus qty at each item's own overall ASP (same method as financial_analysis.py)
    item_asp_map = items_out.set_index("item_name")["asp_egp"].to_dict()
    bonus_value = 0.0
    for item_name, g in bonus_sub.groupby("item_name_canonical"):
        asp = item_asp_map.get(item_name)
        if asp and asp == asp:
            bonus_value += g["qty"].sum() * asp
    name = cust_dim_map.loc[code, "customer_name"] if code in cust_dim_map.index else sub["customer_name_raw"].mode().iloc[0]
    ar_info = ar_rep_map.get(code, {})
    rows.append(dict(
        customer_code=code, customer_name=name,
        total_qty=total_qty, total_sales_egp=total_sales,
        bonus_qty=bonus_qty, bonus_estimated_value_egp=round(bonus_value, 2),
        bonus_pct_of_qty=round(bonus_qty / total_qty * 100, 3) if total_qty else 0,
        bonus_pct_of_sales_value=round(bonus_value / total_sales * 100, 3) if total_sales else 0,
        rep=ar_info.get("rep"), city=ar_info.get("city"),
        ar_net_balance_2026_07_04=ar_info.get("net_balance"),
        n_invoices=sub["invoice_no"].nunique(),
    ))
cust_out = pd.DataFrame(rows).sort_values("total_sales_egp", ascending=False)
cust_out.to_csv(P / "customer_sales_bonus_summary.csv", index=False, encoding="utf-8")

# ---- 3. AR customers with zero invoices in the sales data ------------------
zero_invoice_codes = clog["ar_customers_not_in_transactions"]
zero_inv = ar[ar["customer_code"].isin(zero_invoice_codes)].groupby("customer_code").agg(
    customer_name=("customer_name", "first"), rep=("rep", "first"),
    net_balance=("net_balance", "sum")).reset_index().sort_values("net_balance", ascending=False)
zero_inv.to_csv(P / "ar_customers_zero_invoices.csv", index=False, encoding="utf-8")

print("Item ASP + boxes: ", len(items_out), "rows ->", P / "item_asp_and_boxes.csv")
print("Customer sales+bonus summary:", len(cust_out), "rows ->", P / "customer_sales_bonus_summary.csv")
print("AR customers with zero invoices:", len(zero_inv), "rows ->", P / "ar_customers_zero_invoices.csv")
print()
print("Top 5 items by ASP table:")
print(items_out.head(5).to_string())
print()
print("Top 5 customers by bonus % of sales value:")
print(cust_out[cust_out.total_sales_egp > 10000].sort_values("bonus_pct_of_sales_value", ascending=False).head(5).to_string())
