"""
Parse ABOHASHEM sales-invoice markdown files (auto-converted from Crystal Reports PDF)
into a clean, structured line-item dataset. Source files are read-only inputs; nothing
here fabricates values - unparseable lines are logged to data/parse_anomalies.csv for
transparency instead of being silently guessed at.
"""
import re
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    (ROOT / "فواتير المبيعات من 112025 الى 3152026.md", "main_2025_2026"),
    (ROOT / "فواتير_المبيعات_يونيو_2026-1.md", "june_2026"),
]
OUT_DIR = Path(__file__).resolve().parents[1] / "data"

KNOWN_UNITS = {"كيس", "طبق", "كيلو", "علبة", "كرتونة", "قطعة"}

HEADER_RE = re.compile(r"^فاتورة مبيعات رقم\s+(.+)$")
DATE_RE = re.compile(r"^تحريرا في\s*:\s*([\d/]+)(?:\s+([\d:]+\s*[AP]M))?\s*الكود\s*/\s*(\S*)")
CUSTOMER_RE = re.compile(r"^اسم العميل\s*/\s*(.*?)\s*التليفون\s*/\s*(\S*)\s*$")
ADDR_RE = re.compile(r"^العنوان\s*/\s*(.*?)\s*الموبايل\s*/\s*(\S*)\s*$")
TOTAL_RE = re.compile(r"^إجمالى الفاتورة\s*/\s*(-?[\d.,]+-?)")
TAX_RE = re.compile(r"^ضريبة المبيعات\s*/\s*(-?[\d.,]+-?)")
PAID_RE = re.compile(
    r"^المدفوع\s*/\s*(-?[\d.,]+-?)\s*الباقي\s*/\s*(-?[\d.,]+-?)\s*عدد كميات الفاتورة\s*(-?[\d.,]+-?)"
)
NOTES_RE = re.compile(r"^ملحظات\s*/\s*(.*)$")
ITEM_HEAD_RE = re.compile(r"^(\d+)\s+(\d+)\s+(.*)$")


def to_float(s):
    if s is None:
        return None
    s = s.replace(",", "").strip()
    if s == "":
        return None
    negative = s.endswith("-")
    if negative:
        s = s[:-1]
    try:
        v = float(s)
        return -v if negative else v
    except ValueError:
        return None


def parse_item_line(line, invoice_id, line_no_seq):
    m = ITEM_HEAD_RE.match(line.strip())
    if not m:
        return None, f"item_line_no_match: {line!r}"
    seq, item_code, rest = m.group(1), m.group(2), m.group(3)
    toks = rest.split()
    if len(toks) < 5:
        return None, f"item_line_too_short: {line!r}"
    # last 5 tokens should be numeric: qty, unit_price, discount_pct, tax_pct, total
    tail = toks[-5:]
    numeric_re = re.compile(r"^-?[\d.,]+-?$")
    fields_dropped = 0
    if not all(numeric_re.match(t) for t in tail):
        # rare Crystal Reports extraction glitch: one numeric column (usually a
        # zero-valued tax%) is missing. Fall back to 4 trailing numeric tokens:
        # qty, unit_price, discount_pct, total - tax_pct is left unknown (not
        # fabricated as 0) and the row is flagged in the anomaly log.
        tail = toks[-4:]
        fields_dropped = 1
        if not all(numeric_re.match(t) for t in tail):
            return None, f"item_line_tail_not_numeric: {line!r}"
        name_tokens = toks[:-4]
    else:
        name_tokens = toks[:-5]
    unit = None
    if name_tokens and name_tokens[-1] in KNOWN_UNITS:
        unit = name_tokens[-1]
        name_tokens = name_tokens[:-1]
    item_name_raw = " ".join(name_tokens).strip()
    if fields_dropped:
        qty, price, disc, total = (to_float(t) for t in tail)
        tax = None
    else:
        qty, price, disc, tax, total = (to_float(t) for t in tail)
    row = {
        "invoice_id": invoice_id,
        "line_seq": seq,
        "item_code": item_code,
        "item_name_raw": item_name_raw,
        "unit_raw": unit,
        "qty": qty,
        "unit_price": price,
        "discount_pct": disc,
        "tax_pct": tax,
        "line_total": total,
    }
    err = f"item_line_tax_pct_column_missing: {line!r}" if fields_dropped else None
    return row, err


def parse_block(block_text):
    lines = [l for l in block_text.split("\n") if l.strip() != ""]
    header = {}
    items = []
    errors = []
    invoice_id = None
    for line in lines:
        m = HEADER_RE.match(line)
        if m:
            invoice_id = m.group(1).strip()
            header["invoice_id"] = invoice_id
            continue
        m = DATE_RE.match(line)
        if m:
            header["date"] = m.group(1)
            header["time"] = m.group(2)
            header["customer_code"] = m.group(3)
            continue
        m = CUSTOMER_RE.match(line)
        if m:
            header["customer_name"] = m.group(1).strip()
            header["phone"] = m.group(2)
            continue
        m = ADDR_RE.match(line)
        if m:
            header["address"] = m.group(1).strip()
            header["mobile"] = m.group(2)
            continue
        m = TOTAL_RE.match(line)
        if m:
            header["invoice_total"] = to_float(m.group(1))
            continue
        m = TAX_RE.match(line)
        if m:
            header["tax_total"] = to_float(m.group(1))
            continue
        m = PAID_RE.match(line)
        if m:
            header["paid"] = to_float(m.group(1))
            header["remaining"] = to_float(m.group(2))
            header["total_qty"] = to_float(m.group(3))
            continue
        m = NOTES_RE.match(line)
        if m:
            header["notes"] = (header.get("notes", "") + " | " + m.group(1)).strip(" |")
            continue
        # else must be an item line
        row, err = parse_item_line(line, invoice_id, len(items))
        if row:
            items.append(row)
            if err:
                errors.append(err)
        else:
            errors.append(err)
    return header, items, errors


def main():
    all_headers = []
    all_items = []
    all_errors = []
    for path, source_tag in SOURCES:
        if not path.exists():
            print(f"MISSING SOURCE: {path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(r"```\n(.*?)\n```", text, re.S)
        for b in blocks:
            header, items, errors = parse_block(b)
            header["source_file"] = source_tag
            all_headers.append(header)
            for it in items:
                it["source_file"] = source_tag
            all_items.extend(items)
            for e in errors:
                all_errors.append({"invoice_id": header.get("invoice_id"), "source_file": source_tag, "error": e})

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    header_fields = [
        "invoice_id", "source_file", "date", "time", "customer_code", "customer_name",
        "phone", "address", "mobile", "invoice_total", "tax_total", "paid", "remaining",
        "total_qty", "notes",
    ]
    with open(OUT_DIR / "invoices_header.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header_fields)
        w.writeheader()
        for h in all_headers:
            w.writerow({k: h.get(k) for k in header_fields})

    item_fields = [
        "invoice_id", "source_file", "line_seq", "item_code", "item_name_raw", "unit_raw",
        "qty", "unit_price", "discount_pct", "tax_pct", "line_total",
    ]
    with open(OUT_DIR / "invoice_lines.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=item_fields)
        w.writeheader()
        for it in all_items:
            w.writerow({k: it.get(k) for k in item_fields})

    with open(OUT_DIR / "parse_anomalies.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["invoice_id", "source_file", "error"])
        w.writeheader()
        w.writerows(all_errors)

    print(f"invoices parsed: {len(all_headers)}")
    print(f"line items parsed: {len(all_items)}")
    print(f"parse anomalies: {len(all_errors)}")


if __name__ == "__main__":
    main()
