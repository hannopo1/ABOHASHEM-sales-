#!/usr/bin/env python3
"""Exploratory Data Analysis: descriptive stats, monthly trend, customer/brand/
item analysis, Pareto 80/20, ABC/XYZ classification, growth rates, hierarchy."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
OUT_DIR = ROOT / "data" / "processed"


def load():
    df = pd.read_csv(TX, dtype={"customer_code": str, "invoice_no": str})
    df["invoice_date_parsed"] = pd.to_datetime(df["invoice_date"], format="%Y/%m/%d")
    df["month"] = df["invoice_date_parsed"].dt.to_period("M").astype(str)
    return df


def monthly_series(df):
    m = df.groupby("month").agg(
        revenue=("line_total", "sum"), qty=("qty", "sum"),
        n_invoices=("invoice_no", "nunique"), n_customers=("customer_code", "nunique"),
        avg_selling_price=("unit_price", lambda s: np.average(s, weights=df.loc[s.index, "qty"].clip(lower=0))
                            if s.notna().any() else np.nan),
    ).reset_index().sort_values("month")
    m["mom_growth_pct"] = m["revenue"].pct_change() * 100
    m["yoy_growth_pct"] = m["revenue"].pct_change(12) * 100
    m["revenue_per_invoice"] = m["revenue"] / m["n_invoices"]
    return m


def pareto_abc(df, key):
    g = df.groupby(key)["line_total"].sum().sort_values(ascending=False).reset_index()
    g["cum_revenue"] = g["line_total"].cumsum()
    total = g["line_total"].sum()
    g["cum_pct"] = g["cum_revenue"] / total * 100
    g["rank"] = np.arange(1, len(g) + 1)
    g["rank_pct"] = g["rank"] / len(g) * 100

    def abc(cum_pct):
        if cum_pct <= 80:
            return "A"
        elif cum_pct <= 95:
            return "B"
        return "C"
    g["abc_class"] = g["cum_pct"].apply(abc)
    return g


def xyz_classification(df, key):
    """Coefficient of variation of monthly demand (quantity) per key -> XYZ."""
    piv = df.groupby([key, "month"])["qty"].sum().unstack(fill_value=0)
    cv = (piv.std(axis=1) / piv.mean(axis=1).replace(0, np.nan)).rename("cv_qty")

    def xyz(cv_val):
        if pd.isna(cv_val):
            return "Z"
        if cv_val <= 0.5:
            return "X"
        elif cv_val <= 1.0:
            return "Y"
        return "Z"
    out = cv.reset_index()
    out["xyz_class"] = out["cv_qty"].apply(xyz)
    return out


def hierarchy_tree(df):
    """Customer -> Brand -> Item hierarchy with qty, sales, avg price, contribution."""
    total_rev = df["line_total"].sum()
    rows = []
    for (cust, brand, item), sub in df.groupby(["customer_code", "brand", "item_name_canonical"]):
        rev = sub["line_total"].sum()
        qty = sub["qty"].sum()
        rows.append(dict(
            customer_code=cust, brand=brand, item=item,
            qty=qty, sales=rev, avg_price=(rev / qty if qty else np.nan),
            contribution_pct=rev / total_rev * 100,
        ))
    leaf = pd.DataFrame(rows)

    # growth: compare last 3 months vs prior 3 months at leaf level
    df["month"] = df["invoice_date_parsed"].dt.to_period("M").astype(str)
    months_sorted = sorted(df["month"].unique())
    last3, prev3 = months_sorted[-3:], months_sorted[-6:-3]
    g_last = df[df["month"].isin(last3)].groupby(["customer_code", "brand", "item_name_canonical"])["line_total"].sum()
    g_prev = df[df["month"].isin(prev3)].groupby(["customer_code", "brand", "item_name_canonical"])["line_total"].sum()
    growth = ((g_last - g_prev) / g_prev.replace(0, np.nan) * 100).rename("growth_pct_last3_vs_prev3").reset_index()
    growth.columns = ["customer_code", "brand", "item", "growth_pct_last3_vs_prev3"]
    leaf = leaf.merge(growth, on=["customer_code", "brand", "item"], how="left")
    return leaf


def main():
    df = load()

    # 1. descriptive stats
    desc = df[["qty", "unit_price", "discount_pct", "tax_pct", "line_total"]].describe().to_dict()

    # 2. monthly series
    m = monthly_series(df)
    m.to_csv(OUT_DIR / "eda_monthly_series.csv", index=False)

    # 3. customer analysis
    cust_pareto = pareto_abc(df, "customer_code")
    name_map = df.groupby("customer_code")["customer_name_raw"].agg(lambda s: s.value_counts().index[0])
    cust_pareto["customer_name"] = cust_pareto["customer_code"].map(name_map)
    cust_pareto.to_csv(OUT_DIR / "eda_customer_pareto_abc.csv", index=False)
    n_a_customers = int((cust_pareto["abc_class"] == "A").sum())
    top10_share = float(cust_pareto.head(10)["line_total"].sum() / cust_pareto["line_total"].sum() * 100)
    hhi_customers = float(((cust_pareto["line_total"] / cust_pareto["line_total"].sum()) ** 2).sum() * 10000)

    # 4. brand analysis
    brand_g = df.groupby("brand").agg(revenue=("line_total", "sum"), qty=("qty", "sum"),
                                       n_customers=("customer_code", "nunique")).reset_index()
    brand_g["revenue_share_pct"] = brand_g["revenue"] / brand_g["revenue"].sum() * 100
    brand_g = brand_g.sort_values("revenue", ascending=False)
    brand_g.to_csv(OUT_DIR / "eda_brand_summary.csv", index=False)
    hhi_brands = float(((brand_g["revenue"] / brand_g["revenue"].sum()) ** 2).sum() * 10000)

    # 5. item analysis + ABC + XYZ
    item_pareto = pareto_abc(df, "item_name_canonical")
    item_xyz = xyz_classification(df, "item_name_canonical")
    item_full = item_pareto.merge(item_xyz[["item_name_canonical", "cv_qty", "xyz_class"]],
                                   on="item_name_canonical", how="left")
    brand_map = df.groupby("item_name_canonical")["brand"].agg(lambda s: s.value_counts().index[0])
    item_full["brand"] = item_full["item_name_canonical"].map(brand_map)
    item_full.to_csv(OUT_DIR / "eda_item_abc_xyz.csv", index=False)
    hhi_items = float(((item_pareto["line_total"] / item_pareto["line_total"].sum()) ** 2).sum() * 10000)

    # customer XYZ too (demand stability)
    cust_xyz = xyz_classification(df, "customer_code")
    cust_full = cust_pareto.merge(cust_xyz[["customer_code", "cv_qty", "xyz_class"]], on="customer_code", how="left")
    cust_full.to_csv(OUT_DIR / "eda_customer_pareto_abc.csv", index=False)

    # 6. average selling price trend per brand per month
    asp = df[df["qty"] > 0].groupby(["month", "brand"]).apply(
        lambda g: pd.Series({"avg_selling_price": g["line_total"].sum() / g["qty"].sum()})
    ).reset_index()
    asp.to_csv(OUT_DIR / "eda_asp_by_brand_month.csv", index=False)

    # 7. hierarchy
    hier = hierarchy_tree(df)
    hier.to_csv(OUT_DIR / "eda_hierarchy_customer_brand_item.csv", index=False)

    # 8. seasonality: average revenue by calendar month-of-year, averaged across
    # the years actually observed for that month (2025 has all 12 months incl.
    # Ramadan in Mar; 2026 only has Jan-Jun so far -> must average, not sum, or
    # H1 months would be structurally inflated by having 2 observations vs 1).
    df["month_num"] = df["invoice_date_parsed"].dt.month
    df["year"] = df["invoice_date_parsed"].dt.year
    by_year_month = df.groupby(["year", "month_num"])["line_total"].sum().reset_index()
    seasonality = by_year_month.groupby("month_num")["line_total"].mean().reindex(range(1, 13))
    seasonality_idx = (seasonality / seasonality.mean() * 100).round(1)
    n_years_per_month = by_year_month.groupby("month_num")["year"].nunique().reindex(range(1, 13), fill_value=0)

    summary = dict(
        total_revenue=float(df["line_total"].sum()),
        total_qty=float(df["qty"].sum()),
        n_customers=int(df["customer_code"].nunique()),
        n_brands=int(df["brand"].nunique()),
        n_items=int(df["item_name_canonical"].nunique()),
        n_months=int(df["month"].nunique()),
        avg_monthly_revenue=float(m["revenue"].mean()),
        std_monthly_revenue=float(m["revenue"].std()),
        cv_monthly_revenue=float(m["revenue"].std() / m["revenue"].mean()),
        n_a_class_customers=n_a_customers,
        top10_customers_revenue_share_pct=round(top10_share, 2),
        hhi_customers=round(hhi_customers, 1),
        hhi_brands=round(hhi_brands, 1),
        hhi_items=round(hhi_items, 1),
        abc_customer_counts=cust_full["abc_class"].value_counts().to_dict(),
        abc_item_counts=item_full["abc_class"].value_counts().to_dict(),
        xyz_item_counts=item_full["xyz_class"].value_counts().to_dict(),
        xyz_customer_counts=cust_full["xyz_class"].value_counts().to_dict(),
        seasonality_index_by_month=seasonality_idx.to_dict(),
        seasonality_n_years_observed_by_month=n_years_per_month.to_dict(),
        brand_revenue_share=brand_g.set_index("brand")["revenue_share_pct"].round(2).to_dict(),
    )
    with open(OUT_DIR / "eda_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
