"""Guards on the cost-to-sales join (analysis/13_join_cost_margin.py).

Dependency-free on purpose: these read the committed JSON outputs, so they run
on the stock CI image, which installs only flake8 and pytest. The heavier checks
(reconciliation against the income statement and the invoices) run inside step
13 itself and abort it on failure.

What is locked down here is the reporting discipline, because that is what makes
these figures safe to quote:

  * the measured month and the estimated ones are never blended
  * a month failing the price-drift gate never reaches a headline
  * revenue with no cost row is never treated as zero-cost
  * every margin percentage is taken against the revenue it actually covers
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "data" / "processed" / "margin_summary.json"
DASHBOARD = ROOT / "data" / "processed" / "margin_dashboard.json"

pytestmark = pytest.mark.skipif(
    not SUMMARY.exists(),
    reason="margin outputs absent — run analysis/13_join_cost_margin.py")

TOL = 1.0          # EGP
PCT_TOL = 0.01     # percentage points


@pytest.fixture(scope="module")
def summary():
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dash():
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


def test_reconciliation_recorded_as_passing(summary):
    """Step 13 refuses to emit figures unless all four checks pass, so a stored
    failure means the outputs were produced some other way."""
    rec = summary["reconciliation"]
    assert rec["all_passed"] is True
    assert all(rec["checks"].values()), rec["checks"]


def test_measured_is_exactly_the_cost_month(summary):
    assert summary["measured"]["months"] == [summary["cost_month"]]


def test_measured_and_indicative_never_overlap(summary):
    """The whole point of two bases is that they stay apart."""
    assert not set(summary["measured"]["months"]) & set(summary["indicative"]["months"])


def test_headline_indicative_excludes_unreliable_months(summary):
    """A month outside the drift gate must not reach the headline figure."""
    reliable = set(summary["price_drift"]["reliable_months"])
    assert set(summary["indicative"]["months"]) <= reliable
    excluded = summary.get("indicative_excluded")
    if excluded:
        assert not set(excluded["months"]) & reliable


def test_drift_gate_partitions_every_month(summary, dash):
    reliable = set(summary["price_drift"]["reliable_months"])
    excluded = set(summary["price_drift"]["excluded_months"])
    assert not reliable & excluded
    months = {r["month"] for r in dash["by_month"]}
    assert reliable | excluded == months


def test_reliability_flag_agrees_with_the_threshold(summary, dash):
    limit = summary["price_drift"]["max_drift_pct"]
    for row in dash["by_month"]:
        drift = row["cost_period_drift_pct"]
        if drift is None:
            continue
        assert row["indicative_reliable"] is (abs(drift) <= limit), row["month"]


def test_uncosted_revenue_is_carried_not_zero_costed(summary):
    """Revenue with no cost row must be reported separately. Folding it in at
    zero cost would inflate every margin percentage."""
    cov = summary["coverage"]
    assert cov["revenue_uncosted"] > 0
    assert abs(cov["revenue_costed"] + cov["revenue_uncosted"]
               - cov["revenue_total"]) < TOL
    assert cov["n_items_costed"] < cov["n_items_total"]


def test_coverage_percentage_matches_the_amounts(summary):
    cov = summary["coverage"]
    expected = cov["revenue_costed"] / cov["revenue_total"] * 100
    assert abs(cov["coverage_pct"] - expected) < PCT_TOL


@pytest.mark.parametrize("basis", ["measured", "indicative"])
def test_margins_are_taken_against_costed_revenue(summary, basis):
    b = summary[basis]
    assert abs(b["gross_margin_pct"]
               - b["gross_profit"] / b["revenue_costed"] * 100) < PCT_TOL
    assert abs(b["op_margin_pct"]
               - b["op_profit"] / b["revenue_costed"] * 100) < PCT_TOL


def test_operating_margin_sits_below_gross(summary):
    """Operating profit carries conversion and opex on top of cost of sales, so
    it cannot exceed gross. Catches a cost level wired to the wrong column."""
    for basis in ("measured", "indicative"):
        b = summary[basis]
        assert b["op_profit"] < b["gross_profit"]
        assert b["op_margin_pct"] < b["gross_margin_pct"]


def test_dashboard_payload_agrees_with_the_summary(summary, dash):
    """The app reads the payload, not the summary; they must not drift."""
    assert dash["meta"]["cost_month"] == summary["cost_month"]
    assert dash["meta"]["reliable_months"] == summary["price_drift"]["reliable_months"]
    assert abs(dash["meta"]["coverage_pct"] - summary["coverage"]["coverage_pct"]) < PCT_TOL
    assert dash["totals"]["measured"] == summary["measured"]


def test_every_breakdown_row_states_its_coverage(dash):
    """A row quoting a margin without saying how much of its revenue was costed
    invites the reader to assume all of it."""
    for key in ("by_brand", "by_rep"):
        for row in dash[key]:
            assert row["cost_coverage_pct"] is not None
            assert 0 < row["cost_coverage_pct"] <= 100 + PCT_TOL, row


def test_pricing_gap_rows_are_actually_under_priced(dash):
    """The list is meant to be actionable, so every row must be a real gap."""
    for row in dash["pricing_gap"]:
        assert row["gap_pct"] > 0
        assert row["rec_price"] > row["june_avg_price"]


def test_caveats_travel_with_the_figures(summary, dash):
    assert summary["caveats"], "figures must not ship without their caveats"
    assert dash["caveats"] == summary["caveats"]
