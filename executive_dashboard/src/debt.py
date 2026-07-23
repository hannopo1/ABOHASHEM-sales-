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


def _rep_from_filename(path: str) -> str:
    """Each report is filed under one representative — the file name IS the
    official customer→rep assignment (cleaner than the in-page rep column)."""
    base = path.split("/")[-1].replace("مديونية ", "")
    return re.sub(r"[-_ ]*16_7_2026\.pdf$", "", base).strip()


def load_final_balances() -> dict:
    """Return {customer_code: {'balance', 'name', 'rep', 'rep_official'}} as of
    2026-07-16. ``rep_official`` is the file-based (authoritative) representative.

    Empty dict if the snapshot PDFs are absent (build never hard-fails).
    """
    files = sorted(glob.glob(str(C.REPO_ROOT / "مديونية*16_7_2026.pdf")))
    out: dict[str, dict] = {}
    for f in files:
        rep_official = _rep_from_filename(f)
        for code, bal, name, rep in _parse_pdf(f):
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
