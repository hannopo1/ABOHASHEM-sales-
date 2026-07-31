# CLAUDE.md

Guidance for AI assistants working in this repository.

## What this is

An Arabic (RTL) financial & operational analytics platform for **Abu Hashem for
Meats — Food Industries**: sales, receivables (مديونية), and cash collections
(تحصيلات) for 2026. Everything is built **entirely from the source files in the
repo root** — no external or assumed data.

**Anti-fabrication is the core principle.** Every number must be traceable to a
source file. Consequences to honor:
- The sources contain **no cost data** → never show gross/operating margin,
  COGS, or EBITDA. Only observed net revenue.
- Parsed totals are reconciled **exactly** to the printed grand totals on the
  source PDFs; the build aborts on any mismatch.
- Rows that can't be attributed (e.g. a receipt whose customer name doesn't
  match) are pooled into an explicit «غير مُطابَق» bucket and reported — never
  dropped, never invented.

## Two generations live here — know which one you're touching

- **`executive_dashboard/` — the ACTIVE, maintained app.** All recent work and
  the open PR happen here. Polars pipeline via `build.py`, 9 Arabic sections,
  ECharts/Plotly, ships as one offline standalone HTML. **Start here.**
- **Legacy (do not modify unless explicitly asked):** `analysis/` (numbered
  `01_…10_` pandas scripts) → `data/processed/` (CSV/JSON outputs) →
  `dashboards/` (older Chart.js, 8 tabs) → `reports/` (3 Markdown reports).
  Root-level `index.html`, `dashboard_part*.html`, `sections_part*.html`,
  `js_code.html` are older artifacts of the `dashboards/` generation.

> The root `README.md` and `executive_dashboard/README.md` are useful but
> **partly stale** — they describe the old `DEBT_CODE_ALIASES` +1000 model
> (since replaced, see Conventions) and 2026-07-16 figures (now 2026-07-23).
> Trust this file and the code over the READMEs where they disagree.

## executive_dashboard — architecture & commands

Run everything from inside `executive_dashboard/`:

```bash
pip install -r requirements.txt      # polars, pandas, numpy, plotly, reportlab,
                                     # arabic-reshaper, python-bidi, openpyxl, pymupdf
python3 build.py                     # source files → Polars aggregation → outputs + VALIDATION report
python3 make_standalone.py           # inline everything → dashboard_standalone.html
python3 -m pytest tests/ -q          # unit tests
python3 -m flake8 . --select=E9,F63,F7,F82   # the blocking CI lint gate
```

- `build.py` reads the source files, does **all** aggregation on Polars
  (deterministic; scales to 1M+ rows), then writes `data.js` (the
  `window.DASH` payload the UI reads), `processed_data.csv`, `insights.json`,
  `executive_summary.pdf`, `rep_exceptions.json`, and renders `index.html` from
  its template. It prints a **validation report**; any `[FAIL]` aborts the build
  (non-zero exit). Keep it all-green.
- `make_standalone.py` inlines CSS/JS/data/fonts/images into
  **`dashboard_standalone.html`** — a single ~10 MB file that opens with no
  server and no internet. **This is the deliverable handed to the user**, not
  `index.html`.

### `src/` module map
- `config.py` — single source of truth for **all** business rules: source-file
  paths (`SRC_*`), `AS_OF_DATE`, reconciliation anchors, bonus ladder,
  `canonical_code`, `clean_item_name`, `CUSTOMER_NAME_OVERRIDES`,
  `PAYMENT_METHOD_KEYWORDS`, `BRAND_OVERRIDES`.
- `load.py` — `parse_all` (invoices/lines from the .md files + July PDF),
  `load_dimensions`, `enrich_lines`. Customer codes are canonicalized here.
- `july.py` — geometric (x-band) parser for the July invoices PDF.
- `collections.py` — receipts + returns. `parse_collections`/`parse_returns`
  **compose** two files (old file rows < July + the new July-only file). Also
  the payment-method classifier (`_method`).
