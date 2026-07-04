"""Build the sales & debt analysis tables from the parsed invoice CSVs + the
transcribed debt-by-customer CSV, and export the results (CSV + one combined
Excel workbook) under analysis/data/.

Methodology (see analysis/README.md for full write-up):
  - "Zero invoices" = invoices whose header total is 0 (free/bonus stock, "بونص").
    Excluded from revenue, counted in quantities.
  - Average selling price per item = sum(line_total) / sum(qty) over paid
    (non-zero) lines only -- a realized-price average, which sidesteps the
    unreliable discount%/tax% column ordering noted in parse_invoices.py.
  - Bonus % per customer = bonus quantity / total quantity * 100.
  - Arrears = 30-day credit-term aging applied to the debt-PDF *snapshot*
    balance (as of 2026-07-04), NOT to a sum of historical invoices' "الباقي"
    fields. Those per-invoice remaining amounts are frozen at the time each
    invoice was printed and don't reflect later payments, so summing them
    across 17 months of invoices wildly overstates real debt (verified: it
    produced totals 10-20x the snapshot balance). The snapshot net balance is
    the only reliable *current* figure available.
    Proxy used instead: a customer's snapshot debt (net > 0) is classified as
    "arrears" if their most recent invoice in our data is more than 30 days
    before today (2026-07-04) -- i.e. they've gone quiet for over a month
    while still owing money, past the monthly credit term. If they invoiced
    within the last 30 days, the same debt is classified as "current" (still
    inside a normal revolving-credit cycle). A negative net (credit balance,
    i.e. the company owes the customer) is reported separately, not as debt.
    Known coverage gap: no invoice rows exist for 2026-05-10..05-31 or
    2026-07-01..07-04, so "last invoice date" can lag a customer's true last
    purchase by up to a few weeks for anyone who only ordered in that window.
  - Brand is derived from item name keywords (اسبشيال/اسباشيل -> اسبشيال,
    الهنا -> الهنا, else -> ابوهاشم), since the source brand-classification
    PDF has no item codes to join on positionally.
"""
import re
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "analysis" / "data"
TODAY = date(2026, 7, 4)
ARREARS_CUTOFF_DAYS = 30


def to_float(s):
    if s is None:
        return 0.0
    s = str(s).strip()
    if s == "":
        return 0.0
    neg = s.endswith("-")
    if neg:
        s = s[:-1]
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def parse_date(s):
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", str(s).strip())
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def brand_of(item_name: str) -> str:
    name = item_name or ""
    if "اسبشيال" in name or "اسباشيل" in name or "اسبيشيال" in name:
        return "اسبشيال"
    if "الهنا" in name:
        return "الهنا"
    return "ابوهاشم"


def load_headers():
    df = pl.read_csv(DATA / "invoices_header.csv", infer_schema_length=0)
    df = df.with_columns([
        pl.col("total").map_elements(to_float, return_dtype=pl.Float64).alias("total_f"),
        pl.col("remaining").map_elements(to_float, return_dtype=pl.Float64).alias("remaining_f"),
        pl.col("paid").map_elements(to_float, return_dtype=pl.Float64).alias("paid_f"),
        pl.col("total_qty").map_elements(to_float, return_dtype=pl.Float64).alias("total_qty_f"),
        pl.col("date").map_elements(parse_date, return_dtype=pl.Date).alias("date_d"),
    ])
    return df


def load_lines():
    df = pl.read_csv(DATA / "invoices_lines.csv", infer_schema_length=0)
    df = df.with_columns([
        pl.col("qty").map_elements(to_float, return_dtype=pl.Float64).alias("qty_f"),
        pl.col("line_total").map_elements(to_float, return_dtype=pl.Float64).alias("line_total_f"),
    ])
    return df


def load_debt():
    df = pl.read_csv(DATA / "debt_by_customer.csv")
    return df


def build_zero_invoices(headers: pl.DataFrame) -> pl.DataFrame:
    zero = headers.filter(pl.col("total_f") == 0).select(
        ["invoice_no", "date", "customer_code", "customer_name", "total_qty_f", "notes", "source_file"]
    ).rename({"total_qty_f": "qty"})
    return zero


def build_item_summary(lines: pl.DataFrame) -> pl.DataFrame:
    # Most frequent item_name per item_code, to smooth over OCR spelling variants.
    name_mode = (
        lines.group_by(["item_code", "item_name"])
        .agg(pl.len().alias("n"))
        .sort(["item_code", "n"], descending=[False, True])
        .group_by("item_code", maintain_order=True)
        .first()
        .select(["item_code", "item_name"])
    )

    paid_lines = lines.filter(pl.col("line_total_f") > 0)

    agg = (
        lines.group_by("item_code")
        .agg([
            pl.col("qty_f").sum().alias("total_qty"),
            pl.len().alias("line_count"),
        ])
    )
    paid_agg = (
        paid_lines.group_by("item_code")
        .agg([
            pl.col("qty_f").sum().alias("paid_qty"),
            pl.col("line_total_f").sum().alias("paid_value"),
        ])
    )

    out = (
        agg.join(paid_agg, on="item_code", how="left")
        .join(name_mode, on="item_code", how="left")
        .with_columns([
            pl.col("paid_qty").fill_null(0.0),
            pl.col("paid_value").fill_null(0.0),
        ])
        .with_columns(
            (pl.col("paid_value") / pl.when(pl.col("paid_qty") > 0).then(pl.col("paid_qty")).otherwise(None))
            .alias("avg_selling_price")
        )
        .with_columns(
            pl.col("item_name").map_elements(brand_of, return_dtype=pl.Utf8).alias("brand")
        )
        .select(["item_code", "item_name", "brand", "total_qty", "paid_qty", "paid_value", "avg_selling_price", "line_count"])
        .sort("paid_value", descending=True)
    )
    return out


