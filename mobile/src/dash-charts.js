/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   Namespace C — the 14 ECharts option builders, plus the EChart host component.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
const C = (function(){
const { PAL, AGING_KEYS, AGING_COLORS, egp, egpK, int, num, pct, sum, groupSum } = T;
/* Abu Hashem — mobile runtime · PART 5: the chart layer.

   Every builder below is a port of the desktop dashboard's `ch*` function. The
   DATA TRANSFORM is verbatim in each case — same fields, same sort, same top-N,
   same colours — so the numbers reconcile with the desktop exactly. Only the
   PRESENTATION is retuned for a 390 px touch screen.

   Where a form genuinely does not survive the narrower canvas the change is
   called out in a comment on that builder (sankey 8x8 -> 5x5 vertical, boxplot
   10 -> 6 horizontal). Nothing else is reinterpreted.

   The desktop draws two histograms with Plotly (4.7 MB) and everything else
   with ECharts. Here the histogram is binned by hand and drawn as an ECharts
   bar, so Plotly is not shipped at all.

   Rendering is SVG, not canvas: crisp on high-DPI phones, no devicePixelRatio
   sizing bugs, and it prints. */


/* ---------------------------------------------------------------- base ---- */

/* Mobile-tuned equivalent of the desktop's ecBase(). Differences from the
   desktop, all forced by the narrow viewport:
     - tooltip.confine so it cannot overflow the screen edge
     - legend scrolls instead of wrapping into three rows
     - axis labels elide rather than rotate where possible
     - fatter series so a fingertip can hit them */
function ecBase(){
  const ink="#e2e8f0", muted="#94a3b8", grid="rgba(255,255,255,.07)";
  return {
    color: PAL,
    animationDuration: 320,
    textStyle:{fontFamily:"Cairo, system-ui, 'Segoe UI', Tahoma, sans-serif", color:ink},
    grid:{left:6, right:10, top:28, bottom:6, containLabel:true},
    tooltip:{
      confine:true, backgroundColor:"#0d1220", borderColor:grid, borderWidth:1,
      textStyle:{color:ink, fontSize:11.5, fontFamily:"Cairo, sans-serif"},
      extraCssText:"max-width:78vw;white-space:normal;line-height:1.7",
    },
    legend:{type:"scroll", top:0, itemWidth:11, itemHeight:8,
            textStyle:{color:muted, fontSize:10.5, fontFamily:"Cairo, sans-serif"}},
    _ink:ink, _muted:muted, _grid:grid,
  };
}

const ax = (b, o) => Object.assign({
  axisLine:{lineStyle:{color:b._grid}},
  axisTick:{show:false},
  splitLine:{lineStyle:{color:b._grid}},
  axisLabel:{color:b._muted, fontSize:10, fontFamily:"Cairo, sans-serif", hideOverlap:true},
}, o||{});

/* Elide long Arabic names rather than letting them eat the plot area. */
const clip = (n) => (s) => { s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n-1) + "…" : s; };

const EMPTY = {__empty:true};
const isEmpty = o => !o || o.__empty === true;

/* Three height tiers, replacing the desktop's 340/440/260. */
const H = {short:240, base:300, tall:380};

/* ------------------------------------------------------- line and area ---- */

/* chMonthly — reads D.monthly directly and ignores the filters, exactly as the
   desktop does. The selected month is marked, not filtered to. */
function monthly(D, filters){
  const rows = (D.monthly||[]).filter(m => m.month >= "2025-01");
  if(!rows.length) return EMPTY;
  const b = ecBase();
  const cm = (filters.month && filters.month !== "all") ? filters.month : null;
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", valueFormatter:egp},
    xAxis: ax(b,{type:"category", data:rows.map(r=>r.month), axisLabel:{...ax(b).axisLabel, interval:2, rotate:0}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[{
      type:"line", smooth:true, symbolSize:6,
      data: rows.map(r=>Math.round(r.net_sales)),
      areaStyle:{opacity:.22}, lineStyle:{width:3, color:PAL[0]}, itemStyle:{color:PAL[0]},
      markPoint: {symbolSize:42, label:{fontSize:9},
                  data:[{type:"max", name:"الأعلى"}]},
      markLine: cm ? {symbol:"none", data:[{xAxis:cm}],
                      lineStyle:{color:PAL[3], type:"dashed", width:2},
                      label:{show:true, formatter:"المحدد", fontSize:9, color:PAL[3]}} : undefined,
    }]};
}

/* chDaily — line (sales) + bar (collections at issue) by invoice date. */
function daily(X){
  const m = groupSum(X.invoices, "invoice_date", "reported_total");
  const c = groupSum(X.invoices, "invoice_date", "paid");
  const days = [...m.keys()].sort();
  if(!days.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", valueFormatter:egp},
    legend:{...b.legend, data:["المبيعات","التحصيل"]},
    xAxis: ax(b,{type:"category", data:days.map(d=>d.slice(5)),
                 axisLabel:{...ax(b).axisLabel, interval:Math.max(0, Math.floor(days.length/7)-1)}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[
      {name:"المبيعات", type:"line", smooth:true, symbolSize:5, areaStyle:{opacity:.2},
       lineStyle:{color:PAL[0]}, itemStyle:{color:PAL[0]}, data:days.map(d=>Math.round(m.get(d)))},
      {name:"التحصيل", type:"bar", itemStyle:{color:PAL[2]}, data:days.map(d=>Math.round(c.get(d)||0))},
    ]};
}

/* chVariance — month-over-month delta, diverging. Reads D.monthly, unfiltered. */
function variance(D){
  const rows = (D.monthly||[]).filter(m => m.month >= "2025-07");
  if(rows.length < 2) return EMPTY;
  const dv = rows.map((r,i) => i===0 ? 0 : Math.round(r.net_sales - rows[i-1].net_sales));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", valueFormatter:egp},
    xAxis: ax(b,{type:"category", data:rows.map(r=>r.month),
                 axisLabel:{...ax(b).axisLabel, interval:1, rotate:45}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[{type:"bar", data:dv.map(v=>({value:v,
      itemStyle:{color:v>=0?PAL[2]:PAL[4], borderRadius:v>=0?[5,5,0,0]:[0,0,5,5]}}))}]};
}

/* -------------------------------------------------------------- bars ------ */

/* chTopCustomers / chTopProducts. `n` defaults lower than the desktop's 20 —
   20 horizontal bars at 390 px are 14 px apart and unreadable. */
function topCustomers(X, n){
  const cs = [...X.customers].sort((a,b2)=>b2.sales-a.sales).slice(0, n||12).reverse();
  if(!cs.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}, valueFormatter:egp},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"category", data:cs.map(c=>c.customer_name),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(14), width:96, overflow:"truncate"}}),
    series:[{type:"bar", data:cs.map(c=>Math.round(c.sales)),
             itemStyle:{color:PAL[0], borderRadius:[0,5,5,0]}}],
    _codes: cs.map(c=>c.customer_code),        // for tap-to-drill
  };
}

