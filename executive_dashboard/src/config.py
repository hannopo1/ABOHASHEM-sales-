"""
Central configuration for the Executive Financial Dashboard build.

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
# July and August 2026 sales invoices (Pioneers-template PDFs with an extractable
# text layer). Parsed geometrically by src/invoice_pdf.py at 100% invoice
# reconciliation — 344 July invoices, 301 August ones, every one of them balancing
# Σ line_total against its printed total.
#
# July deliberately reads the WHOLE-month file, not the «1_7…15_7» part-month one
# that also sits in the repo: half a month of July next to a full August would
# make every month-on-month figure in the app wrong by construction. The
# part-month file is a strict prefix of this one and is left unused.
SRC_JULY_PDF = REPO_ROOT / "فواتير المبيعات خلال شهر 7.pdf"
SRC_AUGUST_PDF = REPO_ROOT / "فواتير من 1-8-2026 الى 31-8-2026.pdf"
# Actual cash receipts (سدادات العملاء) and customer returns (ارتجاعات العملاء).
# Geometric x-band tables; parsed by src/collections.py and reconciled EXACTLY to
# the printed grand total carried by each file (the build aborts otherwise).
#
# The receipts arrive as one cumulative file plus later month-only files, and the
# two OVERLAP: the cumulative run stops mid-month (18 July / 16 July), so its last
# month is partial. A month-only file therefore SUPERSEDES the cumulative file for
# the month it covers — it is the same ledger, re-run once the month closed.
# Concatenating them instead would double-count the first half of July.
#
# Each entry is (path, month-it-owns | None for "every month not owned by another",
# printed grand total). Ordered oldest-first; later entries win.
SRC_COLLECTIONS: list[tuple[Path, str | None, float]] = [
    (REPO_ROOT / "تحصيلات العملاء من 1-1-2026 الى 18-7-2026.pdf", None, 22_177_149.68),
    (REPO_ROOT / "تحصيلات العملاء حتى تاريخ 30-7-2026.pdf", "2026-07", 4_031_541.00),
    (REPO_ROOT / "تحصيلات العملاء شهر 8.pdf", "2026-08", 4_022_295.50),
]
# A SECOND August receipts report was uploaded alongside the one above:
# «تحصيلات العملاء شهر 8 سنة 2026.pdf», a per-customer statement totalling
# 4,156,517.75 — 134,222.25 more. It is not a corrected version of the same
# ledger: it adds credit notes (إشعار خصم) and old-return settlements, which are
# not cash received. Every other month in this dataset is on the cash-receipts
# («سدادات») basis, so August stays on it too; mixing bases mid-series would move
# the collection-rate KPI for one month only. Recorded, not used.
SRC_COLLECTIONS_AUG_ALT = (REPO_ROOT / "تحصيلات العملاء شهر 8 سنة 2026.pdf",
                           4_156_517.75)

# Returns: same supersede rule. August arrives in a different report layout
# («تقرير مرتجع المبيعات» — one row per returned ITEM, carrying quantity, item,
# rep and governorate) rather than the one-row-per-credit-note layout of the
# earlier files, so it is parsed by its own band set and rolled up.
SRC_RETURNS: list[tuple[Path, str | None, float]] = [
    (REPO_ROOT / "مرتجعات العملاء من1-1-2026 الى 16-7-2026.pdf", None, 435_830.63),
    (REPO_ROOT / "مرتجعات العملاء خلال شهر 7.pdf", "2026-07", 128_129.55),
]
SRC_RETURNS_ITEMISED: list[tuple[Path, str | None, float]] = [
    (REPO_ROOT / "مرتجعات شهر 8 سنة 2026.pdf", "2026-08", 117_327.25),
]
# Customer account-balance reports («تقرير عن حسابات العملاء»), one file per
# representative — the file name IS the official customer→rep assignment, which
# is why they are listed rather than globbed: the rep has to be stated, not
# guessed out of a filename, and the set that filed has to be reviewable.
#
# Two things about the 3 September set are deliberate and NOT omissions:
#   * «مورين 3-9.pdf» is excluded. Despite sitting in the same upload it is a
#     «حسابات الموردين» report — SUPPLIER balances (≈1.05M). Adding it would
#     inflate customer receivables by money the company OWES.
#   * «محمود السيد» filed on 16 July but not on 3 September. His customers keep
#     whatever the newer files say about them and are otherwise reported as
#     dropped — no balance is carried forward from July to fill the gap.
AR_SNAPSHOT_FILES: list[tuple[Path, str]] = [
    (REPO_ROOT / "ايمن فارس 3-9.pdf", "ايمن فارس"),
    (REPO_ROOT / "بشرى 3-9.pdf", "محمد بشرى"),
    (REPO_ROOT / "حسام حسن 3-9.pdf", "حسام حسن"),
    (REPO_ROOT / "شعبان 3-9.pdf", "شعبان"),
    (REPO_ROOT / "محمد امام الصعيد 3-9.pdf", "محمد امام الصعيد"),
    (REPO_ROOT / "محمد خليل 3-9.pdf", "محمد خليل"),
    (REPO_ROOT / "هانى 3-9.pdf", "هانى"),
]
PROCESSED = REPO_ROOT / "data" / "processed"
JUNE_AGG = REPO_ROOT / "analysis" / "data_2026_06"

# Reused processed inputs (regeneratable from source by the repo pipeline)
F_SALES_ALL = PROCESSED / "sales_transactions.csv"            # full parsed history
F_DIM_CUSTOMERS = PROCESSED / "dim_customers.csv"
F_DIM_ITEMS = PROCESSED / "dim_items.csv"
F_AR_BALANCES = PROCESSED / "ar_customer_balances_current.csv"
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
PERIOD_MONTH = 8
PERIOD_LABEL_AR = "أغسطس ٢٠٢٦"
DEFAULT_MONTH = "2026-08"          # month the dashboard opens on
# AR snapshot date used for the receivable/overdue analysis. Updated to the
# per-rep customer balances filed on 3 September 2026 («… 3-9.pdf»).
AS_OF_DATE = "2026-09-03"
# The snapshot's ISSUE date — the edition of the app cut from this data. It is
# deliberately a SEPARATE field from AS_OF_DATE: the receivables were struck on
# 3 September and re-dating them to the 4th would claim a count nobody made.
# One is when the app was built, the other is when the money was counted.
SNAPSHOT_DATE = "2026-09-04"
# Invoices dated on/before this are classified OVERDUE when still unpaid.
# One month before the snapshot date, matching NET_TERMS_DAYS.
OVERDUE_CUTOFF = "2026-07-31"

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

# Printed grand total the dataset as a whole must reproduce. Each source file is
# first checked against its OWN printed total (see SRC_COLLECTIONS / SRC_RETURNS
# above; a mismatch aborts the build), then the superseded months are dropped, so
# this figure is not the sum of the printed totals — it is what survives the
# supersede rule. Computed by src/collections.py and asserted there, which keeps
# it honest when a month file is added: a hand-maintained constant would silently
# go stale.
#
# These two names remain for the payload/report fields that quote "the printed
# total"; they are filled in at parse time.
COLLECTIONS_PRINTED_TOTAL: float | None = None
RETURNS_PRINTED_TOTAL: float | None = None

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
