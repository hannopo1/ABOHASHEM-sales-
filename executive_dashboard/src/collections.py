"""
Parser + aggregator for the full-year-2026 customer **collections** (سدادات
العملاء) and **returns** (ارتجاعات العملاء) PDFs.

Both are geometric x-band report tables (one logical row spread over two very
close y-lines). Rows are recovered exactly like ``src/debt.py`` / ``src/july.py``:
cluster ``page.get_text("words")`` by vertical gaps, then bucket tokens into
columns by their ``x0``. Parsed sums reconcile **exactly** to the printed grand
totals (``config.COLLECTIONS_PRINTED_TOTAL`` / ``RETURNS_PRINTED_TOTAL``).

Attribution caveat (honest, never fabricated):
  * Neither file carries a customer code. The reference serial they DO carry
    (5500-7100) is the ERP's internal voucher sequence — it does NOT overlap the
    sales-invoice display numbers (b145-b2803), so a return cannot be joined to a
    sales invoice by number. Both files are therefore attributed to a customer by
    **normalised name** against the invoice/customer master (95%+ unique match).
  * Un-attributed rows are pooled into a clearly-labelled «غير مُطابَق» bucket and
    reported — never dropped, never invented. Every total still reconciles to the
    printed grand total regardless of attribution.

All aggregation runs on Polars and is deterministic (sorted, rounded).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

import polars as pl

from . import config as C

# --- column x-bands (measured on the source PDFs, RTL) -----------------------
# Collections: date | البيان (serial+receipt+phrase) | amount | name | seq
_C_DATE = (0, 120)
_C_BAYAN = (120, 315)
_C_AMT = (315, 375)
_C_NAME = (410, 510)
_C_SEQ = (540, 9999)
# Returns: date | value | invoice-serial | name | seq
_R_DATE = (0, 90)
_R_VAL = (90, 155)
_R_INV = (155, 220)
_R_NAME = (300, 430)
_R_SEQ = (520, 9999)

_DATE_RX = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")
_AMOUNT_RX = re.compile(r"^-?[\d,]+\.\d+$")
_INT_RX = re.compile(r"^\d+$")

_COLL_SCHEMA = {
    "date": pl.Date, "month": pl.Utf8, "customer_name": pl.Utf8, "amount": pl.Float64,
    "doc_ref": pl.Utf8, "receipt_no": pl.Utf8, "method": pl.Utf8, "bayan": pl.Utf8,
}
_RET_SCHEMA = {
    "date": pl.Date, "month": pl.Utf8, "customer_name": pl.Utf8,
    "invoice_ref": pl.Utf8, "value": pl.Float64,
}


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _to_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("/"))
    return date(y, m, d)


def _norm(s) -> str:
    """Normalise an Arabic customer name for matching: unify alef/ya/ta-marbuta,
    strip tatweel + diacritics, collapse whitespace."""
    if not s:
        return ""
    s = str(s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ـ", "")):
        s = s.replace(a, b)
    s = re.sub(r"[ً-ْ]", "", s)          # harakat
    return re.sub(r"\s+", " ", s).strip()


def _cluster_rows(page, gap: float = 6.0) -> list[list]:
    """Group a page's words into logical rows by vertical gaps (rows are ~17pt
    apart; the two lines of one row are <1pt apart)."""
    ws = sorted(page.get_text("words"), key=lambda w: (w[1], w[0]))
    rows: list[list] = []
    cur: list = []
    last = None
    for w in ws:
        if last is not None and w[1] - last > gap:
            rows.append(cur)
            cur = []
        cur.append(w)
        last = w[1]
    if cur:
        rows.append(cur)
    return rows


def _join_desc(cells: list[tuple]) -> str:
    """Join word tokens right-to-left (descending x0) into RTL reading order."""
    return " ".join(wd for x, wd in sorted(cells, key=lambda t: -t[0])).strip()


def _method(bayan: str) -> str:
    for kw, label in C.PAYMENT_METHOD_KEYWORDS:
        if kw in bayan:
            return label
    return C.PAYMENT_METHOD_DEFAULT


def parse_collections() -> pl.DataFrame:
    """1,423 receipt rows. Empty (typed) frame if the source PDF is absent."""
    if not C.SRC_COLLECTIONS_PDF.exists():
        return pl.DataFrame(schema=_COLL_SCHEMA)
    import fitz

    doc = fitz.open(str(C.SRC_COLLECTIONS_PDF))
    out: list[dict] = []
    for pi in range(doc.page_count):
        for row in _cluster_rows(doc[pi]):
            amount = date_s = seq = None
            name_cells, bayan_cells = [], []
            for x0, y0, x1, y1, wd, *_ in row:
                if _C_AMT[0] <= x0 <= _C_AMT[1] and _AMOUNT_RX.match(wd):
                    amount = _num(wd)
                elif _C_DATE[0] <= x0 < _C_DATE[1] and _DATE_RX.match(wd):
                    date_s = wd
                elif x0 >= _C_SEQ[0] and re.match(r"^[\d,]+$", wd):
                    seq = wd
                elif _C_NAME[0] <= x0 <= _C_NAME[1]:
                    name_cells.append((x0, wd))
                elif _C_BAYAN[0] <= x0 < _C_BAYAN[1]:
                    bayan_cells.append((x0, wd))
            if amount is None or not date_s or not seq:
                continue
            name = _join_desc(name_cells)
            bayan = _join_desc(bayan_cells)
            serials = [wd for x, wd in sorted(bayan_cells) if _INT_RX.match(wd)]
            out.append({
                "date": _to_date(date_s),
                "month": date_s.split("/")[0] + "-" + date_s.split("/")[1].zfill(2),
                "customer_name": name,
                "amount": amount,
                "doc_ref": serials[0] if serials else "",
                "receipt_no": serials[1] if len(serials) > 1 else "",
                "method": _method(bayan),
                "bayan": bayan,
            })
    return pl.DataFrame(out, schema=_COLL_SCHEMA)


def parse_returns() -> pl.DataFrame:
    """156 credit-note rows. Empty (typed) frame if the source PDF is absent."""
    if not C.SRC_RETURNS_PDF.exists():
        return pl.DataFrame(schema=_RET_SCHEMA)
    import fitz

    doc = fitz.open(str(C.SRC_RETURNS_PDF))
    out: list[dict] = []
    for pi in range(doc.page_count):
        for row in _cluster_rows(doc[pi]):
            value = date_s = seq = invref = None
            name_cells = []
            for x0, y0, x1, y1, wd, *_ in row:
                if _R_VAL[0] <= x0 <= _R_VAL[1] and _AMOUNT_RX.match(wd):
                    value = _num(wd)
                elif _R_DATE[0] <= x0 < _R_DATE[1] and _DATE_RX.match(wd):
                    date_s = wd
                elif x0 >= _R_SEQ[0] and re.match(r"^[\d,]+$", wd):
                    seq = wd
                elif _R_INV[0] <= x0 <= _R_INV[1] and _INT_RX.match(wd):
                    invref = wd
                elif _R_NAME[0] <= x0 <= _R_NAME[1]:
                    name_cells.append((x0, wd))
            if value is None or not date_s or not seq:
                continue
            out.append({
                "date": _to_date(date_s),
                "month": date_s.split("/")[0] + "-" + date_s.split("/")[1].zfill(2),
                "customer_name": _join_desc(name_cells),
                "invoice_ref": invref or "",
                "value": value,
            })
    return pl.DataFrame(out, schema=_RET_SCHEMA)


def _name_index(invoices_full: pl.DataFrame, dim_customers: pl.DataFrame) -> dict:
    """normalised customer-name → code, keeping ONLY names that map to a single
    code (ambiguous names are excluded so attribution never guesses)."""
    name2codes: dict[str, set] = defaultdict(set)
    for df, ncol, ccol in ((invoices_full, "customer_name", "customer_code"),
                           (dim_customers, "customer_name", "customer_code")):
        if df is None or df.height == 0 or ncol not in df.columns:
            continue
        for r in df.with_columns(pl.col(ccol).cast(pl.Utf8)).select(ncol, ccol).iter_rows(named=True):
            nm = _norm(r[ncol])
            if nm and not nm.replace(" ", "").isdigit():
                name2codes[nm].add(str(r[ccol]))
    return {nm: next(iter(codes)) for nm, codes in name2codes.items() if len(codes) == 1}


def compute(collections_df: pl.DataFrame, returns_df: pl.DataFrame,
            invoices_full: pl.DataFrame, dim_customers: pl.DataFrame,
            name_map: dict, rep_map: dict) -> tuple[dict, dict, dict, set, dict]:
    """Aggregate collections + returns into the ``collections`` payload and the
    per-customer maps that drive the recomputed collection-rate/bonus KPIs.

    Returns ``(payload, collected_by_code, returns_by_code, reliable_codes, stats)``.
    """
    name_map = name_map or {}
    rep_map = rep_map or {}
    idx = _name_index(invoices_full, dim_customers)
    UNMATCHED = "غير مُطابَق"

    def code_for(name):
        return idx.get(_norm(name))

    # --- attribute rows ------------------------------------------------------
    collected_by_code: dict[str, float] = defaultdict(float)
    returns_by_code: dict[str, float] = defaultdict(float)
    receipts_matched = returns_matched = 0
    unmatched_coll_amt = unmatched_ret_amt = 0.0

    receipts_rows: list[dict] = []
    for r in collections_df.iter_rows(named=True):
        code = code_for(r["customer_name"])
        rep = rep_map.get(code) if code else None
        if code:
            collected_by_code[code] += r["amount"]
            receipts_matched += 1
        else:
            unmatched_coll_amt += r["amount"]
        receipts_rows.append({
            "date": r["date"].isoformat(), "month": r["month"],
            # Attributed rows show the code's ONE authoritative name (name_map)
            # so the receipt table matches every other view; unmatched rows keep
            # the raw PDF spelling (their only name).
            "customer_name": (name_map.get(code) or r["customer_name"]) if code
                             else r["customer_name"],
            "customer_code": code or "", "rep": rep or UNMATCHED,
            "method": r["method"], "doc_ref": r["doc_ref"],
            "receipt_no": r["receipt_no"], "amount": round(r["amount"], 2),
        })

    returns_rows: list[dict] = []
    for r in returns_df.iter_rows(named=True):
        code = code_for(r["customer_name"])
        rep = rep_map.get(code) if code else None
        if code:
            returns_by_code[code] += r["value"]
            returns_matched += 1
        else:
            unmatched_ret_amt += r["value"]
        returns_rows.append({
            "date": r["date"].isoformat(), "month": r["month"],
            "customer_name": (name_map.get(code) or r["customer_name"]) if code
                             else r["customer_name"],
            "customer_code": code or "",
            "rep": rep or UNMATCHED, "invoice_ref": r["invoice_ref"],
            "value": round(r["value"], 2),
        })

    total_collected = round(float(collections_df["amount"].sum() or 0.0), 2)
    total_returns = round(float(returns_df["value"].sum() or 0.0), 2)

    # --- monthly series ------------------------------------------------------
    def _monthly(df, col):
        if df.height == 0:
            return {}
        g = df.group_by("month").agg([pl.col(col).sum().alias("v"),
                                      pl.len().alias("n")]).sort("month")
        return {r["month"]: (round(float(r["v"]), 2), int(r["n"])) for r in g.iter_rows(named=True)}

    cm, rm = _monthly(collections_df, "amount"), _monthly(returns_df, "value")
    months = sorted(set(cm) | set(rm))
    monthly = [{"month": m,
                "collected": cm.get(m, (0.0, 0))[0], "n_receipts": cm.get(m, (0.0, 0))[1],
                "returns": rm.get(m, (0.0, 0))[0], "n_returns": rm.get(m, (0.0, 0))[1]}
               for m in months]

    # --- by rep (attributed; unmatched pooled honestly) ----------------------
    rep_agg: dict[str, dict] = defaultdict(lambda: {"collected": 0.0, "returns": 0.0, "customers": set()})
    for code, v in collected_by_code.items():
        rep = rep_map.get(code) or UNMATCHED
        rep_agg[rep]["collected"] += v
        rep_agg[rep]["customers"].add(code)
    for code, v in returns_by_code.items():
        rep = rep_map.get(code) or UNMATCHED
        rep_agg[rep]["returns"] += v
        rep_agg[rep]["customers"].add(code)
    if unmatched_coll_amt or unmatched_ret_amt:
        rep_agg[UNMATCHED]["collected"] += unmatched_coll_amt
        rep_agg[UNMATCHED]["returns"] += unmatched_ret_amt
    by_rep = sorted(({"rep": k, "collected": round(v["collected"], 2),
                      "returns": round(v["returns"], 2), "customers": len(v["customers"])}
                     for k, v in rep_agg.items()), key=lambda x: x["collected"], reverse=True)

    # --- by payment method ---------------------------------------------------
    if collections_df.height:
        mg = collections_df.group_by("method").agg([pl.col("amount").sum().alias("amount"),
                                                    pl.len().alias("count")]).sort("amount", descending=True)
        by_method = [{"method": r["method"], "amount": round(float(r["amount"]), 2), "count": int(r["count"])}
                     for r in mg.iter_rows(named=True)]
    else:
        by_method = []

    # --- by customer (attributed) --------------------------------------------
    codes = set(collected_by_code) | set(returns_by_code)
    by_customer = sorted(({"customer_code": c,
                           "customer_name": name_map.get(c) or f"عميل {c}",
                           "rep": rep_map.get(c) or "غير محدد",
                           "collected": round(collected_by_code.get(c, 0.0), 2),
                           "returns": round(returns_by_code.get(c, 0.0), 2)}
                          for c in codes), key=lambda x: x["collected"], reverse=True)

    reliable_codes = set(collected_by_code)      # codes with a unique-name receipt

    payload = {
        "grand_total_collected": total_collected,
        "grand_total_returns": total_returns,
        "printed_total_collected": C.COLLECTIONS_PRINTED_TOTAL,
        "printed_total_returns": C.RETURNS_PRINTED_TOTAL,
        "period": {"collections": "2026-01-01 … 2026-07-18", "returns": "2026-01-01 … 2026-07-16"},
        "monthly": monthly,
        "by_rep": by_rep,
        "by_method": by_method,
        "by_customer": by_customer,
        "receipts": receipts_rows,
        "returns_rows": returns_rows,
        "attribution": {
            "receipts_total": collections_df.height,
            "receipts_matched": receipts_matched,
            "receipts_unmatched": collections_df.height - receipts_matched,
            "unmatched_collected": round(unmatched_coll_amt, 2),
            "returns_total": returns_df.height,
            "returns_matched": returns_matched,
            "returns_unmatched": returns_df.height - returns_matched,
            "unmatched_returns": round(unmatched_ret_amt, 2),
            "unmatched_label": UNMATCHED,
        },
    }
    stats = payload["attribution"]
    return payload, dict(collected_by_code), dict(returns_by_code), reliable_codes, stats
