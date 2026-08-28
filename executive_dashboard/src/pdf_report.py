"""
Executive PDF (Arabic, correctly shaped RTL).

Uses reportlab with the vendored Amiri font, and arabic-reshaper + python-bidi to
render Arabic glyphs in the right joined, right-to-left order (reportlab has no
native RTL engine).

Page 2 is profitability, and appears only when
data/processed/margin_summary.json exists — it is written by
analysis/13_join_cost_margin.py, which is not part of this app's pipeline. When
it is absent the report is the one-pager it always was, so this module never
depends on a step that may not have run.
"""
from __future__ import annotations

import json

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, PageBreak, Spacer,
                                Table, TableStyle)
from reportlab.lib.styles import ParagraphStyle

from . import config as C

_INK = colors.HexColor("#0b1220")
_ACCENT = colors.HexColor("#c9a227")
_MUTED = colors.HexColor("#5b6472")
_PANEL = colors.HexColor("#f4f1e9")
_GOOD = colors.HexColor("#1b7f5a")
_WARN = colors.HexColor("#a8730a")

MARGIN_SUMMARY = C.REPO_ROOT / "data" / "processed" / "margin_summary.json"


def _margin():
    """The profitability payload, or None if the join has not been run."""
    if not MARGIN_SUMMARY.exists():
        return None
    try:
        return json.loads(MARGIN_SUMMARY.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _pct(x):
    return "—" if x is None else f"{x:.1f}%"


def _ar(txt: str) -> str:
    """Reshape and bidi-order a SHORT run that will not wrap.

    Only safe for text that fits on one line. See _ar_block for anything longer.
    """
    return get_display(arabic_reshaper.reshape(str(txt)))


# A4 minus the 16mm margins is 178mm. Wrapping is measured a little narrower so
# a line that lands exactly on the limit is not re-wrapped by reportlab, which
# would push a word onto its own line in the wrong place — the text is already
# bidi-ordered by then, so the stray word lands nowhere sensible.
_WRAP_MM = 172.0


def _ar_block(txt: str, width_mm: float = _WRAP_MM,
              font: str = "Amiri", size: float = 10) -> str:
    """Reshape and bidi-order a paragraph that WILL wrap.

    get_display reorders a whole string for visual display. Handing reportlab a
    multi-line RTL run and letting it wrap puts the resulting lines in reverse
    vertical order — the last sentence prints first — because the reordering has
    already happened across what become separate lines.

    So wrap first and reorder per line: reshape once (joining is decided within
    a word, never across a space), measure with the real font to break lines,
    then bidi each finished line on its own and join with explicit breaks.
    """
    shaped = arabic_reshaper.reshape(str(txt))
    limit = width_mm * mm
    lines, cur = [], ""
    for word in shaped.split(" "):
        trial = word if not cur else cur + " " + word
        if pdfmetrics.stringWidth(trial, font, size) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return "<br/>".join(get_display(ln) for ln in lines)


def _egp(x: float) -> str:
    return f"{x:,.0f}"


def build(kpis, customers, products, receivables, insights, path=C.OUT_PDF):
    pdfmetrics.registerFont(TTFont("Amiri", str(C.FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("Amiri-Bold", str(C.FONT_BOLD)))

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
    )
    title = ParagraphStyle("t", fontName="Amiri-Bold", fontSize=20, alignment=2,
                           textColor=_INK, leading=26)
    sub = ParagraphStyle("s", fontName="Amiri", fontSize=11, alignment=2,
                         textColor=_MUTED, leading=16)
    h2 = ParagraphStyle("h2", fontName="Amiri-Bold", fontSize=13, alignment=2,
                        textColor=_ACCENT, leading=18, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", fontName="Amiri", fontSize=10, alignment=2,
                          textColor=_INK, leading=16)

    mg = _margin()

    story = []
    story.append(Paragraph(_ar("أبو هاشم للحوم — الملخص التنفيذي المالي"), title))
    story.append(Paragraph(_ar(f"لوحة الأداء التنفيذي · {C.PERIOD_LABEL_AR} · لقطة مديونية {C.AS_OF_DATE}"), sub))
    story.append(Spacer(1, 8 * mm))

    # KPI grid (3 columns x N rows), each cell = value over label
    kpi_cells = [
        ("إجمالي المبيعات", _egp(kpis["total_sales"]) + " ج.م"),
        ("عدد الفواتير", _egp(kpis["n_invoices"])),
        ("عدد العملاء", _egp(kpis["n_customers"])),
        ("المديونية القائمة", _egp(kpis["outstanding"]) + " ج.م"),
        ("المتأخرات (تقديري)", _egp(kpis["overdue"]) + " ج.م"),
        ("معدل التحصيل", f"{kpis['collection_rate'] * 100:.1f}%"),
        ("متوسط سعر البيع/وحدة", _egp(kpis["asp"]) + " ج.م"),
        ("إجمالي الكمية", _egp(kpis["total_qty"])),
        ("إجمالي الكراتين", _egp(kpis["total_boxes"])),
        ("متوسط قيمة الفاتورة", _egp(kpis["avg_invoice_value"]) + " ج.م"),
        ("فواتير صفرية", _egp(kpis["zero_invoices"])),
        # Margin used to be hardcoded "غير متاح" here, which was true until the
        # June-2026 costing model was joined in. Still honest when the join has
        # not been run.
        ("هامش مجمل (يونيو 2026)",
         _pct((mg["measured"]["gross_margin_pct"]) if mg else None)
         if mg else "غير متاح"),
    ]
    data = []
    row = []
    for label, value in kpi_cells:
        cell = Paragraph(
            f'<font name="Amiri-Bold" size="13">{_ar(value)}</font><br/>'
            f'<font name="Amiri" size="8" color="#5b6472">{_ar(label)}</font>',
            ParagraphStyle("c", alignment=1, leading=15),
        )
        row.append(cell)
        if len(row) == 3:
            data.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        data.append(row)

    t = Table(data, colWidths=[57 * mm] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9d2c2")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9d2c2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)

    # Top insights
    story.append(Paragraph(_ar("أبرز الرؤى والتوصيات"), h2))
    for key in ["overview", "aging", "top_customers", "receivables_rep"]:
        ins = insights.get(key)
        if not ins:
            continue
        story.append(Paragraph(
            f'<font name="Amiri-Bold">{_ar(ins["title"])}</font> '
            f'<font color="#c9a227">[{_ar("أولوية " + ins["priority"])}]</font>', body))
        story.append(Paragraph(_ar("• " + ins["what"]), body))
        story.append(Paragraph(_ar("• التوصية: " + ins["action"]), body))
        story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_ar_block(
        ("قيود المصدر: لا توجد موازنة، ولا تواريخ استحقاق على الفواتير (أعمار "
         "الديون تقديرية مبنية على لقطة المديونية). التكلفة مقيسة شهريًا على "
         "مستوى الشركة، ولشهر واحد فقط على مستوى الصنف — تفاصيلها في الصفحة "
         "التالية. كل رقم قابل للتتبع حتى الملف المصدري.")
        if mg else
        ("قيود المصدر: لا توجد بيانات تكلفة (لا هامش ربح)، ولا موازنة، ولا تواريخ "
         "استحقاق على الفواتير (أعمار الديون تقديرية مبنية على لقطة المديونية). "
         "كل رقم قابل للتتبع حتى الملف المصدري."), size=11), sub))

    if mg:
        story.append(PageBreak())
        story.extend(_profitability(mg, title, sub, h2, body))

    doc.build(story)
    return path


def _statements_block(st, h2, body):
    """The measured company-level series, above the June per-item detail.

    Deliberately a compact summary rather than all thirteen rows: this page
    exists to state what is measured and at what scope, and a full monthly
    table belongs in the exported workbook, not in a one-page board summary.
    The allocated months are named anyway — a reader must not carry an
    estimated figure away believing it was measured.
    """
    t, m = st["totals"], st["meta"]
    out = [Paragraph(_ar("المستوى الأول — مقيس على مستوى الشركة"), h2)]

    rows = [[_ar("الفترة"), _ar("صافي المبيعات"), _ar("تكلفة المبيعات"),
             _ar("هامش مجمل"), _ar("هامش صافي")],
            [_ar(f"{t['months']} شهرًا · {t['period_from']} – {t['period_to']}"),
             _egp(t["net_sales"]), _egp(t["cogs"]),
             _pct(t["gross_margin_pct"]), _pct(t["net_margin_pct"])]]
    tbl = Table(rows, colWidths=[52 * mm, 30 * mm, 30 * mm, 23 * mm, 23 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Amiri"),
        ("FONTNAME", (0, 0), (-1, 0), "Amiri-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), _PANEL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d2c2")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 1), (-1, 1), _GOOD),
    ]))
    out.append(tbl)

    note = (f"تكلفة المبيعات مقيسة شهريًا من قوائم الدخل "
            f"({st['meta']['n_observations']} قائمة). ")
    if t.get("n_allocated_months"):
        note += (f"{t['n_allocated_months']} أشهر منها "
                 f"({'، '.join(m['quarter_months'])}) موزّعة تناسبيًا من قائمة "
                 f"{m['quarter_period']} المجمّعة، وهي تقدير: التوزيع يقسم "
                 f"المقادير ولا يخلق تفاوتًا في النسب. ")
    note += ("القوائم على مستوى الشركة ولا تعطي تكلفة لكل صنف، فالتفصيل أدناه "
             "يبقى على شهر التكلفة وحده.")
    out.append(Paragraph(_ar_block(note), body))
    return out


