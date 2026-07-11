"""
Data loading for the June-2026 Executive Dashboard.

Two responsibilities:
  1. Re-parse the June source markdown (``فواتير_المبيعات_يونيو_2026-1.md``) into a
     clean, self-contained line-item + invoice-header dataset — including the
     ``المدفوع`` (paid) / ``الباقي`` (remaining) footer fields the base pipeline
     does not persist but which we need for real collection figures.
  2. Load the already-processed dimension / AR files (regeneratable from source)
     used for brand, carton capacity, salesperson and the receivables snapshot.

All tabular results are returned as Polars frames so downstream aggregation
scales to well beyond the current 800 June line-items (the same code path would
handle 1M+ rows unchanged).
"""
from __future__ import annotations

import re
from datetime import date

import polars as pl

from . import config as C

# --- regex lifted/extended from analysis/01_parse_invoices.py -----------------
_INV_SPLIT = re.compile(r"\n## فاتورة ")
_HEADER = re.compile(r"(\S+)\s+—.*?—\s+(\d{4}/\d{1,2}/\d{1,2})(?:\s+([\d:]+\s*[AP]M))?")
_CODE = re.compile(r"الكود:\s*(\S+)")
_NAME = re.compile(r"العميل:\s*([^|]+?)\s*(?:\||$)")
_ADDR = re.compile(r"العنوان:\s*([^|]+?)\s*(?:\||$)")
_PHONE = re.compile(r"(01\d{9})")
_TOTAL = re.compile(r"إجمالى الفاتورة:\s*\*\*(-?[\d.,]+)\*\*")
_REMAIN = re.compile(r"الباقي:\s*(-?[\d.,]+)")
_PAID = re.compile(r"المدفوع:\s*(-?[\d.,]+)")
_QTY = re.compile(r"عدد كميات الفاتورة:\s*(-?[\d.,]+)")
_ROW = re.compile(r"^\|\s*\d+\s*\|.*\|$", re.M)


def _num(s: str | None):
    if s is None:
        return None
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("/"))
    return date(y, m, d)


