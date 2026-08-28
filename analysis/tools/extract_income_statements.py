#!/usr/bin/env python3
"""Extract the monthly income statements from the costing repo into JSON.

Run manually, not from the pipeline:

    python3 analysis/tools/extract_income_statements.py --repo ../Abohashem

It writes ``data/cost/income_statements.json`` — the same vendoring pattern as
``data/cost/model_rows.json``: a parsed, validated, reviewable extract lives in
this repo, while the binary sources stay in ``hannopo1/Abohashem``.

WHY THE PARSING RULES LOOK PARANOID

The sources are eleven observations spread over one workbook and five PDFs, and
neither format is machine-friendly:

* The workbook's six sheets each start at a different origin (B4, E5, G6, G7,
  I9, G5), so a positional rule reads a different line on every sheet. Worse,
  month 11 carries a stray value in the same row as صافي المبيعات — the naive
  "last number in the row" rule silently returned it. Labels are the only stable
  anchor, and even they need care: the group totals sit in one column per sheet,
  sometimes on the header row and sometimes one row below it.

* The PDFs' text layer is corrupted by Arabic ligature decomposition. The same
  word appears as مصروفات / مرصوفات, صافى / صافن; group headers are truncated
  mid-word (مرصوفات تش, مرصوفات بي); numbers detach from their labels; and in
  one document the group totals are emitted *after* the net-profit line.

So this extractor reads from the PDFs only the four figures that are reliably
label-adjacent and comma-formatted — net sales, cost of sales, gross profit and
net profit — plus the percentage column where the document prints one. It does
NOT try to parse the expense breakdown out of a PDF: every general rule tried
against these five documents mis-read at least one of them, and a plausible
wrong number is worse than an absent one. Total operating expenses is therefore
carried as gross profit minus net profit, which is exact by construction.

Every observation must pass its identities or the run aborts. A statement that
does not reconcile is a statement we do not understand, and guessing which
figure is wrong is exactly how a bad number reaches a board report.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "cost" / "income_statements.json"

# Absolute tolerance in EGP for every reconciliation below. The statements are
# kept to the piastre, so anything above a pound is a parsing fault, not
# rounding.
TOL = 1.0

# The June 2026 statement is the anchor between the two repositories: these are
# the values analysis/13_join_cost_margin.py already carries as STATEMENT, read
# from this same document. If the extractor disagrees with them, either the
# extraction broke or the source changed — both must stop the run.
JUNE_ANCHOR = {
    "net_sales": 3_741_772.00,
    "cogs": 2_039_933.08,
    "gross_profit": 1_701_838.92,
    "net_profit": 418_841.92,
}

XLSX_SOURCE = "قائمة دخل تفصيلى  من ٧ الى ١٢ سنة ٢٠٢٥.xlsx"

# Sheet name -> period. Taken from the workbook, not inferred from sheet order,
# because the sheet titles carry the month and the order is not guaranteed.
XLSX_SHEETS = {
    "دخل شهر ٧سنة ٢٠٢٥": "2025-07",
    "دخل شهر ٨ سنة ٢٠٢٥": "2025-08",
    "شهر 9سنة ٢٠٢٥": "2025-09",
    "شهر 10سنة ٢٠٢٥": "2025-10",
    "شهر 11سنة ٢٠٢٥": "2025-11",
    "شهر 12سنة ٢٠٢٥": "2025-12",
}

# Each PDF holds one observation. ``months`` is what the period actually spans:
# the first document is a single combined quarterly statement, not three monthly
# ones, and nothing downstream may treat it as monthly without saying so.
PDF_SOURCES = [
    ("قائمة دخل شهر يناير وفبراير ومارس سنة ٢٠٢٦.pdf", "2026-Q1", 3),
    ("دخل شهر 4 سنة 2026.pdf", "2026-04", 1),
    ("قائمة دخل تفصيلى شهر 5 سنة 2026.pdf", "2026-05", 1),
    ("قائمة دخل تفصيلى شهر ٦ سنة ٢٠٢٦.pdf", "2026-06", 1),
    ("قائمة دخل تفصيلى شهر 7 سنه 2026-1.pdf", "2026-07", 1),
]


class ExtractError(SystemExit):
    """Raised for any unreconciled or unreadable statement."""


def die(msg: str) -> None:
    raise ExtractError(f"extract_income_statements: {msg}")


def close(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol


# --------------------------------------------------------------- git access --

def git_show(repo: Path, ref: str, path: str) -> bytes:
    """Read a file out of the costing repo without checking anything out."""
    p = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                       capture_output=True)
    if p.returncode != 0:
        die(f"cannot read {path!r} at {ref}: "
            f"{p.stderr.decode('utf-8', 'replace').strip()}")
    return p.stdout


def git_rev(repo: Path, ref: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                       capture_output=True, text=True)
    if p.returncode != 0:
        die(f"cannot resolve {ref!r} in {repo}")
    return p.stdout.strip()


# ------------------------------------------------------------------- xlsx ----

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _label_at(ws, row, col):
    v = ws.cell(row=row, column=col).value
    return v.strip() if isinstance(v, str) else ""


def find_label(ws, *needles):
    """First cell whose text contains every needle. Returns (row, col)."""
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str):
                t = c.value.replace("‏", "")
                if all(n in t for n in needles):
                    return c.row, c.column
    return None


def value_right_of(ws, row, col, max_span=6):
    """Nearest numeric cell to the right of a label, in the same row.

    'Nearest', not 'last': month 11 puts an unrelated figure further right on
    the صافي المبيعات row, and taking the last number reads that instead.
    """
    for j in range(col + 1, col + 1 + max_span):
        v = _num(ws.cell(row=row, column=j).value)
        if v is not None:
            return v
    return None


def parse_sheet(ws, period, source):
    """One monthly statement out of one worksheet."""
    anchors = {}
    for key, needles in (("net_sales", ("صافي", "المبيعات")),
                         ("cogs", ("تكلفة", "المبيعات")),
                         ("gross_profit", ("مجمل", "الربح"))):
        hit = find_label(ws, *needles)
        if hit is None:
            die(f"{period}: no {key} label in sheet {ws.title!r}")
        val = value_right_of(ws, *hit)
        if val is None:
            die(f"{period}: {key} label at {hit} has no value to its right")
        anchors[key] = float(val)

    # The expense-group totals all sit in one column per sheet. Establish it
    # from the administrative group, which is well-formed on every sheet, then
    # read the other groups from that same column.
    admin = find_label(ws, "مصروفات", "إدارية")
    if admin is None:
        die(f"{period}: no administrative-expenses header")
    total_col = None
    for j in range(admin[1] + 1, admin[1] + 7):
        if _num(ws.cell(row=admin[0], column=j).value) is not None:
            total_col = j
            break
    if total_col is None:
        die(f"{period}: administrative group has no total")

    groups = {}
    for name, needles in (("admin", ("مصروفات", "إدارية")),
                          ("selling", ("مصروفات", "بيعية")),
                          ("financing", ("مصاريف", "تمويلية"))):
        hit = find_label(ws, *needles)
        if hit is None:
            die(f"{period}: no {name} group header")
        # Month 9's sheet is shifted: its group headers carry a line item and
        # the group total lands one row lower. Accept either row, nothing else.
        val = None
        for r in (hit[0], hit[0] + 1):
            v = _num(ws.cell(row=r, column=total_col).value)
            if v is not None:
                val = float(v)
                break
        if val is None:
            die(f"{period}: {name} group total not in column {total_col}")
        groups[name] = val

    # Net profit sits in the totals column on most sheets, one column left of
    # the label on two of them, and one row above the label on a third. Take
    # the totals column near the label first; fall back to the only number on
    # the label's own row; derive it last, and say so.
    np_hit = find_label(ws, "صاف", "الربح")
    net_profit, np_source = None, "stated"
    if np_hit:
        for r in (np_hit[0], np_hit[0] - 1, np_hit[0] + 1):
            if r < 1:
                continue
            v = _num(ws.cell(row=r, column=total_col).value)
            if v is not None:
                net_profit = float(v)
                break
        if net_profit is None:
            row_vals = [_num(c.value) for c in ws[np_hit[0]]]
            row_vals = [v for v in row_vals if v is not None]
            if len(row_vals) == 1:
                net_profit = float(row_vals[0])
    if net_profit is None:
        net_profit = anchors["gross_profit"] - sum(groups.values())
        np_source = "derived"

    obs = dict(period=period, months=1, basis="measured",
               source=source, sheet=ws.title,
               net_sales=anchors["net_sales"], cogs=anchors["cogs"],
               gross_profit=anchors["gross_profit"],
               expenses=groups,
               total_expenses=sum(groups.values()),
               net_profit=net_profit, net_profit_source=np_source,
               stated_cogs_pct=None, stated_gross_margin_pct=None)
    return obs


def parse_workbook(repo, ref):
    import openpyxl
    raw = git_show(repo, ref, XLSX_SOURCE)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    missing = set(XLSX_SHEETS) - set(wb.sheetnames)
    if missing:
        die(f"workbook is missing expected sheets: {sorted(missing)}")
    return [parse_sheet(wb[name], period, XLSX_SOURCE)
            for name, period in sorted(XLSX_SHEETS.items(), key=lambda kv: kv[1])]


# -------------------------------------------------------------------- pdf ----

# A money token: comma-grouped, or four or more bare digits. Two- and
# three-digit runs are excluded on purpose — the corrupted text layer glues
# year fragments onto labels (سنة26, ربع1), and those must never be read as
# values.
MONEY = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?")
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def norm(text: str) -> str:
    """Collapse the PDF's line breaks and ligature debris into one stream."""
    text = text.replace("‏", " ").replace("‎", " ")
    return re.sub(r"\s+", " ", text)


