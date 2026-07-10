function renderCustomer(){
  return `
  <section class="panel" id="customer">
    <h2 class="panel-title">لوحة ربحية العملاء (على أساس الإيراد الصافي)</h2>
    <p class="panel-sub">تُبنى هذه اللوحة على الإيراد الصافي وليس هامش الربح، لعدم توفر بيانات تكلفة البضاعة المباعة لكل عميل في الملفات المرفوعة. تصنيف ABC حسب حجم الإيراد، وتصنيف XYZ حسب استقرار الطلب (معامل الاختلاف CV للكمية الشهرية).</p>

    <div class="grid kpi" style="margin-bottom:18px;" id="cu-kpis"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>توزيع العملاء حسب فئة ABC (بالإيراد)</h3>
        <div class="chart-wrap"><canvas id="cu-abc"></canvas></div>
      </div>
      <div class="card">
        <h3>تركّز الإيراد: أعلى 5 / 10 / 20 عميلاً مقابل الباقي</h3>
        <div class="chart-wrap"><canvas id="cu-concentration"></canvas></div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>مصفوفة ABC × XYZ (عدد العملاء في كل خلية)</h3>
      <div class="scroll-x"><table id="cu-matrix"></table></div>
      <div class="note">X = طلب مستقر (CV ≤ 0.5) · Y = متوسط التذبذب (0.5–1.0) · Z = تذبذب مرتفع أو نشاط متقطع جدًا. عملاء AZ/AY (إيراد مرتفع + تذبذب) هم أولوية لإدارة علاقة أوثق لضمان استقرار الطلب.</div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>أعلى 25 عميلاً — التفصيل الكامل</h3>
      <div class="scroll-x"><table id="cu-table"></table></div>
    </div>

    <div class="card">
      <h3>مبيعات كل عميل ونسبة البونص (كل 337 عميلاً)</h3>
      <input class="search" id="cu-bonus-search" placeholder="ابحث باسم العميل...">
      <div class="scroll-x" style="max-height:600px;overflow-y:auto;"><table id="cu-bonus-table"></table></div>
      <div class="note">نسبة البونص من قيمة المبيعات = القيمة التقديرية للكمية المجانية ("بونص") مُسعَّرة بمتوسط سعر بيع الصنف نفسه، مقسومة على إجمالي مبيعات العميل. الجدول مرتّب تنازليًا حسب إجمالي المبيعات.</div>
    </div>
  </section>`;
}

