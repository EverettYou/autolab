// Components shared by several views.

import { api } from "../api.js";
import { icon } from "../icons.js";
import { tableOfContents } from "../markdown.js";
import { badge, empty, fmtDate, h, pageHeader } from "../ui.js";

const HEADER_KEYS = ["page_type", "status", "updated", "created", "date"];
const HIDDEN_KEYS = new Set(["title"]);

function valueNode(value, links) {
  if (value === null || value === undefined || value === "") return h("span", { class: "muted" }, "none");
  if (Array.isArray(value)) {
    if (!value.length) return h("span", { class: "muted" }, "none");
    return h("span", { class: "chips" }, value.map((item) => valueNode(item, links)));
  }
  if (typeof value === "object") return h("code", { class: "inline-json" }, JSON.stringify(value));
  const text = String(value);
  const info = links && links.code ? links.code[text] : null;
  if (info && info.route) return h("a", { class: "chip chip-link", href: info.route }, text);
  return h("span", { class: "chip" }, text);
}

// YAML frontmatter as a compact header: type, status and dates first, the rest folded away.
export function frontmatter(pairs, links) {
  if (!pairs || !pairs.length) return null;
  const map = new Map(pairs);
  const head = [];
  if (map.get("page_type")) head.push(badge(String(map.get("page_type")), "type"));
  if (map.get("status")) head.push(badge(String(map.get("status"))));
  for (const key of ["updated", "created", "date"]) {
    if (map.get(key)) head.push(h("span", { class: "muted small" }, `${key} ${fmtDate(String(map.get(key)))}`));
  }
  const rest = pairs.filter(([key]) => !HEADER_KEYS.includes(key) && !HIDDEN_KEYS.has(key));
  const details = rest.length ? h("details", { class: "fm-details" },
    h("summary", null, `${rest.length} more ${rest.length === 1 ? "field" : "fields"}`),
    h("dl", { class: "kv fm" }, rest.map(([key, value]) => [h("dt", null, key), h("dd", null, valueNode(value, links))]))) : null;
  if (!head.length && !details) return null;
  return h("div", { class: "frontmatter" }, head.length ? h("div", { class: "fm-head" }, head) : null, details);
}

export function toc(container, title = "On this page") {
  const items = tableOfContents(container);
  if (items.length < 3) return null;
  return h("nav", { class: "toc", "aria-label": title }, h("div", { class: "toc-title" }, title),
    h("ul", null, items.map((item) => h("li", { class: `toc-${item.level}` }, h("a", { href: `#${item.id}` }, item.text)))));
}

export function tabs(items, activeKey) {
  return h("nav", { class: "tabs", role: "tablist" }, items.map((item) => h("a", {
    class: `tab${item.key === activeKey ? " active" : ""}`, href: item.href, role: "tab",
    "aria-selected": item.key === activeKey ? "true" : "false",
  }, item.label, item.count !== undefined ? h("span", { class: "tab-count" }, item.count) : null)));
}

export function filterChips(options, active, onSelect) {
  const group = h("div", { class: "filter-chips", role: "group" });
  const buttons = options.map((option) => {
    const button = h("button", { type: "button", class: `fchip${option.key === active ? " active" : ""}`,
      "aria-pressed": option.key === active ? "true" : "false" },
    option.label, option.count !== undefined ? h("span", { class: "fchip-count" }, option.count) : null);
    button.addEventListener("click", () => {
      for (const other of buttons) {
        other.classList.remove("active");
        other.setAttribute("aria-pressed", "false");
      }
      button.classList.add("active");
      button.setAttribute("aria-pressed", "true");
      onSelect(option.key);
    });
    return button;
  });
  group.append(...buttons);
  return group;
}

export function catalogPage({ title, subtitle, alerts, missing, filter, summary, extra, note, lead, list }) {
  return h("div", { class: "page" },
    pageHeader({ kicker: "Section", title, subtitle }),
    alerts,
    missing || h("div", null,
      h("div", { class: "toolbar" },
        h("div", { class: "toolbar-search" }, filter),
        h("div", { class: "toolbar-end" }, summary, extra || null)),
      note, lead || null, list));
}

export function searchField(input) {
  return h("label", { class: "search-field" }, icon("search", "search-glyph"), input);
}

export function searchInput(value, placeholder, onInput) {
  const input = h("input", { type: "search", class: "filter-input", placeholder, value: value || "", "aria-label": placeholder });
  input.addEventListener("input", () => onInput(input.value));
  return searchField(input);
}

