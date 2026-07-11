"""
Data-quality scan for the June-2026 dataset.

Detects — but never silently drops — the issues the brief asks for: missing
values, duplicate invoices, zero-value invoices, and abnormal prices/quantities.
Returns a compact summary plus the offending records so the dashboard can show
them in a table.
"""
from __future__ import annotations

import polars as pl

from . import config as C


def run(lines: pl.DataFrame, invoices: pl.DataFrame) -> dict:
    n_lines = lines.height
    n_invoices = invoices.height

    # --- missing values (per key field) -----------------------------------
    missing = {}
    for col in ["customer_code", "customer_name", "item_code", "item_name",
                "qty", "unit_price", "line_total"]:
        missing[col] = int(
            lines.select(
                (pl.col(col).is_null() | (pl.col(col).cast(pl.Utf8).str.strip_chars() == "")).sum()
            ).item()
        )

    # --- duplicate invoice numbers ----------------------------------------
    dup = (
        invoices.group_by("invoice_no").len()
        .filter(pl.col("len") > 1).sort("len", descending=True)
    )
    duplicate_invoices = dup["invoice_no"].to_list()

    # --- zero-value invoices (reported total == 0) ------------------------
    zero_inv = invoices.filter(
        (pl.col("reported_total").is_null()) | (pl.col("reported_total") == 0)
    )

    # --- abnormal prices / quantities -------------------------------------
    abn_price = lines.filter(pl.col("unit_price") > C.PRICE_ABNORMAL_MAX)
    abn_qty = lines.filter(pl.col("qty") > C.QTY_ABNORMAL_MAX)
    neg = lines.filter((pl.col("qty") < 0) | (pl.col("unit_price") < 0) | (pl.col("line_total") < 0))

    # --- reconciliation (Σ line_total vs reported total) ------------------
    recon = invoices.with_columns(
        (pl.col("line_total_sum") - pl.col("reported_total")).abs().alias("diff")
    )
    tol = pl.max_horizontal(
        pl.lit(C.RECON_TOL_ABS), (pl.col("reported_total").abs() * C.RECON_TOL_PCT)
    )
    recon_fail = recon.with_columns(tol.alias("tol")).filter(pl.col("diff") > pl.col("tol"))

    summary = {
        "n_line_items": n_lines,
        "n_invoices": n_invoices,
        "missing_values": missing,
        "missing_total": int(sum(missing.values())),
        "duplicate_invoice_count": len(duplicate_invoices),
        "duplicate_invoices": duplicate_invoices,
        "zero_value_invoice_count": zero_inv.height,
        "abnormal_price_count": abn_price.height,
        "abnormal_qty_count": abn_qty.height,
        "negative_value_count": neg.height,
        "reconciliation_pass": n_invoices - recon_fail.height,
        "reconciliation_fail": recon_fail.height,
        "reconciliation_rate": round((n_invoices - recon_fail.height) / max(n_invoices, 1), 4),
    }

    zero_records = zero_inv.select(
        "invoice_no", "invoice_date", "customer_code", "customer_name",
        "qty_total", "reported_total", "is_bonus",
    ).with_columns(pl.col("invoice_date").cast(pl.Utf8)).to_dicts()

    return {"summary": summary, "zero_invoices": zero_records}
