function renderExecFinancial(){
  return `
  <section class="panel" id="exec-fin">
    <h2 class="panel-title">اللوحة المالية التنفيذية</h2>
    <p class="panel-sub">جميع الأرقام مُحتسبة من فواتير المبيعات الفعلية (18 شهرًا: يناير 2025 – يونيو 2026) ولقطة مديونية العملاء بتاريخ 2026/7/4. لا توجد بيانات تكلفة في الملفات المرفوعة، لذلك لا يظهر هامش ربح أو EBITDA (انظر الملاحظة أسفل الصفحة).</p>

    <div class="grid kpi" id="ef-kpis" style="margin-bottom:18px;"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>اتجاه المبيعات الشهرية + تنبؤ 7 أشهر</h3>
        <div class="chart-wrap tall"><canvas id="ef-trend"></canvas></div>
        <div class="note">الخط المتصل: مبيعات فعلية. الخط المنقط: التوقع الأساسي (نموذج Holt). النطاق المظلل: فترة الثقة 95%. التفاصيل الكاملة في تبويب «التنبؤ».</div>
      </div>
      <div class="card">
        <h3>معدل النمو السنوي (YoY) شهريًا</h3>
        <div class="chart-wrap tall"><canvas id="ef-yoy"></canvas></div>
        <div class="note">متاح فقط للأشهر التي توجد لها بيانات مقارنة من العام السابق (يناير–يونيو 2026 مقابل 2025).</div>
      </div>
    </div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>جسر الإيرادات: من القيمة الاسمية إلى صافي الفاتورة</h3>
        <div class="chart-wrap"><canvas id="ef-waterfall"></canvas></div>
        <div class="note" id="ef-waterfall-note"></div>
      </div>
      <div class="card">
        <h3>رصيد المديونية حسب المندوب (2026/7/4)</h3>
        <div class="chart-wrap"><canvas id="ef-ar"></canvas></div>
      </div>
    </div>

    <div class="grid three">
      <div class="callout info">
        <b>تركّز المخاطر (HHI):</b><br>
        العملاء: <b id="ef-hhi-cust"></b> — منافسة (غير مركّز)<br>
        العلامات التجارية: <b id="ef-hhi-brand"></b> — تركّز مرتفع<br>
        الأصناف: <b id="ef-hhi-item"></b> — تركّز متوسط
        <div class="note">مقياس Herfindahl-Hirschman: أقل من 1500 = غير مركّز، 1500–2500 = متوسط، أعلى من 2500 = مرتفع (معيار وزارة العدل الأمريكية المستخدم كمرجع تحليلي قياسي).</div>
      </div>
      <div class="callout info">
        <b>أيام الذمم المدينة (DSO) التقريبية:</b> <span id="ef-dso"></span> يومًا
        <div class="note" id="ef-dso-note"></div>
      </div>
      <div class="callout warn">
        <b>بنود غير قابلة للاحتساب (غياب بيانات التكلفة):</b>
        <div class="note" id="ef-missing-list"></div>
      </div>
    </div>
  </section>`;
}

