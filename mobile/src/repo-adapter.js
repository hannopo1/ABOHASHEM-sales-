/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   Namespace R — SECTIONS, KPI builders and filters for window.DASH_DATA.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
const R = (function(){
/* Abu Hashem — adapter for window.DASH_DATA (the repo dataset in
   dashboards/data.js, read by dashboards/index.html).

   Labels, KPI definitions, notes, colours and formatters are copied VERBATIM
   from the repo's own dashboard sources (dashboards/tab_exec_financial.js,
   tab_exec_sales.js, tab_customer.js, tab_brand.js). Nothing is recalculated:
   every number below is a field that already exists in data.js. */

const C = {blue:"#2a78d6", green:"#1baf7a", amber:"#eda100", red:"#e34948",
  orange:"#eb6834", indigo:"#4a3aa7", grey:"#898781", pale:"#c3c2b7"};
const BRAND_COLORS = {"الهنا":"#2a78d6","ابوهاشم":"#1baf7a","اسبشيال":"#eda100","غير مصنف":"#898781"};

const nf = (d) => (x) => (x==null||isNaN(x)) ? "—" : Number(x).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const fmt0 = nf(0), fmt1 = nf(1), fmt2 = nf(2);
const fmtEGP = x => (x==null||isNaN(x)) ? "—" : fmt0(x) + " ج.م";
const fmtPct = x => (x==null||isNaN(x)) ? "—" : fmt1(x) + "%";
const fmtEGPk = x => { if(x==null||isNaN(x)) return "—"; const a=Math.abs(x);
  if(a>=1e6) return (x/1e6).toFixed(2)+"M ج.م"; if(a>=1e3) return (x/1e3).toFixed(1)+"K ج.م"; return fmt0(x)+" ج.م"; };

const AR_MONTHS = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
const monthAr = ym => { if(!ym) return "—"; const [y,m]=String(ym).split("-"); return (AR_MONTHS[+m-1]||m)+" "+y; };

/* The as_of the AR rows themselves carry — the analysis pipeline stamps every
   row with it (analysis/00_ar_snapshot.py), so the label cannot drift from the
   balances it sits next to. Empty when the payload predates the stamp. */
const arSnapAsOf = D => {
  const rows = (D && D.ar_balances) || [];
  const stamped = rows.find(r => r && r.as_of);
  return stamped ? T.arDate(stamped.as_of) : "";
};

/* Sections — titles and sub-lines verbatim from the repo tab_*.js panels. */
const SECTIONS = [
  {id:"fin",      label:"المالية",   title:"اللوحة المالية التنفيذية",
   /* Derived, not written: the month count, the window and the AR snapshot date
      all come from the payload being displayed. Written out, this sentence went
      on claiming «18 شهرًا» and «لقطة 2026/7/4» for two months after both moved. */
   sub:D=>"جميع الأرقام مُحتسبة من فواتير المبيعات الفعلية ("+
          T.aggMonths(D)+": "+T.aggWindow(D)+") ولقطة مديونية العملاء بتاريخ "+
          arSnapAsOf(D)+". الهامش والتكلفة في قسم «الربحية» ولا يظهران هنا؛ "+
          "وEBITDA غير متاح لعدم وجود بيانات إهلاك."},
  {id:"sales",    label:"المبيعات",  title:"لوحة المبيعات التنفيذية",
   sub:"أعلى/أدنى الأداء، تحليل باريتو 80/20، وشجرة التحليل الهرمي القابلة للتوسيع (عميل ← علامة تجارية ← صنف)."},
  {id:"customers",label:"العملاء",   title:"لوحة ربحية العملاء (على أساس الإيراد الصافي)",
   sub:"تُبنى هذه اللوحة على الإيراد الصافي وليس هامش الربح، لعدم توفر بيانات تكلفة البضاعة المباعة لكل عميل. تصنيف ABC حسب حجم الإيراد، وتصنيف XYZ حسب استقرار الطلب."},
  {id:"debt",     label:"المديونية", title:"المديونية حسب المندوب والعميل",
   sub:D=>"لقطة أرصدة العملاء بتاريخ "+arSnapAsOf(D)+" — مدين، دائن، وصافي الرصيد."},
  {id:"brands",   label:"العلامات",  title:"لوحة أداء العلامات التجارية",
   sub:"3 علامات تجارية نشطة: الهنا، أبوهاشم، اسبشيال (وفقًا لملف «تصنيف الأصناف كبراند»)."},
  {id:"products", label:"الأصناف",   title:"تحليل الأصناف",
   sub:"تصنيف ABC/XYZ للأصناف، متوسط سعر البيع، والكراتين."},
  {id:"forecast", label:"التنبؤ",    title:"توقع الإيراد — 7 أشهر مقبلة",
   sub:"الخط المتصل: مبيعات فعلية. المنقط: التوقع الأساسي (نموذج Holt). النطاق: فترة الثقة 95%."},
  {id:"quality",  label:"جودة البيانات", title:"جودة البيانات",
   sub:"مطابقة الاستخراج والقيم الشاذّة — لا يُحذف أي سجل، تُرصد فقط."},
  {id:"analysis", label:"التحليل التفاعلي", title:"التحليل التفاعلي",
   sub:"قسّم الإيراد حسب المندوب والعلامة والعميل والصنف. تُحتسب كل الأرقام من الشجرة الهرمية (عميل ← علامة ← صنف) التي يطابق إجماليها إجمالي الإيراد المعلن."},
  {id:"reports",  label:"التقارير",  title:"التقارير — كل الجداول",
   sub:"كل جدول يمكن تصديره معروض هنا كما هو. القسم والتصدير يقرآن التعريف نفسه، فلا يمكن أن يفترقا: ما تراه في الشاشة هو ما يخرج في ملف Excel، صفًا بصف."},
];

/* Sections whose figures come from precomputed company-level aggregates and
   therefore cannot honestly be re-derived for a filtered subset. */
const UNFILTERABLE = ["fin", "forecast", "quality"];

/* KPI rows — exactly the label/value/sub triples the repo tabs build. */
function kpisFin(D){
  const f=D.financial;
  return [
    ["إجمالي الإيرادات ("+T.aggMonths(D)+")", fmtEGP(f.total_revenue_egp), "من "+f.period.start+" إلى "+f.period.end, C.blue],
    ["إيرادات آخر 12 شهرًا", fmtEGP(f.trailing_12m_revenue_egp), "", C.green],
    ["متوسط الإيراد الشهري (آخر 12 شهرًا)", fmtEGP(f.avg_monthly_revenue_t12_egp), "", C.indigo],
    ["رصيد المديونية الصافي", fmtEGP(f.ar_total_net_balance_egp),
     "لقطة "+arSnapAsOf(D), C.amber],
    ["نسبة الاستقطاع الإجمالية", fmtPct(f.aggregate_deduction_rate_pct), "من القيمة الاسمية", C.red],
    ["حصة أعلى 10 عملاء", fmtPct(f.top10_customer_share_pct), "من إجمالي الإيرادات", C.orange],
  ];
}
function kpisSales(D){
  const m=D.monthly_series;
  return [
    ["عدد العملاء النشطين", fmt0(D.eda_summary.n_customers), "", C.blue],
    ["عدد الأصناف المباعة", fmt0(D.eda_summary.n_items), "", C.green],
    ["عدد العلامات التجارية", "3", "أبوهاشم، الهنا، اسبشيال", C.amber],
    ["متوسط قيمة الفاتورة", fmtEGP(m.reduce((a,r)=>a+r.revenue_per_invoice,0)/m.length), "متوسط "+T.aggMonths(D), C.indigo],
  ];
}
function kpisCust(D){
  const c=D.customer_pareto, f=D.financial;
  return [
    ["عدد العملاء الإجمالي", fmt0(c.length), "", C.blue],
    ["عملاء فئة A (80% من الإيراد)", fmt0(c.filter(x=>x.abc_class==="A").length), "", C.green],
    ["متوسط إيراد الشهر النشط/عميل", fmtEGP(f.avg_revenue_per_active_month_per_customer_egp), "الوسيط: "+fmtEGP(f.median_revenue_per_active_month_per_customer_egp), C.indigo],
    ["عملاء لديهم رصيد مدين حاليًا", fmt0(f.ar_n_customers_with_debit_balance), "من لقطة "+arSnapAsOf(D), C.amber],
  ];
}
function kpisBrands(D){
  const f=D.financial;
  return D.brand_summary.filter(b=>b.brand!=="غير مصنف")
    .map(b=>[b.brand, fmtEGP(b.revenue), fmtPct(b.revenue_share_pct)+" من الإيراد · "+fmt0(b.n_customers)+" عميلاً", BRAND_COLORS[b.brand]])
    .concat([["مؤشر تركّز العلامات (HHI)", fmt0(f.hhi_brands), "تركّز مرتفع", C.red]]);
}
function kpisDebt(D){
  const f=D.financial;
  return [
    ["صافي رصيد المديونية", fmtEGP(f.ar_total_net_balance_egp),
     "لقطة "+arSnapAsOf(D), C.amber],
    ["إجمالي مدين", fmtEGP(f.ar_total_debit_egp), "", C.red],
    ["إجمالي دائن", fmtEGP(f.ar_total_credit_egp), "", C.green],
    ["أيام الذمم المدينة (DSO) التقريبية", fmt1(f.dso_proxy_days)+" يومًا", "تقديري", C.indigo],
    ["حصة أعلى 10 مدينين", fmtPct(f.ar_top10_debtor_share_pct), "من إجمالي المديونية", C.orange],
    ["عملاء برصيد دائن", fmt0(f.ar_n_customers_with_credit_balance), "", C.blue],
  ];
}
function kpisProducts(D){
  const items=D.item_abc_xyz;
  return [
    ["عدد الأصناف المباعة فعليًا", fmt0(items.length), "", C.blue],
    ["أصناف فئة A", fmt0(items.filter(i=>i.abc_class==="A").length), "تمثل 80% من الإيراد", C.green],
    ["أصناف بتذبذب طلب مرتفع (Z)", fmt0(items.filter(i=>i.xyz_class==="Z").length), "تحتاج مخزون أمان أعلى", C.red],
    ["حصة أعلى 10 أصناف", fmtPct(D.financial.top10_item_share_pct), "من إجمالي الإيراد", C.orange],
  ];
}
function kpisQuality(D){
  const q=D.data_quality;
  return [
    ["عدد البنود", fmt0(q.n_rows), "", C.blue],
    ["عدد الفواتير", fmt0(q.n_invoices), "", C.green],
    ["تواريخ غير مقروءة", fmt0(q.n_unparseable_dates), "", C.amber],
    ["بنود بسعر صفر", fmt0(q.n_zero_price_lines), "", C.orange],
    ["كميات سالبة", fmt0(q.n_negative_qty), "", C.red],
    ["بنود بونص", fmt0(q.n_bonus_lines), fmt2(q.bonus_share_of_lines_pct)+"% من البنود", C.indigo],
  ];
}


/* ------------------------------------------------------------------ filters

   Ported from the Dart implementation in abu_hashem_mobile/lib/data/filters.dart,
   which is covered by tests asserting that every rep and every brand partitions
   revenue exactly and that a brand slice matches the independent brand_summary
   table. `hierarchy_tree` is the customer -> brand -> item cube; its sales total
   reconciles to financial.total_revenue_egp, which is what makes a filtered
   figure a genuine subset of reported revenue rather than an approximation.

   Month is deliberately not a filter dimension: the cube has no month axis, so a
   month cannot be combined with a customer, rep or item without inventing data. */

/* 127 of 337 customers carry no rep in the AR snapshot. Bucketing them under the
   source runtime's own label keeps 2.1M EGP in the totals; dropping them would
   silently lose it. */
const UNASSIGNED_REP = "غير محدد";

const _repCache = new WeakMap();
function repByCustomer(D){
  let m = _repCache.get(D);
  if(!m){
    m = new Map();
    for(const c of (D.dim_customers||[])) m.set(c.customer_code, c.rep || UNASSIGNED_REP);
    _repCache.set(D, m);
  }
  return m;
}
const repOf = (D, code) => repByCustomer(D).get(code) || UNASSIGNED_REP;

const EMPTY_FILTERS = {rep:null, brand:null, customerCode:null, itemName:null};
const isEmptyFilters = f => !f || (!f.rep && !f.brand && !f.customerCode && !f.itemName);
const activeFilterCount = f =>
  f ? [f.rep, f.brand, f.customerCode, f.itemName].filter(Boolean).length : 0;

/* Whether a monthly trend can honestly be drawn for the current slice:
   "company" (no filter) | "brand" (brand alone) | "unavailable". */
function monthlyAvailability(f){
  if(isEmptyFilters(f)) return "company";
  if(f.brand && !f.rep && !f.customerCode && !f.itemName) return "brand";
  return "unavailable";
}

/* One pass over the cube, aggregating every dimension. Only leaf nodes that
   survive all four filters contribute, so the filters compose rather than
   override one another. */
function applyFilters(D, f){
  f = f || EMPTY_FILTERS;
  const byRep=new Map(), byBrand=new Map(), byCustomer=new Map(),
        byItem=new Map(), custName=new Map(), customers=new Set();
  let sales=0, qty=0;
  const add=(m,k,s,q)=>{ const e=m.get(k)||[0,0]; e[0]+=s; e[1]+=q; m.set(k,e); };

  for(const c of (D.hierarchy_tree||[])){
    if(f.customerCode && c.customer_code !== f.customerCode) continue;
    const rep = repOf(D, c.customer_code);
    if(f.rep && rep !== f.rep) continue;

    for(const bn of Object.keys(c.brands||{})){
      if(f.brand && bn !== f.brand) continue;
      for(const it of (c.brands[bn].items||[])){
        if(f.itemName && it.name !== f.itemName) continue;
        sales += it.sales; qty += it.qty;
        customers.add(c.customer_code); custName.set(c.customer_code, c.name);
        add(byRep, rep, it.sales, it.qty);
        add(byBrand, bn, it.sales, it.qty);
        add(byCustomer, c.customer_code, it.sales, it.qty);
        add(byItem, it.name, it.sales, it.qty);
      }
    }
  }

  const rank=(m,asCustomer)=>[...m.entries()]
    .map(([k,v])=>({name:asCustomer?(custName.get(k)||k):k, sales:v[0], qty:v[1],
                    code:asCustomer?k:null}))
    .sort((a,b)=>b.sales-a.sales);

  const grandTotal = (D.financial && D.financial.total_revenue_egp) || 0;
  return {
    sales, qty,
    nCustomers: customers.size, nBrands: byBrand.size, nItems: byItem.size,
    byRep: rank(byRep,false), byBrand: rank(byBrand,false),
    byCustomer: rank(byCustomer,true), byItem: rank(byItem,false),
    grandTotal,
    shareOfTotal: grandTotal ? sales/grandTotal*100 : 0,
    avgPrice: qty ? sales/qty : null,   // null, not a misleading zero
    monthlyAvailability: monthlyAvailability(f),
    isEmpty: customers.size === 0,
  };
}

/* Option lists for the filter sheet, ordered by revenue so the likely choices
   sit at the top. */
function filterOptions(D){
  const all = applyFilters(D, EMPTY_FILTERS);
  return {reps:all.byRep, brands:all.byBrand, customers:all.byCustomer, items:all.byItem};
}

/* Customer codes matching the current slice — used to narrow the AR and customer
   tables, which carry a rep but no item dimension. */
function matchingCustomerCodes(D, f){
  if(isEmptyFilters(f)) return null;                      // null = no narrowing
  return new Set(applyFilters(D, f).byCustomer.map(r=>r.code));
}

/* Monthly revenue for one brand, aligned to monthly_series and zero-filled. */
function brandSeries(D, brand){
  const by=new Map();
  for(const r of (D.brand_month_revenue||[])) if(r.brand===brand) by.set(r.month, r.line_total);
  return (D.monthly_series||[]).map(m=>by.get(m.month)||0);
}

return {C,BRAND_COLORS,fmt0,fmt1,fmt2,fmtEGP,fmtPct,fmtEGPk,monthAr,SECTIONS,UNFILTERABLE,kpisFin,kpisSales,kpisCust,kpisBrands,kpisDebt,kpisProducts,kpisQuality,UNASSIGNED_REP,repByCustomer,repOf,EMPTY_FILTERS,isEmptyFilters,activeFilterCount,monthlyAvailability,applyFilters,filterOptions,matchingCustomerCodes,brandSeries};
})();
