// Shared professional-document helpers for the RCA Engine deliverables.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, LevelFormat, TableOfContents, HeadingLevel,
  BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak,
  ExternalHyperlink,
} = require("docx");

const NAVY = "1F3864", BLUE = "2E75B6", LIGHT = "D9E2F3", GREY = "595959",
      CODEBG = "F2F2F2", RULE = "BFBFBF";
const CONTENT_W = 9360; // US Letter, 1" margins (DXA)
const AUTHOR = "Darshak Kakani";
const DATE = "18 June 2026";
const VERSION = "1.0";

// ── inline run helpers ──────────────────────────────────────────────────────
const T = (t, o = {}) => new TextRun({ text: t, ...o });
const B = (t, o = {}) => new TextRun({ text: t, bold: true, ...o });
const code = (t) => new TextRun({ text: t, font: "Consolas", size: 19 });

// ── block helpers ────────────────────────────────────────────────────────────
function H1(t) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [T(t)] });
}
function H2(t) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [T(t)] });
}
function H3(t) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [T(t)] });
}
function P(children, o = {}) {
  if (typeof children === "string") children = [T(children)];
  return new Paragraph({ children, spacing: { after: 140, line: 276 }, ...o });
}
function bullet(children, level = 0) {
  if (typeof children === "string") children = [T(children)];
  return new Paragraph({ numbering: { reference: "bul", level }, children,
    spacing: { after: 60, line: 264 } });
}
function num(children, level = 0) {
  if (typeof children === "string") children = [T(children)];
  return new Paragraph({ numbering: { reference: "num", level }, children,
    spacing: { after: 60, line: 264 } });
}
function codeBlock(lines) {
  return lines.map((ln, i) => new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: CODEBG },
    spacing: { after: i === lines.length - 1 ? 160 : 0, line: 252 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 18, color: BLUE, space: 8 },
    },
    children: [new TextRun({ text: ln || " ", font: "Consolas", size: 18 })],
  }));
}

// ── tables ───────────────────────────────────────────────────────────────────
function table(headers, rows, widths) {
  const tb = { style: BorderStyle.SINGLE, size: 1, color: RULE };
  const borders = { top: tb, bottom: tb, left: tb, right: tb,
                    insideHorizontal: tb, insideVertical: tb };
  const mk = (text, { head = false, w } = {}) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: head ? NAVY : "FFFFFF" },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: (Array.isArray(text) ? text : [text]).map((seg) =>
      new Paragraph({ spacing: { after: 0, line: 252 },
        children: typeof seg === "string"
          ? [new TextRun({ text: seg, bold: head, color: head ? "FFFFFF" : "000000", size: 20 })]
          : [seg] })),
  });
  const headerRow = new TableRow({ tableHeader: true,
    children: headers.map((h, i) => mk(h, { head: true, w: widths[i] })) });
  const bodyRows = rows.map((r) => new TableRow({
    children: r.map((c, i) => mk(c, { w: widths[i] })) }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths, borders, rows: [headerRow, ...bodyRows] });
}

// ── images (auto-scale to fit content area) ───────────────────────────────────
function pngDims(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b };
}
function figure(file, caption, { maxWin = 6.6, maxHin = 7.6 } = {}) {
  const { w, h, data } = pngDims(file);
  const maxW = maxWin * 96, maxH = maxHin * 96;
  const scale = Math.min(maxW / w, maxH / h, 1);
  const out = [new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 80, after: 40 },
    children: [new ImageRun({ type: "png", data,
      transformation: { width: Math.round(w * scale), height: Math.round(h * scale) },
      altText: { title: caption, description: caption, name: caption } })],
  })];
  if (caption) out.push(new Paragraph({ alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new TextRun({ text: caption, italics: true, size: 18, color: GREY })] }));
  return out;
}

