"""
Exploratory Data Analysis on the reconciled ABOHASHEM invoice dataset.
Everything here is computed straight from invoice_lines_merged.csv /
invoices_header_merged.csv (+ item_master.csv for brand). Writes result
tables to data/eda/*.csv for reuse by dashboards and the written reports.
"""
import pandas as pd
import numpy as np
from pathlib import Path

OUT = Path("data/eda")
OUT.mkdir(parents=True, exist_ok=True)


def load():
    h = pd.read_csv("data/invoices_header_merged.csv", dtype={"customer_code": str})
    l = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    im = pd.read_csv("data/item_master.csv", dtype={"item_code": str})
    h["date"] = pd.to_datetime(h["date"], format="%Y/%m/%d")
    l = l.merge(h[["invoice_id", "date", "customer_code", "customer_name"]], on="invoice_id", how="left")
    l = l.merge(im[["item_code", "item_name", "brand"]], on="item_code", how="left")
    l["month"] = l["date"].dt.to_period("M").astype(str)
    return h, l, im


def descriptive_stats(h, l):
    stats = {
        "invoices": len(h),
        "line_items": len(l),
        "customers": h["customer_code"].nunique(),
        "brands": l["brand"].nunique(),
        "items": l["item_code"].nunique(),
        "total_revenue": h["invoice_total"].sum(),
        "total_qty": l["qty"].sum(),
        "avg_invoice_value": h["invoice_total"].mean(),
        "median_invoice_value": h["invoice_total"].median(),
        "std_invoice_value": h["invoice_total"].std(),
        "avg_selling_price_overall": h["invoice_total"].sum() / l["qty"].sum(),
    }
    pd.Series(stats).to_csv(OUT / "descriptive_stats.csv", header=["value"])
    return stats


def monthly_sales(h):
    m = h.copy()
    m["month"] = m["date"].dt.to_period("M").astype(str)
    agg = m.groupby("month").agg(
        revenue=("invoice_total", "sum"),
        invoices=("invoice_id", "count"),
        avg_invoice_value=("invoice_total", "mean"),
    ).reset_index()
    agg["mom_growth_pct"] = agg["revenue"].pct_change().mul(100).round(2)
    agg["yoy_growth_pct"] = agg["revenue"].pct_change(12).mul(100).round(2)
    agg.to_csv(OUT / "monthly_sales.csv", index=False, encoding="utf-8-sig")
    return agg


