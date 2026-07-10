#!/usr/bin/env python3
"""
Parse the two source invoice markdown files (converted from Crystal Reports / scanned PDFs)
into a single clean transactional dataset: one row per invoice line item.

Sources (uploaded, unmodified):
  - "فواتير المبيعات من 112025 الى 3152026.md"  (2025-01-01 .. 2026-05-31, free-text/fenced blocks)
  - "فواتير_المبيعات_يونيو_2026-1.md"           (2026-06, markdown tables)

Output:
  - data/processed/sales_transactions.csv
  - data/processed/parse_log.json  (counts, skipped lines, reconciliation checks)
"""
import re
import json
import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
FILE_MAIN = ROOT / "فواتير المبيعات من 112025 الى 3152026.md"
FILE_JUNE = ROOT / "فواتير_المبيعات_يونيو_2026-1.md"
OUT_CSV = ROOT / "data" / "processed" / "sales_transactions.csv"
LOG_JSON = ROOT / "data" / "processed" / "parse_log.json"

NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")

log = {
    "invoices_found_main": 0,
    "invoices_parsed_main": 0,
    "invoices_reconciliation_fail_main": 0,
    "invoice_blocks_no_items_main": 0,
    "invoices_found_june": 0,
    "invoices_parsed_june": 0,
    "line_items_total": 0,
    "reconciliation_fail_examples": [],
    "unparsed_examples": [],
}


def parse_num(s):
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_main_file():
    text = FILE_MAIN.read_text(encoding="utf-8")
    blocks = re.split(r"\n## فاتورة رقم ", text)[1:]
    rows = []
    for block in blocks:
        log["invoices_found_main"] += 1
        header_line, _, rest = block.partition("\n")
        m = re.match(r"(.+?)\s+—\s+(\d{4}/\d{1,2}/\d{1,2})", header_line)
        if not m:
            log["unparsed_examples"].append(header_line[:80])
            continue
        invoice_no, invoice_date = m.group(1).strip(), m.group(2).strip()

        fence = re.search(r"```\n(.*?)\n```", rest, re.S)
        if not fence:
            continue
        body = fence.group(1)
        body_lines = body.split("\n")

        cust_code = ""
        cust_name = ""
        phone = ""
        for ln in body_lines[:5]:
            cm = re.search(r"الكود\s*/\s*(\S+)", ln)
            if cm:
                cust_code = cm.group(1)
            nm = re.search(r"اسم العميل\s*/\s*(.*?)\s+التليفون", ln)
            if nm:
                cust_name = nm.group(1).strip()
            pm = re.search(r"(?:التليفون|الموبايل)\s*/\s*(01\d{9})", ln)
            if pm and not phone:
                phone = pm.group(1)

        inv_total_m = re.search(r"إجمالى الفاتورة\s*/\s*(-?[\d.,]+)", body)
        inv_total = parse_num(inv_total_m.group(1)) if inv_total_m else None
        is_bonus = "بونص" in body

        item_lines = []
        for ln in body_lines:
            ln = ln.strip()
            toks = ln.split()
            if len(toks) < 6:
                continue
            if not NUM_RE.match(toks[0]):
                continue
            if not re.match(r"^\d+$", toks[1]):
                continue
            # exclude summary lines that start with a number by accident (rare)
            if "إجمالى" in ln or "ضريبة" in ln or "الباقي" in ln:
                continue
            tail5 = toks[-5:]
            tail4 = toks[-4:]
            if len(toks) >= 7 and all(NUM_RE.match(t) for t in tail5):
                item_lines.append((toks, ln, 5))
            elif len(toks) >= 6 and all(NUM_RE.match(t) for t in tail4):
                # rare OCR/extraction artifact: one pct column (discount or tax) dropped
                item_lines.append((toks, ln, 4))

        if not item_lines:
            log["invoice_blocks_no_items_main"] += 1
            continue

        line_total_sum = 0.0
        parsed_items = []
        for toks, raw, ncols in item_lines:
            seq = toks[0]
            item_code = toks[1]
            if ncols == 5:
                qty, price, disc_pct, tax_pct, total = (parse_num(x) for x in toks[-5:])
                item_name = " ".join(toks[2:-5]).strip()
            else:
                qty, price, pct, total = (parse_num(x) for x in toks[-4:])
                disc_pct, tax_pct = pct, None
                item_name = " ".join(toks[2:-4]).strip()
            if not item_name:
                continue
            parsed_items.append(dict(
                seq=seq, item_code=item_code, item_name_raw=item_name,
                qty=qty, unit_price=price, discount_pct=disc_pct, tax_pct=tax_pct,
                line_total=total,
            ))
            line_total_sum += total or 0.0

        if not parsed_items:
            continue

        recon_ok = inv_total is not None and abs(line_total_sum - inv_total) < max(1.0, 0.01 * abs(inv_total))
        if not recon_ok:
            log["invoices_reconciliation_fail_main"] += 1
            if len(log["reconciliation_fail_examples"]) < 15:
                log["reconciliation_fail_examples"].append(
                    dict(invoice_no=invoice_no, sum=line_total_sum, reported=inv_total)
                )

        for it in parsed_items:
            rows.append(dict(
                source="main_2025_2026H1", invoice_no=invoice_no, invoice_date=invoice_date,
                customer_code=cust_code, customer_name_raw=cust_name, phone=phone,
                is_bonus=is_bonus, invoice_reported_total=inv_total,
                **it,
            ))
        log["invoices_parsed_main"] += 1
    return rows


