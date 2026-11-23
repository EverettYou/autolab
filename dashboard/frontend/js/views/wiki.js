// Wiki: the category tree beside each page, pages with frontmatter, math and resolved links.

import { api, ApiError } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { badge, empty, fmtDate, h, setTitle } from "../ui.js";
import { browsePage, sideSearch } from "./browse.js";
import { siteSettings } from "../site-config.js";
import { frontmatter, runSearch, toc } from "./common.js";

const enc = encodeURIComponent;
let folderPageLimit = 40;
let treeCache = null;
// Folders the reader opened. The tree is rebuilt on every page, so without this only the
// current page's ancestors stay open and the list collapses back to the top.
const openFolders = new Set();

export function wikiRoute(id) {
  return `/wiki/${id.split("/").map(enc).join("/")}`;
}

async function getTree(signal) {
  if (treeCache && Date.now() - treeCache.at < 20000) return treeCache.data;
  const data = await api("wiki", {}, { signal });
  treeCache = { at: Date.now(), data };
  return data;
}

function pageLink(page, currentId) {
  return h("li", null, h("a", { href: wikiRoute(page.id), class: page.id === currentId ? "current" : null,
    "aria-current": page.id === currentId ? "page" : null, title: page.id },
  page.date && page.id.startsWith("records/") ? h("span", { class: "tree-date" }, page.date) : null, page.title));
}

function pageList(pages, currentId) {
  const list = h("ul", { class: "tree-pages" });
  const limit = pages.findIndex((page) => page.id === currentId) >= folderPageLimit ? pages.length : folderPageLimit;
  list.append(...pages.slice(0, limit).map((page) => pageLink(page, currentId)));
  if (pages.length > limit) {
    const more = h("li", null, h("button", { type: "button", class: "link-button" }, `Show ${pages.length - limit} more`));
    more.firstChild.addEventListener("click", () => {
      more.replaceWith(...pages.slice(limit).map((page) => pageLink(page, currentId)));
    });
    list.append(more);
  }
  return list;
}

function folderNode(node, currentId) {
  const inside = currentId && currentId.startsWith(`${node.path}/`);
  if (inside) openFolders.add(node.path);
  const details = h("details", { class: "tree-folder", "data-path": node.path, open: openFolders.has(node.path) || null },
    h("summary", null, h("span", { class: "tree-name" }, node.name), h("span", { class: "tree-count" }, node.count)));
  let filled = false;
  const fill = () => {
    if (filled) return;
    filled = true;
    const index = node.pages.find((page) => page.id === `${node.path}/index`);
    if (index) details.append(h("ul", { class: "tree-pages" }, pageLink({ ...index, title: "Overview" }, currentId)));
    details.append(...node.folders.map((child) => folderNode(child, currentId)));
    const pages = node.pages.filter((page) => page !== index);
    if (pages.length) details.append(pageList(pages, currentId));
  };
  if (details.open) fill();
  details.addEventListener("toggle", () => {
    if (details.open) {
      openFolders.add(node.path);
      fill();
    } else openFolders.delete(node.path);
  });
  return details;
}

function wikiFinder(signal, onQuery) {
  const input = h("input", { type: "search", class: "filter-input", placeholder: "Search the wiki",
    "aria-label": "Search the wiki" });
  const hits = h("ul", { class: "wiki-hits", hidden: true });
  let timer = 0;
  let controller = null;
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    if (controller) controller.abort();
    const q = input.value.trim();
    onQuery(Boolean(q));
    if (!q) {
      hits.hidden = true;
      hits.replaceChildren();
      return;
    }
    timer = window.setTimeout(async () => {
      controller = new AbortController();
      try {
        const show = (data) => {
          const group = (data.groups || []).find((item) => item.key === "wiki");
          const items = group ? group.items : [];
          hits.hidden = false;
          hits.replaceChildren(...(items.length ? items.map((item) => h("li", null,
            h("a", { href: item.route }, item.title, item.subtitle ? h("small", null, item.subtitle) : null)))
            : [h("li", { class: "muted small" }, "No wiki page matches.")]));
        };
        await runSearch(q, { scope: "wiki", limit: 30, signal: controller.signal, onUpdate: show });
      } catch (error) {
        if (error && error.name === "AbortError") return;
        hits.hidden = false;
        hits.replaceChildren(h("li", { class: "muted small" }, "Search is unavailable."));
      }
    }, 180);
  });
  if (signal) signal.addEventListener("abort", () => { window.clearTimeout(timer); if (controller) controller.abort(); });
  return [sideSearch(input), hits];
}

