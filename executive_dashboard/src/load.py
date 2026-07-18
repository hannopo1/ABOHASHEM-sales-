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


# --- main file (2025-01 .. 2026-05, fenced free-text blocks) ------------------
_MAIN_SPLIT = re.compile(r"\n## فاتورة رقم ")
_MAIN_HEADER = re.compile(r"(.+?)\s+—\s+(\d{4}/\d{1,2}/\d{1,2})")
_MAIN_FENCE = re.compile(r"```\n(.*?)\n```", re.S)
_MAIN_CODE = re.compile(r"الكود\s*/\s*(\S+)")
_MAIN_NAME = re.compile(r"اسم العميل\s*/\s*(.*?)\s+التليفون")
_MAIN_PHONE = re.compile(r"(?:التليفون|الموبايل)\s*/\s*(01\d{9})")
_MAIN_TOTAL = re.compile(r"إجمالى الفاتورة\s*/\s*(-?[\d.,]+)")
_MAIN_PAID = re.compile(r"المدفوع\s*/\s*(-?[\d.,]+)")
_MAIN_REMAIN = re.compile(r"الباقي\s*/\s*(-?[\d.,]+)")
_MAIN_QTY = re.compile(r"عدد كميات الفاتورة\s*(-?[\d.,]+)")
_NUM_TOK = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")