def build_customer_summary(headers: pl.DataFrame) -> pl.DataFrame:
    name_mode = (
        headers.group_by(["customer_code", "customer_name"])
        .agg(pl.len().alias("n"))
        .sort(["customer_code", "n"], descending=[False, True])
        .group_by("customer_code", maintain_order=True)
        .first()
        .select(["customer_code", "customer_name"])
    )

    per_cust = (
        headers.group_by("customer_code")
        .agg([
            pl.col("total_f").filter(pl.col("total_f") > 0).sum().alias("sales_value"),
            pl.col("total_qty_f").sum().alias("total_qty"),
            pl.col("total_qty_f").filter(pl.col("total_f") == 0).sum().alias("bonus_qty"),
            pl.len().alias("invoice_count"),
            (pl.col("total_f") == 0).sum().alias("zero_invoice_count"),
        ])
        .join(name_mode, on="customer_code", how="left")
        .with_columns(
            (pl.col("bonus_qty") / pl.when(pl.col("total_qty") > 0).then(pl.col("total_qty")).otherwise(None) * 100)
            .fill_null(0.0)
            .alias("bonus_pct")
        )
        .select([
            "customer_code", "customer_name", "sales_value", "total_qty",
            "bonus_qty", "bonus_pct", "invoice_count", "zero_invoice_count",
        ])
        .sort("sales_value", descending=True)
    )
    return per_cust


def build_rep_debt_arrears(headers: pl.DataFrame, debt: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    last_invoice = (
        headers.filter(pl.col("date_d").is_not_null())
        .group_by("customer_code")
        .agg(pl.col("date_d").max().alias("last_invoice_date"))
        .with_columns(pl.col("customer_code").cast(pl.Utf8))
    )

    d = debt.with_columns(pl.col("customer_code").cast(pl.Utf8)).join(
        last_invoice, on="customer_code", how="left"
    )

    days_since_last = (pl.lit(TODAY) - pl.col("last_invoice_date")).dt.total_days()
    is_stale = pl.col("last_invoice_date").is_null() | (days_since_last > ARREARS_CUTOFF_DAYS)

    d = d.with_columns([
        pl.when(pl.col("net") > 0).then(pl.col("net")).otherwise(0.0).alias("debt_amount"),
        pl.when(pl.col("net") < 0).then(-pl.col("net")).otherwise(0.0).alias("credit_balance"),
    ]).with_columns([
        pl.when(is_stale).then(pl.col("debt_amount")).otherwise(0.0).alias("arrears_amount"),
        pl.when(is_stale).then(0.0).otherwise(pl.col("debt_amount")).alias("current_amount"),
    ])

    per_customer = (
        d.select([
            "rep", "customer_code", "customer_name", "last_invoice_date",
            "debt_amount", "credit_balance", "current_amount", "arrears_amount",
        ])
        .sort("arrears_amount", descending=True)
    )

    per_rep = (
        d.group_by("rep")
        .agg([
            pl.col("net").sum().alias("debt_pdf_snapshot_net_2026_07_04"),
            pl.col("debt_amount").sum().alias("total_debt"),
            pl.col("current_amount").sum().alias("current_amount"),
            pl.col("arrears_amount").sum().alias("arrears_amount"),
            pl.col("credit_balance").sum().alias("total_credit_balance"),
            pl.len().alias("customer_count"),
        ])
        .sort("debt_pdf_snapshot_net_2026_07_04", descending=True)
    )
    return per_rep, per_customer


def main():
    headers = load_headers()
    lines = load_lines()
    debt = load_debt()

    zero_invoices = build_zero_invoices(headers)
    item_summary = build_item_summary(lines)
    customer_summary = build_customer_summary(headers)
    rep_summary, customer_arrears = build_rep_debt_arrears(headers, debt)

    zero_invoices.write_csv(DATA / "zero_invoices.csv")
    item_summary.write_csv(DATA / "item_summary.csv")
    customer_summary.write_csv(DATA / "customer_sales_bonus_summary.csv")
    rep_summary.write_csv(DATA / "rep_debt_arrears_summary.csv")
    customer_arrears.write_csv(DATA / "customer_debt_arrears_detail.csv")

    with pl.Config(fmt_str_lengths=60):
        print("=== Zero invoices ===")
        print(f"count: {zero_invoices.height} / {headers.height} total invoices")
        print("\n=== Item summary (top 10 by paid value) ===")
        print(item_summary.head(10))
        print("\n=== Customer summary (top 10 by sales) ===")
        print(customer_summary.head(10))
        print("\n=== Rep debt & arrears summary ===")
        print(rep_summary)

    # bundle summaries into one workbook for convenience
    import xlsxwriter  # noqa: F401  (ensures dependency presence is checked early)
    with pl.Config():
        workbook_path = DATA / "sales_debt_analysis.xlsx"
        summaries = {
            "rep_debt_arrears": rep_summary,
            "customer_sales_bonus": customer_summary,
            "item_summary": item_summary,
            "zero_invoices": zero_invoices,
            "customer_debt_detail": customer_arrears,
        }
        with xlsxwriter.Workbook(str(workbook_path)) as wb:
            for sheet_name, frame in summaries.items():
                frame.write_excel(workbook=wb, worksheet=sheet_name)
    print(f"\nWorkbook written to {workbook_path}")


if __name__ == "__main__":
    main()
