/* ============================================================================
   Abu Hashem — Executive Financial Dashboard · client runtime
   Reads window.DASH (pre-aggregated by build.py), renders every visualization
   with the vendored ECharts / Plotly, wires DataTables exports, cross-filtering,
   drill-through and theming. No backend, no network.
   ========================================================================== */
(function () {
"use strict";
const D = window.DASH;
if (!D) { document.body.innerHTML = "<p style='padding:40px'>data.js لم يُحمّل</p>"; return; }

/* ---- palette / formatters ------------------------------------------------ */
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
const MONTHLABEL = Object.fromEntries((D.meta.available_months||[]).map(m=>[m.v,m.l]));
const ALL_LABEL = D.meta.all_months_label || "جميع الشهور";
const DATA_MONTHS = new Set(D.meta.data_months || []);      // months carrying source data
const monthHasData = m => !m || m==="all" || DATA_MONTHS.has(m);
const monthName = ym => MONTHLABEL[ym] || ym;
// code -> display name (derived once from the line-level data)
const CUST_NAME = {}, ITEM_NAME = {};
D.lines.forEach(l => { CUST_NAME[l.customer_code] = l.customer_name; ITEM_NAME[l.item_code] = l.item_name; });
const curMonthLabel = () => {
  const m = (typeof state!=="undefined" && state.filters.month) || D.meta.default_month;
  if (!m || m==="all") return ALL_LABEL;
  return (MONTHLABEL[m] || m) + (monthHasData(m) ? "" : " — لا توجد بيانات");
};

/* ---- state --------------------------------------------------------------- */
const state = { filters:{month:(D.meta.default_month||"2026-06"),
  customer:"",rep:"",brand:"",item:"",status:"",aging:""}, section:"overview" };
const charts = {};                       // id -> echarts instance
const tables = {};                       // id -> DataTable
const isLight = () => document.body.getAttribute("data-theme") === "light";

/* ========================================================================== */
/*  CONTEXT — apply filters and recompute the aggregates the views consume     */
/* ========================================================================== */
function buildContext() {
  const f = state.filters;
  const mAll = !f.month || f.month === "all";
  let lines = D.lines.filter(l =>
    (mAll || l.month === f.month) &&
    (!f.customer || l.customer_code === f.customer) &&
    (!f.rep      || l.rep === f.rep) &&
    (!f.brand    || l.brand === f.brand) &&
    (!f.item     || l.item_code === f.item));
  const invSet = new Set(lines.map(l => l.invoice_no));
  let invoices = D.invoices.filter(v =>
    (mAll || v.month === f.month) &&
    (!f.customer || v.customer_code === f.customer) &&
    (!f.rep      || v.rep === f.rep) &&
    (!f.status   || v.status === f.status) &&
    ((!f.brand && !f.item) || invSet.has(v.invoice_no)));
  if (f.status) { const s = new Set(invoices.map(v => v.invoice_no)); lines = lines.filter(l => s.has(l.invoice_no)); }

  // Receivables is a fixed AR snapshot; narrow it to the month's active cohort.
  const active = new Set(invoices.map(v => v.customer_code));
  const recv = D.receivables.rows.filter(r =>
    (mAll || active.has(r.customer_code)) &&
    (!f.customer || r.customer_code === f.customer) &&
    (!f.rep      || r.rep === f.rep) &&
    (!f.aging    || r.bucket === f.aging));

  const customers = aggCustomers(lines, invoices);
  return { lines, invoices, recv, customers, products: aggProducts(lines),
           buckets: bucketsFromRows(recv),
           kpis: aggKpis(lines, invoices, recv, customers) };
}

/* Per-customer monthly aggregates joined with the fixed AR / bonus snapshot. */
function aggCustomers(lines, invoices) {
  const asOf = new Date(D.meta.as_of);
  const net = D.meta.net_terms_days;
  const m = new Map();
  for (const v of invoices) {
    let o = m.get(v.customer_code);
    if (!o) { o = { customer_code:v.customer_code, customer_name:v.customer_name,
      sales:0, collections:0, invs:new Set(), unpaid:[] }; m.set(v.customer_code, o); }
    o.sales += v.reported_total||0; o.collections += v.paid||0; o.invs.add(v.invoice_no);
    if (v.remaining>0 && v.reported_total>0) o.unpaid.push(v);
  }
  const lm = new Map();
  for (const l of lines) {
    let o = lm.get(l.customer_code);
    if (!o) { o = { units:0, boxes:0, items:new Set() }; lm.set(l.customer_code, o); }
    o.units += l.qty||0; o.boxes += l.boxes||0; o.items.add(l.item_code);
  }
  const rows = [...m.values()].map(o => {
    const ar = D.customer_ar[o.customer_code] || {};
    const l = lm.get(o.customer_code) || { units:0, boxes:0, items:new Set() };
    const nInv = o.invs.size;
    const rec = {
      customer_code:o.customer_code, customer_name:o.customer_name,
      rep: ar.rep || "غير محدد", city: ar.city || "",
      sales: round2(o.sales), collections: round2(o.collections),
      n_invoices: nInv, n_items: l.items.size, units: round2(l.units), boxes: round2(l.boxes),
      avg_invoice_value: nInv ? round2(o.sales/nInv) : 0,
      total_billed: ar.total_billed != null ? ar.total_billed : round2(o.sales),
      outstanding: ar.outstanding != null ? ar.outstanding : null,
      collection_rate: ar.collection_rate != null ? ar.collection_rate : null,
      bonus_pct: ar.bonus_pct || 0, has_ar: !!ar.has_ar,
    };
    rec.bonus_value = round2(o.sales * rec.bonus_pct);
    if (o.unpaid.length) {
      o.unpaid.sort((a,b)=>a.invoice_date<b.invoice_date?-1:1);
      const u = o.unpaid[0]; const due = new Date(u.invoice_date); due.setDate(due.getDate()+net);
      rec.oldest_invoice_no = u.invoice_no; rec.oldest_invoice_date = u.invoice_date;
      rec.oldest_due_date = due.toISOString().slice(0,10);
      rec.oldest_days_overdue = Math.max(0, Math.round((asOf-due)/864e5));
      rec.oldest_amount = round2(u.remaining);
    }
    return rec;
  }).sort((a,b)=>b.sales-a.sales);
  rows.forEach((r,i)=>r.rank=i+1);
  return rows;
}

/* Aging buckets recomputed from the (filtered) AR rows — keeps the chart in
   sync with the month / cross-filter selection. */
function bucketsFromRows(rows) {
  const b = { current:0, d1_30:0, d31_60:0, d61_90:0, d91_120:0, d120p:0 };
  for (const r of rows) { b.current += r.current||0; if (r.overdue>0) b[r.bucket] += r.overdue||0; }
  return b;
}
const round2 = x => Math.round((x||0)*100)/100;

function aggKpis(lines, invoices, recv, customers) {
  const total_sales = sum(invoices, "reported_total");
  const net_sales = sum(lines, "line_total");
  const qty = sum(lines, "qty");
  const boxes = lines.reduce((a,l)=>a+(l.boxes||0),0);
  const priced = lines.filter(l => l.qty>0 && l.line_total>0);
  const asp = priced.length ? sum(priced,"line_total")/sum(priced,"qty") : 0;
  const outstanding = sum(recv,"outstanding"), overdue = sum(recv,"overdue");
  const billed = customers.reduce((a,c)=>a+(c.total_billed||0),0);
  const cust_out = customers.reduce((a,c)=>a+(c.outstanding||0),0);
  const collection_rate = billed ? Math.max(0,Math.min(1,(billed-cust_out)/billed)) : 0;
  const nInv = new Set(invoices.map(v=>v.invoice_no)).size;
  return {
    total_sales, net_sales, qty, boxes, asp, outstanding, overdue, collection_rate,
    collections_at_issue: sum(invoices,"paid"),
    n_invoices: nInv,
    n_customers: new Set(invoices.map(v=>v.customer_code)).size,
    zero_invoices: invoices.filter(v=>!v.reported_total).length,
    avg_invoice_value: nInv ? total_sales/nInv : 0,
  };
}

function aggProducts(lines) {
  const m = new Map();
  const grand = sum(lines,"line_total") || 1;
  for (const l of lines) {
    let o = m.get(l.item_code);
    if (!o) { o={item_code:l.item_code,item_name:l.item_name,brand:l.brand,sales:0,qty:0,boxes:0,
                 cust:new Set(),n_lines:0,prices:[]}; m.set(l.item_code,o); }
    o.sales+=l.line_total||0; o.qty+=l.qty||0; o.boxes+=l.boxes||0; o.n_lines++;
    o.cust.add(l.customer_code); if(l.unit_price>0) o.prices.push(l.unit_price);
  }
  const rows=[...m.values()].map(o=>{
    const pr=o.prices;
    return {item_code:o.item_code,item_name:o.item_name,brand:o.brand,sales:o.sales,qty:o.qty,
      boxes:o.boxes,n_customers:o.cust.size,n_lines:o.n_lines,
      max_price:pr.length?Math.max(...pr):null,min_price:pr.length?Math.min(...pr):null,
      asp:o.qty?o.sales/o.qty:0,contribution_pct:o.sales/grand*100,prices:pr};
  }).sort((a,b)=>b.sales-a.sales);
  rows.forEach((r,i)=>r.rank=i+1);
  return rows;
}
const sum = (arr,k) => arr.reduce((a,x)=>a+(x[k]||0),0);
function groupSum(arr,key,val){const m=new Map();for(const x of arr){const k=x[key];m.set(k,(m.get(k)||0)+(x[val]||0));}return m;}

/* ========================================================================== */
/*  ECharts helpers                                                            */
/* ========================================================================== */
function ecBase() {
  const ink = isLight() ? "#0f172a" : "#e2e8f0";
  const muted = isLight() ? "#475569" : "#94a3b8";
  const grid = isLight() ? "rgba(15,23,42,.08)" : "rgba(255,255,255,.06)";
  return {
    color: PAL,
    textStyle:{fontFamily:"Cairo, sans-serif",color:ink},
    grid:{left:14,right:18,top:34,bottom:24,containLabel:true},
    tooltip:{backgroundColor:isLight()?"#fff":"#0d1220",borderColor:grid,
      textStyle:{color:ink,fontFamily:"Cairo"},confine:true},
    legend:{textStyle:{color:muted},top:4,type:"scroll"},
    _ink:ink,_muted:muted,_grid:grid,
  };
}
function ec(id, option) {
  const el = document.getElementById(id);
  if (!el) return;
  let c = charts[id];
  if (c) { c.dispose(); }
  c = echarts.init(el, null, {renderer:"canvas"});
  c.setOption(option);
  charts[id] = c;
  return c;
}
function axis(base, opt) { // shared cartesian axis styling
  const st = {axisLine:{lineStyle:{color:base._grid}},axisLabel:{color:base._muted},
    splitLine:{lineStyle:{color:base._grid}},axisTick:{show:false}};
  return Object.assign({}, st, opt);
}
window.addEventListener("resize", () => Object.values(charts).forEach(c=>c&&c.resize()));

/* ========================================================================== */
/*  Insight box                                                                */
/* ========================================================================== */
function insight(key) {
  // Months with no source data carry no insights — show nothing rather than
  // falling back to another period's commentary.
  const mk = state.filters.month;
  const set = (mk && mk !== "all") ? D.insights_by_month[mk] : D.insights_by_month["all"];
  if (!set) return "";
  const it = set[key];
  if (!it) return "";
  const p = it.priority.includes("عالية")?"p-high":it.priority.includes("متوسطة")?"p-med":"p-low";
  const row = (k,v)=>`<div class="row"><span class="k">${k}:</span><span>${v}</span></div>`;
  return `<div class="insight ${p}">
    <div class="insight-head"><h4>${it.title}</h4><span class="prio ${p}">أولوية ${it.priority}</span></div>
    <div class="insight-grid">
      ${row("ماذا حدث",it.what)}${row("لماذا",it.why)}
      ${row("المخاطر",it.risk)}${row("الفرص",it.opportunity)}
      <div class="row" style="grid-column:1/-1"><span class="k">الإجراء الموصى به:</span><span>${it.action}</span></div>
    </div></div>`;
}

/* ========================================================================== */
/*  Card factory                                                               */
/* ========================================================================== */
function card(o) { // {id,title,sub,cls,tall,short,approx,insightKey,plotly}
  const tools = o.noPng ? "" :
    `<button class="mini-btn" data-png="${o.id}">PNG ⤓</button>`;
  const approx = o.approx ? `<span class="tag-approx">تقديري</span>` : "";
  const h = o.short?"short":o.tall?"tall":"";
  const chartEl = o.plotly ? `<div id="${o.id}" class="echart ${h}"></div>`
                           : `<div id="${o.id}" class="echart ${h}"></div>`;
  return `<div class="card ${o.cls||""}">
    <div class="card-head"><div><h3>${o.title}${approx}</h3>${o.sub?`<span class="sub">${o.sub}</span>`:""}</div>
      <div class="card-tools">${tools}</div></div>
    ${chartEl}
    ${o.insightKey?`<div class="ins-slot" data-ins="${o.insightKey}"></div>`:""}</div>`;
}
function tableCard(o) { // {id,title,approx}
  return `<div class="card span-2">
    <div class="card-head"><div><h3>${o.title}${o.approx?'<span class="tag-approx">تقديري</span>':''}</h3>
      ${o.sub?`<span class="sub">${o.sub}</span>`:""}</div></div>
    <div class="tbl-wrap"><table id="${o.id}" class="display" style="width:100%"></table></div>
    ${o.insightKey?`<div class="ins-slot" data-ins="${o.insightKey}"></div>`:""}</div>`;
}
/* Refresh all insight slots in the active section for the current month. */
function paintInsights(){
  document.querySelectorAll(".section.active .ins-slot").forEach(el=>{
    el.innerHTML = insight(el.dataset.ins);
  });
}

/* ========================================================================== */
/*  KPI cards                                                                  */
/* ========================================================================== */
const KPI_ICONS = {
  sales:'<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>', money:'<path d="M12 1v22"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
  users:'<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>',
  doc:'<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/>',
  box:'<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8"/><path d="M3.3 7L12 12l8.7-5"/>',
  pct:'<path d="M19 5L5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  warn:'<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
  clock:'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
};
function kpiCard(icon, val, label, accent, sub, subCls, delay) {
  return `<div class="kpi-card" style="--accent:${accent};animation-delay:${delay}s">
    <div class="kpi-ico"><svg viewBox="0 0 24 24" class="ic">${KPI_ICONS[icon]}</svg></div>
    <div class="kpi-val num">${val}</div><div class="kpi-lbl">${label}</div>
    ${sub?`<div class="kpi-sub ${subCls||""}">${sub}</div>`:""}</div>`;
}
function kpiGrid(k) {
  const mon = Object.fromEntries(D.monthly.map(m=>[m.month,m.net_sales]));
  const keys = D.monthly.map(m=>m.month);
  const cm = (state.filters.month && state.filters.month!=="all") ? state.filters.month : null;
  let salesSub="", salesCls="";
  if (cm) {
    const idx = keys.indexOf(cm), prevK = idx>0?keys[idx-1]:null;
    const prev = prevK?mon[prevK]:0, dv = prev?(k.total_sales-prev)/prev:0;
    salesSub = prevK ? (dv>=0?"▲ ":"▼ ")+pct(Math.abs(dv))+" مقابل "+monthName(prevK) : "";
    salesCls = dv>=0?"up":"down";
  } else { salesSub = "كل شهور ٢٠٢٦"; salesCls = "na"; }
  let i=0; const d=()=>0.04*(i++);
  return `<div class="kpi-grid">
    ${kpiCard("sales",egpK(k.total_sales),"إجمالي المبيعات","#3b82f6",salesSub,salesCls,d())}
    ${kpiCard("money",egpK(k.net_sales),"صافي المبيعات","#8b5cf6","","",d())}
    ${kpiCard("money",egpK(k.collections_at_issue),"التحصيل عند الإصدار","#06b6d4","بيع آجل","na",d())}
    ${kpiCard("money",egpK(k.outstanding),"المديونية القائمة","#f59e0b","لقطة "+D.meta.as_of,"na",d())}
    ${kpiCard("warn",egpK(k.overdue),"المتأخرات","#ef4444","تقديري","na",d())}
    ${kpiCard("pct",pct(k.collection_rate),"معدل التحصيل التراكمي","#10b981","","up",d())}
    ${kpiCard("money",egp(k.asp),"متوسط سعر البيع/وحدة","#c4b5fd","","",d())}
    ${kpiCard("box",int(k.qty),"إجمالي الكمية","#34d399","","",d())}
    ${kpiCard("box",int(k.boxes),"إجمالي الكراتين","#f97316","","",d())}
    ${kpiCard("users",int(k.n_customers),"عدد العملاء","#3b82f6","","",d())}
    ${kpiCard("doc",int(k.n_invoices),"عدد الفواتير","#8b5cf6","متوسط "+egpK(k.avg_invoice_value),"na",d())}
    ${kpiCard("warn",int(k.zero_invoices),"فواتير صفرية","#ef4444","بونص/عيّنات","na",d())}
    ${kpiCard("pct","غير متاح","هامش الربح الإجمالي","#64748b","لا توجد تكلفة","na",d())}
  </div>`;
}

/* ========================================================================== */
/*  Chart builders (each takes context D-like `X`)                             */
/* ========================================================================== */
function chMonthly(id,X){const b=ecBase();const rows=D.monthly.filter(m=>m.month>="2025-01");
  const cm=(state.filters.month&&state.filters.month!=="all")?state.filters.month:null;
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    xAxis:axis(b,{type:"category",data:rows.map(r=>r.month)}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"line",smooth:true,data:rows.map(r=>Math.round(r.net_sales)),
      areaStyle:{opacity:.22},lineStyle:{width:3,color:PAL[0]},itemStyle:{color:PAL[0]},
      markPoint:{data:[{type:"max",name:"الأعلى"}]},
      markLine:cm?{symbol:"none",data:[{xAxis:cm}],lineStyle:{color:PAL[3],type:"dashed",width:2},
        label:{show:true,color:b._muted,formatter:"الشهر المحدد"}}:undefined}]});}