def parse_june() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Parse the June markdown. Returns (lines_df, invoices_df)."""
    text = C.SRC_JUNE_MD.read_text(encoding="utf-8")
    blocks = _INV_SPLIT.split(text)[1:]

    lines: list[dict] = []
    invoices: list[dict] = []
    for block in blocks:
        header_line, _, rest = block.partition("\n")
        hm = _HEADER.match(header_line)
        if not hm:
            continue
        invoice_no = hm.group(1)
        inv_date = _to_date(hm.group(2))
        inv_time = (hm.group(3) or "").strip()

        meta = rest.split("\n", 1)[0]
        code_m, name_m = _CODE.search(meta), _NAME.search(meta)
        addr_m, phone_m = _ADDR.search(meta), _PHONE.search(meta)
        cust_code = code_m.group(1) if code_m else ""
        cust_name = name_m.group(1).strip() if name_m else ""
        address = addr_m.group(1).strip() if addr_m else ""
        phone = phone_m.group(1) if phone_m else ""

        total = _num(_TOTAL.search(block).group(1)) if _TOTAL.search(block) else None
        remaining = _num(_REMAIN.search(block).group(1)) if _REMAIN.search(block) else None
        paid = _num(_PAID.search(block).group(1)) if _PAID.search(block) else None
        qty_total = _num(_QTY.search(block).group(1)) if _QTY.search(block) else None
        is_bonus = "بونص" in block

        n_lines = 0
        line_sum = 0.0
        for tr in _ROW.findall(block):
            cells = [c.strip() for c in tr.strip("|").split("|")]
            if len(cells) != 9:
                continue
            seq, item_code, item_name, unit, qty, price, tax_pct, disc_pct, ltot = cells
            qn, pn, txn, dsn, ltn = (_num(x) for x in (qty, price, tax_pct, disc_pct, ltot))
            lines.append(dict(
                invoice_no=invoice_no, invoice_date=inv_date, invoice_time=inv_time,
                customer_code=cust_code, customer_name=cust_name, phone=phone,
                address=address, seq=_num(seq), item_code=item_code,
                item_name=item_name, unit=unit, qty=qn, unit_price=pn,
                tax_pct=txn, discount_pct=dsn, line_total=ltn, is_bonus=is_bonus,
            ))
            n_lines += 1
            line_sum += ltn or 0.0

        invoices.append(dict(
            invoice_no=invoice_no, invoice_date=inv_date, invoice_time=inv_time,
            customer_code=cust_code, customer_name=cust_name, phone=phone,
            address=address, reported_total=total, line_total_sum=round(line_sum, 2),
            remaining=remaining, paid=paid, qty_total=qty_total,
            is_bonus=is_bonus, n_lines=n_lines,
        ))

    lines_df = pl.DataFrame(lines)
    invoices_df = pl.DataFrame(invoices)
    return lines_df, invoices_df


def load_dimensions() -> dict[str, pl.DataFrame]:
    """Load reused processed dimension / AR files as Polars frames."""
    dim_items = pl.read_csv(C.F_DIM_ITEMS, infer_schema_length=2000)
    # carton_units = leading integer of the capacity string (e.g. "12 كيس" -> 12)
    dim_items = dim_items.with_columns(
        pl.col("carton_capacity").cast(pl.Utf8)
        .str.extract(r"(\d+)", 1).cast(pl.Float64).alias("carton_units")
    )

    dim_customers = pl.read_csv(C.F_DIM_CUSTOMERS, infer_schema_length=2000)
    debt_detail = pl.read_csv(C.F_DEBT_DETAIL, infer_schema_length=2000)
    rep_summary = pl.read_csv(C.F_REP_SUMMARY, infer_schema_length=2000)
    ar_balances = pl.read_csv(C.F_AR_BALANCES, infer_schema_length=2000)

    return dict(
        dim_items=dim_items,
        dim_customers=dim_customers,
        debt_detail=debt_detail,
        rep_summary=rep_summary,
        ar_balances=ar_balances,
    )


def load_history_monthly() -> pl.DataFrame:
    """Monthly net-sales series across the full 17-month history for trend/variance."""
    # All columns as strings (customer codes appear comma-quoted, e.g. "1,003");
    # cast only the numerics we aggregate.
    df = pl.read_csv(C.F_SALES_ALL, infer_schema_length=0)
    df = df.with_columns([
        pl.col("line_total").cast(pl.Float64, strict=False),
        pl.col("qty").cast(pl.Float64, strict=False),
        # "2026/6/2" -> "2026-06"
        pl.col("invoice_date").map_elements(
            lambda s: f"{s.split('/')[0]}-{s.split('/')[1].zfill(2)}",
            return_dtype=pl.Utf8,
        ).alias("month"),
    ])
    monthly = (
        df.group_by("month")
        .agg([
            pl.col("line_total").sum().alias("net_sales"),
            pl.col("invoice_no").n_unique().alias("invoices"),
            pl.col("customer_code").n_unique().alias("customers"),
            pl.col("qty").sum().alias("qty"),
        ])
        .sort("month")
    )
    return monthly


def enrich_lines(lines_df: pl.DataFrame, dim_items: pl.DataFrame) -> pl.DataFrame:
    """Attach brand + carton capacity, derive boxes per line, net line value."""
    items = dim_items.select(
        pl.col("item_code").cast(pl.Utf8),
        pl.col("brand"),
        pl.col("carton_capacity"),
        pl.col("carton_units"),
    )
    out = lines_df.with_columns(pl.col("item_code").cast(pl.Utf8)).join(
        items, on="item_code", how="left"
    )
    out = out.with_columns([
        pl.col("brand").fill_null("غير مصنّف"),
        pl.when(pl.col("carton_units").is_not_null() & (pl.col("carton_units") > 0))
        .then(pl.col("qty") / pl.col("carton_units"))
        .otherwise(None).alias("boxes"),
    ])
    return out
