"""Generate the self-contained sales & debt dashboard from analysis/data/*.csv.

Writes two files:
  - analysis/dashboard.html                 : full standalone document (repo deliverable)
  - <scratch_fragment_path> (CLI arg, opt.) : body-only fragment, for the Artifact tool

Run after build_analysis.py.
"""
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "analysis" / "data"
OUT_FULL = ROOT / "analysis" / "dashboard.html"

PALETTE = {
    "good": "#0ca30c",
    "critical": "#d03b3b",
    "blue": "#2a78d6",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "violet": "#4a3aa7",
}


def load():
    rep = pl.read_csv(DATA / "rep_debt_arrears_summary.csv")
    cust_sales = pl.read_csv(DATA / "customer_sales_bonus_summary.csv", infer_schema_length=0)
    cust_debt = pl.read_csv(DATA / "customer_debt_arrears_detail.csv", infer_schema_length=0)
    items = pl.read_csv(DATA / "item_summary.csv", infer_schema_length=0)
    zero_inv = pl.read_csv(DATA / "zero_invoices.csv", infer_schema_length=0)
    headers = pl.read_csv(DATA / "invoices_header.csv", infer_schema_length=0)
    return rep, cust_sales, cust_debt, items, zero_inv, headers


def to_num(df, cols):
    return df.with_columns([pl.col(c).cast(pl.Float64, strict=False).fill_null(0.0) for c in cols])


def build_customers_360(cust_sales, cust_debt):
    cust_sales = to_num(cust_sales, ["sales_value", "total_qty", "bonus_qty", "bonus_pct", "invoice_count", "zero_invoice_count"])
    cust_debt = to_num(cust_debt, ["debt_amount", "credit_balance", "current_amount", "arrears_amount"])
    merged = cust_sales.join(
        cust_debt.select(["customer_code", "rep", "last_invoice_date", "debt_amount", "credit_balance", "current_amount", "arrears_amount"]),
        on="customer_code", how="full", coalesce=True,
    ).with_columns([
        pl.col("rep").fill_null("غير محدد"),
        pl.col("customer_name").fill_null(pl.lit("")),
        pl.col("sales_value").fill_null(0.0),
        pl.col("total_qty").fill_null(0.0),
        pl.col("bonus_qty").fill_null(0.0),
        pl.col("bonus_pct").fill_null(0.0),
        pl.col("invoice_count").fill_null(0.0),
        pl.col("zero_invoice_count").fill_null(0.0),
        pl.col("debt_amount").fill_null(0.0),
        pl.col("credit_balance").fill_null(0.0),
        pl.col("current_amount").fill_null(0.0),
        pl.col("arrears_amount").fill_null(0.0),
    ]).sort("sales_value", descending=True)
    return merged


def fmt_money(x):
    return f"{x:,.0f}"


