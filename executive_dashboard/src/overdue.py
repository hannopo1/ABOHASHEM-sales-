"""
Overdue-receivable analysis via FIFO allocation against the FINAL customer
balance (the as-of snapshot in config.AR_SNAPSHOT_FILES).

Method (standard AR FIFO — oldest paid first):
  * For each customer we take their full parsed invoice history and their final
    outstanding balance B from the snapshot.
  * Implied collections = total_billed - B are applied to the OLDEST invoices
    first; the unpaid residual therefore lands on the most recent invoices, and
    Σ unpaid reconciles EXACTLY to B.
  * Any unpaid (or partially unpaid) invoice dated on or before
    ``config.OVERDUE_CUTOFF`` is classified OVERDUE; later unpaid invoices are
    CURRENT (not yet due).
  * Overdue amounts are aged into buckets by invoice age vs the snapshot date.
    Balance in excess of the parsed history (pre-2025 opening balance) is placed
    in the oldest bucket, keeping the reconciliation exact.
  * A customer whose net balance is a CREDIT is reported separately rather than
    netted off another customer's debt — see ``credit_rows`` in the output.

Output mirrors ``receivables.compute`` (so the dashboard consumes it unchanged),
with an added per-customer ``buckets`` breakdown for exact client-side aging.
"""
from __future__ import annotations

from datetime import date, datetime

import polars as pl

from . import config as C

_BUCKET_KEYS = [k for k, *_ in C.AGING_BUCKETS]


def _valid(nm) -> bool:
    """A usable display name: non-empty and not just digits/spaces."""
    return bool(nm) and not str(nm).strip().replace(" ", "").isdigit()


def _bucket_for_age(age_days: int) -> str:
    if age_days <= 30:
        return "d1_30"
    if age_days <= 60:
        return "d31_60"
    if age_days <= 90:
        return "d61_90"
    if age_days <= 120:
        return "d91_120"
    return "d120p"


