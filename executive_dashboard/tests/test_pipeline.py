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

# COLLECTIONS_PRINTED_TOTAL / RETURNS_PRINTED_TOTAL are deliberately NOT imported
# here: they are filled in at parse time now, so a module-level import binds None.
from src.config import (bonus_pct, BONUS_RULES,  # noqa: E402
                        PAYMENT_METHOD_KEYWORDS, PAYMENT_METHOD_DEFAULT,
                        DEBT_CODE_ALIASES, canonical_code, clean_item_name)


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
def test_printed_totals_are_declared_per_source():
    """The anti-fabrication anchors for the collections drill-down are present.

    They used to be two module constants. They are now one printed total per
    source file, because the receipts arrive as a cumulative run plus month-only
    re-runs and a single constant went stale the moment a month was added.
    """
    from src.config import SRC_COLLECTIONS, SRC_RETURNS, SRC_RETURNS_ITEMISED
    sources = SRC_COLLECTIONS + SRC_RETURNS + SRC_RETURNS_ITEMISED
    assert sources, "no collections/returns sources declared"
    for path, month, printed in sources:
        assert printed > 0, path.name
        assert month is None or len(month) == 7, path.name
    # Exactly one cumulative (month=None) source per family; the rest own a month.
    for family in (SRC_COLLECTIONS, SRC_RETURNS):
        assert sum(1 for _p, m, _t in family if m is None) == 1
    # A month may be owned once per family — receipts and returns are separate
    # ledgers — but never twice within one, which would make the winner depend
    # on list order rather than on a decision.
    for family in (SRC_COLLECTIONS, SRC_RETURNS + SRC_RETURNS_ITEMISED):
        owned = [m for _p, m, _t in family if m]
        assert len(owned) == len(set(owned)), f"two files claim the same month: {owned}"


def test_payment_method_keywords_shape():
    assert PAYMENT_METHOD_DEFAULT
    assert all(len(t) == 2 and t[0] and t[1] for t in PAYMENT_METHOD_KEYWORDS)


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
    if not all(p.exists() for p, _m, _t in C.SRC_COLLECTIONS + C.SRC_RETURNS):
        pytest.skip("source collections/returns PDFs not present")
    return coll, C


def test_each_collections_file_reconciles_to_its_own_printed_total():
    """The per-file anchor: every source must reproduce the total it prints.

    Asserted file by file rather than on the concatenated frame, because the
    supersede rule drops rows — a total that only balances after superseding
    would hide a parser that lost a page from a file it then discarded.
    """
    coll, C = _collections_module()
    for path, _month, printed in C.SRC_COLLECTIONS:
        df = coll._parse_collections_file(path)
        assert abs(float(df["amount"].sum()) - printed) < 0.01, path.name
    for path, _month, printed in C.SRC_RETURNS:
        df = coll._parse_returns_file(path)
        assert abs(float(df["value"].sum()) - printed) < 0.01, path.name
    for path, _month, printed in C.SRC_RETURNS_ITEMISED:
        df = coll._parse_returns_itemised_file(path)
        assert abs(float(df["value"].sum()) - printed) < 0.01, path.name


def test_superseded_months_are_not_double_counted():
    """July appears in both the cumulative receipts file (to the 18th) and the
    whole-month one. Only the whole-month figure may survive."""
    coll, C = _collections_module()
    df = coll.parse_collections()
    july = df.filter(df["month"] == "2026-07")
    owner = next(t for p, m, t in C.SRC_COLLECTIONS if m == "2026-07")
    assert abs(float(july["amount"].sum()) - owner) < 0.01
    # and the month totals must still sum to the whole
    assert abs(float(df["amount"].sum()) - C.COLLECTIONS_PRINTED_TOTAL) < 0.01


def test_returns_itemised_rolls_up_without_inflating_the_month():
    """August returns arrive per ITEM; rolling them to credit-note grain must not
    change the month's value, only its row count."""
    coll, C = _collections_module()
    items = coll.parse_returns_itemised()
    if items.height == 0:
        pytest.skip("no itemised returns source")
    rolled = coll.parse_returns().filter(coll.pl.col("month") == "2026-08")
    assert abs(float(items["value"].sum()) - float(rolled["value"].sum())) < 0.01
    assert rolled.height < items.height


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
