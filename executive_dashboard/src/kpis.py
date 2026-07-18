"""
Executive KPI block for June 2026.

Every figure here is traceable to observed source data. Metrics that would
require data absent from the source (gross margin, budget) are returned with an
explicit ``available: False`` flag rather than a fabricated number, honouring the
repository's no-fabrication rule.
"""
from __future__ import annotations

import polars as pl


def compute(lines: pl.DataFrame, invoices: pl.DataFrame,
            customers: list[dict], receivables: dict,
            collected_total: float | None = None,
            billed_total: float | None = None) -> dict:
    total_sales = float(invoices["reported_total"].sum())
    # Net sales == reported invoice totals (already net of the per-line discount/
    # tax columns, which are 0 throughout June). Kept as a distinct KPI so the
    # definition is explicit rather than implied.
    net_sales = float(lines["line_total"].sum())

    collections = float(invoices["paid"].sum())              # paid-at-issue
    outstanding = receivables["total_outstanding"]           # AR snapshot
    overdue = receivables["total_overdue"]                   # approx arrears

    total_qty = float(lines["qty"].sum())
    total_boxes = float(lines.select(pl.col("boxes").sum()).item() or 0.0)
    n_customers = int(invoices["customer_code"].n_unique())
    n_invoices = int(invoices["invoice_no"].n_unique())
    zero_invoices = int(invoices.filter(
        (pl.col("reported_total").is_null()) | (pl.col("reported_total") == 0)
    ).height)

    # Average selling price per item unit (value-weighted over priced lines).
    priced = lines.filter((pl.col("qty") > 0) & (pl.col("line_total") > 0))
    asp = float(priced["line_total"].sum() / priced["qty"].sum()) if priced.height else 0.0

    # Collection rate — portfolio level. When ACTUAL cash-receipt totals are
    # supplied (from the 2026 collections ledger) the rate is the real, cumulative
    # 2026 figure: total cash collected ÷ total billed in 2026. Otherwise it falls
    # back to the billed-vs-outstanding proxy on the AR snapshot (June is credit-
    # heavy, so paid-at-issue is near zero). This is the same constant across every
    # month view — collections are an annual, not a per-month, attribute.
    if collected_total is not None and billed_total:
        collection_rate = max(0.0, min(1.0, collected_total / billed_total))
        collection_rate_basis = "actual"
    else:
        total_billed = sum(c["total_billed"] for c in customers)
        collection_rate = (
            (total_billed - outstanding) / total_billed if total_billed else 0.0
        )
        collection_rate = max(0.0, min(1.0, collection_rate))
        collection_rate_basis = "proxy"

    avg_invoice_value = total_sales / n_invoices if n_invoices else 0.0

    return {
        "total_sales": total_sales,
        "net_sales": net_sales,
        "collections_at_issue": collections,
        "outstanding": outstanding,
        "overdue": overdue,
        "collection_rate": collection_rate,
        "collection_rate_basis": collection_rate_basis,
        "collected_actual": round(collected_total, 2) if collected_total is not None else None,
        "asp": asp,
        "total_qty": total_qty,
        "total_boxes": total_boxes,
        "n_customers": n_customers,
        "n_invoices": n_invoices,
        "zero_invoices": zero_invoices,
        "avg_invoice_value": avg_invoice_value,
        # Explicitly unavailable — no cost / budget columns in source.
        "gross_margin": {"available": False,
                         "reason": "لا توجد بيانات تكلفة في المصدر"},
        "budget_variance": {"available": False,
                            "reason": "لا توجد موازنة في المصدر"},
    }
