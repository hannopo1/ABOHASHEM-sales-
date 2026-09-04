"""
Parser for the per-representative customer account-balance PDFs
("تقرير عن حسابات العملاء") — the outstanding balance of every customer as of the
day the report was filed.

The current snapshot is listed in ``config.AR_SNAPSHOT_FILES``.

Each row carries a debit (مدين) and a credit (دائن) column; the customer's
balance is the NET of the two. Taking the debit column alone — as this parser
originally did — overstates every rep's total by their customers' credit
balances, and the file's own printed «الصافى» is what catches it: each file is
reconciled against it and a mismatch aborts the build.

Parsed geometrically via column x-bands, deduplicated by customer code.
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import config as C

# x-bands in the debt report (RTL). Debit ~161, credit ~238, code ~521,
# name ~450, rep ~310.
_BAL = (148, 216)
_CREDIT = (216, 272)
_CODE = (505, 535)
_NAME = (342, 505)          # widened; the customer-type word «عميل» (~376) is excluded below
_REP = (285, 342)

# The printed per-file net, used as the reconciliation anchor.
_NET_RX = re.compile(r"الصافى\s*([\d,]+(?:\.\d+)?)")


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_pdf(path) -> list[tuple]:
    import fitz
    doc = fitz.open(path)
    rows_out = []
    for pi in range(doc.page_count):
        by_y = defaultdict(list)
        for x0, y0, x1, y1, word, *_ in doc[pi].get_text("words"):
            by_y[round(y0)].append((x0, word))
        for _y, ws in by_y.items():
            ws = sorted(ws)
            code = next((wd for x, wd in ws if _CODE[0] <= x <= _CODE[1] and re.match(r"^\d+$", wd)), None)
            if not code:
                continue
            bal = next((_num(wd) for x, wd in ws if _BAL[0] <= x <= _BAL[1] and _num(wd) is not None), None)
            if bal is None:
                continue
            credit = next((_num(wd) for x, wd in ws
                           if _CREDIT[0] <= x <= _CREDIT[1] and _num(wd) is not None), 0.0) or 0.0
            bal = round(bal - credit, 2)
            name = " ".join(
                wd for x, wd in sorted((p for p in ws if _NAME[0] <= p[0] <= _NAME[1]),
                                       key=lambda t: -t[0])
                if wd != "عميل" and not re.fullmatch(r"[\d.,]+", wd))
            rep = " ".join(wd for x, wd in sorted((p for p in ws if _REP[0] <= p[0] <= _REP[1]),
                                                  key=lambda t: -t[0]))
            rows_out.append((code, bal, name.strip(), rep.strip()))
    return rows_out


def _printed_net(path) -> float | None:
    """The «الصافى» figure printed at the foot of a balance report."""
    import fitz
    doc = fitz.open(str(path))
    m = _NET_RX.search(doc[doc.page_count - 1].get_text())
    return float(m.group(1).replace(",", "")) if m else None


def load_final_balances() -> dict:
    """Return {customer_code: {'balance', 'name', 'rep', 'rep_official'}} as of
    ``config.AS_OF_DATE``. ``rep_official`` is the file-based (authoritative)
    representative.

    Every file must reproduce its own printed net or the build aborts. Empty dict
    if the snapshot PDFs are absent (build never hard-fails on a fresh checkout).
    """
    out: dict[str, dict] = {}
    for path, rep_official in C.AR_SNAPSHOT_FILES:
        if not path.exists():
            continue
        rows = _parse_pdf(str(path))
        printed = _printed_net(path)
        parsed = round(sum(r[1] for r in rows), 2)
        if printed is not None and abs(parsed - printed) > 0.01:
            raise SystemExit(
                f"[debt] {path.name} does not reconcile to its printed net.\n"
                f"  parsed  : {parsed:,.2f}\n"
                f"  printed : {printed:,.2f}\n"
                f"  diff    : {parsed - printed:,.2f}")
        for code, bal, name, rep in rows:
            # Canonicalise the code (strip thousands-comma + apply the +1000
            # alias) so the balance keys onto the same identity as the invoices.
            # One row per customer; on the rare collision the balances are summed.
            code = C.canonical_code(code)
            if code in out:
                out[code]["balance"] = round(out[code]["balance"] + round(bal, 2), 2)
            else:
                out[code] = {"balance": round(bal, 2), "name": name,
                             "rep": rep, "rep_official": rep_official}
    return out
