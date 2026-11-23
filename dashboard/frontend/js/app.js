// Router, navigation and the global search box. Each view module exports functions that take a
// route context ({params, query, signal, hash}) and return an Element (or {redirect}).

import { api } from "./api.js";
import { searchStages } from "./views/common.js";
import { icon } from "./icons.js";
import { renderLabel } from "./markdown.js";
import { navigate, safeDecode, scrollToHash, setRouteHandler } from "./nav.js";
import { applySiteChrome, siteSettings } from "./site-config.js";
import { applyTheme, mountTheme, themeChoice, watchSystemTheme } from "./theme.js";
import { debounce, errorView, h, loading, setTitle } from "./ui.js";
import * as home from "./views/home.js";
import * as references from "./views/references.js";
import * as labs from "./views/labs.js";
import * as wiki from "./views/wiki.js";
import * as threads from "./views/threads.js";
import * as notes from "./views/notes.js";
import * as apidocs from "./views/apidocs.js";
import * as files from "./views/files.js";
import * as search from "./views/search.js";
import * as status from "./views/status.js";
import * as pdf from "./views/pdf.js";
import * as image from "./views/image.js";
import * as reader from "./views/reader.js";
import * as skills from "./views/skills.js";
import * as settings from "./views/settings.js";

const ROUTES = [
  [/^\/$/, "home", home.render],
  [/^\/references\/?$/, "references", references.list],
  [/^\/references\/([^/]+)\/?$/, "references", references.detail],
  [/^\/labs\/?$/, "labs", labs.list],
  [/^\/labs\/([^/]+)\/?$/, "labs", labs.detail],
  [/^\/wiki\/?$/, "wiki", wiki.page],
  [/^\/wiki\/(.+?)\/?$/, "wiki", wiki.page],
  [/^\/threads\/?$/, "threads", threads.list],
  [/^\/threads\/([^/]+)\/?$/, "threads", threads.thread],
  [/^\/discussion\/?$/, "threads", threads.list],
  [/^\/discussion\/([^/]+)\/?$/, "threads", threads.thread],
  [/^\/notes\/?$/, "notes", notes.render],
  [/^\/notes\/([^/]+)\/?$/, "notes", notes.render],
  [/^\/apidocs\/?$/, "apidocs", apidocs.overview],
  [/^\/apidocs\/([^/]+)\/?$/, "apidocs", apidocs.module],
  [/^\/files(?:\/(.*))?$/, "", files.render],
  [/^\/pdf\/?$/, "", pdf.render],
  [/^\/image\/?$/, "", image.render],
  [/^\/view\/?$/, "", reader.render],
  [/^\/search\/?$/, "", search.render],
  [/^\/auto-research\/?$/, "", status.render],
  [/^\/auto-research\/([^/]+)\/?$/, "", status.item],
  [/^\/skills\/?$/, "", skills.list],
  [/^\/skills\/([^/]+)\/?$/, "", skills.detail],
  [/^\/settings\/?$/, "", settings.render],
];

const main = document.getElementById("app");
let controller = null;
let renderedPath = "";

function browseSection(pathname) {
  if (pathname.startsWith("/wiki")) return "wiki";
  if (pathname.startsWith("/apidocs")) return "apidocs";
  if (pathname.startsWith("/notes")) return "notes";
  return "";
}

function match(pathname) {
  for (const [pattern, section, view] of ROUTES) {
    const found = pattern.exec(pathname);
    if (found) return { section, view, params: found.slice(1).map((part) => (part === undefined ? "" : safeDecode(part))) };
  }
  return null;
}

