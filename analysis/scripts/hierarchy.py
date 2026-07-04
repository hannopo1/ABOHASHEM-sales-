"""
Build the Customer -> Brand -> Item hierarchical sales tree with qty, sales,
unit price, growth% (H1 2026 vs H2 2025, the two comparable half-year windows
available) and contribution% at every level. Written as nested JSON for the
drill-down dashboard plus flat CSVs per level.
"""
import json
import pandas as pd
from pathlib import Path

OUT = Path("data/eda")


def half_year_growth(l, key_cols):
    l = l.copy()
    l["half"] = l["date"].dt.year.astype(str) + "-H" + ((l["date"].dt.month > 6) + 1).astype(str)
    halves = sorted(l["half"].unique())
    if len(halves) < 2:
        return pd.DataFrame(columns=key_cols + ["growth_pct"])
    prev_h, last_h = halves[-2], halves[-1]
    import numpy as np
    g = l.groupby(key_cols + ["half"])["line_total"].sum().unstack("half").fillna(0)
    denom = g[prev_h].replace(0, np.nan)
    pct = (g[last_h] - g[prev_h]) / denom * 100
    g["growth_pct"] = pct.replace([np.inf, -np.inf], np.nan).astype(float).round(2)
    return g[["growth_pct"]].reset_index()


def main():
    h = pd.read_csv("data/invoices_header_merged.csv", dtype={"customer_code": str})
    l = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    im = pd.read_csv("data/item_master.csv", dtype={"item_code": str})
    h["date"] = pd.to_datetime(h["date"], format="%Y/%m/%d")
    l = l.merge(h[["invoice_id", "date", "customer_code", "customer_name"]], on="invoice_id", how="left")
    l = l.merge(im[["item_code", "item_name", "brand"]], on="item_code", how="left")

    canonical = (h.groupby("customer_code")["customer_name"]
                 .agg(lambda x: x.value_counts().index[0]).rename("canonical_name"))
    l = l.merge(canonical, on="customer_code", how="left")

    total_revenue = l["line_total"].sum()

    cust_growth = half_year_growth(l, ["customer_code"])
    brand_growth = half_year_growth(l, ["customer_code", "brand"])
    item_growth = half_year_growth(l, ["customer_code", "brand", "item_code"])

    tree = []
    cust_agg = l.groupby(["customer_code", "canonical_name"]).agg(
        qty=("qty", "sum"), sales=("line_total", "sum")
    ).reset_index().sort_values("sales", ascending=False)

    for _, crow in cust_agg.iterrows():
        code, cname, cqty, csales = crow["customer_code"], crow["canonical_name"], crow["qty"], crow["sales"]
        cg = cust_growth[cust_growth.customer_code == code]["growth_pct"]
        cust_node = {
            "customer_code": code, "customer_name": cname,
            "qty": round(float(cqty), 2), "sales": round(float(csales), 2),
            "avg_price": round(float(csales / cqty), 2) if cqty else None,
            "contribution_pct": round(float(csales / total_revenue * 100), 4),
            "growth_pct_h2h": float(cg.iloc[0]) if len(cg) and pd.notna(cg.iloc[0]) else None,
            "brands": [],
        }
        sub = l[l["customer_code"] == code]
        brand_agg = sub.groupby("brand").agg(qty=("qty", "sum"), sales=("line_total", "sum")).reset_index().sort_values("sales", ascending=False)
        for _, brow in brand_agg.iterrows():
            bname, bqty, bsales = brow["brand"], brow["qty"], brow["sales"]
            bg = brand_growth[(brand_growth.customer_code == code) & (brand_growth.brand == bname)]["growth_pct"]
            brand_node = {
                "brand": bname, "qty": round(float(bqty), 2), "sales": round(float(bsales), 2),
                "avg_price": round(float(bsales / bqty), 2) if bqty else None,
                "contribution_pct_of_customer": round(float(bsales / csales * 100), 2) if csales else None,
                "growth_pct_h2h": float(bg.iloc[0]) if len(bg) and pd.notna(bg.iloc[0]) else None,
                "items": [],
            }
            sub_b = sub[sub["brand"] == bname]
            item_agg = sub_b.groupby(["item_code", "item_name"]).agg(qty=("qty", "sum"), sales=("line_total", "sum")).reset_index().sort_values("sales", ascending=False)
            for _, irow in item_agg.iterrows():
                icode, iname, iqty, isales = irow["item_code"], irow["item_name"], irow["qty"], irow["sales"]
                ig = item_growth[(item_growth.customer_code == code) & (item_growth.brand == bname) & (item_growth.item_code == icode)]["growth_pct"]
                brand_node["items"].append({
                    "item_code": icode, "item_name": iname,
                    "qty": round(float(iqty), 2), "sales": round(float(isales), 2),
                    "avg_price": round(float(isales / iqty), 2) if iqty else None,
                    "contribution_pct_of_brand": round(float(isales / bsales * 100), 2) if bsales else None,
                    "growth_pct_h2h": float(ig.iloc[0]) if len(ig) and pd.notna(ig.iloc[0]) else None,
                })
            cust_node["brands"].append(brand_node)
        tree.append(cust_node)

    with open(OUT / "hierarchy_tree.json", "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=1)

    print(f"customers in tree: {len(tree)}; total_revenue check: {total_revenue:,.2f}")
    print("sample (top customer):")
    print(json.dumps(tree[0], ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main()
