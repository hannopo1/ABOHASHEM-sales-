"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const {Blob} = require("node:buffer");
const {TextDecoder, TextEncoder} = require("node:util");

const SRC = path.resolve(__dirname, "../src");

function load(names, expose, globals = {}) {
  const context = vm.createContext({
    Blob,
    TextDecoder,
    TextEncoder,
    console,
    setTimeout,
    clearTimeout,
    ...globals,
  });
  context.window = context;
  for (const name of names) {
    vm.runInContext(fs.readFileSync(path.join(SRC, name), "utf8"), context, {
      filename: name,
    });
  }
  vm.runInContext(`globalThis.__tested = {${expose.join(",")}}`, context);
  return {context, ...context.__tested};
}

const plain = value => JSON.parse(JSON.stringify(value));

function detailedPayload() {
  return {
    meta: {
      as_of: "2026-04-30",
      net_terms_days: 30,
      available_months: [
        {v: "2026-03", l: "مارس 2026"},
        {v: "2026-04", l: "أبريل 2026"},
      ],
      data_months: ["2026-04"],
      all_months_label: "كل الفترة",
    },
    lines: [
      {invoice_no: "I1", month: "2026-03", customer_code: "C1", rep: "R1",
       brand: "B1", item_code: "P1", item_name: "One", qty: 2, boxes: 1,
       unit_price: 50, line_total: 100},
      {invoice_no: "I2", month: "2026-04", customer_code: "C1", rep: "R1",
       brand: "B2", item_code: "P2", item_name: "Two", qty: 1, boxes: 0.5,
       unit_price: 50, line_total: 50},
      {invoice_no: "I3", month: "2026-04", customer_code: "C2", rep: "R2",
       brand: "B1", item_code: "P1", item_name: "One", qty: 3, boxes: 1,
       unit_price: 40, line_total: 120},
    ],
    invoices: [
      {invoice_no: "I1", invoice_date: "2026-03-01", month: "2026-03",
       customer_code: "C1", customer_name: "Alpha", rep: "R1", status: "unpaid",
       reported_total: 100, paid: 10, remaining: 90},
      {invoice_no: "I2", invoice_date: "2026-04-15", month: "2026-04",
       customer_code: "C1", customer_name: "Alpha", rep: "R1", status: "paid",
       reported_total: 50, paid: 50, remaining: 0},
      {invoice_no: "I3", invoice_date: "2026-04-20", month: "2026-04",
       customer_code: "C2", customer_name: "Beta", rep: "R2", status: "unpaid",
       reported_total: 120, paid: 0, remaining: 120},
    ],
    receivables: {rows: [
      {customer_code: "C1", customer_name: "Alpha", rep: "R1", outstanding: 90,
       overdue: 90, bucket: "d1_30",
       buckets: {current: 0, d1_30: 90, d31_60: 0, d61_90: 0, d91_120: 0, d120p: 0}},
      {customer_code: "C2", customer_name: "Beta", rep: "R2", outstanding: 120,
       overdue: 0, bucket: "current",
       buckets: {current: 120, d1_30: 0, d31_60: 0, d61_90: 0, d91_120: 0, d120p: 0}},
    ]},
    customer_ar: {
      C1: {rep: "R1", city: "Cairo", total_billed: 150, billed_2026: 150,
           outstanding: 90, collected_actual: 60, returns_actual: 5,
           collection_rate: 0.4, bonus_pct: 0.01, has_ar: true},
    },
    collections: {receipts: []},
    insights_by_month: {all: {headline: "all"}, "2026-04": {headline: "April"}},
  };
}

test("detailed dashboard API composes brand and status filters", () => {
  const {A} = load(["dash-tokens.js", "dash-agg.js"], ["A"]);
  const api = A.makeApi(detailedPayload());

  const brand = api.buildContext({month: "all", brand: "B1"});
  assert.deepEqual(plain(brand.lines.map(x => x.invoice_no)), ["I1", "I3"]);
  assert.deepEqual(plain(brand.invoices.map(x => x.invoice_no)), ["I1", "I3"]);
  assert.equal(brand.kpis.total_sales, 220);
  assert.equal(brand.kpis.net_sales, 220);
  assert.equal(brand.kpis.n_customers, 2);
  assert.equal(brand.products[0].item_code, "P1");
  assert.equal(brand.products[0].contribution_pct, 100);

  const paid = api.buildContext({month: "all", status: "paid"});
  assert.deepEqual(plain(paid.invoices.map(x => x.invoice_no)), ["I2"]);
  assert.deepEqual(plain(paid.lines.map(x => x.invoice_no)), ["I2"]);
  assert.equal(paid.customers[0].avg_invoice_value, 50);
});

