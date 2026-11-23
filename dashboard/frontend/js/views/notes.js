// Notes section view — same role as views/wiki.js or views/labs.js.
// Step 4 ESM: platform search-field + library toolbar chrome; window.NotesHost kept.

import { h, setTitle } from "../ui.js";
import { icon } from "../icons.js";

import "../table.js";
import "../splitpanes.js";
import "../search-fields.js";
import "../editor-state.js";
import "../draft-recovery.js";
import "../action-menu.js";
import "./notes/workspace-toolbar.js";
import "./notes/host.js"; // pulls notes-context + projects

let ready = null;
let host = null;
let booted = false;
let project = null;

function createHost() {
  const input = h("input", {
    id: "workspace-search",
    type: "search",
    class: "filter-input",
    placeholder: "Filter projects…",
    autocomplete: "off",
    "aria-label": "Filter projects",
  });
  const root = h("div", { id: "workspace", class: "workspace", hidden: true },
    h("div", { id: "workspace-search-bank" },
      h("label", { class: "search-field workspace-search" }, icon("search", "search-glyph"), input)),
    h("main", { class: "workspace-main" },
      h("div", { id: "workspace-content", class: "content" })),
    h("output", { class: "workspace-toast", id: "workspace-toast", role: "status", hidden: true }),
    h("dialog", { id: "workspace-modal", class: "workbench-dialog" }),
  );
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