function chDaily(id,X){const b=ecBase();
  const m=groupSum(X.invoices,"invoice_date","reported_total");
  const c=groupSum(X.invoices,"invoice_date","paid");
  const days=[...m.keys()].sort();
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    legend:{...b.legend,data:["المبيعات","التحصيل"]},
    xAxis:axis(b,{type:"category",data:days.map(d=>d.slice(5))}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[
      {name:"المبيعات",type:"line",smooth:true,areaStyle:{opacity:.2},lineStyle:{width:2.5,color:PAL[0]},
        itemStyle:{color:PAL[0]},data:days.map(d=>Math.round(m.get(d)))},
      {name:"التحصيل",type:"bar",itemStyle:{color:PAL[2]},data:days.map(d=>Math.round(c.get(d)||0))}]});}

function chTopCustomers(id,X,n){const b=ecBase();
  const cs=[...X.customers].sort((a,b2)=>b2.sales-a.sales).slice(0,n||20).reverse();
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    grid:{...b.grid,left:8},
    xAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    yAxis:axis(b,{type:"category",data:cs.map(c=>c.customer_name)}),
    series:[{type:"bar",data:cs.map(c=>Math.round(c.sales)),itemStyle:{color:PAL[0],borderRadius:[0,6,6,0]},
      label:{show:false}}]}).on("click",p=>openDrill(cs[p.dataIndex].customer_code));}

