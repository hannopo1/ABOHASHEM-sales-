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
                        PAYMENT_METHOD_KEYWORDS, PAYMENT_METHOD_DEFAULT,
                        DEBT_CODE_ALIASES, canonical_code, clean_item_name,
                        clean_customer_name)


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


def test_payment_default_is_vodafone_and_bank_captured():
    """Unidentified receipts default to Vodafone cash; cheques/deposits and the
    common misspellings are captured explicitly."""
    assert PAYMENT_METHOD_DEFAULT == "فودافون كاش"
    kw = dict(PAYMENT_METHOD_KEYWORDS)
    assert kw.get("شيك") == "شيك / إيداع بنكي"
    assert kw.get("فوادفون") == "فودافون كاش"      # misspelling → vodafone
    assert kw.get("انيتا") == "إنستا باي"


def test_clean_customer_name_unifies_variants():
    # alef-maqsura → yaa, whitespace collapsed, tatweel dropped (ta-marbuta kept)
    assert clean_customer_name("مصطفى عز السماعيلية") == "مصطفي عز السماعيلية"
    assert clean_customer_name("ثلجة  الصفا   قويسنا") == "ثلجة الصفا قويسنا"
    assert clean_customer_name("ابو هـاشم") == "ابو هاشم"


def test_clean_item_name_unifies_variants():
    """Spelling variants of the same product normalise to one label."""
    variants = ["سجق شرقى 3 ك ابو هاشم", "سجق شرقي 3 ك ابو هاشم",
                "سجق شرقى 3 كـ ابو هاشم"]
    assert len({clean_item_name(v) for v in variants}) == 1
    assert clean_item_name("سجق شرقى 3 ك ابو هاشم") == "سجق شرقي 3 ك ابو هاشم"
    assert clean_item_name("كفته اسبيشيال عائلى") == "كفته اسبشيال عائلي"
    assert clean_item_name("مفروم  صافى   400") == "مفروم صافي 400"


def test_canonical_code_strips_comma_and_aliases():
    """Codes ≥1000 are comma-formatted in invoices but plain in the debt report;
    canonical_code unifies them (and applies the +1000 alias)."""
    assert canonical_code("1,003") == "1003"      # comma stripped -> joins debt 1003
    assert canonical_code("1003") == "1003"
    assert canonical_code("1,007") == "007"        # comma stripped + aliased to 007
    assert canonical_code("1007") == "007"
    assert canonical_code("438") == "438"          # ordinary code untouched
    assert canonical_code("007") == "007"


def test_debt_code_aliases_are_plus_1000_offsets():
    """Every alias re-keys a +1000 debt code onto its base invoice code."""
    assert DEBT_CODE_ALIASES
    for dcode, icode in DEBT_CODE_ALIASES.items():
        assert dcode.isdigit() and icode.isdigit()
        assert int(dcode) - int(icode) == 1000
        assert dcode != icode


def test_debt_aliases_reage_onto_invoice_codes():
    """After the alias correction, the re-keyed balances land on codes that
    actually carry invoices (so they age correctly instead of as orphans)."""
    coll, C = _collections_module()  # reuses the polars/pymupdf/PDF guard
    from src import debt, load
    import polars as pl
    fb = debt.load_final_balances()
    if not fb:
        pytest.skip("debt snapshot PDFs not present")
    _l, invoices_full = load.parse_all()
    inv_codes = set(invoices_full.with_columns(
        pl.col("customer_code").cast(pl.Utf8))["customer_code"].unique().to_list())
    # No +1000 alias source code should survive in the balances…
    for dcode, icode in C.DEBT_CODE_ALIASES.items():
        assert dcode not in fb
        # …and its target invoice code exists in the invoice history.
        assert icode in inv_codes


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
