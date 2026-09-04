"""Expense line-item names: which spellings are the same item, and which are not.

Every entry in this file is a **human decision**, not a measurement. The six
2025 statements were written by hand, so one item appears under several
spellings across the months — «عمولة البيع +بدلات», «عمولة البيع +بدلات
والاكراميات» and «عمولة البيع +بدلات السفر والاكراميات» are one line in three
guises. Comparing an item month by month is impossible until those are read as
one, so this map says which raw labels collapse together.

Three rules keep the judgement honest:

1. **The raw label is never destroyed.** Every row keeps `label_raw`, and the
   app shows this table on screen so a reader can see exactly what was merged.
2. **A canonical name never crosses a group.** The key is (group, label_raw):
   an administrative «مرتبات» and a selling «مرتبات» are different money and
   stay apart, whatever they are called.
3. **Unmapped labels pass through literally.** Where the source is ambiguous
   the item keeps its own words — see «وهدايا ورشا» below.

Evidence used for each merge: the variants are *complementary across months*
(each month carries exactly one of them), which is what a renaming looks like,
as opposed to two items that co-occur. Where that test fails, nothing is merged.

Standard library only; imported by analysis/lib/statements.py.
"""

# (group, label_raw) -> canonical label.
ALIASES = {
    # --- administrative -----------------------------------------------------
    # July says «كهرباء», August-December say «فواتير كهرباء ونت». Six months,
    # one line each: the same utility bill, renamed once the internet was
    # billed with it.
    ("admin", "كهرباء"): "فواتير كهرباء ونت",

    # Insurance carries a different tail almost every month — «تامينات» in
    # July, «تامينات و اتعاب محمد عطية» August-November, «تامينات و حكومى» in
    # December. One line per month, so they are read as one item. The tails
    # (a named professional fee, a government charge) are visible in the alias
    # table and are NOT separated out: the statement never split them.
    ("admin", "تامينات و اتعاب محمد عطية"): "تامينات",
    ("admin", "تامينات و حكومى"): "تامينات",

    # Same lead item with qualifiers appended in two months.
    ("admin", "صحة وتموين وشرطة"): "صحة وتموين",
    ("admin", "صحة وتموين وهدايا ورشا"): "صحة وتموين",

    # December names the sub-contractor; July, October and November do not.
    ("admin", "تصنيع لدى الغير البانيه"): "تصنيع لدى الغير",

    # Spelling only: قطه -> قطع. Same six-month item.
    ("admin", "صيانات وقطه غيار"): "صيانات وقطع غيار",

    # NOT merged, deliberately:
    #   «وهدايا ورشا» (December, 60,405) — the source cell says only that, and
    #   it is far larger than any «صحة وتموين» month. It may continue the row
    #   above it, or abbreviate a longer name; the sheet does not say. Reading
    #   it into another item would invent a fact, so it stands alone under its
    #   own words and is flagged in the data-quality report.
    #   «حكومية» (October, 4,690) — a separate row in a month that already
    #   carries its own insurance line, so it is not the same item.
    #   «شقة العاملين» / «مياه شقة العاملين» — rent and water are two costs.

    # --- selling ------------------------------------------------------------
    # One commission line written three ways across the six months.
    ("selling", "عمولة البيع +بدلات"): "عمولة البيع +بدلات السفر والاكراميات",
    ("selling", "عمولة البيع +بدلات والاكراميات"):
        "عمولة البيع +بدلات السفر والاكراميات",

    # «زيت» carries a figure only in July and December of 2025, and December
    # spells out what it covers — as do all five 2026 statements. The fuller
    # name is the canonical one; the bare «زيت» folds into it.
    ("selling", "زيت"): "زيت + فلاتر للعربيات",

    # NOT merged: «ايجارات» (premises) and «ايجار عربية 1842» (a vehicle) are
    # different rentals even though their months happen to complement.

    # --- financing ----------------------------------------------------------
    # December's two rows say outright that they cover months 9 to 12. They are
    # the same two loans, posted as a catch-up — see LUMP_POSTINGS.
    ("financing", "مصاريف قرض المبادرة من شهر 9 الى شهر 12"):
        "مصاريف قرض المبادرة",
    ("financing", "مصاريق قرض السيارة من شهر 9 الى 12"):
        "مصاريف قرض السيارة والحساب",
    # Spelling only: مصاريق -> مصاريف.
    ("financing", "مصاريق قرض السيارة والحساب"): "مصاريف قرض السيارة والحساب",

    # ======================================================================
    # THE 2026 STATEMENTS — the same items, spelled by a broken text layer
    # ======================================================================
    # The 2026 documents are PDFs whose Arabic decomposes on extraction: صروف
    # for صرف, لا printed as ال, ي as ى, ت as ي. The words below are what the
    # page actually yields, and each is mapped to the name the 2025 workbook
    # already uses so one item can be followed across the whole series.
    #
    # No general de-mangler is written for this. A substitution table that
    # "fixes" Arabic would be right today and silently wrong on the next
    # document; every spelling here is one line someone read.

    # --- operating (a group only the 2026 statements have) -----------------
    ("operating", "تصنيع لدى الغير البانيه"): "تصنيع لدى الغير",
    ("operating", "فواتير كهرباء"): "فواتير الكهرباء",
    ("operating", "صيانات وقطه غيار"): "صيانات وقطع غيار",
    ("operating", "بدالت ومكافئات"): "بدلات ومكافئات",
    ("operating", "بدالت ومكافاة"): "بدلات ومكافئات",
    ("operating", "منظفات ومكافحة ."): "منظفات ومكافحة",
    # May calls the production payroll «مرتبات»; June and July name it. One
    # salary line per month in this group, so they are the same line — and the
    # group is part of the key, so this never touches the administrative or
    # the selling «مرتبات».
    ("operating", "مرتبات"): "مرتبات انتاج والمصنع",

    # --- administrative ----------------------------------------------------
    ("admin", "محاىم"): "محامى",
    ("admin", "تامينات وحكوىم"): "تامينات",
    ("admin", "تامينات و حكوىم"): "تامينات",
    ("admin", "بدالت ومكافئات"): "بدلات ومكافئات",
    ("admin", "مصاريف المكاتب"): "مصاريف المكتب",
    # «وهدايا ورشا» was left literal when only the 2025 workbook was read: it
    # appeared once, unexplained, and might have continued the row above it.
    # The five 2026 statements settle it — the line stands on its own in every
    # one of them, directly under the insurance line, and June and July spell
    # it out. So it is one item, and the December 2025 figure joins it.
    ("admin", "وهدايا ورشا"): "هدايا ورشاوى",
    ("admin", "هدايا ورشواى"): "هدايا ورشاوى",

    # --- selling -----------------------------------------------------------
    ("selling", "عمولة البيع + بدالت"): "عمولة البيع +بدلات السفر والاكراميات",
    ("selling", "عربية الفاسير 1842"): "عربية الفاستر 1842",
    # May prints the vehicle number on the next page, so the row reads without
    # it. Same vehicle, same month sequence.
    ("selling", "عربية الفاسير"): "عربية الفاستر 1842",
    ("selling", "زيت + فالتر للعربيات"): "زيت + فلاتر للعربيات",
    ("selling", "مواصالت السوان"): "مواصلات اسوان",

    # --- financing ---------------------------------------------------------
    # Every month writes the same two loans with a different date phrase glued
    # to the name.
    ("financing", "مصاريف قرض المبادرة من شهر 1"): "مصاريف قرض المبادرة",
    ("financing", "مصاريف قرض المبادرة من شهر 1 اىل شهر 3"):
        "مصاريف قرض المبادرة",
    ("financing", "مصاريف قرض المبادرة شهر 4."): "مصاريف قرض المبادرة",
    ("financing", "مصاريف قرض المبادرة شهر 5"): "مصاريف قرض المبادرة",
    ("financing", "مصاريف قرض المبادرة من"): "مصاريف قرض المبادرة",
    ("financing", "مصاريق قرض السيارة من شهر 1 اىل 3"):
        "مصاريف قرض السيارة والحساب",
    ("financing", "مصاريق قرض السيارة شهر 4"): "مصاريف قرض السيارة والحساب",
    ("financing", "مصاريق قرض السيارة شهر 5"): "مصاريف قرض السيارة والحساب",
    ("financing", "مصاريق قرض السيارة من"): "مصاريف قرض السيارة والحساب",
    ("financing", "تامير عىل المصنع و العربيات"): "تأمين على المصنع والعربيات",
    ("financing", "مصاريف االشهار"): "مصاريف الاشهار",

    # NOT mapped, deliberately:
    #   «كباس تير يد 3782» — the words are mangled past the point of reading;
    #   it appears twice with the same spelling, so it tracks across months on
    #   its own and needs no guess about what it says.
    #   «استيكر» · «كاوتش» · «دعايا» — each appears in one statement only.
}

