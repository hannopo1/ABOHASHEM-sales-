"""
Per-item (product) analysis for June 2026.

For each item: sales, quantity, boxes, ASP (value-weighted), min/max unit price,
revenue-contribution %, distinct customer count, and a within-month daily trend.
"""
from __future__ import annotations

import polars as pl


def compute(lines: pl.DataFrame) -> list[dict]:
    priced = lines.filter(pl.col("line_total").is_not_null())
    grand_total = float(priced["line_total"].sum()) or 1.0

    agg = (
        lines.group_by("item_code").agg([
            pl.first("item_name").alias("item_name"),
            pl.first("brand").alias("brand"),
            pl.col("line_total").sum().alias("sales"),
            pl.col("qty").sum().alias("qty"),
            pl.col("boxes").sum().alias("boxes"),
            pl.col("customer_code").n_unique().alias("n_customers"),
            pl.col("line_total").count().alias("n_lines"),
            # price stats over priced units only
            pl.col("unit_price").filter(pl.col("unit_price") > 0).max().alias("max_price"),
            pl.col("unit_price").filter(pl.col("unit_price") > 0).min().alias("min_price"),
            pl.col("qty").filter(pl.col("unit_price") > 0).sum().alias("priced_qty"),
            pl.col("line_total").filter(pl.col("unit_price") > 0).sum().alias("priced_val"),
        ])
        .sort("sales", descending=True)
    )

    rows = []
    for i, r in enumerate(agg.iter_rows(named=True), 1):
        pq = float(r["priced_qty"] or 0.0)
        pv = float(r["priced_val"] or 0.0)
        asp = pv / pq if pq else 0.0
        sales = float(r["sales"] or 0.0)
        rows.append({
            "rank": i,
            "item_code": r["item_code"],
            "item_name": r["item_name"],
            "brand": r["brand"],
            "sales": round(sales, 2),
            "qty": round(float(r["qty"] or 0.0), 2),
            "boxes": round(float(r["boxes"] or 0.0), 2) if r["boxes"] is not None else None,
            "asp": round(asp, 2),
            "max_price": round(float(r["max_price"]), 2) if r["max_price"] is not None else None,
            "min_price": round(float(r["min_price"]), 2) if r["min_price"] is not None else None,
            "n_customers": int(r["n_customers"] or 0),
            "n_lines": int(r["n_lines"] or 0),
            "contribution_pct": round(sales / grand_total * 100, 2),
        })
    return rows


def daily_trend_by_item(lines: pl.DataFrame, top_item_codes: list[str]) -> dict:
    """Daily sales series (June) for a handful of top items — for the trend chart."""
    sub = lines.filter(pl.col("item_code").is_in(top_item_codes))
    sub = sub.with_columns(pl.col("invoice_date").cast(pl.Utf8).alias("day"))
    piv = (
        sub.group_by(["item_code", "day"]).agg(pl.col("line_total").sum().alias("v"))
        .sort("day")
    )
    out: dict[str, list] = {}
    for code in top_item_codes:
        s = piv.filter(pl.col("item_code") == code).sort("day")
        out[code] = {"days": s["day"].to_list(), "values": [round(x, 2) for x in s["v"].to_list()]}
    return out
