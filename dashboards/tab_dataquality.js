function renderDataQuality(){
  return `
  <section class="panel" id="dq">
    <h2 class="panel-title">جودة البيانات والاختبارات الإحصائية القياسية</h2>
    <p class="panel-sub">ملخص تقني لضبط الجودة أثناء تحويل الفواتير من نص PDF/Markdown إلى بيانات منظمة، واختبارات الفرضيات الإحصائية على سلسلة الإيراد الشهري.</p>

    <div class="grid kpi" style="margin-bottom:18px;" id="dq-kpis"></div>

    <div class="grid two" style="margin-bottom:16px;">
      <div class="card">
        <h3>القيم المفقودة حسب الحقل</h3>
        <div class="scroll-x"><table id="dq-missing"></table></div>
      </div>
      <div class="card">
        <h3>أصناف بها تفاوت أسعار غير معتاد (IQR × 3)</h3>
        <div class="scroll-x"><table id="dq-outliers"></table></div>
        <div class="note">لا يعني بالضرورة خطأ في البيانات — قد يعكس تفاوض أسعار خاص بعميل معين أو تغيّر سعري عبر الزمن (تضخم). مذكور هنا للمراجعة اليدوية فقط.</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <h3>الاختبارات الإحصائية القياسية على سلسلة الإيراد الشهري (n=18)</h3>
      <div class="scroll-x"><table id="dq-tests"></table></div>
      <div class="callout warn" style="margin-top:12px;">
        <b>تنبيه منهجي:</b> بعينة من 18 مشاهدة شهرية فقط، القوة الإحصائية لكل الاختبارات أدناه محدودة؛ النتائج مؤشرة وليست قطعية. التفسير الاقتصادي الكامل لكل اختبار في التقرير الأكاديمي المرفق.
      </div>
    </div>

    <div class="grid two">
      <div class="card">
        <h3>تسوية أسماء العملاء والأصناف</h3>
        <div class="scroll-x"><table id="dq-normalization"></table></div>
      </div>
      <div class="card">
        <h3>مطابقة عدد الفواتير الشهرية مع فهرس الملف المصدر</h3>
        <div id="dq-recon"></div>
      </div>
    </div>

    <div class="card" style="margin-top:16px;">
      <h3>عملاء لديهم رصيد مديونية لكن بدون أي فاتورة مبيعات مطابقة في بيانات هذا المشروع</h3>
      <div class="scroll-x"><table id="dq-zero-invoice"></table></div>
      <div class="note">هؤلاء العملاء ظهروا في لقطة المديونية (2026/7/4) لكن لم يُعثر على كودهم في فواتير المبيعات المُحلَّلة (2025/1/1 – 2026/6/30). السبب الأرجح: رصيد افتتاحي/تسوية سابقة على يناير 2025، أو معاملات بين 2026/6/30 و2026/7/4 خارج نطاق الملفات المرفوعة — وليس بالضرورة خطأ بيانات.</div>
    </div>
  </section>`;
}

