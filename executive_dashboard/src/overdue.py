"""
Overdue-receivable analysis via FIFO allocation against the FINAL customer
balance (the as-of snapshot in config.AR_SNAPSHOT_FILES).

Method (standard AR FIFO — oldest paid first):
  * For each customer we take their full parsed invoice history and their final
    outstanding balance B from the snapshot.
  * Implied collections = total_billed - B are applied to the OLDEST invoices
    first; the unpaid residual therefore lands on the most recent invoices, and
    Σ unpaid reconciles EXACTLY to B.
  * Each still-open invoice gets a DUE DATE of its own: ``invoice date +
    config.NET_TERMS_DAYS``. It is OVERDUE once that due date has passed at the
    snapshot date, and CURRENT until then. The source invoices carry no due date,
    so this is company policy applied here — stated, not measured.
  * Overdue amounts are aged by DAYS PAST DUE, not by how old the invoice is.
    Balance in excess of the parsed history (pre-2025 opening balance) has no
    invoice and therefore no due date; it is placed in the oldest bucket and
    reported as its own figure, never dressed up with a fabricated due date.
  * A customer whose net balance is a CREDIT is reported separately rather than
    netted off another customer's debt — see ``credit_rows`` in the output.

Output mirrors ``receivables.compute`` (so the dashboard consumes it unchanged),
with an added per-customer ``buckets`` breakdown for exact client-side aging and
an ``overdue_invoices`` list — one row per still-open past-due invoice, which is
what the app's «المستحق والمتأخرات» section renders.

Why the cutoff is no longer a date
----------------------------------
This module used to compare each invoice against a hand-written
``config.OVERDUE_CUTOFF``. Set to 2026-07-31 against a 2026-09-03 snapshot it
granted 34 days of credit, not the 30 the company gives, and it had to be
retyped by hand with every new snapshot or silently drift further. The threshold
is now derived from the terms (``config.overdue_cutoff()``), so it moves with the
snapshot on its own.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl

from . import config as C

_BUCKET_KEYS = [k for k, *_ in C.AGING_BUCKETS]


def _valid(nm) -> bool:
    """A usable display name: non-empty and not just digits/spaces."""
    return bool(nm) and not str(nm).strip().replace(" ", "").isdigit()


# The past-due bands, read from config rather than retyped here. The ladder that
# used to live in this file disagreed with the one receivables.py reads out of
# config.AGING_BUCKETS — two spellings of one rule, which is one too many.
_PAST_DUE_BANDS = [(k, lo, hi) for k, _label, lo, hi in C.AGING_BUCKETS if hi > 0]


def _bucket_for_days_past_due(days_past_due: int) -> str:
    """Band an overdue amount by how many days it is PAST ITS DUE DATE.

    Ageing by invoice age instead put the freshest arrears a whole month too
    deep: with 30-day terms an invoice one day late is already 31 days old, so
    the "1-30" band could never receive anything and always read zero.
    """
    for key, lo, hi in _PAST_DUE_BANDS:
        if lo <= days_past_due <= hi:
            return key
    return _PAST_DUE_BANDS[-1][0]


def compute(invoices_full: pl.DataFrame, final_balances: dict,
            dim_customers: pl.DataFrame,
            net_terms: int = C.NET_TERMS_DAYS,
            as_of_str: str = C.AS_OF_DATE,
            name_map: dict | None = None,
            rep_map: dict | None = None) -> dict:
    name_map = name_map or {}
    ext_rep = rep_map or {}
    as_of = date.fromisoformat(as_of_str)
    terms = timedelta(days=net_terms)

    # customer -> ordered invoice list [(date, amount)], and last date
    inv = invoices_full.with_columns(pl.col("customer_code").cast(pl.Utf8)).select(
        "customer_code", "invoice_no", "invoice_date", "reported_total")
    # (date, amount, invoice_no) — the number is carried so a past-due invoice can
    # be named on the collections screen, not just counted.
    hist: dict[str, list] = {}
    for r in inv.iter_rows(named=True):
        hist.setdefault(r["customer_code"], []).append(
            (r["invoice_date"], float(r["reported_total"] or 0.0), r["invoice_no"]))
    for v in hist.values():
        v.sort(key=lambda t: t[0])

    rep_map_dim = {str(r["customer_code"]): (r["rep"] or "غير محدد")
                   for r in dim_customers.with_columns(pl.col("customer_code").cast(pl.Utf8))
                   .iter_rows(named=True)}

    buckets = {k: 0.0 for k in _BUCKET_KEYS}
    by_rep: dict[str, dict] = {}
    rows: list[dict] = []
    # One row per still-open invoice whose due date has passed. This is the list
    # the collections screen is built from, so it names the invoice rather than
    # only totalling it.
    overdue_invoices: list[dict] = []
    tot_current = tot_overdue = tot_opening = 0.0

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
        first_row = len(overdue_invoices)   # this customer's slice, for backfill
        invs = hist.get(code, [])
        total_billed = sum(a for _d, a, _n in invs)
        collected = max(0.0, total_billed - B)
        opening = max(0.0, B - total_billed)

        rem = collected
        cust_b = {k: 0.0 for k in _BUCKET_KEYS}
        cust_current = cust_overdue = 0.0
        oldest = None
        for d, a, no in invs:                   # oldest -> newest (FIFO paydown)
            pay = min(rem, a)
            rem -= pay
            unpaid = a - pay
            if unpaid <= 0.005:
                continue
            due = d + terms                     # company terms, not a source field
            if due < as_of:                     # the due date has passed => overdue
                dpd = (as_of - due).days
                bucket = _bucket_for_days_past_due(dpd)
                cust_b[bucket] += unpaid
                cust_overdue += unpaid
                if oldest is None or d < oldest[0]:
                    oldest = (d, unpaid)
                overdue_invoices.append({
                    "invoice_no": no,
                    "invoice_date": d.isoformat(),
                    "due_date": due.isoformat(),
                    "days_past_due": dpd,
                    "customer_code": code,
                    "rep": None,                # filled once the rep is resolved
                    "amount_open": round(unpaid, 2),
                    "bucket": bucket,
                })
            else:                               # still within terms
                cust_b["current"] += unpaid
                cust_current += unpaid
        if opening > 0.005:
            # Debt that predates the invoice history: no invoice, so no due date
            # and no age that could be measured. It is counted as overdue and put
            # in the oldest band, but it never enters overdue_invoices — inventing
            # a due date for it would be inventing data. It is reported on its own
            # in `opening_balance` below so the screen can say what it is.
            cust_b["d120p"] += opening
            cust_overdue += opening
            tot_opening += opening

        # corrected master mapping wins, then dim fallback, then debt-report rep
        rep = ext_rep.get(code) or rep_map_dim.get(code) or meta.get("rep_official") \
            or meta.get("rep") or "غير محدد"
        last_dt = max((d for d, _a, _n in invs), default=None)
        old_age = (as_of - oldest[0]).days if oldest else None
        # Always display a real customer name — resolve from the authoritative
        # name map (dim_customers → debt detail → invoice history), then the
        # debt-report name. For the rare account that has NO name in any source
        # file, show an honest labelled placeholder ("عميل <code>") — never a
        # bare number, and never a fabricated name.
        cust_name = name_map.get(code) or (meta.get("name") if _valid(meta.get("name")) else None) \
            or f"عميل {code}"
        # The per-invoice rows were appended before the rep and the display name
        # were resolved; stamp them now so every sheet names the same person the
        # customer table does.
        for oi in overdue_invoices[first_row:]:
            oi["rep"] = rep
            oi["customer_name"] = cust_name
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
    # Oldest money first: that is the order a collections call list is worked in.
    overdue_invoices.sort(key=lambda x: (-x["days_past_due"], -x["amount_open"]))
    total_out = tot_current + tot_overdue
    rep_rows = sorted(
        ({"rep": k, "current": round(v["current"], 2), "overdue": round(v["overdue"], 2),
          "outstanding": round(v["current"] + v["overdue"], 2), "customers": v["customers"]}
         for k, v in by_rep.items()),
        key=lambda x: x["outstanding"], reverse=True)

    return {
        "as_of": as_of_str,
        "net_terms_days": net_terms,
        # The last invoice date still within terms at as_of. Derived from the
        # terms, never typed, so it moves with the snapshot.
        "overdue_cutoff": (as_of - terms).isoformat(),
        "total_outstanding": round(total_out, 2),
        "total_current": round(tot_current, 2),
        "total_overdue": round(tot_overdue, 2),
        # Overdue splits in two: invoices we can name and date, and balance that
        # predates the invoice history and can be neither. Reported apart so the
        # screen never implies a due date it does not have.
        "overdue_invoices": overdue_invoices,
        "overdue_on_invoices": round(tot_overdue - tot_opening, 2),
        "opening_balance": round(tot_opening, 2),
        "overdue_invoice_count": len(overdue_invoices),
        "overdue_customers": len({o["customer_code"] for o in overdue_invoices}),
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
