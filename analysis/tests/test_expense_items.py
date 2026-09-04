"""The expense line items: what they must add up to, and what they must not say.

The six 2025 income statements list every expense item by hand. Reading them out
is worth doing only if the reading can be trusted, and there are exactly three
ways it could lie:

  1. Items that do not add up to the group total the statement printed — a
     breakdown that contradicts the document it came from.
  2. Items where the source has none — an allocated quarter split into three
     months, or a month that filed no statement at all, given a breakdown by
     inference. Allocation divides magnitudes; it does not create line items.
  3. A merge that quietly moves money — two different items collapsed into one
     name, or a name that spans two expense groups so an administrative salary
     and a selling salary become the same figure.

Each of those has a test here. lib.statements and lib.expense_aliases are
standard library only, so these run on a bare CI runner; nothing here needs
polars, openpyxl, or the cost repository.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))

from lib import expense_aliases as A          # noqa: E402
from lib import statements as S               # noqa: E402

SRC = ROOT / "data" / "cost" / "income_statements.json"
DASH = ROOT / "data" / "processed" / "margin_dashboard.json"
TOL = 1.0                                     # EGP


def _rows():
    if not SRC.exists():
        pytest.skip("the vendored income statements are not in this checkout")
    _meta, rows = S.series()
    return rows


def _detail():
    return [r for r in _rows() if r["has_item_detail"]]


# ------------------------------------------------------- the items add up ----

def test_six_months_carry_line_items():
    """Item detail exists for exactly the months whose source lists items.

    Counted, not asserted against a literal: a seventh detailed month arriving
    should widen the app, not fail this test. What would fail it is the detail
    disappearing.
    """
    detail = _detail()
    assert len(detail) >= 6
    assert all(r["basis"] == "measured" for r in detail)
    assert all(r["expense_items"] for r in detail)


def test_items_sum_to_the_group_total_the_statement_printed():
    for r in _detail():
        for group, total in (r["expenses"] or {}).items():
            got = sum(i["amount"] for i in r["expense_items"]
                      if i["group"] == group)
            assert abs(got - total) <= TOL, (
                f"{r['period']} {group}: items {got:,.2f} vs statement "
                f"{total:,.2f}")


def test_groups_sum_to_total_expenses():
    """The three groups are the whole of operating expenses, not part of it."""
    for r in _detail():
        got = sum((r["expenses"] or {}).values())
        assert abs(got - r["total_expenses"]) <= TOL, r["period"]


def test_july_2025_matches_the_source_to_the_piastre():
    """One month pinned outright, as a tripwire under everything above.

    Every other test compares the data against itself. This one compares it
    against the file: if the whole extraction shifted by a column, the internal
    identities would still hold and only this test would notice.
    """
    r = next(x for x in _rows() if x["period"] == "2025-07")
    assert r["expenses"] == pytest.approx(
        {"admin": 463_487.0, "selling": 259_384.0, "financing": 126_120.0})
    assert r["total_expenses"] == pytest.approx(848_991.0)


# ---------------------------------------------- and never claim more ---------

def test_no_allocated_month_carries_line_items():
    """Splitting a quarter's total three ways does not produce three breakdowns."""
    for r in _rows():
        if r["basis"] == "allocated":
            assert r["expense_items"] == []
            assert r["has_item_detail"] is False
            # None, not {}: the groups are unknown for these months, and an
            # empty dict would render as three zeroes.
            assert r["expenses"] is None


def test_a_month_with_no_statement_is_absent_not_zero():
    """August 2026 filed no income statement, so it has no expense row at all."""
    periods = [r["period"] for r in _rows()]
    assert "2026-08" not in periods
    assert "2026-07" in periods                     # the series really does end there


def test_total_only_months_say_so_rather_than_showing_zeroes():
    for r in _rows():
        if not r["has_item_detail"]:
            assert r["expense_items"] == []
            assert r["expenses"] is None
            # The total itself is measured and must survive — it is the figure
            # net profit is computed from.
            assert r["total_expenses"] > 0


# ------------------------------------------------------------- the aliases ---

def test_every_alias_has_a_canonical_name():
    for (group, raw), canon in A.ALIASES.items():
        assert group in ("admin", "selling", "financing")
        assert raw and canon
        assert raw != canon, "an alias that changes nothing is noise"


def test_no_canonical_name_spans_two_groups():
    """An administrative «مرتبات» and a selling «مرتبات» are different money.

    The map is keyed by (group, raw) so it cannot merge across groups by
    accident, but it could still be written to send two groups' spellings to the
    same canonical name. That would make one bar out of two unrelated costs.
    """
    groups_of = {}
    for (group, _raw), canon in A.ALIASES.items():
        groups_of.setdefault(canon, set()).add(group)
    for canon, groups in groups_of.items():
        assert len(groups) == 1, f"«{canon}» is a merge target in {sorted(groups)}"


def test_a_merge_never_collides_inside_one_month():
    """Two items in the same month under one canonical name would be a wrong merge.

    The evidence for every merge in the map is that the spellings are
    complementary — each month carries exactly one of them, which is what a
    renaming looks like. If two ever co-occur they were different items and the
    merge silently added them together.
    """
    for r in _detail():
        seen = {}
        for it in r["expense_items"]:
            key = (it["group"], it["label"])
            assert key not in seen, (
                f"{r['period']}: «{it['label']}» appears twice "
                f"({seen.get(key)} and {it['label_raw']})")
            seen[key] = it["label_raw"]


def test_the_raw_label_always_travels_with_the_row():
    """The merge is a human judgement; the reader must be able to see it."""
    for r in _detail():
        for it in r["expense_items"]:
            if it["label_raw"]:
                assert it["label"] == A.canonical(it["group"], it["label_raw"])
            else:
                # A figure the sheet counted under no name at all. It stays —
                # the group total needs it — but it says so instead of showing
                # a blank row, and a nameless zero would have been dropped
                # upstream as the empty cell it is.
                assert it["label"] == S.UNNAMED_ITEM
                assert it["amount"] != 0


# --------------------------------------------------------- what ships ------

def test_the_app_payload_carries_the_expense_block():
    if not DASH.exists():
        pytest.skip("margin_dashboard.json is not in this checkout")
    d = json.loads(DASH.read_text(encoding="utf-8"))
    exp = d["statements"]["expenses"]
    cov = exp["coverage"]
    assert cov["months_with_item_detail"] == len(cov["item_detail_periods"])
    assert cov["n_items"] == sum(len(r["expense_items"])
                                 for r in d["statements"]["by_month"])
    assert "2026-08" in cov["no_statement_periods"]
    assert exp["aliases"], "the alias table must ship — the merge is shown, not hidden"


def test_rows_outside_the_group_totals_are_reported_not_folded_in():
    """Sheet rows that no group total counted are a finding, not a number to add.

    They exist: three labels across five of the six months. They must reach the
    payload so a reader can see them, and must NOT appear inside the items,
    where they would break the reconciliation with net profit.
    """
    if not DASH.exists():
        pytest.skip("margin_dashboard.json is not in this checkout")
    d = json.loads(DASH.read_text(encoding="utf-8"))
    outside = d["statements"]["expenses"]["rows_outside_totals"]
    for row in outside:
        assert row["period"] and row["label_raw"]
    by_period = {}
    for r in d["statements"]["by_month"]:
        by_period[r["period"]] = {(i["group"], i["label_raw"], i["amount"])
                                  for i in r["expense_items"]}
    for row in outside:
        for group in ("admin", "selling", "financing"):
            assert (group, row["label_raw"], row["amount"]) not in \
                by_period.get(row["period"], set())
