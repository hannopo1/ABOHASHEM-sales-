/* Abu Hashem — mobile runtime · استخراج التقارير والرسوم (export).

   Four formats, all produced on the device with no network and no server:

     CSV    UTF-8 with a BOM, so Excel opens Arabic correctly instead of as
            mojibake. This is the single most common failure when exporting
            Arabic CSV and the BOM is the whole fix.
     XLSX   Written here as OOXML inside a ZIP built by the small writer below.
            No library: a spreadsheet is a handful of XML parts, and shipping a
            ZIP dependency to emit them would cost more than it saves.
     PNG    Straight off the live ECharts instance via getDataURL.
     SVG    renderToSVGString on the same instance — vector, so it stays sharp
            in a report at any size.
     PDF    Through the browser's own print dialogue. A JavaScript PDF library
            cannot shape Arabic without a text-shaping engine and would emit
            disjoint, reversed glyphs; the browser already shapes the page
            correctly, so print-to-PDF is the only route that produces a
            readable Arabic document offline.

   Downloads use a blob and an <a download>. On iOS Safari that is unreliable
   from file://, so the Web Share API is tried first where the platform offers
   it for files. */
const X = (function(){

/* --------------------------------------------------------------- utilities */

const pad = n => String(n).padStart(2, "0");

/**
 * Creates a timestamp formatted as `YYYYMMDD-HHMM`.
 * @return {string} The current local date and time as a compact timestamp.
 */
function stamp(){
  const d = new Date();
  return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate())
       + "-" + pad(d.getHours()) + pad(d.getMinutes());
}

const safeName = s => String(s || "تقرير")
  .replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, " ").trim().slice(0, 60);

/**
 * Shares a file when supported, or downloads it through the browser.
 * @param {Blob} blob - The file data to share or download.
 * @param {string} filename - The file name used for sharing or download.
 * @return {string} An Arabic status message indicating whether the file was shared, downloaded, or sharing was canceled.
 */
