"""
Per-customer analysis + configurable collection-based bonus.

June is a credit-sales month (near-zero paid-at-issue), so a customer's
collection performance is measured on the AR snapshot: how much of everything
they have ever been billed has been collected. That rate drives the bonus ladder
defined in ``config.BONUS_RULES``.
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from . import config as C


def _oldest_unpaid(inv_df: pl.DataFrame) -> dict:
    """Oldest June invoice still carrying a remaining balance, with an approximate
    due date (invoice date + assumed net terms) and days overdue as of snapshot."""
    unpaid = inv_df.filter(
        (pl.col("remaining").is_not_null()) & (pl.col("remaining") > 0)
        & (pl.col("reported_total") > 0)
    ).sort("invoice_date")
    if unpaid.height == 0:
        return {}
    row = unpaid.row(0, named=True)
    inv_date: date = row["invoice_date"]
    due = inv_date + timedelta(days=C.NET_TERMS_DAYS)
    as_of = date.fromisoformat(C.AS_OF_DATE)
    days_overdue = max(0, (as_of - due).days)
    return {
        "oldest_invoice_no": row["invoice_no"],
        "oldest_invoice_date": inv_date.isoformat(),
        "oldest_due_date": due.isoformat(),
        "oldest_days_overdue": days_overdue,
        "oldest_amount": round(float(row["remaining"]), 2),
    }


def compute(lines: pl.DataFrame, invoices: pl.DataFrame,
            dim_customers: pl.DataFrame) -> list[dict]:
    dc = dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8)).select(
        pl.col("customer_code"),
        pl.col("total_revenue").cast(pl.Float64, strict=False).alias("total_billed"),
        pl.col("ar_net_balance").cast(pl.Float64, strict=False).alias("outstanding"),
        pl.col("rep").fill_null("غير محدد"),
        pl.col("city").fill_null(""),
        pl.col("has_ar_snapshot").cast(pl.Utf8).alias("has_ar"),
    )

    # June per-customer line aggregates
    line_agg = (
        lines.group_by("customer_code").agg([
            pl.col("qty").sum().alias("units"),
            pl.col("boxes").sum().alias("boxes"),
            pl.col("item_code").n_unique().alias("n_items"),
        ])
    )
    inv_agg = (
        invoices.group_by("customer_code").agg([
            pl.first("customer_name").alias("customer_name"),
            pl.col("reported_total").sum().alias("sales"),
            pl.col("paid").sum().alias("collections"),
            pl.col("invoice_no").n_unique().alias("n_invoices"),
        ])
    )

    base = (
        inv_agg.join(line_agg, on="customer_code", how="left")
        .join(dc, on="customer_code", how="left")
    )

    rows: list[dict] = []
    for r in base.iter_rows(named=True):
        code = r["customer_code"]
        sales = float(r["sales"] or 0.0)
        billed = float(r["total_billed"] or sales)
        has_ar = str(r.get("has_ar")).lower() in ("true", "1")
        outstanding = float(r["outstanding"] or 0.0) if has_ar else None

        if has_ar and billed > 0:
            rate = max(0.0, min(1.0, (billed - (outstanding or 0.0)) / billed))
            b_pct = C.bonus_pct(rate)
        else:
            rate = None
            b_pct = 0.0

        rec = {
            "customer_code": code,
            "customer_name": r["customer_name"],
            "rep": r["rep"] or "غير محدد",
            "city": r["city"] or "",
            "sales": round(sales, 2),
            "collections": round(float(r["collections"] or 0.0), 2),
            "n_invoices": int(r["n_invoices"] or 0),
            "n_items": int(r["n_items"] or 0),
            "units": round(float(r["units"] or 0.0), 2),
            "boxes": round(float(r["boxes"] or 0.0), 2),
            "avg_invoice_value": round(sales / r["n_invoices"], 2) if r["n_invoices"] else 0.0,
            "total_billed": round(billed, 2),
            "outstanding": round(outstanding, 2) if outstanding is not None else None,
            "collection_rate": round(rate, 4) if rate is not None else None,
            "bonus_pct": b_pct,
            "bonus_value": round(sales * b_pct, 2),
            "has_ar": has_ar,
        }
        rec.update(_oldest_unpaid(invoices.filter(pl.col("customer_code") == code)))
        rows.append(rec)

    rows.sort(key=lambda x: x["sales"], reverse=True)
    for i, rec in enumerate(rows, 1):
        rec["rank"] = i
    return rows