FRAGMENT_TEMPLATE = r"""
<style>
  :root {{
    --surface-1: #fcfcfb; --page: #f9f9f7; --text-primary:#0b0b0b; --text-secondary:#52514e;
    --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7; --border: rgba(11,11,11,0.10);
    --good:#0ca30c; --critical:#d03b3b; --blue:#2a78d6; --aqua:#1baf7a; --yellow:#eda100; --violet:#4a3aa7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --surface-1:#1a1a19; --page:#0d0d0d; --text-primary:#ffffff; --text-secondary:#c3c2b7;
      --muted:#898781; --grid:#2c2c2a; --baseline:#383835; --border: rgba(255,255,255,0.10);
      --good:#0ca30c; --critical:#e66767; --blue:#3987e5; --aqua:#199e70; --yellow:#c98500; --violet:#9085e9;
    }}
  }}
  :root[data-theme="dark"] {{
    --surface-1:#1a1a19; --page:#0d0d0d; --text-primary:#ffffff; --text-secondary:#c3c2b7;
    --grid:#2c2c2a; --baseline:#383835; --border: rgba(255,255,255,0.10);
    --critical:#e66767; --blue:#3987e5; --aqua:#199e70; --yellow:#c98500; --violet:#9085e9;
  }}
  :root[data-theme="light"] {{
    --surface-1:#fcfcfb; --page:#f9f9f7; --text-primary:#0b0b0b; --text-secondary:#52514e;
    --grid:#e1e0d9; --baseline:#c3c2b7; --border: rgba(11,11,11,0.10);
    --critical:#d03b3b; --blue:#2a78d6; --aqua:#1baf7a; --yellow:#eda100; --violet:#4a3aa7;
  }}
  * {{ box-sizing: border-box; }}
  body, .dash {{ background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", Tahoma, sans-serif; }}
  .dash {{ direction: rtl; max-width: 1180px; margin: 0 auto; padding: 24px 20px 64px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); font-size: 13px; margin-bottom: 24px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap: 10px; margin-bottom: 28px; }}
  .kpi {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
  .kpi .label {{ color: var(--text-secondary); font-size: 12px; margin-bottom: 6px; }}
  .kpi .value {{ font-size: 21px; font-weight: 600; font-variant-numeric: tabular-nums; direction: ltr; text-align: right; }}
  section {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; margin-bottom: 20px; }}
  section h2 {{ font-size: 16px; margin: 0 0 4px; }}
  section .note {{ color: var(--text-secondary); font-size: 12px; margin-bottom: 14px; }}
  .legend {{ display:flex; gap:16px; font-size:12px; color:var(--text-secondary); margin-bottom:10px; }}
  .legend span {{ display:inline-flex; align-items:center; gap:6px; }}
  .swatch {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
  .barrow {{ display:grid; grid-template-columns: 110px 1fr 100px; align-items:center; gap:10px; margin:6px 0; font-size:13px; }}
  .barrow .name {{ color: var(--text-primary); }}
  .barrow .track {{ height: 16px; background: var(--grid); border-radius: 4px; overflow:hidden; display:flex; }}
  .barrow .seg.current {{ background: var(--good); }}
  .barrow .seg.arrears {{ background: var(--critical); }}
  .barrow .total {{ text-align:left; direction:ltr; font-variant-numeric: tabular-nums; color: var(--text-secondary); }}
  table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 7px 8px; border-bottom: 1px solid var(--grid); text-align: right; }}
  th {{ color: var(--text-secondary); font-weight: 600; cursor: pointer; user-select: none; white-space: nowrap; }}
  th.sorted::after {{ content: " \25BE"; }}
  td.num, th.num {{ direction: ltr; text-align: right; font-variant-numeric: tabular-nums; }}
  .tablewrap {{ max-height: 480px; overflow: auto; border: 1px solid var(--grid); border-radius: 8px; }}
  .controls {{ display:flex; gap:10px; margin-bottom: 12px; flex-wrap: wrap; }}
  input[type=text] {{ background: var(--page); border: 1px solid var(--border); color: var(--text-primary);
    border-radius: 8px; padding: 7px 10px; font-size: 13px; min-width: 220px; }}
  .tabs {{ display:flex; gap:6px; }}
  .tab {{ padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); font-size: 12px; cursor: pointer; color: var(--text-secondary); }}
  .tab.active {{ background: var(--blue); color: #fff; border-color: var(--blue); }}
  .badge {{ display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }}
  .badge.ابوهاشم {{ background: color-mix(in srgb, var(--blue) 18%, transparent); color: var(--blue); }}
  .badge.الهنا {{ background: color-mix(in srgb, var(--aqua) 18%, transparent); color: var(--aqua); }}
  .badge.اسبشيال {{ background: color-mix(in srgb, var(--violet) 18%, transparent); color: var(--violet); }}
  .pct-bad {{ color: var(--critical); }}
  footer {{ color: var(--muted); font-size: 11px; margin-top: 10px; }}
</style>

<div class="dash">
  <h1>تحليل المبيعات والمديونية — أبو هاشم للحوم</h1>
  <div class="subtitle">{date_range} · تاريخ المديونية: 2026/7/4 · عدد الفواتير: {invoice_count}</div>

  <div class="kpis">
    <div class="kpi"><div class="label">إجمالي المبيعات (غير البونص)</div><div class="value">{total_sales}</div></div>
    <div class="kpi"><div class="label">إجمالي الكمية المباعة</div><div class="value">{total_qty}</div></div>
    <div class="kpi"><div class="label">إجمالي المديونية الحالية</div><div class="value">{total_debt}</div></div>
    <div class="kpi"><div class="label">منها متأخرات (أكثر من شهر)</div><div class="value">{total_arrears}</div></div>
    <div class="kpi"><div class="label">عدد فواتير البونص (صفر)</div><div class="value">{zero_count} <span style="font-size:12px;color:var(--text-secondary)">({zero_pct}%)</span></div></div>
    <div class="kpi"><div class="label">عدد العملاء</div><div class="value">{cust_count}</div></div>
  </div>

  <section>
    <h2>مديونية المندوبين — الحالي مقابل المتأخر</h2>
    <div class="note">المتأخر = رصيد العميل الحالي (تقرير 2026/7/4) لعميل لم تصدر له فاتورة منذ أكثر من 30 يومًا. راجع analysis/README.md لتفاصيل المنهجية.</div>
    <div class="legend">
      <span><span class="swatch" style="background:var(--good)"></span> حالي (خلال آخر 30 يوم)</span>
      <span><span class="swatch" style="background:var(--critical)"></span> متأخر (أكثر من 30 يوم)</span>
    </div>
    <div id="rep-chart"></div>
    <div class="tablewrap" style="margin-top:14px;">
      <table id="rep-table"></table>
    </div>
  </section>

  <section>
    <h2>العملاء — المبيعات، الكمية، نسبة البونص، والمديونية</h2>
    <div class="note">"نسبة البونص" = كمية الأصناف المسلَّمة بقيمة صفر (فواتير بونص) ÷ إجمالي الكمية.</div>
    <div class="controls">
      <input type="text" id="cust-filter" placeholder="بحث بالاسم أو الكود أو المندوب…">
    </div>
    <div class="tablewrap">
      <table id="cust-table"></table>
    </div>
  </section>

  <section>
    <h2>الأصناف — الكمية ومتوسط سعر البيع</h2>
    <div class="note">متوسط سعر البيع = إجمالي قيمة الفواتير غير الصفرية ÷ إجمالي الكمية لنفس الصنف (تجاوزًا لالتباس ترتيب أعمدة الخصم/الضريبة الموضح في README).</div>
    <div class="controls">
      <input type="text" id="item-filter" placeholder="بحث باسم الصنف أو الكود…">
      <div class="tabs" id="brand-tabs"></div>
    </div>
    <div class="tablewrap">
      <table id="item-table"></table>
    </div>
  </section>

  <section>
    <h2>فواتير البونص (صفرية القيمة)</h2>
    <div class="note">{zero_count} فاتورة من إجمالي {invoice_count} (~{zero_pct}%) بقيمة صفر — أصناف مجانية/بونص، مستبعدة من المبيعات ومحتسبة في الكميات فقط.</div>
    <div class="controls">
      <input type="text" id="zero-filter" placeholder="بحث بالعميل أو رقم الفاتورة…">
    </div>
    <div class="tablewrap">
      <table id="zero-table"></table>
    </div>
  </section>

  <footer>تم إنشاؤه من ملفات فواتير المبيعات (2025/1/1 - 2026/6/30) وتقارير مديونية المندوبين (2026/7/4). راجع analysis/README.md للمنهجية والقيود الكاملة.</footer>
</div>

<script>
const REP = {rep_json};
const CUST = {cust_json};
const ITEMS = {items_json};
const ZERO = {zero_json};

function fmt(n) {{ return Math.round(n).toLocaleString('en-US'); }}
function pct(n) {{ return (Math.round(n*10)/10).toLocaleString('en-US'); }}

function renderRepChart() {{
  const el = document.getElementById('rep-chart');
  const maxTotal = Math.max(...REP.map(r => r.total_debt));
  el.innerHTML = REP.map(r => {{
    const curW = (r.current_amount / maxTotal * 100).toFixed(2);
    const arrW = (r.arrears_amount / maxTotal * 100).toFixed(2);
    return `<div class="barrow">
      <div class="name">${{r.rep}}</div>
      <div class="track"><div class="seg current" style="width:${{curW}}%"></div><div class="seg arrears" style="width:${{arrW}}%"></div></div>
      <div class="total">${{fmt(r.total_debt)}}</div>
    </div>`;
  }}).join('');
}}

function makeSortableTable(tableId, columns, rows, opts) {{
  opts = opts || {{}};
  const table = document.getElementById(tableId);
  let sortCol = opts.defaultSort || columns[0].key;
  let sortDir = opts.defaultDir || 'desc';
  let filterFn = () => true;

  function render() {{
    let data = rows.filter(filterFn);
    data.sort((a, b) => {{
      const av = a[sortCol], bv = b[sortCol];
      let cmp;
      if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv;
      else cmp = String(av).localeCompare(String(bv), 'ar');
      return sortDir === 'asc' ? cmp : -cmp;
    }});
    const thead = '<thead><tr>' + columns.map(c =>
      `<th class="${{c.num ? 'num' : ''}} ${{c.key === sortCol ? 'sorted' : ''}}" data-key="${{c.key}}">${{c.label}}</th>`
    ).join('') + '</tr></thead>';
    const tbody = '<tbody>' + data.map(row => '<tr>' + columns.map(c => {{
      let v = row[c.key];
      if (c.fmt) v = c.fmt(v, row);
      return `<td class="${{c.num ? 'num' : ''}}">${{v}}</td>`;
    }}).join('') + '</tr>').join('') + '</tbody>';
    table.innerHTML = thead + tbody;
    table.querySelectorAll('th').forEach(th => {{
      th.addEventListener('click', () => {{
        const key = th.dataset.key;
        if (key === sortCol) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        else {{ sortCol = key; sortDir = 'desc'; }}
        render();
      }});
    }});
  }}
  render();
  return {{ setFilter: (fn) => {{ filterFn = fn; render(); }} }};
}}

renderRepChart();

makeSortableTable('rep-table', [
  {{key:'rep', label:'المندوب'}},
  {{key:'customer_count', label:'عدد العملاء', num:true}},
  {{key:'total_debt', label:'إجمالي المديونية', num:true, fmt:fmt}},
  {{key:'current_amount', label:'حالي', num:true, fmt:fmt}},
  {{key:'arrears_amount', label:'متأخر', num:true, fmt:fmt}},
  {{key:'total_credit_balance', label:'رصيد دائن للعميل', num:true, fmt:fmt}},
], REP, {{defaultSort:'total_debt'}});

const custTableCtl = makeSortableTable('cust-table', [
  {{key:'customer_code', label:'الكود', num:true}},
  {{key:'customer_name', label:'اسم العميل'}},
  {{key:'rep', label:'المندوب'}},
  {{key:'sales_value', label:'إجمالي المبيعات', num:true, fmt:fmt}},
  {{key:'total_qty', label:'الكمية', num:true, fmt:fmt}},
  {{key:'bonus_pct', label:'% بونص', num:true, fmt:(v)=> `<span class="${{v>=10?'pct-bad':''}}">${{pct(v)}}%</span>`}},
  {{key:'debt_amount', label:'المديونية', num:true, fmt:fmt}},
  {{key:'arrears_amount', label:'متأخر', num:true, fmt:fmt}},
  {{key:'invoice_count', label:'عدد الفواتير', num:true}},
], CUST, {{defaultSort:'sales_value'}});

document.getElementById('cust-filter').addEventListener('input', (e) => {{
  const q = e.target.value.trim();
  custTableCtl.setFilter(q === '' ? () => true : (r) =>
    (r.customer_name + r.customer_code + r.rep).includes(q));
}});

const itemColumns = [
  {{key:'item_code', label:'الكود', num:true}},
  {{key:'item_name', label:'اسم الصنف'}},
  {{key:'brand', label:'البراند', fmt: (v) => `<span class="badge ${{v}}">${{v}}</span>`}},
  {{key:'total_qty', label:'إجمالي الكمية', num:true, fmt:fmt}},
  {{key:'paid_qty', label:'كمية غير بونص', num:true, fmt:fmt}},
  {{key:'avg_selling_price', label:'متوسط سعر البيع', num:true, fmt:(v)=> v ? pct(v) : '—'}},
];
const itemTableCtl = makeSortableTable('item-table', itemColumns, ITEMS, {{defaultSort:'total_qty'}});

let itemBrandFilter = 'الكل';
let itemQuery = '';
function applyItemFilter() {{
  itemTableCtl.setFilter((r) => {{
    const brandOk = itemBrandFilter === 'الكل' || r.brand === itemBrandFilter;
    const q = itemQuery.trim();
    const textOk = q === '' || (r.item_name + r.item_code).includes(q);
    return brandOk && textOk;
  }});
}}
document.getElementById('item-filter').addEventListener('input', (e) => {{ itemQuery = e.target.value; applyItemFilter(); }});
const brands = ['الكل', ...new Set(ITEMS.map(r => r.brand))];
document.getElementById('brand-tabs').innerHTML = brands.map(b =>
  `<div class="tab ${{b==='الكل'?'active':''}}" data-brand="${{b}}">${{b}}</div>`).join('');
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  itemBrandFilter = t.dataset.brand;
  applyItemFilter();
}}));

const zeroTableCtl = makeSortableTable('zero-table', [
  {{key:'invoice_no', label:'رقم الفاتورة'}},
  {{key:'date', label:'التاريخ', num:true}},
  {{key:'customer_code', label:'الكود', num:true}},
  {{key:'customer_name', label:'اسم العميل'}},
  {{key:'qty', label:'الكمية', num:true, fmt:fmt}},
  {{key:'notes', label:'ملاحظات'}},
], ZERO, {{defaultSort:'date', defaultDir:'desc'}});
document.getElementById('zero-filter').addEventListener('input', (e) => {{
  const q = e.target.value.trim();
  zeroTableCtl.setFilter(q === '' ? () => true : (r) => (r.customer_name + r.customer_code + r.invoice_no).includes(q));
}});
</script>
"""


