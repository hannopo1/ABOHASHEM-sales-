"""Ordering invariants that keep a rebuild's diff reviewable.

Two places used to iterate a set and emit the result straight into data.js.
Python randomises string hashing per process, so identical inputs produced
differently-ordered output on every run: the numbers matched, the diff did not,
and a rebuild pull request was unreadable.

These read the committed data.js and assert the orderings are total, so the
regression is caught without re-running the build in CI. Standard library only,
like the rest of this suite.
"""
import json
from pathlib import Path

import pytest

DATA_JS = Path(__file__).resolve().parents[1] / "data.js"

pytestmark = pytest.mark.skipif(not DATA_JS.exists(),
                                reason="data.js absent — run build.py")


@pytest.fixture(scope="module")
def dash():
    """
    Load and parse the JSON payload from the committed data file.
    
    Returns:
        dict: The parsed data object.
    """
    txt = DATA_JS.read_text(encoding="utf-8")
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1].replace("<\\/", "</"))


def test_collections_by_customer_has_a_total_order(dash):
    """Sorted by amount descending, ties broken by code — never by set order."""
    rows = dash["collections"]["by_customer"]
    keys = [(-r["collected"], r["customer_code"]) for r in rows]
    assert keys == sorted(keys), "by_customer is not in a deterministic order"


def test_customer_ar_keys_are_sorted(dash):
    codes = list(dash["customer_ar"].keys())
    assert codes == sorted(codes), "customer_ar key order depends on set iteration"


def test_no_duplicate_customers_in_collections(dash):
    """
    Verify that each customer appears at most once in the customer collections.
    """
    codes = [r["customer_code"] for r in dash["collections"]["by_customer"]]
    assert len(codes) == len(set(codes))