function mountCustomer(){
  const cust = D.customer_pareto;
  const custDim = {}; D.dim_customers.forEach(c=> custDim[c.customer_code]=c);
  const fin = D.financial;

  document.getElementById('cu-kpis').innerHTML = [
    ['عدد العملاء الإجمالي', fmt0(cust.length), ''],
    ['عملاء فئة A (80% من الإيراد)', fmt0(cust.filter(c=>c.abc_class==='A').length), ''],
    ['متوسط إيراد الشهر النشط/عميل', fmtEGP(fin.avg_revenue_per_active_month_per_customer_egp), 'الوسيط: '+fmtEGP(fin.median_revenue_per_active_month_per_customer_egp)],
    ['عملاء لديهم رصيد مدين حاليًا', fmt0(fin.ar_n_customers_with_debit_balance), 'من لقطة 2026/7/4'],
  ].map(([label,value,sub])=>`<div class="card"><div class="label">${label}</div><div class="value">${value}</div>${sub?`<div class="delta muted">${sub}</div>`:''}</div>`).join('');

  const abcCounts = {A:0,B:0,C:0}; cust.forEach(c=>abcCounts[c.abc_class]++);
  new Chart(document.getElementById('cu-abc'), {
    type:'bar', data:{ labels:['فئة A','فئة B','فئة C'], datasets:[{data:[abcCounts.A,abcCounts.B,abcCounts.C], backgroundColor:['#2a78d6','#eda100','#898781']}]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}} }
  });

  const sorted = [...cust].sort((a,b)=>b.line_total-a.line_total);
  const top5 = sorted.slice(0,5).reduce((s,c)=>s+c.line_total,0);
  const top10 = sorted.slice(0,10).reduce((s,c)=>s+c.line_total,0);
  const top20 = sorted.slice(0,20).reduce((s,c)=>s+c.line_total,0);
  const total = sorted.reduce((s,c)=>s+c.line_total,0);
  new Chart(document.getElementById('cu-concentration'), {
    type:'doughnut',
    data:{ labels:['أعلى 5 عملاء','عملاء 6–10','عملاء 11–20','باقي العملاء'],
      datasets:[{data:[top5, top10-top5, top20-top10, total-top20], backgroundColor:['#2a78d6','#1baf7a','#eda100','#c3c2b7']}]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom'}} }
  });

  // ABC x XYZ matrix
  const classes = ['A','B','C']; const xyzClasses=['X','Y','Z'];
  const matrix = {}; classes.forEach(a=>{matrix[a]={}; xyzClasses.forEach(x=>matrix[a][x]=0);});
  cust.forEach(c=>{ if(matrix[c.abc_class] && c.xyz_class) matrix[c.abc_class][c.xyz_class]++; });
  const maxCell = Math.max(...classes.flatMap(a=>xyzClasses.map(x=>matrix[a][x])));
  document.getElementById('cu-matrix').innerHTML = `
    <tr><th></th>${xyzClasses.map(x=>`<th>${x}</th>`).join('')}</tr>
    ${classes.map(a=>`<tr><th>${a}</th>${xyzClasses.map(x=>{
      const v = matrix[a][x]; const alpha = v/maxCell;
      return `<td style="background:rgba(42,120,214,${0.12+alpha*0.55});font-weight:700;">${v}</td>`;
    }).join('')}</tr>`).join('')}
  `;

  const top25 = sorted.slice(0,25);
  document.getElementById('cu-table').innerHTML = `
    <tr><th>#</th><th>العميل</th><th>الإيراد</th><th>% تراكمي</th><th>ABC</th><th>XYZ</th><th>المندوب</th><th>رصيد المديونية</th></tr>
    ${top25.map((c,i)=>{
      const dim = custDim[c.customer_code] || {};
      return `<tr><td>${i+1}</td><td>${c.customer_name}</td><td>${fmtEGP(c.line_total)}</td><td>${fmt1(c.cum_pct)}%</td>
        <td><span class="tag ${c.abc_class}">${c.abc_class}</span></td><td><span class="tag ${c.xyz_class||'C'}">${c.xyz_class||'—'}</span></td>
        <td>${dim.rep||'—'}</td><td>${dim.ar_net_balance!=null?fmtEGP(dim.ar_net_balance):'—'}</td></tr>`;
    }).join('')}
  `;

  // Full per-customer sales + bonus % table
  const bonusData = D.customer_bonus_summary;
  function renderBonusTable(filter){
    const q = (filter||'').trim();
    const rows = (q ? bonusData.filter(c=>c.customer_name.includes(q)) : bonusData).slice(0, q?200:337);
    return `
      <tr><th>العميل</th><th>إجمالي المبيعات</th><th>كمية البونص</th><th>قيمة البونص التقديرية</th><th>% البونص من المبيعات</th><th>المندوب</th><th>عدد الفواتير</th></tr>
      ${rows.map(c=>`<tr><td>${c.customer_name}</td><td>${fmtEGP(c.total_sales_egp)}</td><td>${fmt0(c.bonus_qty)}</td>
        <td>${fmtEGP(c.bonus_estimated_value_egp)}</td><td>${fmt2(c.bonus_pct_of_sales_value)}%</td>
        <td>${c.rep||'—'}</td><td>${fmt0(c.n_invoices)}</td></tr>`).join('')}
    `;
  }
  document.getElementById('cu-bonus-table').innerHTML = renderBonusTable('');
  document.getElementById('cu-bonus-search').addEventListener('input', (e)=>{
    document.getElementById('cu-bonus-table').innerHTML = renderBonusTable(e.target.value);
  });
}
