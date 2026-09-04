/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   Namespace T — palette, formatters, label/KPI inventory.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
const T = (function(){
/* Abu Hashem — mobile runtime · PART 1: palette, formatters, label inventory.
   Copied VERBATIM from the source dashboard (dashboard_standalone-٢ (1).html
   client runtime). No value, label, term or formula altered.
   DATA CONTRACT: window.DASH — exactly the schema the source reads
   (meta, lines, invoices, monthly, receivables, customer_ar, collections,
    zero_invoices, data_quality, insights_by_month). Source guard preserved:
   no DASH -> "data.js لم يُحمّل". */

const PAL = ["#3b82f6","#8b5cf6","#10b981","#f59e0b","#ef4444","#06b6d4","#f97316","#ec4899","#c4b5fd","#34d399"];
const AGING_KEYS = ["current","d1_30","d31_60","d61_90","d91_120","d120p"];
const AGING_COLORS = {current:"#10b981",d1_30:"#34d399",d31_60:"#f59e0b",d61_90:"#f97316",d91_120:"#ef4444",d120p:"#dc2626"};

const egp = x => (Math.round(x||0)).toLocaleString("en-US") + " ج.م";
const egpK = x => { x=x||0; const a=Math.abs(x);
  if(a>=1e6) return (x/1e6).toFixed(2)+"M ج.م";
  if(a>=1e3) return (x/1e3).toFixed(1)+"K ج.م"; return Math.round(x)+" ج.م"; };
const num = x => (Math.round((x||0)*100)/100).toLocaleString("en-US");
const int = x => Math.round(x||0).toLocaleString("en-US");
const pct = (x,d=1) => ((x||0)*100).toFixed(d) + "%";
const round2 = x => Math.round((x||0)*100)/100;
const sum = (arr,k) => arr.reduce((a,x)=>a+(x[k]||0),0);
function groupSum(arr,key,val){const m=new Map();for(const x of arr){const k=x[key];m.set(k,(m.get(k)||0)+(x[val]||0));}return m;}

/* Section inventory — verbatim from SECTIONS, in source order. */
const SECTION_LABELS = [
  {id:"overview",    label:"لوحة المعلومات",    h2:"لوحة المعلومات التنفيذية", p:"المبيعات والتحصيل والمديونية"},
  {id:"sales",       label:"المبيعات",           h2:"تحليل المبيعات",           p:"الاتجاهات والمقارنات والتفاصيل"},
  {id:"customers",   label:"العملاء",            h2:"تحليل العملاء",            p:"الترتيب، التركّز، والأداء متعدد الأبعاد"},
  {id:"products",    label:"المنتجات",           h2:"تحليل المنتجات",           p:"المساهمة، تشتت الأسعار، والأداء"},
  {id:"receivables", label:"المديونية",          h2:"المديونية وتحليل الأعمار", p:D=>"لقطة أرصدة "+arDate(asOfOf(D))+" — لا تتأثر بفلتر الشهر"},
  {id:"overdue",     label:"المستحق",            h2:"المستحق والمتأخرات",       p:D=>"الاستحقاق بعد "+termsOf(D)+" يومًا من تاريخ الفاتورة — سياسة الشركة لا حقل بالمصدر"},
  {id:"collections", label:"التحصيل والتسويات",  h2:"التحصيل والتسويات",        p:"التحصيل النقدي الفعلي والمرتجعات وتسوية الأرصدة"},
  {id:"bonus",       label:"الحوافز",            h2:"حوافز التحصيل",            p:"تُحتسب آليًا من معدل التحصيل وفق سلّم قابل للضبط من متغيّر واحد"},
  {id:"analytics",   label:"التحليلات المتقدمة", h2:"التحليلات المتقدمة",       p:"Sunburst · Sankey · Heatmap · التوزيعات"},
  {id:"quality",     label:"جودة البيانات",      h2:"جودة البيانات",            p:"مطابقة الاستخراج والقيم الشاذّة — لا يُحذف أي سجل، تُرصد فقط"},
  {id:"reports",     label:"التقارير",           h2:"التقارير — كل الجداول",    p:"كل جدول يمكن تصديره معروض هنا كما هو — القسم والتصدير يقرآن التعريف نفسه"},
];

/* Bonus ladder rows — verbatim. */
const BONUS_RULES = [["أقل من 70%","0%"],["70% – 80%","1%"],["80% – 90%","2%"],["90% – 95%","3%"],["95% – 100%","5%"]];

/* Filter bar inventory — verbatim labels and options. */
const FILTER_DEFS = [
  {key:"year",     label:"السنة",         fixed:"2026"},
  {key:"month",    label:"الشهر"},
  {key:"customer", label:"العميل",        all:"الكل"},
  {key:"rep",      label:"المندوب",       all:"الكل"},
  {key:"item",     label:"الصنف",         all:"الكل"},
  {key:"brand",    label:"العلامة/الفئة", all:"الكل"},
  {key:"branch",   label:"الفرع",         all:"كل الفروع"},
  {key:"status",   label:"حالة الفاتورة", all:"الكل",
   options:[["unpaid","غير محصّلة"],["paid","محصّلة"],["zero","صفرية"]]},
  {key:"aging",    label:"فئة العمر",     all:"الكل"},
];

/* The 13 KPI cards of kpiGrid() — same order, icons, accents, labels, subs. */
const KPI_DEFS = [
  {icon:"sales", key:"total_sales",          label:"إجمالي المبيعات",       accent:"#3b82f6", fmt:"egpK", momSub:true},
  {icon:"money", key:"net_sales",            label:"صافي المبيعات",         accent:"#8b5cf6", fmt:"egpK"},
  {icon:"money", key:"collections_at_issue", label:"التحصيل عند الإصدار",   accent:"#06b6d4", fmt:"egpK", sub:"بيع آجل", subCls:"na"},
  {icon:"money", key:"outstanding",          label:"المديونية القائمة",     accent:"#f59e0b", fmt:"egpK", subAsOf:true, subCls:"na"},
  {icon:"warn",  key:"overdue",              label:"المتأخرات",             accent:"#ef4444", fmt:"egpK", overdueSub:true, subCls:"na"},
  {icon:"pct",   key:"collection_rate",      label:"معدل التحصيل التراكمي", accent:"#10b981", fmt:"pct", subCls:"up"},
  {icon:"money", key:"asp",                  label:"متوسط سعر البيع/وحدة", accent:"#c4b5fd", fmt:"egp"},
  {icon:"box",   key:"qty",                  label:"إجمالي الكمية",         accent:"#34d399", fmt:"int"},
  {icon:"box",   key:"boxes",                label:"إجمالي الكراتين",       accent:"#f97316", fmt:"int"},
  {icon:"users", key:"n_customers",          label:"عدد العملاء",           accent:"#3b82f6", fmt:"int"},
  {icon:"doc",   key:"n_invoices",           label:"عدد الفواتير",          accent:"#8b5cf6", fmt:"int", subAvg:true, subCls:"na"},
  {icon:"warn",  key:"zero_invoices",        label:"فواتير صفرية",          accent:"#ef4444", fmt:"int", sub:"بونص/عيّنات", subCls:"na"},
  {icon:"pct",   key:null,                   label:"هامش الربح الإجمالي",   accent:"#64748b", fixed:"غير متاح", sub:"لا توجد تكلفة", subCls:"na"},
];

const KPI_ICONS = {
  sales:'<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  money:'<path d="M12 1v22"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
  users:'<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>',
  doc:'<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/>',
  box:'<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8"/><path d="M3.3 7L12 12l8.7-5"/>',
  pct:'<path d="M19 5L5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  warn:'<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
  clock:'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
};
/* ---- period labels -------------------------------------------------------
   Every window the app prints — «يناير – أغسطس 2026», «20 شهرًا», the snapshot
   date — used to be typed into the string that displayed it. About twenty of
   them, spread over three modules. So when August arrived the numbers moved and
   the labels did not: the nav still said «يناير – يوليو 2026», the badge still
   said «18 شهرًا», and the eighteen-month section still announced an AR snapshot
   dated 2026/7/4 that had been superseded two months earlier.

   These derive each label from the payload that section actually reads, so a new
   month relabels the app by arriving. Nothing here formats a date it was not
   given: an absent field yields an empty string, never a guess. */
const AR_MONTH_NAMES = ["يناير","فبراير","مارس","أبريل","مايو","يونيو",
                        "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];

/* "2026-08" -> "أغسطس 2026" */
const arMonth = m => {
  if(!m) return "";
  const p = String(m).split("-");
  const i = parseInt(p[1],10) - 1;
  return (AR_MONTH_NAMES[i] || "") + " " + p[0];
};

/* Arabic counts a noun differently at 1, 2, 3–10 and 11+: "12 أشهر" is wrong
   where "12 شهرًا" is right. */
const arMonths = n => {
  if(n === 1) return "شهر واحد";
  if(n === 2) return "شهرين";
  return n < 11 ? n + " أشهر" : n + " شهرًا";
};

/* A first→last span, collapsing the year when both ends share it:
   ("2026-01","2026-08") -> "يناير – أغسطس 2026"   (not "يناير 2026 – أغسطس 2026")
   ("2025-01","2026-08") -> "يناير 2025 – أغسطس 2026" */
const monthSpan = (from, to) => {
  if(!from || !to) return "";
  if(from === to) return arMonth(from);
  const yf = String(from).split("-")[0], yt = String(to).split("-")[0];
  if(yf === yt) return arMonth(from).replace(" "+yf, "") + " – " + arMonth(to);
  return arMonth(from) + " – " + arMonth(to);
};

/* The invoice-detail window, from the months the payload says it HAS — not from
   the twelve months its month-selector offers. */
const invWindow = D => {
  const m = D && D.meta && D.meta.data_months;
  return (m && m.length) ? monthSpan(m[0], m[m.length-1]) : "";
};

/* The pre-aggregated window and its length. */
const aggSeries = RD => (RD && RD.monthly_series) || [];
const aggWindow = RD => {
  const s = aggSeries(RD);
  return s.length ? monthSpan(s[0].month, s[s.length-1].month) : "";
};
const aggMonths = RD => {
  const n = aggSeries(RD).length;
  return n ? arMonths(n) : "";
};

/* "2026-09-04" -> "4 سبتمبر 2026". The snapshot's ISSUE date, which is NOT the
   date its receivables were struck — that is meta.as_of, and conflating the two
   would re-date the balances to a day nobody counted them on. */
const arDate = d => {
  if(!d) return "";
  const p = String(d).split("-");
  if(p.length < 3) return String(d);
  return parseInt(p[2],10) + " " + (AR_MONTH_NAMES[parseInt(p[1],10)-1] || "") + " " + p[0];
};
const snapshotDate = D => (D && D.meta && D.meta.snapshot_date) || "";

/* The date the receivables were STRUCK (meta.as_of), and the credit terms the
   due date is derived from. Both come off the payload so a new snapshot or a
   change of terms re-labels every screen without a string being retyped. */
const asOfOf = D => (D && D.meta && D.meta.as_of) || "";
const termsOf = D => (D && D.meta && D.meta.net_terms_days) || 30;
/* Latest invoice date still within terms — derived server-side, shown as-is. */
const overdueCutoff = D => (D && D.meta && D.meta.overdue_cutoff) || "";
const snapshotLabel = D => {
  const d = snapshotDate(D);
  return d ? "لقطة " + arDate(d) : "";
};

const FMT = {egp, egpK, num, int, pct:(x)=>pct(x)};

return {PAL,AGING_KEYS,AGING_COLORS,egp,egpK,num,int,pct,round2,sum,groupSum,SECTION_LABELS,BONUS_RULES,FILTER_DEFS,KPI_DEFS,KPI_ICONS,FMT,arMonth,arMonths,monthSpan,invWindow,aggWindow,aggMonths,arDate,snapshotDate,snapshotLabel,asOfOf,termsOf,overdueCutoff};
})();
