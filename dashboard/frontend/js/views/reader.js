// Full-page Markdown and JSON. The file card keeps a fitted preview; this page is the document,
// under the site navigation and nothing else.

import { api, ApiError } from "../api.js";
import { highlightRoot } from "../highlight.js";
import { empty, h, setTitle } from "../ui.js";
import { bindBrowseNav } from "./browse.js";
import { toc } from "./common.js";
import { fileDocument } from "./files.js";

function repoPath(value) {
  if (!value || value.startsWith("/") || value.includes("\\") || value.split("/").includes("..")) return "";
  return value;
}

function safeBack(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "";
  if (value.split(/[?#]/, 1)[0].split("/").includes("..")) return "";
  return value;
}

function fallbackBack(path) {
  const slash = path.lastIndexOf("/");
  if (slash <= 0) return "/files";
  return `/files/${path.slice(0, slash).split("/").map(encodeURIComponent).join("/")}`;
}

// Highlight.js wraps a whole docstring in one span. Splitting that HTML on newlines would
// leave the color on the first line only, so each row reopens whatever tags are still open.
function lineHtml(html) {
  const open = [];
  const tag = /<\/?([A-Za-z][\w:-]*)(\s[^<>]*)?>/g;
  return html.split("\n").map((part) => {
    const prefix = open.join("");
    tag.lastIndex = 0;
    let match;
    while ((match = tag.exec(part))) {
      const name = match[1];
      if (match[0].startsWith("</")) {
        for (let index = open.length - 1; index >= 0; index -= 1) {
          if (open[index].startsWith(`<${name}`) || open[index].startsWith(`<${name} `)) {
            open.splice(index, 1);
            break;
          }
        }
      } else if (!match[0].endsWith("/>")) {
        open.push(match[0]);
      }
    }
    const suffix = open.map((item) => `</${item.match(/^<([A-Za-z][\w:-]*)/)[1]}>`).reverse().join("");
    return prefix + part + suffix;
  });
}

// One row per source line, with the number in a gutter. Highlight.js has already wrapped tokens.
function numberLines(block) {
  const code = block.querySelector("code");
  if (!code || code.dataset.numbered) return;
  code.dataset.numbered = "1";
  let html = code.innerHTML;
  if (html.endsWith("\n")) html = html.slice(0, -1);
  const lines = lineHtml(html.length ? html : "");
  code.replaceChildren(...lines.map((line, index) => {
    const row = document.createElement("span");
    row.className = "src-line";
    const number = document.createElement("span");
    number.className = "src-ln";
    number.textContent = String(index + 1);
    const text = document.createElement("span");
    text.className = "src-text";
    text.innerHTML = line;
    row.append(number, text);
    return row;
  }));
  block.classList.add("numbered");
}

// The same rail as the wiki and API pages. Here it opens the left contents sidebar.
function contentsRail(layout) {
  const pane = layout.querySelector(".doc-toc-pane");
  const sync = () => { if (pane) pane.toggleAttribute("inert", layout.classList.contains("nav-collapsed")); };
  bindBrowseNav(layout, "lab.doc.toc", "Hide contents", "Show contents");
  sync();
  for (const button of layout.querySelectorAll("[data-nav-toggle]")) {
    button.addEventListener("click", sync);
  }
}

export async function render({ query, signal }) {
  const path = repoPath(query.get("path") || "");
  const title = path ? path.split("/").pop() : "File";
  setTitle(title);
  const back = safeBack(query.get("back") || "") || (path ? fallbackBack(path) : "/files");
  const bar = (extra) => h("div", { class: "doc-reader-bar" },
    h("a", { href: back }, "← Back"),
    h("span", { class: "doc-reader-title", title }, title),
    extra || null);
  if (!path) {
    return h("div", { class: "doc-reader" }, bar(),
      empty("This file address is not valid", "The reader opens a Markdown or JSON file in the repository."));
  }
  let data;
  try {
    data = await api("file", { path }, { signal });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return h("div", { class: "doc-reader" }, bar(), empty("Cannot open this file", error.message));
  }
  if (data.type !== "file" || data.kind === "image" || data.kind === "pdf" || data.kind === "binary") {
    return h("div", { class: "doc-reader" }, bar(),
      empty("This file has no full-page view", "Full screen is for text, Markdown and JSON."));
  }
  const { body, tools } = fileDocument(data, { sourceTools: data.kind !== "markdown" });
  highlightRoot(body);
  const sources = body.matches && body.matches("pre.viewer") ? [body] : [...body.querySelectorAll("pre.viewer")];
  for (const block of sources) numberLines(block);
  const outline = data.kind === "markdown" ? toc(body) : null;
  const sheet = h("article", {
    class: data.kind === "json" ? "doc-sheet doc-sheet-wide doc-column" : "doc-sheet doc-column",
  },
    data.truncated ? h("div", { class: "notice" }, "Only the first 2 MB are shown.") : null,
    data.warning ? h("div", { class: "notice" }, data.warning) : null,
    data.error ? empty("Cannot read this file", data.error) : body);
  const layout = h("div", { class: "doc-layout" });
  if (outline) {
    const rail = h("button", {
      class: "browse-rail", type: "button", "data-nav-toggle": "1",
      "aria-expanded": "true", "aria-label": "Hide contents",
    }, h("span", { class: "browse-rail-chevron", "aria-hidden": "true" }));
    layout.append(
      h("div", { class: "doc-toc-pane" }, outline),
      sheet,
      h("div", { class: "browse-rail-slot" }, rail));
    contentsRail(layout);
  } else {
    layout.append(sheet);
  }
  return h("div", { class: "doc-reader" },
    bar(tools.length ? h("div", { class: "file-tools" }, tools) : null),
    h("div", { class: "doc-reader-scroll" }, layout));
}