function topProducts(X, n){
  const ps = X.products.slice(0, n||12).reverse();
  if(!ps.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}, valueFormatter:egp},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"category", data:ps.map(p=>p.item_name),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(14), width:96, overflow:"truncate"}}),
    series:[{type:"bar", data:ps.map(p=>Math.round(p.sales)),
             itemStyle:{color:PAL[1], borderRadius:[0,5,5,0]}}],
    _codes: ps.map(p=>p.item_code),
  };
}

/* chByRep — receivables stacked current vs overdue. */
function byRep(X){
  const reps = [...X.recv.reduce((m,r)=>{ const o=m.get(r.rep)||{c:0,o:0};
      o.c+=r.current; o.o+=r.overdue; m.set(r.rep,o); return m; }, new Map())]
    .map(([rep,v])=>({rep, current:v.c, overdue:v.o, total:v.c+v.o}))
    .sort((a,b2)=>b2.total-a.total);
  if(!reps.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}, valueFormatter:egp},
    legend:{...b.legend, data:["جاري","متأخرات"]},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"category", data:reps.map(r=>r.rep).reverse(),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(12), width:84, overflow:"truncate"}}),
    series:[
      {name:"جاري", type:"bar", stack:"s", itemStyle:{color:PAL[2]},
       data:reps.map(r=>Math.round(r.current)).reverse()},
      {name:"متأخرات", type:"bar", stack:"s", itemStyle:{color:PAL[4], borderRadius:[0,5,5,0]},
       data:reps.map(r=>Math.round(r.overdue)).reverse()},
    ],
    _cats: reps.map(r=>r.rep).reverse(),
  };
}

/* chAgingBar */
function agingBar(X, D){
  const bk = X.buckets, lab = (D.receivables&&D.receivables.bucket_labels)||{};
  if(!AGING_KEYS.some(k=>bk[k])) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}, valueFormatter:egp},
    xAxis: ax(b,{type:"category", data:AGING_KEYS.map(k=>lab[k]||k),
                 axisLabel:{...ax(b).axisLabel, interval:0, rotate:38, fontSize:9}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[{type:"bar", data:AGING_KEYS.map(k=>Math.round(bk[k]||0)),
      itemStyle:{color:p=>AGING_COLORS[AGING_KEYS[p.dataIndex]], borderRadius:[5,5,0,0]},
      label:{show:true, position:"top", fontSize:9, color:b._muted, formatter:o=>egpK(o.value)}}],
    _cats: AGING_KEYS,
  };
}