def parse_main() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Parse the main markdown (2025-01 .. 2026-05). Same schema as ``parse_june``.

    Line columns follow the shared invoice layout (qty, unit price, tax %,
    discount %, line total); the footer carries paid/remaining/quantity.
    """
    text = C.SRC_MAIN_MD.read_text(encoding="utf-8")
    blocks = _MAIN_SPLIT.split(text)[1:]
    lines: list[dict] = []
    invoices: list[dict] = []
    for block in blocks:
        header_line, _, rest = block.partition("\n")
        hm = _MAIN_HEADER.match(header_line)
        if not hm:
            continue
        invoice_no, inv_date = hm.group(1).strip(), _to_date(hm.group(2))

        fence = _MAIN_FENCE.search(rest)
        if not fence:
            continue
        body = fence.group(1)
        blines = body.split("\n")

        cust_code = cust_name = phone = ""
        for ln in blines[:5]:
            if not cust_code and (m := _MAIN_CODE.search(ln)):
                cust_code = m.group(1)
            if not cust_name and (m := _MAIN_NAME.search(ln)):
                cust_name = m.group(1).strip()
            if not phone and (m := _MAIN_PHONE.search(ln)):
                phone = m.group(1)

        total = _num(_MAIN_TOTAL.search(body).group(1)) if _MAIN_TOTAL.search(body) else None
        paid = _num(_MAIN_PAID.search(body).group(1)) if _MAIN_PAID.search(body) else None
        remaining = _num(_MAIN_REMAIN.search(body).group(1)) if _MAIN_REMAIN.search(body) else None
        qty_total = _num(_MAIN_QTY.search(body).group(1)) if _MAIN_QTY.search(body) else None
        is_bonus = "بونص" in body

        line_sum = 0.0
        n_lines = 0
        for ln in blines:
            toks = ln.strip().split()
            if len(toks) < 7 or not _NUM_TOK.match(toks[0]) or not re.match(r"^\d+$", toks[1]):
                continue
            if any(w in ln for w in ("إجمالى", "ضريبة", "الباقي", "المدفوع")):
                continue
            if not all(_NUM_TOK.match(t) for t in toks[-5:]):
                continue
            qty, price, tax_pct, disc_pct, ltot = (_num(x) for x in toks[-5:])
            item_name = " ".join(toks[2:-5]).strip()
            if not item_name:
                continue
            lines.append(dict(
                invoice_no=invoice_no, invoice_date=inv_date, invoice_time="",
                customer_code=cust_code, customer_name=cust_name, phone=phone,
                address="", seq=_num(toks[0]), item_code=toks[1],
                item_name=item_name, unit="", qty=qty, unit_price=price,
                tax_pct=tax_pct, discount_pct=disc_pct, line_total=ltot, is_bonus=is_bonus,
            ))
            n_lines += 1
            line_sum += ltot or 0.0

        if n_lines == 0:
            continue
        invoices.append(dict(
            invoice_no=invoice_no, invoice_date=inv_date, invoice_time="",
            customer_code=cust_code, customer_name=cust_name, phone=phone,
            address="", reported_total=total, line_total_sum=round(line_sum, 2),
            remaining=remaining, paid=paid, qty_total=qty_total,
            is_bonus=is_bonus, n_lines=n_lines,
        ))
    return pl.DataFrame(lines), pl.DataFrame(invoices)


def parse_all(year: int | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Combine the main + June sources into one dataset, tagged with a ``month``
    column ('YYYY-MM'). Optionally restrict to a single calendar ``year``.

    June is taken exclusively from the dedicated June file (higher-fidelity table
    extraction); the main file supplies every earlier month.
    """
    from . import july as july_mod
    lm, im = parse_main()
    lj, ij = parse_june()
    l7, i7 = july_mod.parse_july()          # July 1–15 2026 (PDF); empty if absent
    # main file already contains an (older-format) June? keep the dedicated June
    # file authoritative for 2026-06 and drop any 2026-06 rows from the main set.
    def _drop_june26(df):
        return df.filter(~((pl.col("invoice_date").dt.year() == 2026)
                           & (pl.col("invoice_date").dt.month() == 6)))
    lm, im = _drop_june26(lm), _drop_june26(im)

    frames_l = [lm, lj] + ([l7] if l7.height else [])
    frames_i = [im, ij] + ([i7] if i7.height else [])
    lines = pl.concat(frames_l, how="vertical_relaxed")
    invoices = pl.concat(frames_i, how="vertical_relaxed")
    # Canonicalise customer codes (strip thousands-comma + apply the +1000 alias)
    # so codes ≥1000 join consistently with the debt snapshot and dimensions.
    lines = lines.with_columns(
        pl.col("customer_code").cast(pl.Utf8)
        .map_elements(C.canonical_code, return_dtype=pl.Utf8).alias("customer_code"))
    invoices = invoices.with_columns(
        pl.col("customer_code").cast(pl.Utf8)
        .map_elements(C.canonical_code, return_dtype=pl.Utf8).alias("customer_code"))
    lines = lines.with_columns(pl.col("invoice_date").dt.strftime("%Y-%m").alias("month"))
    invoices = invoices.with_columns(pl.col("invoice_date").dt.strftime("%Y-%m").alias("month"))
    if year is not None:
        lines = lines.filter(pl.col("invoice_date").dt.year() == year)
        invoices = invoices.filter(pl.col("invoice_date").dt.year() == year)
    return lines, invoices


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

    # Canonicalise customer codes so the ≥1000 comma-formatted codes join.
    dim_customers = dim_customers.with_columns(
        pl.col("customer_code").cast(pl.Utf8)
        .map_elements(C.canonical_code, return_dtype=pl.Utf8).alias("customer_code"))
    debt_detail = debt_detail.with_columns(
        pl.col("customer_code").cast(pl.Utf8)
        .map_elements(C.canonical_code, return_dtype=pl.Utf8).alias("customer_code"))

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
    # Display-only brand relabelling (config.BRAND_OVERRIDES) — leaves every
    # financial value untouched, changes only the shown brand label.
    if C.BRAND_OVERRIDES:
        out = out.with_columns(
            pl.col("item_code").replace(C.BRAND_OVERRIDES, default=None).alias("_brand_ovr")
        ).with_columns(
            pl.coalesce(["_brand_ovr", "brand"]).alias("brand")
        ).drop("_brand_ovr")
    return out