test("detailed dashboard API reports unavailable months and safe empty aggregates", () => {
  const {A} = load(["dash-tokens.js", "dash-agg.js"], ["A"]);
  const api = A.makeApi(detailedPayload());

  assert.equal(api.curMonthLabel("2026-03"), "مارس 2026 — لا توجد بيانات");
  assert.equal(api.curMonthLabel("2026-04"), "أبريل 2026");
  assert.equal(api.insight("2026-04", "headline"), "April");
  assert.equal(api.insight("2026-03", "missing"), null);

  const empty = api.buildContext({month: "2099-01"});
  assert.equal(empty.kpis.asp, 0);
  assert.equal(empty.kpis.avg_invoice_value, 0);
  assert.equal(empty.kpis.collection_rate, 0);
  assert.equal(empty.products.length, 0);
});

function aggregatePayload() {
  return {
    financial: {total_revenue_egp: 500},
    dim_customers: [
      {customer_code: "C1", rep: "R1"},
      {customer_code: "C2", rep: ""},
    ],
    hierarchy_tree: [
      {customer_code: "C1", name: "Alpha", brands: {
        Red: {items: [{name: "Steak", sales: 100, qty: 5}, {name: "Zero", sales: 20, qty: 0}]},
        Blue: {items: [{name: "Steak", sales: 50, qty: 2}]},
      }},
      {customer_code: "C2", name: "Beta", brands: {
        Red: {items: [{name: "Burger", sales: 200, qty: 10}]},
      }},
    ],
    monthly_series: [{month: "2026-01"}, {month: "2026-02"}, {month: "2026-03"}],
    brand_month_revenue: [
      {brand: "Red", month: "2026-01", line_total: 12},
      {brand: "Blue", month: "2026-02", line_total: 7},
    ],
  };
}

test("aggregate filters compose across rep, brand, customer and item", () => {
  const {R} = load(["repo-adapter.js"], ["R"]);
  const D = aggregatePayload();

  const all = R.applyFilters(D, null);
  assert.equal(all.sales, 370);
  assert.equal(all.qty, 17);
  assert.equal(all.nCustomers, 2);
  assert.equal(all.shareOfTotal, 74);
  assert.equal(all.byRep[0].name, R.UNASSIGNED_REP);
  assert.equal(all.byRep[0].sales, 200);
  assert.equal(all.monthlyAvailability, "company");

  const slice = R.applyFilters(D, {
    rep: "R1", brand: "Red", customerCode: "C1", itemName: "Steak",
  });
  assert.equal(slice.sales, 100);
  assert.equal(slice.qty, 5);
  assert.equal(slice.avgPrice, 20);
  assert.equal(slice.nBrands, 1);
  assert.equal(slice.nItems, 1);
  assert.equal(slice.monthlyAvailability, "unavailable");
  assert.deepEqual(plain([...R.matchingCustomerCodes(D, {brand: "Red"})]), ["C2", "C1"]);
});

test("aggregate filters preserve honest empty and monthly states", () => {
  const {R} = load(["repo-adapter.js"], ["R"]);
  const D = aggregatePayload();

  const zeroQty = R.applyFilters(D, {itemName: "Zero"});
  assert.equal(zeroQty.sales, 20);
  assert.equal(zeroQty.avgPrice, null);

  const missing = R.applyFilters(D, {customerCode: "missing"});
  assert.equal(missing.isEmpty, true);
  assert.equal(missing.avgPrice, null);
  assert.equal(missing.shareOfTotal, 0);
  assert.equal(R.monthlyAvailability({brand: "Red"}), "brand");
  assert.equal(R.matchingCustomerCodes(D, null), null);
  assert.deepEqual(plain(R.brandSeries(D, "Red")), [12, 0, 0]);
  assert.equal(R.activeFilterCount({rep: "R1", brand: "Red", customerCode: null, itemName: null}), 2);
});

