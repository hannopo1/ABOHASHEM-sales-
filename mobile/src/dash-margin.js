/* Abu Hashem — mobile runtime · الربحية (profitability).

   Reads window.DASH_MARGIN, emitted by analysis/13_join_cost_margin.py from the
   June-2026 costing model joined to sales invoices. Until that join existed the
   app could show revenue but never margin.

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

const SECTION = {
  id:"margin", label:"الربحية", title:"الربحية — التكلفة والهامش",
  sub:"مبنية على نموذج تكاليف يونيو 2026 المطابق لقائمة الدخل، مربوطًا بفواتير المبيعات. "+
      "النسب محسوبة على الإيراد المُسعَّر فقط، والشهور التي تبعد أسعارها عن شهر التكلفة مستبعدة."
};

const OK = "#10b981", WARN = "#f59e0b", BAD = "#ef4444", MUTED = "#64748b";

const has = () => !!(typeof window !== "undefined" && window.DASH_MARGIN);
const D   = () => window.DASH_MARGIN;

const arMonth = m => {
  if(!m) return "";
  const AR=["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
  const p=String(m).split("-");
  return AR[parseInt(p[1],10)-1]+" "+p[0];
};

/**
 * Formats the reliable month window as an Arabic month label or range.
 * @param {Object} d - Dashboard data containing the reliable months.
 * @return {string} The formatted month label, range, or `—` when no reliable months are available.
 */
function windowLabel(d){
  const r=(d.meta.reliable_months||[]).slice().sort();
  if(!r.length) return "—";
  return r.length===1 ? arMonth(r[0]) : arMonth(r[0])+" – "+arMonth(r[r.length-1]);
}

/**
 * Assigns a display color to a margin based on the measured-month benchmark.
 * @param {number|null} pct - The margin percentage to classify.
 * @param {number|null} ref - The measured-month margin percentage used as the benchmark.
 * @return {string} The display color for the margin.
 */
function marginColour(pct, ref){
  if(pct==null) return MUTED;
  if(ref==null) return OK;
  if(pct >= ref*0.95) return OK;
  if(pct >= ref*0.75) return WARN;
  return BAD;
}

/* ------------------------------------------------------------------- KPIs -- */

/**
 * Builds KPI rows for the measured period and approved indicative months.
 * @param {Object} d - Profitability data containing totals and metadata.
 * @return {Array} KPI rows with labels, formatted values, contextual descriptions, and display colors.
 */
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

/**
 * Builds KPI rows for the measured costing month.
 * @param {Object} d - Dashboard data containing measured totals and the costing month.
 * @return {Array} KPI rows for measured gross margin, operating margin, gross profit, and operating profit.
 */
function kpisMeasured(d, R){
  const m=d.totals.measured||{};
  return [
    ["هامش مجمل — مقيس", R.fmtPct(m.gross_margin_pct), arMonth(d.meta.cost_month), OK],
    ["هامش تشغيلي — مقيس", R.fmtPct(m.op_margin_pct), "مطابق لقائمة الدخل", OK],
    ["مجمل الربح", R.fmtEGP(m.gross_profit), arMonth(d.meta.cost_month), R.C.blue],
    ["الربح التشغيلي", R.fmtEGP(m.op_profit), "صافي الربح المُعلن", R.C.indigo],
  ];
}

/* ----------------------------------------------------------------- charts -- */

/**
 * Build the monthly margin and price-index trend chart.
 * @param {Object} d - Monthly profitability data.
 * @param {Object} C - Chart configuration and theme helpers.
 * @return {Object} The chart configuration, or an empty-state marker when monthly data is unavailable.
 */
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

/**
 * Builds a revenue-versus-gross-margin bubble chart for costed items.
 * @param {Object} d - Dashboard data containing item-level profitability records.
 * @param {Object} C - Chart configuration and theme helpers.
 * @return {Object} The configured scatter chart, or an empty-state marker when no qualifying items exist.
 */
function itemScatter(d, C){
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

return {SECTION, has, D, kpisWindow, kpisMeasured, trend, itemScatter, bars,
        pricingGap, windowLabel, arMonth, marginColour, OK, WARN, BAD, MUTED};
})();
