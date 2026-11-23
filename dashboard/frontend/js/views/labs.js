// Labs: one search box over the catalog, and one page per lab whose folder is the Files card.

import { api } from "../api.js";
import { renderInline, renderLabel, renderMarkdown } from "../markdown.js";
import { updateQuery } from "../nav.js";
import { badge, card, debounce, empty, fmtDate, h, keyValues, pageHeader, plural, setTitle, warnings } from "../ui.js";
import { siteSettings } from "../site-config.js";
import { catalogPage, listPages, runSearch, searchInput, searchNote, sideSection } from "./common.js";
import { browser } from "./files.js";
import { pdfReaderHref } from "./pdf.js";

const enc = encodeURIComponent;

export async function list({ query, signal }) {
  const [data, settings] = await Promise.all([api("labs", {}, { signal }), siteSettings()]);
  setTitle("Labs");
  const state = { q: query.get("q") || query.get("stage") || "" };
  const body = h("div", { class: "cards-list" });
  const summary = h("p", { class: "muted small" });
  const note = h("p", { class: "muted small search-mode" });
  let controller = null;
  let paintedQuery = null;

  function row(lab) {
    return h("article", { class: "item" },
      h("div", { class: "item-head" },
        h("a", { class: "item-title", href: `/labs/${enc(lab.id)}` }, lab.title),
        h("div", { class: "item-badges" }, badge(lab.stage), !lab.in_index ? badge("not in labs.json", "warn") : null)),
      h("div", { class: "item-sub" }, h("span", { class: "mono" }, lab.id),
        lab.updated && lab.updated !== lab.created ? h("span", null, `updated ${fmtDate(lab.updated)}`) : null,
        lab.references ? h("span", null, plural(lab.references, "reference")) : null,
        lab.discussion ? h("span", null, plural(lab.discussion, "thread")) : null),
      lab.summary ? h("p", { class: "item-text clamp" }, lab.summary) : null);
  }

  const pages = listPages(body, summary, {
    pageSize: settings.pages.labs,
    total: data.labs.length,
    emptyText: "No labs match this search.",
    row,
  });

  function paint(shown) {
    const q = state.q.trim();
    const reset = q !== paintedQuery;
    paintedQuery = q;
    pages.paint(shown, reset);
  }

  async function refresh() {
    const q = state.q.trim();
    updateQuery({ stage: "", sort: "", q });
    if (controller) controller.abort();
    if (!q) {
      note.textContent = "";
      paint(data.labs);
      return;
    }
    controller = new AbortController();
    if (signal) signal.addEventListener("abort", () => controller.abort(), { once: true });
    note.textContent = "Searching…";
    try {
      const byId = new Map(data.labs.map((lab) => [lab.id, lab]));
      await runSearch(q, { scope: "labs", limit: 500, signal: controller.signal, onUpdate(result) {
        const group = (result.groups || []).find((item) => item.key === "labs");
        paint((group ? group.items : []).map((item) => byId.get(item.id)).filter(Boolean));
        note.textContent = searchNote(result);
      } });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      note.textContent = "Search is unavailable.";
    }
  }

  const schedule = debounce(() => { refresh(); }, 180);
  const filter = searchInput(state.q, "Search a lab, or type a stage such as complete", (value) => { state.q = value; schedule(); });
  refresh();
  return catalogPage({
    title: "Labs",
    subtitle: "Experiments, one folder each. The report, the plan and the outputs are files in that folder.",
    alerts: warnings(data.warnings),
    missing: !data.exists && !data.labs.length ? empty("No lab index", "labs/labs.json does not exist yet.") : null,
    filter, summary, note, list: h("div", null, body, pages.nav),
  });
}

function labRoute(id, params = {}) {
  const query = new URLSearchParams(params).toString();
  return `/labs/${enc(id)}${query ? `?${query}` : ""}`;
}

