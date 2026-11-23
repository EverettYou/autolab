// References: the registry with status filters, and one page per reference.

import { api } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { updateQuery } from "../nav.js";
import { badge, card, chips, debounce, empty, fmtDate, fmtSize, h, keyValues, pageHeader, plural, setTitle, warnings } from "../ui.js";
import { siteSettings } from "../site-config.js";
import { catalogPage, listPages, runSearch, searchInput, searchNote, sideSection } from "./common.js";
import { browser } from "./files.js";
import { pdfReaderHref } from "./pdf.js";

const enc = encodeURIComponent;
const KIND_LABELS = { paper: "Paper", repository: "Repository", dataset: "Dataset" };
const KIND_TONES = { paper: "info", repository: "type", dataset: "good" };

const FACT_LABELS = {
  fetched_at: "Fetched at",
  fetch_status: "Fetch status",
  metadata_source: "Metadata source",
  title_match_score: "Title match score",
};

function factValue(key, value) {
  if (key === "fetched_at") return fmtDate(value) || value;
  return value;
}

function kindBadges(ref) {
  const value = ref.kind;
  const kinds = Array.isArray(value) ? value : (value ? [value] : []);
  return kinds.map((kind) => badge(KIND_LABELS[kind] || kind, KIND_TONES[kind] || "type"));
}

function refRoute(id) {
  return `/references/${enc(id)}`;
}

function sourceButton(ref, small) {
  const cls = `btn external${small ? " btn-small" : ""}`;
  const attrs = { class: cls, target: "_blank", rel: "noopener noreferrer" };
  if (ref.arxiv_id) return h("a", { ...attrs, href: `https://arxiv.org/abs/${ref.arxiv_id}` }, `arXiv:${ref.arxiv_id}`);
  if (ref.entry_url) return h("a", { ...attrs, href: ref.entry_url }, "Source");
  return null;
}

function pdfButton(bytePath, back, small) {
  return h("a", { class: `btn btn-primary${small ? " btn-small" : ""}`, href: pdfReaderHref(bytePath, back) }, "Open PDF");
}

