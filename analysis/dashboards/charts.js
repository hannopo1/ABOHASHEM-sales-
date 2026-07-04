/* Minimal self-contained SVG chart helpers - no external dependencies. */
const PALETTE = {
  series: ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"],
  seriesDark: ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767", "#d55181", "#d95926"],
  good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b",
};

function isDark() {
  const root = document.documentElement;
  if (root.getAttribute("data-theme") === "dark") return true;
  if (root.getAttribute("data-theme") === "light") return false;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function seriesColor(i) { return (isDark() ? PALETTE.seriesDark : PALETTE.series)[i % 8]; }

function fmtNum(n, d = 0) {
  if (n === null || n === undefined || isNaN(n)) return "-";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
}
function fmtPct(n, d = 1) { return (n === null || n === undefined || isNaN(n)) ? "-" : Number(n).toFixed(d) + "%"; }
function fmtEGP(n) { return fmtNum(n, 0) + " ج.م"; }

function el(tag, attrs = {}, children = []) {
  const ns = "http://www.w3.org/2000/svg";
  const isSvg = ["svg", "rect", "circle", "line", "path", "text", "g", "polyline", "polygon", "tspan"].includes(tag);
  const e = isSvg ? document.createElementNS(ns, tag) : document.createElement(tag);
  for (const k in attrs) {
    if (k === "class") e.setAttribute("class", attrs[k]);
    else if (k === "text") e.textContent = attrs[k];
    else e.setAttribute(k, attrs[k]);
  }
  children.forEach((c) => e.appendChild(c));
  return e;
}

function tooltip() {
  let tt = document.getElementById("__viz_tooltip");
  if (!tt) {
    tt = document.createElement("div");
    tt.id = "__viz_tooltip";
    tt.className = "viz-tooltip";
    document.body.appendChild(tt);
  }
  return tt;
}
function showTip(evt, html) {
  const tt = tooltip();
  tt.innerHTML = html;
  tt.style.display = "block";
  tt.style.left = evt.pageX + 14 + "px";
  tt.style.top = evt.pageY + 10 + "px";
}
function hideTip() { const tt = tooltip(); tt.style.display = "none"; }

/* Horizontal bar chart: data = [{label, value}], single series.
   Rendered as HTML/CSS flex rows rather than SVG <text> - SVG text-anchor
   does not reliably respect RTL (Arabic) runs across browsers, which was
   silently clipping name labels behind the bar fill. HTML text handles
   Arabic bidi correctly by default. */
function hBarChart(container, data, opts = {}) {
  container.innerHTML = "";
  const rowH = opts.rowH || 28;
  const maxV = Math.max(...data.map((d) => d.value), 1);
  const labelW = opts.labelW || 170;
  const wrap = el("div", { class: "hbar-wrap" });
  data.forEach((d) => {
    const row = el("div", { class: "hbar-row" });
    row.style.height = rowH + "px";
    const label = el("div", { class: "hbar-label", text: d.label });
    label.style.width = labelW + "px";
    label.title = d.label;
    const track = el("div", { class: "hbar-track" });
    const barPct = Math.max(1, (d.value / maxV) * 100);
    const bar = el("div", { class: "viz-bar hbar-fill" });
    bar.style.width = barPct + "%";
    bar.style.background = opts.color || seriesColor(0);
    bar.addEventListener("mousemove", (e) => showTip(e, `<b>${d.label}</b><br>${opts.fmt ? opts.fmt(d.value) : fmtNum(d.value)}`));
    bar.addEventListener("mouseleave", hideTip);
    const value = el("div", { class: "hbar-value", text: opts.fmt ? opts.fmt(d.value) : fmtNum(d.value) });
    track.appendChild(bar);
    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(value);
    wrap.appendChild(row);
  });
  container.appendChild(wrap);
}

/* Line chart with optional band (ci lower/upper) and optional split at forecast start */
function lineChart(container, series, opts = {}) {
  container.innerHTML = "";
  const w = container.clientWidth || 700;
  const h = opts.h || 260;
  const padL = 60, padR = 20, padT = 20, padB = 34;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  // Unified category x-axis: the union of every series' x labels, sorted.
  // Each series is then positioned by its LOOKUP index in this shared axis
  // (not its own local array index) so a shorter forecast series lines up
  // with the correct calendar months instead of collapsing onto the start
  // of the historical series.
  const allX = [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort();
  const xIndex = new Map(allX.map((x, i) => [x, i]));
  const allY = series.flatMap((s) => s.points.flatMap((p) => [p.y, p.lo ?? p.y, p.hi ?? p.y]));
  const minY = Math.min(0, ...allY), maxY = Math.max(...allY) * 1.08;
  const n = allX.length;
  const xPos = (i) => padL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
  const yPos = (v) => padT + plotH - ((v - minY) / (maxY - minY || 1)) * plotH;

  const svg = el("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, class: "viz-root" });
  // gridlines
  for (let g = 0; g <= 4; g++) {
    const yy = padT + (g / 4) * plotH;
    svg.appendChild(el("line", { x1: padL, x2: w - padR, y1: yy, y2: yy, class: "viz-grid" }));
    const val = maxY - (g / 4) * (maxY - minY);
    svg.appendChild(el("text", { x: padL - 8, y: yy + 4, "text-anchor": "end", class: "viz-axis", text: opts.fmtY ? opts.fmtY(val) : fmtNum(val) }));
  }
  // x labels (sparse)
  allX.forEach((xv, i) => {
    if (n > 10 && i % Math.ceil(n / 8) !== 0 && i !== n - 1) return;
    svg.appendChild(el("text", { x: xPos(i), y: h - 8, "text-anchor": "middle", class: "viz-axis", text: xv }));
  });

  series.forEach((s, si) => {
    const color = s.color || seriesColor(si);
    const idxOf = (p) => xIndex.get(p.x);
    // CI band
    if (s.points.some((p) => p.lo !== undefined)) {
      const top = s.points.map((p) => `${xPos(idxOf(p))},${yPos(p.hi)}`).join(" ");
      const bot = s.points.slice().reverse().map((p) => `${xPos(idxOf(p))},${yPos(p.lo)}`).join(" ");
      svg.appendChild(el("polygon", { points: `${top} ${bot}`, fill: color, opacity: 0.15, stroke: "none" }));
    }
    const pts = s.points.map((p) => `${xPos(idxOf(p))},${yPos(p.y)}`).join(" ");
    const dash = s.dashed ? "6,4" : "none";
    svg.appendChild(el("polyline", { points: pts, fill: "none", stroke: color, "stroke-width": 2.5, "stroke-dasharray": dash }));
    s.points.forEach((p) => {
      const c = el("circle", { cx: xPos(idxOf(p)), cy: yPos(p.y), r: 4, fill: color, class: "viz-point" });
      c.addEventListener("mousemove", (e) => showTip(e, `<b>${s.name}</b><br>${p.x}: ${opts.fmtY ? opts.fmtY(p.y) : fmtNum(p.y)}`));
      c.addEventListener("mouseleave", hideTip);
      svg.appendChild(c);
    });
  });
  container.appendChild(svg);
  if (series.length > 1 || opts.legend) {
    const leg = el("div", { class: "viz-legend" });
    series.forEach((s, si) => {
      const item = el("span", { class: "viz-legend-item" });
      item.innerHTML = `<span class="viz-swatch" style="background:${s.color || seriesColor(si)}"></span>${s.name}`;
      leg.appendChild(item);
    });
    container.appendChild(leg);
  }
}

/* Donut chart: data = [{label, value}] */
function donutChart(container, data, opts = {}) {
  container.innerHTML = "";
  const size = opts.size || 220;
  const cx = size / 2, cy = size / 2, r = size / 2 - 10, r0 = r * 0.58;
  const total = data.reduce((a, d) => a + d.value, 0) || 1;
  const svg = el("svg", { width: size, height: size, viewBox: `0 0 ${size} ${size}`, class: "viz-root" });
  let angle = -Math.PI / 2;
  data.forEach((d, i) => {
    const frac = d.value / total;
    const a0 = angle, a1 = angle + frac * 2 * Math.PI;
    angle = a1;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const xi0 = cx + r0 * Math.cos(a1), yi0 = cy + r0 * Math.sin(a1);
    const xi1 = cx + r0 * Math.cos(a0), yi1 = cy + r0 * Math.sin(a0);
    const path = `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${xi0},${yi0} A${r0},${r0} 0 ${large} 0 ${xi1},${yi1} Z`;
    const color = d.color || seriesColor(i);
    const p = el("path", { d: path, fill: color, stroke: "var(--surface-1)", "stroke-width": 2 });
    p.addEventListener("mousemove", (e) => showTip(e, `<b>${d.label}</b><br>${fmtPct((d.value / total) * 100)} (${opts.fmt ? opts.fmt(d.value) : fmtNum(d.value)})`));
    p.addEventListener("mouseleave", hideTip);
    svg.appendChild(p);
  });
  container.appendChild(svg);
  const leg = el("div", { class: "viz-legend" });
  data.forEach((d, i) => {
    const item = el("span", { class: "viz-legend-item" });
    item.innerHTML = `<span class="viz-swatch" style="background:${d.color || seriesColor(i)}"></span>${d.label} (${fmtPct((d.value / total) * 100)})`;
    leg.appendChild(item);
  });
  container.appendChild(leg);
}

/* KPI tile */
function kpiTile(container, label, value, sub) {
  const tile = el("div", { class: "kpi-tile" });
  tile.innerHTML = `<div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ""}`;
  container.appendChild(tile);
}

/* Simple sortable table */
function dataTable(container, columns, rows, opts = {}) {
  container.innerHTML = "";
  const table = el("table", { class: "viz-table" });
  const thead = el("thead");
  const trh = el("tr");
  columns.forEach((c) => trh.appendChild(el("th", { text: c.label })));
  thead.appendChild(trh);
  table.appendChild(thead);
  const tbody = el("tbody");
  rows.slice(0, opts.limit || rows.length).forEach((r) => {
    const tr = el("tr");
    columns.forEach((c) => {
      const v = c.fmt ? c.fmt(r[c.key]) : r[c.key];
      tr.appendChild(el("td", { text: v }));
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}
