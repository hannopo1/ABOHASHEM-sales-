/* Abu Hashem mobile — module extracted verbatim from the standalone build.
   Namespace G — debt aging (أعمار المديونية) tiers and rollups.
   Do not reformat: this is byte-identical to the shipped runtime so the
   rebuilt file can be diffed against it. Regenerate the bundle with
   `python3 mobile/build_standalone.py`. */
const G = (function(){
const { AGING_COLORS } = T;
/* Abu Hashem — mobile runtime · PART 4: debt aging (أعمار المديونية).

   Ages each customer's OPEN balance by INVOICE DATE, by walking that customer's
   invoices oldest-first and consuming them with their own dated receipts and
   returns (FIFO). Whatever is left unconsumed is aged `as_of − invoice_date`.

   Why this is not the same as the source dashboard's aging
   --------------------------------------------------------
   The source computes "FIFO على الرصيد النهائي": it takes the AR snapshot's
   CLOSING balance and allocates it backwards over the customer's invoices. That
   silently assumes the whole balance arose inside the invoice window, so debt
   older than the window is reported as recent. This module instead applies the
   real dated cash, and whatever the transactions cannot explain is reported as
   an opening balance of UNKNOWN age rather than being folded into a tier.

   Both totals reconcile to receivables.total_outstanding exactly; they disagree
   about how the balance is distributed, and the UI shows both.

   Known limits of the source, surfaced rather than smoothed:
   - Receipts and returns carry no usable invoice reference (0 of 1554 receipt
     doc_ref and 0 of 176 return invoice_ref match a real invoice_no), so FIFO is
     applied at customer level by date, not invoice to invoice.
   - Invoices begin 2026-01-01 but the debt does not, hence the opening balance.
   - A customer who paid more in-window than they were billed was paying down
     that opening balance; the surplus is reported separately, not clamped away. */


/* Tiers measured from the INVOICE date (the basis chosen for this dashboard),
   not from a due date. Colours are reused from the source's own aging ramp so
   the two views read as the same family. */
const AGE_TIERS = [
  {key:"lt30", label:"أقل من شهر",     lo:0,  hi:30,       color:AGING_COLORS.current},
  {key:"m1_2", label:"شهر – شهرين",    lo:30, hi:60,       color:AGING_COLORS.d31_60},
  {key:"m2_3", label:"شهرين – 3 شهور", lo:60, hi:90,       color:AGING_COLORS.d61_90},
  {key:"gt90", label:"أكثر من 3 شهور", lo:90, hi:Infinity, color:AGING_COLORS.d120p},
];
const AGE_KEYS = AGE_TIERS.map(t => t.key);

/* The two rows that are NOT ages. They exist so the tiers stay a true partition
   of the reported balance instead of quietly absorbing what they cannot date. */
const OPENING = {key:"opening", label:"رصيد افتتاحي — عمر غير محدد", color:"#64748b"};
const OVERPAID = {key:"overpaid", label:"سداد رصيد سابق (دفعات زائدة)", color:"#06b6d4"};

const DAY = 864e5;
const days = (a, b) => Math.round((a - b) / DAY);
const parse = s => Date.parse(String(s).slice(0, 10));

function tierOf(age){
  for(const t of AGE_TIERS) if(age >= t.lo && age < t.hi) return t.key;
  return AGE_TIERS[0].key;                       // age < 0 (invoice dated after as_of)
}

/* Per-customer rows are independent of any filter, so compute all of them once
   per payload and let callers narrow afterwards. */
const _cache = new WeakMap();

function agingRows(D){
  let rows = _cache.get(D);
  if(rows) return rows;

  const asOf = parse(D.meta.as_of);

  /* Invoices oldest-first, per customer. Zero-value invoices (bonus / samples)
     carry no debt and would otherwise absorb credit that belongs to real ones. */
  const invBy = new Map();
  for(const v of (D.invoices||[])){
    if(!(v.reported_total > 0)) continue;
    const c = String(v.customer_code);
    if(!invBy.has(c)) invBy.set(c, []);
    invBy.get(c).push({date:parse(v.invoice_date), amount:v.reported_total, no:v.invoice_no});
  }
  for(const list of invBy.values()) list.sort((a,b)=>a.date-b.date);

  /* Every dated credit against the customer: cash received and goods returned. */
  const credBy = new Map(), C = D.collections || {};
  let unattributedReturns = 0;
  const addCred = (code, amt) => credBy.set(code, (credBy.get(code)||0) + (amt||0));
  for(const r of (C.receipts||[])) addCred(String(r.customer_code), r.amount);
  for(const r of (C.returns_rows||[])){
    if(r.customer_code == null){ unattributedReturns += r.value||0; continue; }
    addCred(String(r.customer_code), r.value);
  }

  rows = [];
  for(const ar of ((D.receivables && D.receivables.rows) || [])){
    const code = String(ar.customer_code);
    let credit = credBy.get(code) || 0;
    const open = [];
    for(const inv of (invBy.get(code) || [])){
      if(credit >= inv.amount){ credit -= inv.amount; continue; }  // fully settled
      open.push({date:inv.date, amount:inv.amount - credit, no:inv.no});
      credit = 0;
    }

    const tiers = {}; for(const k of AGE_KEYS) tiers[k] = 0;
    for(const o of open) tiers[tierOf(days(asOf, o.date))] += o.amount;

    const derived = open.reduce((a,o)=>a+o.amount, 0);
    const residual = ar.outstanding - derived;

    rows.push({
      code, name:ar.customer_name, rep:ar.rep || "غير محدد",
      snapshot: ar.outstanding,
      tiers,
      /* A positive residual is balance the transactions cannot date — it predates
         the window. A negative one means the customer paid down that older debt
         inside the window; reported as its own figure, never netted into a tier. */
      opening:  residual > 0 ? residual : 0,
      overpaid: residual < 0 ? -residual : 0,
      nOpenInvoices: open.length,
      oldestInvoiceDate: open.length ? new Date(open[0].date).toISOString().slice(0,10) : null,
      oldestAmount: open.length ? open[0].amount : 0,
      oldestAge: open.length ? days(asOf, open[0].date) : null,
      /* Sort weight: oldest money first, so the collection targets surface. */
      weight: tiers.gt90*4 + tiers.m2_3*3 + tiers.m1_2*2 + tiers.lt30,
    });
  }

  rows.sort((a,b)=>b.weight-a.weight || b.snapshot-a.snapshot);
  rows.unattributedReturns = unattributedReturns;
  _cache.set(D, rows);
  return rows;
}

/* Narrow to a cohort of customer codes (null = every customer). */
function agingFor(D, codes){
  const all = agingRows(D);
  if(!codes) return all;
  const out = all.filter(r => codes.has(r.code));
  out.unattributedReturns = all.unattributedReturns;
  return out;
}

function agingTotals(rows){
  const tiers = {}; for(const k of AGE_KEYS) tiers[k] = 0;
  let snapshot = 0, opening = 0, overpaid = 0;
  for(const r of rows){
    for(const k of AGE_KEYS) tiers[k] += r.tiers[k];
    snapshot += r.snapshot; opening += r.opening; overpaid += r.overpaid;
  }
  const aged = AGE_KEYS.reduce((a,k)=>a+tiers[k], 0);
  return {
    tiers, aged, opening, overpaid, snapshot,
    nCustomers: rows.length,
    nOverpaid: rows.filter(r=>r.overpaid>0).length,
    /* Must be ~0: the tiers plus the two residual rows are a partition of the
       reported balance. Displayed, so a drift can never pass unnoticed. */
    reconDelta: (aged + opening - overpaid) - snapshot,
    openingShare: snapshot ? opening/snapshot*100 : 0,
  };
}

function agingByRep(rows){
  const m = new Map();
  for(const r of rows){
    let e = m.get(r.rep);
    if(!e){ e = {rep:r.rep, snapshot:0, opening:0, aged:0, customers:0}; m.set(r.rep, e); }
    e.snapshot += r.snapshot; e.opening += r.opening; e.customers++;
    for(const k of AGE_KEYS) e.aged += r.tiers[k];
  }
  return [...m.values()].sort((a,b)=>b.snapshot-a.snapshot);
}

/* The source's own six due-date buckets, for the side-by-side reconciliation.
   Recomputed from the same cohort so both columns describe the same customers. */
function sourceBuckets(rows, D){
  const byCode = new Map(((D.receivables&&D.receivables.rows)||[]).map(r=>[String(r.customer_code), r]));
  const b = {current:0, d1_30:0, d31_60:0, d61_90:0, d91_120:0, d120p:0};
  for(const r of rows){
    const src = byCode.get(r.code); if(!src || !src.buckets) continue;
    for(const k in b) b[k] += src.buckets[k] || 0;
  }
  return b;
}

return {AGE_TIERS,AGE_KEYS,OPENING,OVERPAID,tierOf,agingRows,agingFor,agingTotals,agingByRep,sourceBuckets};
})();
