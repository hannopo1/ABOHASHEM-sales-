# تطبيق أبو هاشم للجوال

تطبيق جوال بملف واحد (RTL، عربي) يقرأ نفس أرقام لوحات هذا المستودع. يُفتح من
`file://` على الهاتف بلا خادم وبلا إنترنت.

## البنية

```
mobile/
  src/                وحدات التطبيق (تُحرَّر هنا)
    dash-tokens.js      النطاق T — الألوان، المُنسِّقات، مسميات الأقسام وبطاقات KPI
    dash-agg.js         النطاق A — makeApi()، التجميع فوق window.DASH
    repo-adapter.js     النطاق R — الأقسام وبطاقات KPI والفلاتر فوق window.DASH_DATA
    dash-aging.js       النطاق G — أعمار المديونية (FIFO بالتحصيلات والمرتجعات)
    dash-charts.js      النطاق C — 14 مُنشئ رسم ECharts + مكوّن EChart المضيف
    dash-app.js         مكوّن App والأقسام والفلاتر والأوراق السفلية
    app.css             أنماط الرأس
  data/snapshots/     لقطات المديونية (مخرجات build.py) + index.json
  vendor/             React 18.3.1 + ReactDOM 18.3.1 (UMD, production)
  tools/              أدوات التحقق
  dist/               الملف الجاهز للتوزيع
  index.html          قشرة تطوير (تتطلب خادمًا محليًا)
  build_standalone.py مولّد الملف المفرد
```

### ما لا يُكرَّر هنا

يقرأ البناء هذين الملفين من مكانهما بدل نسخهما:

| المصدر | السبب |
|---|---|
| `executive_dashboard/vendor/echarts.min.js` | مطابق بايت-ببايت للنسخة التي كان يحملها البناء المُسلَّم. نسخة واحدة تُبقي اللوحتين على إصدار ECharts واحد (5.6.0). |
| `dashboards/data.js` | `window.DASH_DATA` — مخرجات `analysis/10_export_dashboard_data.py`. |
| `executive_dashboard/vendor/fonts/Cairo-*.woff2` | تُضمَّن كـ data-URI عند البناء. |

اللقطات وحدها تعيش تحت `mobile/data/` لأنها مخرجات `build.py` لم تُودَع في أي مكان آخر
بالمستودع، وهي أحدث مما فيه (`as_of` 23 و30 يوليو مقابل 16 يوليو المُودَعة).

## التشغيل

```bash
# بناء الملف المفرد
python3 mobile/build_standalone.py

# تطوير سريع (وحدة لكل <script>، بلا إعادة بناء)
python3 -m http.server 8000        # من جذر المستودع
# ثم افتح http://localhost:8000/mobile/
```

## التحقق

```bash
# 1) التكافؤ مع البناء المُسلَّم — كود التطبيق والبيانات والمكتبات
python3 mobile/tools/verify_against_shipped.py <الملف-المُسلَّم>.html

# 2) اختبار تشغيل حقيقي في متصفح بلا واجهة
pip install playwright
python3 mobile/tools/smoke_test.py
```

`verify_against_shipped.py` يثبت أن الوحدات المستخرجة تُعيد إنتاج البناء الأصلي:
كل سطر تنفيذي متطابق، وكل حمولة بيانات متطابقة، وكل بايت مكتبة متطابق.
`smoke_test.py` يفتح الملف فعليًا ويمرّ على كل الأقسام في مجموعتَي البيانات.

## مجموعتا البيانات

يحمل التطبيق مصدرين مستقلين ويبدّل بينهما (لا يدمجهما):

| المصدر | المتغيّر | التغطية | الأقسام |
|---|---|---|---|
| **تفصيلي** | `window.DASH` | لقطات مديونية 2026 على مستوى الفاتورة | 11 |
| **18 شهرًا** | `window.DASH_DATA` | تجميعات مسبقة، 18 شهرًا و337 عميلًا | 9 |
