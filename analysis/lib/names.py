"""Picking one display label per key, when the sources disagree or say nothing.

The same idiom appeared in four pipeline steps:

    df.groupby(key)[label].agg(lambda s: s.value_counts().index[0])

which is "the most common label for this key" — and which raises IndexError the
moment every row for one key has a blank label, because ``value_counts`` drops
those and leaves an empty index. That is not a hypothetical: customer code 009
invoices under a blank name on all five of its PDF invoices, and adding the July
and August PDFs to the dataset crashed two separate steps on it.

``best`` returns None instead of raising, so the caller decides what a missing
label means. Callers that display the value should label it honestly — the
convention in this repo is «عميل <code>» / «صنف <code>», never a fabricated name
and never a bare number.
"""
from __future__ import annotations


def best(series):
    """Most frequent non-blank value in ``series``; None when there is none."""
    s = series.dropna().astype(str).str.strip()
    counts = s[s != ""].value_counts()
    return counts.index[0] if len(counts) else None


def best_or(series, fallback):
    """``best``, with an explicit fallback for the no-label-anywhere case."""
    picked = best(series)
    return fallback if picked is None else picked
