"""
Parse the second source file (فواتير_المبيعات_يونيو_2026-1.md), which uses a
different markdown-table export format than the main file. Appends rows to the
same invoice_lines.csv / invoices_header.csv produced by parse_invoices.py.
"""
import re
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "فواتير_المبيعات_يونيو_2026-1.md"
OUT_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCE_TAG = "june_2026"

KEY_MAP = {
    "الكود": "customer_code",
    "العميل": "customer_name",
    "التليفون": "phone",
    "الموبايل": "mobile",
    "العنوان": "address",
}

INVOICE_HEADER_RE = re.compile(r"^## فاتورة\s+(\S+)\s+—\s+صفحة\s+(\d+)\s+—\s+(.*)$")


def to_float(s):
    if s is None:
        return None
    s = s.replace(",", "").replace("**", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_kv_line(line):
    out = {}
    for part in line.split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k = k.strip()
        field = KEY_MAP.get(k)
        if field:
            out[field] = v.strip()
    return out


def parse_footer_line(line):
    out = {}
    footer_map = {
        "إجمالى الفاتورة": "invoice_total",
        "ضريبة المبيعات": "tax_total",
        "الباقي": "remaining",
        "المدفوع": "paid",
        "عدد كميات الفاتورة": "total_qty",
    }
    for part in line.split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k = k.strip()
        field = footer_map.get(k)
        if field:
            out[field] = to_float(v)
    return out


def main():
    text = SRC.read_text(encoding="utf-8")
    lines = text.split("\n")

    headers = []
    items = []
    errors = []

    cur = None
    cur_items = []
    in_table = False
    table_header_seen = False

    def flush():
        nonlocal cur, cur_items
        if cur is not None:
            headers.append(cur)
            items.extend(cur_items)
        cur = None
        cur_items = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = INVOICE_HEADER_RE.match(line.strip())
        if m:
            flush()
            invoice_id, page_no, date_str = m.group(1), m.group(2), m.group(3)
            cur = {
                "invoice_id": invoice_id,
                "source_file": SOURCE_TAG,
                "page_no": page_no,
                "date_time_raw": date_str,
            }
            in_table = False
            table_header_seen = False
            i += 1
            continue

        if cur is not None:
            stripped = line.strip()
            if stripped.startswith("الكود:"):
                cur.update(parse_kv_line(stripped))
            elif stripped.startswith("| م |"):
                table_header_seen = True
                in_table = True
            elif stripped.startswith("|---"):
                pass  # markdown separator row
            elif in_table and stripped.startswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if len(cells) == 9 and cells[0].isdigit():
                    (seq, item_code, item_name, unit, qty, price, tax_pct, disc_pct, total) = cells
                    items.append({
                        "invoice_id": cur["invoice_id"],
                        "source_file": SOURCE_TAG,
                        "line_seq": seq,
                        "item_code": item_code,
                        "item_name_raw": item_name.strip(),
                        "unit_raw": unit.strip(),
                        "qty": to_float(qty),
                        "unit_price": to_float(price),
                        "discount_pct": to_float(disc_pct),
                        "tax_pct": to_float(tax_pct),
                        "line_total": to_float(total),
                    })
                else:
                    errors.append({"invoice_id": cur["invoice_id"], "source_file": SOURCE_TAG,
                                    "error": f"item_row_shape_unexpected: {stripped!r}"})
            elif stripped.startswith("إجمالى الفاتورة"):
                cur.update(parse_footer_line(stripped))
                in_table = False
        i += 1
    flush()

    # split date_time_raw -> date/time
    for h in headers:
        raw = h.get("date_time_raw", "")
        m = re.match(r"^([\d/]+)(?:\s+(.*))?$", raw)
        if m:
            h["date"] = m.group(1)
            h["time"] = m.group(2)

    header_fields = [
        "invoice_id", "source_file", "date", "time", "customer_code", "customer_name",
        "phone", "address", "mobile", "invoice_total", "tax_total", "paid", "remaining",
        "total_qty", "notes",
    ]
    item_fields = [
        "invoice_id", "source_file", "line_seq", "item_code", "item_name_raw", "unit_raw",
        "qty", "unit_price", "discount_pct", "tax_pct", "line_total",
    ]

    with open(OUT_DIR / "invoices_header_june2026.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header_fields)
        w.writeheader()
        for h in headers:
            w.writerow({k: h.get(k) for k in header_fields})

    with open(OUT_DIR / "invoice_lines_june2026.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=item_fields)
        w.writeheader()
        for it in items:
            w.writerow({k: it.get(k) for k in item_fields})

    with open(OUT_DIR / "parse_anomalies_june2026.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["invoice_id", "source_file", "error"])
        w.writeheader()
        w.writerows(errors)

    print(f"invoices parsed: {len(headers)}")
    print(f"line items parsed: {len(items)}")
    print(f"parse anomalies: {len(errors)}")


if __name__ == "__main__":
    main()
