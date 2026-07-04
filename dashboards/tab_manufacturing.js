function renderManufacturing(){
  return `
  <section class="panel" id="mfg">
    <h2 class="panel-title">لوحة التصنيع والتعبئة (مشتقة من بيانات المبيعات)</h2>
    <div class="callout warn" style="margin-bottom:16px;">
      <b>لا توجد بيانات تصنيع مباشرة في الملفات المرفوعة</b> — لا بيانات إنتاج فعلي، لا تكلفة مواد خام (BOM)، لا كفاءة خطوط (OEE)، لا نسب هالك/فاقد، ولا أرصدة مخزون. جميع ما يُعرض أدناه هو <b>احتياج تعبئة وتغليف ضمني مُشتق حسابيًا</b> من الكميات المباعة فعليًا وملف «سعة الكرتونة من القطع والأطباق»، وليس بيانات إنتاج مرصودة مباشرة.
    </div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>احتياج التعبئة الشهري الضمني — أعلى 15 صنفًا (عدد كراتين/شكاير تقديري)</h3>
        <div class="chart-wrap tall"><canvas id="mf-cartons"></canvas></div>
        <div class="note">الاحتياج الضمني = (إجمالي الكمية المباعة خلال 18 شهرًا ÷ 18) ÷ سعة الكرتونة/الكيس لكل صنف (من ملف سعة الكرتونة). يفترض تطابق الإنتاج الشهري مع المبيعات الشهرية (بدون بيانات مخزون فعلية للتحقق من هذا الافتراض).</div>
      </div>
      <div class="card">
        <h3>مؤشر الموسمية الشهري (نسبة إلى المتوسط = 100)</h3>
        <div class="chart-wrap tall"><canvas id="mf-season"></canvas></div>
        <div class="note" id="mf-season-note"></div>
      </div>
    </div>

    <div class="card">
      <h3>جدول مرجعي: سعة الكرتونة/الكيس، الكمية الإجمالية بالكرتونة، ومتوسط سعر البيع لكل صنف</h3>
      <div class="scroll-x"><table id="mf-table"></table></div>
      <div class="note">"الكمية بالكرتونة" = إجمالي الكمية المباعة خلال 18 شهرًا ÷ سعة الكرتونة/الكيس. متوسط سعر البيع (ASP) = صافي المبيعات ÷ الكمية (بالوحدة الأصلية: كيلو/طبق/قطعة حسب الصنف).</div>
    </div>
  </section>`;
}

function mountManufacturing(){
  const carton = D.carton_reference;
  const withUnits = carton.filter(c=>c.carton_units).sort((a,b)=>b.implied_monthly_cartons-a.implied_monthly_cartons).slice(0,15);
  new Chart(document.getElementById('mf-cartons'), {
    type:'bar',
    data:{ labels: withUnits.map(c=>c.item_name), datasets:[{data: withUnits.map(c=>c.implied_monthly_cartons), backgroundColor:'#4a3aa7'}]},
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>fmt1(c.raw)+' وحدة تعبئة/شهر'}}} }
  });

  const seas = D.eda_summary.seasonality_index_by_month;
  const nYears = D.eda_summary.seasonality_n_years_observed_by_month;
  const monthNames=['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
  const seasVals = monthNames.map((_,i)=> seas[String(i+1)]);
  new Chart(document.getElementById('mf-season'), {
    type:'bar',
    data:{ labels: monthNames, datasets:[{data: seasVals,
      backgroundColor: seasVals.map(v=> v>=110? '#e34948' : v<=90? '#2a78d6' : '#c3c2b7')}]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
      scales:{ y:{ ticks:{callback:v=>v+'%'} } } }
  });
  const lowYearMonths = monthNames.filter((_,i)=>nYears[String(i+1)]<2);
  document.getElementById('mf-season-note').textContent =
    `الأشهر بالأحمر أعلى من المتوسط بأكثر من 10% (ذروة تحتاج تخطيط طاقة تعبئة)، والأزرق أقل من المتوسط بأكثر من 10%. تنبيه منهجي: الأشهر (${lowYearMonths.join('، ')}) مبنية على رصد سنة واحدة فقط (2025) وليس متوسط سنتين، فموثوقيتها أقل من بقية الأشهر.`;

  const aspBoxes = D.item_asp_boxes;
  document.getElementById('mf-table').innerHTML = `
    <tr><th>الصنف</th><th>العلامة التجارية</th><th>سعة الكرتونة/الكيس</th><th>إجمالي الكمية (18 شهرًا)</th><th>الكمية بالكرتونة/الكيس</th><th>متوسط سعر البيع</th></tr>
    ${[...aspBoxes].sort((a,b)=>b.total_qty-a.total_qty).map(c=>`<tr><td>${c.item_name}</td><td>${c.brand}</td>
      <td>${c.carton_capacity||'—'}</td><td>${fmt0(c.total_qty)}</td>
      <td>${c.qty_in_boxes!=null?fmt1(c.qty_in_boxes):'—'}</td><td>${c.asp_egp!=null?fmt2(c.asp_egp):'—'}</td></tr>`).join('')}
  `;
}
