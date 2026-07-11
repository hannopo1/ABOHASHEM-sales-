"""
Executive one-pager PDF (Arabic, correctly shaped RTL).

Uses reportlab with the vendored Amiri font, and arabic-reshaper + python-bidi to
render Arabic glyphs in the right joined, right-to-left order (reportlab has no
native RTL engine).
"""
from __future__ import annotations

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.lib.styles import ParagraphStyle

from . import config as C

_INK = colors.HexColor("#0b1220")
_ACCENT = colors.HexColor("#c9a227")
_MUTED = colors.HexColor("#5b6472")
_PANEL = colors.HexColor("#f4f1e9")


def _ar(txt: str) -> str:
    return get_display(arabic_reshaper.reshape(str(txt)))


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
        ("هامش الربح", "غير متاح"),
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
            data.append(row); row = []
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
    story.append(Paragraph(_ar(
        "قيود المصدر: لا توجد بيانات تكلفة (لا هامش ربح)، ولا موازنة، ولا تواريخ "
        "استحقاق على الفواتير (أعمار الديون تقديرية مبنية على لقطة المديونية). "
        "كل رقم قابل للتتبع حتى الملف المصدري."), sub))

    doc.build(story)
    return path