export async function list({ query, signal }) {
  const [data, settings] = await Promise.all([api("references", {}, { signal }), siteSettings()]);
  setTitle("References");
  const state = { q: query.get("q") || query.get("status") || query.get("kind") || "" };
  const body = h("div", { class: "cards-list" });
  const summary = h("p", { class: "muted small" });
  const note = h("p", { class: "muted small search-mode" });
  let controller = null;
  let paintedQuery = null;

  function row(ref) {
    const authors = ref.authors.length
      ? ref.authors.join(", ") + (ref.authors_total > ref.authors.length ? " et al." : "")
      : null;
    const actions = [
      sourceButton(ref, true),
      ref.published_url ? h("a", { class: "btn btn-small external", href: ref.published_url, target: "_blank", rel: "noopener noreferrer" }, "Published") : null,
      ref.has_pdf ? pdfButton(`/references/${enc(ref.id)}/paper.pdf`, refRoute(ref.id), true) : null,
    ].filter(Boolean);
    const facts = [
      ref.reproduction ? h("span", null, "reproduction") : null,
      ref.repos ? h("span", null, plural(ref.repos, "repository", "repositories")) : null,
      ref.attempts ? h("span", null, plural(ref.attempts, "attempt")) : null,
      ref.cited_by ? h("span", null, `cited by ${plural(ref.cited_by, "lab")}`) : null,
      !ref.in_registry ? badge("not in references.json", "warn") : null,
    ].filter(Boolean);
    return h("article", { class: "item ref-item" },
      h("div", { class: "item-head" },
        h("a", { class: "item-title", href: refRoute(ref.id) }, ref.title),
        h("div", { class: "item-badges" }, badge(ref.status), kindBadges(ref))),
      h("div", { class: "item-sub" },
        authors ? h("span", null, authors) : h("span", { class: "muted" }, "No authors recorded"),
        ref.published ? h("span", null, ref.published.slice(0, 4)) : null,
        h("span", { class: "mono" }, ref.id)),
      h("p", { class: "item-text clamp" }, ref.blurb || h("span", { class: "muted" }, "No abstract recorded.")),
      actions.length ? h("div", { class: "ref-actions" }, actions) : null,
      facts.length ? h("div", { class: "item-facts" }, facts) : null);
  }

  const pages = listPages(body, summary, {
    pageSize: settings.pages.references,
    total: data.references.length,
    emptyText: "No references match this search.",
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
    updateQuery({ status: "", kind: "", q });
    if (controller) controller.abort();
    if (!q) {
      note.textContent = "";
      paint(data.references);
      return;
    }
    controller = new AbortController();
    if (signal) signal.addEventListener("abort", () => controller.abort(), { once: true });
    note.textContent = "Searching…";
    try {
      const byId = new Map(data.references.map((ref) => [ref.id, ref]));
      await runSearch(q, { scope: "references", limit: 500, signal: controller.signal, onUpdate(result) {
        const group = (result.groups || []).find((item) => item.key === "references");
        paint((group ? group.items : []).map((item) => byId.get(item.id)).filter(Boolean));
        note.textContent = searchNote(result);
      } });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      note.textContent = "Search is unavailable.";
    }
  }

  const schedule = debounce(() => { refresh(); }, 180);
  const filter = searchInput(state.q, "Search a paper, or type a status or kind such as reproduced", (value) => { state.q = value; schedule(); });
  refresh();
  return catalogPage({
    title: "References",
    subtitle: "Papers, code repositories and datasets we fetched, with their reproductions and attempts.",
    alerts: warnings(data.warnings),
    missing: !data.exists && !data.references.length ? empty("No reference registry", "references/references.json does not exist yet.") : null,
    filter, summary, note, list: h("div", null, body, pages.nav),
  });
}

function parentPath(inner) {
  const slash = inner.lastIndexOf("/");
  return slash < 0 ? "" : inner.slice(0, slash);
}

export async function detail({ params, query, signal }) {
  const id = params[0];
  const data = await api(`references/${enc(id)}`, {}, { signal });
  if (data.redirect) return { redirect: data.redirect };
  setTitle(data.title, "References");
  const file = query.get("file") || "";
  const prefix = `references/${id}/`;

  function refQuery(params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) search.set(key, value);
    }
    const text = search.toString();
    return `${refRoute(id)}${text ? `?${text}` : ""}`;
  }

  function routeFor(repoPath) {
    if (repoPath === `references/${id}`) return refRoute(id);
    if (repoPath.startsWith(prefix)) return refQuery({ file: repoPath.slice(prefix.length) });
    return `/files/${repoPath.split("/").map(enc).join("/")}`;
  }

  let filesBrowser = null;
  if (data.files) {
    filesBrowser = await browser({
      path: file ? `${prefix}${file}` : `references/${id}`, signal, routeFor,
      rootPath: `references/${id}`, rootLabel: id,
    });
    if (filesBrowser.data.kind === "pdf" && filesBrowser.data.raw) {
      const parent = parentPath(file);
      return { redirect: pdfReaderHref(filesBrowser.data.raw, parent ? refQuery({ file: parent }) : refRoute(id)) };
    }
  }
  const links = [
    sourceButton(data, false),
    data.published_url ? h("a", { class: "btn external", href: data.published_url, target: "_blank", rel: "noopener noreferrer" }, "Published") : null,
    data.pdf ? pdfButton(data.pdf.route, refRoute(id), false) : null,
  ];

  const abstract = card("Abstract", h("div", null,
    data.abstract ? renderMarkdown(data.abstract, data.links, { anchors: false, className: "markdown abstract" })
      : h("p", { class: "muted" }, "No abstract recorded."),
    data.categories.length ? chips(data.categories) : null));

  const facts = card("Details", h("div", null,
    keyValues([["Status", badge(data.status)], ["Kind", h("span", { class: "item-badges" }, kindBadges(data))], ["Published", fmtDate(data.published) || "—"],
      ["Updated upstream", fmtDate(data.upstream_updated) || "—"], ["PDF", data.pdf ? `${fmtSize(data.pdf.size)}${data.pdf.pages ? `, ${data.pdf.pages} pages` : ""}` : "—"],
      ...data.provenance.filter(([key]) => !/sha|checksum|digest/i.test(key))
        .map(([key, value]) => [FACT_LABELS[key] || key.replace(/_/g, " "), factValue(key, value)])], "kv facts"),
    data.aliases.length ? h("div", { class: "field" }, h("div", { class: "field-label" }, "Aliases"), chips(data.aliases)) : null,
    data.legacy_paths.length ? h("details", null, h("summary", null, "Former locations"), h("ul", { class: "mono-list" }, data.legacy_paths.map((path) => h("li", null, path)))) : null));

  const side = h("aside", { class: "side" },
    (data.related || []).length ? sideSection("Related", data.related, (item) => [h("a", { href: refRoute(item.id) }, item.title), " ", kindBadges(item)]) : null,
    sideSection("Cited by labs", data.cited_by, (lab) => [h("a", { href: `/labs/${enc(lab.id)}` }, lab.title), " ", badge(lab.stage)], "No lab cites this reference."),
    sideSection("Wiki pages", data.wiki, (page) => h("a", { href: `/wiki/${page.id.split("/").map(enc).join("/")}` }, page.title), "No wiki page cites it."));

  const files = filesBrowser ? card("Files", filesBrowser.element) : null;

  const header = pageHeader({
    kicker: h("a", { href: "/references" }, "References"),
    kickerEnd: data.id,
    title: data.title,
    subtitle: data.authors.length ? data.authors.join(", ") : h("span", { class: "muted" }, "No authors recorded"),
    meta: [badge(data.status), ...kindBadges(data)],
  });
  const actions = links.filter(Boolean);
  if (actions.length) header.append(h("div", { class: "ref-actions" }, actions));
  return h("div", { class: "page" },
    header,
    warnings(data.warnings),
    h("div", { class: "grid grid-detail" },
      h("div", { class: "stack-col" }, abstract, files),
      h("div", { class: "stack-col" }, facts, side)));
}
