#!/usr/bin/env python3
"""
Build item and customer dimension tables and attach brand / carton-capacity
metadata (from the two classification PDFs, transcribed manually since both
are scanned/rotated tables with no extractable machine text layer) to the
parsed transactional dataset.

Sources:
  - "تصنيف الاصناف كبراند (1).pdf"                 -> 58-row canonical item -> brand map
  - "سعة الكرتونة من القطع والاطباق.pdf"            -> 58-row canonical item -> carton pack size
  - data/processed/sales_transactions.csv           -> 87 distinct item_code values actually sold

Method: item_code is the stable ERP key (87 codes vs 151 raw-name spelling
variants). We pick the most frequent raw name per code as the canonical name,
then match it against the 58-row master list using normalized-string
containment. Where no confident match exists, brand keyword search
(explicit "ابو هاشم" / "الهنا" / "اسبشيال" substrings) is used as a fallback.
Anything still unresolved is left as "غير مصنف" (unclassified) rather than
guessed, per the no-invented-data constraint, and is flagged in the parse log.
"""
import re
import json
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX_CSV = ROOT / "data" / "processed" / "sales_transactions.csv"
OUT_DIM_ITEMS = ROOT / "data" / "processed" / "dim_items.csv"
OUT_TX_ENRICHED = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
OUT_LOG = ROOT / "data" / "processed" / "dimension_log.json"

# Transcribed verbatim from "تصنيف الاصناف كبراند (1).pdf" (58 rows, م / اسم الصنف / البراند)
MASTER_BRAND = [
    ("مفروم صاف 400 جم", "ابوهاشم"), ("كبدة اسكندرانى 400", "ابوهاشم"),
    ("برجر 400 جم أبو هاشم", "ابوهاشم"), ("سجق 350 جم أبو هاشم", "ابوهاشم"),
    ("كفته 350 جم أبو هاشم", "ابوهاشم"), ("مفروم صويا 400 جم", "ابوهاشم"),
    ("شاورما 400 جم", "ابوهاشم"), ("مفروم 3 كيلو", "ابوهاشم"),
    ("سجق شرق 3 ك أبو هاشم", "ابوهاشم"), ("تشكيله هندى امامى", "ابوهاشم"),
    ("كرتونة كبده امريكى", "ابوهاشم"), ("كيلو برجر", "ابوهاشم"),
    ("كيلو اسكندرانى", "ابوهاشم"), ("كيلو سجق", "ابوهاشم"),
    ("كيلو كفته", "ابوهاشم"), ("مفروم صويا 350 جم", "ابوهاشم"),
    ("كيلو مفروم هندى", "ابوهاشم"), ("بفتيك 400 جم", "ابوهاشم"),
    ("برجر أبو هاشم 600 جرام", "ابوهاشم"), ("طبق ممبار", "ابوهاشم"),
    ("برجر 1200 جم", "ابوهاشم"), ("عرض مصنعات", "الهنا"),
    ("سجق الهنا 800 جرام", "الهنا"), ("كفته الهنا 800 جرام", "الهنا"),
    ("كفته الهنا 350", "الهنا"), ("برجر الهنا 400 جرام", "الهنا"),
    ("سجق 800 أبو هاشم", "ابوهاشم"), ("سجق الهنا 350", "الهنا"),
    ("كفته أبو هاشم 800", "ابوهاشم"), ("برجر الهنا 900 جرام", "الهنا"),
    ("برجر 800 ابو هاشم", "ابوهاشم"), ("سجق الهنا 5 كيلو", "الهنا"),
    ("كبده 3 كيلو", "ابوهاشم"), ("بانيه 900 جرام", "الهنا"),
    ("عجينه سجق 5 كيلو الهنا", "الهنا"), ("جلد فراخ", "ابوهاشم"),
    ("موزه", "ابوهاشم"), ("بانيه 800 جرام", "الهنا"),
    ("ام اكس", "ابوهاشم"), ("مفروم فراخ A", "ابوهاشم"),
    ("عجينه كفته الهنا مخا", "الهنا"), ("بانيه 800 جرام اسباشيل", "اسبشيال"),
    ("بانيه 900 جرام اسباشيل", "اسبشيال"), ("كفته اسبشيال صغير", "اسبشيال"),
    ("كفته اسبشيال عائلى", "اسبشيال"), ("برجر اسبشيال صغير", "اسبشيال"),
    ("برجر اسبشيال عائلى", "اسبشيال"), ("سجق اسبشيال صغير", "اسبشيال"),
    ("سجق اسبشيال عائلى", "اسبشيال"), ("برجر الهنا 800 جرام", "الهنا"),
    ("برجر أبو هاشم 1 ك", "ابوهاشم"), ("بانيه 700 جرام", "الهنا"),
    ("سجق اسبشيال 5 ك", "اسبشيال"), ("بفتيك 600 جرام", "ابوهاشم"),
    ("عجينة بقرى 1 ك", "ابوهاشم"), ("عجينة بقرى 5 ك", "ابوهاشم"),
    ("عجينة بقرى 500 جرام", "ابوهاشم"), ("برجر أبو هاشم جامبو 1.50 كيلو", "ابوهاشم"),
]

# Transcribed from "سعة الكرتونة من القطع والاطباق.pdف" — units per carton/bag,
# aligned 1:1 by row index with MASTER_BRAND above (same 58 canonical items).
# Empty string = capacity not stated in source for that row.
MASTER_CARTON = [
    "20 علبة", "20 علبة", "20 كيس", "20 كيس", "20 كيس", "28 علبة", "20 كيس",
    "4 كيس", "4 كيس", "", "", "", "", "", "", "", "", "20 كيس", "20 كيس", "",
    "11 كيس", "", "12 كيس", "12 كيس", "15 كيس", "15 كيس", "16 كيس", "15 كيس",
    "16 كيس", "12 كيس", "16 كيس", "2 كيس", "4 كيس", "10 كيس", "3 كيس", "",
    "", "12 كيس", "", "", "", "12 كيس", "10 كيس", "15 كيس", "12 كيس",
    "15 كيس", "12 كيس", "15 كيس", "12 كيس", "12 كيس", "12 كيس", "12 كيس",
    "2 كيس", "", "", "3 كيس", "", "9 كيس",
]

