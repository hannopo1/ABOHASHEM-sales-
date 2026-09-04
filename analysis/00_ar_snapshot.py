#!/usr/bin/env python3
"""
Turn the per-representative customer account-balance PDFs into the AR snapshot
CSV the rest of the pipeline reads.

Why this step exists
--------------------
The AR snapshot used to be a hand-placed file, ``ar_customer_balances_2026-07-04.csv``,
and SIX pipeline steps named that file directly. So when newer balance reports
arrived, the executive dashboard (which parses the PDFs itself) moved on while
every step downstream of here stayed on 4 July — and the app ended up showing two
different debt totals two months apart, one per navigation group.

Now there is one generated file and one constant. A newer set of reports means
editing ``config.AR_SNAPSHOT_FILES`` and nothing else; the date travels with the
data instead of being baked into six filenames.

Source of truth is ``executive_dashboard/src/debt.py`` — the same parser the
dashboard uses, reconciled file by file against each report's printed «الصافى».

Output
------
  - data/processed/ar_customer_balances_current.csv
  - data/processed/ar_snapshot_log.json  (as_of, per-rep totals, reconciliation)
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "executive_dashboard"))

from src import config as C, debt as debt_mod  # noqa: E402

OUT_CSV = ROOT / "data" / "processed" / "ar_customer_balances_current.csv"
OUT_LOG = ROOT / "data" / "processed" / "ar_snapshot_log.json"

FIELDS = ["rep", "customer_code", "customer_name", "city", "phone",
          "debit", "credit", "as_of"]


def main():
    present = [(p, rep) for p, rep in C.AR_SNAPSHOT_FILES if p.exists()]
    if not present:
        raise SystemExit(
            "[00_ar_snapshot] none of the balance reports in "
            "config.AR_SNAPSHOT_FILES exist — refusing to write an empty AR "
            "snapshot over the one the pipeline reads.")

    balances = debt_mod.load_final_balances()      # aborts on a printed-net mismatch

    rows = []
    for code, meta in sorted(balances.items()):
        rows.append({
            "rep": meta["rep_official"] or meta["rep"] or "غير محدد",
            "customer_code": code,
            # A customer with no name in the report keeps the honest placeholder
            # used everywhere else, never a bare code and never an invented name.
            "customer_name": meta["name"] or f"عميل {code}",
            "city": meta["city"],
            "phone": meta["phone"],
            "debit": f"{meta['debit']:.2f}",
            "credit": f"{meta['credit']:.2f}",
            "as_of": C.AS_OF_DATE,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    by_rep = {}
    for r in rows:
        slot = by_rep.setdefault(r["rep"], {"customers": 0, "net": 0.0})
        slot["customers"] += 1
        slot["net"] = round(slot["net"] + float(r["debit"]) - float(r["credit"]), 2)

    net = round(sum(v["net"] for v in by_rep.values()), 2)
    printed = round(sum(debt_mod._printed_net(p) or 0.0 for p, _rep in present), 2)
    if abs(net - printed) > 0.02:
        raise SystemExit(
            f"[00_ar_snapshot] snapshot net {net:,.2f} != Σ printed net {printed:,.2f}")

    log = {
        "as_of": C.AS_OF_DATE,
        "reports": [p.name for p, _rep in present],
        "customers": len(rows),
        "net_balance": net,
        "printed_net": printed,
        "in_credit": sum(1 for r in rows
                         if float(r["debit"]) - float(r["credit"]) < 0),
        "by_rep": {k: by_rep[k] for k in sorted(by_rep)},
    }
    with open(OUT_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps(log, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