/* chBonusDist */
function bonusDist(X){
  const tiers = {0:0,1:0,2:0,3:0,5:0};
  X.customers.forEach(c => { const t = Math.round(c.bonus_pct*100); if(tiers[t]!=null) tiers[t]++; });
  if(!Object.values(tiers).some(v=>v)) return EMPTY;
  const labels = {0:"0%",1:"1%",2:"2%",3:"3%",5:"5%"};
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}},
    xAxis: ax(b,{type:"category", data:Object.keys(tiers).map(t=>labels[t])}),
    yAxis: ax(b,{type:"value", name:"عدد العملاء", nameTextStyle:{color:b._muted, fontSize:10}}),
    series:[{type:"bar", data:Object.values(tiers),
      itemStyle:{color:p=>["#ef4444","#f59e0b","#f97316","#10b981","#3b82f6"][p.dataIndex],
                 borderRadius:[5,5,0,0]},
      label:{show:true, position:"top", fontSize:10, color:b._muted}}]};
}

/* ----------------------------------------------------------- waterfall ---- */

/* chAgingWaterfall — transparent-base stacked bar, as the desktop does it. */
function agingWaterfall(X, D){
  const bk = X.buckets, lab = (D.receivables&&D.receivables.bucket_labels)||{};
  if(!AGING_KEYS.some(k=>bk[k])) return EMPTY;
  let acc=0; const base=[], val=[];
  AGING_KEYS.forEach(k => { base.push(acc); val.push(Math.round(bk[k]||0)); acc += bk[k]||0; });
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"},
      formatter:p=>{ const i=p[0].dataIndex; return (lab[AGING_KEYS[i]]||"")+"<br/>"+egp(val[i]); }},
    xAxis: ax(b,{type:"category", data:AGING_KEYS.map(k=>lab[k]||k),
                 axisLabel:{...ax(b).axisLabel, interval:0, rotate:38, fontSize:9}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[
      {type:"bar", stack:"t", itemStyle:{color:"transparent"}, data:base, silent:true},
      {type:"bar", stack:"t", data:val,
       itemStyle:{color:p=>AGING_COLORS[AGING_KEYS[p.dataIndex]], borderRadius:[4,4,0,0]}},
    ]};
}

/* chWaterfall — sales bridge by brand contribution. */
function salesWaterfall(X){
  const bm = [...groupSum(X.lines,"brand","line_total")].sort((a,c)=>c[1]-a[1]);
  if(!bm.length) return EMPTY;
  const cats = ["البداية", ...bm.map(x=>x[0]), "الإجمالي"];
  let acc=0; const base=[0], val=[0];
  bm.forEach(x => { base.push(acc); val.push(Math.round(x[1])); acc += x[1]; });
  base.push(0); val.push(Math.round(acc));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"},
      formatter:p=>{ const i=p[0].dataIndex; return cats[i]+"<br/>"+egp(val[i]); }},
    xAxis: ax(b,{type:"category", data:cats,
                 axisLabel:{...ax(b).axisLabel, interval:0, rotate:38, fontSize:9, formatter:clip(9)}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[
      {type:"bar", stack:"t", itemStyle:{color:"transparent"}, data:base, silent:true},
      {type:"bar", stack:"t", data:val.map((v,i)=>({value:v,
        itemStyle:{color:i===val.length-1?PAL[1]:PAL[0], borderRadius:[4,4,0,0]}}))},
    ]};
}

/* ------------------------------------------------------------- pareto ----- */

/* chPareto — every customer, bar + cumulative % on a second axis, 80% marker.
   The x labels are hidden on the desktop too, so nothing is lost on mobile. */
function pareto(X){
  const cs = [...X.customers].sort((a,b2)=>b2.sales-a.sales);
  if(!cs.length) return EMPTY;
  const total = sum(cs,"sales") || 1;
  let cum = 0;
  const bar = cs.map(c=>Math.round(c.sales));
  const line = cs.map(c => { cum += c.sales; return +(cum/total*100).toFixed(1); });
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis",
      formatter:p=>{ const i=p[0].dataIndex;
        return cs[i].customer_name+"<br/>"+egp(bar[i])+"<br/>تراكمي: "+line[i]+"%"; }},
    legend:{...b.legend, data:["المبيعات","التراكمي %"]},
    xAxis: ax(b,{type:"category", data:cs.map(c=>c.customer_name), axisLabel:{show:false}}),
    yAxis:[
      ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
      ax(b,{type:"value", max:100, splitLine:{show:false},
            axisLabel:{...ax(b).axisLabel, formatter:"{value}%"}}),
    ],
    series:[
      {name:"المبيعات", type:"bar", data:bar, itemStyle:{color:PAL[0]}},
      {name:"التراكمي %", type:"line", yAxisIndex:1, data:line, smooth:true, symbol:"none",
       lineStyle:{width:2.4, color:PAL[3]}, itemStyle:{color:PAL[3]},
       markLine:{symbol:"none", data:[{yAxis:80}],
                 lineStyle:{color:PAL[4], type:"dashed"},
                 label:{formatter:"80%", fontSize:9, color:PAL[4]}}},
    ],
    _codes: cs.map(c=>c.customer_code),
  };
}