def _profitability(mg, title, sub, h2, body):
    """Page 2 — profitability, with the price-drift caveat attached to the
    figures rather than buried in a footnote."""
    cov, drift = mg["coverage"], mg["price_drift"]
    meas, ind = mg["measured"], mg["indicative"]
    window = ", ".join(drift["reliable_months"])

    st = mg.get("statements")

    out = [
        Paragraph(_ar("الربحية — التكلفة والهامش"), title),
        Paragraph(_ar_block(
            "مستويان مقيسان على نطاقين مختلفين: هامش الشركة من قوائم الدخل، "
            "ثم تفصيل حسب الصنف والعلامة والمندوب من نموذج التكاليف. "
            f"التغطية على مستوى الصنف {cov['coverage_pct']:.1f}% من الإيراد "
            f"({cov['n_items_costed']} صنفًا من {cov['n_items_total']}).",
            size=11) if st else _ar_block(
            f"نموذج تكاليف {mg['cost_month']} مطابق لقائمة الدخل، مربوطًا بفواتير "
            f"المبيعات. التغطية {cov['coverage_pct']:.1f}% من الإيراد "
            f"({cov['n_items_costed']} صنفًا من {cov['n_items_total']}).",
            size=11), sub),
        Spacer(1, 6 * mm),
    ]

    if st:
        out.extend(_statements_block(st, h2, body))
        out.append(Spacer(1, 5 * mm))
        out.append(Paragraph(_ar(
            f"المستوى الثاني — تفصيل شهر {mg['cost_month']}"), h2))

    rows = [[_ar("الأساس"), _ar("الإيراد المُسعَّر"), _ar("هامش مجمل"),
             _ar("هامش تشغيلي"), _ar("الشهور")]]
    rows.append([_ar("مقيس"), _egp(meas["revenue_costed"]),
                 _pct(meas["gross_margin_pct"]), _pct(meas["op_margin_pct"]),
                 _ar(mg["cost_month"])])
    rows.append([_ar("تقديري (ضمن النافذة)"), _egp(ind["revenue_costed"]),
                 _pct(ind["gross_margin_pct"]), _pct(ind["op_margin_pct"]),
                 _ar(str(len(ind["months"])) + " شهور")])
    exc = mg.get("indicative_excluded")
    if exc:
        rows.append([_ar("مستبعد — غير قابل للمقارنة"), _egp(exc["revenue_costed"]),
                     _pct(exc["gross_margin_pct"]), _pct(exc["op_margin_pct"]),
                     _ar(str(len(exc["months"])) + " شهرًا")])

    t = Table(rows, colWidths=[46 * mm, 33 * mm, 26 * mm, 28 * mm, 25 * mm])
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Amiri"),
        ("FONTNAME", (0, 0), (-1, 0), "Amiri-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), _PANEL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d2c2")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 1), (-1, 1), _GOOD),
    ]
    if exc:
        # The excluded row is not a result; colour it as the warning it is.
        style.append(("TEXTCOLOR", (0, 3), (-1, 3), _WARN))
    t.setStyle(TableStyle(style))
    out.append(t)

    out.append(Paragraph(_ar("لماذا استُبعدت شهور"), h2))
    out.append(Paragraph(_ar_block(
        f"التكلفة لكل صنف مقيسة لشهر {mg['cost_month']} وحده. مؤشر أسعار بسلّة "
        f"ثابتة يبيّن "
        f"أن الأسعار كانت أدنى من شهر التكلفة بنحو 15% حتى فبراير 2026 ثم ارتفعت "
        f"في مارس–أبريل 2026. احتساب تكلفة يونيو على أسعار ما قبل الزيادة يُنتج "
        f"هامشًا تشغيليًا سالبًا طوال 2025، وهو أثر منهجي لا خسارة فعلية. لذلك "
        f"تُستبعد الشهور التي يتجاوز انحراف أسعارها "
        f"{drift['max_drift_pct']:.0f}%، وتبقى النافذة الموثوقة: {window}."), body))

    out.append(Paragraph(_ar("إيراد بلا بيانات تكلفة"), h2))
    out.append(Paragraph(_ar_block(
        f"{_egp(cov['revenue_uncosted'])} ج.م من الإيراد "
        f"({100 - cov['coverage_pct']:.1f}%) لا تُقابله بيانات تكلفة. لا تُحتسب "
        f"له تكلفة صفرية — كل نسبة هامش أعلاه محسوبة على الإيراد المُسعَّر وحده، "
        f"وإلا لظهر الهامش أعلى من حقيقته."), body))

    top = cov.get("uncosted_items_top") or []
    if top:
        rows2 = [[_ar("الصنف"), _ar("الإيراد")]]
        for r in top[:8]:
            rows2.append([_ar(str(r["item_name"])[:44]), _egp(r["revenue"])])
        t2 = Table(rows2, colWidths=[110 * mm, 48 * mm])
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Amiri"),
            ("FONTNAME", (0, 0), (-1, 0), "Amiri-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), _PANEL),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d2c2")),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]))
        out.append(Spacer(1, 3 * mm))
        out.append(t2)

    src = mg["cost_source"]
    out.append(Spacer(1, 5 * mm))
    # Both levels come from the same repository but from different documents,
    # and a reader tracing a figure needs to know which one it came from.
    line = f"مصدر التكلفة: {src['repo']} · {src['path']}"
    if st:
        line += f" · قوائم الدخل (الالتزام {st['meta']['source_commit'][:7]})"
    out.append(Paragraph(_ar(f"{line} — انظر {src['see']}."), sub))
    return out