function chTopProducts(id,X,n){const b=ecBase();
  const ps=X.products.slice(0,n||20).reverse();
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    xAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    yAxis:axis(b,{type:"category",data:ps.map(p=>p.item_name)}),
    series:[{type:"bar",data:ps.map(p=>Math.round(p.sales)),
      itemStyle:{color:PAL[1],borderRadius:[0,6,6,0]}}]});}

function chPareto(id,X){const b=ecBase();
  const cs=[...X.customers].sort((a,b2)=>b2.sales-a.sales);
  const total=sum(cs,"sales")||1; let cum=0;
  const cats=cs.map(c=>c.customer_name), bar=cs.map(c=>Math.round(c.sales));
  const line=cs.map(c=>{cum+=c.sales;return +(cum/total*100).toFixed(1);});
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis"},legend:{...b.legend,data:["المبيعات","التراكمي %"]},
    xAxis:axis(b,{type:"category",data:cats,axisLabel:{show:false}}),
    yAxis:[axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
           axis(b,{type:"value",max:100,axisLabel:{color:b._muted,formatter:"{value}%"},splitLine:{show:false}})],
    series:[{name:"المبيعات",type:"bar",data:bar,itemStyle:{color:PAL[0]}},
      {name:"التراكمي %",type:"line",yAxisIndex:1,data:line,smooth:true,lineStyle:{color:PAL[3],width:2.5},
       itemStyle:{color:PAL[3]},markLine:{data:[{yAxis:80,name:"80%"}],
       lineStyle:{color:PAL[4],type:"dashed"},label:{formatter:"80%",color:b._muted}}}]});}

function chAgingBar(id,X){const b=ecBase();const bk=X.buckets;const lab=D.receivables.bucket_labels;
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    xAxis:axis(b,{type:"category",data:AGING_KEYS.map(k=>lab[k])}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"bar",data:AGING_KEYS.map(k=>Math.round(bk[k])),
      itemStyle:{color:p=>AGING_COLORS[AGING_KEYS[p.dataIndex]],borderRadius:[6,6,0,0]},
      label:{show:true,position:"top",color:b._muted,formatter:o=>egpK(o.value)}}]});}

function chAgingWaterfall(id,X){const b=ecBase();const bk=X.buckets;const lab=D.receivables.bucket_labels;
  let acc=0;const base=[],val=[];
  AGING_KEYS.forEach(k=>{base.push(acc);val.push(Math.round(bk[k]));acc+=bk[k];});
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",formatter:p=>{const i=p[1].dataIndex;
      return lab[AGING_KEYS[i]]+"<br/>"+egp(val[i]);}},
    xAxis:axis(b,{type:"category",data:AGING_KEYS.map(k=>lab[k])}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"bar",stack:"t",itemStyle:{color:"transparent"},data:base,silent:true},
      {type:"bar",stack:"t",data:val,itemStyle:{color:p=>AGING_COLORS[AGING_KEYS[p.dataIndex]],borderRadius:[4,4,0,0]}}]});}

function chByRep(id,X){const b=ecBase();
  const reps=[...X.recv.reduce((m,r)=>{const o=m.get(r.rep)||{c:0,o:0};o.c+=r.current;o.o+=r.overdue;m.set(r.rep,o);return m;},new Map())]
    .map(([rep,v])=>({rep,current:v.c,overdue:v.o,total:v.c+v.o})).sort((a,b2)=>b2.total-a.total);
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},legend:{...b.legend,data:["جاري","متأخرات"]},
    xAxis:axis(b,{type:"category",data:reps.map(r=>r.rep)}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{name:"جاري",type:"bar",stack:"s",data:reps.map(r=>Math.round(r.current)),itemStyle:{color:PAL[2]}},
      {name:"متأخرات",type:"bar",stack:"s",data:reps.map(r=>Math.round(r.overdue)),itemStyle:{color:PAL[4],borderRadius:[6,6,0,0]}}]});}

function chGauge(id,rate){const b=ecBase();
  ec(id,{...b,series:[{type:"gauge",startAngle:210,endAngle:-30,min:0,max:100,radius:"92%",
    progress:{show:true,width:16,itemStyle:{color:PAL[2]}},
    axisLine:{lineStyle:{width:16,color:[[.7,"#ef4444"],[.9,"#f59e0b"],[1,"#10b981"]]}},
    pointer:{width:5,itemStyle:{color:b._ink}},axisTick:{show:false},splitLine:{length:12,lineStyle:{color:b._muted}},
    axisLabel:{color:b._muted,fontSize:10,distance:-38},
    detail:{valueAnimation:true,formatter:"{value}%",color:b._ink,fontSize:26,offsetCenter:[0,"38%"]},
    title:{offsetCenter:[0,"68%"],color:b._muted,fontSize:12},
    data:[{value:+(rate*100).toFixed(1),name:"معدل التحصيل"}]}]});}