def compute(invoices_full: pl.DataFrame, final_balances: dict,
            dim_customers: pl.DataFrame,
            net_terms: int = C.NET_TERMS_DAYS,
            as_of_str: str = C.AS_OF_DATE,
            cutoff_str: str = C.OVERDUE_CUTOFF,
            name_map: dict | None = None,
            rep_map: dict | None = None) -> dict:
    name_map = name_map or {}
    ext_rep = rep_map or {}
    as_of = date.fromisoformat(as_of_str)
    cutoff = date.fromisoformat(cutoff_str)

    # customer -> ordered invoice list [(date, amount)], and last date
    inv = invoices_full.with_columns(pl.col("customer_code").cast(pl.Utf8)).select(
        "customer_code", "invoice_no", "invoice_date", "reported_total")
    hist: dict[str, list] = {}
    for r in inv.iter_rows(named=True):
        hist.setdefault(r["customer_code"], []).append(
            (r["invoice_date"], float(r["reported_total"] or 0.0)))
    for v in hist.values():
        v.sort(key=lambda t: t[0])

    rep_map_dim = {str(r["customer_code"]): (r["rep"] or "غير محدد")
                   for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8))
                   .iter_rows(named=True)}

    buckets = {k: 0.0 for k in _BUCKET_KEYS}
    by_rep: dict[str, dict] = {}
    rows: list[dict] = []
    tot_current = tot_overdue = 0.0

    # Customers whose net balance is a CREDIT (the company owes them). They carry
    # no receivable to age, so they are kept out of the buckets — netting one
    # customer's credit against another's debt would understate the debt actually
    # out there — but they are counted and reported rather than dropped, because
    # the per-file printed net includes them and the two figures have to be
    # reconcilable: outstanding − credit == Σ printed net.
    credit_rows: list[dict] = []
    tot_credit = 0.0

    for code, meta in final_balances.items():
        B = float(meta["balance"] or 0.0)
        if B <= 0:
            if B < 0:
                tot_credit += -B
                credit_rows.append({
                    "customer_code": code,
                    "customer_name": name_map.get(code)
                    or (meta.get("name") if _valid(meta.get("name")) else None)
                    or f"عميل {code}",
                    "rep": ext_rep.get(code) or rep_map_dim.get(code)
                    or meta.get("rep_official") or meta.get("rep") or "غير محدد",
                    "credit_balance": round(-B, 2),
                })
            continue
        invs = hist.get(code, [])
        total_billed = sum(a for _d, a in invs)
        collected = max(0.0, total_billed - B)
        opening = max(0.0, B - total_billed)

        rem = collected
        cust_b = {k: 0.0 for k in _BUCKET_KEYS}
        cust_current = cust_overdue = 0.0
        oldest = None
        for d, a in invs:                       # oldest -> newest (FIFO paydown)
            pay = min(rem, a)
            rem -= pay
            unpaid = a - pay
            if unpaid <= 0.005:
                continue
            if d <= cutoff:                     # June-or-earlier unpaid => overdue
                age = (as_of - d).days
                cust_b[_bucket_for_age(age)] += unpaid
                cust_overdue += unpaid
                if oldest is None or d < oldest[0]:
                    oldest = (d, unpaid)
            else:                               # July => not yet due (current)
                cust_b["current"] += unpaid
                cust_current += unpaid
        if opening > 0.005:                     # pre-history debt => oldest bucket
            cust_b["d120p"] += opening
            cust_overdue += opening

        # corrected master mapping wins, then dim fallback, then debt-report rep
        rep = ext_rep.get(code) or rep_map_dim.get(code) or meta.get("rep_official") \
            or meta.get("rep") or "غير محدد"
        last_dt = max((d for d, _a in invs), default=None)
        old_age = (as_of - oldest[0]).days if oldest else None
        # Always display a real customer name — resolve from the authoritative
        # name map (dim_customers → debt detail → invoice history), then the
        # debt-report name. For the rare account that has NO name in any source
        # file, show an honest labelled placeholder ("عميل <code>") — never a
        # bare number, and never a fabricated name.
        cust_name = name_map.get(code) or (meta.get("name") if _valid(meta.get("name")) else None) \
            or f"عميل {code}"
        rows.append({
            "rep": rep,
            "customer_code": code,
            "customer_name": cust_name,
            "last_invoice_date": last_dt.isoformat() if last_dt else "",
            "outstanding": round(B, 2),
            "current": round(cust_current, 2),
            "overdue": round(cust_overdue, 2),
            "credit_balance": 0.0,
            "days_since_last": (as_of - last_dt).days if last_dt else None,
            "days_overdue": max(0, old_age - net_terms) if old_age is not None else 0,
            "bucket": max(cust_b, key=cust_b.get),          # dominant/oldest bucket for the table
            "buckets": {k: round(v, 2) for k, v in cust_b.items()},
            "oldest_invoice_date": oldest[0].isoformat() if oldest else "",
            "oldest_amount": round(oldest[1], 2) if oldest else 0.0,
        })
        for k in _BUCKET_KEYS:
            buckets[k] += cust_b[k]
        tot_current += cust_current
        tot_overdue += cust_overdue
        slot = by_rep.setdefault(rep, {"current": 0.0, "overdue": 0.0, "customers": 0})
        slot["current"] += cust_current
        slot["overdue"] += cust_overdue
        slot["customers"] += 1

    rows.sort(key=lambda x: x["outstanding"], reverse=True)
    total_out = tot_current + tot_overdue
    rep_rows = sorted(
        ({"rep": k, "current": round(v["current"], 2), "overdue": round(v["overdue"], 2),
          "outstanding": round(v["current"] + v["overdue"], 2), "customers": v["customers"]}
         for k, v in by_rep.items()),
        key=lambda x: x["outstanding"], reverse=True)

    return {
        "as_of": as_of_str,
        "total_outstanding": round(total_out, 2),
        "total_current": round(tot_current, 2),
        "total_overdue": round(tot_overdue, 2),
        "total_credit": round(tot_credit, 2),
        # outstanding − credit is the figure the source files print as «الصافى».
        "net_of_credit": round(total_out - tot_credit, 2),
        "credit_customers": len(credit_rows),
        "credit_rows": sorted(credit_rows, key=lambda x: -x["credit_balance"]),
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "bucket_labels": {key: label for key, label, *_ in C.AGING_BUCKETS},
        "by_rep": rep_rows,
        "rows": rows,
    }
