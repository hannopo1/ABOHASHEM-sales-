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
# Checked in this order; first hit wins; no hit -> "أخرى".
PAYMENT_METHOD_KEYWORDS: list[tuple[str, str]] = [
    ("فودافون", "فودافون كاش"),
    ("تحويل", "تحويل بنكي"),
    ("تصفية", "تصفية / تسوية"),
    ("انستا", "إنستا باي"),
    ("نقد", "نقدي"),
]
PAYMENT_METHOD_DEFAULT = "أخرى"

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


# ---------------------------------------------------------------------------
# Debt-snapshot customer-code aliases (data-quality correction)
# ---------------------------------------------------------------------------
# The 2026-07-16 debt reports code a subset of customers with a +1000 offset
# relative to the sales-invoice system (an ERP re-coding). They are the SAME
# customers — verified name-identical against the invoice history (e.g. debt
# code 1019 «مصطفى عز السماعيلية» carries the exact unpaid balance of invoice
# code 019). Left unmerged, their balance is mis-aged as orphan «120+ opening»
# debt and their sales appear rep-less. This map re-keys the debt balance onto
# the invoice code so it ages correctly against the real invoices and inherits
# the representative from its debt file. It touches ONLY the code linkage — no
# balance, invoice, collection or sales value is altered. {debt_code: inv_code}.
DEBT_CODE_ALIASES: dict[str, str] = {
    "1000": "000",   # عادل دشيشة المنصورية      (محمد خليل)
    "1001": "001",   # منفذ امان السيدة زينب     (محمد خليل)
    "1007": "007",   # مطعم لهاليبو باب الشعرية  (محمد خليل)
    "1008": "008",   # اولاد الشيخ الوراق        (محمد خليل)
    "1011": "011",   # ثلجة حليم الوراق          (محمد خليل)
    "1012": "012",   # بيت العيلة الدويقة        (ايمن فارس)
    "1014": "014",   # بيتزا ابورئال الخانكة     (محمد خليل)
    "1015": "015",   # بيت العيلة السيدة زينب    (ايمن فارس)
    "1016": "016",   # بيت العيلة مصر والسودان   (ايمن فارس)
    "1018": "018",   # مصيلحى صقر قريش           (محمد خليل)
    "1019": "019",   # مصطفى عز السماعيلية       (حسام حسن)
    "1020": "020",   # الليبى م خليل             (محمد خليل)
    "1021": "021",   # ماركت الخوة م خليل        (محمد خليل)
    # Blank-name debt codes whose customer was identified from official records;
    # each matches the invoice code by exact name + reconciling balance.
    "1010": "010",   # مطعم العدلية بلبيس        (حسام حسن) 7,750 = July sales
    "1013": "013",   # الخواص جمصة               (حسام حسن) 2,000 residual
}

# Customer-name overrides for debt codes that carry NO name in the source PDF and
# have NO matching invoice to inherit a name from. Supplied from official records
# (never inferred). Applied at highest priority in the name map.
CUSTOMER_NAME_OVERRIDES: dict[str, str] = {
    "1023": "ثلاجة المناشى الوراق",   # (حسام حسن) — dormant opening debt, 838
}


def canonical_code(code) -> str:
    """Single source of truth for customer-code identity.

    Codes ≥1000 are written comma-formatted in the sales-invoice source («1,003»)
    but plain in the debt reports («1003»), so they never joined — leaving real
    unpaid June invoices mis-aged as orphan «120+» debt. This strips the
    thousands-comma, then applies the verified +1000 duplicate-code alias, so
    every source resolves each customer to one code. Touches only identity — no
    financial value is altered.
    """
    c = str(code).replace(",", "").strip()
    return DEBT_CODE_ALIASES.get(c, c)


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