function agingPayload() {
  const buckets = (current, old) => ({
    current, d1_30: 0, d31_60: 0, d61_90: 0, d91_120: 0, d120p: old,
  });
  return {
    meta: {as_of: "2026-04-30"},
    invoices: [
      {customer_code: 1, invoice_no: "old", invoice_date: "2026-01-01", reported_total: 100},
      {customer_code: 1, invoice_no: "new", invoice_date: "2026-04-15", reported_total: 50},
      {customer_code: 1, invoice_no: "sample", invoice_date: "2025-01-01", reported_total: 0},
      {customer_code: 2, invoice_no: "mid", invoice_date: "2026-02-15", reported_total: 100},
    ],
    collections: {
      receipts: [{customer_code: 1, amount: 120}, {customer_code: 2, amount: 20}],
      returns_rows: [{customer_code: 1, value: 10}, {customer_code: null, value: 7}],
    },
    receivables: {rows: [
      {customer_code: "1", customer_name: "Alpha", rep: "R1", outstanding: 70,
       buckets: buckets(70, 0)},
      {customer_code: "2", customer_name: "Beta", rep: "R2", outstanding: 50,
       buckets: buckets(0, 50)},
      {customer_code: "3", customer_name: "Opening", outstanding: 40,
       buckets: buckets(40, 0)},
    ]},
  };
}

test("FIFO aging honors exact tier boundaries", () => {
  const {G} = load(["dash-tokens.js", "dash-aging.js"], ["G"]);
  assert.equal(G.tierOf(-1), "lt30");
  assert.equal(G.tierOf(0), "lt30");
  assert.equal(G.tierOf(29), "lt30");
  assert.equal(G.tierOf(30), "m1_2");
  assert.equal(G.tierOf(60), "m2_3");
  assert.equal(G.tierOf(90), "gt90");
});

test("FIFO aging partitions dated, opening, and overpaid balances", () => {
  const {G} = load(["dash-tokens.js", "dash-aging.js"], ["G"]);
  const D = agingPayload();
  const rows = G.agingRows(D);
  const byCode = Object.fromEntries(rows.map(row => [row.code, row]));

  assert.equal(byCode["1"].tiers.lt30, 20);
  assert.equal(byCode["1"].opening, 50);
  assert.equal(byCode["1"].nOpenInvoices, 1);
  assert.equal(byCode["1"].oldestInvoiceDate, "2026-04-15");
  assert.equal(byCode["2"].tiers.m2_3, 80);
  assert.equal(byCode["2"].overpaid, 30);
  assert.equal(byCode["3"].opening, 40);
  assert.equal(rows.unattributedReturns, 7);

  const totals = G.agingTotals(rows);
  assert.equal(totals.aged, 100);
  assert.equal(totals.opening, 90);
  assert.equal(totals.overpaid, 30);
  assert.equal(totals.snapshot, 160);
  assert.equal(totals.reconDelta, 0);
  assert.equal(totals.nOverpaid, 1);

  assert.equal(G.agingRows(D), rows, "same payload should use the WeakMap cache");
});

test("aging cohort, representative, and source-bucket rollups reconcile", () => {
  const {G} = load(["dash-tokens.js", "dash-aging.js"], ["G"]);
  const D = agingPayload();
  const cohort = G.agingFor(D, new Set(["1", "3"]));

  assert.deepEqual(plain(cohort.map(row => row.code)), ["1", "3"]);
  assert.equal(cohort.unattributedReturns, 7);
  assert.deepEqual(plain(G.sourceBuckets(cohort, D)), {
    current: 110, d1_30: 0, d31_60: 0, d61_90: 0, d91_120: 0, d120p: 0,
  });
  const reps = G.agingByRep(G.agingRows(D));
  assert.equal(reps[0].rep, "R1");
  assert.equal(reps.find(row => row.rep === "غير محدد").customers, 1);
});

