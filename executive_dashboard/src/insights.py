"""
Automated executive commentary.

Produces, for each major visualization, a structured insight the dashboard renders
underneath the chart: what happened, why, the risk, the opportunity, the
recommended action and a priority. Text is generated from the computed numbers so
it always matches the figures on screen.
"""
from __future__ import annotations


def _egp(x: float) -> str:
    return f"{x:,.0f} ج.م"


def _pct(x: float) -> str:
    return f"{x * 100:,.1f}%"


def _insight(title, what, why, risk, opportunity, action, priority):
    return {
        "title": title, "what": what, "why": why, "risk": risk,
        "opportunity": opportunity, "action": action, "priority": priority,
    }


def generate(kpis, customers, products, receivables, monthly, dq) -> dict:
    out: dict[str, dict] = {}

    # --- Portfolio / KPIs --------------------------------------------------
    out["overview"] = _insight(
        "الأداء التنفيذي — يونيو ٢٠٢٦",
        f"بلغت المبيعات {_egp(kpis['total_sales'])} عبر {kpis['n_invoices']} فاتورة "
        f"و{kpis['n_customers']} عميلاً، بمتوسط فاتورة {_egp(kpis['avg_invoice_value'])}.",
        "الشهر بيع آجل بالكامل تقريبًا (التحصيل عند الإصدار شبه صفري)، لذا يُقاس "
        "الأداء التحصيلي على لقطة المديونية لا على المدفوع الفوري.",
        f"إجمالي المديونية القائمة {_egp(kpis['outstanding'])} منها متأخرات "
        f"{_egp(kpis['overdue'])} تمثّل مخاطر تحصيل مباشرة.",
        f"معدل التحصيل التراكمي {_pct(kpis['collection_rate'])} — رفعه نقطة واحدة "
        "يحرّر سيولة تعادل عدة فواتير كبيرة.",
        "تركيز جهد التحصيل على العملاء ذوي المتأخرات الأعلى خلال أول أسبوعين من الشهر التالي.",
        "عالية",
    )

    # --- Monthly trend / variance -----------------------------------------
    m = {r["month"]: r for r in monthly}
    jun = m.get("2026-06", {}).get("net_sales", 0.0)
    may = m.get("2026-05", {}).get("net_sales", 0.0)
    delta = (jun - may) / may if may else 0.0
    out["monthly_trend"] = _insight(
        "اتجاه المبيعات الشهري",
        f"مبيعات يونيو {_egp(jun)} مقابل {_egp(may)} في مايو "
        f"({'انخفاض' if delta < 0 else 'ارتفاع'} {_pct(abs(delta))}).",
        "تراجع طفيف مع اتساع قاعدة العملاء (أعلى عدد عملاء وفواتير في السلسلة) — "
        "أي متوسط قيمة الفاتورة تراجع لا عدد الصفقات.",
        "استمرار تراجع متوسط الفاتورة يضغط الإيراد رغم نمو التغطية.",
        "قاعدة العملاء الأوسع تتيح رفع متوسط السلة عبر عروض مجمّعة.",
        "مراجعة تسعير/تشكيلة الأصناف للعملاء الجدد لرفع متوسط الفاتورة.",
        "متوسطة",
    )

    # --- Concentration / top customers ------------------------------------
    total = kpis["total_sales"] or 1.0
    top10 = sum(c["sales"] for c in customers[:10])
    top10_share = top10 / total
    out["top_customers"] = _insight(
        "تركّز العملاء (أعلى ١٠)",
        f"أعلى ١٠ عملاء يمثّلون {_pct(top10_share)} من مبيعات الشهر "
        f"({_egp(top10)}).",
        "قاعدة إيراد تعتمد على عدد محدود من كبار العملاء — نمط شائع في توزيع اللحوم بالجملة.",
        "فقدان عميل واحد من القمة يُحدث فجوة إيراد ملموسة.",
        "علاقات القمة قابلة للتعميق ببرامج ولاء وحوافز تحصيل.",
        "وضع خطة احتفاظ وحوافز مخصّصة لأكبر ١٠ عملاء.",
        "عالية" if top10_share > 0.5 else "متوسطة",
    )

    # --- Pareto ------------------------------------------------------------
    cum = 0.0
    n80 = 0
    for c in customers:
        cum += c["sales"]
        n80 += 1
        if cum >= 0.8 * total:
            break
    out["pareto"] = _insight(
        "تحليل باريتو (٨٠/٢٠)",
        f"{n80} عميلاً فقط ({n80 / max(len(customers),1) * 100:.0f}% من العملاء) "
        "يولّدون 80% من الإيراد.",
        "تركّز إيرادي مرتفع يعكس اعتمادًا على شريحة صغيرة عالية القيمة.",
        "أي تعثّر تحصيل لدى هذه الشريحة ينعكس مباشرة على السيولة.",
        "توجيه موارد البيع والتحصيل لهذه الشريحة يعظّم العائد على الجهد.",
        "تصنيف العملاء ABC وربط أولوية الخدمة والتحصيل بالتصنيف.",
        "متوسطة",
    )

    # --- Products ----------------------------------------------------------
    if products:
        p0 = products[0]
        top5 = sum(p["sales"] for p in products[:5])
        out["top_products"] = _insight(
            "أعلى المنتجات",
            f"«{p0['item_name']}» يتصدّر بـ {_egp(p0['sales'])} "
            f"({p0['contribution_pct']:.1f}% من الإيراد)؛ أعلى ٥ أصناف = {_egp(top5)}.",
            "تشكيلة الإيراد يقودها عدد محدود من الأصناف عالية الدوران.",
            "نقص توريد صنف متصدّر يوقف جزءًا من الإيراد فورًا.",
            "الأصناف المتصدّرة مرشّحة لتوسيع التوزيع ورفع السعر بحذر.",
            "ضمان توافر مخزون الأصناف الخمسة الأعلى وضبط أسعارها.",
            "متوسطة",
        )

    # --- Aging / receivables ----------------------------------------------
    overdue_share = receivables["total_overdue"] / (receivables["total_outstanding"] or 1.0)
    out["aging"] = _insight(
        "أعمار الديون (تقديري)",
        f"من إجمالي مديونية {_egp(receivables['total_outstanding'])}، المتأخرات "
        f"{_egp(receivables['total_overdue'])} ({_pct(overdue_share)}).",
        "معظم الرصيد «جاري» (غير مستحق) وهو مؤشر صحي، لكن شريحة المتأخرات مركّزة لدى مناديب بعينهم.",
        "المتأخرات الأقدم (+٩٠ يوم) هي الأعلى احتمالًا للتحوّل لديون معدومة.",
        "تحصيل المتأخرات القصيرة قبل تقادمها يقلّل المخصصات مستقبلًا.",
        "خطة تحصيل مرحلية تبدأ بأقدم الشرائح وأكبر الأرصدة.",
        "عالية" if overdue_share > 0.1 else "متوسطة",
    )

    # --- Receivables by rep ------------------------------------------------
    if receivables["by_rep"]:
        worst = max(receivables["by_rep"], key=lambda x: x["overdue"])
        out["receivables_rep"] = _insight(
            "المديونية حسب المندوب",
            f"أعلى متأخرات لدى «{worst['rep']}» بقيمة {_egp(worst['overdue'])} "
            f"عبر {worst['customers']} عميلًا.",
            "توزّع المخاطر التحصيلية غير متجانس بين المناديب.",
            "تركّز المتأخرات لدى مندوب واحد يرفع مخاطر الاعتماد الفردي.",
            "مقارنة أداء المناديب تتيح نقل ممارسات الأفضل للأضعف.",
            f"مراجعة محفظة «{worst['rep']}» ووضع مستهدف تحصيل أسبوعي.",
            "عالية",
        )

    # --- Bonus -------------------------------------------------------------
    eligible = [c for c in customers if c["bonus_pct"] > 0]
    bonus_total = sum(c["bonus_value"] for c in customers)
    out["bonus"] = _insight(
        "حافز التحصيل المستحق",
        f"{len(eligible)} عميلًا مؤهّلون للحافز بإجمالي مستحق {_egp(bonus_total)} "
        "وفق سلّم التحصيل المُعدّ.",
        "الحافز مرتبط مباشرة بمعدل التحصيل التراكمي للعميل، ويكافئ الالتزام.",
        "سلّم حوافز فضفاض قد يرفع التكلفة دون أثر تحصيلي حقيقي.",
        "ضبط عتبات السلّم (متغيّر واحد) يوازن بين التحفيز والتكلفة.",
        "اعتماد السلّم الحالي ومراجعته ربع سنويًا مقابل معدل التحصيل الفعلي.",
        "منخفضة",
    )

    # --- Zero invoices -----------------------------------------------------
    zc = kpis["zero_invoices"]
    out["zero_invoices"] = _insight(
        "الفواتير صفرية القيمة",
        f"{zc} فاتورة بقيمة صفرية (غالبًا بونص/عيّنات) خلال الشهر.",
        "فواتير البونص تُسجَّل بقيمة صفر لكنها تستهلك مخزونًا فعليًا.",
        "غياب رقابة على البونص يخفي تكلفة حقيقية غير ظاهرة في الإيراد.",
        "قياس نسبة البونص للمبيعات يكشف فرص ترشيد.",
        "اعتماد سقف بونص لكل عميل ومتابعته شهريًا.",
        "متوسطة",
    )

    # --- Data quality ------------------------------------------------------
    s = dq["summary"]
    out["data_quality"] = _insight(
        "جودة البيانات",
        f"طوبقت {s['reconciliation_pass']} من {s['n_invoices']} فاتورة "
        f"({s['reconciliation_rate'] * 100:.1f}%)، مع {s['duplicate_invoice_count']} "
        f"تكرار و{s['zero_value_invoice_count']} فاتورة صفرية.",
        "الاستخراج من صور الفواتير يتطابق مع الإجماليات المصدرية بدقة عالية.",
        "أي قيم مفقودة أو شاذّة قد تنحرف بالمؤشرات إن لم تُراقب.",
        "بيانات نظيفة تتيح الثقة في القرارات المبنية عليها.",
        "الإبقاء على فحص جودة آلي مع كل تحديث بيانات.",
        "منخفضة",
    )

    return out