function setActive(section) {
  for (const link of document.querySelectorAll("#nav a")) {
    if (link.dataset.section === section) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function setSystemActive(pathname) {
  const button = document.getElementById("system-menu-button");
  let active = false;
  for (const link of document.querySelectorAll("#system-menu-panel a[data-system]")) {
    const on = pathname === `/${link.dataset.system}` || pathname.startsWith(`/${link.dataset.system}/`);
    if (on) {
      link.setAttribute("aria-current", "page");
      active = true;
    } else link.removeAttribute("aria-current");
  }
  if (button) button.classList.toggle("is-active", active);
}

function mountSystemMenu() {
  const root = document.getElementById("system-menu");
  const button = document.getElementById("system-menu-button");
  const panel = document.getElementById("system-menu-panel");
  if (!root || !button || !panel) return;
  button.replaceChildren(icon("gear"));
  const close = () => {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };
  const open = () => {
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
  };
  button.addEventListener("click", event => {
    event.stopPropagation();
    if (panel.hidden) open();
    else close();
  });
  panel.addEventListener("click", () => close());
  document.addEventListener("click", event => {
    if (!root.contains(event.target)) close();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") close();
  });
}

async function route(restore) {
  // Remember this before the view loads. The loading placeholder is short, and the
  // browser clamps the scroll position to the top once it replaces a long page.
  const kept = window.scrollY;
  const previousPath = renderedPath;
  // The wiki and API side indexes scroll on their own. Rebuilding the page must not
  // send that list back to the first entry.
  const sideNav = main.querySelector(".browse-nav");
  const sideScroll = sideNav ? sideNav.scrollTop : null;
  const sideSection = browseSection(previousPath);
  if (controller) controller.abort();
  controller = new AbortController();
  const { signal } = controller;
  const settings = await siteSettings();
  if (signal.aborted) return;
  applySiteChrome(settings);
  const { pathname, search: query, hash } = window.location;
  const found = match(pathname);
  notes.sync(pathname);
  setActive(found ? found.section : "");
  setSystemActive(pathname);
  const samePage = pathname === previousPath && pathname !== "/search";
  const timer = setTimeout(() => {
    if (!signal.aborted && !samePage) main.replaceChildren(loading());
  }, 180);
  try {
    let view;
    if (found) {
      view = await found.view({ params: found.params, query: new URLSearchParams(query), signal, hash, path: pathname });
    } else {
      setTitle("Not found");
      view = errorView({ status: 404, message: `There is no page at ${pathname}.` });
    }
    if (signal.aborted) return;
    clearTimeout(timer);
    if (view && view.redirect) {
      navigate(view.redirect, { replace: true });
      return;
    }
    // A new page opens at the top. A query change on the same page — a tab, a note, a
    // file inside a reference or a lab — stays where the reader was. Search is the
    // exception: a new query is a new result list.
    main.replaceChildren(view);
    renderedPath = pathname;
    if (typeof restore === "number") window.scrollTo(0, restore);
    else if (scrollToHash(hash)) { /* the link named a section */ }
    else if (samePage) window.scrollTo(0, kept);
    else window.scrollTo(0, 0);
    if (sideScroll && sideSection && sideSection === browseSection(pathname)) {
      const nav = main.querySelector(".browse-nav");
      if (nav) nav.scrollTop = sideScroll;
    }
  } catch (error) {
    if (error && error.name === "AbortError") return;
    clearTimeout(timer);
    setTitle("Error");
    main.replaceChildren(errorView(error));
    if (error && error.status !== 404 && error.status !== 0) console.error(error);
  }
}

function passThrough(url) {
  return url.pathname.startsWith("/raw/") || url.pathname.startsWith("/api/") || url.pathname.startsWith("/static/")
    || /\.pdf$/i.test(url.pathname);
}

document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest("a[href]");
  if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
  const url = new URL(link.href, window.location.href);
  if (url.origin !== window.location.origin || passThrough(url)) return;
  event.preventDefault();
  if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) {
    window.history.pushState(window.history.state, "", url.hash);
    scrollToHash(url.hash);
    return;
  }
  navigate(url.pathname + url.search + url.hash);
});

window.addEventListener("popstate", (event) => {
  const scroll = event.state && typeof event.state.scroll === "number" ? event.state.scroll : undefined;
  route(scroll);
});

// -- global search box ---------------------------------------------------------------------------

const topbar = document.getElementById("topbar");
const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const pop = document.getElementById("search-pop");
const searchToggle = document.getElementById("search-toggle");
const navToggle = document.getElementById("nav-toggle");
const nav = document.getElementById("nav");
applyTheme(themeChoice());
form.insertBefore(icon("search", "search-glyph"), input);
if (searchToggle) searchToggle.replaceChildren(icon("search"));
if (navToggle) navToggle.replaceChildren(icon("menu"));
mountTheme(document.getElementById("theme-control"));
mountSystemMenu();
watchSystemTheme();
let searchController = null;
let active = -1;

function setSearchOpen(open) {
  if (!topbar || !searchToggle) return;
  topbar.classList.toggle("search-open", open);
  searchToggle.setAttribute("aria-expanded", open ? "true" : "false");
  searchToggle.setAttribute("aria-label", open ? "Close search" : "Open search");
  if (open) {
    setNavOpen(false);
    input.focus();
    input.select();
  } else {
    closePop();
  }
}

function setNavOpen(open) {
  if (!topbar || !navToggle) return;
  topbar.classList.toggle("nav-open", open);
  navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  navToggle.setAttribute("aria-label", open ? "Close sections menu" : "Open sections menu");
  if (open) setSearchOpen(false);
}

function closePop() {
  pop.hidden = true;
  active = -1;
}

function popItems() {
  return [...pop.querySelectorAll("a.pop-item")];
}

function highlight(index) {
  const items = popItems();
  items.forEach((item, position) => item.classList.toggle("active", position === index));
  active = index;
}

