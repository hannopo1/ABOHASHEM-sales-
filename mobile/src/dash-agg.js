/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   Namespace A — makeApi(), aggregation over window.DASH.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
const A = (function(){
const { sum, round2 } = T;
/**
 * Create the mobile dashboard runtime API for the supplied data.
 * @param {Object} D - Dashboard source data and metadata used for month helpers, filtering, aggregation, and insights.
 * @return {Object} An API exposing the source data, month metadata and helpers, filtered context builder, and insight lookup.
 */

function makeApi(D){
  const MONTHLABEL = Object.fromEntries((D.meta.available_months||[]).map(m=>[m.v,m.l]));
  const ALL_LABEL = D.meta.all_months_label || "جميع الشهور";
  const DATA_MONTHS = new Set(D.meta.data_months || []);
  const monthHasData = m => !m || m==="all" || DATA_MONTHS.has(m);
  const monthName = ym => MONTHLABEL[ym] || ym;
  const curMonthLabel = m => (!m || m==="all") ? ALL_LABEL
    : (MONTHLABEL[m] || m) + (monthHasData(m) ? "" : " — لا توجد بيانات");

  /**
   * Aggregates sales, collection, activity, billing, and overdue-invoice metrics by customer.
   * @param {Array<Object>} lines - Invoice line items used to calculate units, boxes, and item counts.
   * @param {Array<Object>} invoices - Invoice records used to calculate sales, collections, invoice counts, and outstanding amounts.
   * @return {Array<Object>} Customer summary records sorted by sales, each with a sales rank.
   */
  function aggCustomers(lines, invoices){
    const asOf = new Date(D.meta.as_of), net = D.meta.net_terms_days, m = new Map();
    for (const v of invoices){
      let o = m.get(v.customer_code);
      if(!o){ o={customer_code:v.customer_code,customer_name:v.customer_name,sales:0,collections:0,invs:new Set(),unpaid:[]}; m.set(v.customer_code,o); }
      o.sales += v.reported_total||0; o.collections += v.paid||0; o.invs.add(v.invoice_no);
      if(v.remaining>0 && v.reported_total>0) o.unpaid.push(v);
    }
    const lm = new Map();
    for (const l of lines){
      let o = lm.get(l.customer_code);
      if(!o){ o={units:0,boxes:0,items:new Set()}; lm.set(l.customer_code,o); }
      o.units += l.qty||0; o.boxes += l.boxes||0; o.items.add(l.item_code);
    }
    const rows = [...m.values()].map(o=>{
      const ar = (D.customer_ar||{})[o.customer_code] || {};
      const l = lm.get(o.customer_code) || {units:0,boxes:0,items:new Set()};
      const nInv = o.invs.size;
      const rec = {customer_code:o.customer_code, customer_name:o.customer_name,
        rep: ar.rep || "غير محدد", city: ar.city || "",
        sales: round2(o.sales), collections: round2(o.collections),
        n_invoices:nInv, n_items:l.items.size, units:round2(l.units), boxes:round2(l.boxes),
        avg_invoice_value: nInv ? round2(o.sales/nInv) : 0,
        total_billed: ar.total_billed != null ? ar.total_billed : round2(o.sales),
        billed_2026: ar.billed_2026 != null ? ar.billed_2026 : null,
        outstanding: ar.outstanding != null ? ar.outstanding : null,
        collected_actual: ar.collected_actual != null ? ar.collected_actual : null,
        returns_actual: ar.returns_actual != null ? ar.returns_actual : null,
        collection_rate: ar.collection_rate != null ? ar.collection_rate : null,
        rate_source: ar.rate_source || "none",
        bonus_pct: ar.bonus_pct || 0, has_ar: !!ar.has_ar};
      rec.bonus_value = round2(o.sales * rec.bonus_pct);
      if(o.unpaid.length){
        o.unpaid.sort((a,b)=>a.invoice_date<b.invoice_date?-1:1);
        const u=o.unpaid[0], due=new Date(u.invoice_date); due.setDate(due.getDate()+net);
        rec.oldest_invoice_no=u.invoice_no; rec.oldest_invoice_date=u.invoice_date;
        rec.oldest_due_date=due.toISOString().slice(0,10);
        rec.oldest_days_overdue=Math.max(0,Math.round((asOf-due)/864e5));
        rec.oldest_amount=round2(u.remaining);
      }
      return rec;
    }).sort((a,b)=>b.sales-a.sales);
    rows.forEach((r,i)=>r.rank=i+1);
    return rows;
  }

  /**
   * Aggregate receivable amounts into aging buckets.
   * @param {Array<Object>} rows - Rows containing either precomputed bucket amounts or current and overdue values.
   * @return {Object} The totals for current, 1–30, 31–60, 61–90, 91–120, and over-120-day buckets.
   */
  function bucketsFromRows(rows){
    const b={current:0,d1_30:0,d31_60:0,d61_90:0,d91_120:0,d120p:0};
    for(const r of rows){
      if(r.buckets){ for(const k in b) b[k]+=r.buckets[k]||0; }
      else { b.current += r.current||0; if(r.overdue>0) b[r.bucket]+=r.overdue||0; }
    }
    return b;
  }

  /**
   * Aggregates sales and volume metrics by product.
   * @param {Array<Object>} lines - Sales lines containing product, customer, sales, quantity, box, and unit-price data.
   * @return {Array<Object>} Products sorted by sales, including totals, customer and line counts, price range, average selling price, sales contribution, and rank.
   */
  function aggProducts(lines){
    const m=new Map(), grand=sum(lines,"line_total")||1;
    for(const l of lines){
      let o=m.get(l.item_code);
      if(!o){ o={item_code:l.item_code,item_name:l.item_name,brand:l.brand,sales:0,qty:0,boxes:0,cust:new Set(),n_lines:0,prices:[]}; m.set(l.item_code,o); }
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

  /**
   * Calculates sales, receivables, collection metrics, and invoice statistics for dashboard KPIs.
   * @param {Array} lines - Invoice line items used to calculate net sales, quantities, boxes, and average selling price.
   * @param {Array} invoices - Invoices used to calculate reported sales, invoice counts, payments, and zero-value invoices.
   * @param {Array} recv - Receivable records used to calculate outstanding and overdue amounts.
   * @param {Array} customers - Customer aggregates used to calculate billing, collections, returns, and collection rate.
   * @return {Object} Aggregated KPI values, including sales, receivables, collection metrics, invoice counts, and customer counts.
   */
  function aggKpis(lines, invoices, recv, customers){
    const total_sales=sum(invoices,"reported_total"), net_sales=sum(lines,"line_total");
    const qty=sum(lines,"qty"), boxes=lines.reduce((a,l)=>a+(l.boxes||0),0);
    const priced=lines.filter(l=>l.qty>0&&l.line_total>0);
    const asp=priced.length?sum(priced,"line_total")/sum(priced,"qty"):0;
    const outstanding=sum(recv,"outstanding"), overdue=sum(recv,"overdue");
    const billed=customers.reduce((a,c)=>a+(c.total_billed||0),0);
    const cust_out=customers.reduce((a,c)=>a+(c.outstanding||0),0);
    const collected_actual=customers.reduce((a,c)=>a+(c.collected_actual||0),0);
    const billed_2026=customers.reduce((a,c)=>a+(c.billed_2026||0),0);
    const returns_actual=customers.reduce((a,c)=>a+(c.returns_actual||0),0);
    const collection_rate = D.collections && billed_2026
      ? Math.max(0,Math.min(1,collected_actual/billed_2026))
      : (billed ? Math.max(0,Math.min(1,(billed-cust_out)/billed)) : 0);
    const nInv=new Set(invoices.map(v=>v.invoice_no)).size;
    return {total_sales,net_sales,qty,boxes,asp,outstanding,overdue,collection_rate,
      collected_actual,billed_2026,returns_actual,
      collection_rate_basis:(D.collections&&billed_2026)?"actual":"proxy",
      collections_at_issue:sum(invoices,"paid"),
      n_invoices:nInv,
      n_customers:new Set(invoices.map(v=>v.customer_code)).size,
      zero_invoices:invoices.filter(v=>!v.reported_total).length,
      avg_invoice_value:nInv?total_sales/nInv:0};
  }

  /**
   * Builds an aggregated dashboard context using the specified filters.
   * @param {Object} f - Filter criteria for month, customer, representative, brand, item, invoice status, and receivables aging.
   * @return {Object} The filtered lines, invoices, receivables, customer and product aggregates, aging buckets, and KPI metrics.
   */
  function buildContext(f){
    const mAll = !f.month || f.month==="all";
    let lines = (D.lines||[]).filter(l =>
      (mAll || l.month===f.month) && (!f.customer || l.customer_code===f.customer) &&
      (!f.rep || l.rep===f.rep) && (!f.brand || l.brand===f.brand) && (!f.item || l.item_code===f.item));
    const invSet = new Set(lines.map(l=>l.invoice_no));
    let invoices = (D.invoices||[]).filter(v =>
      (mAll || v.month===f.month) && (!f.customer || v.customer_code===f.customer) &&
      (!f.rep || v.rep===f.rep) && (!f.status || v.status===f.status) &&
      ((!f.brand && !f.item) || invSet.has(v.invoice_no)));
    if(f.status){ const s=new Set(invoices.map(v=>v.invoice_no)); lines=lines.filter(l=>s.has(l.invoice_no)); }
    const active = new Set(invoices.map(v=>v.customer_code));
    const recv = ((D.receivables&&D.receivables.rows)||[]).filter(r =>
      (mAll || active.has(r.customer_code)) && (!f.customer || r.customer_code===f.customer) &&
      (!f.rep || r.rep===f.rep) && (!f.aging || r.bucket===f.aging));
    const customers = aggCustomers(lines, invoices);
    return {lines, invoices, recv, customers, products:aggProducts(lines),
      buckets:bucketsFromRows(recv), kpis:aggKpis(lines,invoices,recv,customers)};
  }

  /**
   * Retrieves an insight for a specified month or the complete dataset.
   * @param {string} monthKey - The month identifier, or `"all"` for the complete dataset.
   * @param {string} key - The insight identifier.
   * @return {*} The requested insight, or `null` when unavailable.
   */
  function insight(monthKey, key){
    const set = (monthKey && monthKey!=="all")
      ? (D.insights_by_month||{})[monthKey] : (D.insights_by_month||{})["all"];
    return set ? (set[key]||null) : null;
  }

  return {D, MONTHLABEL, ALL_LABEL, DATA_MONTHS, monthHasData, monthName,
    curMonthLabel, buildContext, insight};
}

return {makeApi};
})();