- `debt.py` — geometric parser for the customer balance PDFs (`load_final_balances`).
- `overdue.py` — FIFO receivable aging vs `AS_OF_DATE`.
- `kpis.py`, `customers.py`, `products.py`, `insights.py`, `data_quality.py`,
  `pdf_report.py` — analytics + the auto-generated commentary + the PDF.
- Frontend (design — see rules below): `index.html`, `style.css`, `script.js`.
  `vendor/` holds ECharts, Plotly, Bootstrap-RTL, jQuery, DataTables+Buttons,
  Cairo/Amiri fonts (all local, offline).

## Critical conventions (current state)

- **`config.canonical_code`** — customer-code identity. Real codes are natural
  numbers; the ERP dropped the leading `1000` from codes 1000–1099, leaving a
  **leading-zero** form in invoices (`009`, `019`, `000`). Rule: **any code
  matching `0\d+` → `str(1000 + int(code))`**; thousands-commas are stripped
  (`1,003`→`1003`). Invoices, dimensions, and the debt snapshot all pass through
  this, so every source resolves to one true code. (The old `DEBT_CODE_ALIASES`
  map has been **removed** — do not reintroduce it.)
- **Name consolidation** — every customer code shows ONE authoritative name via
  `build._consolidate_names` (reference master → debt detail → invoice history);
  item names via `config.clean_item_name`. Note: `invoices_full` is left **raw
  on purpose** so the collections name-matcher can use every spelling variant.
- **Payment methods** — `config.PAYMENT_METHOD_KEYWORDS` is an **ordered** list
  (first hit wins; ordering is load-bearing, e.g. `شيك` before `بنك`); receipts
  naming no method default to «فودافون كاش».
- **Reconciliation anchors** — `COLLECTIONS_PRINTED_TOTAL` /
  `RETURNS_PRINTED_TOTAL` are exact-match gates enforced by `build.validate()`.
  When you change collections/returns sources, recompute these. Current
  composition runs to 2026-07-23: old file (Jan–Jun) + new July file.
- **June regression guards** — `build.validate()` asserts June stays
  **311 invoices / 116 customers / 3,867,491** sales. These must never change
  (June source data is frozen); if your change moves them, you broke something.
- **`AS_OF_DATE`** — the receivable snapshot date (currently `2026-07-23`).

## Data vs design — a hard rule for data refreshes

When asked to "update the numbers"/refresh data, change **only** the
data-ingestion layer: `config.py` source paths & constants, and parser wiring in
`load/collections/debt`. **Do not touch** `index.html` / `style.css` /
`script.js` (design) or the analytics/aggregation logic — the dashboard must
look and behave identically, just with new numbers. Source files (Arabic
filenames) live in the **repo root** and are wired via `config.SRC_*`.

## Dev workflow & git

- After any data/logic change: `build.py` (all PASS) → `make_standalone.py` →
  `pytest tests/ -q` → the flake8 gate. Commit the **regenerated deliverables**
  (`data.js`, `dashboard_standalone.html`, `processed_data.csv`, etc.) together
  with the source change.
- **CI**: `.github/workflows/python-app.yml` runs flake8 (blocking selection
  `E9,F63,F7,F82`, plus a non-blocking full report at max-line-length 127) and
  pytest on push/PR to `main` (Python 3.10).
- **Tests** (`tests/test_pipeline.py`) are stdlib-only by default and guard the
  polars/pymupdf/PDF-dependent tests with `pytest.importorskip` + file-existence
  skips, so they pass on the bare CI image.
- Feature work is on branch `claude/customer-payment-cleanup-xvxgtz` (draft
  PR #8). Commit messages / PR text are in English; user-facing dashboard text
  and chat are Arabic. End commits with the `Co-Authored-By` footer.

## Gotchas

- Arabic RTL everywhere; keep it.
- PDF parsing is **geometric** (column x-bands) and layout-sensitive — verify
  new files share the expected layout before wiring them in.
- Polars aggregation is deterministic (sorted, rounded) — preserve that.
- The user's deliverable is `dashboard_standalone.html`, not `index.html`.
