function renderBrand(){
  return `
  <section class="panel" id="brand">
    <h2 class="panel-title">لوحة أداء العلامات التجارية</h2>
    <p class="panel-sub">3 علامات تجارية نشطة: الهنا، أبوهاشم، اسبشيال (وفقًا لملف «تصنيف الأصناف كبراند»).</p>

    <div class="grid kpi" style="margin-bottom:18px;" id="br-kpis"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>الإيراد الشهري لكل علامة تجارية</h3>
        <div class="chart-wrap tall"><canvas id="br-trend"></canvas></div>
      </div>
      <div class="card">
        <h3>حصة العلامات التجارية من إجمالي الإيراد</h3>
        <div class="chart-wrap tall"><canvas id="br-share"></canvas></div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>متوسط سعر البيع (ASP) الشهري لكل علامة تجارية</h3>
      <div class="chart-wrap"><canvas id="br-asp"></canvas></div>
      <div class="note">يُحتسب كـ (صافي المبيعات ÷ الكمية المباعة) شهريًا لكل علامة — يعكس مزيج الأصناف وتغيّرات الأسعار معًا، وليس تغيّر السعر المعلن لصنف واحد بعينه.</div>
    </div>

    <div class="card">
      <h3>توقع الإيراد لكل علامة تجارية — 7 أشهر مقبلة (نموذج Holt)</h3>
      <div class="small-mult-grid" id="br-forecast-grid"></div>
    </div>
  </section>`;
}

function mountBrand(){
  const brand = D.brand_summary, fin = D.financial;
  const brandColors = {'الهنا':'#2a78d6','ابوهاشم':'#1baf7a','اسبشيال':'#eda100','غير مصنف':'#898781'};

  document.getElementById('br-kpis').innerHTML = brand.filter(b=>b.brand!=='غير مصنف').map(b=>[
    b.brand, fmtEGP(b.revenue), fmtPct(b.revenue_share_pct)+' من الإيراد · '+fmt0(b.n_customers)+' عميلاً'
  ]).map(([label,value,sub])=>`<div class="card"><div class="label">${label}</div><div class="value">${value}</div><div class="delta muted">${sub}</div></div>`).join('')
   + `<div class="card"><div class="label">مؤشر تركّز العلامات (HHI)</div><div class="value">${fmt0(fin.hhi_brands)}</div><div class="delta critical">تركّز مرتفع</div></div>`;

  const months = D.monthly_series.map(r=>r.month);
  const bmRev = D.brand_month_revenue;
  const brands3 = ['الهنا','ابوهاشم','اسبشيال'];
  new Chart(document.getElementById('br-trend'), {
    type:'line',
    data:{ labels: months.map(monthAr), datasets: brands3.map(b=>({
      label:b, data: months.map(mo=>{ const r=bmRev.find(x=>x.month===mo && x.brand===b); return r? r.line_total: 0; }),
      borderColor: brandColors[b], backgroundColor: brandColors[b], tension:.25, pointRadius:2, borderWidth:2.5,
    }))},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ y:{ ticks:{callback:v=>fmt0(v)} } } }
  });

  new Chart(document.getElementById('br-share'), {
    type:'doughnut',
    data:{ labels: brand.map(b=>b.brand), datasets:[{data: brand.map(b=>b.revenue), backgroundColor: brand.map(b=>brandColors[b.brand]||'#898781')}]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}} }
  });

  const aspData = D.asp_by_brand_month;
  new Chart(document.getElementById('br-asp'), {
    type:'line',
    data:{ labels: months.map(monthAr), datasets: brands3.map(b=>({
      label:b, data: months.map(mo=>{ const r=aspData.find(x=>x.month===mo && x.brand===b); return r? r.avg_selling_price: null; }),
      borderColor: brandColors[b], backgroundColor: brandColors[b], tension:.25, pointRadius:2, borderWidth:2.5,
    }))},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}},
      scales:{ y:{ ticks:{callback:v=>fmt2(v)} } } }
  });

  const disagg = D.forecast_disagg;
  const grid = document.getElementById('br-forecast-grid');
  grid.innerHTML = brands3.map(b=>`<div class="card"><h3 style="font-size:13px;">${b}</h3><div class="chart-wrap short"><canvas id="br-fc-${b}"></canvas></div></div>`).join('');
  brands3.forEach(b=>{
    const hist = disagg.brands[b].historical;
    const fcRows = disagg.brands[b].forecast;
    const labels = disagg.months_historical.map(monthAr).concat(disagg.months_future.map(monthAr));
    const histSeries = hist.concat(Array(fcRows.length).fill(null));
    const baseSeries = Array(hist.length-1).fill(null).concat([hist[hist.length-1]]).concat(fcRows.map(r=>r.base_case));
    new Chart(document.getElementById(`br-fc-${b}`), {
      type:'line',
      data:{ labels, datasets:[
        {label:'فعلي', data: histSeries, borderColor: brandColors[b], pointRadius:1, borderWidth:2},
        {label:'توقع', data: baseSeries, borderColor:'#eb6834', borderDash:[5,3], pointRadius:1, borderWidth:2},
      ]},
      options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
        scales:{ x:{ ticks:{display:false} }, y:{ ticks:{callback:v=>fmt0(v)} } } }
    });
  });
}