function chDonut(id,pairs,fmt){const b=ecBase();
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"item",valueFormatter:fmt||egp},
    series:[{type:"pie",radius:["48%","74%"],avoidLabelOverlap:true,itemStyle:{borderColor:isLight()?"#fff":"#0d1220",borderWidth:2},
      label:{color:b._muted,formatter:"{b}: {d}%"},
      data:pairs.map((p,i)=>({name:p[0],value:Math.round(p[1]),itemStyle:{color:PAL[i%PAL.length]}}))}]});}

function chTreemap(id,X){const b=ecBase();
  const brands=new Map();
  X.lines.forEach(l=>{let br=brands.get(l.brand);if(!br){br={name:l.brand,children:new Map()};brands.set(l.brand,br);}
    br.children.set(l.item_name,(br.children.get(l.item_name)||0)+(l.line_total||0));});
  const data=[...brands.values()].map((br,i)=>({name:br.name,itemStyle:{color:PAL[i%PAL.length]},
    children:[...br.children].map(([n,v])=>({name:n,value:Math.round(v)}))}));
  ec(id,{...b,tooltip:{...b.tooltip,valueFormatter:egp},series:[{type:"treemap",roam:false,nodeClick:"zoomToNode",
    breadcrumb:{show:true,itemStyle:{color:"#1e293b",textStyle:{color:b._muted}}},
    label:{color:"#fff",fontFamily:"Cairo"},upperLabel:{show:true,height:22,color:"#fff"},
    levels:[{itemStyle:{gapWidth:2,borderColor:isLight()?"#fff":"#0a0e1a"}},{itemStyle:{gapWidth:1}}],data}]});}

function chBox(id,X){const b=ecBase();
  const items=X.products.filter(p=>p.prices&&p.prices.length>=3).slice(0,10);
  // manual five-number summary (vendored echarts build has no dataTool)
  const boxData=items.map(p=>{const s=[...p.prices].sort((a,c)=>a-c);
    const q=f=>s[Math.floor((s.length-1)*f)];return [s[0],q(.25),q(.5),q(.75),s[s.length-1]];});
  ec(id,{...b,tooltip:{...b.tooltip},xAxis:axis(b,{type:"category",data:items.map(p=>p.item_name),
      axisLabel:{color:b._muted,interval:0,rotate:35,fontSize:10}}),
    yAxis:axis(b,{type:"value",name:"سعر الوحدة",axisLabel:{color:b._muted}}),
    series:[{type:"boxplot",data:boxData,itemStyle:{color:"rgba(59,130,246,.25)",borderColor:PAL[0]}}]});}

function chScatter(id,X){const b=ecBase();
  const pts=X.customers.filter(c=>c.outstanding!=null).map(c=>[Math.round(c.sales),Math.round(c.outstanding),c.customer_name,c.collection_rate]);
  ec(id,{...b,tooltip:{...b.tooltip,formatter:p=>`${p.data[2]}<br/>مبيعات: ${egp(p.data[0])}<br/>مديونية: ${egp(p.data[1])}<br/>تحصيل: ${p.data[3]!=null?pct(p.data[3]):"—"}`},
    xAxis:axis(b,{type:"value",name:"مبيعات الفترة",axisLabel:{color:b._muted,formatter:egpK}}),
    yAxis:axis(b,{type:"value",name:"المديونية القائمة",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"scatter",symbolSize:d=>Math.max(8,Math.sqrt(d[0])/12),
      itemStyle:{color:p=>p.data[3]>=.9?PAL[2]:p.data[3]>=.7?PAL[3]:PAL[4],opacity:.75},data:pts}]});}

function chRadar(id,X){const b=ecBase();
  const top=[...X.customers].sort((a,c)=>c.sales-a.sales).slice(0,5);
  const max=k=>Math.max(...X.customers.map(c=>c[k]||0))||1;
  const ind=[{name:"المبيعات",max:max("sales")},{name:"الفواتير",max:max("n_invoices")},
    {name:"الأصناف",max:max("n_items")},{name:"الكمية",max:max("units")},{name:"معدل التحصيل",max:1}];
  ec(id,{...b,tooltip:{...b.tooltip},legend:{...b.legend,data:top.map(t=>t.customer_name)},
    radar:{indicator:ind,axisName:{color:b._muted,fontSize:11},splitLine:{lineStyle:{color:b._grid}},
      splitArea:{show:false},axisLine:{lineStyle:{color:b._grid}}},
    series:[{type:"radar",data:top.map((t,i)=>({name:t.customer_name,value:[t.sales,t.n_invoices,t.n_items,t.units,t.collection_rate||0],
      lineStyle:{color:PAL[i]},areaStyle:{opacity:.08,color:PAL[i]},itemStyle:{color:PAL[i]}}))}]});}

function chSunburst(id,X){const b=ecBase();
  const top=X.products.slice(0,8).map(p=>p.item_code);
  const reps=new Map();
  X.lines.filter(l=>top.includes(l.item_code)).forEach(l=>{
    let r=reps.get(l.rep);if(!r){r=new Map();reps.set(l.rep,r);}
    r.set(l.item_name,(r.get(l.item_name)||0)+(l.line_total||0));});
  const data=[...reps].map(([rep,items],i)=>({name:rep,itemStyle:{color:PAL[i%PAL.length]},
    children:[...items].map(([n,v])=>({name:n,value:Math.round(v)}))}));
  ec(id,{...b,tooltip:{...b.tooltip,valueFormatter:egp},series:[{type:"sunburst",radius:[0,"92%"],data,
    label:{color:"#fff",fontFamily:"Cairo",minAngle:8},itemStyle:{borderColor:isLight()?"#fff":"#0a0e1a",borderWidth:1}}]});}

function chSankey(id,X){const b=ecBase();
  const topC=[...X.customers].sort((a,c)=>c.sales-a.sales).slice(0,8).map(c=>c.customer_name);
  const topP=X.products.slice(0,8).map(p=>p.item_name);
  const cS=new Set(topC),pS=new Set(topP);
  const links=new Map();
  X.lines.forEach(l=>{if(cS.has(l.customer_name)&&pS.has(l.item_name)){
    const k=l.customer_name+"→"+l.item_name;links.set(k,(links.get(k)||0)+(l.line_total||0));}});
  const nodes=[...new Set([...topC,...topP])].map(n=>({name:n}));
  const linkArr=[...links].map(([k,v])=>{const[s,t]=k.split("→");return{source:s,target:t,value:Math.round(v)};}).filter(l=>l.value>0);
  ec(id,{...b,tooltip:{...b.tooltip,valueFormatter:egp},series:[{type:"sankey",data:nodes,links:linkArr,
    emphasis:{focus:"adjacency"},lineStyle:{color:"gradient",opacity:.4},
    label:{color:b._ink,fontFamily:"Cairo",fontSize:11},nodeGap:8,
    itemStyle:{color:PAL[0],borderColor:"transparent"}}]});}

function chHeatmap(id,X){const b=ecBase();
  const reps=[...new Set(X.lines.map(l=>l.rep))];
  const brands=[...new Set(X.lines.map(l=>l.brand))];
  const m=new Map();X.lines.forEach(l=>{const k=l.rep+"|"+l.brand;m.set(k,(m.get(k)||0)+(l.line_total||0));});
  const data=[];let mx=0;
  reps.forEach((r,ri)=>brands.forEach((br,bi)=>{const v=Math.round(m.get(r+"|"+br)||0);mx=Math.max(mx,v);data.push([bi,ri,v]);}));
  ec(id,{...b,tooltip:{...b.tooltip,formatter:p=>`${reps[p.data[1]]} · ${brands[p.data[0]]}<br/>${egp(p.data[2])}`},
    grid:{...b.grid,bottom:60,left:80},
    xAxis:axis(b,{type:"category",data:brands,axisLabel:{color:b._muted,rotate:30,interval:0,fontSize:10}}),
    yAxis:axis(b,{type:"category",data:reps,axisLabel:{color:b._muted}}),
    visualMap:{min:0,max:mx||1,calculable:true,orient:"horizontal",left:"center",bottom:0,
      inRange:{color:["#0d1220","#3b82f6","#8b5cf6","#ef4444"]},textStyle:{color:b._muted}},
    series:[{type:"heatmap",data,label:{show:false},itemStyle:{borderColor:isLight()?"#fff":"#0a0e1a",borderWidth:1}}]});}

