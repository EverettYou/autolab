// A JSON file as a vertical document. A key sits in the gray label style of the Auto Research
// facts, and its value sits beside it. The two columns split the row: the key takes 15% and the
// value takes the rest. A list of plain values stays on that line. A list of records that repeat
// the same fields is a table, scrolled once it is taller than a few rows. Other objects open
// downward from the value side. Jupyter notebooks stay a document view.

import { renderMarkdown } from "./markdown.js";
import { fmtDate, h } from "./ui.js";

const LEAF_CAP = 80;
const ROW_CAP = 200;
const TABLE_CAP = 400;
const LABEL_KEYS = ["title", "name", "id", "slug"];
const STAMP = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

function cellSource(cell) {
  const source = cell && cell.source;
  if (Array.isArray(source)) return source.join("");
  return typeof source === "string" ? source : "";
}

function renderNotebook(value) {
  return h("div", { class: "notebook" }, value.cells.map((cell) => {
    const source = cellSource(cell);
    if (cell.cell_type === "markdown") return renderMarkdown(source, {});
    const language = cell.cell_type === "code" ? "python" : "";
    return h("pre", { class: "code code-cell", "data-lang": language || null },
      h("code", { class: language ? `language-${language}` : null }, source));
  }));
}

function isNotebook(value) {
  return Boolean(value && typeof value === "object" && Array.isArray(value.cells) && typeof value.nbformat === "number");
}

