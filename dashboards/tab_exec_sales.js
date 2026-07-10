function renderExecSales(){
  return `
  <section class="panel" id="exec-sales">
    <h2 class="panel-title">لوحة المبيعات التنفيذية</h2>
    <p class="panel-sub">أعلى/أدنى الأداء، تحليل باريتو 80/20، وشجرة التحليل الهرمي القابلة للتوسيع (عميل ← علامة تجارية ← صنف).</p>

    <div class="grid kpi" style="margin-bottom:18px;" id="es-kpis"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>أعلى 10 عملاء بالإيراد</h3>
        <div class="chart-wrap tall"><canvas id="es-top-cust"></canvas></div>
      </div>
      <div class="card">
        <h3>أعلى 10 أصناف بالإيراد</h3>
        <div class="chart-wrap tall"><canvas id="es-top-item"></canvas></div>
      </div>
    </div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>تحليل باريتو 80/20 — تركّز الإيراد على العملاء</h3>
        <div class="chart-wrap"><canvas id="es-pareto-cust"></canvas></div>
        <div class="note" id="es-pareto-cust-note"></div>
      </div>
      <div class="card">
        <h3>تحليل باريتو 80/20 — تركّز الإيراد على الأصناف</h3>
        <div class="chart-wrap"><canvas id="es-pareto-item"></canvas></div>
        <div class="note" id="es-pareto-item-note"></div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>خريطة حصص الإيراد (Treemap): العلامة التجارية ← الصنف</h3>
      <div class="treemap" id="es-treemap"></div>
    </div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>أدنى 10 أصناف أداءً (من ذوات الحركة الفعلية)</h3>
        <div class="scroll-x"><table id="es-bottom-table"></table></div>
        <div class="note">مستبعد منها الأصناف نادرة التكرار (أقل من 5 عمليات بيع) لتفادي ضوضاء العيّنات الصغيرة.</div>
      </div>
      <div class="card">
        <h3>الإيراد الشهري وعدد الفواتير</h3>
        <div class="chart-wrap tall"><canvas id="es-monthly"></canvas></div>
      </div>
    </div>

    <div class="card">
      <h3>الشجرة الهرمية للمبيعات: عميل ← علامة تجارية ← صنف</h3>
      <input class="search" id="es-tree-search" placeholder="ابحث باسم العميل...">
      <div class="tree" id="es-tree"></div>
      <div class="note">تُعرض القيم: الكمية، صافي المبيعات، متوسط السعر، نسبة المساهمة من إجمالي الإيراد، ونمو آخر 3 أشهر مقابل الـ3 أشهر السابقة لها (عند توفر بيانات كافية). القائمة مرتّبة تنازليًا حسب المبيعات ومطوية افتراضيًا؛ اضغط للتوسيع.</div>
    </div>
  </section>`;
}