async function deliver(blob, filename){
  if(navigator.canShare && navigator.share){
    try{
      const file = new File([blob], filename, {type: blob.type});
      if(navigator.canShare({files: [file]})){
        await navigator.share({files: [file], title: filename});
        return "تمت المشاركة: " + filename;
      }
    }catch(e){
      if(e && e.name === "AbortError") return "أُلغيت المشاركة";
      /* fall through to the download path */
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return "تم التنزيل: " + filename;
}

/* ------------------------------------------------------------------- CSV -- */

const csvCell = v => {
  if(v == null) return "";
  const s = String(v);
  return /[",\n\r;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};

/**
 * Converts tabular data into CSV text with a header row and CRLF line endings.
 * @param {Object} table - The table containing column definitions and rows.
 * @return {string} The CSV-formatted text.
 */
function toCSV(table){
  const head = table.columns.map(c => csvCell(c.label)).join(",");
  const body = table.rows.map(r =>
    table.columns.map(c => csvCell(c.get(r))).join(",")).join("\r\n");
  return head + "\r\n" + body + "\r\n";
}

/**
 * Downloads table data as a UTF-8 CSV file with a timestamped filename.
 * @param {Object} table - The table data and label used to generate the CSV file.
 * @return {*} The result of delivering the generated file.
 */
function downloadCSV(table){
  /* U+FEFF: without it Excel reads the file as the system codepage and every
     Arabic column becomes mojibake. */
  const blob = new Blob(["﻿" + toCSV(table)],
                        {type: "text/csv;charset=utf-8"});
  return deliver(blob, safeName(table.label) + "-" + stamp() + ".csv");
}

/* ------------------------------------------------------------- ZIP writer -- */

/* Minimal ZIP, stored (no compression). Enough for XLSX, which Excel accepts
   uncompressed, and far smaller than shipping a compression library. */
const CRC = (function(){
  const t = new Uint32Array(256);
  for(let n = 0; n < 256; n++){
    let c = n;
    for(let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();

/**
 * Calculates the CRC-32 checksum for a byte sequence.
 * @param {Uint8Array} bytes - The bytes to checksum.
 * @return {number} The unsigned CRC-32 checksum.
 */
function crc32(bytes){
  let c = 0xFFFFFFFF;
  for(let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

/**
 * Creates an XLSX-compatible archive from UTF-8 text files.
 * @param {Array<{name: string, data: string}>} files - Files to include in the archive.
 * @return {Blob} The generated archive as an XLSX-format blob.
 */
function zip(files){
  const enc = new TextEncoder();
  const parts = [], central = [];
  let offset = 0;

  const u16 = n => [n & 0xFF, (n >>> 8) & 0xFF];
  const u32 = n => [n & 0xFF, (n >>> 8) & 0xFF, (n >>> 16) & 0xFF, (n >>> 24) & 0xFF];

  for(const f of files){
    const name = enc.encode(f.name);
    const data = enc.encode(f.data);
    const sum = crc32(data);
    /* Local header. Version 20, no flags, method 0 (stored), zeroed DOS time —
       Excel does not care about the timestamp and a fixed one keeps output
       byte-stable between runs. */
    const local = new Uint8Array([].concat(
      u32(0x04034b50), u16(20), u16(0), u16(0), u16(0), u16(0),
      u32(sum), u32(data.length), u32(data.length),
      u16(name.length), u16(0)));
    parts.push(local, name, data);
    central.push(new Uint8Array([].concat(
      u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0),
      u32(sum), u32(data.length), u32(data.length),
      u16(name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset))),
      name);
    offset += local.length + name.length + data.length;
  }

  const centralSize = central.reduce((a, b) => a + b.length, 0);
  const end = new Uint8Array([].concat(
    u32(0x06054b50), u16(0), u16(0), u16(files.length), u16(files.length),
    u32(centralSize), u32(offset), u16(0)));

  return new Blob(parts.concat(central, [end]),
                  {type: "application/vnd.openxmlformats-officedocument."
                        + "spreadsheetml.sheet"});
}

/* ------------------------------------------------------------------ XLSX -- */

const xmlEsc = s => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

const colRef = i => {
  let s = "", n = i + 1;
  while(n > 0){ const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = ((n - r) / 26) | 0; }
  return s;
};

/**
 * Builds worksheet XML for an Excel-compatible spreadsheet.
 * @param {Object} table - Table definition containing column labels, row data, and value accessors.
 * @return {string} Worksheet XML with headers, data rows, numeric values, inline strings, right-to-left layout, and a frozen header row.
 */
function sheetXML(table){
  const rows = [];
  const cells = (vals, header) => vals.map((v, i) => {
    const ref = colRef(i) + (rows.length + 1);
    const num = !header && v !== "" && v != null && v !== "—"
                && typeof v === "number" && isFinite(v);
    return num
      ? `<c r="${ref}" s="0"><v>${v}</v></c>`
      : `<c r="${ref}" t="inlineStr"${header ? ' s="1"' : ''}>`
        + `<is><t xml:space="preserve">${xmlEsc(v)}</t></is></c>`;
  }).join("");

  rows.push("<row r=\"1\">" + cells(table.columns.map(c => c.label), true) + "</row>");
  for(const r of table.rows)
    rows.push(`<row r="${rows.length + 1}">`
              + cells(table.columns.map(c => c.get(r)), false) + "</row>");

  const last = colRef(Math.max(table.columns.length - 1, 0)) + (table.rows.length + 1);
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + `<sheetPr><outlinePr/></sheetPr><dimension ref="A1:${last}"/>`
    /* rightToLeft: the sheet opens with column A on the right, matching the app. */
    + '<sheetViews><sheetView rightToLeft="1" workbookViewId="0" tabSelected="1">'
    + '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
    + '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
    + "<sheetData>" + rows.join("") + "</sheetData></worksheet>";
}

/**
 * Creates an XLSX workbook from tabular data.
 * @param {Array<Object>} tables - The worksheet definitions, including labels and table data.
 * @return {Blob} The generated XLSX workbook.
 */
function workbook(tables){
  const names = tables.map((t, i) =>
    (safeName(t.label).replace(/[\[\]:*?/\\]/g, "").slice(0, 28) || ("ورقة" + (i + 1))));
  const files = [
    {name: "[Content_Types].xml", data:
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      + '<Default Extension="xml" ContentType="application/xml"/>'
      + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
      + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
      + tables.map((t, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")
      + "</Types>"},
    {name: "_rels/.rels", data:
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
      + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
      + "</Relationships>"},
    {name: "xl/workbook.xml", data:
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
      + "<sheets>"
      + names.map((n, i) => `<sheet name="${xmlEsc(n)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")
      + "</sheets></workbook>"},
    {name: "xl/_rels/workbook.xml.rels", data:
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
      + tables.map((t, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")
      + `<Relationship Id="rId${tables.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`
      + "</Relationships>"},
    {name: "xl/styles.xml", data:
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
      + '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
      + '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
      + '<fills count="2"><fill><patternFill patternType="none"/></fill>'
      + '<fill><patternFill patternType="gray125"/></fill></fills>'
      + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
      + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
      + '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
      + '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
      + "</styleSheet>"},
  ];
  tables.forEach((t, i) =>
    files.push({name: `xl/worksheets/sheet${i + 1}.xml`, data: sheetXML(t)}));
  return zip(files);
}

const downloadXLSX = (tables, label) =>
  deliver(workbook(tables), safeName(label) + "-" + stamp() + ".xlsx");

/* ---------------------------------------------------------------- charts -- */

/**
 * Lists currently mounted charts with their titles and display indexes.
 * @returns {Array<{i: number, title: string, inst: object}>} Connected chart entries, ordered from newest to oldest.
 */
function charts(){
  return REGISTRY
    .filter(c => c.inst && c.el && c.el.isConnected)
    .map((c, i) => ({
      i,
      title: (c.props && c.props.title) || ("رسم " + (i + 1)),
      inst: c.inst,
    }));
}

/**
 * Renders a chart as a rasterized PNG data URL.
 * @param {Object} entry - Chart entry containing the live ECharts instance.
 * @param {number} [scale] - Pixel ratio used for the generated image; defaults to 2.
 * @return {string} A PNG data URL.
 */
function chartPNGDataURL(entry, scale){
  const src = entry.inst.getDom();
  const w = Math.max(src.clientWidth || 0, 320);
  const h = Math.max(src.clientHeight || 0, 240);

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-10000px;top:0;width:" + w
                     + "px;height:" + h + "px;background:#111827;";
  document.body.appendChild(host);

  let tmp = null;
  try{
    tmp = echarts.init(host, null, {renderer: "canvas", width: w, height: h});
    /* animation:false is essential, not cosmetic. ecBase() sets a 320 ms entry
       animation, and getDataURL reads the canvas synchronously — with animation
       on it captures frame zero, producing an image with axes, grid and legend
       but no data. */
    const opt = entry.inst.getOption();
    opt.animation = false;
    tmp.setOption(opt, true);
    return tmp.getDataURL({type: "png", pixelRatio: scale || 2,
                           backgroundColor: "#111827"});
  } finally {
    if(tmp) tmp.dispose();
    host.remove();
  }
}

/**
 * Exports a chart as a PNG image.
 * @param {Object} entry - The chart entry containing its title and instance.
 * @return {Promise<*>} The delivery result, or an Arabic error message if PNG generation fails.
 */
function downloadChartPNG(entry){
  const url = chartPNGDataURL(entry, 2);
  if(url.indexOf("data:image/png;base64,") !== 0)
    return Promise.resolve("تعذّر إنتاج صورة PNG لهذا الرسم");
  const bin = atob(url.split(",")[1]);
  const buf = new Uint8Array(bin.length);
  for(let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return deliver(new Blob([buf], {type: "image/png"}),
                 safeName(entry.title) + "-" + stamp() + ".png");
}

/**
 * Export a chart as an SVG file.
 * @param {Object} entry - The chart entry containing the chart instance and title.
 * @return {Promise<string>} A status message describing the export result.
 */
function downloadChartSVG(entry){
  const svg = entry.inst.renderToSVGString
    ? entry.inst.renderToSVGString()
    : (entry.inst.getDom().querySelector("svg") || {}).outerHTML;
  if(!svg) return Promise.resolve("تعذّر استخراج الرسم كـ SVG");
  return deliver(new Blob([svg], {type: "image/svg+xml;charset=utf-8"}),
                 safeName(entry.title) + "-" + stamp() + ".svg");
}

/* ------------------------------------------------------------------- PDF -- */

/**
 * Opens the browser print dialog for saving the report as a PDF.
 * @return {string} Instructions to select “Save as PDF” in the print dialog.
 */
function printReport(){
  document.body.setAttribute("data-printing", "1");
  const done = () => document.body.removeAttribute("data-printing");
  window.addEventListener("afterprint", done, {once: true});
  /* Let the print stylesheet apply and ECharts resize before the dialogue. */
  setTimeout(() => {
    try{ REGISTRY.forEach(c => c.inst && c.inst.resize()); }catch(e){}
    window.print();
    setTimeout(done, 1500);
  }, 260);
  return "افتح «حفظ كـ PDF» من نافذة الطباعة";
}

return {stamp, safeName, deliver, toCSV, downloadCSV, zip, workbook,
        downloadXLSX, sheetXML, charts, chartPNGDataURL, downloadChartPNG,
        downloadChartSVG, printReport};
})();