/* -------------------------------------------------------------- donut ----- */

function donut(pairs, fmt){
  const rows = (pairs||[]).filter(p => p[1] > 0);
  if(!rows.length) return EMPTY;
  const b = ecBase();
  const f = fmt || egp;
  return {...b,
    tooltip:{...b.tooltip, trigger:"item", formatter:p=>p.name+"<br/>"+f(p.value)+" ("+p.percent+"%)"},
    legend:{...b.legend, bottom:0, top:undefined, formatter:clip(14)},
    series:[{type:"pie", radius:["46%","72%"], center:["50%","44%"],
      avoidLabelOverlap:true, padAngle:2,
      itemStyle:{borderRadius:4, borderColor:"#0a0e1a", borderWidth:1},
      label:{color:b._muted, fontSize:10, formatter:"{d}%"},
      labelLine:{length:8, length2:8},
      data: rows.map((p,i)=>({name:p[0], value:Math.round(p[1]),
                              itemStyle:{color:p[2]||PAL[i%PAL.length]}}))}],
    _cats: rows.map(p=>p[0]),
  };
}

/* -------------------------------------------------------------- gauge ----- */

function gauge(rate, label){
  const b = ecBase();
  return {...b,
    series:[{type:"gauge", startAngle:210, endAngle:-30, min:0, max:100, radius:"88%",
      center:["50%","56%"],
      progress:{show:true, width:14, itemStyle:{color:PAL[2]}},
      axisLine:{lineStyle:{width:14, color:[[.7,"#ef4444"],[.9,"#f59e0b"],[1,"#10b981"]]}},
      axisTick:{show:false}, splitLine:{length:9, lineStyle:{color:b._grid}},
      axisLabel:{show:false},
      pointer:{width:4, itemStyle:{color:b._ink}},
      title:{show:!!label, offsetCenter:[0,"76%"], color:b._muted, fontSize:10.5,
             fontFamily:"Cairo, sans-serif"},
      detail:{formatter:"{value}%", fontSize:22, color:b._ink, offsetCenter:[0,"34%"],
              fontFamily:"'JetBrains Mono', monospace"},
      data:[{value:+((rate||0)*100).toFixed(1), name:label||""}]}]};
}

/* ------------------------------------------------------------ treemap ----- */

/* chTreemap — brand -> item, tap to zoom into a brand. */
function treemap(X){
  const brands = new Map();
  X.lines.forEach(l => {
    let br = brands.get(l.brand);
    if(!br){ br = {name:l.brand, children:new Map()}; brands.set(l.brand, br); }
    br.children.set(l.item_name, (br.children.get(l.item_name)||0) + (l.line_total||0));
  });
  if(!brands.size) return EMPTY;
  const data = [...brands.values()].map((br,i)=>({
    name: br.name, itemStyle:{color:PAL[i%PAL.length]},
    children: [...br.children].map(([n,v])=>({name:n, value:Math.round(v)})),
  }));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, formatter:p=>p.name+"<br/>"+egp(p.value)},
    series:[{type:"treemap", roam:false, nodeClick:"zoomToNode", width:"100%", height:"88%",
      top:26, breadcrumb:{show:true, height:20, bottom:0,
        itemStyle:{color:"#1e293b", textStyle:{color:b._muted, fontSize:10}}},
      label:{fontSize:10, fontFamily:"Cairo, sans-serif", formatter:clip(12)},
      upperLabel:{show:true, height:18, fontSize:10, color:"#fff"},
      levels:[{itemStyle:{gapWidth:2, borderColor:"#0a0e1a"}},
              {itemStyle:{gapWidth:1, borderColor:"rgba(0,0,0,.35)"}}],
      data}]};
}

/* ------------------------------------------------------------ boxplot ----- */

/* chBox — MOBILE CHANGE: top 6 items instead of 10, drawn horizontally. The
   desktop rotates 10 category labels 35 degrees, which at 390 px overlaps into
   an unreadable stripe. Quantiles keep the source's nearest-rank method so the
   figures match the desktop exactly. */
function priceBox(X){
  const items = X.products.filter(p => p.prices && p.prices.length >= 3).slice(0, 6);
  if(!items.length) return EMPTY;
  const boxData = items.map(p => {
    const s = [...p.prices].sort((a,c)=>a-c);
    const q = f => s[Math.floor((s.length-1)*f)];
    return [s[0], q(.25), q(.5), q(.75), s[s.length-1]];
  });
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"item",
      formatter:p=>{ const d=p.data;
        return items[p.dataIndex].item_name+"<br/>أدنى "+num(d[1])+" · ربع أول "+num(d[2])
             + "<br/>وسيط "+num(d[3])+"<br/>ربع ثالث "+num(d[4])+" · أعلى "+num(d[5]); }},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", name:"سعر الوحدة", nameTextStyle:{color:b._muted, fontSize:10},
                 scale:true}),
    yAxis: ax(b,{type:"category", data:items.map(p=>p.item_name),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(13), width:90, overflow:"truncate"}}),
    series:[{type:"boxplot", data:boxData, boxWidth:[10,26],
      itemStyle:{color:"rgba(59,130,246,.28)", borderColor:PAL[0], borderWidth:1.4}}]};
}

