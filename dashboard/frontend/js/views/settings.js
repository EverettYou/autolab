// site.json, laid out like the JSON viewer. Each value is an open field.
// The API key is always blank on the page. Leaving it untouched keeps the key
// already in the file and does not copy one in from the environment.

import { api, post } from "../api.js";
import { rememberSite } from "../site-config.js";
import { h, pageHeader, setTitle } from "../ui.js";

function editString(value, secret) {
  const long = !secret && (value.includes("\n") || value.length > 80);
  const input = long
    ? h("textarea", { class: "json-edit-area", rows: "4", spellcheck: "false" }, value)
    : h("input", {
      class: "json-edit", type: secret ? "password" : "text", autocomplete: "off", spellcheck: "false",
      value,
    });
  const state = { changed: false, read: () => input.value };
  input.addEventListener("input", () => { state.changed = true; });
  return { input, state };
}

function editBoolean(value) {
  let current = value;
  const button = h("button", { type: "button", class: "json-bool json-edit-bool" }, current ? "true" : "false");
  button.addEventListener("click", () => {
    current = !current;
    button.textContent = current ? "true" : "false";
  });
  return { input: button, read: () => current };
}

function editNumber(value) {
  const input = h("input", { class: "json-edit json-num", type: "text", autocomplete: "off", spellcheck: "false", value: String(value) });
  return {
    input,
    read() {
      const text = input.value.trim();
      if (text === "") return null;
      const number = Number(text);
      return Number.isFinite(number) ? number : text;
    },
  };
}

function row(key, valueNode) {
  return h("div", { class: "json-line" }, h("span", { class: "json-key" }, key), h("span", { class: "json-val" }, valueNode));
}

function field(key, value, secrets) {
  if (value === null) return { node: row(key, h("span", { class: "json-none" }, "none")), read: () => null };
  if (Array.isArray(value)) {
    const label = value.length === 1 ? "1 item" : `${value.length} items`;
    return { node: row(key, h("span", { class: "json-meta" }, label)), read: () => value };
  }
  if (typeof value === "object") {
    const children = Object.entries(value).map(([name, item]) => ({ name, ...field(name, item, secrets) }));
    const count = children.length;
    const preview = count === 1 ? "1 field" : `${count} fields`;
    return {
      node: h("details", { class: "json-entry", open: true },
        h("summary", { class: "json-line" },
          h("span", { class: "json-key" }, key),
          h("span", { class: "json-val" },
            h("span", { class: "json-preview json-meta" }, preview),
            h("span", { class: "json-chevron", "aria-hidden": "true" }))),
        h("div", { class: "json-children" }, children.map((child) => child.node))),
      read: () => Object.fromEntries(children.map((child) => [child.name, child.read()])),
    };
  }
  if (typeof value === "boolean") {
    const edited = editBoolean(value);
    return { node: row(key, edited.input), read: edited.read };
  }
  if (typeof value === "number") {
    const edited = editNumber(value);
    return { node: row(key, edited.input), read: edited.read };
  }
  const secret = key === "api_key";
  const edited = editString(secret ? "" : String(value ?? ""), secret);
  if (secret) secrets.push(edited.state);
  return { node: row(key, edited.input), read: () => edited.state.read() };
}

function documentEditor(document) {
  const secrets = [];
  const fields = Object.entries(document || {}).map(([key, value]) => ({ key, ...field(key, value, secrets) }));
  return {
    node: h("div", { class: "json-view" },
      h("div", { class: "json-doc" }, fields.map((item) => item.node))),
    read: () => Object.fromEntries(fields.map((item) => [item.key, item.read()])),
    keyChanged: () => secrets.some((state) => state.changed),
    clearSecrets() {
      for (const input of this.node.querySelectorAll("input[type=password]")) input.value = "";
      for (const state of secrets) state.changed = false;
    },
  };
}

export async function render({ signal }) {
  const data = await api("settings", {}, { signal });
  setTitle("Settings");
  const editor = documentEditor(data.document || {});
  const error = h("p", { class: "form-error settings-error", hidden: true });
  const button = h("button", { class: "btn btn-primary", type: "button" }, "Save");
  button.addEventListener("click", async () => {
    error.hidden = true;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Saving…";
    try {
      const saved = await post("settings", { document: editor.read(), api_key_changed: editor.keyChanged() });
      if (saved && saved.document) rememberSite(saved.document);
      editor.clearSecrets();
      button.textContent = "Saved";
      window.setTimeout(() => { button.textContent = original; }, 1200);
    } catch (err) {
      error.hidden = false;
      error.textContent = (err && err.message) || "Could not save settings.";
      button.textContent = original;
    }
    button.disabled = false;
  });
  return h("div", { class: "page narrow" },
    pageHeader({ kicker: "site.json", title: "Settings", actions: button }),
    editor.node,
    error);
}
