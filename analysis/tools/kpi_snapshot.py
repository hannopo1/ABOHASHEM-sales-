#!/usr/bin/env python3
"""Capture the headline numbers, and diff two captures into Markdown.

Used by the rebuild workflow so a pull request opened after new source files
land says what those files did to the figures, instead of showing a wall of
regenerated CSV and a 11 MB HTML blob and leaving the reviewer to guess.

    python3 analysis/tools/kpi_snapshot.py capture before.json
    ... regenerate ...
    python3 analysis/tools/kpi_snapshot.py capture after.json
    python3 analysis/tools/kpi_snapshot.py diff before.json after.json > body.md

Standard library only: it has to run before the pipeline's dependencies are
necessarily installed, and it must never be the reason a rebuild fails. Missing
inputs are recorded as missing rather than raised.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data" / "processed"

# label -> (file, dotted path). A path segment that is an integer indexes a list.
METRICS = {
    "الإيراد الإجمالي": (P / "eda_summary.json", "total_revenue", "egp"),
    "عدد العملاء": (P / "eda_summary.json", "n_customers", "int"),
    "عدد الأصناف": (P / "eda_summary.json", "n_items", "int"),
    "عدد الشهور": (P / "eda_summary.json", "n_months", "int"),
    "عدد البنود": (P / "data_quality_metrics.json", "n_rows", "int"),
    "عدد الفواتير": (P / "data_quality_metrics.json", "n_invoices", "int"),
    "تغطية التكلفة %": (P / "margin_summary.json", "coverage.coverage_pct", "pct"),
    "إيراد غير مُسعَّر": (P / "margin_summary.json", "coverage.revenue_uncosted", "egp"),
    "هامش مجمل — مقيس %": (P / "margin_summary.json", "measured.gross_margin_pct", "pct"),
    "هامش تشغيلي — مقيس %": (P / "margin_summary.json", "measured.op_margin_pct", "pct"),
    "هامش مجمل — تقديري %": (P / "margin_summary.json", "indicative.gross_margin_pct", "pct"),
    "هامش تشغيلي — تقديري %": (P / "margin_summary.json", "indicative.op_margin_pct", "pct"),
    "شهور ضمن النافذة": (P / "margin_summary.json", "price_drift.reliable_months", "count"),
}

DASH_JS = ROOT / "executive_dashboard" / "data.js"
DASH_METRICS = {
    "المديونية القائمة": ("receivables.total_outstanding", "egp"),
    "المتأخرات": ("receivables.total_overdue", "egp"),
    "إجمالي التحصيل": ("collections.grand_total_collected", "egp"),
    "إجمالي المرتجعات": ("collections.grand_total_returns", "egp"),
}


def dig(obj, path: str):
    """
    Traverse a nested object using a dotted path.
    
    Parameters:
    	obj: The dictionary or list to traverse.
    	path (str): A dot-separated path containing dictionary keys and list indexes.
    
    Returns:
    	The value at the specified path, or `None` when the path is invalid or unavailable.
    """
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def load_json(path: Path):
    """
    Load and parse a UTF-8 JSON file.
    
    Parameters:
        path (Path): Path to the JSON file.
    
    Returns:
        object: The parsed JSON value, or `None` if the file cannot be read or parsed.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_dash():
    """
    Load the dashboard data embedded in the JavaScript source file.
    
    Returns:
    	dict: The parsed dashboard data, or `None` if the file cannot be read or parsed.
    """
    try:
        txt = DASH_JS.read_text(encoding="utf-8")
        return json.loads(txt[txt.index("{"):txt.rindex("}") + 1].replace("<\\/", "</"))
    except (OSError, ValueError):
        return None


def capture() -> dict:
    """
    Collect configured KPI values from source JSON files and dashboard data.
    
    Returns:
    	dict: A label-keyed mapping containing each metric's value and formatting kind. Missing or invalid values are represented as `None`.
    """
    out, cache = {}, {}
    for label, (path, dotted, kind) in METRICS.items():
        if path not in cache:
            cache[path] = load_json(path)
        val = dig(cache[path], dotted)
        if kind == "count":
            val = len(val) if isinstance(val, list) else None
        out[label] = {"value": val, "kind": kind}
    dash = load_dash()
    for label, (dotted, kind) in DASH_METRICS.items():
        out[label] = {"value": dig(dash, dotted), "kind": kind}
    return out


def fmt(value, kind: str) -> str:
    """
    Format a metric value according to its display kind.
    
    Parameters:
        value: The metric value to format.
        kind (str): The display format, such as currency or percentage.
    
    Returns:
        str: The formatted value, or "—" when the value is unavailable.
    """
    if value is None:
        return "—"
    if kind == "egp":
        return f"{value:,.0f}"
    if kind == "pct":
        return f"{value:.2f}%"
    return f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)


def delta(before, after, kind: str) -> str:
    """
    Describe the change between two metric values.
    
    Parameters:
        before: The earlier metric value.
        after: The later metric value.
        kind (str): The metric formatting kind used to represent numeric differences.
    
    Returns:
        str: A localized description of the change, including numeric and percentage differences when applicable.
    """
    if before is None and after is None:
        return "—"
    if before is None:
        return "جديد"
    if after is None:
        return "**اختفى**"
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return "—" if before == after else "تغيّر"
    d = after - before
    if abs(d) < 1e-9:
        return "بلا تغيير"
    sign = "+" if d > 0 else "−"
    body = f"{sign}{abs(d):,.2f}" if kind == "pct" else f"{sign}{abs(d):,.0f}"
    if before:
        body += f"  ({sign}{abs(d) / abs(before) * 100:.1f}%)"
    return body


def diff(a: dict, b: dict) -> str:
    """
    Build an Arabic Markdown comparison table for two KPI snapshots.
    
    Parameters:
    	a (dict): The earlier KPI snapshot.
    	b (dict): The later KPI snapshot.
    
    Returns:
    	str: A Markdown table containing each metric's earlier value, later value, and difference, followed by a change summary.
    """
    lines = ["### أثر البيانات الجديدة على الأرقام", "",
             "| المؤشر | قبل | بعد | الفرق |", "|---|---:|---:|---:|"]
    changed = 0
    for label in b:
        kind = b[label].get("kind", "int")
        before = (a.get(label) or {}).get("value")
        after = b[label].get("value")
        d = delta(before, after, kind)
        if d not in ("بلا تغيير", "—"):
            changed += 1
        lines.append(f"| {label} | {fmt(before, kind)} | {fmt(after, kind)} | {d} |")
    lines += ["", f"**{changed}** مؤشرًا تغيّر من أصل **{len(b)}**.", ""]
    if not changed:
        lines.append("لم تتغيّر أي أرقام — إعادة البناء متطابقة مع المُودَع.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """
    Handle command-line requests to capture KPI data or compare two snapshots.
    
    Parameters:
    	argv (list[str]): Command-line arguments containing a `capture` or `diff` command and its file paths.
    
    Returns:
    		int: `0` for a successful command, `2` for invalid arguments.
    """
    if len(argv) == 3 and argv[1] == "capture":
        Path(argv[2]).write_text(
            json.dumps(capture(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"captured {len(capture())} metrics -> {argv[2]}")
        return 0
    if len(argv) == 4 and argv[1] == "diff":
        a = load_json(Path(argv[2])) or {}
        b = load_json(Path(argv[3])) or {}
        print(diff(a, b))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
