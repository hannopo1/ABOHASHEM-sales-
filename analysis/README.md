# Sales & Debt Analysis — ABOHASHEM

Analysis built from the repo's raw invoice exports and per-rep receivables (مديونية) PDFs.
Covers: rep debt with 30-day arrears aging, per-customer sales & bonus %, per-item quantity
and average selling price (with brand grouping), and a flagged list of zero-value ("بونص")
invoices.

## How to re-run

```bash
pip install polars openpyxl xlsxwriter
python3 analysis/scripts/parse_invoices.py   # -> analysis/data/invoices_header.csv, invoices_lines.csv
python3 analysis/scripts/build_analysis.py   # -> analysis/data/*.csv + sales_debt_analysis.xlsx
```

`analysis/data/debt_by_customer.csv` was transcribed by hand from the 8 `مديونية <rep> 4-7.pdf`
snapshot reports (as of 2026-07-04) — those PDFs render as real text, not scanned images, so no
OCR/PDF-parsing library was needed; re-transcribe it if a newer receivables snapshot is provided.

## Data sources

| File | Rows | Coverage |
|---|---|---|
| `فواتير المبيعات من 112025 الى 3152026.md` | 4,591 invoices | 2025-01-01 → 2026-05-09 |
| `فواتير_المبيعات_يونيو_2026-1.md` | 311 invoices | 2026-06-01 → 2026-06-30 |
| 8× `مديونية <rep> 4-7.pdf` | 242 customer balances | snapshot as of 2026-07-04 |
| `تصنيف الاصناف كبراند (1).pdf` | 58 item names | reference only (see Brand note) |

**Known coverage gap**: there is no invoice data for 2026-05-10→05-31 or 2026-07-01→07-04, so any
"most recent invoice" figure can lag a customer's true last purchase by up to a few weeks if they
only ordered in that window.

## Methodology & assumptions

- **Zero invoices**: invoices with header total = 0 (line items priced at 0, usually noted
  "بونص") are free/bonus stock. They're excluded from revenue but included in quantity figures.
- **Average selling price per item**: `sum(line_total) / sum(qty)` over paid (non-zero) lines
  only, grouped by item code. Sampling both invoice files showed the discount%/tax% columns are
  **not reliably ordered** (a non-zero discount landed in different column positions in different
  files/rows), so unit-price/discount/tax fields aren't trusted directly — realized revenue ÷
  quantity sidesteps that ambiguity entirely.
- **Bonus % per customer**: `bonus_qty / total_qty × 100`, where `bonus_qty` is the quantity
  received via zero-total invoices.
- **Sales per customer**: sum of invoice totals (the billed amount, not the paid amount) across
  all non-zero invoices for that customer.
- **Rep debt & arrears (30-day credit-term aging)**: the debt-PDF snapshot balance (as of
  2026-07-04) is the only reliable *current* balance — it is **not** reconstructed by summing
  invoices' "الباقي" fields. Those are frozen at print time and don't reflect later payments,
  so summing them across 17 months of invoices overstated real debt by roughly 10-20x when first
  tried. Instead: a customer's snapshot debt (net > 0) is classified as **arrears** if their most
  recent invoice in our data is more than 30 days before 2026-07-04 (i.e. they've gone quiet for
  over a month while still owing money, past the monthly credit term); otherwise it's **current**.
  A negative net balance (the company owes the customer) is reported separately as
  `credit_balance`, not counted as debt.
- **Brand grouping**: derived from item-name keywords (`اسبشيال`/`اسباشيل` → اسبشيال, `الهنا` →
  الهنا, else → ابوهاشم) rather than a join against the reference PDF, because that PDF has no
  item codes — only a name list — so keyword matching on the actual invoice item names is more
  robust than trying to align two independently-ordered lists.
- **Parsing caveats**: 10 of 4,902 invoices had no line items the parser could extract (unusual
  formatting); line-item totals summed to the invoice header total within EGP 1 for 4,847 of 4,892
  checkable invoices. Both formats have OCR/extraction noise in the unit field (طبق/طلى/طلق/طني/كس
  are all the same unit) which isn't used in any calculation.

## Output files (`analysis/data/`)

- `invoices_header.csv`, `invoices_lines.csv` — parsed invoice data (intermediate).
- `debt_by_customer.csv` — transcribed receivables snapshot, 2026-07-04.
- `zero_invoices.csv` — flagged bonus/free-stock invoices.
- `item_summary.csv` — quantity, avg selling price, brand per item.
- `customer_sales_bonus_summary.csv` — sales value, quantity, bonus % per customer.
- `rep_debt_arrears_summary.csv` — current vs. arrears debt per rep.
- `customer_debt_arrears_detail.csv` — same, at customer level.
- `sales_debt_analysis.xlsx` — the five summary tables above bundled into one workbook.

See `analysis/dashboard.html` for the interactive view of all of the above.
