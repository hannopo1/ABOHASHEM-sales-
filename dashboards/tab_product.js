function renderProduct(){
  return `
  <section class="panel" id="product">
    <h2 class="panel-title">لوحة أداء المنتجات (الأصناف)</h2>
    <p class="panel-sub">تصنيف ABC (حجم الإيراد) × XYZ (استقرار الطلب) على مستوى الصنف، مع اتجاهات السعر والكمية لأهم 10 أصناف.</p>

    <div class="grid kpi" style="margin-bottom:18px;" id="pr-kpis"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>مصفوفة ABC/XYZ للأصناف (فقاعة = حصة الإيراد)</h3>
        <div class="chart-wrap tall"><canvas id="pr-scatter"></canvas></div>
        <div class="note">المحور الأفقي: ترتيب الصنف بالإيراد (1 = الأعلى). المحور الرأسي: معامل اختلاف الكمية الشهرية (كلما ارتفع، زاد تذبذب الطلب). اللون يمثل فئة ABC.</div>
      </div>
      <div class="card">
        <h3>أعلى 15 صنفًا بالإيراد</h3>
        <div class="chart-wrap tall"><canvas id="pr-top15"></canvas></div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>اتجاه الإيراد الشهري لأهم 10 أصناف</h3>
      <div class="chart-wrap tall"><canvas id="pr-trend"></canvas></div>
    </div>

    <div class="card">
      <h3>متوسط سعر البيع الشهري (ASP) لأهم 6 أصناف</h3>
      <div class="chart-wrap tall"><canvas id="pr-asp"></canvas></div>
      <div class="note">يعكس التسعير الفعلي المحقق شهريًا لكل صنف (صافي القيمة ÷ الكمية)، ويشمل أثر التفاوض السعري لكل عميل ونسب الاستقطاع.</div>
    </div>
  </section>`;
}

function mountProduct(){
  const items = D.item_abc_xyz;
  document.getElementById('pr-kpis').innerHTML = [
    ['عدد الأصناف المباعة فعليًا', fmt0(items.length), ''],
    ['أصناف فئة A', fmt0(items.filter(i=>i.abc_class==='A').length), 'تمثل 80% من الإيراد'],
    ['أصناف بتذبذب طلب مرتفع (Z)', fmt0(items.filter(i=>i.xyz_class==='Z').length), 'تحتاج مخزون أمان أعلى'],
    ['حصة أعلى 10 أصناف', fmtPct(D.financial.top10_item_share_pct), 'من إجمالي الإيراد'],
  ].map(([label,value,sub])=>`<div class="card"><div class="label">${label}</div><div class="value">${value}</div>${sub?`<div class="delta muted">${sub}</div>`:''}</div>`).join('');

  const abcColor = {A:'#2a78d6', B:'#eda100', C:'#898781'};
  const totalRev = items.reduce((s,i)=>s+i.line_total,0);
  new Chart(document.getElementById('pr-scatter'), {
    type:'bubble',
    data:{ datasets: ['A','B','C'].map(cls=>({
      label:'فئة '+cls,
      data: items.filter(i=>i.abc_class===cls).map(i=>({x:i.rank, y: i.cv_qty||0, r: Math.max(4, Math.sqrt(i.line_total/totalRev)*90)})),
      backgroundColor: abcColor[cls]+'99', borderColor: abcColor[cls],
    }))},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ x:{ title:{display:true,text:'ترتيب الصنف بالإيراد'} }, y:{ title:{display:true,text:'معامل اختلاف الكمية الشهرية'} } } }
  });

  const top15 = [...items].sort((a,b)=>b.line_total-a.line_total).slice(0,15);
  new Chart(document.getElementById('pr-top15'), {
    type:'bar',
    data:{ labels: top15.map(i=>i.item_name_canonical), datasets:[{data: top15.map(i=>i.line_total),
      backgroundColor: top15.map(i=>abcColor[i.abc_class])}]},
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>fmtEGP(c.raw)}}}, scales:{x:{ticks:{callback:v=>fmt0(v)}}} }
  });

  const itemMonth = D.item_month_series;
  const months = D.monthly_series.map(r=>r.month);
  const top10Names = Object.keys(itemMonth);
  new Chart(document.getElementById('pr-trend'), {
    type:'line',
    data:{ labels: months.map(monthAr), datasets: top10Names.slice(0,6).map((name,idx)=>({
      label: name.length>28? name.slice(0,28)+'…': name,
      data: months.map(mo=>{ const row=(itemMonth[name]||[]).find(r=>r.month===mo); return row? row.revenue: 0; }),
      borderColor: PALETTE[idx%PALETTE.length], backgroundColor: PALETTE[idx%PALETTE.length],
      tension:.25, pointRadius:1.5, borderWidth:2,
    }))},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ y:{ ticks:{callback:v=>fmt0(v)} } } }
  });

  new Chart(document.getElementById('pr-asp'), {
    type:'line',
    data:{ labels: months.map(monthAr), datasets: top10Names.slice(0,6).map((name,idx)=>({
      label: name.length>28? name.slice(0,28)+'…': name,
      data: months.map(mo=>{ const row=(itemMonth[name]||[]).find(r=>r.month===mo); return row? row.asp: null; }),
      borderColor: PALETTE[idx%PALETTE.length], backgroundColor: PALETTE[idx%PALETTE.length],
      tension:.25, pointRadius:1.5, borderWidth:2,
    }))},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ y:{ ticks:{callback:v=>fmt2(v)} } } }
  });
}
