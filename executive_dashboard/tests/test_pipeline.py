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

# Make ``src`` importable without installing the package.
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from src.config import bonus_pct, BONUS_RULES  # noqa: E402


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
