// Notes section view — same role as views/wiki.js or views/labs.js.
// Shared workbench helpers live under /static/js/; this view owns the host shell.

import { h, setTitle } from "../ui.js";

const STYLES = [
  "/static/vendor/notes-pdfjs/web/pdf_viewer.css",
  "/static/vendor/notes-markdown/markdown-renderer.css",
];

const SCRIPTS = [
  "/static/vendor/fontawesome/icons.js",
  "/static/js/table.js",
  "/static/js/splitpanes.js",
  "/static/js/search-fields.js",
  "/static/js/editor-state.js",
  "/static/js/draft-recovery.js",
  "/static/js/action-menu.js",
  "/static/js/views/notes/workspace-toolbar.js",
  "/static/js/views/notes/projects.js",
  "/static/js/views/notes/host.js",
];

let ready = null;
let host = null;
let booted = false;
let project = null;

function loadStyle(href) {
  if (document.querySelector(`link[data-workbench-href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.dataset.workbenchHref = href;
  document.head.append(link);
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[data-workbench-src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.dataset.workbenchSrc = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.append(script);
  });
}

function createHost() {
  const root = document.createElement("div");
  root.id = "workspace";
  root.className = "workspace";
  root.hidden = true;
  root.innerHTML = `
    <div id="workspace-search-bank">
      <label class="workspace-search">
        <span class="sr-only">Search notes</span>
        <input id="workspace-search" type="search" placeholder="Search notes…" autocomplete="off">
      </label>
    </div>
    <main class="workspace-main"><div id="workspace-content" class="content"></div></main>
    <output class="workspace-toast" id="workspace-toast" role="status" hidden></output>
    <dialog id="workspace-modal"></dialog>
  `;
  document.body.append(root);
  return root;
}

async function ensureHost({ onLocation } = {}) {
  if (ready) {
    await ready;
    window.NotesHost?.wire({ onLocation });
    return host;
  }
  ready = (async () => {
    host = document.getElementById("workspace") || createHost();
    for (const href of STYLES) loadStyle(href);
    for (const src of SCRIPTS) await loadScript(src);
    window.NotesHost.wire({ onLocation });
    await window.DraftRecovery.start("lab-notes");
    return host;
  })();
  return ready;
}

export function sync(path) {
  const on = /^\/notes(?:\/|$)/.test(path);
  document.body.classList.toggle("workspace-open", on);
  if (host) host.hidden = !on;
}

export async function render({ params }) {
  setTitle(params[0] || "Notes");
  const next = params[0] || "";
  await ensureHost({
    onLocation: value => {
      project = value;
      if (document.body.classList.contains("workspace-open")) {
        const path = value ? "/notes/" + encodeURIComponent(value) : "/notes";
        if (location.pathname !== path) history.replaceState(history.state, "", path);
        setTitle(value || "Notes");
      }
    },
  });
  document.body.classList.add("workspace-open");
  if (host) host.hidden = false;
  if (!booted || next !== project) window.NotesHost?.open(next);
  booted = true;
  project = next;
  return h("div", { class: "workspace-placeholder", hidden: true });
}