def main():
    rep, cust_sales, cust_debt, items, zero_inv, headers = load()

    rep = to_num(rep, ["debt_pdf_snapshot_net_2026_07_04", "total_debt", "current_amount", "arrears_amount", "total_credit_balance", "customer_count"])
    items = to_num(items, ["total_qty", "paid_qty", "paid_value", "avg_selling_price", "line_count"])
    zero_inv = to_num(zero_inv, ["qty"])

    cust360 = build_customers_360(cust_sales, cust_debt)

    total_sales = cust360["sales_value"].sum()
    total_qty = cust360["total_qty"].sum()
    total_debt = rep["total_debt"].sum()
    total_arrears = rep["arrears_amount"].sum()
    zero_count = zero_inv.height
    invoice_count = headers.height
    zero_pct = round(zero_count / invoice_count * 100, 1)
    cust_count = cust360.height

    fragment = FRAGMENT_TEMPLATE.format(
        date_range="فواتير: 2025/1/1 → 2026/6/30",
        invoice_count=f"{invoice_count:,}",
        total_sales=fmt_money(total_sales),
        total_qty=fmt_money(total_qty),
        total_debt=fmt_money(total_debt),
        total_arrears=fmt_money(total_arrears),
        zero_count=f"{zero_count:,}",
        zero_pct=zero_pct,
        cust_count=f"{cust_count:,}",
        rep_json=json.dumps(rep.to_dicts(), ensure_ascii=False),
        cust_json=json.dumps(cust360.to_dicts(), ensure_ascii=False),
        items_json=json.dumps(items.to_dicts(), ensure_ascii=False),
        zero_json=json.dumps(zero_inv.sort("date", descending=True).to_dicts(), ensure_ascii=False),
    )

    full_doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>تحليل المبيعات والمديونية — أبو هاشم للحوم</title>
</head>
<body>
{fragment}
</body>
</html>
"""
    OUT_FULL.write_text(full_doc, encoding="utf-8")
    print(f"Wrote {OUT_FULL}")

    if len(sys.argv) > 1:
        frag_path = Path(sys.argv[1])
        frag_path.write_text(fragment, encoding="utf-8")
        print(f"Wrote fragment {frag_path}")


if __name__ == "__main__":
    main()