/* ------------------------------------------------------------ scatter ----- */

/* chScatter — sales vs outstanding, radius by sales, colour by collection rate. */
function scatter(X){
  const pts = X.customers.filter(c => c.outstanding != null)
    .map(c => [Math.round(c.sales), Math.round(c.outstanding), c.customer_name,
               c.collection_rate, c.customer_code]);
  if(!pts.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"item", formatter:p=>
      p.data[2]+"<br/>مبيعات: "+egp(p.data[0])+"<br/>مديونية: "+egp(p.data[1])
      +"<br/>تحصيل: "+(p.data[3]==null?"—":pct(p.data[3]))},
    xAxis: ax(b,{type:"value", name:"مبيعات الفترة", nameGap:24, nameLocation:"middle",
                 nameTextStyle:{color:b._muted, fontSize:10},
                 axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[{type:"scatter", data:pts,
      symbolSize:d=>Math.max(9, Math.sqrt(d[0])/14),
      itemStyle:{opacity:.78,
        color:p=>p.data[3]>=.9?PAL[2]:p.data[3]>=.7?PAL[3]:PAL[4]}}],
    _codes: pts.map(p=>p[4]),
  };
}

/* -------------------------------------------------------------- radar ----- */

function radar(X){
  /* MOBILE CHANGE: 4 series instead of the desktop's 5. Five long Arabic names
     wrap the scrolling legend onto a second page and overlap their swatches. */
  const top = [...X.customers].sort((a,c)=>c.sales-a.sales).slice(0,4);
  if(!top.length) return EMPTY;
  const max = k => Math.max(...X.customers.map(c=>c[k]||0)) || 1;
  const ind = [
    {name:"المبيعات", max:max("sales")}, {name:"الفواتير", max:max("n_invoices")},
    {name:"الأصناف", max:max("n_items")}, {name:"الكمية", max:max("units")},
    {name:"معدل التحصيل", max:1},
  ];
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"item"},
    legend:{...b.legend, bottom:0, top:undefined, formatter:clip(10),
            itemGap:14, itemWidth:9, textStyle:{color:b._muted, fontSize:9.5,
            fontFamily:"Cairo, sans-serif", padding:[0,3,0,0]}},
    radar:{indicator:ind, radius:"56%", center:["50%","42%"],
      axisName:{color:b._muted, fontSize:9.5, fontFamily:"Cairo, sans-serif"},
      splitLine:{lineStyle:{color:b._grid}}, splitArea:{show:false},
      axisLine:{lineStyle:{color:b._grid}}},
    series:[{type:"radar", symbolSize:4,
      data: top.map((t,i)=>({name:t.customer_name,
        value:[t.sales, t.n_invoices, t.n_items, t.units, t.collection_rate||0],
        lineStyle:{width:1.8, color:PAL[i%PAL.length]},
        itemStyle:{color:PAL[i%PAL.length]}, areaStyle:{opacity:.08}}))}]};
}

/* ----------------------------------------------------------- sunburst ----- */

/* chSunburst — rep -> item, restricted to the top 8 items, exactly as desktop. */
function sunburst(X){
  const top = X.products.slice(0,8).map(p=>p.item_code);
  const reps = new Map();
  X.lines.filter(l => top.includes(l.item_code)).forEach(l => {
    let r = reps.get(l.rep); if(!r){ r = new Map(); reps.set(l.rep, r); }
    r.set(l.item_name, (r.get(l.item_name)||0) + (l.line_total||0));
  });
  if(!reps.size) return EMPTY;
  const data = [...reps].map(([rep,items],i)=>({
    name: rep, itemStyle:{color:PAL[i%PAL.length]},
    children: [...items].map(([n,v])=>({name:n, value:Math.round(v)})),
  }));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, formatter:p=>p.name+"<br/>"+egp(p.value)},
    series:[{type:"sunburst", radius:[0,"88%"], center:["50%","50%"], data,
      label:{color:"#fff", fontSize:9, fontFamily:"Cairo, sans-serif", minAngle:12,
             formatter:o=>clip(10)(o.name)},
      itemStyle:{borderColor:"#0a0e1a", borderWidth:1}}]};
}

/* ------------------------------------------------------------- sankey ----- */

/* chSankey — MOBILE CHANGE: top 5 customers x 5 items instead of 8x8, and the
   flow runs vertically. A 16-node horizontal sankey at 390 px collapses its
   labels into overlapping slivers; 10 nodes top-to-bottom stays legible.
   Matching is by NAME, as in the source (duplicate names would merge). */