function divider() {
  return new Paragraph({ spacing: { after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 1 } },
    children: [T("")] });
}
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ── title page + document control ─────────────────────────────────────────────
function titlePage(title, subtitle, docId, abstract) {
  const tb = { style: BorderStyle.SINGLE, size: 1, color: RULE };
  const kv = (k, v) => new TableRow({ children: [
    new TableCell({ width: { size: 2700, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: LIGHT },
      margins: { top: 70, bottom: 70, left: 120, right: 120 },
      children: [new Paragraph({ children: [B(k, { size: 20 })] })] }),
    new TableCell({ width: { size: 6660, type: WidthType.DXA },
      margins: { top: 70, bottom: 70, left: 120, right: 120 },
      children: [new Paragraph({ children: [T(v, { size: 20 })] })] }),
  ]});
  const controlTable = new Table({ width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [2700, 6660],
    borders: { top: tb, bottom: tb, left: tb, right: tb,
               insideHorizontal: tb, insideVertical: tb },
    rows: [
      kv("System", "Enterprise Log Intelligence Platform — Root Cause Analysis Engine"),
      kv("Document", title),
      kv("Reference", docId),
      kv("Version", VERSION),
      kv("Status", "Issued for review"),
      kv("Date", DATE),
      kv("Owner / Author", AUTHOR),
      kv("Intended audience", "Platform Engineering · Site Reliability · Applied AI"),
      kv("Classification", "Confidential"),
    ] });
  // Revision history — a small touch that signals a maintained, owned document.
  const revHead = (t) => new TableCell({ width: { size: t.w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: NAVY },
    margins: { top: 50, bottom: 50, left: 110, right: 110 },
    children: [new Paragraph({ children: [B(t.t, { size: 18, color: "FFFFFF" })] })] });
  const revCell = (txt, w) => new TableCell({ width: { size: w, type: WidthType.DXA },
    margins: { top: 50, bottom: 50, left: 110, right: 110 },
    children: [new Paragraph({ children: [T(txt, { size: 18 })] })] });
  const revTable = new Table({ width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [1100, 1700, 2400, 4160],
    borders: { top: tb, bottom: tb, left: tb, right: tb,
               insideHorizontal: tb, insideVertical: tb },
    rows: [
      new TableRow({ tableHeader: true, children: [
        revHead({ t: "Version", w: 1100 }), revHead({ t: "Date", w: 1700 }),
        revHead({ t: "Author", w: 2400 }), revHead({ t: "Summary", w: 4160 }) ] }),
      new TableRow({ children: [
        revCell(VERSION, 1100), revCell(DATE, 1700), revCell(AUTHOR, 2400),
        revCell("Initial design, prototype and validation against both incident scenarios.", 4160) ] }),
    ] });
  const out = [
    new Paragraph({ spacing: { before: 1200, after: 0 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: NAVY, space: 12 } },
      children: [new TextRun({ text: "Enterprise Log Intelligence Platform",
        size: 22, color: BLUE, bold: true })] }),
    new Paragraph({ spacing: { before: 380, after: 60 },
      children: [new TextRun({ text: title, bold: true, size: 50, color: NAVY })] }),
    new Paragraph({ spacing: { after: 300 },
      children: [new TextRun({ text: subtitle, size: 28, color: GREY })] }),
  ];
  if (abstract) out.push(new Paragraph({ spacing: { before: 120, after: 280 },
    children: [new TextRun({ text: abstract, italics: true, size: 21, color: "404040" })] }));
  out.push(controlTable);
  out.push(new Paragraph({ spacing: { before: 280, after: 100 },
    children: [B("Revision history", { size: 20, color: NAVY })] }));
  out.push(revTable);
  out.push(new Paragraph({ spacing: { before: 360 },
    children: [new TextRun({ text: "Confidential. For internal review only.",
      size: 18, color: GREY, italics: true })] }));
  out.push(pageBreak());
  return out;
}

// ── document assembly ─────────────────────────────────────────────────────────
function buildDoc({ title, footerId, children }) {
  return new Document({
    creator: AUTHOR, title, description: title,
    styles: {
      default: { document: { run: { font: "Calibri", size: 22 } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
          quickFormat: true, run: { size: 30, bold: true, color: NAVY, font: "Calibri" },
          paragraph: { spacing: { before: 300, after: 140 }, outlineLevel: 0,
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: LIGHT, space: 4 } } } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
          quickFormat: true, run: { size: 25, bold: true, color: BLUE, font: "Calibri" },
          paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal",
          quickFormat: true, run: { size: 22, bold: true, color: "404040", font: "Calibri" },
          paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
      ],
    },
    numbering: { config: [
      { reference: "bul", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 280 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 280 } } } } ] },
      { reference: "num", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 280 } } } } ] },
    ] },
    sections: [{
      properties: { page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      headers: { default: new Header({ children: [ new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 4 } },
        tabStops: [{ type: "right", position: CONTENT_W }],
        children: [ new TextRun({ text: title, size: 16, color: GREY }),
          new TextRun({ text: "\tLog Intelligence Platform · RCA Engine", size: 16, color: GREY }) ] }) ] }) },
      footers: { default: new Footer({ children: [ new Paragraph({
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 4 } },
        tabStops: [{ type: "right", position: CONTENT_W }],
        children: [
          new TextRun({ text: `${footerId} · v${VERSION} · Confidential`, size: 16, color: GREY }),
          new TextRun({ children: ["\tPage ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES],
            size: 16, color: GREY }) ] }) ] }) },
      children,
    }],
  });
}

function toc(title = "Table of Contents") {
  return [ new Paragraph({ spacing: { after: 120 },
      children: [new TextRun({ text: title, bold: true, size: 28, color: NAVY })] }),
    new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
    pageBreak() ];
}

async function write(doc, outPath) {
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buf);
  console.log("wrote", path.basename(outPath), (buf.length / 1024).toFixed(0) + "KB");
}

module.exports = {
  T, B, code, H1, H2, H3, P, bullet, num, codeBlock, table, figure, divider,
  pageBreak, titlePage, buildDoc, toc, write, ExternalHyperlink, TextRun,
  DIAG: path.resolve(__dirname, "..", "diagrams"),
};
