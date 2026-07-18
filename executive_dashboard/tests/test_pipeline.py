"""
Pipeline unit tests — intentionally dependency-free (only the stdlib) so they run
on the stock CI image, which installs just flake8 + pytest.

They lock down the configurable collection-based bonus ladder, the single most
important business rule in the dashboard, at every tier boundary. Heavier,
data-driven checks (reconciliation, totals, aging) run inside ``build.py``'s
validation report against Polars, which is out of scope for the CI image.
"""
import sys
from pathlib import Path

import pytest

# Make ``src`` importable without installing the package.
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from src.config import (bonus_pct, BONUS_RULES,  # noqa: E402
                        COLLECTIONS_PRINTED_TOTAL, RETURNS_PRINTED_TOTAL,
                        PAYMENT_METHOD_KEYWORDS, PAYMENT_METHOD_DEFAULT)


def test_bonus_ladder_boundaries():
    """Each tier boundary maps to the documented bonus fraction."""
    assert bonus_pct(0.69) == 0.00
    assert bonus_pct(0.70) == 0.01
    assert bonus_pct(0.79) == 0.01
    assert bonus_pct(0.80) == 0.02
    assert bonus_pct(0.89) == 0.02
    assert bonus_pct(0.90) == 0.03
    assert bonus_pct(0.94) == 0.03
    assert bonus_pct(0.95) == 0.05
    assert bonus_pct(1.00) == 0.05


def test_bonus_handles_missing_rate():
    assert bonus_pct(None) == 0.0


def test_bonus_never_exceeds_top_tier():
    top = BONUS_RULES[-1][1]
    assert bonus_pct(2.0) == top
    assert all(pct <= top for _, pct in BONUS_RULES)


def test_bonus_rules_are_monotonic():
    thresholds = [t for t, _ in BONUS_RULES]
    pcts = [p for _, p in BONUS_RULES]
    assert thresholds == sorted(thresholds)
    assert pcts == sorted(pcts)


# --- collections / returns (stdlib-only config checks; always run) -----------
def test_printed_totals_are_positive():
    """The anti-fabrication anchors for the collections drill-down are present."""
    assert COLLECTIONS_PRINTED_TOTAL > 0
    assert RETURNS_PRINTED_TOTAL > 0
    assert COLLECTIONS_PRINTED_TOTAL == 22_177_149.68
    assert RETURNS_PRINTED_TOTAL == 435_830.63


def test_payment_method_keywords_shape():
    assert PAYMENT_METHOD_DEFAULT
    assert all(len(t) == 2 and t[0] and t[1] for t in PAYMENT_METHOD_KEYWORDS)


# --- collections / returns parsing (needs polars + pymupdf + source PDFs) -----
def _collections_module():
    pytest.importorskip("polars")
    pytest.importorskip("fitz")
    from src import collections as coll
    from src import config as C
    if not (C.SRC_COLLECTIONS_PDF.exists() and C.SRC_RETURNS_PDF.exists()):
        pytest.skip("source collections/returns PDFs not present")
    return coll, C


def test_collections_reconcile_to_printed_total():
    coll, C = _collections_module()
    df = coll.parse_collections()
    assert df.height == 1423
    assert abs(float(df["amount"].sum()) - C.COLLECTIONS_PRINTED_TOTAL) < 0.01


def test_returns_reconcile_to_printed_total():
    coll, C = _collections_module()
    df = coll.parse_returns()
    assert df.height == 156
    assert abs(float(df["value"].sum()) - C.RETURNS_PRINTED_TOTAL) < 0.01


def test_method_classification():
    coll, _ = _collections_module()
    assert coll._method("مدفوع منه فودافون كاش أ ساهر") == "فودافون كاش"
    assert coll._method("مدفوع منه نقدى") == "نقدي"
    assert coll._method("تحويل بنكي") == "تحويل بنكي"
    assert coll._method("بيان بلا طريقة") == PAYMENT_METHOD_DEFAULT


def test_attribution_reconciles_to_grand_total():
    coll, C = _collections_module()
    import build
    from src import load, debt  # noqa: F401
    dims = load.load_dimensions()
    _lines, invoices_full = load.parse_all()
    fb = debt.load_final_balances()
    name_map = build._name_map(dims["dim_customers"], invoices_full, dims["debt_detail"])
    rep_map = build._corrected_rep_map(fb, dims["dim_customers"], dims["debt_detail"])
    payload, collected, returns_by, reliable, stats = coll.compute(
        coll.parse_collections(), coll.parse_returns(),
        invoices_full, dims["dim_customers"], name_map, rep_map)
    a = payload["attribution"]
    assert a["receipts_matched"] + a["receipts_unmatched"] == a["receipts_total"]
    assert abs(sum(collected.values()) + a["unmatched_collected"]
               - payload["grand_total_collected"]) < 0.01
