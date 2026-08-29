"""Guards on the calibrated monthly margin (analysis/13_join_cost_margin.py).

Dependency-free like the sibling test files: these read committed CSV and JSON,
so they run on the stock CI image.

The calibrated basis is the weakest of the three the app publishes, and it is
the one most easily misread as a measurement. So what these tests defend is not
the arithmetic alone but the boundaries around it:

  * every calibrated month reproduces its own income statement, or the figure
    has no claim to be calibrated at all
  * the cost month is untouched, so level two and level three cannot disagree
    about June
  * months with no statement appear nowhere
  * the three Q1-2026 months keep the estimated flag they inherited
  * item, customer and representative are the same lines cut three ways
"""
import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data" / "processed"
DASHBOARD = P / "margin_dashboard.json"
SUMMARY = P / "margin_summary.json"
STATEMENTS = P / "income_statements_by_month.csv"

pytestmark = pytest.mark.skipif(
    not (DASHBOARD.exists() and STATEMENTS.exists()),
    reason="margin outputs absent — run analysis/13_join_cost_margin.py")

COST_MONTH = "2026-06"
QUARTER_MONTHS = {"2026-01", "2026-02", "2026-03"}
# Invoices start here; the statements do not begin until July 2025, so these
# months can never be calibrated.
NO_STATEMENT = {"2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"}

PCT_TOL = 0.01      # percentage points, against the published rounding
CENT = 0.02         # EGP, against our own rounded output


def _load(name):
    with (P / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def dash():
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stmt():
    return {r["period"]: r for r in _load("income_statements_by_month.csv")}


@pytest.fixture(scope="module")
def cuts():
    return {"item": _load("margin_by_item_month.csv"),
            "customer": _load("margin_by_customer_month.csv"),
            "rep": _load("margin_by_rep_month.csv")}


def _by_month(rows, field):
    out = {}
    for r in rows:
        out[r["month"]] = out.get(r["month"], 0.0) + float(r[field])
    return out


# ------------------------------------------------------- the calibration ties

def test_every_calibrated_month_reproduces_its_statement(cuts, stmt):
    """Gross and net margin per month must equal the income statement's.

    This is the whole claim the calibrated basis makes. If it fails, the rows
    are June costs on another month's quantities — the very artefact the price
    gate exists to keep out of sight.
    """
    rev = _by_month(cuts["item"], "revenue")
    gp = _by_month(cuts["item"], "gross_profit")
    op = _by_month(cuts["item"], "op_profit")
    assert rev, "no calibrated months emitted"
    for m in sorted(rev):
        assert m in stmt, f"{m} has no income statement but was calibrated"
        assert gp[m] / rev[m] * 100 == pytest.approx(
            float(stmt[m]["gross_margin_pct"]), abs=PCT_TOL), m
        assert op[m] / rev[m] * 100 == pytest.approx(
            float(stmt[m]["net_margin_pct"]), abs=PCT_TOL), m


def test_cost_month_factors_are_exactly_one(dash):
    """June is measured, not calibrated. Scaling it would move level two."""
    cal = dash["calibration"]
    june = next(r for r in cal["by_month"] if r["month"] == COST_MONTH)
    assert june["k_cogs"] == 1.0
    assert june["k_opex"] == 1.0
    assert june["basis"] == "measured"


def test_cost_month_agrees_with_the_june_detail(dash):
    """Level three's June must equal level two's June, to the piastre.

    Two different code paths compute it — agg() and agg_monthly() — and the
    reader is told they describe the same month.
    """
    rows = [r for r in dash["by_item_month"] if r["month"] == COST_MONTH]
    assert rows, "the cost month is missing from the monthly cut"
    measured = dash["totals"]["measured"]
    for field in ("revenue_costed", "gross_profit", "op_profit"):
        key = "revenue" if field == "revenue_costed" else field
        assert sum(r[key] for r in rows) == pytest.approx(
            measured[field], abs=CENT), field


# ------------------------------------------------------------- the boundaries

def test_months_without_a_statement_are_absent(cuts):
    for name, rows in cuts.items():
        months = {r["month"] for r in rows}
        assert not (months & NO_STATEMENT), (
            f"{name}: emitted months with no income statement to calibrate on")


def test_quarter_months_keep_the_estimated_flag(cuts):
    for name, rows in cuts.items():
        for r in rows:
            want = r["month"] in QUARTER_MONTHS
            got = str(r["estimated"]).strip().lower() == "true"
            assert got == want, f"{name} {r['month']}: estimated={r['estimated']}"


def test_every_row_carries_a_basis(dash):
    for key in ("by_item_month", "by_customer_month", "by_rep_month"):
        for r in dash[key]:
            assert r["basis"] in ("measured", "calibrated"), (key, r)
            assert isinstance(r["estimated"], bool), (key, r)


def test_calibrated_window_is_the_intersection(dash):
    """Invoices 2025-01..2026-06, statements 2025-07..2026-07 -> twelve months."""
    months = dash["calibration"]["months"]
    assert months == sorted(months)
    assert months[0] == "2025-07" and months[-1] == COST_MONTH
    assert len(months) == 12
    assert dash["calibration"]["estimated_months"] == sorted(QUARTER_MONTHS)


# --------------------------------------------------------------- the identity

def test_the_three_cuts_are_the_same_lines(cuts):
    """Item, customer and rep partition one set of invoice lines."""
    ref = _by_month(cuts["item"], "gross_profit")
    for name in ("customer", "rep"):
        other = _by_month(cuts[name], "gross_profit")
        assert set(other) == set(ref), name
        for m in ref:
            assert other[m] == pytest.approx(ref[m], abs=CENT), (name, m)


def test_summary_and_dashboard_agree(dash):
    """The PDF reads margin_summary.json, the app reads margin_dashboard.json."""
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))["calibration"]
    assert s["months"] == dash["calibration"]["months"]
    assert s["estimated_months"] == dash["calibration"]["estimated_months"]


def test_absent_statements_disable_calibration_rather_than_failing():
    """A checkout without the vendored extract must still produce margin.

    The extract is committed, so this path is not exercised by a normal run —
    which is exactly why it needs a test. Without it the first person to clone
    the repo before the statements landed would get a hard failure from a step
    that used to work.
    """
    import importlib.util
    import sys

    path = ROOT / "analysis" / "lib" / "statements.py"
    spec = importlib.util.spec_from_file_location("_stmt_probe", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stmt_probe"] = mod
    spec.loader.exec_module(mod)
    try:
        assert mod.ratios() is not None, "the vendored extract should be present"
        mod.SRC = ROOT / "data" / "cost" / "does-not-exist.json"
        assert mod.ratios() is None
    finally:
        sys.modules.pop("_stmt_probe", None)


def test_calibration_is_documented_as_not_a_measurement():
    """The caveat naming the method's limit must survive in the payload.

    Level three is the one a reader is most likely to quote as measured margin
    per item. The sentence saying it is not has to travel with the data.
    """
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    joined = " ".join(s["caveats"])
    assert "المعايَر" in joined
    assert "ليست ربحية مقيسة لكل صنف" in joined
