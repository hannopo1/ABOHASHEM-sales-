"""
Receivables & aging analysis (AR snapshot 2026-07-04).

IMPORTANT — honest caveat: the source invoices carry NO due date, so a true
per-invoice 6-bucket aging cannot be derived. The snapshot instead already
splits each customer's balance into *current* vs *arrears* (overdue). We keep
``current`` as-is and distribute each customer's arrears into an aging bucket by
the age of their last activity (relative to the snapshot, net of assumed terms).
The bucket totals therefore reconcile exactly to the AR outstanding total; only
the split *within* the overdue band is an approximation, and it is labelled as
such everywhere it appears.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from . import config as C


def _parse_date(s) -> date | None:
    if s is None or str(s).strip() == "":
        return None
    txt = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            from datetime import datetime
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _bucket_for_overdue(days_overdue: int) -> str:
    for key, _label, lo, hi in C.AGING_BUCKETS:
        if key == "current":
            continue
        if lo <= days_overdue <= hi:
            return key
    return "d120p"


def compute(debt_detail: pl.DataFrame) -> dict:
    as_of = date.fromisoformat(C.AS_OF_DATE)
    buckets = {key: 0.0 for key, *_ in C.AGING_BUCKETS}
    by_rep: dict[str, dict] = {}
    rows: list[dict] = []

    total_current = total_overdue = total_credit = 0.0

    for r in debt_detail.iter_rows(named=True):
        current = float(r.get("current_amount") or 0.0)
        arrears = float(r.get("arrears_amount") or 0.0)
        credit = float(r.get("credit_balance") or 0.0)
        rep = r.get("rep") or "غير محدد"
        last_dt = _parse_date(r.get("last_invoice_date"))

        age = (as_of - last_dt).days if last_dt else 9999
        days_overdue = max(1, age - C.NET_TERMS_DAYS)

        buckets["current"] += current
        bkey = "current"
        if arrears > 0:
            bkey = _bucket_for_overdue(days_overdue)
            buckets[bkey] += arrears

        total_current += current
        total_overdue += arrears
        total_credit += credit

        rep_slot = by_rep.setdefault(rep, {"current": 0.0, "overdue": 0.0, "customers": 0})
        rep_slot["current"] += current
        rep_slot["overdue"] += arrears
        rep_slot["customers"] += 1

        outstanding = current + arrears
        if outstanding > 0 or credit > 0:
            rows.append({
                "rep": rep,
                "customer_code": str(r.get("customer_code")),
                "customer_name": r.get("customer_name"),
                "last_invoice_date": last_dt.isoformat() if last_dt else "",
                "outstanding": round(outstanding, 2),
                "current": round(current, 2),
                "overdue": round(arrears, 2),
                "credit_balance": round(credit, 2),
                "days_since_last": age if last_dt else None,
                "days_overdue": days_overdue if arrears > 0 else 0,
                "bucket": bkey,
            })

    rows.sort(key=lambda x: x["outstanding"], reverse=True)
    total_outstanding = total_current + total_overdue

    rep_rows = sorted(
        ({"rep": k, "current": round(v["current"], 2), "overdue": round(v["overdue"], 2),
          "outstanding": round(v["current"] + v["overdue"], 2), "customers": v["customers"]}
         for k, v in by_rep.items()),
        key=lambda x: x["outstanding"], reverse=True,
    )

    return {
        "total_outstanding": round(total_outstanding, 2),
        "total_current": round(total_current, 2),
        "total_overdue": round(total_overdue, 2),
        "total_credit": round(total_credit, 2),
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "bucket_labels": {key: label for key, label, *_ in C.AGING_BUCKETS},
        "by_rep": rep_rows,
        "rows": rows,
    }
