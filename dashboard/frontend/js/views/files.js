// Read-only file viewer: folder listings and one renderer per file type.
// Markdown, JSON, code, images and PDFs each go through the same path wherever a browser is embedded.
// PDFs are not embedded here; the page redirects to the PDF reader.
// `browser()` is also embedded by the lab and reference pages with their own route mapping.

import { api } from "../api.js";
import { highlightRoot } from "../highlight.js";
import { renderJson } from "../json-view.js";
import { renderMarkdown } from "../markdown.js";
import { empty, fmtDate, fmtSize, h, filesRoute, setTitle } from "../ui.js";
import { imageReaderHref } from "./image.js";
import { pdfReaderHref } from "./pdf.js";
import { frontmatter } from "./common.js";

const TYPE_LABEL = { dir: "folder", "outside-link": "link outside the repository", "broken-link": "broken link" };

export function crumbs(path, routeFor, rootPath = "", rootLabel = "") {
  const base = rootPath ? rootPath.split("/") : [];
  const parts = path ? path.split("/") : [];
  const items = [h("a", { href: routeFor(rootPath) }, rootLabel)];
  for (let index = base.length; index < parts.length; index += 1) {
    const sub = parts.slice(0, index + 1).join("/");
    items.push(h("span", { class: "sep" }, "/"));
    items.push(index === parts.length - 1
      ? h("span", { class: "current", title: parts[index] }, parts[index])
      : h("a", { href: routeFor(sub), title: parts[index] }, parts[index]));
  }
  return h("nav", { class: "crumbs", "aria-label": "Path" }, items);
}

function currentBack() {
  return `${window.location.pathname}${window.location.search}`;
}

export function listing(payload, routeFor) {
  if (!payload.entries.length) return empty("This folder is empty.");
  const rows = payload.entries.map((entry) => {
    const usable = entry.type === "dir" || entry.type === "file";
    const name = usable
      ? h("a", { href: routeFor(entry.path), title: entry.name }, entry.name + (entry.type === "dir" ? "/" : ""))
      : h("span", { class: "muted", title: entry.name }, entry.name);
    return h("tr", { class: `entry entry-${entry.type}` },
      h("td", { class: "entry-name" }, h("span", { class: `ficon ficon-${entry.type === "file" ? entry.kind : entry.type}` }), name),
      h("td", { class: "entry-kind muted" }, entry.type === "file" ? entry.kind : TYPE_LABEL[entry.type] || entry.type),
      h("td", { class: "entry-size num" }, entry.type === "file" ? fmtSize(entry.size) : ""),
      h("td", { class: "entry-date muted" }, entry.modified ? fmtDate(entry.modified) : ""));
  });
  return h("div", { class: "listing" },
    h("div", { class: "table-wrap" }, h("table", { class: "files" },
      h("thead", null, h("tr", null, h("th", null, "Name"), h("th", null, "Kind"), h("th", { class: "num" }, "Size"), h("th", null, "Modified"))),
      h("tbody", null, rows))),
    payload.truncated ? h("p", { class: "muted small" }, `Showing ${payload.entries.length} of ${payload.total} entries.`) : null);
}

function svg(viewBox, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  el.setAttribute("viewBox", viewBox);
  el.setAttribute("aria-hidden", "true");
  for (const child of children) el.append(child);
  return el;
}

function svgPath(d, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "path");
  el.setAttribute("d", d);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

// Source is the file-code mark. Wrap is an arrow that runs to the right edge, turns down, and points back left.
function sourceIcon() {
  return svg("0 0 384 512", svgPath("M64 464c-8.8 0-16-7.2-16-16L48 64c0-8.8 7.2-16 16-16l160 0 0 80c0 17.7 14.3 32 32 32l80 0 0 288c0 8.8-7.2 16-16 16L64 464zM64 0C28.7 0 0 28.7 0 64L0 448c0 35.3 28.7 64 64 64l256 0c35.3 0 64-28.7 64-64l0-293.5c0-17-6.7-33.3-18.7-45.3L274.7 18.7C262.7 6.7 246.5 0 229.5 0L64 0zm97 289c9.4-9.4 9.4-24.6 0-33.9s-24.6-9.4-33.9 0L79 303c-9.4 9.4-9.4 24.6 0 33.9l48 48c9.4 9.4 24.6 9.4 33.9 0s9.4-24.6 0-33.9l-31-31 31-31zM257 255c-9.4-9.4-24.6-9.4-33.9 0s-9.4 24.6 0 33.9l31 31-31 31c-9.4 9.4-9.4 24.6 0 33.9s24.6 9.4 33.9 0l48-48c9.4-9.4 9.4-24.6 0-33.9l-48-48z", { fill: "currentColor" }));
}