def after(stream: str, pattern: str, period: str, what: str):
    """The first money token after a label, plus the percentage if one trails.

    Labels are matched loosely because the same word decomposes differently
    across documents: صافى / صافن, and spaces appear inside words (الرب ح).
    """
    m = re.search(pattern, stream)
    if not m:
        die(f"{period}: cannot find the {what} label")
    tail = stream[m.end():m.end() + 120]
    money = MONEY.search(tail)
    if not money:
        die(f"{period}: no value after the {what} label")
    value = float(money.group(0).replace(",", ""))
    # A percentage may sit either side of the figure depending on the document.
    pct = None
    around = tail[:money.end() + 12]
    pm = PCT.search(around)
    if pm:
        pct = float(pm.group(1))
    return value, pct


def parse_pdf(repo, ref, path, period, months):
    import pymupdf
    raw = git_show(repo, ref, path)
    doc = pymupdf.open(stream=raw, filetype="pdf")
    stream = norm(" ".join(page.get_text() for page in doc))

    net_sales, _ = after(stream, r"صافي\s*المبيعات", period, "net sales")
    cogs, cogs_pct = after(stream, r"تكلفة\s*المبيعات", period, "cost of sales")
    gross, gross_pct = after(stream, r"مجمل\s*الرب\s*ح|مجمل\s*الربح",
                             period, "gross profit")
    net_profit, _ = after(stream, r"صاف[ىني]\s*الرب\s*ح|صاف[ىني]\s*الربح",
                          period, "net profit")

    return dict(period=period, months=months, basis="measured",
                source=path, sheet=None,
                net_sales=net_sales, cogs=cogs, gross_profit=gross,
                # The expense breakdown is deliberately not parsed out of the
                # PDFs; see the module docstring. Total operating expenses is
                # exact by construction.
                expenses=None, total_expenses=gross - net_profit,
                net_profit=net_profit, net_profit_source="stated",
                stated_cogs_pct=cogs_pct, stated_gross_margin_pct=gross_pct)