function isPrimitive(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function isLeafArray(value) {
  return Array.isArray(value) && value.every(isPrimitive);
}

function isTableCell(value) {
  return isPrimitive(value) || isLeafArray(value);
}

// A list of records with the same fields, each field a plain value, is one table:
// those fields are the columns.
function isTableRecords(items) {
  if (!Array.isArray(items) || items.length < 2) return false;
  const keys = Object.keys(items[0] || {});
  if (keys.length < 2) return false;
  const signature = keys.join("\0");
  return items.every((item) => item && typeof item === "object" && !Array.isArray(item)
    && Object.keys(item).join("\0") === signature
    && keys.every((key) => isTableCell(item[key])));
}

function recordTable(items) {
  const keys = Object.keys(items[0]);
  const shown = items.slice(0, TABLE_CAP);
  const table = h("table", { class: "json-table" },
    h("thead", {}, h("tr", {}, keys.map((key) => h("th", { scope: "col" }, key)))),
    h("tbody", {}, shown.map((item) => h("tr", {}, keys.map((key, index) => {
      const value = item[key];
      const content = isLeafArray(value) ? inlineArray(value) : scalar(value);
      return index === 0 ? h("th", { scope: "row" }, content) : h("td", {}, content);
    })))));
  return h("div", { class: "json-table-wrap" }, table,
    items.length > shown.length
      ? h("p", { class: "json-meta json-table-more" }, `And ${items.length - shown.length} more.`)
      : null);
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return String(value);
  if (Number.isInteger(value)) return String(value);
  const text = String(value);
  return text.length <= 14 ? text : value.toPrecision(8).replace(/\.?0+$/, "");
}

// Same delimiters as the Markdown renderer: $$...$$, \[...\], \(...\), $...$.
const MATH_PATTERNS = [
  { re: /^\$\$(?!\$)([^$]+?)\$\$/, display: true },
  { re: /^\\\[([\s\S]+?)\\\]/, display: true },
  { re: /^\\\(([\s\S]+?)\\\)/, display: false },
  { re: /^\$(?=[^\s$])((?:\\.|[^\\$`\n]|\n(?![ \t]*\n))+?)(?<=[^\s\\])\$(?!\d)/, display: false },
];
const URL_BODY = /^https?:\/\/[^\s<>"']+/i;

function mathNode(tex, display) {
  const el = h("span", { class: display ? "math math-display" : "math math-inline" });
  const katex = window.katex;
  if (!katex) {
    el.textContent = tex;
    return el;
  }
  try {
    katex.render(tex.trim(), el, {
      displayMode: display, throwOnError: false, strict: "ignore", trust: false, output: "htmlAndMathml",
    });
  } catch {
    el.classList.add("math-error");
    el.textContent = tex;
  }
  return el;
}

function splitUrl(raw) {
  let end = raw.length;
  while (end > 0 && /[.,;:!?)]/.test(raw[end - 1])) {
    if (raw[end - 1] === ")") {
      const head = raw.slice(0, end);
      const open = (head.match(/\(/g) || []).length;
      const close = (head.match(/\)/g) || []).length;
      if (close <= open) break;
    }
    end -= 1;
  }
  return [raw.slice(0, end), raw.slice(end)];
}

function linkNode(url) {
  return h("a", { class: "external", href: url, target: "_blank", rel: "noopener noreferrer" }, url);
}

function renderRich(text) {
  const parts = [];
  let index = 0;
  while (index < text.length) {
    const rest = text.slice(index);
    const mathAt = rest.search(/\$|\\\(|\\\[/);
    const urlAt = rest.search(/https?:\/\//i);
    const mathFirst = mathAt >= 0 && (urlAt < 0 || mathAt <= urlAt);
    const next = mathFirst ? mathAt : urlAt;
    if (next < 0) {
      parts.push(rest);
      break;
    }
    if (next > 0) parts.push(rest.slice(0, next));
    const slice = rest.slice(next);
    if (mathFirst) {
      const matched = MATH_PATTERNS.map((pattern) => {
        const match = pattern.re.exec(slice);
        return match ? { raw: match[0], tex: match[1], display: pattern.display } : null;
      }).find(Boolean);
      if (!matched) {
        parts.push(slice[0]);
        index += next + 1;
        continue;
      }
      parts.push(mathNode(matched.tex, matched.display));
      index += next + matched.raw.length;
      continue;
    }
    const urlMatch = URL_BODY.exec(slice);
    if (!urlMatch) {
      parts.push(slice[0]);
      index += next + 1;
      continue;
    }
    const [url, trail] = splitUrl(urlMatch[0]);
    if (url.length < "https://x".length) {
      parts.push(urlMatch[0][0]);
      index += next + 1;
      continue;
    }
    parts.push(linkNode(url));
    if (trail) parts.push(trail);
    index += next + urlMatch[0].length;
  }
  return parts;
}

function renderString(text) {
  if (!text) return h("span", { class: "json-none" }, "none");
  if (STAMP.test(text)) return h("span", { class: "json-time" }, fmtDate(text) || text);
  if (!/[$\\]|https?:\/\//i.test(text)) return text;
  return renderRich(text);
}

function scalar(value) {
  if (value === null || value === undefined) return h("span", { class: "json-none" }, "none");
  if (typeof value === "boolean") return h("span", { class: "json-bool" }, value ? "true" : "false");
  if (typeof value === "number") return h("span", { class: "json-num" }, formatNumber(value));
  if (typeof value === "string") return renderString(value);
  return String(value);
}

function clip(text) {
  const value = String(text);
  return value.length > 42 ? `${value.slice(0, 42)}…` : value;
}

function inlineArray(items) {
  if (!items.length) return h("span", { class: "json-none" }, "none");
  const numbers = items.every((item) => item === null || typeof item === "number");
  const shown = items.slice(0, LEAF_CAP);
  const parts = [];
  shown.forEach((item, index) => {
    if (index) parts.push(h("span", { class: "json-sep" }, ", "));
    parts.push(scalar(item));
  });
  if (items.length > shown.length) {
    parts.push(h("span", { class: "json-meta" }, `, and ${items.length - shown.length} more`));
  }
  return h("span", { class: numbers ? "json-array json-array-num" : "json-array" }, parts);
}

function itemLabel(item, index) {
  if (item && typeof item === "object" && !Array.isArray(item)) {
    for (const key of LABEL_KEYS) {
      const value = item[key];
      if (typeof value === "string" && value && value.length <= 80) return value;
    }
  }
  return String(index + 1);
}

function namedRecords(items) {
  return items.some((item, index) => itemLabel(item, index) !== String(index + 1));
}

function recordPreview(items) {
  if (items.length === 1) return itemLabel(items[0], 0);
  if (!namedRecords(items)) return items.length === 1 ? "1 record" : `${items.length} records`;
  const shown = items.slice(0, 2).map((item, index) => clip(itemLabel(item, index)));
  const text = shown.join(", ");
  return items.length > shown.length ? `${text}, and ${items.length - shown.length} more` : text;
}

function fieldPreview(value) {
  const count = Object.keys(value).length;
  return count === 1 ? "1 field" : `${count} fields`;
}

function line(key, value) {
  const body = isLeafArray(value) ? inlineArray(value) : scalar(value);
  return h("div", { class: "json-line" },
    h("span", { class: "json-key" }, key),
    h("span", { class: "json-val" }, body));
}

function entry(key, previewText, meta, body) {
  return h("details", { class: "json-entry" },
    h("summary", { class: "json-line" },
      h("span", { class: "json-key" }, key),
      h("span", { class: "json-val" },
        h("span", { class: meta ? "json-preview json-meta" : "json-preview" }, previewText),
        h("span", { class: "json-chevron", "aria-hidden": "true" }))),
    body);
}

function renderObject(obj) {
  return h("div", { class: "json-children" }, Object.entries(obj).map(([key, value]) => renderNode(key, value)));
}

function withoutLabel(item, label) {
  const skip = LABEL_KEYS.find((key) => item[key] === label);
  if (!skip) return item;
  return Object.fromEntries(Object.entries(item).filter(([key]) => key !== skip));
}

function renderRecords(items) {
  if (items.length === 1) return renderObject(items[0]);
  const shown = items.slice(0, ROW_CAP);
  const nodes = shown.map((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return line(String(index + 1), item);
    const label = itemLabel(item, index);
    const rest = withoutLabel(item, label);
    if (!Object.keys(rest).length) return line(label, null);
    return entry(label, fieldPreview(rest), true, renderObject(rest));
  });
  return h("div", { class: "json-children" }, nodes,
    items.length > shown.length ? h("p", { class: "json-meta" }, `And ${items.length - shown.length} more.`) : null);
}

function renderNode(key, value) {
  if (value === null || isPrimitive(value) || isLeafArray(value)) return line(key, value);
  if (Array.isArray(value)) {
    if (!value.length) return line(key, []);
    if (isTableRecords(value)) {
      return h("div", { class: "json-line json-line-table" },
        h("span", { class: "json-key" }, key),
        h("div", { class: "json-val" }, recordTable(value)));
    }
    return entry(key, recordPreview(value), !namedRecords(value) && value.length !== 1, renderRecords(value));
  }
  if (!Object.keys(value).length) return line(key, null);
  return entry(key, fieldPreview(value), true, renderObject(value));
}

function renderValue(value) {
  if (Array.isArray(value)) {
    if (isLeafArray(value)) return h("div", { class: "json-doc" }, h("div", { class: "json-line json-line-solo" }, h("span", { class: "json-val" }, inlineArray(value))));
    if (isTableRecords(value)) return recordTable(value);
    const group = renderRecords(value);
    group.classList.replace("json-children", "json-doc");
    return group;
  }
  if (value && typeof value === "object") {
    return h("div", { class: "json-doc" }, Object.entries(value).map(([key, item]) => renderNode(key, item)));
  }
  return h("div", { class: "json-doc" }, h("div", { class: "json-line json-line-solo" }, h("span", { class: "json-val" }, scalar(value))));
}

export function renderJson(value) {
  if (isNotebook(value)) return h("div", { class: "json-view" }, renderNotebook(value));
  return h("div", { class: "json-view" }, renderValue(value));
}