function mountExecFinancial(){
  const fin = D.financial, eda = D.eda_summary, m = D.monthly_series, fc = D.forecast;

  document.getElementById('ef-kpis').innerHTML = [
    ['إجمالي الإيرادات (18 شهرًا)', fmtEGP(fin.total_revenue_egp), 'من '+fin.period.start+' إلى '+fin.period.end],
    ['إيرادات آخر 12 شهرًا', fmtEGP(fin.trailing_12m_revenue_egp), ''],
    ['متوسط الإيراد الشهري (آخر 12 شهرًا)', fmtEGP(fin.avg_monthly_revenue_t12_egp), ''],
    ['رصيد المديونية الصافي', fmtEGP(fin.ar_total_net_balance_egp), 'لقطة 2026/7/4'],
    ['نسبة الاستقطاع الإجمالية', fmtPct(fin.aggregate_deduction_rate_pct), 'من القيمة الاسمية'],
    ['حصة أعلى 10 عملاء', fmtPct(fin.top10_customer_share_pct), 'من إجمالي الإيرادات'],
  ].map(([label,value,sub])=>`
    <div class="card"><div class="label">${label}</div><div class="value">${value}</div>
    ${sub?`<div class="delta muted">${sub}</div>`:''}</div>
  `).join('');

  // Trend + forecast chart
  const histMonths = m.map(r=>monthAr(r.month));
  const histRev = m.map(r=>r.revenue);
  const fcMonths = fc.forecast_company_revenue.map(r=>monthAr(r.month));
  const allMonths = histMonths.concat(fcMonths);
  const histSeries = histRev.concat(Array(fcMonths.length).fill(null));
  const baseSeries = Array(histRev.length-1).fill(null).concat([histRev[histRev.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.base_case));
  const upperSeries = Array(histRev.length-1).fill(null).concat([histRev[histRev.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.optimistic_case));
  const lowerSeries = Array(histRev.length-1).fill(null).concat([histRev[histRev.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.conservative_case));

  new Chart(document.getElementById('ef-trend'), {
    type:'line',
    data:{ labels: allMonths, datasets:[
      {label:'مبيعات فعلية', data: histSeries, borderColor:'#2a78d6', backgroundColor:'#2a78d6', tension:.25, pointRadius:2, borderWidth:2.5},
      {label:'نطاق الثقة 95%', data: upperSeries, borderColor:'transparent', backgroundColor:'rgba(42,120,214,0.12)', fill:'+1', pointRadius:0, borderWidth:0},
      {label:'الحد الأدنى', data: lowerSeries, borderColor:'transparent', backgroundColor:'rgba(42,120,214,0.12)', fill:false, pointRadius:0, borderWidth:0},
      {label:'توقع أساسي', data: baseSeries, borderColor:'#eb6834', borderDash:[6,4], pointRadius:2, borderWidth:2.5, fill:false},
    ]},
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{legend:{position:'bottom', labels:{filter: (item)=> item.text!=='الحد الأدنى'}}},
      scales:{ y:{ ticks:{ callback:v=>fmt0(v) } } } }
  });

  // YoY chart
  const yoyRows = m.filter(r=>r.yoy_growth_pct!=null);
  new Chart(document.getElementById('ef-yoy'), {
    type:'bar',
    data:{ labels: yoyRows.map(r=>monthAr(r.month)), datasets:[{
      label:'نمو سنوي %', data: yoyRows.map(r=>r.yoy_growth_pct),
      backgroundColor: yoyRows.map(r=> r.yoy_growth_pct>=0? '#1baf7a':'#e34948')
    }]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
      scales:{ y:{ ticks:{ callback:v=>v+'%' } } } }
  });

  // Waterfall (Gross -> Deductions -> Net)
  const gross = fin.gross_list_value_egp, ded = fin.aggregate_deduction_value_egp, net = fin.net_invoiced_value_egp;
  new Chart(document.getElementById('ef-waterfall'), {
    type:'bar',
    data:{ labels:['القيمة الاسمية (الكمية × السعر)','الاستقطاعات التجارية','صافي الفاتورة'],
      datasets:[
        {label:'قاعدة', data:[0, net, 0], backgroundColor:'transparent', stack:'s'},
        {label:'القيمة', data:[gross, ded, net], backgroundColor:['#2a78d6','#e34948','#1baf7a'], stack:'s'},
      ]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:(c)=> c.datasetIndex===1? fmtEGP(c.raw): ''}}},
      scales:{ y:{ ticks:{ callback:v=>fmt0(v) } } } }
  });
  document.getElementById('ef-waterfall-note').textContent =
    `القيمة الاسمية ${fmtEGP(gross)} − استقطاعات ${fmtEGP(ded)} (${fmtPct(fin.aggregate_deduction_rate_pct)}) = صافي ${fmtEGP(net)}. ` + fin.deduction_field_note;

  // AR by rep
  const arReps = [...fin.ar_by_rep].sort((a,b)=>b.net_balance-a.net_balance);
  new Chart(document.getElementById('ef-ar'), {
    type:'bar',
    data:{ labels: arReps.map(r=>r.rep), datasets:[{label:'صافي الرصيد', data:arReps.map(r=>r.net_balance), backgroundColor:'#4a3aa7'}]},
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
      scales:{ x:{ ticks:{ callback:v=>fmt0(v) } } } }
  });

  document.getElementById('ef-hhi-cust').textContent = fmt0(fin.hhi_customers);
  document.getElementById('ef-hhi-brand').textContent = fmt0(fin.hhi_brands);
  document.getElementById('ef-hhi-item').textContent = fmt0(fin.hhi_items);
  document.getElementById('ef-dso').textContent = fmt1(fin.dso_proxy_days);
  document.getElementById('ef-dso-note').textContent = fin.dso_proxy_method_note;
  document.getElementById('ef-missing-list').textContent = fin.not_computable_due_to_missing_cost_data.join(' · ');
}