# ---------------------------------------------------------------- validate ----

def validate(obs):
    """Every identity the documents assert about themselves."""
    p = obs["period"]

    if not close(obs["net_sales"] - obs["cogs"], obs["gross_profit"]):
        die(f"{p}: net sales − cost of sales ≠ gross profit "
            f"({obs['net_sales']} − {obs['cogs']} ≠ {obs['gross_profit']})")

    if not close(obs["gross_profit"] - obs["total_expenses"], obs["net_profit"]):
        die(f"{p}: gross profit − expenses ≠ net profit "
            f"({obs['gross_profit']} − {obs['total_expenses']} "
            f"≠ {obs['net_profit']})")

    if obs["expenses"] is not None:
        s = sum(obs["expenses"].values())
        if not close(s, obs["total_expenses"]):
            die(f"{p}: expense groups sum to {s}, total says "
                f"{obs['total_expenses']}")

    # Where the document prints its own percentage column, it is an independent
    # check on the figures above it — the one cross-check the source gives us.
    if obs["net_sales"]:
        if obs["stated_cogs_pct"] is not None:
            got = obs["cogs"] / obs["net_sales"] * 100
            if abs(got - obs["stated_cogs_pct"]) > 0.02:
                die(f"{p}: cost-of-sales ratio {got:.2f}% contradicts the "
                    f"stated {obs['stated_cogs_pct']:.2f}%")
        if obs["stated_gross_margin_pct"] is not None:
            got = obs["gross_profit"] / obs["net_sales"] * 100
            if abs(got - obs["stated_gross_margin_pct"]) > 0.02:
                die(f"{p}: gross margin {got:.2f}% contradicts the stated "
                    f"{obs['stated_gross_margin_pct']:.2f}%")

    if p == "2026-06":
        for k, want in JUNE_ANCHOR.items():
            if not close(obs[k], want):
                die(f"2026-06: {k} is {obs[k]}, but the costing model and "
                    f"analysis/13_join_cost_margin.py carry {want}. The two "
                    f"repositories no longer agree on the same statement.")


