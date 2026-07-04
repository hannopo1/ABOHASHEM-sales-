#!/usr/bin/env python3
"""Consolidate all analysis outputs into a single embedded JS data file for
the self-contained HTML dashboards (avoids file:// fetch/CORS issues)."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
OUT = ROOT / "dashboards" / "data.js"


def rd_json(name):
    with open(P / name, encoding="utf-8") as f:
        return json.load(f)


def rd_csv(name):
    return pd.read_csv(P / name, dtype={"customer_code": str} if "customer" in name else None)


def clean(obj):
    """Recursively replace NaN/inf with None for strict JSON output."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj


def main():
    data = {}
    data["parse_log"] = rd_json("parse_log.json")
    data["dimension_log"] = rd_json("dimension_log.json")
    data["customer_dim_log"] = rd_json("customer_dim_log.json")
    data["data_quality"] = rd_json("data_quality_metrics.json")
    data["eda_summary"] = rd_json("eda_summary.json")
    data["timeseries"] = rd_json("timeseries_diagnostics.json")
    data["forecast"] = rd_json("forecast_results.json")
    data["forecast_disagg"] = rd_json("forecast_disaggregated.json")
    data["financial"] = rd_json("financial_analysis.json")

    monthly = rd_csv("eda_monthly_series.csv")
    data["monthly_series"] = json.loads(monthly.to_json(orient="records"))

    cust_pareto = rd_csv("eda_customer_pareto_abc.csv")
    data["customer_pareto"] = json.loads(cust_pareto.to_json(orient="records"))

    brand_summary = rd_csv("eda_brand_summary.csv")
    data["brand_summary"] = json.loads(brand_summary.to_json(orient="records"))

    item_abc_xyz = rd_csv("eda_item_abc_xyz.csv")
    data["item_abc_xyz"] = json.loads(item_abc_xyz.to_json(orient="records"))

    asp_by_brand_month = rd_csv("eda_asp_by_brand_month.csv")
    data["asp_by_brand_month"] = json.loads(asp_by_brand_month.to_json(orient="records"))

    tx0 = pd.read_csv(P / "sales_transactions_enriched.csv")
    tx0["invoice_date_parsed"] = pd.to_datetime(tx0["invoice_date"], format="%Y/%m/%d")
    tx0["month"] = tx0["invoice_date_parsed"].dt.to_period("M").astype(str)
    brand_month_rev = tx0.groupby(["month", "brand"])["line_total"].sum().reset_index()
    data["brand_month_revenue"] = json.loads(brand_month_rev.to_json(orient="records"))

    dim_items = rd_csv("dim_items.csv")
    data["dim_items"] = json.loads(dim_items.to_json(orient="records"))

    item_asp_boxes = rd_csv("item_asp_and_boxes.csv")
    data["item_asp_boxes"] = json.loads(item_asp_boxes.to_json(orient="records"))

    customer_bonus = rd_csv("customer_sales_bonus_summary.csv")
    data["customer_bonus_summary"] = json.loads(customer_bonus.to_json(orient="records"))

    ar_zero_invoice = rd_csv("ar_customers_zero_invoices.csv")
    data["ar_zero_invoice_customers"] = json.loads(ar_zero_invoice.to_json(orient="records"))

    dim_customers = rd_csv("dim_customers.csv")
    data["dim_customers"] = json.loads(dim_customers.to_json(orient="records"))

    ar = rd_csv("ar_customer_balances_2026-07-04.csv")
    ar["net_balance"] = ar["debit"] - ar["credit"]
    data["ar_balances"] = json.loads(ar.to_json(orient="records"))

    # hierarchy: aggregate to a lighter 3-level structure for the browser
    # (customer -> brand -> item) instead of shipping the full flat 2069-row table twice
    hier = rd_csv("eda_hierarchy_customer_brand_item.csv")
    name_map = dim_customers.set_index("customer_code")["customer_name"].to_dict()
    tree = {}
    for _, r in hier.iterrows():
        cust = r["customer_code"]
        tree.setdefault(cust, {"name": name_map.get(cust, cust), "sales": 0.0, "qty": 0.0, "brands": {}})
        node = tree[cust]
        node["sales"] += float(r["sales"]) if pd.notna(r["sales"]) else 0.0
        node["qty"] += float(r["qty"]) if pd.notna(r["qty"]) else 0.0
        b = node["brands"].setdefault(r["brand"], {"sales": 0.0, "qty": 0.0, "items": []})
        b["sales"] += float(r["sales"]) if pd.notna(r["sales"]) else 0.0
        b["qty"] += float(r["qty"]) if pd.notna(r["qty"]) else 0.0
        b["items"].append(dict(
            name=r["item"], qty=float(r["qty"]) if pd.notna(r["qty"]) else 0.0,
            sales=float(r["sales"]) if pd.notna(r["sales"]) else 0.0,
            avg_price=None if pd.isna(r["avg_price"]) else float(r["avg_price"]),
            contribution_pct=float(r["contribution_pct"]) if pd.notna(r["contribution_pct"]) else 0.0,
            growth_pct=None if pd.isna(r["growth_pct_last3_vs_prev3"]) else float(r["growth_pct_last3_vs_prev3"]),
        ))
    tree_list = sorted(
        [dict(customer_code=k, **v) for k, v in tree.items()],
        key=lambda x: -x["sales"])
    data["hierarchy_tree"] = tree_list

    # carton capacity reference table (from dim_items, only rows with known capacity)
    carton_ref = dim_items[dim_items["carton_capacity"].notna() & (dim_items["carton_capacity"] != "")].copy()
    carton_ref["carton_units"] = carton_ref["carton_capacity"].str.extract(r"(\d+)").astype(float)
    carton_ref["implied_monthly_cartons"] = (carton_ref["total_qty"] / 18) / carton_ref["carton_units"]
    data["carton_reference"] = json.loads(
        carton_ref[["item_name", "brand", "carton_capacity", "carton_units", "total_qty",
                     "implied_monthly_cartons"]].to_json(orient="records"))

    # monthly revenue series for the top 10 items (for price/trend small multiples)
    tx = pd.read_csv(P / "sales_transactions_enriched.csv", dtype={"customer_code": str})
    tx["invoice_date_parsed"] = pd.to_datetime(tx["invoice_date"], format="%Y/%m/%d")
    tx["month"] = tx["invoice_date_parsed"].dt.to_period("M").astype(str)
    top_items = tx.groupby("item_name_canonical")["line_total"].sum().sort_values(ascending=False).head(10).index
    item_month = {}
    for item in top_items:
        sub = tx[tx["item_name_canonical"] == item]
        g = sub.groupby("month").apply(lambda d: pd.Series({
            "revenue": d["line_total"].sum(), "qty": d["qty"].sum(),
            "asp": (d["line_total"].sum() / d["qty"].sum()) if d["qty"].sum() else None,
        })).reset_index()
        item_month[item] = json.loads(g.to_json(orient="records"))
    data["item_month_series"] = item_month

    data = clean(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DASH_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