function mountDataQuality(){
  const dq = D.data_quality, ts = D.timeseries, plog = D.parse_log, dlog = D.dimension_log, clog = D.customer_dim_log;

  document.getElementById('dq-kpis').innerHTML = [
    ['إجمالي الفواتير المُحلَّلة', fmt0(dq.n_invoices), 'من أصل '+fmt0(plog.invoices_found_main+plog.invoices_found_june)+' فاتورة في الملفين المصدر'],
    ['بنود الفواتير (أسطر)', fmt0(dq.n_rows), ''],
    ['مطابقة إجمالي الفاتورة مع تفاصيل بنودها', (dq.n_invoices_reconciliation_mismatch_over_1egp===0?'100%':fmtPct(100-dq.n_invoices_reconciliation_mismatch_over_1egp/dq.n_invoices*100)), 'فرق أكبر من جنيه واحد في '+fmt0(dq.n_invoices_reconciliation_mismatch_over_1egp)+' فاتورة فقط'],
    ['أسطر مكررة مكتشفة', fmt0(dq.n_duplicate_line_candidates), ''],
    ['بنود مبيعات مجانية (بونص)', fmtPct(dq.bonus_share_of_lines_pct), fmt0(dq.n_bonus_lines)+' سطرًا'],
    ['حصة الإيراد غير المصنّف بعلامة تجارية', fmtPct(dq.revenue_share_unclassified_brand_pct), ''],
  ].map(([label,value,sub])=>`<div class="card"><div class="label">${label}</div><div class="value">${value}</div>${sub?`<div class="delta muted">${sub}</div>`:''}</div>`).join('');

  document.getElementById('dq-missing').innerHTML = `
    <tr><th>الحقل</th><th>عدد المفقود</th><th>%</th></tr>
    ${Object.entries(dq.missing_values).map(([k,v])=>`<tr><td>${k}</td><td>${fmt0(v.n_missing)}</td><td>${fmt2(v.pct_missing)}%</td></tr>`).join('')}
    <tr><td colspan="3" style="color:var(--muted);font-size:11.5px;">ملاحظة: غياب رقم الهاتف في ٪${fmt1(dq.missing_values.phone.pct_missing)} من الأسطر لا يؤثر على أي تحليل مالي أو تشغيلي في هذا التقرير (حقل معلوماتي فقط).</td></tr>
  `;

  document.getElementById('dq-outliers').innerHTML = `
    <tr><th>الصنف</th><th>عدد الحالات الشاذة</th><th>من إجمالي</th><th>نطاق السعر الطبيعي</th></tr>
    ${dq.price_outliers_by_item.slice(0,12).map(o=>`<tr><td>${o.item_name}</td><td>${o.n_outliers}</td><td>${o.n_total}</td><td>${fmt2(o.price_range_normal[0])} – ${fmt2(o.price_range_normal[1])}</td></tr>`).join('')}
  `;

  const testsRows = [
    ['ADF (المستوى) — جذر الوحدة', ts.adf_level.stat.toFixed(3), ts.adf_level.pvalue.toFixed(4), ts.adf_level.pvalue<0.05?'رفض جذر الوحدة':'عدم رفض جذر الوحدة (السلسلة غير مستقرة في مستواها)'],
    ['ADF (الفرق الأول)', ts.adf_first_diff.stat.toFixed(3), ts.adf_first_diff.pvalue.toFixed(6), ts.adf_first_diff.pvalue<0.05?'مستقرة بعد أخذ الفرق الأول — I(1)':'غير مستقرة'],
    ['KPSS (المستوى)', ts.kpss_level.stat.toFixed(3), ts.kpss_level.pvalue.toFixed(4), ts.kpss_level.pvalue<0.05?'رفض الاستقرارية (متوافق مع ADF)':'عدم رفض الاستقرارية'],
    ['Ljung-Box (تأخير 4)', ts.ljung_box[0].lb_stat.toFixed(3), ts.ljung_box[0].lb_pvalue.toFixed(4), ts.ljung_box[0].lb_pvalue<0.05?'ارتباط ذاتي دال':'لا يوجد ارتباط ذاتي دال'],
    ['Ljung-Box (تأخير 8)', ts.ljung_box[1].lb_stat.toFixed(3), ts.ljung_box[1].lb_pvalue.toFixed(4), ts.ljung_box[1].lb_pvalue<0.05?'ارتباط ذاتي دال':'لا يوجد ارتباط ذاتي دال'],
    ['Durbin-Watson (بواقي الانحدار)', ts.durbin_watson.toFixed(3), '—', Math.abs(ts.durbin_watson-2)<0.5?'قريب من 2 — لا ارتباط ذاتي ملحوظ':'قد يوجد ارتباط ذاتي'],
    ['Jarque-Bera (التوزيع الطبيعي للبواقي)', ts.jarque_bera.stat.toFixed(3), ts.jarque_bera.pvalue.toFixed(4), ts.jarque_bera.pvalue>0.05?'عدم رفض التوزيع الطبيعي':'رفض التوزيع الطبيعي'],
    ['Breusch-Pagan (ثبات التباين)', ts.breusch_pagan.lm_stat.toFixed(3), ts.breusch_pagan.lm_pvalue.toFixed(4), ts.breusch_pagan.lm_pvalue>0.05?'تجانس التباين (Homoskedastic)':'عدم تجانس التباين'],
    ['White Test (ثبات التباين العام)', ts.white_test.lm_stat.toFixed(3), ts.white_test.lm_pvalue.toFixed(4), ts.white_test.lm_pvalue>0.05?'تجانس التباين':'عدم تجانس التباين'],
    ['Ramsey RESET (الشكل الوظيفي)', ts.ramsey_reset.stat.toFixed(3), ts.ramsey_reset.pvalue.toFixed(4), ts.ramsey_reset.pvalue>0.05?'لا وجود لسوء تحديد الشكل الوظيفي':'احتمال سوء تحديد الشكل الوظيفي'],
    ['Chow Test (كسر هيكلي عند يناير 2026)', ts.chow_test_split_2026_01.f_stat.toFixed(3), ts.chow_test_split_2026_01.pvalue.toFixed(4), ts.chow_test_split_2026_01.pvalue<0.05?'كسر هيكلي دال':'لا يوجد دليل كافٍ على كسر هيكلي (قد يعود لضعف قوة الاختبار)'],
  ];
  document.getElementById('dq-tests').innerHTML = `
    <tr><th>الاختبار</th><th>الإحصائية</th><th>القيمة الاحتمالية</th><th>التفسير</th></tr>
    ${testsRows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td></tr>`).join('')}
  `;

  document.getElementById('dq-normalization').innerHTML = `
    <tr><td>أكواد عملاء فريدة (المعرّف الثابت)</td><td>${fmt0(dq.n_distinct_customer_codes)}</td></tr>
    <tr><td>صيغ أسماء عملاء مختلفة (قبل التسوية)</td><td>${fmt0(dq.n_distinct_customer_names_raw)}</td></tr>
    <tr><td>أكواد أصناف فريدة</td><td>${fmt0(dq.n_distinct_item_codes)}</td></tr>
    <tr><td>صيغ أسماء أصناف مختلفة (قبل التسوية)</td><td>${fmt0(dq.n_distinct_item_names_raw)}</td></tr>
    <tr><td>عملاء لديهم لقطة مديونية مطابقة</td><td>${fmt0(clog.n_customers_matched)} من ${fmt0(clog.n_customers_in_ar_snapshot)}</td></tr>
    <tr><td>أصناف مصنّفة عبر القائمة المرجعية مباشرة</td><td>${fmt0(dlog.matched_master)}</td></tr>
    <tr><td>أصناف مصنّفة عبر كلمات مفتاحية بالاسم</td><td>${fmt0(dlog.matched_keyword)}</td></tr>
    <tr><td>أصناف غير مصنّفة (متبقية)</td><td>${fmt0(dlog.unclassified.length)}</td></tr>
  `;

  const mismatches = Object.keys(dq.monthly_invoice_count_mismatches||{}).length;
  document.getElementById('dq-recon').innerHTML = `
    <div class="callout ${mismatches===0?'info':'warn'}">
      عدد الأشهر التي يتطابق فيها عدد الفواتير المُستخرج مع الفهرس الشهري المذكور صراحة في الملف المصدر نفسه:
      <b>${17-mismatches} من 17 شهرًا</b> (يناير 2025 – مايو 2026، الفترة المغطاة بفهرس صريح في الملف).
      ${mismatches===0? 'مطابقة كاملة 100% — لا فروقات.' : ''}
    </div>
  `;

  const zeroInv = D.ar_zero_invoice_customers;
  document.getElementById('dq-zero-invoice').innerHTML = `
    <tr><th>العميل</th><th>المندوب</th><th>صافي رصيد المديونية</th></tr>
    ${zeroInv.map(c=>`<tr><td>${c.customer_name}</td><td>${c.rep}</td><td>${fmtEGP(c.net_balance)}</td></tr>`).join('')}
  `;
}
