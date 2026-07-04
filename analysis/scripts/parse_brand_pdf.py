import re, csv, sys

def load_lines(path):
    lines = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('--- page'):
                continue
            if line.strip() in ('م', 'اسم الصنف', 'البر اند', 'الكرتونة', ''):
                continue
            lines.append(line)
    return lines

def parse_records(lines):
    records = []
    cur_num = None
    cur_text_parts = []
    for line in lines:
        m = re.match(r'^(\d+)(.*)$', line)
        if m:
            # flush previous record if any text collected without being closed (shouldn't happen normally)
            cur_num = int(m.group(1))
            rest = m.group(2)
            cur_text_parts = [rest] if rest.strip() else []
            records.append({'num': cur_num, 'parts': cur_text_parts})
        else:
            if records:
                records[-1]['parts'].append(line)
    return records

if __name__ == '__main__':
    lines = load_lines(sys.argv[1])
    records = parse_records(lines)
    for r in records[:15]:
        print(r['num'], r['parts'])
    print('total records:', len(records))