function mountExecSales(){
  const cust = D.customer_pareto, items = D.item_abc_xyz, brand = D.brand_summary, fin = D.financial, m = D.monthly_series;

  document.getElementById('es-kpis').innerHTML = [
    ['عدد العملاء النشطين', fmt0(D.eda_summary.n_customers), ''],
    ['عدد الأصناف المباعة', fmt0(D.eda_summary.n_items), ''],
    ['عدد العلامات التجارية', '3', 'أبوهاشم، الهنا، اسبشيال'],
    ['متوسط قيمة الفاتورة', fmtEGP(m.reduce((a,r)=>a+r.revenue_per_invoice,0)/m.length), 'متوسط 18 شهرًا'],
  ].map(([label,value,sub])=>`<div class="card"><div class="label">${label}</div><div class="value">${value}</div>${sub?`<div class="delta muted">${sub}</div>`:''}</div>`).join('');

  const top10c = [...cust].sort((a,b)=>b.line_total-a.line_total).slice(0,10);
  new Chart(document.getElementById('es-top-cust'), {
    type:'bar', data:{ labels: top10c.map(r=>r.customer_name), datasets:[{data: top10c.map(r=>r.line_total), backgroundColor:'#2a78d6'}]},
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>fmtEGP(c.raw)}}}, scales:{x:{ticks:{callback:v=>fmt0(v)}}} }
  });

  const top10i = [...items].sort((a,b)=>b.line_total-a.line_total).slice(0,10);
  new Chart(document.getElementById('es-top-item'), {
    type:'bar', data:{ labels: top10i.map(r=>r.item_name_canonical), datasets:[{data: top10i.map(r=>r.line_total), backgroundColor:'#1baf7a'}]},
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>fmtEGP(c.raw)}}}, scales:{x:{ticks:{callback:v=>fmt0(v)}}} }
  });

  function paretoChart(canvasId, rows, labelKey){
    const top30 = rows.slice(0,30);
    new Chart(document.getElementById(canvasId), {
      data:{ labels: top30.map(r=>r[labelKey]), datasets:[
        {type:'bar', label:'إيراد', data: top30.map(r=>r.line_total), backgroundColor:'#2a78d6', order:2, yAxisID:'y'},
        {type:'line', label:'نسبة تراكمية %', data: top30.map(r=>r.cum_pct), borderColor:'#e34948', yAxisID:'y1', pointRadius:1, borderWidth:2, order:1},
      ]},
      options:{ responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
        plugins:{legend:{position:'bottom'}},
        scales:{
          x:{ ticks:{ display:false } },
          y:{ ticks:{ callback:v=>fmt0(v) } },
          y1:{ position:'right', min:0, max:100, ticks:{ callback:v=>v+'%' }, grid:{drawOnChartArea:false} },
        } }
    });
  }
  paretoChart('es-pareto-cust', cust, 'customer_name');
  paretoChart('es-pareto-item', items, 'item_name_canonical');
  const nA_c = cust.filter(r=>r.abc_class==='A').length;
  document.getElementById('es-pareto-cust-note').textContent =
    `${nA_c} عميلاً (فئة A) يمثلون 80% من الإيراد من أصل ${cust.length} عميلاً — تركّز مرتفع نسبيًا على عدد محدود من الحسابات.`;
  const nA_i = items.filter(r=>r.abc_class==='A').length;
  document.getElementById('es-pareto-item-note').textContent =
    `${nA_i} صنفًا (فئة A) يمثلون 80% من الإيراد من أصل ${items.length} صنفًا مباعًا فعليًا.`;

  // Treemap: brand -> item (slice & dice, area proportional to revenue share)
  const treemapData = {};
  items.forEach(it=>{ (treemapData[it.brand] = treemapData[it.brand]||[]).push(it); });
  const brandOrder = Object.keys(treemapData).sort((a,b)=> treemapData[b].reduce((s,x)=>s+x.line_total,0)-treemapData[a].reduce((s,x)=>s+x.line_total,0));
  const totalRev = items.reduce((s,x)=>s+x.line_total,0);
  const brandColors = {'الهنا':'#2a78d6','ابوهاشم':'#1baf7a','اسبشيال':'#eda100','غير مصنف':'#898781'};
  const tmEl = document.getElementById('es-treemap');
  tmEl.innerHTML = brandOrder.map(b=>{
    const rows = treemapData[b].sort((x,y)=>y.line_total-x.line_total).slice(0,8);
    const brandRev = treemapData[b].reduce((s,x)=>s+x.line_total,0);
    const widthPct = (brandRev/totalRev*100).toFixed(2);
    const inner = rows.map(it=>{
      const h = Math.max(8, (it.line_total/brandRev*100));
      return `<div class="cell" style="height:${h}%;background:${brandColors[b]||'#898781'};opacity:${0.55+0.45*(it.line_total/rows[0].line_total)};" title="${it.item_name_canonical}: ${fmt0(it.line_total)} ج.م">${it.item_name_canonical.slice(0,22)}</div>`;
    }).join('');
    return `<div style="width:${widthPct}%;min-width:140px;display:flex;flex-direction:column;gap:2px;">${inner}</div>`;
  }).join('');

  // Bottom performers (items with >=5 lines, lowest revenue)
  const dimItems = D.dim_items.filter(d=>d.n_lines>=5);
  const bottom10 = [...dimItems].sort((a,b)=>a.total_revenue-b.total_revenue).slice(0,10);
  document.getElementById('es-bottom-table').innerHTML = `
    <tr><th>الصنف</th><th>العلامة</th><th>الإيراد</th><th>الكمية</th></tr>
    ${bottom10.map(r=>`<tr><td>${r.item_name}</td><td>${r.brand}</td><td>${fmtEGP(r.total_revenue)}</td><td>${fmt0(r.total_qty)}</td></tr>`).join('')}
  `;

  new Chart(document.getElementById('es-monthly'), {
    data:{ labels: m.map(r=>monthAr(r.month)), datasets:[
      {type:'bar', label:'الإيراد', data:m.map(r=>r.revenue), backgroundColor:'#2a78d6', yAxisID:'y'},
      {type:'line', label:'عدد الفواتير', data:m.map(r=>r.n_invoices), borderColor:'#eb6834', yAxisID:'y1', pointRadius:2, borderWidth:2},
    ]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ y:{ ticks:{callback:v=>fmt0(v)} }, y1:{ position:'right', grid:{drawOnChartArea:false} } } }
  });

  // Hierarchy tree
  const treeData = D.hierarchy_tree;
  function renderTree(filter){
    const q = (filter||'').trim();
    const rows = q ? treeData.filter(c=>c.name.includes(q)) : treeData.slice(0,80);
    return rows.map(c=>{
      const brandsSorted = Object.entries(c.brands).sort((a,b)=>b[1].sales-a[1].sales);
      const brandHtml = brandsSorted.map(([bname,b])=>{
        const itemsSorted = [...b.items].sort((x,y)=>y.sales-x.sales);
        const itemHtml = itemsSorted.map(it=>`
          <div class="level-3">
            <div style="display:flex;justify-content:space-between;">
              <span>${it.name}</span>
              <span class="node-meta">كمية ${fmt0(it.qty)} · ${fmtEGP(it.sales)} · متوسط سعر ${it.avg_price?fmt2(it.avg_price):'—'} · مساهمة ${fmt2(it.contribution_pct)}% ${it.growth_pct!=null?('· نمو '+fmt1(it.growth_pct)+'%'):''}</span>
            </div>
          </div>`).join('');
        return `<details class="level-2"><summary><span class="node-name">${bname}</span><span class="node-meta">${fmtEGP(b.sales)}</span></summary>${itemHtml}</details>`;
      }).join('');
      return `<details><summary><span class="node-name">${c.name}</span><span class="node-meta">${fmtEGP(c.sales)}</span></summary>${brandHtml}</details>`;
    }).join('');
  }
  document.getElementById('es-tree').innerHTML = renderTree('');
  document.getElementById('es-tree-search').addEventListener('input', (e)=>{
    document.getElementById('es-tree').innerHTML = renderTree(e.target.value);
  });
}
