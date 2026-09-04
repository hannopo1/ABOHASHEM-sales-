/* Abu Hashem — mobile runtime · الربحية (profitability).

   Reads window.DASH_MARGIN. It carries two different things and the section
   shows them as two levels, because they are measured at different scopes:

     LEVEL 1  window.DASH_MARGIN.statements — a company-level series of
              thirteen months (July 2025 – July 2026) built by
              analysis/14_income_statements.py from the income statements.
              Cost of sales here is measured, month by month.

     LEVEL 2  by_item / by_customer / by_rep / by_brand — margin by item,
              customer, representative and brand, from
              analysis/13_join_cost_margin.py. The statements carry no per-SKU
              cost, so this level is June 2026 only, behind the price-drift
              gate, exactly as before.

     LEVEL 3  by_item_month / by_customer_month / by_rep_month — the same three
              dimensions by month, twelve months, on the CALIBRATED basis: June
              unit costs scaled per month until the totals reproduce that
              month's income statement. Level one supplies the level, level two
              supplies the mix.

   Collapsing the levels would be the easiest mistake to make here and the most
   damaging: it would let a reader take a thirteen-month company margin as
   evidence about a brand or a representative, which no data supports.

   And level three is the one most easily overread. It is not measured margin
   per item. If a single item's cost moved against the rest of the basket
   between June and the month shown, nothing in it can see that. Every surface
   built from it — the divider, each table header, the exported column — has to
   say so, which is why the basis travels on every row rather than in a footnote.

   TWO THINGS THIS MODULE REFUSES TO DO, because both would mislead:

   1. It never blends the measured month with estimated ones. June 2026 is the
      only month whose cost is observed; it reconciles to the income statement
      and is shown on its own, labelled.

   2. It never shows a margin for a month that fails the price-drift gate.
      Selling prices sat ~15% below June 2026 until February 2026, so charging
      June costs against those months yields negative operating margins that are
      an artefact of the period mismatch, not history. Those months are drawn on
      the trend so the shape is visible, but greyed, excluded from every total,
      and named in the banner.

   Percentages are always against COSTED revenue — 33 of 87 items, 94.1% of
   revenue. Uncosted revenue is shown as its own figure, never as zero cost. */