function marginPayload() {
  return {
    meta: {
      reliable_months: ["2026-06", "2026-04", "2026-05"],
      cost_month: "2026-06", coverage_pct: 92,
      n_items_costed: 3, n_items_total: 4, revenue_uncosted: 40,
    },
    totals: {
      measured: {revenue_costed: 100, gross_profit: 20, op_profit: 10,
                 gross_margin_pct: 20, op_margin_pct: 10},
      indicative: {revenue_costed: 300, gross_profit: 90, op_profit: 30},
    },
    pricing_gap: Array.from({length: 14}, (_, i) => ({item: i})),
  };
}

test("profitability KPIs weight margins by covered revenue", () => {
  const {M} = load(["dash-margin.js"], ["M"]);
  const R = {
    fmtPct: x => x == null ? "—" : `${x.toFixed(1)}%`,
    fmtEGP: x => `${x} EGP`,
    C: {blue: "blue", indigo: "indigo", green: "green"},
    BRAND_COLORS: {Known: "brand"},
  };
  const d = marginPayload();
  const kpis = M.kpisWindow(d, R);

  assert.equal(kpis[0][1], "27.5%");
  assert.equal(kpis[1][1], "10.0%");
  assert.equal(kpis[0][2], "أبريل 2026 – يونيو 2026");
  assert.equal(kpis[2][1], "110 EGP");
  assert.equal(kpis[5][1], "40 EGP");
  assert.equal(M.kpisMeasured(d, R)[0][1], "20.0%");
});

test("profitability helpers cover missing, boundary, ordering, and limit cases", () => {
  const {M} = load(["dash-margin.js"], ["M"]);
  assert.equal(M.windowLabel({meta: {reliable_months: []}}), "—");
  assert.equal(M.arMonth(null), "");
  assert.equal(M.marginColour(null, 20), M.MUTED);
  assert.equal(M.marginColour(19, 20), M.OK);
  assert.equal(M.marginColour(15, 20), M.WARN);
  assert.equal(M.marginColour(14.9, 20), M.BAD);

  const rows = [
    {name: "Low", gross_margin_pct: 10},
    {name: "Missing", gross_margin_pct: null},
    {name: "Known", gross_margin_pct: 30},
  ];
  const R = {BRAND_COLORS: {Known: "brand"}};
  assert.deepEqual(plain(M.bars(rows, "name", R, 20)), [
    ["Known", 30, "brand"], ["Low", 10, M.BAD],
  ]);
  const gaps = marginPayload();
  assert.equal(M.pricingGap(gaps).length, 12);
  assert.equal(gaps.pricing_gap.length, 14, "limiting must not mutate source data");
});

test("profitability trend sorts months and visibly distinguishes unreliable data", () => {
  const {M} = load(["dash-margin.js"], ["M"]);
  const C = {ecBase: () => ({
    legend: {}, tooltip: {}, _muted: "muted", _grid: "grid",
  })};
  const d = {by_month: [
    {month: "2026-06", basis: "measured", indicative_reliable: false,
     gross_margin_pct: 20, op_margin_pct: 10, price_index: 100, cost_period_drift_pct: 0},
    {month: "2026-04", basis: "indicative", indicative_reliable: false,
     gross_margin_pct: 5, op_margin_pct: -2, price_index: 80, cost_period_drift_pct: -20},
    {month: "2026-05", basis: "indicative", indicative_reliable: true,
     gross_margin_pct: 18, op_margin_pct: 8, price_index: 97, cost_period_drift_pct: -3},
  ]};
  const chart = M.trend(d, C);

  assert.deepEqual(plain(chart.xAxis.data), ["أبريل 2026", "مايو 2026", "يونيو 2026"]);
  assert.equal(chart.series[0].data[0].itemStyle.color, "#475569");
  assert.equal(chart.series[0].data[1].itemStyle.color, "#3b82f6");
  assert.equal(chart.series[0].markArea.data[0][0].xAxis, "مايو 2026");
  assert.equal(M.trend({by_month: []}, C).__empty, true);
});

function exportModule(extra = {}) {
  return load(["dash-export.js"], ["X"], {
    REGISTRY: [],
    navigator: {},
    URL: {createObjectURL: () => "blob:test", revokeObjectURL: () => {}},
    ...extra,
  });
}

