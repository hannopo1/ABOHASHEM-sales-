"""
Map each invoice item_code to a Brand using: (1) explicit brand keyword present
in the item's own name (highest confidence, directly evidenced by the source
text), (2) fuzzy match against the brand-classification PDF (تصنيف الاصناف
كبراند) when no keyword is present, (3) Unclassified when neither succeeds -
never force a low-confidence guess into a real brand bucket.
"""
import pandas as pd
import re
import difflib

def norm(s):
    if pd.isna(s):
        return ''
    s = str(s)
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    s = re.sub(r'[^\w]', '', s)
    return s.lower()

KEYWORDS = [
    ('الهنا', 'الهنا'),
    ('اسبشيال', 'اسبشيال'),
    ('اسبيشيال', 'اسبشيال'),
    ('اسباشيل', 'اسبشيال'),
    ('ابوهاشم', 'ابوهاشم'),
    ('ابو هاشم', 'ابوهاشم'),
    ('أبو هاشم', 'ابوهاشم'),
]

FUZZY_THRESHOLD = 0.75

def main():
    lines = pd.read_csv('data/invoice_lines_merged.csv')
    brand_ref = pd.read_csv('data/brand_map.csv')
    brand_ref['norm'] = brand_ref['item_name_ref'].map(norm)

    invoice_items = (lines.groupby('item_code')['item_name_raw']
                      .agg(lambda x: x.value_counts().index[0])
                      .reset_index())

    rows = []
    for _, r in invoice_items.iterrows():
        name = r['item_name_raw']
        name_n = norm(name)
        brand, method, score = None, None, None
        for kw, b in KEYWORDS:
            if kw in str(name):
                brand, method, score = b, 'keyword_in_name', 1.0
                break
        if brand is None:
            best_ref, best_score = None, 0.0
            for _, ref in brand_ref.iterrows():
                s = difflib.SequenceMatcher(None, name_n, ref['norm']).ratio()
                if s > best_score:
                    best_score, best_ref = s, ref
            if best_score >= FUZZY_THRESHOLD:
                brand, method, score = best_ref['brand'], 'fuzzy_match_brand_pdf', round(best_score, 3)
            else:
                brand, method, score = 'غير مصنف (صنف جديد/غير مدرج بملف التصنيف)', 'unclassified', round(best_score, 3)
        rows.append({'item_code': r['item_code'], 'item_name': name, 'brand': brand,
                     'match_method': method, 'match_score': score})

    out = pd.DataFrame(rows).sort_values('item_code')
    out.to_csv('data/item_brand_map.csv', index=False, encoding='utf-8-sig')
    print(out['brand'].value_counts())
    print('\nunclassified items:')
    print(out[out.match_method == 'unclassified'][['item_code', 'item_name', 'match_score']].to_string(index=False))

if __name__ == '__main__':
    main()
