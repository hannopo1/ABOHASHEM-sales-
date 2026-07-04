# منصة الذكاء المالي — ABOHASHEM FOR MEAT

تحليل شامل مبني حصريًا على ملفات الفواتير وملفي التصنيف المرفوعة في جذر المستودع. لا توجد أي بيانات مُفترضة أو خارجية.

## البنية

```
analysis/
├── scripts/     # خط أنابيب بايثون: تحليل الفواتير → تنظيف → EDA → اختبارات إحصائية → تنبؤ
├── data/        # مخرجات منظّفة (CSV/JSON) — كل رقم في التقارير قابل للتتبع لملف هنا
│   └── eda/     # نواتج التحليل الاستكشافي والتنبؤ
├── dashboards/  # 6 لوحات HTML تفاعلية (افتح index.html في المتصفح)
└── reports/     # التقارير المكتوبة الثلاثة (جودة بيانات، اقتصاد قياسي أكاديمي، استثماري تنفيذي)
```

## إعادة تشغيل خط الأنابيب

```bash
cd scripts
python3 parse_invoices.py            # يقرأ ملف الفواتير الرئيسي → data/invoices_header.csv, invoice_lines.csv
python3 parse_invoices_june2026.py   # يقرأ ملف يونيو 2026 → *_june2026.csv
python3 build_reference_tables.py    # يستخرج تصنيف البراند وسعة الكرتونة من ملفي PDF
python3 build_item_brand_map.py      # يطابق كود الصنف بالبراند (كلمة مفتاحية ثم مطابقة ضبابية)
python3 build_masters_and_dq.py      # يدمج المصدرين، يبني جداول العملاء/الأصناف، ويحسب مقاييس جودة البيانات
python3 eda.py                       # التحليل الاستكشافي: شهري، عملاء، براند، أصناف، Pareto/ABC/XYZ
python3 timeseries_tests.py          # ADF/KPSS/Ljung-Box/Durbin-Watson/Jarque-Bera/BP/White/RESET
python3 forecast.py                  # مقارنة نماذج + تنبؤ 7 أشهر (شركة/براند/أفضل 10 عملاء/أفضل 10 أصناف)
python3 financial_analysis.py        # مؤشرات إيرادية/تركّز/ذمم مدينة
python3 hierarchy.py                 # شجرة عميل ← براند ← صنف الهرمية الكاملة
```

## اللوحات

افتح `dashboards/index.html` في أي متصفح (بدون حاجة لخادم — كل البيانات مضمّنة في `data.js`):

1. **index.html** — التنفيذية (مالية + مبيعات)
2. **customer_profitability.html** — ربحية العملاء (إيرادية) + Drill-down
3. **brand_performance.html** — أداء البراندات الثلاثة
4. **product_performance.html** — أداء الأصناف (ABC × XYZ)
5. **manufacturing_inventory.html** — التصنيع والمخزون (محدودة بحدود البيانات المرفوعة)
6. **forecast_dashboard.html** — التنبؤ 7 أشهر مع مقارنة النماذج

## قيود جوهرية على النطاق (اقرأ قبل أي استخدام)

- **لا توجد بيانات تكلفة/مشتريات/مخزون فعلي** في الملفات المرفوعة → كل الأرقام إيرادية (Revenue-side)، لا هامش ربح أو EBITDA أو صافي ربح.
- **18 نقطة شهرية فقط** (2025-01 → 2026-06) → أقل من 24 اللازمة لتحليل موسمي موثوق؛ النماذج الموسمية استُبعدت عمدًا من مقارنة التنبؤ.
- **حقل "الباقي" في الفواتير** يعكس رصيد وقت التحرير فقط وليس متابعة تحصيل فعلية — راجع `reports/01_data_quality_report.md` §3.7 قبل أي استخدام ائتماني.

التفاصيل الكاملة لكل قيد وكل افتراض موثقة في `reports/01_data_quality_report.md`.
