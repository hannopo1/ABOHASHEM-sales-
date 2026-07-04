function renderForecast(){
  return `
  <section class="panel" id="forecast">
    <h2 class="panel-title">لوحة التنبؤ — 7 أشهر مقبلة (يوليو 2026 – يناير 2027)</h2>
    <p class="panel-sub" id="fc-method-note"></p>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>توقع إيراد الشركة الإجمالي</h3>
        <div class="chart-wrap tall"><canvas id="fc-company"></canvas></div>
      </div>
      <div class="card">
        <h3>مقارنة نماذج التنبؤ (التحقق المتدحرج rolling-origin CV)</h3>
        <div class="scroll-x"><table id="fc-cv-table"></table></div>
        <div class="note">النموذج الفائز <b id="fc-best-model"></b> يُختار حسب أقل قيمة RMSE في التحقق خارج العيّنة (وليس أفضل ملاءمة داخل العيّنة فقط)، لتفادي الإفراط في المطابقة (overfitting) على 18 مشاهدة فقط.</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>جدول التوقع الشهري التفصيلي (3 سيناريوهات)</h3>
      <div class="scroll-x"><table id="fc-table"></table></div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>توقع أعلى 6 عملاء (7 أشهر، نموذج Holt)</h3>
      <div class="small-mult-grid" id="fc-cust-grid"></div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>توقع أعلى 6 أصناف (7 أشهر، نموذج Holt)</h3>
      <div class="small-mult-grid" id="fc-item-grid"></div>
    </div>

    <div class="callout warn">
      <b>مخاطر التنبؤ والقيود المنهجية:</b>
      <div class="note">
        1) العيّنة قصيرة نسبيًا (18 مشاهدة شهرية) — أي نموذج موسمي كلاسيكي (SARIMA بدورة 12، Holt-Winters الموسمي، أو الإعداد الافتراضي لـ Prophet) يتطلب دورتين موسميتين كاملتين (24 مشاهدة على الأقل) وهو غير متاح هنا، لذلك اقتصرت المقارنة على النماذج غير الموسمية القابلة للتقدير بمصداقية عند هذا الحجم.<br>
        2) فترات الثقة مبنية على تقريب طبيعي (Normal approximation) لتباين البواقي، وتتسع مع الأفق الزمني كما هو متوقع إحصائيًا.<br>
        3) التوقع يفترض استمرار النمط التاريخي (الاتجاه العام + التذبذب العشوائي)؛ أي صدمة خارجية (تضخم حاد، تغيّر تسعير جوهري، دخول/خروج عميل كبير) غير مُدرجة في النموذج.<br>
        4) توقعات العملاء/الأصناف الفردية تعتمد على نموذج Holt الموحّد دون إعادة معايرة كاملة (CV) لكل سلسلة على حدة، لذا فهي إرشادية وليست بنفس درجة دقة توقع مستوى الشركة الكلي.
      </div>
    </div>
  </section>`;
}

function mountForecast(){
  const fc = D.forecast, disagg = D.forecast_disagg;
  document.getElementById('fc-method-note').textContent = fc.method_note;
  document.getElementById('fc-best-model').textContent = fc.best_model_by_rolling_rmse;

  const months = fc.historical_months.map(monthAr);
  const fcMonths = fc.forecast_company_revenue.map(r=>monthAr(r.month));
  const hist = D.monthly_series.map(r=>r.revenue);
  const allMonths = months.concat(fcMonths);
  const histSeries = hist.concat(Array(fcMonths.length).fill(null));
  const baseSeries = Array(hist.length-1).fill(null).concat([hist[hist.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.base_case));
  const upperSeries = Array(hist.length-1).fill(null).concat([hist[hist.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.optimistic_case));
  const lowerSeries = Array(hist.length-1).fill(null).concat([hist[hist.length-1]]).concat(fc.forecast_company_revenue.map(r=>r.conservative_case));
  new Chart(document.getElementById('fc-company'), {
    type:'line',
    data:{ labels: allMonths, datasets:[
      {label:'فعلي', data: histSeries, borderColor:'#2a78d6', pointRadius:2, borderWidth:2.5},
      {label:'متفائل/متحفظ (95%)', data: upperSeries, borderColor:'transparent', backgroundColor:'rgba(42,120,214,.12)', fill:'+1', pointRadius:0},
      {label:'حد أدنى', data: lowerSeries, borderColor:'transparent', backgroundColor:'rgba(42,120,214,.12)', fill:false, pointRadius:0},
      {label:'أساسي', data: baseSeries, borderColor:'#eb6834', borderDash:[6,4], pointRadius:2, borderWidth:2.5},
    ]},
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{legend:{position:'bottom', labels:{filter:i=>i.text!=='حد أدنى'}}},
      scales:{ y:{ ticks:{callback:v=>fmt0(v)} } } }
  });

  const cvRows = Object.entries(fc.cv_summary).filter(([,v])=>v);
  document.getElementById('fc-cv-table').innerHTML = `
    <tr><th>النموذج</th><th>RMSE</th><th>MAE</th><th>MAPE%</th><th>SMAPE%</th></tr>
    ${cvRows.sort((a,b)=>a[1].rmse-b[1].rmse).map(([name,v])=>`
      <tr style="${name===fc.best_model_by_rolling_rmse?'font-weight:800;background:rgba(42,120,214,.08);':''}">
      <td>${name}</td><td>${fmt0(v.rmse)}</td><td>${fmt0(v.mae)}</td><td>${fmt1(v.mape)}</td><td>${fmt1(v.smape)}</td></tr>`).join('')}
  `;

  document.getElementById('fc-table').innerHTML = `
    <tr><th>الشهر</th><th>متحفظ</th><th>أساسي</th><th>متفائل</th></tr>
    ${fc.forecast_company_revenue.map(r=>`<tr><td>${monthAr(r.month)}</td><td>${fmtEGP(r.conservative_case)}</td><td><b>${fmtEGP(r.base_case)}</b></td><td>${fmtEGP(r.optimistic_case)}</td></tr>`).join('')}
  `;

  function smallMultiples(gridId, entries, colorFn){
    const grid = document.getElementById(gridId);
    grid.innerHTML = entries.map(([key,val],i)=>`<div class="card"><h3 style="font-size:12.5px;">${val.name||key}</h3><div class="chart-wrap short"><canvas id="${gridId}-${i}"></canvas></div></div>`).join('');
    entries.forEach(([key,val],i)=>{
      const labels = disagg.months_historical.map(monthAr).concat(disagg.months_future.map(monthAr));
      const h = val.historical;
      const histS = h.concat(Array(val.forecast.length).fill(null));
      const baseS = Array(h.length-1).fill(null).concat([h[h.length-1]]).concat(val.forecast.map(r=>r.base_case));
      new Chart(document.getElementById(`${gridId}-${i}`), {
        type:'line',
        data:{ labels, datasets:[
          {data: histS, borderColor: colorFn(i), pointRadius:1, borderWidth:2},
          {data: baseS, borderColor:'#eb6834', borderDash:[5,3], pointRadius:1, borderWidth:2},
        ]},
        options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
          scales:{ x:{ticks:{display:false}}, y:{ticks:{callback:v=>fmt0(v)}} } }
      });
    });
  }
  smallMultiples('fc-cust-grid', Object.entries(disagg.top_customers).slice(0,6), i=>PALETTE[i%PALETTE.length]);
  smallMultiples('fc-item-grid', Object.entries(disagg.top_items).slice(0,6), i=>PALETTE[i%PALETTE.length]);
}
