// Build MANUAL.docx from MANUAL.md.
//
// A deliberately small Markdown subset: headings, paragraphs, bullet and numbered lists,
// tables, fenced code, blockquotes, inline bold/italic/code, and an explicit <<<PAGEBREAK>>>
// marker. Enough for this document and nothing more, so the converter stays readable.
//
//   node docs/build_manual.js
//
const fs = require("fs");
const path = require("path");
const d = require("docx");

const SRC = path.join(__dirname, "MANUAL.md");
const OUT = path.join(__dirname, "control-evals-manual.docx");

const PAGE_W = 11906;            // A4 portrait, DXA
const MARGIN = 1134;             // 2cm
const TABLE_W = PAGE_W - 2 * MARGIN;

const FONT = "Calibri";
const MONO = "Consolas";

const raw = fs.readFileSync(SRC, "utf8").split(/\r?\n/);

// ---------------------------------------------------------------- front matter
const meta = {};
let start = 0;
for (; start < raw.length; start++) {
  const m = raw[start].match(/^%([A-Z]+)%\s*(.*)$/);
  if (!m) break;
  meta[m[1]] = m[2];
}
const lines = raw.slice(start);

// ---------------------------------------------------------------- inline runs
// Recursive, because bold routinely wraps a code span in this document
// (`**`max_tokens` is a ceiling**`) and a code span routinely contains an asterisk
// (`all_of(*oracles)`). Code is tried first at each position so a backtick span always
// wins over an asterisk inside it; bold is non-greedy so it stops at its own closing pair.
function inline(text, opts = {}, depth = 0) {
  const runs = [];
  const re = /(`[^`]+`|\*\*[\s\S]+?\*\*|\*[^*\n]+?\*)/g;
  let last = 0, m;
  const plain = (t) => {
    if (t) runs.push(new d.TextRun({ text: t, font: FONT, size: 20, ...opts }));
  };
  while ((m = re.exec(text)) !== null) {
    plain(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) {
      runs.push(new d.TextRun({ text: tok.slice(1, -1), font: MONO, size: 18, ...opts }));
    } else if (tok.startsWith("**")) {
      const inner = tok.slice(2, -2);
      const sub = { ...opts, bold: true };
      runs.push(...(depth < 3 ? inline(inner, sub, depth + 1)
                              : [new d.TextRun({ text: inner, font: FONT, size: 20, ...sub })]));
    } else {
      const inner = tok.slice(1, -1);
      const sub = { ...opts, italics: true };
      runs.push(...(depth < 3 ? inline(inner, sub, depth + 1)
                              : [new d.TextRun({ text: inner, font: FONT, size: 20, ...sub })]));
    }
    last = m.index + tok.length;
  }
  plain(text.slice(last));
  return runs.length ? runs : [new d.TextRun({ text: "", font: FONT, size: 20 })];
}

// ---------------------------------------------------------------- table helper
function cell(text, { header = false, width } = {}) {
  return new d.TableCell({
    width: { size: width, type: d.WidthType.DXA },
    shading: header
      ? { type: d.ShadingType.CLEAR, fill: "E8EDF2" }
      : { type: d.ShadingType.CLEAR, fill: "FFFFFF" },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    children: [
      new d.Paragraph({
        spacing: { before: 20, after: 20 },
        children: inline(text, header ? { bold: true } : {}),
      }),
    ],
  });
}

function buildTable(rows) {
  const cols = Math.max(...rows.map((r) => r.length));
  const norm = rows.map((r) => {
    const c = r.slice();
    while (c.length < cols) c.push("");
    return c;
  });
  // Weight columns by their longest cell, clamped so no column collapses.
  const weights = [];
  for (let i = 0; i < cols; i++) {
    let w = 0;
    for (const r of norm) w = Math.max(w, Math.min(r[i].length, 60));
    weights.push(Math.max(w, 6));
  }
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((w) => Math.floor((w / total) * TABLE_W));
  widths[widths.length - 1] += TABLE_W - widths.reduce((a, b) => a + b, 0);

  return new d.Table({
    columnWidths: widths,
    width: { size: TABLE_W, type: d.WidthType.DXA },
    rows: norm.map(
      (r, i) =>
        new d.TableRow({
          tableHeader: i === 0,
          children: r.map((t, j) => cell(t, { header: i === 0, width: widths[j] })),
        })
    ),
  });
}

// ---------------------------------------------------------------- main parse
const body = [];
const HEADINGS = [
  d.HeadingLevel.HEADING_1,
  d.HeadingLevel.HEADING_2,
  d.HeadingLevel.HEADING_3,
  d.HeadingLevel.HEADING_4,
];

let i = 0;
while (i < lines.length) {
  const line = lines[i];

  if (line.trim() === "") { i++; continue; }

  if (line.trim() === "<<<PAGEBREAK>>>") {
    body.push(new d.Paragraph({ children: [new d.PageBreak()] }));
    i++; continue;
  }

  // fenced code
  if (line.startsWith("```")) {
    i++;
    const code = [];
    while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
    i++;
    for (const c of code) {
      body.push(new d.Paragraph({
        spacing: { before: 0, after: 0 },
        shading: { type: d.ShadingType.CLEAR, fill: "F4F5F7" },
        children: [new d.TextRun({ text: c || " ", font: MONO, size: 17 })],
      }));
    }
    body.push(new d.Paragraph({ spacing: { after: 120 }, children: [] }));
    continue;
  }

  // heading
  const h = line.match(/^(#{1,4})\s+(.*)$/);
  if (h) {
    body.push(new d.Paragraph({
      heading: HEADINGS[h[1].length - 1],
      spacing: { before: h[1].length === 1 ? 360 : 240, after: 120 },
      children: inline(h[2]),
    }));
    i++; continue;
  }

  // table
  if (line.trim().startsWith("|")) {
    const rows = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((s) => s.trim());
      if (!cells.every((c) => /^:?-{2,}:?$/.test(c) || c === "")) rows.push(cells);
      i++;
    }
    if (rows.length) {
      body.push(buildTable(rows));
      body.push(new d.Paragraph({ spacing: { after: 160 }, children: [] }));
    }
    continue;
  }

  // blockquote
  if (line.startsWith("> ")) {
    const q = [];
    while (i < lines.length && lines[i].startsWith("> ")) q.push(lines[i++].slice(2));
    body.push(new d.Paragraph({
      spacing: { before: 120, after: 160 },
      indent: { left: 400 },
      border: { left: { style: d.BorderStyle.SINGLE, size: 12, color: "7A8FA6", space: 12 } },
      children: inline(q.join(" "), { italics: true }),
    }));
    continue;
  }

  // bullet list
  if (/^[-*]\s+/.test(line)) {
    while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
      let text = lines[i].replace(/^[-*]\s+/, "");
      i++;
      while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*[-*]\s/.test(lines[i])) {
        text += " " + lines[i].trim(); i++;
      }
      body.push(new d.Paragraph({
        numbering: { reference: "bullets", level: 0 },
        spacing: { before: 40, after: 40 },
        children: inline(text),
      }));
    }
    continue;
  }

  // numbered list
  if (/^\d+\.\s+/.test(line)) {
    while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
      let text = lines[i].replace(/^\d+\.\s+/, "");
      i++;
      while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*\d+\.\s/.test(lines[i])) {
        text += " " + lines[i].trim(); i++;
      }
      body.push(new d.Paragraph({
        numbering: { reference: "numbers", level: 0 },
        spacing: { before: 40, after: 40 },
        children: inline(text),
      }));
    }
    continue;
  }

  // paragraph — join soft-wrapped lines
  const para = [];
  while (
    i < lines.length && lines[i].trim() !== "" &&
    !/^(#{1,4})\s/.test(lines[i]) && !lines[i].trim().startsWith("|") &&
    !lines[i].startsWith("```") && !lines[i].startsWith("> ") &&
    !/^[-*]\s+/.test(lines[i]) && !/^\d+\.\s+/.test(lines[i]) &&
    lines[i].trim() !== "<<<PAGEBREAK>>>"
  ) { para.push(lines[i].trim()); i++; }
  body.push(new d.Paragraph({
    spacing: { before: 60, after: 140, line: 276 },
    alignment: d.AlignmentType.JUSTIFIED,
    children: inline(para.join(" ")),
  }));
}