function sankey(X){
  const topC = [...X.customers].sort((a,c)=>c.sales-a.sales).slice(0,5).map(c=>c.customer_name);
  const topP = X.products.slice(0,5).map(p=>p.item_name);
  const cS = new Set(topC), pS = new Set(topP);
  const links = new Map();
  X.lines.forEach(l => {
    if(cS.has(l.customer_name) && pS.has(l.item_name)){
      const k = l.customer_name+"→"+l.item_name;
      links.set(k, (links.get(k)||0) + (l.line_total||0));
    }
  });
  const linkArr = [...links].map(([k,v])=>{ const [s,t] = k.split("→");
    return {source:s, target:t, value:Math.round(v)}; }).filter(l=>l.value>0);
  if(!linkArr.length) return EMPTY;
  const nodes = [...new Set([...topC, ...topP])].map(n=>({name:n}));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"item", valueFormatter:egp},
    series:[{type:"sankey", orient:"vertical", data:nodes, links:linkArr,
      top:24, bottom:14, left:8, right:8,
      emphasis:{focus:"adjacency"},
      lineStyle:{color:"gradient", opacity:.42},
      label:{color:b._ink, fontFamily:"Cairo, sans-serif", fontSize:9.5,
             position:"top", formatter:o=>clip(11)(o.name)},
      nodeGap:10, nodeWidth:12,
      itemStyle:{color:PAL[0], borderColor:"transparent"}}]};
}

/* ------------------------------------------------------------ heatmap ----- */

/* chHeatmap — rep x brand matrix. */
function heatmap(X){
  const reps = [...new Set(X.lines.map(l=>l.rep))];
  const brands = [...new Set(X.lines.map(l=>l.brand))];
  if(!reps.length || !brands.length) return EMPTY;
  const m = new Map();
  X.lines.forEach(l => { const k = l.rep+"|"+l.brand; m.set(k, (m.get(k)||0)+(l.line_total||0)); });
  const data = []; let mx = 0;
  reps.forEach((r,ri) => brands.forEach((br,bi) => {
    const v = Math.round(m.get(r+"|"+br)||0); mx = Math.max(mx,v); data.push([bi,ri,v]);
  }));
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip,
      formatter:p=>reps[p.data[1]]+" × "+brands[p.data[0]]+"<br/>"+egp(p.data[2])},
    grid:{...b.grid, bottom:52, left:4, top:20},
    xAxis: ax(b,{type:"category", data:brands, splitArea:{show:true},
                 axisLabel:{...ax(b).axisLabel, interval:0, fontSize:9.5, formatter:clip(9)}}),
    yAxis: ax(b,{type:"category", data:reps, splitArea:{show:true},
                 axisLabel:{...ax(b).axisLabel, formatter:clip(11), width:78, overflow:"truncate"}}),
    visualMap:{min:0, max:mx||1, calculable:true, orient:"horizontal", left:"center", bottom:0,
      itemHeight:70, textStyle:{color:b._muted, fontSize:9},
      inRange:{color:["#0d1220","#3b82f6","#8b5cf6","#ef4444"]}},
    series:[{type:"heatmap", data, label:{show:false},
      itemStyle:{borderColor:"#0a0e1a", borderWidth:1}}],
    _rows: reps, _cols: brands,
  };
}

/* ---------------------------------------------------------- histogram ----- */

/* chHistogram — the desktop's only Plotly chart. Binned here by hand so the
   4.7 MB Plotly bundle is not shipped. Same input set, same 30 bins. */
function histogram(X){
  const vals = X.invoices.filter(v => v.reported_total > 0).map(v => v.reported_total);
  if(vals.length < 2) return EMPTY;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const nb = 30, w = (hi - lo) / nb || 1;
  const bins = new Array(nb).fill(0);
  for(const v of vals) bins[Math.min(nb-1, Math.floor((v-lo)/w))]++;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"},
      formatter:p=>{ const i=p[0].dataIndex;
        return egpK(lo+i*w)+" – "+egpK(lo+(i+1)*w)+"<br/>"+int(p[0].value)+" فاتورة"; }},
    xAxis: ax(b,{type:"category", data:bins.map((_,i)=>Math.round(lo+i*w)),
      name:"قيمة الفاتورة", nameLocation:"middle", nameGap:24,
      nameTextStyle:{color:b._muted, fontSize:10},
      axisLabel:{...ax(b).axisLabel, interval:Math.floor(nb/5), formatter:egpK}}),
    yAxis: ax(b,{type:"value", name:"عدد الفواتير",
                 nameTextStyle:{color:b._muted, fontSize:10}}),
    series:[{type:"bar", data:bins, barCategoryGap:"6%",
      itemStyle:{color:PAL[0], borderColor:PAL[1], borderWidth:.5}}]};
}

/* ---------------------------------------------- collections-only charts --- */

