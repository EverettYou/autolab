// Full search results across references, labs, wiki pages, threads and notes.

import { renderLabel } from "../markdown.js";
import { navigate } from "../nav.js";
import { badge, empty, h, pageHeader, setTitle } from "../ui.js";
import { siteSettings } from "../site-config.js";
import { searchField, searchNote, searchStages } from "./common.js";

export async function render({ query, signal }) {
  const q = (query.get("q") || "").trim();
  setTitle(q ? `Search: ${q}` : "Search");
  const input = h("input", { type: "search", class: "filter-input wide", value: q, placeholder: "Search titles, or describe what you need", "aria-label": "Search" });
  const form = h("form", { class: "search-page-form", role: "search" }, searchField(input), h("button", { class: "btn btn-primary", type: "submit" }, "Search"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    navigate(`/search?q=${encodeURIComponent(input.value.trim())}`);
  });
  const header = pageHeader({ kicker: "Search", title: q ? `Results for "${q}"` : "Search" });
  if (!q) return h("div", { class: "page narrow" }, header, form, empty("Type a few words. A match can be in a title, a lab summary, a paper abstract, or the opening of a wiki page."));
  const note = h("p", { class: "muted small search-mode", "aria-live": "polite" });
  const results = h("div", { class: "search-groups" });
  const paint = (data) => {
    const text = searchNote(data);
    note.hidden = !text;
    note.textContent = text;
    const groups = (data.groups || []).filter((group) => group.total);
    results.replaceChildren(...(groups.length ? groups.map((group) => h("section", { class: "search-group" },
      h("h2", null, group.label, h("span", { class: "count" }, group.total)),
      h("ul", { class: "rows" }, group.items.map((item) => h("li", { class: "row" },
        h("div", { class: "row-main" }, h("a", { class: "row-title", href: item.route }, group.key === "discussion" ? renderLabel(item.title) : item.title),
          item.subtitle && item.subtitle !== item.title ? h("div", { class: "row-sub" }, item.subtitle) : null,
          item.reason ? h("div", { class: "row-sub" }, item.reason) : null),
        h("div", { class: "row-side" }, item.badge ? badge(item.badge, group.key === "wiki" ? "type" : undefined) : null)))),
      group.total > group.items.length ? h("p", { class: "muted small" }, `${group.total - group.items.length} more; refine the query to narrow them down.`) : null))
      : [empty(`Nothing matches "${q}".`)]));
  };
  const settings = await siteSettings();
  if (signal?.aborted) return h("div", { class: "page narrow" }, header, form);
  const stages = searchStages(q, { limit: settings.search_hits.page, signal });
  const first = await stages.next();
  if (first.value) paint(first.value);
  const rest = (async () => {
    for await (const data of stages) {
      if (signal.aborted) return;
      paint(data);
    }
  })();
  rest.catch((error) => {
    if (!error || error.name === "AbortError" || signal.aborted) return;
    if (!note.textContent) note.hidden = false;
  });
  return h("div", { class: "page narrow" }, header, form, note, results);
}