function chVariance(id){const b=ecBase();
  const rows=D.monthly.filter(m=>m.month>="2025-07");
  const dv=rows.map((r,i)=>i===0?0:Math.round(r.net_sales-rows[i-1].net_sales));
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    xAxis:axis(b,{type:"category",data:rows.map(r=>r.month)}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"bar",data:dv.map(v=>({value:v,itemStyle:{color:v>=0?PAL[2]:PAL[4],borderRadius:v>=0?[6,6,0,0]:[0,0,6,6]}}))}]});}

function chWaterfall(id,X){const b=ecBase();// sales bridge by brand contribution
  const bm=[...groupSum(X.lines,"brand","line_total")].sort((a,c)=>c[1]-a[1]);
  const cats=["البداية",...bm.map(x=>x[0]),"الإجمالي"];
  let acc=0;const base=[0],val=[0];
  bm.forEach(x=>{base.push(acc);val.push(Math.round(x[1]));acc+=x[1];});
  base.push(0);val.push(Math.round(acc));
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
    xAxis:axis(b,{type:"category",data:cats,axisLabel:{color:b._muted,rotate:25,interval:0,fontSize:10}}),
    yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
    series:[{type:"bar",stack:"t",itemStyle:{color:"transparent"},data:base,silent:true},
      {type:"bar",stack:"t",data:val.map((v,i)=>({value:v,itemStyle:{color:i===val.length-1?PAL[1]:PAL[0],borderRadius:[4,4,0,0]}}))}]});}

function chHistogram(id,X){ // Plotly histogram of invoice values
  const vals=X.invoices.filter(v=>v.reported_total>0).map(v=>v.reported_total);
  const ink=isLight()?"#0f172a":"#e2e8f0", grid=isLight()?"#e2e8f0":"rgba(255,255,255,.08)";
  Plotly.newPlot(id,[{x:vals,type:"histogram",nbinsx:30,marker:{color:"#3b82f6",line:{color:"#8b5cf6",width:1}}}],
    {paper_bgcolor:"transparent",plot_bgcolor:"transparent",font:{family:"Cairo",color:ink},
     margin:{l:50,r:20,t:20,b:40},bargap:.04,xaxis:{title:"قيمة الفاتورة",gridcolor:grid,zeroline:false},
     yaxis:{title:"عدد الفواتير",gridcolor:grid}},{displayModeBar:false,responsive:true});
  charts[id]={_plotly:true,dispose(){Plotly.purge(id);},resize(){Plotly.Plots.resize(id);},
    getDataURL(){return null;}};}

function chBonusDist(id,X){const b=ecBase();
  const tiers={0:0,1:0,2:0,3:0,5:0};
  X.customers.forEach(c=>{const t=Math.round(c.bonus_pct*100);if(tiers[t]!=null)tiers[t]++;});
  const labels={0:"0%",1:"1%",2:"2%",3:"3%",5:"5%"};
  ec(id,{...b,tooltip:{...b.tooltip,trigger:"axis"},
    xAxis:axis(b,{type:"category",data:Object.keys(tiers).map(t=>labels[t])}),
    yAxis:axis(b,{type:"value",name:"عدد العملاء",axisLabel:{color:b._muted}}),
    series:[{type:"bar",data:Object.values(tiers),
      itemStyle:{color:p=>["#ef4444","#f59e0b","#f97316","#10b981","#3b82f6"][p.dataIndex],borderRadius:[6,6,0,0]},
      label:{show:true,position:"top",color:b._muted}}]});}

function chReconGauge(id){const b=ecBase();const s=D.data_quality;
  chGauge(id,s.reconciliation_rate);}

/* ========================================================================== */
/*  DataTables                                                                 */
/* ========================================================================== */
const DT_LANG={search:"بحث:",lengthMenu:"عرض _MENU_",info:"_START_–_END_ من _TOTAL_",
  paginate:{first:"الأول",last:"الأخير",next:"التالي",previous:"السابق"},zeroRecords:"لا نتائج",
  infoEmpty:"لا سجلات",infoFiltered:"(من _MAX_)"};
function dt(id,columns,data,opts){
  if(tables[id]){tables[id].destroy();$("#"+id).empty();}
  tables[id]=$("#"+id).DataTable(Object.assign({
    data,columns,language:DT_LANG,pageLength:10,lengthMenu:[10,25,50,100],
    dom:"<'d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2'Bf>rt<'d-flex justify-content-between align-items-center mt-2'ip>",
    buttons:[{extend:"excelHtml5",text:"Excel",className:"dt-button"},
      {extend:"csvHtml5",text:"CSV",className:"dt-button"},
      {extend:"copyHtml5",text:"نسخ",className:"dt-button"},
      {extend:"print",text:"طباعة",className:"dt-button"}],
    order:opts&&opts.order||[[0,"asc"]],
  },opts||{}));
  return tables[id];}

const bonusBadge=p=>{const t=Math.round(p*100);return `<span class="badge-b bonus-${t}">${t}%</span>`;};
const ageCls=b=>`age-${b}`;

