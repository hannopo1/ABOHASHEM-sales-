"""The AR snapshot the whole pipeline reads must be current and reconciled.

Six pipeline steps used to name a dated file, `ar_customer_balances_2026-07-04.csv`.
When newer balance reports arrived the executive dashboard moved on — it parses the
PDFs itself — and everything downstream stayed on 4 July, so the app showed one debt
figure under «المديونية والتحصيل» and a two-month-old one under «التحليل».

These tests pin the property that broke: the generated snapshot is the CURRENT one,
it reconciles to the reports' own printed totals, and its date travels with it.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "ar_customer_balances_current.csv"
sys.path.insert(0, str(ROOT / "executive_dashboard"))


@pytest.fixture(scope="module")
def rows():
    if not CSV_PATH.exists():
        pytest.skip("AR snapshot not generated (run analysis/00_ar_snapshot.py)")
    with open(CSV_PATH, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def cfg():
    pytest.importorskip("polars")
    from src import config as C
    return C


def test_every_row_is_stamped_with_the_snapshot_date(rows, cfg):
    """The date travels with the data, so no label can quote a different one."""
    assert rows, "AR snapshot is empty"
    stamps = {r["as_of"] for r in rows}
    assert stamps == {cfg.AS_OF_DATE}, stamps


def test_snapshot_reconciles_to_the_printed_nets(rows, cfg):
    """Σ(debit − credit) equals the «الصافى» the source reports print."""
    pytest.importorskip("fitz")
    from src import debt as debt_mod
    parsed = round(sum(float(r["debit"]) - float(r["credit"]) for r in rows), 2)
    printed = round(sum(debt_mod._printed_net(p) or 0.0
                        for p, _rep in cfg.AR_SNAPSHOT_FILES if p.exists()), 2)
    assert abs(parsed - printed) < 0.02, f"{parsed:,.2f} vs {printed:,.2f}"


def test_no_customer_appears_twice(rows):
    """One row per customer — a duplicate would double-count a balance."""
    codes = [r["customer_code"] for r in rows]
    assert len(codes) == len(set(codes))


def test_no_row_carries_a_bare_code_as_its_name(rows):
    """A nameless customer is labelled «عميل <code>», never left blank."""
    for r in rows:
        nm = (r["customer_name"] or "").strip()
        assert nm and not nm.replace(" ", "").isdigit(), r


def test_snapshot_date_is_not_the_balance_date(cfg):
    """The edition date and the date the money was counted are separate fields.

    Collapsing them would re-date the balances to a day nobody counted them on.
    """
    assert cfg.SNAPSHOT_DATE != cfg.AS_OF_DATE
    assert cfg.SNAPSHOT_DATE > cfg.AS_OF_DATE
