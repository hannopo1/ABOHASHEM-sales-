"""Guards on the income-statement series (analysis/14_income_statements.py).

Dependency-free like test_margin.py: these read committed JSON, so they run on
the stock CI image. The document parsing itself is guarded inside
analysis/tools/extract_income_statements.py, which aborts rather than emit a
statement it cannot reconcile.

What matters here is that the two things this series must never confuse stay
separated:

  * measured months and the three allocated from the Q1 statement
  * a company-level margin and the per-item margin, which is still June-only
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "cost" / "income_statements.json"
OUT = ROOT / "data" / "processed" / "income_statements.json"
DASHBOARD = ROOT / "data" / "processed" / "margin_dashboard.json"

pytestmark = pytest.mark.skipif(
    not OUT.exists(),
    reason="statement outputs absent — run analysis/14_income_statements.py")

TOL = 1.0        # EGP, against the statements themselves
CENT = 0.011     # EGP, against our own rounded output

QUARTER = "2026-Q1"
QUARTER_MONTHS = ["2026-01", "2026-02", "2026-03"]

# The June statement as analysis/13_join_cost_margin.py carries it. Restated
# here rather than imported so a change to either file has to be made twice,
# deliberately, instead of propagating silently.
JUNE = {"net_sales": 3_741_772.00, "cogs": 2_039_933.08,
        "gross_profit": 1_701_838.92, "net_profit": 418_841.92}


@pytest.fixture(scope="module")
def out():
    return json.loads(OUT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def src():
    return json.loads(SRC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def months(out):
    return out["by_month"]


# ------------------------------------------------------- the source itself --

def test_every_observation_reconciles(src):
    """Each statement's own arithmetic, checked against what was committed."""
    for o in src["observations"]:
        assert abs(o["net_sales"] - o["cogs"] - o["gross_profit"]) <= TOL, \
            f"{o['period']}: net sales − cost of sales ≠ gross profit"
        assert abs(o["gross_profit"] - o["total_expenses"]
                   - o["net_profit"]) <= TOL, \
            f"{o['period']}: gross profit − expenses ≠ net profit"


def test_stated_percentages_match(src):
    """Where a statement prints its own ratio column, it must agree.

    This is the only independent check the documents give us on the figures
    above them, so it is worth asserting separately from the arithmetic.
    """
    checked = 0
    for o in src["observations"]:
        if o.get("stated_gross_margin_pct") is None:
            continue
        got = o["gross_profit"] / o["net_sales"] * 100
        assert abs(got - o["stated_gross_margin_pct"]) <= 0.02, o["period"]
        checked += 1
    assert checked >= 3, "expected the 2026 statements to carry a ratio column"


def test_june_ties_to_the_costing_model(src):
    """The anchor between the two repositories.

    If this fails, the statements and analysis/13_join_cost_margin.py no longer
    describe the same month, and no margin figure in this repository can be
    trusted until that is resolved.
    """
    june = next(o for o in src["observations"] if o["period"] == "2026-06")
    for key, want in JUNE.items():
        assert abs(june[key] - want) <= TOL, \
            f"June {key}: statements say {june[key]}, the costing model {want}"


def test_thirteen_months_from_eleven_observations(src, out):
    assert len(src["observations"]) == 11
    assert sum(o["months"] for o in src["observations"]) == 13
    assert out["totals"]["months"] == 13
    assert len(out["by_month"]) == 13


# ------------------------------------------------------------ the series ----

def test_monthly_identities_hold_after_rounding(months):
    """Published figures, not intermediates, must satisfy the identities."""
    for r in months:
        assert round(r["net_sales"] - r["cogs"], 2) == r["gross_profit"], \
            r["period"]
        assert round(r["gross_profit"] - r["total_expenses"], 2) \
            == r["net_profit"], r["period"]


def test_quarter_allocation_sums_back(src, months):
    """The three allocated months must reconstitute the quarter exactly.

    An allocation that does not add up to its own source would be worse than
    no allocation: it would put a number in front of a reader that no document
    supports.
    """
    q = next(o for o in src["observations"] if o["period"] == QUARTER)
    parts = [r for r in months if r["source_period"] == QUARTER]
    assert [r["period"] for r in parts] == QUARTER_MONTHS
    for f in ("net_sales", "cogs", "gross_profit", "total_expenses",
              "net_profit"):
        assert abs(sum(r[f] for r in parts) - q[f]) <= CENT, f


def test_allocated_months_are_labelled(months):
    """Nothing derived may travel without saying it is derived."""
    for r in months:
        if r["period"] in QUARTER_MONTHS:
            assert r["basis"] == "allocated" and r["estimated"] is True
            assert r["source_period"] == QUARTER
            assert r["allocation_weight"] is not None
        else:
            assert r["basis"] == "measured" and r["estimated"] is False
            assert r["allocation_weight"] is None


def test_allocation_carries_no_within_quarter_margin_signal(months):
    """A pro-rata split cannot invent variation it was not given.

    All three months necessarily carry the quarter's ratio, so the series must
    never be read as evidence about how margin moved inside Q1. Asserted so
    that a future change which appears to add such variation is challenged
    rather than believed.
    """
    parts = [r for r in months if r["source_period"] == QUARTER]
    ratios = {r["gross_margin_pct"] for r in parts}
    assert len(ratios) == 1


def test_weights_are_a_partition(months):
    parts = [r for r in months if r["source_period"] == QUARTER]
    assert abs(sum(r["allocation_weight"] for r in parts) - 1.0) <= 1e-5
    assert all(0 < r["allocation_weight"] < 1 for r in parts)


def test_totals_match_the_series(out, months):
    t = out["totals"]
    for f in ("net_sales", "cogs", "gross_profit", "net_profit"):
        assert abs(sum(r[f] for r in months) - t[f]) <= CENT, f
    assert abs(t["gross_profit"] / t["net_sales"] * 100
               - t["gross_margin_pct"]) <= 0.01
    assert t["n_allocated_months"] == 3


def test_no_month_shows_a_negative_gross_margin(months):
    """The finding that supersedes the excluded basis.

    Charging June-2026 unit costs against 2025 revenue produced a −2.13%
    operating margin, which the price index argued was an artefact. The
    statements measure those months: if any of them really were negative, that
    argument would collapse and every conclusion drawn from it would need
    revisiting.
    """
    for r in months:
        assert r["gross_margin_pct"] > 0, r["period"]


# --------------------------------------------------------- what it is not ---

def test_statements_do_not_widen_the_per_item_window(out):
    """Company-level cost must not be mistaken for per-SKU cost."""
    assert out["meta"]["level"] == "company"
    dash = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dash["meta"]["cost_month"] == "2026-06", \
        "per-item margin is still measured for one month only"
    assert len(dash["statements"]["by_month"]) == 13


def test_the_two_windows_are_stated_separately(out):
    """Sales run 2025-01..2026-06, statements 2025-07..2026-07.

    Neither window may be described by the other: six months of sales have no
    statement, and July 2026 has a statement with no invoices behind it.
    """
    meta = out["meta"]
    assert meta["sales_window"] == "2025-01..2026-06"
    assert meta["statement_window"] == "2025-07..2026-07"
    assert meta["statement_window"] != meta["sales_window"]