const M = (function(){

/* The three levels, each counted from the data behind it rather than written
   down. Level 3 widened from twelve months to thirteen the moment July's
   invoices met July's existing income statement, and a literal would have gone
   on saying twelve. Level 2's month is the cost month the model measured. */
const SECTION = {
  id:"margin", label:"الربحية", title:"الربحية — التكلفة والهامش",
  sub:()=>{
    const d=D();
    const stmts=((d&&d.statements&&d.statements.by_month)||[]).length;
    const cal=calMonths().length;
    const costM=(d&&d.calibration&&d.calibration.cost_month)||
                (d&&d.meta&&d.meta.cost_month)||"";
    return "ثلاثة مستويات: هامش مقيس على مستوى الشركة من قوائم الدخل"+
      (stmts?" ("+T.arMonths(stmts)+")":"")+"، "+
      "ثم تفصيل مقيس حسب الصنف والعلامة والمندوب"+
      (costM?" لشهر "+T.arMonth(costM)+" وحده":"")+"، "+
      "ثم ربحية شهرية لكل صنف وعميل ومندوب معايَرة على قوائم الدخل"+
      (cal?" ("+T.arMonths(cal)+")":" — غير متاحة")+".";
  }
};

const OK = "#10b981", WARN = "#f59e0b", BAD = "#ef4444", MUTED = "#64748b";

const has = () => !!(typeof window !== "undefined" && window.DASH_MARGIN);
const D   = () => window.DASH_MARGIN;

/* Level 1 is absent from any build made before analysis/14_income_statements.py
   ran, so every use of it is guarded rather than assumed. */
const hasStmt = () => !!(has() && window.DASH_MARGIN.statements);
const S       = () => window.DASH_MARGIN.statements;

const arMonth = m => {
  if(!m) return "";
  const AR=["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
  const p=String(m).split("-");
  return AR[parseInt(p[1],10)-1]+" "+p[0];
};

/* The reliable window as a human phrase, e.g. "مارس – يونيو 2026". */
function windowLabel(d){
  const r=(d.meta.reliable_months||[]).slice().sort();
  if(!r.length) return "—";
  return r.length===1 ? arMonth(r[0]) : arMonth(r[0])+" – "+arMonth(r[r.length-1]);
}

/* Colour a margin against the measured month, which is the only benchmark the
   data actually supports. */
function marginColour(pct, ref){
  if(pct==null) return MUTED;
  if(ref==null) return OK;
  if(pct >= ref*0.95) return OK;
  if(pct >= ref*0.75) return WARN;
  return BAD;
}

/* ------------------------------------------------------------------- KPIs -- */

/* ------------------------------------------------- level 1 · the statements -- */

/* The company-level series. Every figure here is measured cost of sales from a
   signed income statement, so unlike level 2 it carries no coverage caveat and
   no price-drift gate — but it also says nothing about any single product. */
function kpisStatements(R){
  const t = S().totals, m = S().meta;
  /* The thirteen-month total IS measured: the Q1 parts sum back to the quarter
     its own statement measures, so no estimate enters the aggregate. What is
     estimated is the split into three months. Saying only "مقيس" beside "13
     شهرًا" would let that read as thirteen measured months, so the label names
     the statements and the sub-line names the allocated ones. */
  const alloc = t.n_allocated_months
    ? " · منها "+t.n_allocated_months+" أشهر موزّعة" : "";
  return [
    ["هامش مجمل — "+m.n_observations+" قوائم", R.fmtPct(t.gross_margin_pct),
     t.months+" شهرًا · "+arMonth(t.period_from)+" – "+arMonth(t.period_to)+alloc, OK],
    ["هامش صافي", R.fmtPct(t.net_margin_pct),
     "بعد كل المصروفات"+alloc, OK],
    ["صافي المبيعات", R.fmtEGP(t.net_sales), "بعد المردودات", R.C.blue],
    ["تكلفة المبيعات", R.fmtEGP(t.cogs),
     t.n_allocated_months ? "مقيسة في "+m.n_observations+" قوائم"
                          : "مقيسة شهريًا", R.C.indigo],
    ["مجمل الربح", R.fmtEGP(t.gross_profit), "الإيراد − التكلفة", R.C.blue],
    ["صافي الربح", R.fmtEGP(t.net_profit), "حسب القوائم", R.C.green],
  ];
}

/* Net sales and cost of sales as columns, gross margin as a line.

   The three months split out of the combined Q1 statement are drawn in a
   different colour and named in the tooltip. They are not a separate series:
   hiding them would leave a gap in the middle of the year, and giving them
   their own legend entry would imply they are a different kind of quantity.
   They are the same quantity, estimated. */
function stmtTrend(C){
  const rows=(S().by_month||[]).slice().sort((a,b)=>a.period<b.period?-1:1);
  if(!rows.length) return {__empty:true};
  const est=r=>r.basis==="allocated";
  const b=C.ecBase();
  const label=r=>arMonth(r.period)+(est(r)?" (موزّع)":"");

  return Object.assign(b, {
    legend:Object.assign(b.legend,{data:["صافي المبيعات","تكلفة المبيعات","هامش مجمل %"]}),
    grid:{left:6,right:10,top:34,bottom:6,containLabel:true},
    tooltip:Object.assign(b.tooltip,{trigger:"axis",
      formatter:ps=>{
        const r=rows[ps[0].dataIndex];
        return "<b>"+arMonth(r.period)+"</b><br>"
          +(est(r)?"<span style='color:"+WARN+"'>موزّع تناسبيًا من قائمة الربع الأول — تقديري</span><br>":"")
          +ps.map(p=>p.marker+" "+p.seriesName+": <b>"
              +(p.value==null?"—":Number(p.value).toLocaleString("en",{maximumFractionDigits:1}))
              +"</b>").join("<br>")
          +"<br>هامش صافي: <b>"+(r.net_margin_pct==null?"—":r.net_margin_pct.toFixed(1)+"%")+"</b>";
      }}),
    xAxis:{type:"category",data:rows.map(label),
           axisLabel:{color:b._muted,fontSize:9,rotate:55},
           axisLine:{lineStyle:{color:b._grid}}},
    yAxis:[{type:"value",name:"ج.م",nameTextStyle:{color:b._muted,fontSize:9},
            axisLabel:{color:b._muted,fontSize:9,formatter:v=>(v/1e6).toFixed(1)+"M"},
            splitLine:{lineStyle:{color:b._grid}}},
           {type:"value",name:"%",min:0,max:60,nameTextStyle:{color:b._muted,fontSize:9},
            axisLabel:{color:b._muted,fontSize:9},splitLine:{show:false}}],
    series:[
      {name:"صافي المبيعات",type:"bar",barGap:"-30%",
       data:rows.map(r=>({value:r.net_sales,
         itemStyle:{color:est(r)?"rgba(59,130,246,.38)":"#3b82f6"}}))},
      {name:"تكلفة المبيعات",type:"bar",
       data:rows.map(r=>({value:r.cogs,
         itemStyle:{color:est(r)?"rgba(239,68,68,.32)":"rgba(239,68,68,.62)"}}))},
      {name:"هامش مجمل %",type:"line",yAxisIndex:1,smooth:true,symbolSize:6,
       data:rows.map(r=>({value:r.gross_margin_pct,
         itemStyle:{color:est(r)?WARN:OK}})),
       lineStyle:{color:OK,width:2}},
    ],
  });
}

/* Headline: the reliable window (measured June + the indicative months that
   pass the gate). This is the widest span the data can honestly support. */
function kpisWindow(d, R){
  const m=d.totals.measured||{}, i=d.totals.indicative||{};
  const rev=(m.revenue_costed||0)+(i.revenue_costed||0);
  const gp=(m.gross_profit||0)+(i.gross_profit||0);
  const op=(m.op_profit||0)+(i.op_profit||0);
  const gm=rev?gp/rev*100:null, om=rev?op/rev*100:null;
  return [
    ["هامش مجمل", R.fmtPct(gm), windowLabel(d), marginColour(gm, m.gross_margin_pct)],
    ["هامش تشغيلي", R.fmtPct(om), "بعد تحميل المصروفات", marginColour(om, m.op_margin_pct)],
    ["مجمل الربح", R.fmtEGP(gp), "الإيراد − تكلفة المبيعات", R.C.blue],
    ["الربح التشغيلي", R.fmtEGP(op), "بعد التحويل والمصروفات", R.C.indigo],
    ["تغطية التكلفة", R.fmtPct(d.meta.coverage_pct),
     d.meta.n_items_costed+" صنفًا من "+d.meta.n_items_total, R.C.green],
    ["إيراد غير مُسعَّر", R.fmtEGP(d.meta.revenue_uncosted),
     "لا تُحتسب له تكلفة صفرية", WARN],
  ];
}

/* The measured month on its own — the row that ties to the income statement. */
function kpisMeasured(d, R){
  const m=d.totals.measured||{};
  return [
    ["هامش مجمل — مقيس", R.fmtPct(m.gross_margin_pct), arMonth(d.meta.cost_month), OK],
    ["هامش تشغيلي — مقيس", R.fmtPct(m.op_margin_pct), "مطابق لقائمة الدخل", OK],
    ["مجمل الربح", R.fmtEGP(m.gross_profit), arMonth(d.meta.cost_month), R.C.blue],
    /* Title and sub-line name two different accounting concepts for one number.
       They coincide in June because the full loaded cost absorbs every expense
       line the statement carries, so op_profit lands exactly on its net profit.
       That is a fact about this month, not a general identity. */
    ["الربح التشغيلي", R.fmtEGP(m.op_profit),
     "يطابق صافي الربح في قائمة الدخل", R.C.indigo],
  ];
}

/* ----------------------------------------------------------------- charts -- */

/* Margin trend across every month. Months that fail the gate are still drawn —
   hiding them would hide the price step that causes them — but greyed, with the
   reliable window marked, so nobody reads the 2025 dip as a trading loss. */
function trend(d, C){
  const rows=(d.by_month||[]).slice().sort((a,b)=>a.month<b.month?-1:1);
  if(!rows.length) return {__empty:true};
  const months=rows.map(r=>arMonth(r.month));
  const ok=r=>r.indicative_reliable||r.basis==="measured";
  const b=C.ecBase();
  const first=rows.findIndex(ok);

  return Object.assign(b, {
    legend:Object.assign(b.legend,{data:["هامش مجمل %","هامش تشغيلي %","مؤشر الأسعار"]}),
    grid:{left:6,right:10,top:34,bottom:6,containLabel:true},
    tooltip:Object.assign(b.tooltip,{trigger:"axis",
      formatter:ps=>{
        const r=rows[ps[0].dataIndex];
        return "<b>"+arMonth(r.month)+"</b><br>"
          +(ok(r)?"":"<span style='color:"+WARN+"'>خارج النافذة الموثوقة</span><br>")
          +ps.map(p=>p.marker+" "+p.seriesName+": <b>"+(p.value==null?"—":Number(p.value).toFixed(1))+"</b>").join("<br>")
          +"<br>انحراف السعر عن شهر التكلفة: <b>"+(r.cost_period_drift_pct==null?"—":r.cost_period_drift_pct.toFixed(1)+"%")+"</b>";
      }}),
    xAxis:{type:"category",data:months,axisLabel:{color:b._muted,fontSize:9,rotate:55},
           axisLine:{lineStyle:{color:b._grid}}},
    yAxis:[{type:"value",name:"%",nameTextStyle:{color:b._muted,fontSize:9},
            axisLabel:{color:b._muted,fontSize:9},splitLine:{lineStyle:{color:b._grid}}},
           {type:"value",name:"مؤشر",min:70,max:110,nameTextStyle:{color:b._muted,fontSize:9},
            axisLabel:{color:b._muted,fontSize:9},splitLine:{show:false}}],
    series:[
      {name:"هامش مجمل %",type:"line",smooth:true,symbolSize:5,
       data:rows.map(r=>({value:r.gross_margin_pct,
         itemStyle:{color:ok(r)?"#3b82f6":"#475569"}})),
       lineStyle:{color:"#3b82f6",width:2},
       markArea:first>=0?{silent:true,itemStyle:{color:"rgba(16,185,129,.07)"},
         data:[[{xAxis:months[first],name:"النافذة الموثوقة"},{xAxis:months[months.length-1]}]]}:undefined},
      {name:"هامش تشغيلي %",type:"line",smooth:true,symbolSize:5,
       data:rows.map(r=>({value:r.op_margin_pct,
         itemStyle:{color:ok(r)?"#10b981":"#475569"}})),
       lineStyle:{color:"#10b981",width:2},
       markLine:{silent:true,symbol:"none",lineStyle:{color:"rgba(255,255,255,.18)",type:"dashed"},
                 data:[{yAxis:0}]}},
      {name:"مؤشر الأسعار",type:"line",yAxisIndex:1,smooth:true,symbol:"none",
       data:rows.map(r=>r.price_index),
       lineStyle:{color:WARN,width:1,type:"dotted"}},
    ],
  });
}

/* Revenue against gross margin, one bubble per item. The quadrant that matters
   is high revenue with low margin — volume earning little. */
function itemScatter(d, C, R){
  const rows=(d.by_item||[]).filter(r=>r.gross_margin_pct!=null && r.revenue_costed>0);
  if(!rows.length) return {__empty:true};
  const b=C.ecBase();
  const mx=Math.max.apply(null,rows.map(r=>r.revenue_costed));
  return Object.assign(b,{
    grid:{left:6,right:14,top:20,bottom:6,containLabel:true},
    tooltip:Object.assign(b.tooltip,{formatter:p=>{
      const r=p.data.r;
      return "<b>"+r.item_name+"</b><br>العلامة: "+(r.brand||"—")
        +"<br>الإيراد: <b>"+Math.round(r.revenue_costed).toLocaleString("en")+"</b>"
        +"<br>هامش مجمل: <b>"+r.gross_margin_pct.toFixed(1)+"%</b>"
        +"<br>هامش تشغيلي: <b>"+(r.op_margin_pct==null?"—":r.op_margin_pct.toFixed(1)+"%")+"</b>";
    }}),
    /* No axis names: at 390px an Arabic axis title clips against the grid and
       costs more room than it explains. The card subtitle carries the reading
       instead, and the tooltip names every value. */
    xAxis:{type:"value",axisLabel:{color:b._muted,fontSize:9,
             formatter:v=>(v/1e6).toFixed(1)+"M"},
           splitLine:{lineStyle:{color:b._grid}}},
    yAxis:{type:"value",axisLabel:{color:b._muted,fontSize:9,formatter:v=>v+"%"},
           splitLine:{lineStyle:{color:b._grid}}},
    /* symbolSize receives the raw [x, y] value, not the data object, so size
       is taken from x (revenue) rather than from the attached row. */
    series:[{type:"scatter",
      symbolSize:v=>8+Math.sqrt(Math.max(v[0],0)/mx)*22,
      data:rows.map(r=>({value:[r.revenue_costed,r.gross_margin_pct],r,
        itemStyle:{color:R.BRAND_COLORS[r.brand]||"#3b82f6",opacity:.75}}))}],
  });
}

/* ------------------------------------------------------------------ lists -- */

/* Brands keep their own identity colours; everything else is graded red/amber/
   green against the measured month, so a weak representative is visible at a
   glance instead of every bar being the same colour. */
const bars = (rows, keyName, R, ref) => rows
  .filter(r=>r.gross_margin_pct!=null)
  .sort((a,b)=>b.gross_margin_pct-a.gross_margin_pct)
  .map(r=>[r[keyName], r.gross_margin_pct,
           R.BRAND_COLORS[r[keyName]] || marginColour(r.gross_margin_pct, ref)]);

/* Items whose realised price sits below what the costing model recommends.
   Straight from the model's own pricing engine — not re-derived here. */
const pricingGap = d => (d.pricing_gap||[]).slice(0, 12);

/* --------------------------------------------- level 3 · monthly, per cut -- */

/* Absent from any build made before the calibration landed, so — like level 1
   — every use is guarded rather than assumed. */
const hasCal = () => !!(has() && window.DASH_MARGIN.calibration);
const CAL    = () => window.DASH_MARGIN.calibration;

/* Months carrying a calibrated figure, newest first: the picker opens on the
   most recent month, which is the one a reader is asking about. */
const calMonths = () => (hasCal() ? (CAL().months||[]).slice().reverse() : []);

/* What a single row's basis means, in words, wherever it is shown. The string
   is identical in the app and in the exported workbook on purpose — a reader
   comparing the two must not have to decide whether they mean the same thing. */
function basisLabel(r){
  if(!r) return "";
  if(r.basis==="measured") return "مقيس";
  return r.estimated ? "معايَر — تقديري (الربع الأول)" : "معايَر على قائمة الدخل";
}

/* One dimension's rows for one month, biggest revenue first. */
function calRows(key, month){
  if(!hasCal()) return [];
  return (D()[key]||[]).filter(r=>r.month===month);
}

/* The extremes of a month, which is what the reader is actually scanning for.
   Rows below a revenue floor are dropped: a customer with one small invoice
   can post a 90% margin that says nothing about anything. */
function calExtremes(key, month, nameOf, minRevenue){
  const rows=calRows(key,month).filter(r=>r.gross_margin_pct!=null
                                       && r.revenue>=(minRevenue||0));
  if(rows.length<2) return null;
  const s=rows.slice().sort((a,b)=>b.gross_margin_pct-a.gross_margin_pct);
  return {top:s[0], bottom:s[s.length-1], n:rows.length,
          topName:nameOf(s[0]), bottomName:nameOf(s[s.length-1])};
}


/* ==================================================================== المصروفات
   The expense side of the same statements, category by category and line by
   line.

   Level 1 above shows what the company spent as ONE number per month. Every
   one of the eleven statements carries the detail behind that number, and the
   app never showed it.

   FOUR CATEGORIES, AND WHERE THEY COME FROM

   From May 2026 the statements print four expense groups themselves —
   تشغيلية · إدارية وعمومية · بيعية وتسويقية · تمويلية. Those three months need
   no interpretation: every line is drawn where the accountant put it. The
   earlier statements print three, because what they call «إدارية وعمومية» is
   later split into an operating group and a smaller administrative one; their
   selling and financing groups are the same two categories under the same
   names and carry over untouched.

   So each item says how it reached its category — stated · mapped · unsplit ·
   as_filed — and the reading is on screen, not buried in a script.

   Three things this deliberately does NOT do:
     · It never divides a line the statement did not divide. One earlier rent
       line covers operating and administrative rent both; it stays where it
       was filed and is flagged, rather than split by a ratio nobody measured.
     · It never draws a zero for a month with no statement. August 2026 filed
       none; the coverage card says so in words.
     · It never hides a renaming. Items are grouped under a canonical name so a
       reader can follow «مرتبات» across eleven statements, and both the alias
       table and the category decisions are shown. */

const hasExp = () => !!(hasStmt() && S().expenses);
const EXP    = () => S().expenses;

/* One row per STATEMENT, not per month: 2026-Q1 arrived as a single quarterly
   document, so its items describe three months at once and are shown as such
   rather than attributed to a month that never had a breakdown. */
const expStatements = () => (EXP().by_statement) || [];

const CAT_ORDER = () => ((EXP().categories || {}).order) ||
                        ["operating", "admin", "selling", "financing"];
const CAT_AR = c => (((EXP().categories || {}).labels) || {})[c] || c;
const CAT_COL = {operating: "#10b981", admin: "#8b5cf6",
                 selling: "#3b82f6", financing: "#f59e0b"};

/* How an item reached its category, in the reader's words. */
const BASIS_AR = {
  stated: "الفئة من القائمة نفسها",
  mapped: "الفئة منقولة — من موضع الاسم نفسه في قوائم الفئات الأربع",
  unsplit: "بند واحد يغطي فئتين ولم تفصله القائمة — بقي كما قُيّد",
  as_filed: "لا شاهد ينقله — بقي في المجموعة التي قيّدته",
};

/* The items of one statement, or of all of them when period is falsy.
   Grouped by (category, canonical label) — the pair, never the label alone: an
   administrative «مرتبات» and a selling «مرتبات» are different money. */
function expItems(period){
  const rows=expStatements().filter(r=>!period || r.period===period);
  const m=new Map();
  for(const r of rows){
    for(const it of r.expense_items||[]){
      const k=it.category+" "+it.label;
      let a=m.get(k);
      if(!a){ a={category:it.category, label:it.label, total:0, months:{},
                 raws:new Set(), groups:new Set(), basis:new Set(), note:null};
              m.set(k,a); }
      a.total += it.amount||0;
      a.months[r.period] = (a.months[r.period]||0) + (it.amount||0);
      a.raws.add(it.label_raw);
      a.groups.add(it.group);
      a.basis.add(it.category_basis);
      if(it.note) a.note = it.note;
    }
  }
  const out=[...m.values()];
  const grand=out.reduce((x,a)=>x+a.total,0);
  for(const a of out){
    a.n_months = Object.keys(a.months).length;
    a.avg = a.n_months ? a.total/a.n_months : null;
    a.share = grand ? a.total/grand*100 : null;
    a.variants = [...a.raws].filter(v=>v!==a.label);
    /* The weakest basis the item was read on: an item that is "stated" in
       three statements and "mapped" in eight is a mapped item to the reader. */
    a.worst = ["as_filed","unsplit","mapped","stated"]
      .find(b=>a.basis.has(b)) || "stated";
  }
  return out.sort((x,y)=>y.total-x.total);
}

/* The request itself: each main category, then the lines inside it. */
function expByCategory(period){
  const items=expItems(period);
  return CAT_ORDER().map(c=>{
    const mine=items.filter(i=>i.category===c);
    const total=mine.reduce((a,i)=>a+i.total,0);
    for(const i of mine) i.share_of_cat = total ? i.total/total*100 : null;
    return {category:c, label:CAT_AR(c), total:total, items:mine};
  }).filter(g=>g.items.length);
}

/* Headline figures, each counted from the rows rather than written down. */
function expKpis(R){
  const rows=S().by_month||[], t=S().totals, cov=EXP().coverage||{};
  const spend=rows.reduce((a,r)=>a+(r.total_expenses||0),0);
  const cats=expByCategory(null);
  const top=cats.slice().sort((a,b)=>b.total-a.total)[0];
  const item=expItems(null)[0];
  return [
    ["إجمالي المصروفات", R.fmtEGP(spend),
     t.months+" شهرًا · "+arMonth(t.period_from)+" – "+arMonth(t.period_to),
     CAT_COL.admin],
    ["متوسط شهري", R.fmtEGP(rows.length?spend/rows.length:0),
     "على مدى السلسلة", R.C.indigo],
    ["نسبتها من صافي المبيعات", R.fmtPct(t.net_sales?spend/t.net_sales*100:null),
     "مصروفات التشغيل وحدها", R.C.blue],
    ["أكبر فئة", top?top.label.replace("مصروفات ",""):"—",
     top?R.fmtEGP(top.total):"", top?CAT_COL[top.category]:R.C.grey],
    ["أكبر بند", item?item.label:"—",
     item?R.fmtEGP(item.total)+" · "+CAT_AR(item.category).replace("مصروفات ",""):"",
     CAT_COL.selling],
    ["قوائم بتفصيل بالبند",
     String(cov.statements_with_item_detail||0)+" من "+(cov.statements||0),
     (cov.n_items||0)+" سطر بند", R.C.green],
  ];
}

/* Monthly columns, stacked by the four categories where they are known and
   drawn as a single grey column where only a total is. The grey is the point:
   a month whose breakdown does not exist must not look like a month whose
   breakdown happens to be flat. */
function expStack(C){
  const rows=(S().by_month||[]).slice().sort((a,b)=>a.period<b.period?-1:1);
  if(!rows.length) return {__empty:true};
  const b=C.ecBase();
  const order=CAT_ORDER();
  const names=order.map(CAT_AR).concat(["إجمالي فقط"]);
  const series=order.map((c,i)=>({
    name:names[i], type:"bar", stack:"e",
    data:rows.map(r=>r.categories?(r.categories[c]||0):null),
    itemStyle:{color:CAT_COL[c]||"#64748b"}}));
  series.push({name:"إجمالي فقط", type:"bar", stack:"e",
    data:rows.map(r=>r.categories?null:(r.total_expenses||0)),
    itemStyle:{color:"rgba(148,163,184,.45)"}});

  return Object.assign(b,{
    legend:Object.assign(b.legend,{data:names}),
    grid:{left:6,right:10,top:44,bottom:6,containLabel:true},
    tooltip:Object.assign(b.tooltip,{trigger:"axis",
      formatter:ps=>{
        const r=rows[ps[0].dataIndex];
        return "<b>"+arMonth(r.period)+"</b><br>"
          +(r.categories?"":"<span style='color:"+WARN+"'>لا يوجد تفصيل بالبند لهذا الشهر — إجمالي فقط</span><br>")
          +(r.basis==="allocated"?"<span style='color:"+WARN+"'>موزّع تناسبيًا من قائمة الربع الأول</span><br>":"")
          +ps.filter(p=>p.value!=null).map(p=>p.marker+" "+p.seriesName+": <b>"
              +Number(p.value).toLocaleString("en",{maximumFractionDigits:0})
              +"</b>").join("<br>")
          +"<br>الإجمالي: <b>"+Number(r.total_expenses||0)
              .toLocaleString("en",{maximumFractionDigits:0})+"</b>";
      }}),
    xAxis:{type:"category",data:rows.map(r=>arMonth(r.period)),
           axisLabel:{color:b._muted,fontSize:9,rotate:55},
           axisLine:{lineStyle:{color:b._grid}}},
    yAxis:{type:"value",name:"ج.م",nameTextStyle:{color:b._muted,fontSize:9},
           axisLabel:{color:b._muted,fontSize:9,
                      formatter:v=>(v/1e3).toFixed(0)+"K"},
           splitLine:{lineStyle:{color:b._grid}}},
    series:series,
  });
}

/* Arabic counts a noun differently at 1, 2, 3–10 and 11+, and «قائمة» is not
   «شهر»: reusing the month counter and patching its output with string
   replacement produced «11 قائمة» by luck and «قائمتان» never. */
const arDocs = n => n === 1 ? "قائمة واحدة" : n === 2 ? "قائمتين"
                  : n < 11 ? n + " قوائم" : n + " قائمة";

const SECTION_EXP = {
  id:"expenses", label:"المصروفات", title:"المصروفات — أربع فئات وكل بند على حدة",
  sub:()=>{
    if(!hasExp()) return "المصروفات على أربع فئات، وكل فئة ببنودها.";
    const c=EXP().coverage||{};
    const st=((EXP().categories||{}).stated_periods)||[];
    return "أربع فئات رئيسية وكل فئة مفصَّلة ببنودها، من "+
      arDocs(c.statements_with_item_detail||0)+
      " تغطي "+T.arMonths(c.months_with_item_detail||0)+
      " · الفئات مُعلَنة في المصدر لـ"+T.arMonths(st.length)+
      " ومقروءة فيما عداها"+
      ((c.no_statement_periods||[]).length?
        " · أشهر بلا قائمة دخل: "+c.no_statement_periods.length:"")+".";
  }
};

return {SECTION, SECTION_EXP, has, D, hasStmt, S, kpisStatements, stmtTrend,
        hasExp, EXP, expStatements, expItems, expByCategory, arDocs,
        expKpis, expStack, CAT_ORDER, CAT_AR, CAT_COL, BASIS_AR,
        kpisWindow, kpisMeasured, trend, itemScatter, bars,
        pricingGap, windowLabel, arMonth, marginColour,
        hasCal, CAL, calMonths, calRows, calExtremes, basisLabel,
        OK, WARN, BAD, MUTED};
})();