/* co_monthly — sales vs collections vs returns, full 2026, month-invariant. */
function collectionsMonthly(D, filters){
  const bmonth = groupSum((D.invoices||[]).filter(v=>v.month>="2026-01"), "month", "reported_total");
  const cmonth = new Map(), rmonth = new Map();
  ((D.collections&&D.collections.monthly)||[]).forEach(m=>{
    cmonth.set(m.month, m.collected); rmonth.set(m.month, m.returns);
  });
  const months = [...new Set([...bmonth.keys(), ...cmonth.keys(), ...rmonth.keys()])].sort();
  if(!months.length) return EMPTY;
  const cm = (filters.month && filters.month !== "all") ? filters.month : null;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", valueFormatter:egp},
    legend:{...b.legend, data:["المبيعات","التحصيل","المرتجعات"]},
    xAxis: ax(b,{type:"category", data:months,
                 axisLabel:{...ax(b).axisLabel, rotate:45, fontSize:9}}),
    yAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    series:[
      {name:"المبيعات", type:"bar", itemStyle:{color:PAL[0]},
       data:months.map(m=>Math.round(bmonth.get(m)||0))},
      {name:"التحصيل", type:"bar", itemStyle:{color:PAL[2]},
       data:months.map(m=>Math.round(cmonth.get(m)||0))},
      {name:"المرتجعات", type:"line", smooth:true, symbolSize:5,
       lineStyle:{width:2.4, color:PAL[4]}, itemStyle:{color:PAL[4]},
       data:months.map(m=>Math.round(rmonth.get(m)||0)),
       markLine: cm ? {symbol:"none", data:[{xAxis:cm}],
         lineStyle:{color:PAL[3], type:"dashed"},
         label:{show:true, formatter:"المحدد", fontSize:9, color:PAL[3]}} : undefined},
    ]};
}

/* co_rep — collections vs returns by rep, top 12 by collected. */
function collectionsByRep(D, filters){
  const f = filters, mAll = !f.month || f.month === "all";
  const flt = r => (mAll || r.month===f.month) && (!f.rep || r.rep===f.rep)
                && (!f.customer || String(r.customer_code)===String(f.customer));
  const recs = ((D.collections&&D.collections.receipts)||[]).filter(flt);
  const rets = ((D.collections&&D.collections.returns_rows)||[]).filter(flt);
  const repC = groupSum(recs,"rep","amount"), repR = groupSum(rets,"rep","value");
  const reps = [...new Set([...repC.keys(), ...repR.keys()])]
    .sort((a,c)=>(repC.get(c)||0)-(repC.get(a)||0)).slice(0,12).reverse();
  if(!reps.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"}, valueFormatter:egp},
    legend:{...b.legend, data:["التحصيل","المرتجعات"]},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"category", data:reps,
                 axisLabel:{...ax(b).axisLabel, formatter:clip(12), width:84, overflow:"truncate"}}),
    series:[
      {name:"التحصيل", type:"bar", itemStyle:{color:PAL[2]},
       data:reps.map(r=>Math.round(repC.get(r)||0))},
      {name:"المرتجعات", type:"bar", itemStyle:{color:PAL[4]},
       data:reps.map(r=>Math.round(repR.get(r)||0))},
    ]};
}

/* co_bottom — worst 15 collection rates, RAG at 0.9 / 0.7. */
function worstCollectors(X){
  const bottom = X.customers.filter(c => c.collection_rate != null)
    .sort((a,c)=>a.collection_rate-c.collection_rate).slice(0,15).reverse();
  if(!bottom.length) return EMPTY;
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"},
      valueFormatter:v=>pct(v)},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", max:1, axisLabel:{...ax(b).axisLabel, formatter:x=>pct(x,0)}}),
    yAxis: ax(b,{type:"category", data:bottom.map(c=>c.customer_name),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(13), width:90, overflow:"truncate"}}),
    series:[{type:"bar", data:bottom.map(c=>c.collection_rate),
      itemStyle:{borderRadius:[0,5,5,0],
        color:p=>p.value>=.9?PAL[2]:p.value>=.7?PAL[3]:PAL[4]}}],
    _codes: bottom.map(c=>c.customer_code),
  };
}

/* ------------------------------------------------- AR movement (new) ------ */

/* Not a desktop chart: the desktop only ever holds ONE snapshot, so it cannot
   compare two. Given two payloads it diffs the AR ledger per customer. */