/* ========================================================================== */
/*  SECTION DEFINITIONS                                                         */
/* ========================================================================== */
const SECTIONS = {
  overview:{ label:"لوحة المعلومات",
    dom:()=>`<div class="section-head"><div><h2>لوحة المعلومات التنفيذية</h2>
        <p>ملخص أداء <span id="ovPeriod"></span> — المبيعات والتحصيل والمديونية</p></div></div>
      <div id="kpiHost"></div>
      <div class="grid g-2">
        ${card({id:"c_monthly",title:"اتجاه المبيعات الشهري",sub:"السلسلة الكاملة",insightKey:"monthly_trend"})}
        ${card({id:"c_daily",title:"المبيعات والتحصيل اليومي",sub:""})}
        ${card({id:"c_aging",title:"أعمار الديون",approx:true,insightKey:"aging"})}
        ${card({id:"c_gauge",title:"معدل التحصيل التراكمي",short:true})}
        ${card({id:"c_brand",title:"توزيع المبيعات حسب العلامة"})}
        ${card({id:"c_top10",title:"أعلى ١٠ عملاء",insightKey:"top_customers"})}
      </div>`,
    update:(X)=>{ document.getElementById("kpiHost").innerHTML=kpiGrid(X.kpis);
      const ov=document.getElementById("ovPeriod"); if(ov) ov.textContent=curMonthLabel();
      chMonthly("c_monthly",X);chDaily("c_daily",X);chAgingBar("c_aging",X);chGauge("c_gauge",X.kpis.collection_rate);
      chDonut("c_brand",[...groupSum(X.lines,"brand","line_total")].sort((a,b)=>b[1]-a[1]));
      chTopCustomers("c_top10",X,10); }},

  sales:{ label:"المبيعات",
    dom:()=>`<div class="section-head"><div><h2>تحليل المبيعات</h2><p>الاتجاهات والمقارنات والتفاصيل</p></div></div>
      <div class="grid g-2">
        ${card({id:"s_daily",title:"اتجاه المبيعات اليومي",insightKey:"monthly_trend"})}
        ${card({id:"s_variance",title:"تحليل التباين الشهري (شهر مقابل شهر)"})}
        ${card({id:"s_waterfall",title:"جسر المبيعات حسب العلامة (Waterfall)"})}
        ${card({id:"s_topP",title:"أعلى ٢٠ صنفًا"})}
      </div>
      ${tableCard({id:"t_sales",title:"جدول المبيعات (بنود الفواتير)",sub:"قابل للبحث والفرز والتصدير"})}`,
    update:(X)=>{ chDaily("s_daily",X);chVariance("s_variance");chWaterfall("s_waterfall",X);chTopProducts("s_topP",X,20);
      dt("t_sales",[
        {title:"الفاتورة",data:"invoice_no"},{title:"التاريخ",data:"invoice_date"},
        {title:"العميل",data:"customer_name"},{title:"المندوب",data:"rep"},
        {title:"الصنف",data:"item_name"},{title:"العلامة",data:"brand"},
        {title:"الكمية",data:"qty",render:int},{title:"السعر",data:"unit_price",render:num},
        {title:"الإجمالي",data:"line_total",render:num}],
        X.lines,{order:[[8,"desc"]]}); }},

  customers:{ label:"العملاء",
    dom:()=>`<div class="section-head"><div><h2>تحليل العملاء</h2><p>الترتيب، التركّز، والأداء متعدد الأبعاد</p></div></div>
      <div class="grid g-2">
        ${card({id:"cu_top",title:"أعلى ٢٠ عميلًا حسب المبيعات",insightKey:"top_customers"})}
        ${card({id:"cu_pareto",title:"تحليل باريتو (٨٠/٢٠)",insightKey:"pareto"})}
        ${card({id:"cu_radar",title:"مقارنة أعلى ٥ عملاء (رادار)"})}
        ${card({id:"cu_scatter",title:"المبيعات مقابل المديونية",sub:"حجم النقطة = المبيعات"})}
      </div>
      ${tableCard({id:"t_cust",title:"ترتيب العملاء وكشف الأداء",sub:"انقر صفًا لعرض كشف الحساب"})}`,
    update:(X)=>{ chTopCustomers("cu_top",X,20);chPareto("cu_pareto",X);chRadar("cu_radar",X);chScatter("cu_scatter",X);
      const t=dt("t_cust",[
        {title:"#",data:"rank"},{title:"العميل",data:"customer_name"},{title:"المندوب",data:"rep"},
        {title:"المبيعات",data:"sales",render:num},{title:"الفواتير",data:"n_invoices"},
        {title:"الأصناف",data:"n_items"},{title:"الكراتين",data:"boxes",render:int},
        {title:"متوسط الفاتورة",data:"avg_invoice_value",render:num},
        {title:"المديونية",data:"outstanding",render:d=>d==null?"—":num(d)},
        {title:"معدل التحصيل",data:"collection_rate",render:d=>d==null?"—":pct(d)},
        {title:"الحافز",data:"bonus_pct",render:bonusBadge}],
        X.customers,{order:[[3,"desc"]]});
      $("#t_cust tbody").off("click").on("click","tr",function(){const d=t.row(this).data();if(d)openDrill(d.customer_code);}); }},

  products:{ label:"المنتجات",
    dom:()=>`<div class="section-head"><div><h2>تحليل المنتجات</h2><p>المساهمة، تشتت الأسعار، والأداء</p></div></div>
      <div class="grid g-2">
        ${card({id:"p_top",title:"أعلى ٢٠ صنفًا",insightKey:"top_products"})}
        ${card({id:"p_tree",title:"خريطة الإيراد (علامة ← صنف)"})}
        ${card({id:"p_box",title:"تشتت سعر البيع لأعلى الأصناف"})}
        ${card({id:"p_donut",title:"توزيع الإيراد حسب العلامة"})}
      </div>
      ${tableCard({id:"t_prod",title:"أداء المنتجات",sub:"ASP · أعلى/أدنى سعر · المساهمة"})}`,
    update:(X)=>{ chTopProducts("p_top",X,20);chTreemap("p_tree",X);chBox("p_box",X);
      chDonut("p_donut",[...groupSum(X.lines,"brand","line_total")].sort((a,b)=>b[1]-a[1]));
      dt("t_prod",[
        {title:"#",data:"rank"},{title:"الصنف",data:"item_name"},{title:"العلامة",data:"brand"},
        {title:"المبيعات",data:"sales",render:num},{title:"الكمية",data:"qty",render:int},
        {title:"الكراتين",data:"boxes",render:d=>d==null?"—":int(d)},
        {title:"م.السعر",data:"asp",render:num},{title:"أعلى",data:"max_price",render:d=>d==null?"—":num(d)},
        {title:"أدنى",data:"min_price",render:d=>d==null?"—":num(d)},
        {title:"العملاء",data:"n_customers"},{title:"المساهمة",data:"contribution_pct",render:d=>d.toFixed(1)+"%"}],
        X.products,{order:[[3,"desc"]]}); }},

  receivables:{ label:"المديونية",
    dom:()=>`<div class="section-head"><div><h2>المديونية وتحليل الأعمار</h2>
        <p>لقطة ${D.meta.as_of} <span class="tag-approx">الأعمار تقديرية — لا تواريخ استحقاق بالمصدر</span></p></div></div>
      <div class="grid g-2">
        ${card({id:"r_aging",title:"أعمار الديون",approx:true,insightKey:"aging"})}
        ${card({id:"r_water",title:"تراكم الأعمار (Waterfall)",approx:true})}
        ${card({id:"r_rep",title:"المديونية حسب المندوب",insightKey:"receivables_rep"})}
        ${card({id:"r_donut",title:"جاري مقابل متأخرات"})}
      </div>
      ${tableCard({id:"t_recv",title:"تفاصيل المديونية حسب العميل",approx:true,sub:"الرصيد · جاري · متأخرات · أيام التأخر"})}`,
    update:(X)=>{ chAgingBar("r_aging",X);chAgingWaterfall("r_water",X);chByRep("r_rep",X);
      chDonut("r_donut",[["جاري",sum(X.recv,"current")],["متأخرات",sum(X.recv,"overdue")]]);
      dt("t_recv",[
        {title:"المندوب",data:"rep"},{title:"العميل",data:"customer_name"},
        {title:"آخر نشاط",data:"last_invoice_date"},{title:"الرصيد",data:"outstanding",render:num},
        {title:"جاري",data:"current",render:num},{title:"متأخرات",data:"overdue",render:num},
        {title:"أيام التأخر",data:"days_overdue"},
        {title:"الفئة",data:"bucket",render:b=>`<span class="${ageCls(b)}">${D.receivables.bucket_labels[b]}</span>`}],
        X.recv,{order:[[3,"desc"]]}); }},

  collections:{ label:"التحصيل",
    dom:()=>`<div class="section-head"><div><h2>التحصيل</h2><p>معدل التحصيل والفواتير غير المحصّلة</p></div></div>
      <div class="grid g-2">
        ${card({id:"co_gauge",title:"معدل التحصيل التراكمي",short:true})}
        ${card({id:"co_donut",title:"محصّل مقابل قائم"})}
        ${card({id:"co_daily",title:"التحصيل عند الإصدار (يومي)"})}
        ${card({id:"co_bottom",title:"أدنى ١٥ عميلًا في معدل التحصيل"})}
      </div>
      ${tableCard({id:"t_coll",title:"سجل الفواتير والتحصيل",sub:"المدفوع · الباقي · الحالة"})}`,
    update:(X)=>{ chGauge("co_gauge",X.kpis.collection_rate);
      const billed=X.customers.reduce((a,c)=>a+(c.total_billed||0),0);
      const out=X.customers.reduce((a,c)=>a+(c.outstanding||0),0);
      chDonut("co_donut",[["محصّل",Math.max(0,billed-out)],["قائم",out]]);
      const b=ecBase();const m=groupSum(X.invoices,"invoice_date","paid");const days=[...m.keys()].sort();
      ec("co_daily",{...b,tooltip:{...b.tooltip,trigger:"axis",valueFormatter:egp},
        xAxis:axis(b,{type:"category",data:days.map(d=>d.slice(5))}),
        yAxis:axis(b,{type:"value",axisLabel:{color:b._muted,formatter:egpK}}),
        series:[{type:"bar",data:days.map(d=>Math.round(m.get(d)||0)),itemStyle:{color:PAL[5],borderRadius:[5,5,0,0]}}]});
      const bottom=X.customers.filter(c=>c.collection_rate!=null).sort((a,c)=>a.collection_rate-c.collection_rate).slice(0,15).reverse();
      ec("co_bottom",{...b,tooltip:{...b.tooltip,valueFormatter:x=>pct(x)},
        xAxis:axis(b,{type:"value",max:1,axisLabel:{color:b._muted,formatter:x=>pct(x,0)}}),
        yAxis:axis(b,{type:"category",data:bottom.map(c=>c.customer_name)}),
        series:[{type:"bar",data:bottom.map(c=>c.collection_rate),
          itemStyle:{color:p=>p.value>=.9?PAL[2]:p.value>=.7?PAL[3]:PAL[4],borderRadius:[0,6,6,0]}}]});
      dt("t_coll",[
        {title:"الفاتورة",data:"invoice_no"},{title:"التاريخ",data:"invoice_date"},
        {title:"العميل",data:"customer_name"},{title:"المندوب",data:"rep"},
        {title:"الإجمالي",data:"reported_total",render:num},{title:"المدفوع",data:"paid",render:num},
        {title:"الباقي",data:"remaining",render:num},
        {title:"الحالة",data:"status",render:s=>({paid:'<span class="pos">محصّلة</span>',unpaid:'<span class="age-d31_60">غير محصّلة</span>',zero:'<span class="neg">صفرية</span>'}[s]||s)}],
        X.invoices,{order:[[4,"desc"]]}); }},

  bonus:{ label:"الحوافز",
    dom:()=>`<div class="section-head"><div><h2>حوافز التحصيل</h2>
        <p>تُحتسب آليًا من معدل التحصيل وفق سلّم قابل للضبط من متغيّر واحد</p></div></div>
      <div class="grid g-2">
        ${card({id:"b_dist",title:"توزيع العملاء على شرائح الحافز",insightKey:"bonus"})}
        <div class="card"><div class="card-head"><h3>سلّم الحافز (BONUS_RULES)</h3></div>
          <div id="ladderHost" class="note"></div></div>
      </div>
      ${tableCard({id:"t_bonus",title:"تقرير الحوافز",sub:"معدل التحصيل · نسبة الحافز · القيمة المستحقة"})}`,
    update:(X)=>{ chBonusDist("b_dist",X);
      const rules=[["أقل من 70%","0%"],["70% – 80%","1%"],["80% – 90%","2%"],["90% – 95%","3%"],["95% – 100%","5%"]];
      const tot=X.customers.reduce((a,c)=>a+(c.bonus_value||0),0);
      document.getElementById("ladderHost").innerHTML=
        rules.map(r=>`<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border2)"><span>${r[0]}</span><b>${r[1]}</b></div>`).join("")+
        `<div style="margin-top:10px">إجمالي الحافز المستحق: <b class="pos">${egp(tot)}</b></div>`;
      const rows=X.customers.filter(c=>c.has_ar).map(c=>c);
      dt("t_bonus",[
        {title:"العميل",data:"customer_name"},{title:"المندوب",data:"rep"},
        {title:"مبيعات الشهر",data:"sales",render:num},{title:"إجمالي مُفوتر",data:"total_billed",render:num},
        {title:"المديونية",data:"outstanding",render:d=>d==null?"—":num(d)},
        {title:"معدل التحصيل",data:"collection_rate",render:d=>d==null?"—":pct(d)},
        {title:"الحافز %",data:"bonus_pct",render:bonusBadge},
        {title:"قيمة الحافز",data:"bonus_value",render:num}],
        rows,{order:[[7,"desc"]]}); }},

  analytics:{ label:"التحليلات المتقدمة",
    dom:()=>`<div class="section-head"><div><h2>التحليلات المتقدمة</h2><p>Sunburst · Sankey · Heatmap · التوزيعات</p></div></div>
      <div class="grid g-2">
        ${card({id:"a_sun",title:"شمسية: مندوب ← صنف",insightKey:"pareto"})}
        ${card({id:"a_sankey",title:"تدفق: عميل ← صنف",tall:true})}
        ${card({id:"a_heat",title:"حرارية: مندوب × علامة"})}
        ${card({id:"a_hist",title:"توزيع قيم الفواتير (Histogram)"})}
      </div>`,
    update:(X)=>{ chSunburst("a_sun",X);chSankey("a_sankey",X);chHeatmap("a_heat",X);chHistogram("a_hist",X); }},

  quality:{ label:"جودة البيانات",
    dom:()=>{const s=D.data_quality;
      const stat=(v,l,a)=>`<div class="kpi-card" style="--accent:${a};animation-delay:0s"><div class="kpi-val num">${v}</div><div class="kpi-lbl">${l}</div></div>`;
      return `<div class="section-head"><div><h2>جودة البيانات</h2>
        <p>مطابقة الاستخراج والقيم الشاذّة — لا يُحذف أي سجل، تُرصد فقط</p></div></div>
      <div class="kpi-grid">
        ${stat(pct(s.reconciliation_rate),"مطابقة الإجماليات","#10b981")}
        ${stat(int(s.n_line_items),"بنود الفواتير","#3b82f6")}
        ${stat(int(s.n_invoices),"عدد الفواتير","#8b5cf6")}
        ${stat(int(s.missing_total),"قيم مفقودة","#f59e0b")}
        ${stat(int(s.duplicate_invoice_count),"فواتير مكررة","#f97316")}
        ${stat(int(s.zero_value_invoice_count),"فواتير صفرية","#ef4444")}
        ${stat(int(s.abnormal_price_count),"أسعار شاذّة","#ec4899")}
        ${stat(int(s.abnormal_qty_count),"كميات شاذّة","#c4b5fd")}
      </div>
      <div class="grid g-2">
        ${card({id:"q_recon",title:"نسبة المطابقة",short:true,insightKey:"data_quality"})}
        ${card({id:"q_hist",title:"توزيع قيم الفواتير"})}
      </div>
      ${tableCard({id:"t_zero",title:"الفواتير صفرية القيمة",insightKey:"zero_invoices",sub:"بونص / عيّنات"})}`;},
    update:(X)=>{ chReconGauge("q_recon");chHistogram("q_hist",X);
      dt("t_zero",[
        {title:"الفاتورة",data:"invoice_no"},{title:"التاريخ",data:"invoice_date"},
        {title:"كود العميل",data:"customer_code"},{title:"العميل",data:"customer_name"},
        {title:"الكمية",data:"qty_total",render:int},
        {title:"بونص",data:"is_bonus",render:v=>v?'<span class="age-d31_60">نعم</span>':"—"}],
        D.zero_invoices,{order:[[1,"asc"]]}); }},
};

