"""Parse ABOHASHEM's two raw sales-invoice markdown exports into a unified schema.

Source files (repo root):
  - "فواتير المبيعات من 112025 الى 3152026.md" : 4,591 invoices, 2025-01-01..2026-05-09,
    fenced plain-text blocks (Crystal Reports -> text conversion).
  - "فواتير_المبيعات_يونيو_2026-1.md" : 311 invoices, 2026-06-01..2026-06-30,
    markdown tables (scanned invoice images -> OCR conversion).

Both formats carry the same logical fields but with different layouts and some OCR
noise (unit names in particular are unreliable: طبق/طلى/طلق/طني/كس are all OCR
variants of the same unit). The discount%/tax% columns are also not reliably ordered
across files (verified by hand on samples with non-zero discounts), so this script
keeps them for reference only -- downstream analysis derives price/discount effects
from qty and line_total directly, which are always internally consistent.

Outputs two CSVs under analysis/data/:
  - invoices_header.csv : one row per invoice
  - invoices_lines.csv  : one row per invoice line item
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "data"
MAIN_FILE = ROOT / "فواتير المبيعات من 112025 الى 3152026.md"
JUNE_FILE = ROOT / "فواتير_المبيعات_يونيو_2026-1.md"

HEADER_FIELDS = [
    "invoice_no", "date", "customer_code", "customer_name", "phone",
    "total", "tax", "paid", "remaining", "total_qty", "notes", "source_file",
]
LINE_FIELDS = [
    "invoice_no", "line_no", "item_code", "item_name", "unit",
    "qty", "unit_price_field", "pct1", "pct2", "line_total", "source_file",
]

NUM = r"[-\d.]+"


def parse_main_file(text):
    headers, lines = [], []
    blocks = re.split(r"^## فاتورة رقم (.+?) — (\S+)\s*$", text, flags=re.M)
    # blocks[0] is preamble; then triples of (invoice_no, date, body)
    for i in range(1, len(blocks), 3):
        invoice_no, date, body = blocks[i], blocks[i + 1], blocks[i + 2]
        fence = re.search(r"```(.*?)```", body, flags=re.S)
        if not fence:
            continue
        content = fence.group(1)

        m_code = re.search(r"الكود\s*/\s*(\S+)", content)
        m_cust = re.search(r"اسم العميل\s*/\s*(.*?)\s*التليفون\s*/\s*(\S*)", content)
        m_total = re.search(rf"إجمالى الفاتورة\s*/\s*({NUM})", content)
        m_tax = re.search(rf"ضريبة المبيعات\s*/\s*({NUM})", content)
        m_paid = re.search(rf"المدفوع\s*/\s*({NUM})\s*الباقي\s*/\s*({NUM})", content)
        m_qty = re.search(rf"عدد كميات الفاتورة\s*({NUM})", content)
        m_notes = re.search(r"مل[حا]ظات\s*/\s*(.*)", content)

        headers.append({
            "invoice_no": invoice_no.strip(),
            "date": date.strip(),
            "customer_code": m_code.group(1) if m_code else "",
            "customer_name": m_cust.group(1).strip() if m_cust else "",
            "phone": m_cust.group(2).strip() if m_cust else "",
            "total": m_total.group(1) if m_total else "",
            "tax": m_tax.group(1) if m_tax else "",
            "paid": m_paid.group(1) if m_paid else "",
            "remaining": m_paid.group(2) if m_paid else "",
            "total_qty": m_qty.group(1) if m_qty else "",
            "notes": m_notes.group(1).strip() if m_notes else "",
            "source_file": MAIN_FILE.name,
        })

        for line in content.splitlines():
            line = line.strip()
            m = re.match(
                rf"^(\d+)\s+(\S+)\s+(.+?)\s+(طبق|كيلو|كيس|علبة|كرتونة|جركن|كيس \d+ كيلو)"
                rf"\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})$",
                line,
            )
            if not m:
                continue
            seq, code, name, unit, qty, price, pct1, pct2, total = m.groups()
            lines.append({
                "invoice_no": invoice_no.strip(),
                "line_no": seq,
                "item_code": code,
                "item_name": name.strip(),
                "unit": unit,
                "qty": qty,
                "unit_price_field": price,
                "pct1": pct1,
                "pct2": pct2,
                "line_total": total,
                "source_file": MAIN_FILE.name,
            })
    return headers, lines


def parse_june_file(text):
    headers, lines = [], []
    sections = re.split(r"^## فاتورة (\S+) — صفحة (\d+) — (.+?)\s*$", text, flags=re.M)
    for i in range(1, len(sections), 4):
        invoice_no, page, date, body = sections[i], sections[i + 1], sections[i + 2], sections[i + 3]

        m_code = re.search(r"الكود:\s*(\S+)", body)
        m_cust = re.search(r"العميل:\s*(.*?)(?:\s*\||$)", body)
        m_phone = re.search(r"(?:التليفون|الموبايل):\s*(\S+)", body)
        m_total = re.search(rf"إجمالى الفاتورة:\s*\*\*({NUM})\*\*", body)
        m_tax = re.search(rf"ضريبة المبيعات:\s*({NUM})", body)
        m_remaining = re.search(rf"الباقي:\s*({NUM})", body)
        m_paid = re.search(rf"المدفوع:\s*({NUM})", body)
        m_qty = re.search(rf"عدد كميات الفاتورة:\s*({NUM})", body)
        m_notes = re.search(r"ملاحظات:\s*(.*)", body)

        headers.append({
            "invoice_no": invoice_no.strip(),
            "date": date.strip(),
            "customer_code": m_code.group(1) if m_code else "",
            "customer_name": m_cust.group(1).strip() if m_cust else "",
            "phone": m_phone.group(1) if m_phone else "",
            "total": m_total.group(1) if m_total else "",
            "tax": m_tax.group(1) if m_tax else "",
            "paid": m_paid.group(1) if m_paid else "",
            "remaining": m_remaining.group(1) if m_remaining else "",
            "total_qty": m_qty.group(1) if m_qty else "",
            "notes": m_notes.group(1).strip() if m_notes else "",
            "source_file": JUNE_FILE.name,
        })

        for row in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\S+)\s*\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|\s*$", body, flags=re.M):
            seq, code, name, unit, qty, price, pct_a, pct_b, total = row.groups()
            lines.append({
                "invoice_no": invoice_no.strip(),
                "line_no": seq,
                "item_code": code,
                "item_name": name.strip(),
                "unit": unit.strip(),
                "qty": qty.strip(),
                "unit_price_field": price.strip(),
                "pct1": pct_a.strip(),
                "pct2": pct_b.strip(),
                "line_total": total.strip(),
                "source_file": JUNE_FILE.name,
            })
    return headers, lines


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    main_text = MAIN_FILE.read_text(encoding="utf-8")
    june_text = JUNE_FILE.read_text(encoding="utf-8")

    h1, l1 = parse_main_file(main_text)
    h2, l2 = parse_june_file(june_text)

    headers = h1 + h2
    lines = l1 + l2

    write_csv(OUT_DIR / "invoices_header.csv", HEADER_FIELDS, headers)
    write_csv(OUT_DIR / "invoices_lines.csv", LINE_FIELDS, lines)

    print(f"main file: {len(h1)} invoices parsed (expected 4591), {len(l1)} line items")
    print(f"june file: {len(h2)} invoices parsed (expected 311), {len(l2)} line items")
    print(f"total: {len(headers)} invoices, {len(lines)} line items")


if __name__ == "__main__":
    main()
