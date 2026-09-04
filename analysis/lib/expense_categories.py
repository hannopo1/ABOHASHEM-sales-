"""The four expense categories, and which line belongs to which.

The categories are not ours. From May 2026 the income statements print four
expense groups themselves — تشغيلية · إدارية وعمومية · بيعية وتسويقية · تمويلية —
and those three months need no interpretation at all: every line is read where
the accountant put it.

The earlier statements print THREE groups. Their selling and financing groups
are the same two categories under the same names, so they carry over untouched.
The difference is one group: what those statements call «إدارية وعمومية» is, in
the later statements, split into an operating group and a smaller administrative
one. Rent in May 2026 is 66,600 operating plus 8,000 administrative; in April it
is a single administrative line of 73,100.

So this file decides ONE thing: for a line filed under that combined
administrative group, which of the two categories it belongs to. Every decision
is made on the accountant's own later placement of the same item — nothing is
inferred from what a name sounds like — and each line records how it was
decided, so a reader can always tell a measurement from a reading.

FOUR BASES, AND WHAT EACH ONE PROMISES

  stated    The statement itself declared this category. May–July 2026, and
            every selling and financing line in every statement.
  mapped    The four-category statements place this same name in exactly one of
            operating / administrative, so the earlier line is carried there.
  unsplit   They place it in BOTH. One earlier line covers two categories and
            the statement never divided it, so it stays where it was filed and
            says so. Splitting it by proportion would be an estimate, and this
            file does not make estimates.
  as_filed  The four-category statements never show this name — mostly one-off
            administrative lines from 2025. Nothing to move it on, so it stays
            where its own statement put it.

The lists below are checked against the data, not merely asserted: a test in
analysis/tests/test_expense_items.py recomputes them from the four-category
statements and fails if this file and the source disagree.

Standard library only.
"""

CATEGORIES = ["operating", "admin", "selling", "financing"]

CATEGORY_LABELS = {
    "operating": "مصروفات تشغيلية",
    "admin": "مصروفات إدارية وعمومية",
    "selling": "مصروفات بيعية وتسويقية",
    "financing": "مصروفات بنكية وتمويلية",
}

# The statements that print all four groups. Everything read from them is
# `stated`; everything below exists only to read the earlier ones.
FOUR_WAY_PERIODS = ["2026-05", "2026-06", "2026-07"]

# Filed under the combined administrative group, and shown by the later
# statements to belong to the operating one. Each of these appears in the
# operating group of May–July 2026 and in no administrative group there.
MOVED_TO_OPERATING = [
    "تصنيع لدى الغير",          # sub-contract manufacturing — production cost
    "عمالة خارجية",             # outside labour
    "صيانات وقطع غيار",         # maintenance and spare parts
    "بدلات ومكافئات",           # allowances and bonuses
    "منظفات ومكافحة",           # cleaning and pest control
    "أخرى",                     # the operating group's own "other" line
    "غفرة رمضان",
]

# Two names deliberately absent from the list above: «فواتير الكهرباء» and
# «مرتبات انتاج والمصنع». Both exist only in the four-category statements — the
# earlier ones carry «فواتير كهرباء ونت» and a single administrative «مرتبات»
# instead — so neither is ever filed under the combined group and neither needs
# deciding. A decision that never applies is one nobody can check, and the test
# suite rejects it.

# Filed under the combined group and shown to stay there: the later statements
# keep these in the administrative group.
KEPT_IN_ADMIN = [
    "مرتبات",                   # the office payroll — production has its own
    "فواتير كهرباء ونت",        # the office electricity-and-internet bill
    "محامى",
    "مكتب المحاسبة",
    "تامينات",
    "مصاريف المكتب",
    "ضيافات وكافيهات",
    "هدايا ورشاوى",
]

# One name, two categories in the later statements. The earlier statements file
# it once, and that single figure covers both — 66,600 operating against 8,000
# administrative in May 2026, against one line of 73,100 in April. It is left
# where it was filed and flagged, because the only ways to divide it are to
# invent a ratio or to move the whole of it into a category most of it does not
# belong to.
UNSPLIT = [
    "ايجارات",
]

# Names the four-category statements never carry, so nothing can move them.
# They stay in the group their own statement declared.
AS_FILED = [
    "صحة وتموين", "شقة العاملين", "مياه شقة العاملين", "غرامات اخر قضية",
    "باركوود منتجات", "اعمال الخير", "ديون اعدمت", "حكومية", "دفاترمبيعات",
    "استيكر", "بوفيه", "فهمى",
]

_LOOKUP = ({n: ("operating", "mapped") for n in MOVED_TO_OPERATING}
           | {n: ("admin", "mapped") for n in KEPT_IN_ADMIN}
           | {n: ("admin", "unsplit") for n in UNSPLIT}
           | {n: ("admin", "as_filed") for n in AS_FILED})


class UnknownExpenseItem(KeyError):
    """A line under the combined administrative group with no decision here."""


def classify(group, label, four_way):
    """(category, basis) for one line item.

    `group` is the group its own statement filed it under, `label` its
    canonical name, and `four_way` whether that statement printed all four
    groups. Raises rather than guessing: a new administrative line must be
    decided by a person, not dropped into a default bucket where it would sit
    unnoticed in someone's board pack.
    """
    if four_way or group != "admin":
        return group, "stated"
    try:
        return _LOOKUP[label]
    except KeyError:
        raise UnknownExpenseItem(
            f"«{label}» is filed under the combined administrative group and "
            f"has no line in analysis/lib/expense_categories.py. Decide whether "
            f"it is operating or administrative — there is no default.") from None


def decision_table():
    """Rows for the screen: what was moved, what was not, and on what basis."""
    return [{"label": label, "category": cat, "basis": basis}
            for label, (cat, basis) in sorted(_LOOKUP.items())]
