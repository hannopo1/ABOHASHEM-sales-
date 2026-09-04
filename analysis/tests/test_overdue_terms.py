"""
The 30-day due-date rule, tested at its boundaries.

The rule the company grants is: an invoice falls due NET_TERMS_DAYS after the day
it was issued, and is overdue once that day has passed. What the code used to do
instead was compare every invoice against a date typed into config by hand —
2026-07-31 against a 2026-09-03 snapshot, which is 34 days of credit, not 30, and
which had to be retyped with every new snapshot or drift further.

These tests pin the rule to the terms rather than to a date, so the same defect
cannot be reintroduced by editing a literal.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "executive_dashboard"))

# config imports only re/datetime/pathlib, so it loads anywhere — which keeps the
# rule tests (derived cutoff, the 30/31-day boundary) running on a bare CI runner.
# overdue.py pulls in polars, so it is imported inside the tests that need it,
# behind importorskip — the same shape test_ar_snapshot.py uses. Importing it at
# module level made collection fail outright and took the whole suite down with it.
from src import config as C  # noqa: E402


def _overdue_mod():
    pytest.importorskip("polars")
    from src import overdue as overdue_mod
    return overdue_mod


def test_cutoff_is_derived_from_the_terms_not_typed():
    """The overdue threshold must follow AS_OF_DATE and the terms, always."""
    assert not hasattr(C, "OVERDUE_CUTOFF"), (
        "a hand-written cutoff is back in config; it goes stale with every "
        "snapshot — derive it from AS_OF_DATE and NET_TERMS_DAYS instead")
    as_of = date.fromisoformat(C.AS_OF_DATE)
    assert C.overdue_cutoff() == as_of - timedelta(days=C.NET_TERMS_DAYS)


def test_cutoff_follows_a_different_as_of():
    """Move the snapshot and the threshold moves with it, with no edit."""
    assert C.overdue_cutoff("2026-10-31") == date(2026, 10, 1)
    assert C.overdue_cutoff("2025-01-15") == date(2024, 12, 16)


def test_due_date_is_invoice_date_plus_the_terms():
    assert C.due_date(date(2026, 8, 3)) == date(2026, 9, 2)
    assert C.due_date(date(2026, 1, 31)) == date(2026, 3, 2)      # crosses months


@pytest.mark.parametrize("age_days, overdue", [
    (0, False),      # issued today
    (29, False),
    (30, False),     # due exactly today — not yet past due
    (31, True),      # one day late
    (400, True),
])
def test_overdue_boundary_is_exactly_the_terms(age_days, overdue):
    """Due today is CURRENT; due yesterday is OVERDUE. No fencepost slack."""
    as_of = date.fromisoformat(C.AS_OF_DATE)
    invoice_date = as_of - timedelta(days=age_days)
    assert (C.due_date(invoice_date) < as_of) is overdue


def test_bands_come_from_config_not_a_second_ladder():
    """One spelling of the aging ladder, in config, read by everyone."""
    from_config = [(k, lo, hi) for k, _lbl, lo, hi in C.AGING_BUCKETS if hi > 0]
    assert _overdue_mod()._PAST_DUE_BANDS == from_config


@pytest.mark.parametrize("days_past_due, bucket", [
    (1, "d1_30"),      # the band that was structurally empty when ageing ran
    (30, "d1_30"),     # from the invoice date instead of the due date
    (31, "d31_60"),
    (60, "d31_60"),
    (61, "d61_90"),
    (90, "d61_90"),
    (91, "d91_120"),
    (120, "d91_120"),
    (121, "d120p"),
    (5000, "d120p"),
])
def test_bucket_is_chosen_by_days_past_due(days_past_due, bucket):
    assert _overdue_mod()._bucket_for_days_past_due(days_past_due) == bucket


def test_the_first_band_can_actually_be_reached():
    """Ageing from the invoice date made "1-30" unreachable by construction.

    With 30-day terms the youngest overdue invoice is 31 days old, so measuring
    from the invoice date could never place anything in the first band — it read
    zero on every screen while the freshest arrears were reported a month worse
    than they were.
    """
    as_of = date.fromisoformat(C.AS_OF_DATE)
    one_day_late = as_of - timedelta(days=C.NET_TERMS_DAYS + 1)
    dpd = (as_of - C.due_date(one_day_late)).days
    assert dpd == 1
    assert _overdue_mod()._bucket_for_days_past_due(dpd) == "d1_30"