def customer_analysis(h):
    g = h.groupby("customer_code").agg(
        canonical_name=("customer_name", lambda x: x.value_counts().index[0]),
        revenue=("invoice_total", "sum"),
        invoices=("invoice_id", "count"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    ).reset_index()
    g = g.sort_values("revenue", ascending=False)
    g["contribution_pct"] = (g["revenue"] / g["revenue"].sum() * 100).round(3)
    g["cum_contribution_pct"] = g["contribution_pct"].cumsum().round(3)
    g["rank"] = range(1, len(g) + 1)
    g.to_csv(OUT / "customer_ranking.csv", index=False, encoding="utf-8-sig")
    return g


def brand_analysis(l):
    g = l.groupby("brand").agg(
        revenue=("line_total", "sum"),
        qty=("qty", "sum"),
    ).reset_index().sort_values("revenue", ascending=False)
    g["asp"] = g["revenue"] / g["qty"]
    g["contribution_pct"] = (g["revenue"] / g["revenue"].sum() * 100).round(2)
    g.to_csv(OUT / "brand_ranking.csv", index=False, encoding="utf-8-sig")

    # brand monthly for seasonality/growth
    bm = l.groupby(["month", "brand"])["line_total"].sum().reset_index()
    bm.to_csv(OUT / "brand_monthly.csv", index=False, encoding="utf-8-sig")
    return g


def item_analysis(l):
    g = l.groupby(["item_code", "item_name", "brand"]).agg(
        revenue=("line_total", "sum"),
        qty=("qty", "sum"),
        n_invoices=("invoice_id", "nunique"),
    ).reset_index().sort_values("revenue", ascending=False)
    g["asp"] = g["revenue"] / g["qty"]
    g["contribution_pct"] = (g["revenue"] / g["revenue"].sum() * 100).round(3)
    g["cum_contribution_pct"] = g["contribution_pct"].cumsum().round(3)
    g["rank"] = range(1, len(g) + 1)

    # ABC classification on revenue contribution
    def abc(c):
        if c <= 80:
            return "A"
        elif c <= 95:
            return "B"
        else:
            return "C"
    g["abc_class"] = g["cum_contribution_pct"].apply(abc)

    # XYZ classification on demand variability (CoV of monthly qty)
    im_month = l.groupby(["item_code", "month"])["qty"].sum().reset_index()
    cov = im_month.groupby("item_code")["qty"].agg(["mean", "std"]).reset_index()
    cov["cov"] = cov["std"] / cov["mean"]

    def xyz(c):
        if pd.isna(c):
            return "Z"
        elif c <= 0.5:
            return "X"
        elif c <= 1.0:
            return "Y"
        else:
            return "Z"
    cov["xyz_class"] = cov["cov"].apply(xyz)
    g = g.merge(cov[["item_code", "cov", "xyz_class"]], on="item_code", how="left")

    g.to_csv(OUT / "item_ranking_abc_xyz.csv", index=False, encoding="utf-8-sig")
    return g


def pareto_concentration(customer_rank, item_rank):
    def summarize(df, label):
        n80 = (df["cum_contribution_pct"] <= 80).sum() + 1
        pct_of_total = round(100 * n80 / len(df), 2)
        return {"segment": label, "n_total": len(df), "n_to_reach_80pct_revenue": int(n80),
                "pct_of_population_driving_80pct_revenue": pct_of_total}
    rows = [summarize(customer_rank, "customers"), summarize(item_rank, "items")]
    pd.DataFrame(rows).to_csv(OUT / "pareto_summary.csv", index=False, encoding="utf-8-sig")


def price_trends(l):
    pt = l.groupby(["month", "item_code", "item_name"]).apply(
        lambda d: pd.Series({"asp": d["line_total"].sum() / d["qty"].sum() if d["qty"].sum() else np.nan})
    ).reset_index()
    pt.to_csv(OUT / "price_trends.csv", index=False, encoding="utf-8-sig")


def concentration_risk(customer_rank, brand_rank):
    def hhi(shares_pct):
        s = shares_pct / 100
        return float((s ** 2).sum() * 10000)  # HHI on 0-10000 scale
    out = {
        "customer_hhi": hhi(customer_rank["contribution_pct"]),
        "brand_hhi": hhi(brand_rank["contribution_pct"]),
        "top1_customer_share_pct": float(customer_rank["contribution_pct"].iloc[0]),
        "top5_customer_share_pct": float(customer_rank["contribution_pct"].iloc[:5].sum()),
        "top10_customer_share_pct": float(customer_rank["contribution_pct"].iloc[:10].sum()),
    }
    pd.Series(out).to_csv(OUT / "concentration_risk.csv", header=["value"])
    return out


def main():
    h, l, im = load()
    stats = descriptive_stats(h, l)
    monthly = monthly_sales(h)
    cust = customer_analysis(h)
    brand = brand_analysis(l)
    item = item_analysis(l)
    pareto_concentration(cust, item)
    price_trends(l)
    conc = concentration_risk(cust, brand)

    print("descriptive stats:", stats)
    print("\nmonthly sales (last 6):")
    print(monthly.tail(6))
    print("\ntop 10 customers:")
    print(cust.head(10)[["canonical_name", "revenue", "contribution_pct"]])
    print("\nbrand ranking:")
    print(brand)
    print("\nconcentration risk:", conc)
    print("\nABC distribution:")
    print(item["abc_class"].value_counts())
    print("\nXYZ distribution:")
    print(item["xyz_class"].value_counts())


if __name__ == "__main__":
    main()