function treeNav(tree, currentId) {
  return h("div", { class: "tree nav-tree" },
    h("ul", { class: "tree-pages top" }, tree.pages.map((page) => pageLink(page, currentId))),
    tree.folders.map((node) => folderNode(node, currentId)));
}

function folderView(data) {
  const node = data.folder;
  return h("article", { class: "wiki-article" },
    h("div", { class: "kicker" }, "Wiki folder"), h("h1", null, node.path),
    node.folders.length ? h("div", { class: "folder-grid" }, node.folders.map((child) => h("a", { class: "folder-card", href: wikiRoute(child.path) },
      h("span", { class: "folder-name" }, child.name), h("span", { class: "muted small" }, `${child.count} pages`)))) : null,
    node.pages.length ? h("ul", { class: "rows" }, node.pages.map((page) => h("li", { class: "row" },
      h("div", { class: "row-main" }, h("a", { class: "row-title", href: wikiRoute(page.id) }, page.title), h("div", { class: "row-sub" }, page.id)),
      h("div", { class: "row-side" }, page.type ? badge(page.type, "type") : null, page.status ? badge(page.status) : null,
        h("span", { class: "muted small" }, fmtDate(page.date || page.updated)))))) : empty("No pages in this folder."));
}

function overview(tree) {
  return h("article", { class: "wiki-article" }, h("div", { class: "kicker" }, "Wiki"), h("h1", null, "Wiki"),
    h("p", { class: "muted" }, `${tree.count} pages. wiki/index.md is missing, so this is the folder overview.`),
    h("div", { class: "folder-grid" }, tree.folders.map((child) => h("a", { class: "folder-card", href: wikiRoute(child.path) },
      h("span", { class: "folder-name" }, child.name), h("span", { class: "muted small" }, `${child.count} pages`)))));
}

export async function page({ params, signal }) {
  const settings = await siteSettings();
  if (signal?.aborted) return h("div");
  folderPageLimit = settings.wiki_folder_page;
  const id = (params[0] || "").replace(/\/+$/, "");
  const treePromise = getTree(signal);
  let data = null;
  try {
    data = await api(`wiki/${(id || "index").split("/").map(enc).join("/")}`, {}, { signal });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404 || id) throw error;
  }
  const treeData = await treePromise;
  if (data && data.redirect) return { redirect: data.redirect };
  const tree = treeData.exists ? treeNav(treeData.tree, data && data.id) : empty("No wiki folder");
  const layout = (article, side) => browsePage({
    nav: h("nav", { class: "browse-nav", "aria-label": "Wiki pages" },
      ...wikiFinder(signal, (querying) => { tree.hidden = querying; }), tree),
    main: article,
    toc: side,
    storageKey: "lab.wiki.nav",
    hideLabel: "Hide pages",
    showLabel: "Show pages",
  });
  if (!data) {
    setTitle("Wiki");
    return layout(treeData.exists ? overview(treeData.tree) : empty("The wiki is empty", "wiki/ does not exist yet."), null);
  }
  if (data.folder) {
    setTitle(data.id, "Wiki");
    return layout(folderView(data), null);
  }
  const doc = data.doc;
  setTitle(data.title, "Wiki");
  const rendered = renderMarkdown(doc.markdown, doc.links);
  const hasTitle = rendered.firstElementChild && rendered.firstElementChild.tagName === "H1";
  const crumbs = h("nav", { class: "crumbs", "aria-label": "Wiki path" }, h("a", { href: "/wiki" }, "wiki"),
    data.breadcrumbs.map((crumb) => [h("span", { class: "sep" }, "/"),
      h("a", { href: crumb.page ? wikiRoute(crumb.page) : wikiRoute(crumb.id) }, crumb.name)]));
  const article = h("article", { class: "wiki-article" }, crumbs,
    hasTitle ? null : h("h1", null, data.title),
    frontmatter(doc.frontmatter, doc.links),
    doc.truncated ? h("div", { class: "notice" }, "Only the first 2 MB of this page are shown.") : null,
    rendered,
    h("footer", { class: "page-foot" },
      data.backlinks.length ? h("section", { class: "backlinks" }, h("h2", null, "Linked from"),
        h("ul", { class: "compact-list plain" }, data.backlinks.map((item) => h("li", null, h("a", { href: wikiRoute(item.id) }, item.title),
          h("span", { class: "muted small" }, ` ${item.id}`))))) : null,
      h("p", { class: "muted small" }, h("a", { href: `/raw/${doc.path.split("/").map(enc).join("/")}`, target: "_blank", rel: "noopener" }, doc.path),
        doc.modified ? ` \u00b7 modified ${fmtDate(doc.modified)}` : "")));
  return layout(article, toc(rendered));
}