export function searchNote(data) {
  if (!data) return "";
  if (data.mode === "tag") {
    const labels = String(data.query || "").trim().split(/\s+/).filter(Boolean);
    return labels.length > 1 ? "Filtered to items with all of these labels." : "Filtered to this label.";
  }
  const pending = data.pending || [];
  if (data.mode === "llm-refined") return "Ranked for the question you asked.";
  if (data.mode === "hybrid") {
    return pending.includes("refine")
      ? "Ranked by meaning. Reading the matches…"
      : "Ranked by meaning as well as matching words.";
  }
  if (pending.length) return "Matching words. Ranking by meaning…";
  return "";
}

// Word matches first, then meaning, then the language-model pass. Each stage is yielded as it arrives.
export async function* searchStages(q, { scope = "all", limit = 50, signal, through = "refine" } = {}) {
  const params = { q, limit, stage: "lexical" };
  if (scope && scope !== "all") params.scope = scope;
  let data = await api("search", params, { signal });
  yield data;
  if (signal?.aborted || through === "lexical" || data.mode === "tag" || !data.semantic_enabled) return;
  try {
    data = await api("search", { ...params, stage: "hybrid" }, { signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    yield { ...data, pending: [] };
    return;
  }
  yield data;
  if (through !== "refine" || !data.complex_query || data.mode !== "hybrid") return;
  try {
    data = await api("search", { ...params, stage: "refine" }, { signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    yield { ...data, pending: [] };
    return;
  }
  yield data;
}

export async function runSearch(q, options = {}) {
  let last;
  for await (const data of searchStages(q, options)) {
    last = data;
    if (options.onUpdate) options.onUpdate(data);
  }
  return last;
}

export function matches(query, ...fields) {
  const terms = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const haystack = fields.filter(Boolean).join(" ").toLowerCase();
  return terms.every((term) => haystack.includes(term));
}

export function sideSection(title, items, render, emptyText) {
  return h("section", { class: "side-section" }, h("h3", null, title, items && items.length ? h("span", { class: "count" }, items.length) : null),
    items && items.length ? h("ul", { class: "side-list" }, items.map((item) => h("li", null, render(item))))
      : h("p", { class: "muted small" }, emptyText || "None"));
}

// Slice a catalog into pages. The nav sits under the list and stays hidden when one page holds everything.
export function listPages(body, summary, { pageSize, total, emptyText, row }) {
  const nav = h("nav", { class: "result-pages", "aria-label": "Pages", hidden: true });
  let items = [];
  let page = 0;
  const size = Math.max(1, pageSize);

  function indexes(count) {
    const keep = new Set([0, count - 1, page - 1, page, page + 1]);
    return [...keep].filter((index) => index >= 0 && index < count).sort((a, b) => a - b);
  }

  function control(label, index, { current = false, disabled = false, name = "" } = {}) {
    const button = h("button", {
      type: "button", class: "result-page",
      "aria-current": current ? "page" : null,
      "aria-label": name || null,
      disabled: disabled || null,
    }, label);
    if (!current && !disabled) {
      button.addEventListener("click", () => {
        page = index;
        draw();
        body.scrollIntoView({ block: "start" });
      });
    }
    return button;
  }

  function draw() {
    const count = Math.max(1, Math.ceil(items.length / size));
    if (page > count - 1) page = count - 1;
    if (page < 0) page = 0;
    const slice = items.slice(page * size, page * size + size);
    body.replaceChildren(...(slice.length ? slice.map(row) : [empty(emptyText)]));
    summary.textContent = `${items.length} of ${total}`;
    const pages = Math.ceil(items.length / size);
    nav.replaceChildren();
    if (pages <= 1) {
      nav.hidden = true;
      return;
    }
    nav.hidden = false;
    nav.append(control("‹", page - 1, { disabled: page === 0, name: "Previous page" }));
    let previous = -1;
    for (const index of indexes(pages)) {
      if (previous >= 0 && index - previous > 1) nav.append(h("span", { class: "result-gap", "aria-hidden": "true" }, "…"));
      nav.append(control(String(index + 1), index, { current: index === page }));
      previous = index;
    }
    nav.append(control("›", page + 1, { disabled: page >= pages - 1, name: "Next page" }));
  }

  return {
    nav,
    paint(shown, reset) {
      items = shown;
      if (reset) page = 0;
      draw();
    },
  };
}