function wrapIcon() {
  return svg("0 0 24 24",
    svgPath("M4 6h13a4 4 0 0 1 4 4v4a4 4 0 0 1-4 4H9", { fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round" }),
    svgPath("M12 14l-4 4 4 4", { fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" }));
}

function expandIcon() {
  return svg("0 0 448 512", svgPath("M32 32C14.3 32 0 46.3 0 64v96c0 17.7 14.3 32 32 32s32-14.3 32-32V96h64c17.7 0 32-14.3 32-32s-14.3-32-32-32H32zM64 352c0-17.7-14.3-32-32-32s-32 14.3-32 32v96c0 17.7 14.3 32 32 32h96c17.7 0 32-14.3 32-32s-14.3-32-32-32H64V352zM320 32c-17.7 0-32 14.3-32 32s14.3 32 32 32h64v64c0 17.7 14.3 32 32 32s32-14.3 32-32V64c0-17.7-14.3-32-32-32H320zM448 352c0-17.7-14.3-32-32-32s-32 14.3-32 32v64H320c-17.7 0-32 14.3-32 32s14.3 32 32 32h96c17.7 0 32-14.3 32-32V352z", { fill: "currentColor" }));
}

function toolButton(label, icon, onChange) {
  const button = h("button", {
    type: "button",
    class: "tool-toggle",
    title: label,
    "aria-label": label,
    "aria-pressed": "false",
    onclick() {
      const on = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", on ? "true" : "false");
      onChange(on);
    },
  }, icon);
  return button;
}

function sourceBlock(payload) {
  const pre = h("pre", { class: "code viewer", "data-lang": payload.language || null },
    h("code", { class: payload.language ? `language-${payload.language}` : null }, payload.content || ""));
  const wrap = toolButton("Wrap lines", wrapIcon(), (on) => pre.classList.toggle("wrap", on));
  return { pre, wrap };
}

export function readerHref(path, back) {
  const params = new URLSearchParams();
  params.set("path", path);
  if (back) params.set("back", back);
  return `/view?${params.toString()}`;
}

function fullScreenIcon(href) {
  if (!href) return null;
  return h("a", {
    class: "tool-toggle", href,
    title: "Full screen", "aria-label": "Full screen",
  }, expandIcon());
}

function fileFullScreen(payload) {
  if (!payload.path || payload.error || payload.kind === "binary" || payload.kind === "pdf") return null;
  const back = currentBack();
  if (payload.kind === "image") return payload.raw ? fullScreenIcon(imageReaderHref(payload.raw, back)) : null;
  return fullScreenIcon(readerHref(payload.path, back));
}

// Type-specific controls come first. Full screen is the last control for every file type.
function arrangeTools(payload, leading) {
  return [...leading.filter(Boolean), fileFullScreen(payload)].filter(Boolean);
}

function jsonBody(payload, { sourceTools = false } = {}) {
  let value = null;
  if (payload.content && !payload.warning && !payload.truncated) {
    try {
      value = JSON.parse(payload.content);
    } catch {
      value = null;
    }
  }
  const source = sourceBlock(payload);
  if (value === null) return { body: source.pre, tools: sourceTools ? [source.wrap] : [] };
  const data = renderJson(value);
  if (!sourceTools) return { body: data, tools: [] };
  source.pre.hidden = true;
  source.wrap.hidden = true;
  const toggle = toolButton("Source", sourceIcon(), (on) => {
    data.hidden = on;
    source.pre.hidden = !on;
    source.wrap.hidden = !on;
  });
  return { body: h("div", null, data, source.pre), tools: [toggle, source.wrap] };
}

// The document itself, without the file card's name row.
// `sourceTools` puts Source, and Wrap once Source is on, in the full-page reader bar.
export function fileDocument(payload, options = {}) {
  if (payload.kind === "markdown") {
    return {
      body: h("div", null, frontmatter(payload.frontmatter, payload.links),
        renderMarkdown(payload.markdown, payload.links)),
      tools: [],
    };
  }
  if (payload.kind === "json") return jsonBody(payload, options);
  if (payload.kind === "image" || payload.kind === "pdf" || payload.kind === "binary" || payload.error) {
    return { body: empty("This file has no full-page view"), tools: [] };
  }
  const source = sourceBlock(payload);
  return { body: source.pre, tools: options.sourceTools ? [source.wrap] : [] };
}

export function fileContent(payload, routeFor = filesRoute) {
  let body;
  let tools = [];
  const leading = [];
  if (payload.kind === "image") {
    body = h("div", { class: "image-view" }, h("img", { src: payload.raw, alt: payload.name }));
  } else if (payload.kind === "pdf") {
    body = empty("Open this PDF in the reader", h("a", { class: "btn btn-primary", href: pdfReaderHref(payload.raw) }, "Open PDF"));
    if (payload.raw) leading.push(h("a", { class: "btn btn-small", href: pdfReaderHref(payload.raw) }, "Open PDF"));
  } else if (payload.kind === "binary") {
    body = empty("Binary file", "Binary files are listed with their metadata only.");
  } else if (payload.error) {
    body = empty("Cannot read this file", payload.error);
  } else if (payload.kind === "markdown") {
    ({ body } = fileDocument(payload));
    body = h("div", { class: "md-preview" }, body);
  } else if (payload.kind === "json") {
    ({ body } = fileDocument(payload));
  } else {
    const source = sourceBlock(payload);
    body = source.pre;
    leading.push(source.wrap);
  }
  tools = arrangeTools(payload, leading);
  const meta = h("div", { class: "file-meta" },
    h("span", { class: "file-name", title: payload.name }, payload.name),
    h("span", { class: "file-facts" }, [payload.kind, payload.language && payload.language !== payload.kind ? payload.language : null,
      fmtSize(payload.size), payload.modified ? `modified ${fmtDate(payload.modified)}` : null].filter(Boolean).join(" \u00b7 ")),
    tools.length ? h("div", { class: "file-tools" }, tools) : null);
  const view = h("div", { class: "file-view" }, meta,
    payload.truncated ? h("div", { class: "notice" }, "Only the first 2 MB are shown.") : null,
    payload.warning ? h("div", { class: "notice" }, payload.warning) : null, body);
  highlightRoot(view);
  return view;
}

// A folder or file view for `path`, with links produced by `routeFor(path)`.
export async function browser({ path, signal, routeFor = filesRoute, rootPath = "", rootLabel = "" }) {
  const data = await api("file", { path }, { signal });
  const view = data.type === "dir" ? listing(data, routeFor) : fileContent(data, routeFor);
  const label = rootLabel || data.root_name;
  return { data, element: h("div", { class: "browser" }, crumbs(data.path || path, routeFor, rootPath, label), view) };
}

export async function render({ params, query, signal }) {
  const path = (params[0] || "").replace(/\/+$/, "");
  const { data, element } = await browser({ path, signal });
  if (data.type === "file" && data.kind === "pdf" && data.raw) {
    const slash = path.lastIndexOf("/");
    return { redirect: pdfReaderHref(data.raw, slash > 0 ? `/files/${path.slice(0, slash)}` : "/files") };
  }
  if (path && data.route && !data.route.startsWith("/files/") && query.get("view") !== "source") return { redirect: data.route };
  setTitle(path);
  return h("div", { class: "page" }, h("header", { class: "page-header" },
    h("div", { class: "kicker" }, "Repository file"), h("h1", { class: "mono-title" }, path || "Lab")), element);
}
