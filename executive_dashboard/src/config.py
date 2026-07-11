"""
Central configuration for the June-2026 Executive Financial Dashboard build.

Every tunable business rule lives here so the pipeline stays declarative and the
numbers stay traceable to a single, reviewable place.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent            # executive_dashboard/src
APP_DIR = PKG_DIR.parent                              # executive_dashboard
REPO_ROOT = APP_DIR.parent                            # repository root

SRC_JUNE_MD = REPO_ROOT / "فواتير_المبيعات_يونيو_2026-1.md"
PROCESSED = REPO_ROOT / "data" / "processed"
JUNE_AGG = REPO_ROOT / "analysis" / "data_2026_06"

# Reused processed inputs (regeneratable from source by the repo pipeline)
F_SALES_ALL = PROCESSED / "sales_transactions.csv"            # 17-month history
F_DIM_CUSTOMERS = PROCESSED / "dim_customers.csv"
F_DIM_ITEMS = PROCESSED / "dim_items.csv"
F_AR_BALANCES = PROCESSED / "ar_customer_balances_2026-07-04.csv"
F_DEBT_DETAIL = JUNE_AGG / "customer_debt_arrears_detail.csv"
F_REP_SUMMARY = JUNE_AGG / "rep_debt_arrears_summary.csv"
F_ITEM_SUMMARY = JUNE_AGG / "item_summary.csv"                 # cross-check only
F_BONUS_SUMMARY = JUNE_AGG / "customer_sales_bonus_summary.csv"  # cross-check only

# Output deliverables
OUT_DATA_JS = APP_DIR / "data.js"
OUT_INDEX = APP_DIR / "index.html"
OUT_PROCESSED_CSV = APP_DIR / "processed_data.csv"
OUT_INSIGHTS = APP_DIR / "insights.json"
OUT_PDF = APP_DIR / "executive_summary.pdf"

FONT_REGULAR = APP_DIR / "vendor" / "fonts" / "Amiri-Regular.ttf"
FONT_BOLD = APP_DIR / "vendor" / "fonts" / "Amiri-Bold.ttf"

# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------
PERIOD_YEAR = 2026
PERIOD_MONTH = 6
PERIOD_LABEL_AR = "يونيو ٢٠٢٦"
# AR debt snapshot date the arrears files were extracted at.
AS_OF_DATE = "2026-07-04"

# ---------------------------------------------------------------------------
# Business rules (all configurable in one place)
# ---------------------------------------------------------------------------
# Assumed credit terms (source invoices carry NO due date) — used only to label
# an invoice "overdue" and to compute an approximate days-overdue figure.
NET_TERMS_DAYS = 30

# Bonus ladder driven by collection rate. Single source of truth: a customer's
# bonus % is the value of the first tier whose upper bound they fall under.
# Read as: collection_rate < 0.70 -> 0% ; < 0.80 -> 1% ; ... ; <= 1.0 -> 5%.
BONUS_RULES: list[tuple[float, float]] = [
    (0.70, 0.00),
    (0.80, 0.01),
    (0.90, 0.02),
    (0.95, 0.03),
    (1.01, 0.05),   # 95%..100%  (1.01 upper bound keeps a rate of exactly 1.0 in-tier)
]

# Reconciliation tolerance: |Σ line_total - reported invoice total|
RECON_TOL_ABS = 1.0
RECON_TOL_PCT = 0.01

# Abnormality thresholds for the data-quality scan (unit price / quantity).
# Flags are advisory only — nothing is dropped from the dataset.
PRICE_ABNORMAL_MAX = 5000.0     # EGP per unit above this is worth a human look
QTY_ABNORMAL_MAX = 5000.0       # units on a single line above this is unusual

# Aging buckets (days). Approximate — see receivables.py for the honest caveat.
AGING_BUCKETS = [
    ("current", "جاري (غير مستحق)", 0, 0),
    ("d1_30", "1–30 يوم", 1, 30),
    ("d31_60", "31–60 يوم", 31, 60),
    ("d61_90", "61–90 يوم", 61, 90),
    ("d91_120", "91–120 يوم", 91, 120),
    ("d120p", "أكثر من 120 يوم", 121, 10_000),
]


def bonus_pct(collection_rate: float) -> float:
    """Return the bonus fraction (e.g. 0.05 == 5%) for a collection rate.

    Configurable entirely through ``BONUS_RULES`` above.
    """
    if collection_rate is None:
        return 0.0
    for upper, pct in BONUS_RULES:
        if collection_rate < upper:
            return pct
    return BONUS_RULES[-1][1]