// ---------------------------------------------------------------- title page
const titlePage = [
  new d.Paragraph({ spacing: { before: 2600, after: 0 }, children: [] }),
  new d.Paragraph({
    spacing: { after: 100 },
    children: [new d.TextRun({ text: meta.TITLE || "Manual", font: MONO, size: 72, bold: true })],
  }),
  new d.Paragraph({
    spacing: { after: 400 },
    border: { bottom: { style: d.BorderStyle.SINGLE, size: 8, color: "7A8FA6", space: 8 } },
    children: [],
  }),
  new d.Paragraph({
    spacing: { after: 200 },
    children: [new d.TextRun({ text: meta.SUBTITLE || "", font: FONT, size: 30, bold: true })],
  }),
  new d.Paragraph({
    spacing: { after: 900 },
    children: [new d.TextRun({ text: meta.SUBSUB || "", font: FONT, size: 26, color: "444444" })],
  }),
  new d.Paragraph({
    spacing: { after: 100 },
    children: [new d.TextRun({ text: meta.VERSION || "", font: FONT, size: 20, color: "444444" })],
  }),
  new d.Paragraph({
    spacing: { after: 100 },
    children: [new d.TextRun({ text: meta.STATUS || "", font: FONT, size: 20, italics: true, color: "8A3324" })],
  }),
  new d.Paragraph({ children: [new d.PageBreak()] }),
  new d.Paragraph({
    heading: d.HeadingLevel.HEADING_1,
    spacing: { after: 200 },
    children: [new d.TextRun({ text: "Contents", font: FONT, size: 36, bold: true })],
  }),
  new d.TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  new d.Paragraph({ children: [new d.PageBreak()] }),
];