test("CSV export quotes delimiters, quotes, newlines, and nulls", () => {
  const {X} = exportModule();
  const table = {
    columns: [
      {label: "Name", get: r => r.name},
      {label: "Value,EGP", get: r => r.value},
      {label: "Note", get: r => r.note},
    ],
    rows: [{name: "A\"B", value: 12, note: null}, {name: "line\nbreak", value: 0, note: "ok"}],
  };
  assert.equal(
    X.toCSV(table),
    'Name,"Value,EGP",Note\r\n"A""B",12,\r\n"line\nbreak",0,ok\r\n',
  );
});

test("spreadsheet XML is RTL, escaped, and keeps numeric cells numeric", () => {
  const {X} = exportModule();
  const columns = Array.from({length: 27}, (_, i) => ({
    label: i === 0 ? "A&B" : `C${i}`,
    get: row => row[i],
  }));
  const values = Array(27).fill("");
  values[0] = 42.5;
  values[1] = "42.5";
  values[26] = '<tag "quoted">';
  const xml = X.sheetXML({columns, rows: [values]});

  assert.match(xml, /rightToLeft="1"/);
  assert.match(xml, /dimension ref="A1:AA2"/);
  assert.match(xml, /<c r="A2" s="0"><v>42\.5<\/v><\/c>/);
  assert.match(xml, /<c r="B2" t="inlineStr">/);
  assert.match(xml, /A&amp;B/);
  assert.match(xml, /&lt;tag &quot;quoted&quot;&gt;/);
});

test("XLSX writer emits a deterministic ZIP with required workbook parts", async () => {
  const {X} = exportModule();
  const tables = [{
    label: "Sales/2026[]:*?\\ name that is deliberately far too long for Excel",
    columns: [{label: "Amount", get: r => r.amount}],
    rows: [{amount: 12}],
  }];
  const first = new Uint8Array(await X.workbook(tables).arrayBuffer());
  const second = new Uint8Array(await X.workbook(tables).arrayBuffer());

  assert.deepEqual(first, second);
  assert.equal(new TextDecoder("latin1").decode(first.slice(0, 4)), "PK\u0003\u0004");
  const text = new TextDecoder().decode(first);
  for (const name of ["[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml",
                      "xl/worksheets/sheet1.xml"]) {
    assert.ok(text.includes(name), `${name} should be present`);
  }
  const sheetName = /<sheet name="([^"]+)"/.exec(text)[1];
  assert.ok(sheetName.length <= 28);
  assert.doesNotMatch(sheetName, /[\[\]:*?/\\]/);
});

test("PNG chart export disables animation and always disposes temporary charts", () => {
  const events = [];
  const host = {style: {}, remove: () => events.push("remove")};
  const document = {
    createElement: () => host,
    body: {appendChild: value => assert.equal(value, host)},
  };
  const temp = {
    setOption: (option, replace) => events.push(["set", option.animation, replace]),
    getDataURL: options => { events.push(["url", options.pixelRatio]); return "data:image/png;base64,AA=="; },
    dispose: () => events.push("dispose"),
  };
  const echarts = {
    init: (value, theme, options) => {
      assert.equal(value, host);
      assert.equal(theme, null);
      assert.deepEqual(plain(options), {renderer: "canvas", width: 320, height: 240});
      return temp;
    },
  };
  const {X} = exportModule({document, echarts});
  const option = {animation: true, series: [{data: [1]}]};
  const entry = {inst: {
    getDom: () => ({clientWidth: 100, clientHeight: 100}),
    getOption: () => option,
  }};

  assert.equal(X.chartPNGDataURL(entry, 3), "data:image/png;base64,AA==");
  assert.equal(option.animation, false);
  assert.deepEqual(events, [["set", false, true], ["url", 3], "dispose", "remove"]);
});

test("PNG chart export cleans up after an ECharts failure", () => {
  const events = [];
  const host = {style: {}, remove: () => events.push("remove")};
  const document = {createElement: () => host, body: {appendChild: () => {}}};
  const echarts = {init: () => ({
    setOption: () => { throw new Error("render failed"); },
    dispose: () => events.push("dispose"),
  })};
  const {X} = exportModule({document, echarts});
  const entry = {inst: {
    getDom: () => ({clientWidth: 640, clientHeight: 480}),
    getOption: () => ({animation: true}),
  }};

  assert.throws(() => X.chartPNGDataURL(entry, 2), /render failed/);
  assert.deepEqual(events, ["dispose", "remove"]);
});