const suggest = debounce(async () => {
  const q = input.value.trim();
  if (searchController) searchController.abort();
  if (q.length < 2) {
    closePop();
    return;
  }
  searchController = new AbortController();
  const signal = searchController.signal;
  const show = (result) => {
    if (signal.aborted) return;
    const groups = result.groups.filter((group) => group.items.length);
    pop.replaceChildren(
      ...(groups.length ? groups.map((group) => h("div", { class: "pop-group" },
        h("div", { class: "pop-label" }, `${group.label}`, h("span", { class: "muted" }, ` ${group.total}`)),
        group.items.map((item) => h("a", { class: "pop-item", href: item.route },
          h("span", { class: "pop-title" }, group.key === "discussion" ? renderLabel(item.title) : item.title),
          item.badge ? h("span", { class: "pop-badge" }, item.badge) : null))))
        : [h("div", { class: "pop-empty" }, "No matches")]),
      h("a", { class: "pop-item pop-all", href: `/search?q=${encodeURIComponent(q)}` }, `All results for "${q}"`));
    pop.hidden = false;
    active = -1;
  };
  try {
    const settings = await siteSettings();
    if (signal.aborted) return;
    for await (const result of searchStages(q, { limit: settings.search_hits.navbar, signal, through: "hybrid" })) show(result);
  } catch (error) {
    if (error.name !== "AbortError") closePop();
  }
}, 160);

input.addEventListener("input", suggest);
input.addEventListener("keydown", (event) => {
  const items = popItems();
  if (event.key === "ArrowDown" && items.length) {
    event.preventDefault();
    highlight((active + 1) % items.length);
  } else if (event.key === "ArrowUp" && items.length) {
    event.preventDefault();
    highlight((active - 1 + items.length) % items.length);
  } else if (event.key === "Escape") {
    closePop();
    input.blur();
  }
});
form.addEventListener("submit", (event) => {
  event.preventDefault();
  const items = popItems();
  if (active >= 0 && items[active]) {
    navigate(items[active].getAttribute("href"));
  } else if (input.value.trim()) {
    navigate(`/search?q=${encodeURIComponent(input.value.trim())}`);
  }
  closePop();
  setSearchOpen(false);
  input.blur();
});
pop.addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    closePop();
    setSearchOpen(false);
  }
});
if (searchToggle) {
  searchToggle.addEventListener("click", () => {
    setSearchOpen(!topbar.classList.contains("search-open"));
  });
}
if (navToggle) {
  navToggle.addEventListener("click", () => {
    setNavOpen(!topbar.classList.contains("nav-open"));
  });
}
if (nav) {
  nav.addEventListener("click", (event) => {
    if (event.target.closest("a")) setNavOpen(false);
  });
}
document.addEventListener("click", (event) => {
  const onSearch = form.contains(event.target) || (searchToggle && searchToggle.contains(event.target));
  if (!onSearch) {
    closePop();
    setSearchOpen(false);
  }
  const onNav = (nav && nav.contains(event.target)) || (navToggle && navToggle.contains(event.target));
  if (!onNav) setNavOpen(false);
});
document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement && document.activeElement.tagName);
  if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
    event.preventDefault();
    if (window.matchMedia("(max-width: 980px)").matches) setSearchOpen(true);
    else {
      input.focus();
      input.select();
    }
  } else if (event.key === "Escape") {
    closePop();
    setSearchOpen(false);
    setNavOpen(false);
  }
});
window.addEventListener("resize", () => {
  if (!window.matchMedia("(max-width: 980px)").matches) setSearchOpen(false);
  if (!window.matchMedia("(max-width: 720px)").matches) setNavOpen(false);
});

let featureFlags = null;

async function loadFeatures() {
  try {
    featureFlags = await api("features");
  } catch {
    featureFlags = {};
  }
  for (const link of document.querySelectorAll("#nav a[data-optional]")) {
    const key = link.dataset.optional;
    link.hidden = !Boolean(featureFlags && featureFlags[key]);
  }
  return featureFlags;
}

function featureEnabled(key) {
  return Boolean(featureFlags && featureFlags[key]);
}

function gatedView(flag, view) {
  return async (ctx) => {
    if (!featureEnabled(flag)) {
      setTitle("Not available");
      return errorView({
        status: 404,
        message: flag === "notes"
          ? "Notes are off for this lab (enable features.notes and add a notes/ folder)."
          : "API docs are off for this lab (enable features.lib and set package in config.yml).",
      });
    }
    return view(ctx);
  };
}

// Replace open Notes / API routes with feature-gated wrappers (nav already hides links).
ROUTES.forEach((entry, i) => {
  if (entry[1] === "notes") ROUTES[i] = [entry[0], entry[1], gatedView("notes", entry[2])];
  if (entry[1] === "apidocs") ROUTES[i] = [entry[0], entry[1], gatedView("lib", entry[2])];
});

setRouteHandler(route);
loadFeatures().finally(() => route());
