"""
Parser for the customer account-balance PDFs dated 2026-07-16
(``مديونية <rep>-16_7_2026.pdf``) — the FINAL post-July customer balances.

These are "تقرير عن حسابات العملاء" reports (one row per customer): the balance
(الرصيد) column is the outstanding amount; the code column is the customer code.
Parsed geometrically via column x-bands, deduplicated by customer code.
"""
from __future__ import annotations

import glob
import re
from collections import defaultdict

from . import config as C

# x-bands in the debt report (RTL). Balance ~161, code ~521, name ~450, rep ~310.
_BAL = (148, 216)
_CODE = (505, 535)
_NAME = (342, 505)          # widened; the customer-type word «عميل» (~376) is excluded below
_REP = (285, 342)


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
            name = " ".join(
                wd for x, wd in sorted((p for p in ws if _NAME[0] <= p[0] <= _NAME[1]),
                                       key=lambda t: -t[0])
                if wd != "عميل" and not re.fullmatch(r"[\d.,]+", wd))
            rep = " ".join(wd for x, wd in sorted((p for p in ws if _REP[0] <= p[0] <= _REP[1]),
                                                  key=lambda t: -t[0]))
            rows_out.append((code, bal, name.strip(), rep.strip()))
    return rows_out


def load_final_balances() -> dict:
    """Return {customer_code: {'balance', 'name', 'rep'}} as of 2026-07-16.

    Empty dict if the snapshot PDFs are absent (build never hard-fails).
    """
    files = sorted(glob.glob(str(C.REPO_ROOT / "مديونية*16_7_2026.pdf")))
    out: dict[str, dict] = {}
    for f in files:
        for code, bal, name, rep in _parse_pdf(f):
            # one row per customer; last wins (files are per-rep, codes unique)
            out[code] = {"balance": round(bal, 2), "name": name, "rep": rep}
    return out
