// Notes section view — same role as views/wiki.js or views/labs.js.
// Step 1 ESM: static imports replace loadScript; window.NotesHost bridge kept.

import { h, setTitle } from "../ui.js";

import "../../vendor/fontawesome/icons.js";
import "../table.js";
import "../splitpanes.js";
import "../search-fields.js";
import "../editor-state.js";
import "../draft-recovery.js";
import "../action-menu.js";
import "./notes/workspace-toolbar.js";
import "./notes/host.js";
import "./notes/projects.js";

let ready = null;
let host = null;
let booted = false;
let project = null;

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
    <dialog id="workspace-modal" class="workbench-dialog"></dialog>
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
    // Side-effect imports above already registered NotesHost / DraftRecovery.
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
