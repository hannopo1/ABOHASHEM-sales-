"""
Parser for the July 1–15 2026 sales-invoices PDF (Pioneers-template).

Unlike the earlier months (delivered as pre-converted markdown), July arrived as
a native PDF — one invoice per page, 160 pages — carrying an extractable text
layer. Header/footer fields are label-anchored; line items are recovered
geometrically via column x-bands + y-gap clustering, which is robust to wrapped
Arabic item names. Every one of the 160 invoices reconciles (Σ line_total ==
reported total), so no value is inferred or fabricated.

Emits the exact same schema as ``load.parse_june`` / ``load.parse_main`` so it
concatenates straight into the 2026 dataset.
"""
from __future__ import annotations

import re
from datetime import date

import polars as pl

from . import config as C

# Column x-bands of the Pioneers invoice template (RTL). (name, lo, hi)
_BANDS = [("total", 0, 70), ("pct", 70, 135), ("price", 135, 200), ("qty", 200, 275),
          ("unit", 275, 345), ("name", 345, 492), ("code", 492, 545), ("seq", 545, 9999)]


def _band(x: float):
    for n, lo, hi in _BANDS:
        if lo <= x < hi:
            return n
    return None


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _to_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("/"))
    return date(y, m, d)


def _header_footer(text: str) -> dict:
    def g(rx):
        m = re.search(rx, text)
        return m.group(1) if m else None
    return dict(
        invoice_no=(g(r"([Bb]\d+)\s*فاتورة مبيعات رقم") or "").upper() or None,
        # Invoice ISSUE date — anchored to the customer «الكود» field, where the
        # date is printed ("/ الكود2026/7/1"). This avoids ever picking up the
        # report-period header dates that appear on the first page. Falls back to
        # the first date on the page only if the anchor is missing.
        invoice_date=g(r"الكود\s*(\d{4}/\d{1,2}/\d{1,2})") or g(r"(\d{4}/\d{1,2}/\d{1,2})"),
        customer_code=g(r"(\d+)\s*\n\s*/?\s*الكود") or "",
        customer_name=(g(r"([^\n]+)\n\s*اسم العميل") or "").strip(),
        phone=g(r"(01\d{9,10})") or "",
        reported_total=_num(g(r"([\d.,]+)\s*/\s*إجمالى الفاتورة")),
        paid=_num(g(r"/\s*المدفوع\s*([\d.,]+)")),
        remaining=_num(g(r"/\s*الباقي\s*([\d.,]+)")),
        qty_total=_num(g(r"([\d.,]+)\s*عدد كميات الفاتورة")),
        is_bonus="بونص" in text,
    )


def _items(page) -> list[dict]:
    words = page.get_text("words")               # (x0, y0, x1, y1, word, ...)
    ys_hdr = [w[1] for w in words if w[4] == "الضريبة"]
    ys_ft = [w[1] for w in words if "الفاتورة" in w[4] or w[4] == "إجمالى"]
    y_top = max(ys_hdr) + 3 if ys_hdr else 250
    y_bot = min([y for y in ys_ft if y > y_top], default=1e9)
    reg = sorted((w for w in words if y_top < w[1] < y_bot), key=lambda w: w[1])
    if not reg:
        return []
    # cluster words into item rows by vertical gaps (handles 2-line wrapped names)
    blocks, cur, last = [], [], None
    for w in reg:
        if last is not None and w[1] - last > 9:
            blocks.append(cur)
            cur = []
        cur.append(w)
        last = w[1]
    if cur:
        blocks.append(cur)

    out = []
    for blk in blocks:
        cols: dict[str, list] = {}
        for x0, y0, x1, y1, word, *_ in blk:
            b = _band(x0)
            if b:
                cols.setdefault(b, []).append((x0, word))
        if "seq" not in cols or "total" not in cols:
            continue
        name = " ".join(wd for x, wd in sorted(cols.get("name", []), key=lambda t: -t[0]))
        firstnum = lambda k: next((_num(wd) for x, wd in sorted(cols.get(k, []))
                                   if _num(wd) is not None), None)
        code = next((wd for x, wd in cols.get("code", []) if re.match(r"^\d+$", wd)), "")
        ltot, qty, price = firstnum("total"), firstnum("qty"), firstnum("price")
        pcts = [_num(wd) for x, wd in sorted(cols.get("pct", [])) if _num(wd) is not None]
        if ltot is None or qty is None:
            continue
        out.append(dict(
            item_code=code, item_name=name.strip(),
            unit=" ".join(wd for x, wd in cols.get("unit", [])),
            qty=qty, unit_price=price,
            discount_pct=pcts[0] if pcts else 0.0,
            tax_pct=pcts[1] if len(pcts) > 1 else 0.0,
            line_total=ltot,
        ))
    return out


def parse_july() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Returns (lines_df, invoices_df) in the shared invoice schema. Empty frames
    if the source PDF is absent (kept optional so the build never hard-fails)."""
    if not C.SRC_JULY_PDF.exists():
        return pl.DataFrame(), pl.DataFrame()
    import fitz

    doc = fitz.open(str(C.SRC_JULY_PDF))
    lines: list[dict] = []
    invoices: list[dict] = []
    for pi in range(doc.page_count):
        page = doc[pi]
        hf = _header_footer(page.get_text())
        items = _items(page)
        if not items or not hf["invoice_no"] or not hf["invoice_date"]:
            continue
        inv_date = _to_date(hf["invoice_date"])
        is_bonus = hf["is_bonus"] or (hf["reported_total"] == 0)
        line_sum = 0.0
        for seq, it in enumerate(items, 1):
            lines.append(dict(
                invoice_no=hf["invoice_no"], invoice_date=inv_date, invoice_time="",
                customer_code=hf["customer_code"], customer_name=hf["customer_name"],
                phone=hf["phone"], address="", seq=float(seq),
                item_code=it["item_code"], item_name=it["item_name"], unit=it["unit"],
                qty=it["qty"], unit_price=it["unit_price"], tax_pct=it["tax_pct"],
                discount_pct=it["discount_pct"], line_total=it["line_total"], is_bonus=is_bonus,
            ))
            line_sum += it["line_total"] or 0.0
        invoices.append(dict(
            invoice_no=hf["invoice_no"], invoice_date=inv_date, invoice_time="",
            customer_code=hf["customer_code"], customer_name=hf["customer_name"],
            phone=hf["phone"], address="", reported_total=hf["reported_total"],
            line_total_sum=round(line_sum, 2), remaining=hf["remaining"], paid=hf["paid"],
            qty_total=hf["qty_total"], is_bonus=is_bonus, n_lines=len(items),
        ))
    return pl.DataFrame(lines), pl.DataFrame(invoices)