def parse_june_file():
    text = FILE_JUNE.read_text(encoding="utf-8")
    blocks = re.split(r"\n## فاتورة ", text)[1:]
    rows = []
    for block in blocks:
        log["invoices_found_june"] += 1
        header_line, _, rest = block.partition("\n")
        m = re.match(r"(\S+)\s+—.*?—\s+(\d{4}/\d{1,2}/\d{1,2})", header_line)
        if not m:
            log["unparsed_examples"].append("[june] " + header_line[:80])
            continue
        invoice_no, invoice_date = m.group(1), m.group(2)

        meta_line = rest.split("\n", 1)[0]
        cm = re.search(r"الكود:\s*(\S+)", meta_line)
        nm = re.search(r"العميل:\s*([^|]+?)\s*(?:\||$)", meta_line)
        pm = re.search(r"(01\d{9})", meta_line)
        cust_code = cm.group(1) if cm else ""
        cust_name = nm.group(1).strip() if nm else ""
        phone = pm.group(1) if pm else ""

        inv_total_m = re.search(r"إجمالى الفاتورة:\s*\*\*(-?[\d.,]+)\*\*", block)
        inv_total = parse_num(inv_total_m.group(1)) if inv_total_m else None
        is_bonus = "بونص" in block

        table_rows = re.findall(r"^\|\s*\d+\s*\|.*\|$", block, re.M)
        parsed_items = []
        line_total_sum = 0.0
        for tr in table_rows:
            cells = [c.strip() for c in tr.strip("|").split("|")]
            if len(cells) != 9:
                continue
            seq, item_code, item_name, unit, qty, price, tax_pct, disc_pct, total = cells
            qty_n, price_n, tax_n, disc_n, total_n = (parse_num(x) for x in (qty, price, tax_pct, disc_pct, total))
            item_name_full = f"{item_name} ({unit})" if unit else item_name
            parsed_items.append(dict(
                seq=seq, item_code=item_code, item_name_raw=item_name,
                qty=qty_n, unit_price=price_n, discount_pct=disc_n, tax_pct=tax_n,
                line_total=total_n,
            ))
            line_total_sum += total_n or 0.0

        if not parsed_items:
            continue
        for it in parsed_items:
            rows.append(dict(
                source="june_2026", invoice_no=invoice_no, invoice_date=invoice_date,
                customer_code=cust_code, customer_name_raw=cust_name, phone=phone,
                is_bonus=is_bonus, invoice_reported_total=inv_total,
                **it,
            ))
        log["invoices_parsed_june"] += 1
    return rows


def main():
    rows = parse_main_file() + parse_june_file()
    log["line_items_total"] = len(rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source", "invoice_no", "invoice_date", "customer_code", "customer_name_raw",
                  "phone", "is_bonus", "invoice_reported_total", "seq", "item_code",
                  "item_name_raw", "qty", "unit_price", "discount_pct", "tax_pct", "line_total"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(json.dumps(log, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