// ---------------------------------------------------------------- document
const doc = new d.Document({
  creator: "control-evals",
  title: meta.TITLE,
  description: meta.SUBTITLE,
  features: { updateFields: true },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: d.LevelFormat.BULLET, text: "•",
          alignment: d.AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: d.LevelFormat.DECIMAL, text: "%1.",
          alignment: d.AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
    ],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: 20 } },
      heading1: { run: { font: FONT, size: 34, bold: true, color: "1A2A3A" },
                  paragraph: { spacing: { before: 400, after: 160 } } },
      heading2: { run: { font: FONT, size: 26, bold: true, color: "24455F" },
                  paragraph: { spacing: { before: 300, after: 120 } } },
      heading3: { run: { font: FONT, size: 22, bold: true, color: "24455F" },
                  paragraph: { spacing: { before: 220, after: 100 } } },
      heading4: { run: { font: FONT, size: 20, bold: true, color: "444444" },
                  paragraph: { spacing: { before: 180, after: 80 } } },
    },
  },
  sections: [
    {
      properties: {
        page: { size: { width: PAGE_W, height: 16838 },
                margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } },
      },
      footers: {
        default: new d.Footer({
          children: [
            new d.Paragraph({
              alignment: d.AlignmentType.CENTER,
              border: { top: { style: d.BorderStyle.SINGLE, size: 4, color: "C4CDD6", space: 8 } },
              children: [
                new d.TextRun({ text: "control-evals — Technical Reference Manual, Rev 1     ",
                                font: FONT, size: 16, color: "666666" }),
                new d.TextRun({ children: [d.PageNumber.CURRENT], font: FONT, size: 16, color: "666666" }),
              ],
            }),
          ],
        }),
      },
      children: [...titlePage, ...body],
    },
  ],
});

d.Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`wrote ${OUT} (${(buf.length / 1024).toFixed(0)} KB)`);
});