/* ========================================================================== */
/*  Rendering / navigation                                                     */
/* ========================================================================== */
const built = {};
function showSection(id){
  state.section=id;
  document.querySelectorAll(".nav-item").forEach(n=>n.classList.toggle("active",n.dataset.section===id));
  const host=document.getElementById("sections");
  document.querySelectorAll(".section").forEach(s=>s.classList.remove("active"));
  let el=document.getElementById("sec_"+id);
  if(!el){ el=document.createElement("section");el.className="section";el.id="sec_"+id;
    el.innerHTML=SECTIONS[id].dom();host.appendChild(el);built[id]=false; }
  el.classList.add("active");
  const X=buildContext();
  SECTIONS[id].update(X);
  paintInsights();
  built[id]=true;
  bindPng();
  setTimeout(()=>Object.values(charts).forEach(c=>c&&c.resize&&c.resize()),60);
  document.getElementById("sidebar").classList.remove("open");
}
function refreshActive(){ if(state.section){ SECTIONS[state.section].update(buildContext()); paintInsights(); } }

/* ---- PNG export per chart ---- */
function bindPng(){
  document.querySelectorAll("[data-png]").forEach(btn=>{
    btn.onclick=()=>{const c=charts[btn.dataset.png];if(!c)return;
      let url; try{url=c.getDataURL({pixelRatio:2,backgroundColor:isLight()?"#fff":"#0a0e1a"});}catch(e){toast("تعذّر تصدير هذا الرسم");return;}
      if(!url){toast("تصدير PNG غير متاح لهذا الرسم");return;}
      const a=document.createElement("a");a.href=url;a.download=btn.dataset.png+".png";a.click();};
  });
}

