import re, csv, sys
from parse_brand_pdf import load_lines, parse_records

def build_brand_table():
    lines = load_lines('data/brand_raw.txt')
    records = parse_records(lines)
    brands = set()
    for r in records:
        if len(r['parts']) > 1:
            brands.add(r['parts'][-1].strip())
    rows = []
    for r in records:
        joined = re.sub(r'\s+', ' ', ' '.join(p.strip() for p in r['parts'])).strip()
        brand = None
        for b in sorted(brands, key=len, reverse=True):
            if joined.endswith(b):
                brand = b
                joined = joined[:-len(b)].strip()
                break
        rows.append({'ref_num': r['num'], 'item_name_ref': joined, 'brand': brand})
    with open('data/brand_map.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['ref_num', 'item_name_ref', 'brand'])
        w.writeheader()
        w.writerows(rows)
    return rows

def build_carton_table():
    lines = load_lines('data/carton_raw.txt')
    records = parse_records(lines)
    pat = re.compile(r'العدد\s*(\d+)\s*(علبة|كيس)')
    rows = []
    for r in records:
        joined = re.sub(r'\s+', ' ', ' '.join(p.strip() for p in r['parts'])).strip()
        m = pat.search(joined)
        if m:
            qty, unit_pack = int(m.group(1)), m.group(2)
            item = joined[:m.start()].strip()
        else:
            qty, unit_pack, item = None, None, joined
        rows.append({'ref_num': r['num'], 'item_name_ref': item, 'units_per_carton': qty, 'pack_type': unit_pack})
    with open('data/carton_capacity.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['ref_num', 'item_name_ref', 'units_per_carton', 'pack_type'])
        w.writeheader()
        w.writerows(rows)
    return rows

if __name__ == '__main__':
    b = build_brand_table()
    c = build_carton_table()
    print('brand rows:', len(b), 'carton rows:', len(c))