# -------------------------------------------------------------------- main ----

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path,
                    help="path to a clone of hannopo1/Abohashem")
    ap.add_argument("--ref", default="origin/main",
                    help="git ref to read the statements from")
    args = ap.parse_args(argv)

    repo = args.repo.expanduser().resolve()
    if not (repo / ".git").exists():
        die(f"{repo} is not a git repository")
    commit = git_rev(repo, args.ref)

    # Read from the resolved commit, never from args.ref: a ref that advances
    # mid-run would mix revisions and still record one commit as the source.
    rows = parse_workbook(repo, commit)
    for path, period, months in PDF_SOURCES:
        rows.append(parse_pdf(repo, commit, path, period, months))
    rows.sort(key=lambda r: r["period"])

    for obs in rows:
        validate(obs)

    covered = sum(r["months"] for r in rows)
    if covered != 13:
        die(f"expected 13 months of coverage, the sources give {covered}")

    payload = {
        "meta": {
            "source_repo": "hannopo1/Abohashem",
            "source_commit": commit,
            "source_ref": args.ref,
            "extracted_on": date.today().isoformat(),
            "extractor": "analysis/tools/extract_income_statements.py",
            "n_observations": len(rows),
            "months_covered": covered,
            "note": "قوائم دخل على مستوى الشركة. لا تحتوي تكلفة لكل صنف.",
        },
        "observations": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)} — {len(rows)} observations, "
          f"{covered} months, all identities reconciled")
    for r in rows:
        gm = r["gross_profit"] / r["net_sales"] * 100 if r["net_sales"] else 0
        print(f"  {r['period']}  {r['months']}mo  "
              f"net {r['net_sales']:>13,.2f}  cogs {r['cogs']:>13,.2f}  "
              f"GM {gm:5.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
