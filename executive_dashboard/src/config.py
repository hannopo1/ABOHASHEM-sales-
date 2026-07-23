"""
Central configuration for the June-2026 Executive Financial Dashboard build.

Every tunable business rule lives here so the pipeline stays declarative and the
numbers stay traceable to a single, reviewable place.
"""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent            # executive_dashboard/src
APP_DIR = PKG_DIR.parent                              # executive_dashboard
REPO_ROOT = APP_DIR.parent                            # repository root

SRC_JUNE_MD = REPO_ROOT / "فواتير_المبيعات_يونيو_2026-1.md"
SRC_MAIN_MD = REPO_ROOT / "فواتير المبيعات من 112025 الى 3152026.md"
# July 1–15 2026 sales invoices (Pioneers-template PDF with an extractable text
# layer). Parsed geometrically at 100% invoice reconciliation.
SRC_JULY_PDF = REPO_ROOT / "فواتير المبيعات من 1_7_2026الى 15_7_2026.pdf"
# Full-year-2026 actual cash receipts (سدادات العملاء) and customer returns
# (ارتجاعات العملاء). Geometric x-band tables; parsed by src/collections.py and
# reconciled EXACTLY to the printed grand totals below.
SRC_COLLECTIONS_PDF = REPO_ROOT / "تحصيلات العملاء من 1-1-2026 الى 18-7-2026.pdf"
SRC_RETURNS_PDF = REPO_ROOT / "مرتجعات العملاء من1-1-2026 الى 16-7-2026.pdf"
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
OUT_REP_EXCEPTIONS = APP_DIR / "rep_exceptions.json"

FONT_REGULAR = APP_DIR / "vendor" / "fonts" / "Amiri-Regular.ttf"
FONT_BOLD = APP_DIR / "vendor" / "fonts" / "Amiri-Bold.ttf"

# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------
PERIOD_YEAR = 2026
PERIOD_MONTH = 7
PERIOD_LABEL_AR = "يوليو ٢٠٢٦"
DEFAULT_MONTH = "2026-07"          # month the dashboard opens on
# AR snapshot date used for the receivable/overdue analysis. Updated to the
# FINAL post-July customer balances (مديونية …-16_7_2026.pdf).
AS_OF_DATE = "2026-07-16"
# Invoices dated on/before this are classified OVERDUE when still unpaid.
OVERDUE_CUTOFF = "2026-06-30"

# Arabic month names (used to label the month selector).
MONTHS_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
ALL_MONTHS_LABEL = "جميع الشهور"
# Every calendar month of the period year — the month selector lists all twelve;
# months with no source data render an honest empty state (never fabricated).
ALL_MONTHS = [f"{PERIOD_YEAR}-{m:02d}" for m in range(1, 13)]


def month_label_ar(ym: str) -> str:
    """'2026-06' -> 'يونيو 2026' (matches the requested selector labels exactly)."""
    y, m = ym.split("-")
    return f"{MONTHS_AR[int(m)]} {y}"

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

# Printed grand totals on the collections / returns source PDFs. The parsed sums
# must equal these EXACTLY (the build aborts otherwise) — the anti-fabrication
# anchor for the collections/reconciliation drill-down.
COLLECTIONS_PRINTED_TOTAL = 22_177_149.68
RETURNS_PRINTED_TOTAL = 435_830.63

# Payment-method classification for a receipt, by keyword in its البيان text.
# Checked in this order; first hit wins. Ordering is load-bearing:
#   * انستا before تحويل   — «تحويل على انستا» is an InstaPay transfer
#   * شيك before بنك       — «تحصيل شيك بنكى» is a cheque, not a plain transfer
#   * بنك before نقد       — «ايداع نقدى فى حساب البنك» arrives via the bank
# فوادفون / انيتا are real misspellings present in the source PDF.
PAYMENT_METHOD_KEYWORDS: list[tuple[str, str]] = [
    ("فودافون", "فودافون كاش"),
    ("فوادفون", "فودافون كاش"),
    ("انستا", "إنستا باي"),
    ("انيتا", "إنستا باي"),
    ("شيك", "شيكات"),
    ("تحويل", "تحويل بنكي"),
    ("بنك", "تحويل بنكي"),
    ("تصفية", "تصفية / تسوية"),
    ("إشعار", "تصفية / تسوية"),
    ("اشعار", "تصفية / تسوية"),
    ("نقد", "نقدي"),
]
# Receipts whose البيان names no method (e.g. «اذن استلم رقم …») are Vodafone
# Cash per the business owner — the ERP clerk only spells out the channel when
# it is NOT the default wallet.
PAYMENT_METHOD_DEFAULT = "فودافون كاش"

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


# Display-only brand relabelling (master/reference mapping override). Keys are
# item codes; values are the brand label to show. Applied at enrichment time —
# it NEVER touches any financial value (sales, qty, price), only the shown brand.
# Requested change: the beef-paste product «العجينة البقري» (عجينة بقرى 1ك/500جم/5ك,
# codes 433/435/436) moves from «أبو هاشم» to «اسبشيال».
BRAND_OVERRIDES: dict[str, str] = {
    "433": "اسبشيال",
    "435": "اسبشيال",
    "436": "اسبشيال",
}


# Customer-name overrides for codes that carry NO name in any source (invoices,
# debt, master) and cannot inherit one. Supplied from official records (never
# inferred). Applied at highest priority in the name map. Keys are the TRUE
# (restored) customer codes — see canonical_code below.
CUSTOMER_NAME_OVERRIDES: dict[str, str] = {
    "1023": "ثلاجة المناشى الوراق",   # (حسام حسن) — dormant opening debt, 838
}


def clean_item_name(name) -> str:
    """Normalise an item name for display so spelling variants of the SAME product
    collapse to one label: drop tatweel, unify alef-maqsura (ى→ي) and the brand
    spelling (اسبيشيال→اسبشيال), and collapse whitespace. Purely cosmetic — the
    item code (and every financial value) is untouched.
    """
    if not name:
        return name
    s = str(name).replace("ـ", "").replace("ى", "ي").replace("اسبيشيال", "اسبشيال")
    return re.sub(r"\s+", " ", s).strip()


def canonical_code(code) -> str:
    """Single source of truth for customer-code identity.

    Real customer codes are natural numbers. For the 1000–1099 range the sales
    ERP dropped the leading «1000», leaving a zero-padded 3-digit form in the
    invoices (1009→«009», 1019→«019», 1000→«000») while the debt reports keep the
    true code. This restores it: a zero-padded «0XX» → str(1000+XX). It also
    strips the thousands-comma from codes that DID keep the 1000 («1,003»→«1003»),
    so invoices, dimensions and the debt snapshot all resolve each customer to one
    true code. Natural codes (1, 6, 10, 50…) are stored un-padded and untouched.
    Touches only identity — no financial value is altered.
    """
    c = str(code).replace(",", "").strip()
    if re.fullmatch(r"0\d\d", c):      # ERP-corrupted code — restore the dropped 1000
        return str(1000 + int(c))
    return c


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