# Raw labels whose own words say the figure covers more than the month it sits
# in. The amount is the statement's, and is not re-spread: it is shown where it
# was booked, with this note attached, because splitting it across months would
# be an estimate the source does not support.
LUMP_POSTINGS = {
    ("financing", "مصاريف قرض المبادرة من شهر 9 الى شهر 12"):
        "القيمة مقيدة في ديسمبر وتغطي الأشهر 9–12 بنص الملف",
    ("financing", "مصاريق قرض السيارة من شهر 9 الى 12"):
        "القيمة مقيدة في ديسمبر وتغطي الأشهر 9–12 بنص الملف",
    ("financing", "مصاريف قرض المبادرة من شهر 1"):
        "نصّ السطر يقول «من شهر 1» — القيمة مقيدة في يونيو وتغطي ما قبله",
    ("financing", "مصاريق قرض السيارة من شهر 1"):
        "نصّ السطر يقول «من شهر 1» — القيمة مقيدة في يونيو وتغطي ما قبله",
}


def canonical(group, label_raw):
    """The display name for one raw label, within its own group."""
    return ALIASES.get((group, label_raw), label_raw)


def lump_note(group, label_raw):
    """A timing caveat for this raw label, or None."""
    return LUMP_POSTINGS.get((group, label_raw))


def alias_table():
    """Rows for the on-screen table: what was merged, and into what.

    Sorted so the table reads the same on every rebuild.
    """
    return [{"group": g, "label_raw": raw, "label": canon}
            for (g, raw), canon in sorted(ALIASES.items())]