/* ========================================================================== */
/*  Drill-through — customer statement                                         */
/* ========================================================================== */
function openDrill(code){
  // Full-year 2026 statement for the customer (independent of the month filter),
  // joined with the fixed AR / bonus snapshot.
  const inv=D.invoices.filter(v=>v.customer_code===code);
  const lines=D.lines.filter(l=>l.customer_code===code);
  if(!inv.length && !lines.length) return;
  const [c]=aggCustomers(lines,inv);
  if(!c) return;
  const items=[...groupSum(lines,"item_name","line_total")].sort((a,b)=>b[1]-a[1]);
  const mk=(v,l)=>`<div class="mini-kpi"><div class="v num">${v}</div><div class="l">${l}</div></div>`;
  const invRows=inv.sort((a,b)=>b.reported_total-a.reported_total).map(v=>`<tr>
    <td>${v.invoice_no}</td><td>${v.invoice_date}</td><td class="num">${num(v.reported_total)}</td>
    <td class="num">${num(v.paid)}</td><td class="num">${num(v.remaining)}</td>
    <td>${({paid:'<span class="pos">محصّلة</span>',unpaid:'<span class="age-d31_60">غير محصّلة</span>',zero:'<span class="neg">صفرية</span>'}[v.status])}</td></tr>`).join("");
  const itemRows=items.map(([n,v])=>`<tr><td>${n}</td><td class="num">${num(v)}</td></tr>`).join("");
  document.getElementById("drillTitle").textContent="كشف حساب — "+c.customer_name;
  document.getElementById("drillBody").innerHTML=`
    <div class="mini-kpis">
      ${mk(egpK(c.sales),"مبيعات ٢٠٢٦")}${mk(int(c.n_invoices),"الفواتير")}
      ${mk(int(c.n_items),"الأصناف")}${mk(c.outstanding==null?"—":egpK(c.outstanding),"المديونية")}
      ${mk(c.collection_rate==null?"—":pct(c.collection_rate),"معدل التحصيل")}${mk(bonusBadge(c.bonus_pct),"الحافز")}
    </div>
    ${c.oldest_invoice_no?`<div class="note" style="margin-bottom:14px">أقدم فاتورة غير محصّلة:
      <b>${c.oldest_invoice_no}</b> بتاريخ ${c.oldest_invoice_date} — استحقاق تقديري ${c.oldest_due_date}
      (${c.oldest_days_overdue} يوم تأخر) بقيمة ${egp(c.oldest_amount)}</div>`:""}
    <div class="grid g-2">
      <div><h3 style="margin-bottom:8px">الفواتير</h3><div class="tbl-wrap"><table class="dataTable" style="width:100%">
        <thead><tr><th>الفاتورة</th><th>التاريخ</th><th>الإجمالي</th><th>المدفوع</th><th>الباقي</th><th>الحالة</th></tr></thead>
        <tbody>${invRows}</tbody></table></div></div>
      <div><h3 style="margin-bottom:8px">الأصناف المشتراة</h3><div class="tbl-wrap"><table class="dataTable" style="width:100%">
        <thead><tr><th>الصنف</th><th>القيمة</th></tr></thead><tbody>${itemRows}</tbody></table></div></div>
    </div>`;
  document.getElementById("drillModal").classList.add("open");
}
function closeDrill(){document.getElementById("drillModal").classList.remove("open");}

/* ========================================================================== */
/*  Filters                                                                     */
/* ========================================================================== */
function fillFilters(){
  const uniq=(arr,k)=>[...new Set(arr.map(x=>x[k]).filter(Boolean))].sort();
  const pairs=(map)=>Object.entries(map).map(([v,l])=>({v,l})).sort((a,b)=>a.l.localeCompare(b.l,"ar"));
  const opt=(el,vals)=>{vals.forEach(v=>{const o=document.createElement("option");
    o.value=typeof v==="object"?v.v:v;o.textContent=typeof v==="object"?v.l:v;el.appendChild(o);});};

  // Month selector — the one new feature. Populated with the 2026 months present
  // in the data plus an "All months" option; defaults to June.
  const fm=document.getElementById("f_month");
  fm.innerHTML="";
  opt(fm,[{v:"all",l:ALL_LABEL}, ...D.meta.available_months]);
  fm.value=state.filters.month;

  opt(document.getElementById("f_customer"),pairs(CUST_NAME));
  opt(document.getElementById("f_rep"),uniq(D.lines,"rep"));
  opt(document.getElementById("f_item"),pairs(ITEM_NAME));
  opt(document.getElementById("f_brand"),uniq(D.lines,"brand"));
  opt(document.getElementById("f_branch"),uniq(D.lines,"rep"));  // no branch field → salesperson region
  const ag=document.getElementById("f_aging");
  AGING_KEYS.forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=D.receivables.bucket_labels[k];ag.appendChild(o);});

  const map={f_month:"month",f_customer:"customer",f_rep:"rep",f_item:"item",
             f_brand:"brand",f_branch:"rep",f_status:"status",f_aging:"aging"};
  Object.keys(map).forEach(fid=>document.getElementById(fid).addEventListener("change",e=>{
    state.filters[map[fid]]=e.target.value;
    if(fid==="f_month"){
      document.getElementById("periodLabel").textContent=curMonthLabel();
      if(!monthHasData(e.target.value)) toast("لا توجد بيانات مبيعات لهذا الشهر بالمصدر");
    }
    renderChips(); refreshActive(); }));
}
function renderChips(){
  const f=state.filters;const host=document.getElementById("filterChips");host.innerHTML="";
  const labels={customer:"العميل",rep:"المندوب",item:"الصنف",brand:"العلامة",status:"الحالة",aging:"العمر"};
  const statusL={unpaid:"غير محصّلة",paid:"محصّلة",zero:"صفرية"};
  Object.entries(f).forEach(([k,v])=>{if(!v||k==="month")return;  // month has its own selector
    let txt=CUST_NAME[v]||ITEM_NAME[v]||statusL[v]||(k==="aging"?D.receivables.bucket_labels[v]:v);
    const c=document.createElement("span");c.className="chip";c.innerHTML=`${labels[k]||k}: <b>${txt}</b> ✕`;
    c.onclick=()=>{state.filters[k]="";syncSelects();renderChips();refreshActive();};host.appendChild(c);});
}
function syncSelects(){
  const m={f_month:"month",f_customer:"customer",f_rep:"rep",f_item:"item",
           f_brand:"brand",f_status:"status",f_aging:"aging"};
  Object.entries(m).forEach(([fid,k])=>{const el=document.getElementById(fid);if(el)el.value=state.filters[k];});
  const br=document.getElementById("f_branch");if(br&&br.value!==state.filters.rep)br.value=state.filters.rep;
}
function resetFilters(){  // reset cross-filters but keep the selected month
  const month=state.filters.month;
  state.filters={month,customer:"",rep:"",brand:"",item:"",status:"",aging:""};
  syncSelects();renderChips();refreshActive();toast("أُعيد ضبط الفلاتر");}

/* ---- global quick search: routes to active DataTable ---- */
function wireSearch(){
  document.getElementById("globalSearch").addEventListener("input",e=>{
    const v=e.target.value;Object.values(tables).forEach(t=>{try{t.search(v).draw();}catch(_){}}); });
}

/* ========================================================================== */
/*  Misc: theme, print, export-all, toast                                      */
/* ========================================================================== */
let toastT;
function toast(msg){const t=document.getElementById("toast");t.textContent=msg;t.classList.add("show");
  clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove("show"),2200);}
function toggleTheme(){document.body.setAttribute("data-theme",isLight()?"dark":"light");
  refreshActive();toast(isLight()?"المظهر الفاتح":"المظهر الداكن");}
function exportAll(){const t=tables[Object.keys(tables)[0]];
  const btn=$(".dt-button").filter((i,e)=>/Excel/.test(e.textContent)).first();
  if(btn.length){btn[0].click();}else{toast("افتح قسمًا به جدول للتصدير");}}

/* ========================================================================== */
/*  Boot                                                                        */
/* ========================================================================== */
function boot(){
  document.getElementById("periodLabel").textContent=curMonthLabel();
  const dm=D.meta.data_months||[];
  const span=dm.length?`${monthName(dm[0]).split(" ")[0]}–${monthName(dm[dm.length-1]).split(" ")[0]}`:"";
  document.getElementById("dataNote").innerHTML=
    `المصدر: فواتير 2026 (${span}) · لقطة مديونية ${D.meta.as_of}.<br>`+
    `قيود: لا تكلفة (لا هامش)، لا موازنة، الأعمار تقديرية.`;
  fillFilters();wireSearch();
  document.querySelectorAll(".nav-item").forEach(n=>n.addEventListener("click",()=>showSection(n.dataset.section)));
  document.getElementById("btnTheme").onclick=toggleTheme;
  document.getElementById("btnPrint").onclick=()=>window.print();
  document.getElementById("btnExportAll").onclick=exportAll;
  document.getElementById("btnReset").onclick=resetFilters;
  document.getElementById("navToggle").onclick=()=>document.getElementById("sidebar").classList.toggle("open");
  document.getElementById("drillClose").onclick=closeDrill;
  document.getElementById("drillModal").addEventListener("click",e=>{if(e.target.id==="drillModal")closeDrill();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrill();});
  showSection("overview");
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();
