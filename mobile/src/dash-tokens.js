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
/**
 * Groups records by a key and totals a numeric property for each group.
 * @param {Array<Object>} arr - The records to aggregate.
 * @param {string} key - The property used to identify each group.
 * @param {string} val - The numeric property to total.
 * @return {Map<*, number>} A map from group keys to summed values.
 */
function groupSum(arr,key,val){const m=new Map();for(const x of arr){const k=x[key];m.set(k,(m.get(k)||0)+(x[val]||0));}return m;}

/* Section inventory — verbatim from SECTIONS, in source order. */
const SECTION_LABELS = [
  {id:"overview",    label:"لوحة المعلومات",    h2:"لوحة المعلومات التنفيذية", p:"المبيعات والتحصيل والمديونية"},
  {id:"sales",       label:"المبيعات",           h2:"تحليل المبيعات",           p:"الاتجاهات والمقارنات والتفاصيل"},
  {id:"customers",   label:"العملاء",            h2:"تحليل العملاء",            p:"الترتيب، التركّز، والأداء متعدد الأبعاد"},
  {id:"products",    label:"المنتجات",           h2:"تحليل المنتجات",           p:"المساهمة، تشتت الأسعار، والأداء"},
  {id:"receivables", label:"المديونية",          h2:"المديونية وتحليل الأعمار", p:"الأعمار تقديرية — لا تواريخ استحقاق بالمصدر"},
  {id:"collections", label:"التحصيل والتسويات",  h2:"التحصيل والتسويات",        p:"التحصيل النقدي الفعلي والمرتجعات وتسوية الأرصدة"},
  {id:"bonus",       label:"الحوافز",            h2:"حوافز التحصيل",            p:"تُحتسب آليًا من معدل التحصيل وفق سلّم قابل للضبط من متغيّر واحد"},
  {id:"analytics",   label:"التحليلات المتقدمة", h2:"التحليلات المتقدمة",       p:"Sunburst · Sankey · Heatmap · التوزيعات"},
  {id:"quality",     label:"جودة البيانات",      h2:"جودة البيانات",            p:"مطابقة الاستخراج والقيم الشاذّة — لا يُحذف أي سجل، تُرصد فقط"},
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
  {icon:"warn",  key:"overdue",              label:"المتأخرات",             accent:"#ef4444", fmt:"egpK", sub:"تقديري", subCls:"na"},
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
const FMT = {egp, egpK, num, int, pct:(x)=>pct(x)};

return {PAL,AGING_KEYS,AGING_COLORS,egp,egpK,num,int,pct,round2,sum,groupSum,SECTION_LABELS,BONUS_RULES,FILTER_DEFS,KPI_DEFS,KPI_ICONS,FMT};
})();