function arMovement(Dfrom, Dto){
  const a = new Map(((Dfrom.receivables&&Dfrom.receivables.rows)||[])
    .map(r=>[String(r.customer_code), r]));
  const bm = new Map(((Dto.receivables&&Dto.receivables.rows)||[])
    .map(r=>[String(r.customer_code), r]));
  const rows = [];
  let rose=0, fell=0, added=0, cleared=0, dRose=0, dFell=0, dAdded=0, dCleared=0;
  for(const [code, rb] of bm){
    const ra = a.get(code);
    if(!ra){ rows.push({code, name:rb.customer_name, rep:rb.rep, from:0, to:rb.outstanding,
                        delta:rb.outstanding, kind:"new"});
             added++; dAdded += rb.outstanding; continue; }
    const d = rb.outstanding - ra.outstanding;
    rows.push({code, name:rb.customer_name, rep:rb.rep, from:ra.outstanding, to:rb.outstanding,
               delta:d, kind: d>1 ? "up" : d<-1 ? "down" : "flat"});
    if(d>1){ rose++; dRose+=d; } else if(d<-1){ fell++; dFell+=d; }
  }
  for(const [code, ra] of a) if(!bm.has(code)){
    rows.push({code, name:ra.customer_name, rep:ra.rep, from:ra.outstanding, to:0,
               delta:-ra.outstanding, kind:"cleared"});
    cleared++; dCleared -= ra.outstanding;
  }
  rows.sort((x,y)=>Math.abs(y.delta)-Math.abs(x.delta));
  const totFrom = (Dfrom.receivables||{}).total_outstanding || 0;
  const totTo   = (Dto.receivables||{}).total_outstanding || 0;
  return {rows, totFrom, totTo, netDelta: totTo-totFrom,
          rose, fell, added, cleared, dRose, dFell, dAdded, dCleared,
          /* the per-customer deltas must account for the headline move */
          reconDelta: rows.reduce((s,r)=>s+r.delta, 0) - (totTo-totFrom)};
}

function arMovementChart(mv){
  if(!mv.rows.length) return EMPTY;
  const top = mv.rows.slice(0,12).reverse();
  const b = ecBase();
  return {...b,
    tooltip:{...b.tooltip, trigger:"axis", axisPointer:{type:"shadow"},
      formatter:p=>{ const r=top[p[0].dataIndex];
        return r.name+"<br/>من "+egp(r.from)+" إلى "+egp(r.to)
             + "<br/>الفرق: "+(r.delta>=0?"+":"")+egp(r.delta); }},
    grid:{...b.grid, left:4},
    xAxis: ax(b,{type:"value", axisLabel:{...ax(b).axisLabel, formatter:egpK}}),
    yAxis: ax(b,{type:"category", data:top.map(r=>r.name),
                 axisLabel:{...ax(b).axisLabel, formatter:clip(13), width:90, overflow:"truncate"}}),
    series:[{type:"bar", data:top.map(r=>Math.round(r.delta)),
      itemStyle:{color:p=>p.value>=0?PAL[4]:PAL[2],
                 borderRadius:p=>p.value>=0?[0,5,5,0]:[5,0,0,5]}}],
    _codes: top.map(r=>r.code),
  };
}

return {ecBase,isEmpty,H,monthly,daily,variance,topCustomers,topProducts,byRep,agingBar,bonusDist,agingWaterfall,salesWaterfall,pareto,donut,gauge,treemap,priceBox,scatter,radar,sunburst,sankey,heatmap,histogram,collectionsMonthly,collectionsByRep,worstCollectors,arMovement,arMovementChart};
})();
/* Hosts one ECharts instance. SVG renderer: crisp on high-DPI phones, no
   devicePixelRatio sizing bugs, and it survives printing. The instance is
   disposed on unmount -- React swaps section subtrees wholesale, and a leaked
   instance keeps a resize listener alive against a detached node. */
/* Live EChart instances, in mount order. dash-export.js walks this to turn the
   chart the user is looking at into a PNG or an SVG; nothing else reads it.
   Entries are removed on unmount, so a disposed instance is never exported. */
const REGISTRY = [];

class EChart extends React.Component {
  componentDidMount(){
    REGISTRY.push(this);
    this.draw();
    this.onResize = () => { if(this.inst) this.inst.resize(); };
    window.addEventListener("resize", this.onResize);
  }
  componentDidUpdate(prev){ if(prev.option !== this.props.option) this.draw(); }
  componentWillUnmount(){
    window.removeEventListener("resize", this.onResize);
    const i = REGISTRY.indexOf(this);
    if(i >= 0) REGISTRY.splice(i, 1);
    if(this.inst){ this.inst.dispose(); this.inst = null; }
  }
  draw(){
    const el = this.el, o = this.props.option;
    if(!el || !o || typeof echarts === "undefined") return;
    if(!this.inst) this.inst = echarts.init(el, null, {renderer:"svg"});
    /* notMerge: option shapes differ between builders (axis arrays, visualMap),
       so a merge would leave stale components behind. */
    this.inst.setOption(o, true);
    this.inst.off("click");
    if(this.props.onPick) this.inst.on("click", p => this.props.onPick(p, o));
  }
  render(){
    return React.createElement("div",{ref:e=>this.el=e,
      "data-chart-title":this.props.title||null,
      style:{width:"100%", height:(this.props.h||300), touchAction:"pan-y"}});
  }
}
