"""
Match each invoice item_code to its packing factor (units per carton) using
fuzzy text matching against the carton-capacity reference PDF
(سعة الكرتونة من القطع والاطباق). Produces data/item_carton_map.csv, then
joins it with item_brand_map.csv into the final data/item_master.csv used by
every downstream script and dashboard.
"""
import re
import difflib
import pandas as pd

FUZZY_THRESHOLD = 0.80


def norm(s):
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[^\w]", "", s)
    return s.lower()


def main():
    lines = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    carton = pd.read_csv("data/carton_capacity.csv")
    carton["norm"] = carton["item_name_ref"].map(norm)
    carton_valid = carton.dropna(subset=["units_per_carton"])

    invoice_items = (lines.groupby("item_code")["item_name_raw"]
                      .agg(lambda x: x.value_counts().index[0]).reset_index())

    rows = []
    for _, r in invoice_items.iterrows():
        name_n = norm(r["item_name_raw"])
        best_ref, best_score = None, 0.0
        for _, ref in carton_valid.iterrows():
            s = difflib.SequenceMatcher(None, name_n, ref["norm"]).ratio()
            if s > best_score:
                best_score, best_ref = s, ref
        if best_score >= FUZZY_THRESHOLD:
            rows.append({"item_code": r["item_code"], "item_name": r["item_name_raw"],
                         "units_per_carton": best_ref["units_per_carton"], "pack_type": best_ref["pack_type"],
                         "match_score": round(best_score, 3)})
        else:
            rows.append({"item_code": r["item_code"], "item_name": r["item_name_raw"],
                         "units_per_carton": None, "pack_type": None, "match_score": round(best_score, 3)})

    out = pd.DataFrame(rows).sort_values("item_code")
    out.to_csv("data/item_carton_map.csv", index=False, encoding="utf-8-sig")
    print("matched:", out["units_per_carton"].notna().sum(), "/", len(out))

    # join with brand map into the final item master table
    bm = pd.read_csv("data/item_brand_map.csv", dtype={"item_code": str})
    cm = out[["item_code", "units_per_carton", "pack_type"]]
    master = bm.merge(cm, on="item_code", how="left")
    master.to_csv("data/item_master.csv", index=False, encoding="utf-8-sig")
    print("item_master rows:", len(master))


if __name__ == "__main__":
    main()