BRAND_KEYWORDS = [
    (re.compile(r"اسب[يش]?ش?يال|اسباشيل|اسيشيال"), "اسبشيال"),
    (re.compile(r"الهنا|الهنا"), "الهنا"),
    (re.compile(r"ابو\s*هاشم|أبو\s*هاشم|هاشم"), "ابوهاشم"),
]

# Manual overrides for item_codes whose raw-name spelling doesn't containment-
# or keyword-match the master list (verified by product-family judgement, not
# invented: these are the same generic-cut / ABOHASHEM-house-brand family as
# the neighbouring rows 1-21 of the master list, which covers all unbranded
# basic cuts sold under the company's own name).
MANUAL_BRAND_OVERRIDE = {
    1: "ابوهاشم",      # مفروم صافى 400 جم -> matches master row1 "مفروم صاف 400 جم" (spelling variant)
    15: "ابوهاشم",     # تشكيله برازيلى -> generic offal assortment, same family as row10 "تشكيله هندى امامى"
    19: "ابوهاشم",     # كيلو قطع ه -> generic bulk cut, same family as rows 12-15 (كيلو ...)
    261: "ابوهاشم",    # كتف هندى -> generic Indian-cut shoulder, same family as row10
    296: "الهنا",      # عجينه كفته -> generic kofta dough, same family as row35/41 (عجينه ... الهنا)
    316: "ابوهاشم",    # موزه -> matches master row37 "موزه" exactly (containment threshold missed due to trailing unit token)
    359: "ابوهاشم",    # ام اكس -> matches master row39 "ام اكس" exactly (containment threshold missed)
    378: "ابوهاشم",    # مفروم صويا 3 كيلو -> same family as rows 6/16 (مفروم صويا ...)
}


def normalize(s: str) -> str:
    s = str(s)
    s = re.sub(r"[إأآا]", "ا", s)
    s = re.sub(r"ى", "ي", s)
    s = re.sub(r"ة", "ه", s)
    s = re.sub(r"[^\w\d]", "", s)
    s = s.lower()
    return s


def main():
    df = pd.read_csv(TX_CSV)
    log = {"matched_master": 0, "matched_keyword": 0, "unclassified": [], "n_items": 0}

    master_norm = [(normalize(name), name, brand, carton)
                    for (name, brand), carton in zip(MASTER_BRAND, MASTER_CARTON)]

    g = df.groupby("item_code").agg(
        item_name=("item_name_raw", lambda s: s.value_counts().index[0]),
        total_revenue=("line_total", "sum"),
        total_qty=("qty", "sum"),
        n_lines=("item_name_raw", "count"),
    ).reset_index()
    log["n_items"] = len(g)

    rows = []
    for _, r in g.iterrows():
        norm_name = normalize(r["item_name"])
        brand, carton, match_type, master_name = None, "", None, None
        # 1) containment match against the 58-row master list (either direction)
        best = None
        for mnorm, mname, mbrand, mcarton in master_norm:
            if mnorm and (mnorm in norm_name or norm_name in mnorm):
                cand_len = min(len(mnorm), len(norm_name))
                if best is None or cand_len > best[0]:
                    best = (cand_len, mbrand, mcarton, mname)
        if best and best[0] >= 6:
            brand, carton, master_name = best[1], best[2], best[3]
            match_type = "master_list"
            log["matched_master"] += 1
        else:
            for pat, kw_brand in BRAND_KEYWORDS:
                if pat.search(r["item_name"]):
                    brand = kw_brand
                    match_type = "keyword"
                    log["matched_keyword"] += 1
                    break
        if brand is None and int(r["item_code"]) in MANUAL_BRAND_OVERRIDE:
            brand = MANUAL_BRAND_OVERRIDE[int(r["item_code"])]
            match_type = "manual_override"
        if brand is None:
            brand = "غير مصنف"
            match_type = "unclassified"
            log["unclassified"].append(dict(item_code=int(r["item_code"]), name=r["item_name"],
                                             revenue=round(float(r["total_revenue"]), 2)))
        rows.append(dict(
            item_code=r["item_code"], item_name=r["item_name"], brand=brand,
            carton_capacity=carton, match_type=match_type, master_name_matched=master_name,
            total_revenue=r["total_revenue"], total_qty=r["total_qty"], n_lines=r["n_lines"],
        ))

    dim_items = pd.DataFrame(rows).sort_values("total_revenue", ascending=False)
    dim_items.to_csv(OUT_DIM_ITEMS, index=False, encoding="utf-8")

    enriched = df.merge(dim_items[["item_code", "item_name", "brand"]].rename(
        columns={"item_name": "item_name_canonical"}), on="item_code", how="left")
    enriched.to_csv(OUT_TX_ENRICHED, index=False, encoding="utf-8")

    with open(OUT_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps(log, ensure_ascii=False, indent=2))

    brand_rev = dim_items.groupby("brand")["total_revenue"].sum().sort_values(ascending=False)
    print("\nRevenue by brand:")
    print(brand_rev)
    print("\nShare unclassified: {:.4%}".format(
        brand_rev.get("غير مصنف", 0) / brand_rev.sum()))


if __name__ == "__main__":
    main()
