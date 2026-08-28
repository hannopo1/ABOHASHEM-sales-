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
    """Load the profitability summary from the configured JSON file.
    
    Returns:
    	dict: The parsed profitability data, or `None` if the file is missing, unreadable, or contains invalid JSON.
    """
    if not MARGIN_SUMMARY.exists():
        return None
    try:
        return json.loads(MARGIN_SUMMARY.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _pct(x):
    """Format a percentage value to one decimal place, using an em dash when no value is available.
    
    Parameters:
    	x: The percentage value to format.
    
    Returns:
    	str: The formatted percentage or an em dash."""
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
    """
              Format an Arabic paragraph for right-to-left display with measured line wrapping.
              
              Parameters:
                  txt (str): Arabic text to format.
                  width_mm (float): Maximum line width in millimeters.
                  font (str): Font used to measure the text.
                  size (float): Font size used to measure the text.
              
              Returns:
                  str: Bidi-ordered text with explicit line breaks.
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
    """Format an Egyptian pound amount with comma separators and no decimal places.
    
    Parameters:
    	x (float): The amount to format.
    
    Returns:
    	str: The formatted amount.
    """
    return f"{x:,.0f}"


def build(kpis, customers, products, receivables, insights, path=C.OUT_PDF):
    """
    Build the executive financial report PDF.
    
    Parameters:
    	kpis (dict): Key performance indicators used in the report.
    	customers (dict): Customer data used to generate the report.
    	products (dict): Product data used to generate the report.
    	receivables (dict): Receivables data used to generate the report.
    	insights (dict): Overview, aging, customer, and receivables findings and recommendations.
    	path (str or pathlib.Path): Destination path for the generated PDF.
    
    Returns:
    	str or pathlib.Path: The path of the generated PDF.
    """
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
         "الديون تقديرية مبنية على لقطة المديونية). بيانات التكلفة متاحة لشهر "
         "يونيو 2026 فقط — تفاصيلها في الصفحة التالية. كل رقم قابل للتتبع حتى "
         "الملف المصدري.")
        if mg else
        ("قيود المصدر: لا توجد بيانات تكلفة (لا هامش ربح)، ولا موازنة، ولا تواريخ "
         "استحقاق على الفواتير (أعمار الديون تقديرية مبنية على لقطة المديونية). "
         "كل رقم قابل للتتبع حتى الملف المصدري."), size=11), sub))

    if mg:
        story.append(PageBreak())
        story.extend(_profitability(mg, title, sub, h2, body))

    doc.build(story)
    return path


def _profitability(mg, title, sub, h2, body):
    """
    Build the profitability section of the report.
    
    Parameters:
        mg (dict): Profitability data containing coverage, price-drift, measured,
            indicative, and cost-source details.
        title: Paragraph style for the section title.
        sub: Paragraph style for subtitles and source references.
        h2: Paragraph style for subsection headings.
        body: Paragraph style for explanatory text.
    
    Returns:
        list: ReportLab flowables for the profitability page.
    """
    cov, drift = mg["coverage"], mg["price_drift"]
    meas, ind = mg["measured"], mg["indicative"]
    window = ", ".join(drift["reliable_months"])

    out = [
        Paragraph(_ar("الربحية — التكلفة والهامش"), title),
        Paragraph(_ar_block(
            f"نموذج تكاليف {mg['cost_month']} مطابق لقائمة الدخل، مربوطًا بفواتير "
            f"المبيعات. التغطية {cov['coverage_pct']:.1f}% من الإيراد "
            f"({cov['n_items_costed']} صنفًا من {cov['n_items_total']}).",
            size=11), sub),
        Spacer(1, 6 * mm),
    ]

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
        f"التكلفة مقيسة لشهر {mg['cost_month']} فقط. مؤشر أسعار بسلّة ثابتة يبيّن "
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
    out.append(Paragraph(_ar(
        f"مصدر التكلفة: {src['repo']} · {src['path']} — انظر {src['see']}."), sub))
    return out