export async function detail({ params, query, signal }) {
  const id = params[0];
  const data = await api(`labs/${enc(id)}`, {}, { signal });
  setTitle(data.title, "Labs");
  const prefix = `labs/${id}/`;
  // Older links used ?doc= for Markdown and ?path= for everything else. Both open in the Files card.
  const requested = query.get("file") || query.get("path") || query.get("doc") || (query.get("tab") === "notes" ? "notes" : "");

  function labQuery(file) {
    return file ? labRoute(id, { file }) : labRoute(id);
  }

  function routeFor(repoPath) {
    if (repoPath === `labs/${id}`) return labRoute(id);
    if (!repoPath.startsWith(prefix)) return `/files/${repoPath.split("/").map(enc).join("/")}`;
    return labQuery(repoPath.slice(prefix.length));
  }

  let filesCard;
  if (data.files) {
    const browsed = await browser({
      path: requested ? `${prefix}${requested}` : `labs/${id}`,
      signal, routeFor, rootPath: `labs/${id}`, rootLabel: id,
    });
    if (browsed.data.kind === "pdf" && browsed.data.raw) {
      const slash = requested.lastIndexOf("/");
      const parent = slash < 0 ? "" : requested.slice(0, slash);
      return { redirect: pdfReaderHref(browsed.data.raw, parent ? labQuery(parent) : labRoute(id)) };
    }
    filesCard = card("Files", browsed.element);
  } else {
    filesCard = card("Files", empty("This lab has no folder", `labs/${id}/ does not exist.`));
  }

  const blocked = data.stage === "blocked" ? h("div", { class: "blocked-banner" },
    h("div", { class: "callout-label" }, "Blocked"),
    h("div", null, h("div", { class: "callout-label" }, "Why"),
      data.blocked_reason ? renderMarkdown(data.blocked_reason, data.links, { anchors: false })
        : h("p", null, "No reason is recorded.")),
    data.next_action ? h("div", null, h("div", { class: "callout-label" }, "How to resolve"),
      renderMarkdown(data.next_action, data.links, { anchors: false })) : null) : null;
  const focus = data.current_focus || (data.next_action && data.stage !== "blocked") ? h("div", { class: "callout lab-focus" },
    data.current_focus ? h("div", null, h("div", { class: "callout-label" }, "Current focus"), renderMarkdown(data.current_focus, data.links, { anchors: false })) : null,
    data.stage === "blocked" ? null
      : data.next_action ? h("div", null, h("div", { class: "callout-label" }, "Next action"), renderMarkdown(data.next_action, data.links, { anchors: false })) : null) : null;

  const side = h("aside", { class: "side" },
    sideSection("References", data.reference_list, (ref) => [ref.exists ? h("a", { href: `/references/${enc(ref.id)}` }, ref.title)
      : h("span", { class: "missing", title: "Not in the reference registry" }, ref.id), " ", badge(ref.status)], "No references recorded."),
    sideSection("Threads", data.threads, (thread) => [thread.exists ? h("a", { href: `/threads/${enc(thread.id)}` }, renderLabel(thread.title || thread.id))
      : h("span", { class: "missing" }, `${thread.id} (not in state.json threads)`), " ", badge(thread.status)], "No threads."),
    data.tasks.length ? sideSection("Research tasks", data.tasks, (item) => item.detail
      ? h("a", { href: `/auto-research/${enc(item.detail)}` }, renderInline(item.title)) : renderInline(item.title)) : null,
    data.wiki.length ? sideSection("Wiki pages", data.wiki, (page) => h("a", { href: `/wiki/${page.id.split("/").map(enc).join("/")}` }, page.title)) : null,
    data.extra.length ? h("section", { class: "side-section" }, h("h3", null, "Other fields"), keyValues(data.extra)) : null);

  return h("div", { class: "page" },
    pageHeader({ kicker: h("a", { href: "/labs" }, "Labs"), kickerEnd: data.id, title: data.title,
      subtitle: data.summary ? renderInline(data.summary, data.links) : null,
      meta: [badge(data.stage),
        data.created ? h("span", { class: "muted small" }, `created ${fmtDate(data.created)}`) : null,
        data.updated ? h("span", { class: "muted small" }, `updated ${fmtDate(data.updated)}`) : null] }),
    blocked,
    focus,
    warnings(data.warnings),
    h("div", { class: "grid grid-detail" },
      h("div", { class: "stack-col" }, filesCard),
      side));
}
